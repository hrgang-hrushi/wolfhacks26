"""Load the tables into the Tiger Data service.

Usage:  python -m web.tiger.load [--schema unwatched]
        python -m web.tiger.load --dump-dir DIR      write CSV files and SQL scripts instead (for Tiger's browser console)

Four steps:
  1. Setup: tables, time-partitioned tables, running summaries, policies. Safe to run twice.
  2. One transaction: empty every table, copy the new rows in, write a load record with status `loaded`.
     A failure here rolls back, so the database keeps the previous complete data or none.
  3. Refresh every running summary over the whole time range (this cannot run inside a transaction).
  4. Compress the old chunks, read the sizes back, set the load record to `complete`.
The service and the check treat any status other than `complete` as "loading".

The connection string is never printed.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from web.tiger import build, config
from web.tiger import schema as tables

DATA_TABLES = list(tables.TABLES)
STOP_POINTS = ("copy", "refresh_one", "refresh")


def code_version():
    """Short commit id, with -dirty when there are uncommitted changes. 'unknown' outside a git checkout."""
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, timeout=10).stdout.strip()
        return (head + ("-dirty" if dirty else "")) if head else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def copy_table(cur, table, frame):
    """COPY by column name, so the frame's column order cannot swap two columns."""
    cols = tables.columns(table)
    stmt = sql.SQL("COPY {} ({}) FROM STDIN").format(sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, cols)))
    with cur.copy(stmt) as copy:
        for row in build.to_rows(frame, cols):
            copy.write_row(row)


def refresh(conn, views=None):
    """Bring the running summaries up to date over everything, old data included."""
    for view in (views or tables.SUMMARIES):
        conn.execute(sql.SQL("CALL refresh_continuous_aggregate({}, NULL, NULL)").format(sql.Literal(view)))


def compress_chunks(conn):
    """Convert every chunk older than the newest chunk-length of data. One call per chunk."""
    for table, h in tables.HYPERTABLES.items():
        newest = conn.execute(sql.SQL("SELECT max(time) FROM {}").format(sql.Identifier(table))).fetchone()[0]
        if newest is None:
            continue
        chunks = conn.execute(sql.SQL("SELECT c::text FROM show_chunks({}, older_than => %s::timestamptz - %s::interval) c")
                              .format(sql.Literal(table)), [newest, h["chunk"]]).fetchall()
        for (chunk,) in chunks:
            conn.execute(sql.SQL("CALL convert_to_columnstore({}::regclass, if_not_columnstore => true)").format(sql.Literal(chunk)))


def compression_stats(conn):
    """{table: chunks, compressed chunks, bytes before and after, ratio}. Blanks mean nothing is compressed yet."""
    out = {}
    for table in tables.HYPERTABLES:
        row = conn.execute(sql.SQL("SELECT total_chunks, number_compressed_chunks, before_compression_total_bytes, "
                                   "after_compression_total_bytes FROM hypertable_columnstore_stats({})")
                           .format(sql.Literal(table))).fetchone()
        total, done, before, after = row if row else (0, 0, None, None)
        out[table] = {"chunks": int(total or 0), "compressed_chunks": int(done or 0),
                      "bytes_before": None if before is None else int(before),
                      "bytes_after": None if after is None else int(after),
                      "ratio": round(before / after, 2) if before and after else None}
    return out


def load(url, root=Path("."), schema=None, *, schedule_jobs=True, compress=True, stop_after=None, _before_commit=None):
    """Build from `root`, then load. Returns a summary dict. `stop_after` stops a load at a known point (tests only)."""
    name = config.check_schema_name(schema) if schema else config.schema_name()
    if stop_after not in (None, *STOP_POINTS):
        raise ValueError(f"stop_after must be one of {STOP_POINTS}")
    t0 = time.time()
    built = build.build_all(root)                       # every refusal happens before the database is touched
    t_build = time.time() - t0

    admin = config.connect(url, autocommit=True, schema=None)
    try:
        info = tables.setup(admin, name, schedule_jobs=schedule_jobs)
        t1 = time.time()
        conn = config.connect(url, schema=name)
        try:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("TRUNCATE {}").format(sql.SQL(", ").join(map(sql.Identifier, DATA_TABLES))))
                for table in DATA_TABLES:
                    copy_table(cur, table, built.tables[table])
                manifest_id = cur.execute(
                    "INSERT INTO load_manifest (status, sources, row_counts, code_version, timescaledb_version) "
                    "VALUES ('loaded', %s, %s, %s, %s) RETURNING id",
                    [Jsonb(built.fingerprints), Jsonb(built.counts), code_version(), info["timescaledb_version"]]).fetchone()[0]
                if _before_commit is not None:
                    _before_commit()
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except psycopg.Error:
                pass                                    # a broken connection: keep the first error
            raise
        finally:
            conn.close()
        t_copy = time.time() - t1
        summary = {"schema": name, "manifest_id": manifest_id, "status": "loaded", "counts": built.counts,
                   "sensor_values_dropped": built.sensor_values_dropped, "seconds_build": round(t_build, 1),
                   "seconds_copy": round(t_copy, 1), "timescaledb_version": info["timescaledb_version"]}
        if stop_after == "copy":
            return summary
        views = list(tables.SUMMARIES)
        refresh(admin, views[:1])
        if stop_after == "refresh_one":
            return summary
        refresh(admin, views[1:])
        if stop_after == "refresh":
            return summary
        if compress:
            compress_chunks(admin)
        stats = compression_stats(admin)
        admin.execute("UPDATE load_manifest SET status = 'complete', finished_at = now(), compression = %s WHERE id = %s",
                      [Jsonb(stats), manifest_id])
        size = admin.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        summary.update(status="complete", compression=stats, database_size_bytes=int(size), seconds_total=round(time.time() - t0, 1))
        return summary
    finally:
        admin.close()


