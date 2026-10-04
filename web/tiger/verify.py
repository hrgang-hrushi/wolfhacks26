"""Check that the database holds what the files say.

Usage:  python -m web.tiger.verify [--schema unwatched]
Exit:   0 every check passed; 1 a check failed; 2 the database could not be reached (the kind is printed).

The files are rebuilt in memory and compared with the database: counts, blanks, buckets, time ranges, each running
summary against a recompute, compression, and a sample of roads value by value. The load record's file
fingerprints are compared first; if a file changed since the load the check says which and stops there.
Rows added by the storm replay (replay_of set) are left out of every comparison.
"""
import argparse
from collections import namedtuple
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg
from psycopg import sql

from web.tiger import build, config
from web.tiger import schema as tables

Check = namedtuple("Check", "name ok detail")
EXAMPLE_ROAD = "ncdot:40002748092:0.940"      # the road followed in the README
SAMPLE = 200


def _frame(conn, query, params=None):
    cur = conn.execute(query, params)
    return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


def _one(conn, query, params=None):
    return conn.execute(query, params).fetchone()[0]


def _same(a, b):
    """Two cells are the same: both blank, or equal (floats within rounding)."""
    a_blank, b_blank = a is None or a is pd.NA or a is pd.NaT or a != a, b is None or b is pd.NA or b is pd.NaT or b != b
    if a_blank or b_blank:
        return bool(a_blank and b_blank)
    if isinstance(a, (float, np.floating)) or isinstance(b, (float, np.floating)):
        return bool(np.isclose(float(a), float(b), rtol=1e-9, atol=1e-9))
    return a == b


def _compare(db, want, keys, values, label):
    """Outer-merge on the keys (blank keys kept) and compare every value. Returns (ok, detail)."""
    if len(db) != len(want):
        return False, f"{label}: {len(db):,} rows in the database, {len(want):,} recomputed"
    fill = "∅"
    a = db.assign(**{k: db[k].astype(object).where(db[k].notna(), fill) for k in keys})
    b = want.assign(**{k: want[k].astype(object).where(want[k].notna(), fill) for k in keys})
    m = a.merge(b, on=keys, how="outer", suffixes=("_db", "_want"), indicator=True)
    if (m._merge != "both").any():
        return False, f"{label}: {int((m._merge != 'both').sum()):,} rows do not pair up"
    for v in values:
        bad = [i for i, (x, y) in enumerate(zip(m[v + "_db"], m[v + "_want"])) if not _same(x, y)]
        if bad:
            return False, f"{label}: {len(bad):,} rows differ in {v}"
    return True, f"{label}: {len(db):,} rows equal a recompute from the files"


def recompute_summaries(built):
    """The three running summaries, computed from the built tables with pandas."""
    r = built.tables["camera_readings"]
    cam = (r.assign(bucket=r.time.dt.floor("h")).groupby(["bucket", "camera_id"], as_index=False)
           .agg(worst_p_flooded=("p_flooded", "max"), worst_depth_pred_cm=("depth_pred_cm", "max"),
                worst_depth_measured_cm=("depth_measured_cm", "max"), readings=("time", "size"),
                first_reading=("time", "min"), last_reading=("time", "max")))
    s = built.tables["sensor_levels"]
    sen = (s.assign(bucket=s.time.dt.floor("h")).groupby(["bucket", "station"], as_index=False)
           .agg(highest_level_m=("level_m", "max"), mean_level_m=("level_m", "mean"),
                worst_depth_on_road_cm=("depth_on_road_cm", "max"), readings=("time", "size"),
                first_reading=("time", "min"), last_reading=("time", "max")))
    p = built.tables["pothole_reports"]
    month = p.time.dt.tz_localize(None).dt.to_period("M").dt.to_timestamp().dt.tz_localize("UTC")
    pot = (p.assign(bucket=month).groupby(["bucket", "seg_id", "source"], as_index=False, dropna=False)
           .agg(reports=("report_id", "size")))
    return {"camera_hourly": cam, "sensor_hourly": sen, "pothole_monthly": pot}


SUMMARY_KEYS = {"camera_hourly": ["bucket", "camera_id"], "sensor_hourly": ["bucket", "station"],
                "pothole_monthly": ["bucket", "seg_id", "source"]}


