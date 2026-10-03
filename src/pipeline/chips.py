"""Cut one 128x128 4-band NAIP 2022 chip per segment midpoint from Planetary Computer.

    uv run python -m src.pipeline.chips --limit 50   # smoke test on a random 50 segments
    uv run python -m src.pipeline.chips              # every segment (resumes; skips existing chips)

Each chip is data/chips/{seg_id}.npy with ':' in the seg_id written as '_' (ncdot_{ROUTEID}_{BEG_MP}.npy,
see chip_path): uint8, shape (4, 128, 128), bands R, G, B, NIR at the native 0.6 m (about 77 m on a
side), centred on the segment midpoint. Chips are read with windowed COG range requests; segments
are grouped by NAIP tile so each COG is opened once.
"""

from __future__ import annotations

import argparse
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "3")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "1")

import geopandas as gpd
import numpy as np
import planetary_computer
import pystac_client
import rasterio
import shapely
from pyproj import Transformer
from rasterio.windows import Window
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
SEGMENTS = ROOT / "data" / "raw" / "ncdot_joined.parquet"
CHIPS = ROOT / "data" / "chips"
INDEX = ROOT / "data" / "raw" / "naip_2022_index.parquet"

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
NC_BBOX = [-84.35, 33.80, -75.40, 36.62]
YEAR = 2022
SIZE = 128
LOG_EVERY_S = 5.0


def chip_path(seg_id: str) -> Path:
    """Chip file for a segment. ':' is not a legal filename character on Windows."""
    return CHIPS / f"{seg_id.replace(':', '_')}.npy"


def naip_index(refresh: bool = False) -> gpd.GeoDataFrame:
    """Footprint, href and CRS of every NC NAIP tile for YEAR (one STAC crawl, then cached)."""
    if INDEX.exists() and not refresh:
        return gpd.read_parquet(INDEX)
    t0 = time.perf_counter()
    search = pystac_client.Client.open(STAC).search(
        collections=["naip"],
        bbox=NC_BBOX,
        datetime=f"{YEAR}-01-01/{YEAR}-12-31",
        query={"naip:state": {"eq": "nc"}},
        limit=500,
    )
    rows = []
    for it in search.items_as_dicts():
        props = it["properties"]  # older items carry proj:epsg instead of proj:code
        crs = props.get("proj:code") or f"EPSG:{props['proj:epsg']}"
        rows.append({"item_id": it["id"], "href": it["assets"]["image"]["href"], "crs": crs, "geometry": shape(it["geometry"])})
    index = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    index.to_parquet(INDEX)
    print(f"indexed {len(index):,} NAIP {YEAR} tiles in {time.perf_counter() - t0:.0f}s -> {INDEX.relative_to(ROOT)}")
    return index


def plan(segments: Path, limit: int | None, seed: int, overwrite: bool) -> gpd.GeoDataFrame:
    """One row per chip to cut: seg_id, midpoint lon/lat, and the NAIP tile that covers it."""
    seg = gpd.read_parquet(segments, columns=["seg_id", "geometry"])
    if limit is not None and limit < len(seg):
        # random rather than head(): the file is ordered by county, and a spread of tiles is
        # what makes the smoke-test timing representative
        seg = seg.sample(limit, random_state=seed)
    mid = shapely.line_interpolate_point(seg.geometry.values, 0.5, normalized=True)
    pts = gpd.GeoDataFrame(seg[["seg_id"]], geometry=mid, crs=seg.crs)
    if not overwrite:
        pts = pts[[not chip_path(s).exists() for s in pts["seg_id"]]]
    joined = pts.sjoin(naip_index(), predicate="within", how="left")
    # tiles overlap at their edges; any one covering tile will do
    joined = joined[~joined.index.duplicated()].drop(columns="index_right")
    joined["lon"], joined["lat"] = joined.geometry.x, joined.geometry.y
    return joined