def dump(root, out_dir, schema=None):
    """Per-table CSV files and two SQL scripts, for loading through Tiger's browser console when its port is blocked.

    Order in the console: run setup.sql (it creates everything, empties the tables and writes a load record with
    status `loaded`, so the service answers "loading"), import each CSV into its table, run after_load.sql (it
    refreshes the summaries, compresses, and sets the record to `complete`). Running the three again reloads cleanly."""
    import csv
    name = config.check_schema_name(schema) if schema else config.schema_name()   # before anything is written
    out_dir = Path(out_dir)
    built = build.build_all(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    for table, frame in built.tables.items():
        cols = tables.columns(table)
        with open(out_dir / f"{table}.csv", "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(cols)
            for row in build.to_rows(frame, cols):
                w.writerow(["" if v is None else (v.isoformat() if hasattr(v, "isoformat") else v) for v in row])
    setup = [f"CREATE SCHEMA IF NOT EXISTS {name};", f"SET search_path = {name}, public;"]
    setup += [text + ";" for _, text in tables.statements()]
    # the console runs each statement on its own: the record goes in first, so the tables are never empty under a
    # load that still reads as complete
    setup.append("INSERT INTO load_manifest (status, sources, row_counts, code_version) VALUES ('loaded', "
                 f"'{json.dumps(built.fingerprints)}'::jsonb, '{json.dumps(built.counts)}'::jsonb, '{code_version()}');")
    setup.append("TRUNCATE " + ", ".join(DATA_TABLES) + ";")
    (out_dir / "setup.sql").write_text("\n".join(setup) + "\n")
    after = [f"SET search_path = {name}, public;"]
    after += [f"CALL refresh_continuous_aggregate('{v}', NULL, NULL);" for v in tables.SUMMARIES]
    for table, h in tables.HYPERTABLES.items():
        after.append(f"DO $$ DECLARE c regclass; BEGIN FOR c IN SELECT show_chunks('{table}', older_than => "
                     f"(SELECT max(time) FROM {table}) - INTERVAL '{h['chunk']}') LOOP "
                     f"CALL convert_to_columnstore(c, if_not_columnstore => true); END LOOP; END $$;")
    after.append("UPDATE load_manifest SET status = 'complete', finished_at = now() "
                 "WHERE id = (SELECT max(id) FROM load_manifest) AND status = 'loaded';")
    (out_dir / "after_load.sql").write_text("\n".join(after) + "\n")
    return built.counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="Load the dashboard tables into the Tiger Data service.")
    ap.add_argument("--schema", default=None, help="database schema (default: TIGER_SCHEMA or 'unwatched')")
    ap.add_argument("--dump-dir", default=None, help="write CSV files and SQL scripts here instead of loading")
    args = ap.parse_args(argv)
    if args.dump_dir:
        counts = dump(Path("."), args.dump_dir, schema=args.schema)
        print(f"wrote {len(counts)} CSV files and two SQL scripts: {counts}")
        return 0
    try:
        url = config.database_url()
        s = load(url, Path("."), schema=args.schema)
    except config.ConfigError as e:
        print(e)
        return 2
    except config.DatabaseUnavailable as e:
        print(f"{e} ({e.kind})")
        return 2
    except tables.SetupRefused as e:
        print(e)
        return 3
    except psycopg.Error as e:
        print(config.describe(e))
        return 2
    print(f"schema {s['schema']}: {s['status']}")
    for table, n in s["counts"].items():
        print(f"  {table}: {n:,} rows")
    print(f"  built in {s['seconds_build']} s, copied in {s['seconds_copy']} s, {s.get('seconds_total', '?')} s in all")
    for table, c in s.get("compression", {}).items():
        ratio = "not compressed yet" if c["ratio"] is None else f"{c['bytes_before']:,} -> {c['bytes_after']:,} bytes ({c['ratio']}x)"
        print(f"  {table}: {c['compressed_chunks']} of {c['chunks']} chunks compressed, {ratio}")
    if "database_size_bytes" in s:
        print(f"  database size: {s['database_size_bytes'] / 1e6:.1f} MB; TimescaleDB {s['timescaledb_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