def summary_checks(conn, built):
    want = recompute_summaries(built)
    out = []
    for view, keys in SUMMARY_KEYS.items():
        values = [c for c in want[view].columns if c not in keys]
        where = sql.SQL(" WHERE NOT is_replay") if view != "pothole_monthly" else sql.SQL("")
        db = _frame(conn, sql.SQL("SELECT {} FROM {}").format(
            sql.SQL(", ").join(map(sql.Identifier, keys + values)), sql.Identifier(view)) + where)
        for c in db.columns:
            if str(db[c].dtype) == "object" and c in ("readings", "reports", "mean_level_m"):
                db[c] = pd.to_numeric(db[c])
        if "bucket" in db and len(db):
            db["bucket"] = pd.to_datetime(db.bucket, utc=True)
        ok, detail = _compare(db, want[view], keys, values, view)
        if ok and view == "pothole_monthly" and int(db.reports.sum()) != len(built.tables["pothole_reports"]):
            ok, detail = False, f"{view}: the monthly counts add up to {int(db.reports.sum()):,}, not every report"
        out.append(Check(f"summary {view}", ok, detail))
    return out


def checks(conn, schema, root):
    """(name, ok, detail) rows. `conn` must have its search path on `schema`."""
    out = []
    root = Path(root)
    row = conn.execute("SELECT id, status, sources, timescaledb_version, compression FROM load_manifest "
                       "ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return [Check("load record", False, "the database has no load record")]
    _, status, sources, version, recorded = row
    out.append(Check("load record", status == "complete", f"status is {status}"))
    recorded = recorded or {}
    whole = bool(version) and set(recorded) == set(tables.HYPERTABLES) and all(
        isinstance(c, dict) and c.get("bytes_before") and c.get("bytes_after") for c in recorded.values())
    out.append(Check("load record holds the version and the measured sizes", whole,
                     f"TimescaleDB {version}; sizes recorded for {sorted(recorded)}" if whole
                     else f"version {version!r}; sizes recorded for {sorted(recorded)}"))

    now = build.fingerprints(root)
    changed = sorted(f for f in set(now) | set(sources) if now.get(f, {}).get("sha256") != sources.get(f, {}).get("sha256"))
    out.append(Check("files unchanged since the load", not changed,
                     "every source file matches the load record" if not changed else f"changed since the load: {changed}"))
    if changed:
        out.append(Check("comparison with the files", False, "skipped: the files are not the ones that were loaded"))
        return out

    built = build.build_all(root)
    roads = built.tables["roads"]

    counts = {
        "roads": _one(conn, "SELECT count(*) FROM roads"), "road_shapes": _one(conn, "SELECT count(*) FROM road_shapes"),
        "cameras": _one(conn, "SELECT count(*) FROM cameras"),
        "camera_readings": _one(conn, "SELECT count(*) FROM camera_readings WHERE replay_of IS NULL"),
        "sensor_levels": _one(conn, "SELECT count(*) FROM sensor_levels WHERE replay_of IS NULL"),
        "pothole_reports": _one(conn, "SELECT count(*) FROM pothole_reports"),
    }
    out.append(Check("row counts", counts == built.counts, ", ".join(f"{k} {v:,}" for k, v in counts.items())
                     if counts == built.counts else f"database {counts} but the files give {built.counts}"))

    blanks = {c: _one(conn, sql.SQL("SELECT count(*) FROM roads WHERE {} IS NULL").format(sql.Identifier(c)))
              for c in ("pred_years_to_poor", "treatment_cost", "pred_flood", "rating")}
    want_blanks = {c: int(roads[c].isna().sum()) for c in blanks}
    out.append(Check("blanks stay blank", blanks == want_blanks, f"database {blanks}, files {want_blanks}"))

    buckets = dict(conn.execute("SELECT repair_bucket, count(*) FROM roads GROUP BY 1").fetchall())
    want_buckets = roads.repair_bucket.value_counts().to_dict()
    out.append(Check("repair buckets", buckets == want_buckets, str({b: buckets.get(b, 0) for b in tables.BUCKETS})))

    held = conn.execute("SELECT count(*) FILTER (WHERE rate_heldout), count(*) FILTER (WHERE crack_heldout), "
                        "count(*) FILTER (WHERE flood_heldout) FROM roads").fetchone()
    want_held = tuple(int(roads[c].sum()) for c in ("rate_heldout", "crack_heldout", "flood_heldout"))
    out.append(Check("held-out flags", tuple(held) == want_held, f"rate {held[0]:,}, cracking {held[1]:,}, flood {held[2]:,}"))

    zone = conn.execute("SELECT count(*), count(*) FILTER (WHERE helene_damaged) FROM roads WHERE in_helene_zone").fetchone()
    top = _one(conn, "SELECT count(*) FILTER (WHERE helene_damaged) FROM (SELECT helene_damaged FROM roads "
                     "WHERE in_helene_zone ORDER BY pred_flood DESC, seg_id LIMIT 50) t")
    z = roads[roads.in_helene_zone].sort_values(["pred_flood", "seg_id"], ascending=[False, True])
    want_zone = (len(z), int(z.helene_damaged.sum()), int(z.head(50).helene_damaged.sum()))
    out.append(Check("Helene numbers", (zone[0], zone[1], top) == want_zone,
                     f"{zone[0]:,} roads in the zone, {zone[1]:,} damaged, {top} damaged in the 50 riskiest"))

    ranges_ok, parts = True, []
    for table in tables.HYPERTABLES:
        where = sql.SQL(" WHERE replay_of IS NULL") if table != "pothole_reports" else sql.SQL("")
        lo, hi = conn.execute(sql.SQL("SELECT min(time), max(time) FROM {}").format(sql.Identifier(table)) + where).fetchone()
        t = built.tables[table].time
        ranges_ok &= (pd.Timestamp(lo) == t.min() and pd.Timestamp(hi) == t.max())
        parts.append(f"{table} {t.min():%Y-%m-%d %H:%M} to {t.max():%Y-%m-%d %H:%M}")
    out.append(Check("time ranges (UTC)", bool(ranges_ok), "; ".join(parts)))

    out.extend(summary_checks(conn, built))

    live = dict(conn.execute("SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates "
                             "WHERE view_schema = %s", [schema]).fetchall())
    out.append(Check("summaries include new rows", set(live) == set(tables.SUMMARIES) and not any(live.values()),
                     "real-time aggregation is on for all three" if not any(live.values()) and len(live) == 3 else str(live)))

    comp = {t: conn.execute(sql.SQL("SELECT number_compressed_chunks, total_chunks, before_compression_total_bytes, "
                                    "after_compression_total_bytes FROM hypertable_columnstore_stats({})")
                            .format(sql.Literal(t))).fetchone() for t in tables.HYPERTABLES}
    comp_ok = all(c and (c[0] or 0) >= 1 for c in comp.values())
    out.append(Check("compression", comp_ok, "; ".join(
        f"{t} {c[0] or 0} of {c[1] or 0} chunks" + (f", {c[2]:,} -> {c[3]:,} bytes" if c[2] and c[3] else "") for t, c in comp.items())))

    ids = roads.seg_id.sample(min(SAMPLE, len(roads)), random_state=0).tolist()
    if EXAMPLE_ROAD in set(roads.seg_id):
        ids.append(EXAMPLE_ROAD)
    cols = tables.columns("roads")
    db = _frame(conn, sql.SQL("SELECT {} FROM roads WHERE seg_id = ANY(%s)").format(sql.SQL(", ").join(map(sql.Identifier, cols))),
                [ids]).set_index("seg_id")
    want = roads[roads.seg_id.isin(ids)].set_index("seg_id")
    wrong = [(i, c) for i in want.index for c in cols[1:] if i not in db.index or not _same(db.at[i, c], want.at[i, c])]
    out.append(Check("road values", not wrong and len(db) == len(want),
                     f"{len(want)} roads equal the files, column by column" if not wrong else f"{len(wrong)} cells differ, e.g. {wrong[:3]}"))

    replay = _one(conn, "SELECT (SELECT count(*) FROM camera_readings WHERE replay_of IS NOT NULL) + "
                        "(SELECT count(*) FROM sensor_levels WHERE replay_of IS NOT NULL)")
    out.append(Check("storm replay rows", True, f"{replay:,} present (left out of every check above)"))
    return out


def run(url, schema, root=Path(".")):
    conn = config.connect(url, schema=schema, read_only=True)
    try:
        return checks(conn, schema, root)
    finally:
        conn.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check the Tiger Data service against the project's files.")
    ap.add_argument("--schema", default=None, help="database schema (default: TIGER_SCHEMA or 'unwatched')")
    args = ap.parse_args(argv)
    try:
        url = config.database_url()
        results = run(url, args.schema or config.schema_name())
    except config.ConfigError as e:
        print(e)
        return 2
    except (config.DatabaseUnavailable, psycopg.Error) as e:
        print(config.describe(e))
        return 2
    for c in results:
        print(f"{'ok  ' if c.ok else 'FAIL'} {c.name}: {c.detail}")
    failed = [c for c in results if not c.ok]
    print(f"{len(results) - len(failed)} of {len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