def cut_tile(href: str, crs: str, chips: list[tuple[str, float, float]]) -> list[tuple[str, str | None]]:
    """Open one NAIP COG and save every chip that falls on it. Returns (seg_id, error or None)."""
    results: list[tuple[str, str | None]] = []
    try:
        to_tile = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        # sign per open: SAS tokens expire after ~1 h, the library caches and renews them
        with rasterio.open(planetary_computer.sign(href)) as ds:
            for seg_id, lon, lat in chips:
                try:
                    row, col = ds.index(*to_tile.transform(lon, lat))
                    win = Window(col - SIZE // 2, row - SIZE // 2, SIZE, SIZE)
                    chip = ds.read(window=win, boundless=True, fill_value=0)
                    if chip.shape != (4, SIZE, SIZE):
                        raise ValueError(f"unexpected chip shape {chip.shape}")
                    out = chip_path(seg_id)
                    tmp = out.with_suffix(".npy.tmp")
                    with open(tmp, "wb") as f:
                        np.save(f, chip)
                    tmp.replace(out)
                    results.append((seg_id, None))
                except Exception as e:  # keep going; one bad window should not sink the tile
                    results.append((seg_id, f"{type(e).__name__}: {e}"))
    except Exception as e:
        done = {s for s, _ in results}
        results += [(s, f"{type(e).__name__}: {e}") for s, _, _ in chips if s not in done]
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None, help="only cut chips for a random N segments")
    ap.add_argument("--seed", type=int, default=0, help="seed for the --limit sample")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--segments", type=Path, default=SEGMENTS)
    ap.add_argument("--overwrite", action="store_true", help="recut chips that already exist")
    ap.add_argument("--refresh-index", action="store_true", help="re-crawl the NAIP tile index")
    args = ap.parse_args()

    CHIPS.mkdir(parents=True, exist_ok=True)
    if args.refresh_index:
        naip_index(refresh=True)
    todo = plan(args.segments, args.limit, args.seed, args.overwrite)
    uncovered = todo[todo["href"].isna()]
    todo = todo[todo["href"].notna()]
    groups = [
        (href, crs, list(zip(g["seg_id"], g["lon"], g["lat"])))
        for (href, crs), g in todo.groupby(["href", "crs"], sort=False)
    ]
    total = len(todo)
    print(
        f"{total:,} chips to cut from {len(groups):,} NAIP tiles with {args.workers} workers"
        + (f" ({len(uncovered):,} midpoints outside NAIP {YEAR} coverage)" if len(uncovered) else ""),
        flush=True,
    )
    if total == 0:
        return

    t0 = time.perf_counter()
    ok = 0
    failed: list[tuple[str, str]] = []
    last_log = t0
    lock = threading.Lock()

    def log(final: bool = False) -> None:
        done = ok + len(failed)
        elapsed = time.perf_counter() - t0
        rate = done / elapsed if elapsed else 0.0
        eta = (total - done) / rate if rate else float("inf")
        tail = f"done in {elapsed:.1f}s" if final else f"eta {eta / 60:.1f} min"
        print(f"[chips] {done:,}/{total:,} ({done / total:.1%})  {rate:.1f} chips/s  {len(failed)} failed  {tail}", flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(cut_tile, *g) for g in groups]
        for fut in as_completed(futures):
            with lock:
                for seg_id, err in fut.result():
                    if err is None:
                        ok += 1
                    else:
                        failed.append((seg_id, err))
                if time.perf_counter() - last_log >= LOG_EVERY_S:
                    log()
                    last_log = time.perf_counter()
    log(final=True)

    if failed:
        out = CHIPS / "_failed.csv"
        out.write_text("seg_id,error\n" + "\n".join(f'{s},"{e}"' for s, e in failed) + "\n")
        print(f"{len(failed)} failures listed in {out.relative_to(ROOT)}; rerun to retry them")


if __name__ == "__main__":
    main()
