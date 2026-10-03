"""Fetch 3DEP 30 m elevation for the NC bbox and derive slope + flow accumulation.

    uv run python -m src.pipeline.dem              # fetch (skipped if dem.tif exists), then terrain
    uv run python -m src.pipeline.dem --force      # refetch the DEM
    uv run python -m src.pipeline.dem --workers 1  # lower peak memory (~3 GB per worker)

Outputs in data/processed/dem/, all EPSG:32119 (NC State Plane, metres), 30 m, float32
    dem.tif       elevation, m (3DEP 1 arc-second seamless, bilinear-resampled)
    slope.tif     D8 downslope gradient, m/m        (pysheds cell_slopes)
    flowacc.tif   D8 flow accumulation, cell count  (pysheds accumulation; x900 for m^2)

pysheds works in float64/int64 and needs ~15 full-size arrays at its peak, so the statewide grid
(~290M cells) is processed in tiles: each CORE x CORE window is run with a HALO of extra cells on
every side and only the core is kept. Accumulation therefore counts upstream cells out to the halo
(~15 km) only; main stems of large rivers are undercounted, local drainage is not.
"""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_CACHEMAX", "1024")

import numpy as np
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rasterio.windows import Window
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed" / "dem"

NC_BBOX = (-84.35, 33.80, -75.40, 36.62)  # lon/lat, slightly padded
DST_CRS = "EPSG:32119"
RES = 30.0
CORE = 4096  # px; multiple of the 512 px GeoTIFF block
HALO = 512  # px of upstream context (~15 km) around each core

TIF = dict(driver="GTiff", count=1, dtype="float32", nodata=np.nan, tiled=True, blockxsize=512,
           blockysize=512, compress="zstd", predictor=3, BIGTIFF="IF_SAFER")  # fmt: skip


def fetch_dem(out: Path) -> dict[str, float]:
    """Download the 1 arc-second DEM with py3dep, resample to 30 m State Plane, write dem.tif."""
    import py3dep

    t0 = time.perf_counter()
    da = py3dep.static_3dep_dem(NC_BBOX, 4326, 30)
    src = np.ascontiguousarray(da.values, dtype=np.float32)
    src_transform, src_crs = da.rio.transform(), da.rio.crs
    left, bottom, right, top = da.rio.bounds()
    del da
    t_fetch = time.perf_counter() - t0
    print(f"fetched {src.shape[1]:,} x {src.shape[0]:,} px ({src.nbytes / 1e9:.2f} GB) in {t_fetch:.0f}s", flush=True)

    t0 = time.perf_counter()
    transform, width, height = calculate_default_transform(
        src_crs, DST_CRS, src.shape[1], src.shape[0], left, bottom, right, top, resolution=RES
    )
    dst = np.full((height, width), np.nan, dtype=np.float32)
    reproject(src, dst, src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=transform, dst_crs=DST_CRS, dst_nodata=np.nan,
              resampling=Resampling.bilinear, num_threads=os.cpu_count())  # fmt: skip
    del src
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_suffix(".partial.tif")
    with rasterio.open(partial, "w", height=height, width=width, crs=DST_CRS, transform=transform, **TIF) as dst_ds:
        dst_ds.write(dst, 1)
    partial.replace(out)
    t_write = time.perf_counter() - t0
    print(f"resampled to {width:,} x {height:,} px @ {RES:.0f} m and wrote {out.name} in {t_write:.0f}s", flush=True)
    return {"fetch_s": t_fetch, "resample_write_s": t_write}


