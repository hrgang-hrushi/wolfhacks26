"""Pull NCDOT pavement condition layers statewide and join them.

    uv run python src/pipeline/pull_ncdot.py              # county check, pull both layers, join
    uv run python src/pipeline/pull_ncdot.py --force      # re-pull even if the parquet exists
    uv run python src/pipeline/pull_ncdot.py --join-only  # redo the join from cached parquet

Outputs
    data/raw/ncdot_master.parquet     NCDOT_PMS_Network_Master_PCS layer 0
    data/raw/ncdot_asphalt.parquet    NCDOT_Asphalt_PCS layer 0
    data/processed/segments.parquet   master segments + matched asphalt columns (asph_*)
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

BASE = "https://gis11.services.ncdot.gov/arcgis/rest/services"
LAYERS = {
    "master": f"{BASE}/NCDOT_PMS_Network_Master_PCS/MapServer/0",
    "asphalt": f"{BASE}/NCDOT_Asphalt_PCS/MapServer/0",
}
PAGE = 2000
MP_TOL = 0.01

_session = requests.Session()


def _get(url: str, params: dict, tries: int = 5) -> dict:
    for attempt in range(tries):
        try:
            r = _session.get(url, params=params, timeout=180)
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise RuntimeError(data["error"])
            return data
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def county_string(pattern: str = "Buncombe") -> list[str]:
    """One query against the master layer; returns the exact COUNTY value(s) matching pattern."""
    data = _get(
        f"{LAYERS['master']}/query",
        {
            "where": f"COUNTY LIKE '%{pattern}%'",
            "outFields": "COUNTY",
            "returnDistinctValues": "true",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    return sorted({f["attributes"]["COUNTY"] for f in data["features"]})


def _page(layer_url: str, offset: int) -> list[dict]:
    data = _get(
        f"{layer_url}/query",
        {
            "where": "OBJECTID>0",
            "outFields": "*",
            "outSR": 4326,
            "f": "geojson",
            "orderByFields": "OBJECTID",
            "resultRecordCount": PAGE,
            "resultOffset": offset,
        },
    )
    return data["features"]


def pull_layer(name: str, out: Path, workers: int = 4) -> gpd.GeoDataFrame:
    url = LAYERS[name]
    count = _get(f"{url}/query", {"where": "OBJECTID>0", "returnCountOnly": "true", "f": "json"})["count"]
    offsets = range(0, count, PAGE)
    feats: list[dict] = []
    with ThreadPoolExecutor(workers) as pool:
        for page in tqdm(pool.map(lambda o: _page(url, o), offsets), total=len(offsets), desc=name):
            feats.extend(page)

    gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
    gdf = gdf.drop(columns=[c for c in ("GEOM.STLength()", "GDB_GEOMATTR_DATA") if c in gdf.columns])
    # the asphalt layer serves these two as strings
    for col in ("LENGTH", "LANE_MILES"):
        if col in gdf.columns:
            gdf[col] = pd.to_numeric(gdf[col], errors="coerce")

    n_unique = gdf["OBJECTID"].nunique()
    if len(gdf) != count or n_unique != count:
        raise RuntimeError(f"{name}: server count {count}, pulled {len(gdf)} rows, {n_unique} unique OBJECTIDs")
    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(out)
    return gdf


def join_layers(master: gpd.GeoDataFrame, asphalt: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Left-join asphalt survey rows onto master segments on ROUTEID + BEG_MP + END_MP (±MP_TOL)."""
    # ROUTEID is not comparable as served: master is ROUTE + 3-digit county code ("...011"),
    # asphalt is ROUTE + 2-digit zero-based county index ("...10"). Rebuild asphalt's in master form.
    a = pd.DataFrame(asphalt.drop(columns="geometry"))
    a["route_key"] = a["ROUTE"] + a["SAP_COUNTY"].astype(int).astype(str).str.zfill(3)

    pairs = master[["OBJECTID", "ROUTEID", "BEG_MP", "END_MP"]].merge(
        a[["OBJECTID", "route_key", "BEG_MP", "END_MP"]],
        left_on="ROUTEID",
        right_on="route_key",
        suffixes=("", "_a"),
    )
    d_beg = (pairs["BEG_MP"] - pairs["BEG_MP_a"]).abs()
    d_end = (pairs["END_MP"] - pairs["END_MP_a"]).abs()
    eps = 1e-9  # mileposts are 3-decimal floats
    pairs = pairs[(d_beg <= MP_TOL + eps) & (d_end <= MP_TOL + eps)].assign(d=d_beg + d_end)

    # closest pair wins; a row on either side is used at most once
    pairs = pairs.sort_values("d", kind="stable")
    used_m: set[int] = set()
    used_a: set[int] = set()
    keep = []
    for om, oa in zip(pairs["OBJECTID"], pairs["OBJECTID_a"]):
        ok = om not in used_m and oa not in used_a
        keep.append(ok)
        if ok:
            used_m.add(om)
            used_a.add(oa)
    pairs = pairs[keep]

    seg = master.merge(pairs[["OBJECTID", "OBJECTID_a"]], on="OBJECTID", how="left")
    seg = seg.merge(
        a.drop(columns="route_key").add_prefix("asph_"), left_on="OBJECTID_a", right_on="asph_OBJECTID", how="left"
    ).drop(columns="OBJECTID_a")
    mp = lambda s: (s * 1000).round().astype(int).astype(str).str.zfill(6)  # noqa: E731
    seg.insert(0, "seg_id", seg["ROUTEID"] + "_" + mp(seg["BEG_MP"]) + "_" + mp(seg["END_MP"]))
    if not seg["seg_id"].is_unique:
        raise RuntimeError("seg_id (ROUTEID_BEG_END) is not unique in the master layer")

    n = len(pairs)
    yr = master["PCS_SRVY_YR"].eq(asphalt["SRVY_YR"].max())
    print(f"raw ROUTEID values shared by both layers: {len(set(master['ROUTEID']) & set(asphalt['ROUTEID']))}")
    print(f"matched pairs (normalized ROUTEID, ±{MP_TOL} mi): {n:,}")
    print(f"  asphalt rows matched: {n / len(asphalt):.2%} ({n:,}/{len(asphalt):,})")
    print(f"  master rows matched:  {n / len(master):.2%} ({n:,}/{len(master):,})")
    print(f"  master rows surveyed {int(asphalt['SRVY_YR'].max())} matched: {n / yr.sum():.2%} ({n:,}/{yr.sum():,})")
    return seg


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-pull layers even if the parquet exists")
    ap.add_argument("--join-only", action="store_true", help="skip the pull, join cached parquet")
    args = ap.parse_args()

    if not args.join_only:
        print(f"Buncombe COUNTY string: {county_string('Buncombe')!r}")

    layers = {}
    for name in LAYERS:
        out = RAW / f"ncdot_{name}.parquet"
        if out.exists() and not args.force or args.join_only:
            layers[name] = gpd.read_parquet(out)
            print(f"{name}: {len(layers[name]):,} rows (cached {out.relative_to(ROOT)})")
        else:
            t0 = time.perf_counter()
            layers[name] = pull_layer(name, out)
            print(f"{name}: {len(layers[name]):,} rows -> {out.relative_to(ROOT)} in {time.perf_counter() - t0:.0f}s")

    seg = join_layers(layers["master"], layers["asphalt"])
    out = PROCESSED / "segments.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    seg.to_parquet(out)
    print(f"segments: {len(seg):,} rows -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
