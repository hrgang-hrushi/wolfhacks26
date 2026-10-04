"""Build the static data files that both dashboards read.

Run from the repo root:

    uv run python scripts/build_web_data.py

Reads handoff/predictions_geo.parquet (committed) and, when they are present on
this machine, three files that are not committed:

    data/raw/ncdot_joined.parquet    route, county, mileposts, rating, treatment, cost
    handoff/traffic_crash.parquet    traffic count or estimate (committed)
    data/raw/helene_labels.parquet   what Helene actually damaged (for the backtest)

Writes web/public/data/ (git-ignored, regenerate before deploying):

    stats.json          statewide counts, tier counts, county table, shard index
    overview.json       the ~5,000 highest-priority roads, for zoomed-out views
    shards/<cell>.json  every road, bucketed on a 0.25 degree grid
    detail/<cell>.json  per-road NCDOT record fields, loaded when a road is opened
    ranked.json         top 1,000 roads in each of the three action tiers
    county/<code>.json  every action-tier road in one county, plus its SR index
    routes.json         where each Interstate / US / NC route is; which counties have an SR number
    storm.json          the 300 highest flood scores in the Helene zone
    backtest.json       the 50 highest held-out flood scores and what happened to them

Nothing here is invented. A field that cannot be joined is left out, and the
script says so.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[1]
PRED = ROOT / "handoff" / "predictions_geo.parquet"
JOINED = ROOT / "data" / "raw" / "ncdot_joined.parquet"
TRAFFIC = ROOT / "handoff" / "traffic_crash.parquet"
HELENE = ROOT / "data" / "raw" / "helene_labels.parquet"
PRIORITY = ROOT / "web" / "src" / "lib" / "priority.json"
OUT = ROOT / "web" / "public" / "data"

CELL_DEG = 0.25          # shard grid size in degrees
QUANT = 100_000          # coordinates are stored as round(degrees * 1e5)
OVERVIEW_N = 5_000       # roads in the zoomed-out file
OVERVIEW_SIMPLIFY = 0.0002  # degrees (~20 m); zoomed-out view only
RANKED_PER_TIER = 1_000
STORM_N = 300
BACKTEST_N = 50
MARKER = ".generated"  # tells the script the output folder is its own

TIER_KEYS = ["fix_now", "within_year", "within_five", "monitor", "no_estimate"]
ROUTE_CLASS = {"1": "I", "2": "US", "3": "NC", "4": "SR"}

# Numbers copied from README.md. Do not edit them here without editing the README.
README_METRICS = {
    "source": "README.md, section 'Does it work?' (5-fold spatial block cross-validation on a 5 km grid)",
    "wear_mae": {
        "label": "Wear rate: typical miss, rating points a year (lower is better)",
        "no_model": 0.965, "baseline": 0.753, "with_terrain": 0.749,
    },
    "crack_aucpr": {
        "label": "Cracking: how well it ranks cracked roads first, 0 to 1 (higher is better)",
        "no_model": 0.158, "baseline": 0.377, "with_terrain": 0.422,
    },
    "helene_top50": {
        "label": "Helene damage: of the 50 roads ranked riskiest in the storm zone, how many were damaged",
        "no_model": 2, "baseline": 13, "with_terrain": 18,
    },
}

# The worked example in README.md ("Follow one road through the model").
README_FEATURED = {
    "source": "README.md, section 'Follow one road through the model'",
    "route": "40002748", "county": "092",
    "rating": 73.4, "survey_year": 2025, "resurfaced": 2010, "aadt": 1600,
    "wear_actual": 1.77, "wear_predicted": 1.62, "years_to_poor": 8,
    "crack_top_pct": 13, "length_mi": 1.7,
}


# ---------------------------------------------------------------- tier logic

def load_priority() -> dict:
    return json.loads(PRIORITY.read_text())


def tier_index(ytp, crack, flood, hz, cfg) -> np.ndarray:
    """0 fix now, 1 within a year, 2 within five years, 3 monitor, 4 no estimate.

    Mirrors tierOf() in web/src/lib/data.ts. Missing years-to-Poor never
    satisfies a years test; flood counts only inside the Helene zone.
    """
    t = cfg["tiers"]
    ytp = np.asarray(ytp, dtype=float)
    crack = np.asarray(crack, dtype=float)
    flood = np.asarray(flood, dtype=float)
    hz = np.asarray(hz).astype(bool)
    has = ~np.isnan(ytp)
    fix = (has & (ytp <= t["fix_now"]["ytp_max"])) | (crack >= t["fix_now"]["crack_min"]) \
        | (hz & (flood >= t["fix_now"]["flood_min"]))
    year = (has & (ytp <= t["within_year"]["ytp_max"])) | (crack >= t["within_year"]["crack_min"])
    five = has & (ytp <= t["within_five"]["ytp_max"])
    out = np.where(has, 3, 4)
    out = np.where(five, 2, out)
    out = np.where(year, 1, out)
    out = np.where(fix, 0, out)
    return out.astype(np.int8)


def priority_score(ytp, crack, flood, hz, cfg) -> np.ndarray:
    """0 to 1. Mirrors scoreOf() in web/src/lib/data.ts."""
    s = cfg["score"]
    ytp = np.asarray(ytp, dtype=float)
    h = float(s["ytp_horizon_years"])
    ytp_part = np.where(np.isnan(ytp), 0.0, 1.0 - np.minimum(np.nan_to_num(ytp, nan=h), h) / h)
    flood_part = np.where(np.asarray(hz).astype(bool), np.asarray(flood, dtype=float), 0.0)
    return s["w_ytp"] * ytp_part + s["w_crack"] * np.asarray(crack, dtype=float) + s["w_flood"] * flood_part


# ---------------------------------------------------------------- geometry

def cell_key(lng: float, lat: float) -> str:
    """Shard a point falls in. The client computes the same thing from a 5-decimal point."""
    return f"{math.floor((lng + 180.0) / CELL_DEG)}_{math.floor((lat + 90.0) / CELL_DEG)}"


def encode_path(coords: np.ndarray) -> list[int]:
    """[lng, lat] pairs -> flat ints: first pair is round(deg * 1e5), the rest are deltas."""
    q = np.rint(np.asarray(coords, dtype=float)[:, :2] * QUANT).astype(np.int64)
    if len(q) > 1:
        keep = np.ones(len(q), dtype=bool)
        keep[1:] = np.any(q[1:] != q[:-1], axis=1)
        q = q[keep]
    if len(q) == 1:  # a stretch shorter than a metre collapses to a point; keep it drawable
        q = np.vstack([q, q])
    d = np.empty_like(q)
    d[0] = q[0]
    d[1:] = q[1:] - q[:-1]
    return d.reshape(-1).tolist()


def decode_path(flat: list[int]) -> np.ndarray:
    a = np.asarray(flat, dtype=np.int64).reshape(-1, 2)
    return np.cumsum(a, axis=0) / QUANT


def encode_geom(geom) -> list:
    """LineString -> one flat path. MultiLineString -> list of flat paths."""
    if geom.geom_type == "LineString":
        return encode_path(shapely.get_coordinates(geom))
    return [encode_path(shapely.get_coordinates(part)) for part in geom.geoms]


def midpoint(geoms: np.ndarray) -> np.ndarray:
    """Point half way along each line, rounded to 5 decimals (N, 2)."""
    pts = shapely.line_interpolate_point(geoms, 0.5, normalized=True)
    xy = shapely.get_coordinates(pts)
    if len(xy) != len(geoms):  # multi-part lines do not interpolate; fall back one by one
        xy = np.array([
            shapely.get_coordinates(
                g.interpolate(0.5, normalized=True) if g.geom_type == "LineString" else g.representative_point()
            )[0]
            for g in geoms
        ])
    return np.round(xy, 5)


# ---------------------------------------------------------------- helpers

def num(v, nd):
    """Rounded float, or None for missing."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), nd)