def _terrain_tile(job: tuple[str, int, int, int, int]) -> tuple[int, int, np.ndarray, np.ndarray, int]:
    """Run pysheds on one core window plus halo; return slope, accumulation and sink count for the core."""
    from pysheds.grid import Grid
    from pysheds.view import Raster, ViewFinder

    dem_path, row, col, h, w = job
    with rasterio.open(dem_path) as src:
        r0, c0 = max(row - HALO, 0), max(col - HALO, 0)
        r1, c1 = min(row + h + HALO, src.height), min(col + w + HALO, src.width)
        win = Window(c0, r0, c1 - c0, r1 - r0)
        dem = src.read(1, window=win).astype(np.float64)
        transform, crs = src.window_transform(win), src.crs
    core = np.s_[row - r0 : row - r0 + h, col - c0 : col - c0 + w]

    valid = np.isfinite(dem)
    if not valid[core].any():
        nan = np.full((h, w), np.nan, dtype=np.float32)
        return row, col, nan, nan, 0

    # resolve_flats lifts flat cells by eps per step, up to 3 * max_iter (3000) steps. If the total
    # lift can exceed a real elevation difference, flats rise above their neighbours and new sinks
    # appear; float32 resampling noise on lake and river surfaces (differences of ~1e-5 m) does
    # exactly that at the default eps and cuts the flow network. Snap to 1 cm and keep the total
    # lift under 1 cm so it cannot happen.
    dem = np.round(dem, 2)
    vf = ViewFinder(affine=transform, shape=dem.shape, crs=crs.to_wkt(), nodata=np.nan)
    grid = Grid(viewfinder=vf)
    flooded = grid.fill_depressions(grid.fill_pits(Raster(dem, vf)))
    fdir = grid.flowdir(grid.resolve_flats(flooded, eps=1e-6))
    # cells left without a flow direction, away from the window edge where flow simply exits
    sinks = (np.asarray(fdir) < 0) & valid
    sinks[[0, -1], :] = sinks[:, [0, -1]] = False
    n_sinks = int(sinks[core].sum())
    acc = np.asarray(grid.accumulation(fdir), dtype=np.float32)[core]
    # flats resolved by resolve_flats can come out a hair negative on the filled surface
    slope = np.maximum(np.asarray(grid.cell_slopes(flooded, fdir), dtype=np.float32)[core], 0)
    acc[~valid[core]] = np.nan
    slope[~valid[core]] = np.nan
    return row, col, slope, acc, n_sinks


def terrain(dem_path: Path, workers: int) -> float:
    """Tile the DEM through pysheds and mosaic slope.tif and flowacc.tif."""
    t0 = time.perf_counter()
    with rasterio.open(dem_path) as src:
        profile = dict(height=src.height, width=src.width, crs=src.crs, transform=src.transform, **TIF)
        jobs = [
            (str(dem_path), row, col, min(CORE, src.height - row), min(CORE, src.width - col))
            for row in range(0, src.height, CORE)
            for col in range(0, src.width, CORE)
        ]
    # write beside the final names and swap in at the end: a failed run leaves the previous rasters
    # intact, and nothing rewrites a large file in place (in-place rewrites time out in iCloud-synced folders)
    tmp = {name: OUT / f"{name}.partial.tif" for name in ("slope", "flowacc")}
    with (
        rasterio.open(tmp["slope"], "w", **profile) as slope_ds,
        rasterio.open(tmp["flowacc"], "w", **profile) as acc_ds,
        ProcessPoolExecutor(workers) as pool,
    ):
        n_sinks = 0
        for row, col, slope, acc, sinks in tqdm(pool.map(_terrain_tile, jobs), total=len(jobs), desc="terrain tiles"):
            win = Window(col, row, slope.shape[1], slope.shape[0])
            slope_ds.write(slope, 1, window=win)
            acc_ds.write(acc, 1, window=win)
            n_sinks += sinks
    for name, path in tmp.items():
        path.replace(OUT / f"{name}.tif")
    elapsed = time.perf_counter() - t0
    print(f"slope.tif + flowacc.tif from {len(jobs)} tiles in {elapsed:.0f}s; {n_sinks:,} interior sink cells", flush=True)
    return elapsed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="refetch the DEM even if dem.tif exists")
    ap.add_argument("--workers", type=int, default=2, help="terrain tile processes (~3 GB RAM each)")
    args = ap.parse_args()

    dem_path = OUT / "dem.tif"
    timings: dict[str, float] = {}
    if args.force or not dem_path.exists():
        timings.update(fetch_dem(dem_path))
    else:
        print(f"{dem_path.relative_to(ROOT)} exists, skipping fetch (--force to refetch)")
    timings["terrain_s"] = terrain(dem_path, args.workers)
    print("timings: " + ", ".join(f"{k}={v:.0f}s" for k, v in timings.items()) + f", total={sum(timings.values()):.0f}s")


if __name__ == "__main__":
    main()