def dump(path: Path, obj) -> tuple[int, int]:
    """Write compact JSON. Returns (raw bytes, gzip bytes)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, separators=(",", ":"), allow_nan=False).encode()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    return len(raw), len(gzip.compress(raw, 6))


def route_label(route: str) -> str:
    """'40002748' -> 'SR 2748'. Class digit and the number in characters 4 to 8 are all we claim."""
    cls = ROUTE_CLASS.get(route[0], "Route")
    n = int(route[3:8])
    return f"I-{n}" if cls == "I" else f"{cls} {n}"


def seg_record(r) -> dict:
    """One road as the map sees it."""
    ho = (1 if r.rate_heldout else 0) | (2 if r.crack_heldout else 0) | (4 if r.flood_heldout else 0)
    rec = {
        "id": r.seg_id,
        "path": None,  # filled by the caller
        "rate": num(r.pred_rate, 2),
        "ytp": num(r.pred_years_to_poor, 2),
        "crack": num(r.pred_crack, 3),
        "hz": int(r.in_helene_zone),
        "ho": ho,
    }
    if r.in_helene_zone:  # outside the zone the flood score means nothing, so it is not shipped
        rec["flood"] = num(r.pred_flood, 4)
    return rec


def list_row(r, has_join: bool) -> dict:
    """One road as the work queue sees it (no geometry)."""
    row = {
        "id": r.seg_id, "t": int(r.tier), "s": num(r.score, 4),
        "rate": num(r.pred_rate, 2), "ytp": num(r.pred_years_to_poor, 2), "crack": num(r.pred_crack, 3),
        "hz": int(r.in_helene_zone),
        "ho": (1 if r.rate_heldout else 0) | (2 if r.crack_heldout else 0) | (4 if r.flood_heldout else 0),
        "c": [float(r.mx), float(r.my)],
    }
    if r.in_helene_zone:
        row["flood"] = num(r.pred_flood, 4)
    if has_join:
        row.update(detail_fields(r))
    return row


def detail_fields(r) -> dict:
    """Real NCDOT record fields. Missing values are dropped, never filled in."""
    d = {
        "bmp": num(r.BEG_MP, 3), "emp": num(r.END_MP, 3), "len": num(r.LENGTH, 3),
        "fr": r.FROM_DESC if isinstance(r.FROM_DESC, str) else None,
        "to": r.TO_DESC if isinstance(r.TO_DESC, str) else None,
        "rtg": num(r.RTG_NBR, 1), "sy": int(r.PCS_SRVY_YR),
        "ry": None if pd.isna(r.YEAR_LAST_REHAB) else int(r.YEAR_LAST_REHAB),
        "ln": int(r.NUMBER_OF_LANES),
        "trt": r.PMS_TREATMENT_NAME if isinstance(r.PMS_TREATMENT_NAME, str) else None,
        "cost": None if pd.isna(r.TREATMENT_COST) else int(round(r.TREATMENT_COST)),
    }
    aadt = getattr(r, "tr_aadt_best", float("nan"))
    if not pd.isna(aadt):
        d["aadt"] = int(round(aadt))
        d["as"] = r.tr_aadt_best_source  # 'count' or 'estimate'
    return {k: v for k, v in d.items() if v is not None}


def hist(values: np.ndarray, step: float, top: float, side: str) -> list[int]:
    """Counts per bin of width `step` from 0 to `top`, built so a threshold count is exact.

    side='le': bin k holds ((k-1)*step, k*step], so sum(counts[:k+1]) == count(v <= k*step).
    side='ge': bin k holds [k*step, (k+1)*step), so sum(counts[k:])   == count(v >= k*step).
    """
    n = int(round(top / step))
    q = np.asarray(values, dtype=float) / step
    idx = np.ceil(q - 1e-9) if side == "le" else np.floor(q + 1e-9)
    idx = np.clip(idx.astype(int), 0, n)
    return np.bincount(idx, minlength=n + 1).tolist()


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    out: Path = args.out

    cfg = load_priority()
    import geopandas as gpd

    g = gpd.read_parquet(PRED)
    assert g.crs is not None and g.crs.to_epsg() == 4326, f"expected EPSG:4326, got {g.crs}"
    assert g.seg_id.is_unique
    n_total = len(g)
    print(f"predictions: {n_total:,} roads")

    # Round once, here, to the precision the files carry. Tiers, scores and counts are then
    # worked out from exactly the numbers the dashboards show, so "1.0 years" can never sit
    # in a different tier than the one the screen implies. Ranking by flood keeps full precision.
    g["flood_raw"] = g.pred_flood
    g["pred_rate"] = g.pred_rate.round(2)
    g["pred_years_to_poor"] = g.pred_years_to_poor.round(2)
    g["pred_crack"] = g.pred_crack.round(3)
    g["pred_flood"] = g.pred_flood.round(4)

    has_join = JOINED.exists()
    if has_join:
        cols = ["seg_id", "COUNTY", "ROUTE", "BEG_MP", "END_MP", "FROM_DESC", "TO_DESC", "LENGTH",
                "NUMBER_OF_LANES", "RTG_NBR", "PCS_SRVY_YR", "YEAR_LAST_REHAB",
                "PMS_TREATMENT_NAME", "TREATMENT_COST"]
        import pyarrow.parquet as pq
        have = set(pq.ParquetFile(JOINED).schema_arrow.names)
        missing = [c for c in cols if c not in have]
        if missing:
            print(f"!! {JOINED.name} lacks {missing}; route, county, treatment and cost are left out")
            has_join = False
        else:
            j = pd.read_parquet(JOINED, columns=cols)
            g = g.merge(j, on="seg_id", how="left", validate="one_to_one")
            assert g.ROUTE.notna().all(), "some roads have no NCDOT record"
    else:
        print(f"!! {JOINED} not found; route, county, treatment and cost are left out")

    if has_join and TRAFFIC.exists():
        t = pd.read_parquet(TRAFFIC, columns=["seg_id", "tr_aadt_best", "tr_aadt_best_source"])
        g = g.merge(t, on="seg_id", how="left", validate="one_to_one")
        g.loc[g.tr_aadt_best_source == "none", "tr_aadt_best"] = np.nan

    # Flood is not a claim outside the Helene zone.
    hz = g.in_helene_zone.to_numpy().astype(bool)
    g["tier"] = tier_index(g.pred_years_to_poor, g.pred_crack, g.pred_flood, hz, cfg)
    g["score"] = priority_score(g.pred_years_to_poor, g.pred_crack, g.pred_flood, hz, cfg)

    geoms = g.geometry.to_numpy()
    mid = midpoint(geoms)
    g["mx"], g["my"] = mid[:, 0], mid[:, 1]
    g["cell"] = [cell_key(x, y) for x, y in mid]
    g["cls"] = g.seg_id.str.slice(6, 7)   # 'ncdot:' + ROUTE(8) + county(3) + ':' + milepost
    g["cty"] = g.seg_id.str.slice(14, 17)
    if has_join:
        assert (g.seg_id.str.slice(6, 14) == g.ROUTE).all(), "seg_id does not start with ROUTE"
        assert (g.cty == g.COUNTY.str.slice(0, 3)).all(), "seg_id county code does not match COUNTY"

    if out.exists():
        # Only ever wipe a folder this script wrote.
        if any(out.iterdir()) and not (out / MARKER).exists():
            raise SystemExit(f"{out} is not empty and was not written by this script; refusing to delete it")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("Generated by scripts/build_web_data.py. Safe to delete.\n")

    # ---- shards + detail -------------------------------------------------
    print("encoding geometry ...")
    paths = [encode_geom(geom) for geom in geoms]
    g["ix"] = np.arange(n_total)

    cells: dict[str, dict] = {}
    tot_raw = tot_gz = det_raw = det_gz = 0
    for key, part in g.groupby("cell", sort=True):
        segs = []
        detail = {}
        for r in part.itertuples(index=False):
            rec = seg_record(r)
            p = paths[r.ix]
            if p and isinstance(p[0], list):
                rec.pop("path")
                rec["paths"] = p
            else:
                rec["path"] = p
            segs.append(rec)
            if has_join:
                detail[r.seg_id] = detail_fields(r)
        raw, gz = dump(out / "shards" / f"{key}.json", {"cell": key, "segs": segs})
        cells[key] = {"n": len(segs), "gz": gz}
        tot_raw += raw
        tot_gz += gz
        if has_join:
            raw, gz = dump(out / "detail" / f"{key}.json", detail)
            det_raw += raw
            det_gz += gz
    sizes = sorted(c["gz"] for c in cells.values())
    print(f"shards: {len(cells)} files, {tot_raw/1e6:.1f} MB raw, {tot_gz/1e6:.1f} MB gzip; "
          f"per shard gzip median {sizes[len(sizes)//2]/1e3:.0f} KB, max {sizes[-1]/1e3:.0f} KB")
    if has_join:
        print(f"detail: {det_raw/1e6:.1f} MB raw, {det_gz/1e6:.1f} MB gzip")

    # ---- ranking ---------------------------------------------------------
    order = g.sort_values(["tier", "score"], ascending=[True, False], kind="stable")

    # ---- storm list (Helene zone, by flood score) --------------------------
    zone = g[hz].sort_values("flood_raw", ascending=False, kind="stable")
    storm_rows = []
    for rank, r in enumerate(zone.head(STORM_N).itertuples(index=False), 1):
        row = list_row(r, has_join)
        row["rank"] = rank
        row["path"] = paths[r.ix]
        storm_rows.append(row)
    raw, gz = dump(out / "storm.json", {
        "n_zone": int(hz.sum()),
        "min_flood": num(zone.head(STORM_N).pred_flood.min(), 4),
        "rows": storm_rows,
    })
    print(f"storm.json: {len(storm_rows)} roads, {gz/1e3:.0f} KB gzip")

    # ---- overview ----------------------------------------------------------
    ov_ids = pd.Index(order.head(OVERVIEW_N).seg_id).union(zone.head(STORM_N).seg_id)
    ov = g[g.seg_id.isin(ov_ids)]
    ov_geoms = shapely.simplify(ov.geometry.to_numpy(), OVERVIEW_SIMPLIFY, preserve_topology=False)
    ov_segs = []
    for r, geom in zip(ov.itertuples(index=False), ov_geoms):
        rec = seg_record(r)
        p = encode_geom(geom)
        if p and isinstance(p[0], list):
            rec.pop("path")
            rec["paths"] = p
        else:
            rec["path"] = p
        ov_segs.append(rec)
    raw, gz = dump(out / "overview.json", {"cell": "overview", "segs": ov_segs})
    print(f"overview.json: {len(ov_segs):,} roads, {raw/1e3:.0f} KB raw, {gz/1e3:.0f} KB gzip")

    # ---- ranked.json ---------------------------------------------------------
    ranked = []
    for tier in (0, 1, 2):
        for r in order[order.tier == tier].head(RANKED_PER_TIER).itertuples(index=False):
            ranked.append(list_row(r, has_join))
    raw, gz = dump(out / "ranked.json", {"per_tier": RANKED_PER_TIER, "rows": ranked})
    print(f"ranked.json: {len(ranked):,} rows, {gz/1e3:.0f} KB gzip")

    # ---- county files + route index ------------------------------------------
    counties = {}
    if has_join:
        action = order[order.tier <= 2]
        co_raw = 0
        for code, part in g.groupby("cty", sort=True):
            name = part.COUNTY.iloc[0].split("-", 1)[1]
            b = part.geometry.total_bounds
            tc = np.bincount(part.tier, minlength=5).tolist()
            counties[code] = {
                "name": name, "n": len(part), "tiers": tc,
                "hz": int(part.in_helene_zone.sum()),
                "hf": int(((part.in_helene_zone == 1) & (part.pred_flood >= cfg["tiers"]["fix_now"]["flood_min"])).sum()),
                "b": [round(float(v), 4) for v in b],
            }
            sr = {}
            for route, rp in part[part.cls == "4"].groupby("ROUTE"):
                rb = rp.geometry.total_bounds
                sr[str(int(route[3:8]))] = [round(float(v), 4) for v in rb]
            rows = [list_row(r, True) for r in action[action.cty == code].itertuples(index=False)]
            raw, _ = dump(out / "county" / f"{code}.json", {"code": code, "name": name, "rows": rows, "sr": sr})
            co_raw += raw
        print(f"county files: {len(counties)}, {co_raw/1e6:.1f} MB raw, {len(action):,} action-tier roads")

        primary = {}
        for route, rp in g[g.cls != "4"].groupby("ROUTE"):
            lab = route_label(route)
            rb = rp.geometry.total_bounds
            e = primary.get(lab)
            if e is None:
                primary[lab] = {"b": [float(v) for v in rb], "n": len(rp)}
            else:  # same class and number under several route codes (direction, business, ...)
                e["b"] = [min(e["b"][0], rb[0]), min(e["b"][1], rb[1]), max(e["b"][2], rb[2]), max(e["b"][3], rb[3])]
                e["n"] += len(rp)
        for e in primary.values():
            e["b"] = [round(float(v), 4) for v in e["b"]]
        sr_counties: dict[str, list[str]] = {}
        srp = g[g.cls == "4"]
        for (route, code), _ in srp.groupby(["ROUTE", "cty"]):
            sr_counties.setdefault(str(int(route[3:8])), []).append(code)
        raw, gz = dump(out / "routes.json", {
            "primary": primary,
            "sr": {k: " ".join(sorted(set(v))) for k, v in sr_counties.items()},
        })
        print(f"routes.json: {len(primary)} primary routes, {len(sr_counties):,} SR numbers, {gz/1e3:.0f} KB gzip")

    # ---- backtest ----------------------------------------------------------
    backtest_summary = None
    if HELENE.exists():
        h = pd.read_parquet(HELENE, columns=["seg_id", "y_helene_failed"])
        z = zone[zone.flood_heldout].merge(h, on="seg_id", how="left", validate="one_to_one")
        assert z.y_helene_failed.notna().all(), "a Helene-zone road has no outcome label"
        top = z.head(BACKTEST_N)
        rows = []
        for rank, r in enumerate(top.itertuples(index=False), 1):
            row = list_row(r, has_join)
            row["rank"] = rank
            row["failed"] = int(r.y_helene_failed)
            row["path"] = paths[r.ix]
            rows.append(row)
        base = float(z.y_helene_failed.mean())
        backtest_summary = {
            "n": BACKTEST_N,
            "damaged": int(top.y_helene_failed.sum()),
            "zone_roads": int(len(z)),
            "zone_damaged": int(z.y_helene_failed.sum()),
            "expected_by_chance": round(BACKTEST_N * base, 1),
        }
        dump(out / "backtest.json", {**backtest_summary, "rows": rows})
        print(f"backtest.json: {backtest_summary['damaged']} of {BACKTEST_N} damaged; "
              f"{backtest_summary['zone_damaged']:,} of {backtest_summary['zone_roads']:,} in the zone "
              f"(about {backtest_summary['expected_by_chance']} of 50 by chance)")
        if backtest_summary["damaged"] != README_METRICS["helene_top50"]["with_terrain"]:
            print("!! backtest count differs from the README's 18 of 50. Check before showing it.")
    else:
        print(f"!! {HELENE} not found; backtest.json was NOT written (Model in action will be hidden)")

    # ---- featured example --------------------------------------------------
    featured = None
    if has_join:
        f = g[(g.ROUTE == README_FEATURED["route"]) & (g.cty == README_FEATURED["county"])]
        f = f[(f.RTG_NBR - README_FEATURED["rating"]).abs() < 0.05]
        if len(f) == 1:
            r = next(f.itertuples(index=False))
            crack_top = float((g.pred_crack >= r.pred_crack).mean() * 100)
            featured = {
                "id": r.seg_id, "c": [float(r.mx), float(r.my)], "path": paths[r.ix],
                "readme": README_FEATURED,
                "data": {"rate": num(r.pred_rate, 2), "ytp": num(r.pred_years_to_poor, 2),
                         "crack": num(r.pred_crack, 3), "crack_top_pct": round(crack_top, 1),
                         "rtg": num(r.RTG_NBR, 1), **detail_fields(r)},
            }
            print(f"featured road: {r.seg_id}  rating {r.RTG_NBR}  pred_rate {r.pred_rate:.2f}  "
                  f"ytp {r.pred_years_to_poor:.1f}  cracking top {crack_top:.1f}%")
        else:
            print(f"!! featured road (SR 2748, Wake, rating 73.4) matched {len(f)} rows; chip left out")

    # ---- stats -------------------------------------------------------------
    tier_counts = np.bincount(g.tier, minlength=5).tolist()
    cls_counts = {ROUTE_CLASS[k]: int(v) for k, v in g.cls.value_counts().sort_index().items()}
    stats = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "version": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"),
        "source": "handoff/predictions_geo.parquet" + (" + data/raw/ncdot_joined.parquet" if has_join else ""),
        "total": n_total,
        "has_join": has_join,
        "tiers": dict(zip(TIER_KEYS, tier_counts)),
        "classes": cls_counts,
        "helene": {
            "zone": int(hz.sum()),
            "high_flood": int((hz & (g.pred_flood >= cfg["tiers"]["fix_now"]["flood_min"])).sum()),
        },
        "heldout": {
            "rate": int(g.rate_heldout.sum()),
            "crack": int(g.crack_heldout.sum()),
            "flood": int(g.flood_heldout.sum()),
        },
        "no_ytp": int(g.pred_years_to_poor.isna().sum()),
        "avg": {
            "rate": num(g.pred_rate.clip(lower=0).mean(), 3),
            "ytp_median": num(g.pred_years_to_poor.median(), 1),
            "crack": num(g.pred_crack.mean(), 3),
        },
        "hist": {
            "ytp": {"step": 0.5, "counts": hist(g.pred_years_to_poor.dropna().to_numpy(), 0.5, 50, "le")},
            "crack": {"step": 0.01, "counts": hist(g.pred_crack.to_numpy(), 0.01, 1, "ge")},
            "flood_zone": {"step": 0.01, "counts": hist(g.pred_flood.to_numpy()[hz], 0.01, 1, "ge")},
        },
        "cell_deg": CELL_DEG,
        "cells": cells,
        "counties": counties,
        "backtest": backtest_summary,
        "featured": featured,
        "readme_metrics": README_METRICS,
        "files": {
            "overview_n": len(ov_segs), "ranked_per_tier": RANKED_PER_TIER, "storm_n": len(storm_rows),
        },
    }
    # The alert sliders count from these histograms; make sure they agree with a direct count.
    assert sum(stats["hist"]["ytp"]["counts"][:3]) == int((g.pred_years_to_poor <= 1).sum())
    assert sum(stats["hist"]["crack"]["counts"][60:]) == int((g.pred_crack >= 0.6).sum())
    assert sum(stats["hist"]["flood_zone"]["counts"][50:]) == stats["helene"]["high_flood"]
    raw, gz = dump(out / "stats.json", stats)
    print(f"stats.json: {raw/1e3:.0f} KB raw, {gz/1e3:.0f} KB gzip")

    # ---- sanity print --------------------------------------------------------
    print("\ntier counts")
    for k, v in zip(TIER_KEYS, tier_counts):
        print(f"  {k:<12} {v:>8,}  {v / n_total:6.1%}")
    print(f"Helene zone: {int(hz.sum()):,} roads, {stats['helene']['high_flood']} with flood score >= "
          f"{cfg['tiers']['fix_now']['flood_min']}")
    print(f"held-out: wear {stats['heldout']['rate']:,}, cracking {stats['heldout']['crack']:,}, "
          f"flood {stats['heldout']['flood']:,}")

    # A phone framed on Wake County: the shards a 0.55 x 0.8 degree window touches.
    w, s, e, n = -78.92, 35.42, -78.37, 36.12
    keys = {f"{cx}_{cy}"
            for cx in range(math.floor((w + 180) / CELL_DEG), math.floor((e + 180) / CELL_DEG) + 1)
            for cy in range(math.floor((s + 90) / CELL_DEG), math.floor((n + 90) / CELL_DEG) + 1)}
    wake = sum(cells[k]["gz"] for k in keys if k in cells)
    print(f"phone view on Raleigh / Wake: {len(keys & set(cells))} shards, {wake/1e3:.0f} KB gzip")
    total = sum(p.stat().st_size for p in out.rglob("*.json"))
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"wrote {shown}: {total/1e6:.1f} MB on disk")


if __name__ == "__main__":
    main()
