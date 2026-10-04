"""Fetch USGS 3DEP 10 m ground for the roads near the Helene high-water marks, as small tiles.

    python -m src.pipeline.helene_dem10 --list     # which tiles are needed
    python -m src.pipeline.helene_dem10            # fetch the missing ones (finished tiles are skipped)
    python -m src.pipeline.helene_dem10 --force    # fetch them all again

Output in data/processed/dem10_helene/: one GeoTIFF per 0.1 degree tile in the source grid (EPSG:4269,
1/3 arc-second, metres NAVD88, no resampling) with HALO_PX extra cells on every side, plus manifest.json
holding each tile's sha256, shape and grid. Only tiles that hold a mark or a sampled road point are
fetched. Reading refuses a missing, altered or wrong-resolution tile; there is no fall-back to the 30 m
ground of src/pipeline/dem.py, which is too coarse for depth (docs/specs/2026-10-03_helene-depth-map.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS as RioCRS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed" / "dem10_helene"

TILE_DEG = 0.1
HALO_PX = 3  # extra cells around each tile, so interpolation at a tile edge has real neighbours
PX_DEG = 1 / 10800  # 1/3 arc-second
RES_TOL = 1e-7
CRS = "EPSG:4269"
CACHE = 16  # tiles held in memory at once (about 4.7 MB each)
SOURCE = "USGS 3DEP 1/3 arc-second seamless DEM via py3dep.static_3dep_dem(resolution=10); metres, NAVD88"

TIF = dict(driver="GTiff", count=1, dtype="float32", nodata=np.nan, tiled=True, blockxsize=256,
           blockysize=256, compress="zstd", predictor=3)  # fmt: skip


class GroundError(RuntimeError):
    """The 10 m ground cannot be trusted or used as asked."""


class MissingTile(GroundError):
    """A tile that a point needs has not been fetched."""


# ---- tile arithmetic ----
def tile_of(lon, lat):
    """Integer (lat, lon) index of the 0.1 degree tile that holds each point."""
    ilat = np.floor(np.round(np.asarray(lat, dtype=float) / TILE_DEG, 9)).astype(int)
    ilon = np.floor(np.round(np.asarray(lon, dtype=float) / TILE_DEG, 9)).astype(int)
    return ilat, ilon


def tile_name(tile) -> str:
    return f"t_{int(tile[0]):+05d}_{int(tile[1]):+05d}.tif"


def tile_bounds(tile):
    """west, south, east, north of the tile itself, without the extra cells."""
    ilat, ilon = int(tile[0]), int(tile[1])
    return ilon * TILE_DEG, ilat * TILE_DEG, (ilon + 1) * TILE_DEG, (ilat + 1) * TILE_DEG


def fetch_bounds(tile):
    w, s, e, n = tile_bounds(tile)
    pad = HALO_PX * PX_DEG
    return w - pad, s - pad, e + pad, n + pad


def tiles_needed(lon, lat):
    """The sorted tiles that hold at least one of the points. Nothing is added 'to be safe'."""
    lon, lat = np.atleast_1d(np.asarray(lon, dtype=float)), np.atleast_1d(np.asarray(lat, dtype=float))
    ok = np.isfinite(lon) & np.isfinite(lat)
    ilat, ilon = tile_of(lon[ok], lat[ok])
    return sorted({(int(a), int(b)) for a, b in zip(ilat, ilon)})


def _covers(shape, transform, tile, margin_px) -> bool:
    """True when the grid reaches at least margin_px cells past the tile on every side."""
    w, s, e, n = tile_bounds(tile)
    west, north = transform.c, transform.f
    east, south = west + shape[1] * transform.a, north + shape[0] * transform.e
    m = margin_px * PX_DEG - 1e-9
    return west <= w - m and east >= e + m and south <= s - m and north >= n + m


# ---- fetching ----
def _fetch(bounds):
    """One window of the USGS 10 m grid: (array, affine transform, CRS). The only network call."""
    import py3dep

    da = py3dep.static_3dep_dem(tuple(bounds), 4326, 10)
    return np.asarray(da.values, dtype="float32"), da.rio.transform(), da.rio.crs


def check_reply(arr, transform, crs, tile) -> None:
    """Refuse a reply that is empty, blank, in another grid, or for another place."""
    name = tile_name(tile)
    if getattr(arr, "ndim", 0) != 2 or arr.size == 0:
        raise GroundError(f"{name}: the server sent an empty reply")
    if not np.isfinite(arr).any():
        raise GroundError(f"{name}: the reply holds no ground at all")
    if crs is None or RioCRS.from_user_input(crs).to_epsg() != 4269:
        raise GroundError(f"{name}: the reply is in {crs}, expected {CRS}")
    if transform.b != 0 or transform.d != 0:
        raise GroundError(f"{name}: the reply's grid is rotated")
    if abs(transform.a - PX_DEG) > RES_TOL or abs(-transform.e - PX_DEG) > RES_TOL:
        raise GroundError(f"{name}: wrong resolution ({transform.a:.3g} degree cells, expected {PX_DEG:.3g})")
    if not _covers(arr.shape, transform, tile, margin_px=1):
        raise GroundError(f"{name}: the reply does not cover the tile that was asked for")


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_tile(out, tile, arr, transform, crs=CRS) -> dict:
    """Write under a temporary name, then swap it in (the Desktop folder is synced). Returns the manifest entry."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / tile_name(tile)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with rasterio.open(tmp, "w", height=arr.shape[0], width=arr.shape[1], transform=transform,
                           crs=crs, **TIF) as ds:  # fmt: skip
            ds.write(np.asarray(arr, dtype="float32"), 1)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return {"sha256": sha256(path), "shape": [int(v) for v in arr.shape], "transform": [float(v) for v in tuple(transform)[:6]]}


def new_manifest() -> dict:
    return {"source": SOURCE, "crs": CRS, "px_deg": PX_DEG, "halo_px": HALO_PX, "tiles": {}}


def load_manifest(out) -> dict:
    path = Path(out) / "manifest.json"
    if not path.exists():
        raise GroundError(f"no 10 m ground at {path.parent}: run python -m src.pipeline.helene_dem10")
    return json.loads(path.read_text())


def save_manifest(out, manifest) -> None:
    path = Path(out) / "manifest.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    os.replace(tmp, path)


def _have(out, manifest, tile) -> bool:
    entry, path = manifest["tiles"].get(tile_name(tile)), Path(out) / tile_name(tile)
    return entry is not None and path.exists() and sha256(path) == entry["sha256"]


def pull(tiles, out=OUT, force=False, fetch=None, workers=4, say=lambda *_: None) -> int:
    """Fetch the tiles that are not already on disk and intact. A failed tile leaves no file and no entry."""
    fetch = fetch or _fetch
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(out) if (out / "manifest.json").exists() else new_manifest()
    todo = [t for t in tiles if force or not _have(out, manifest, t)]
    done, failure = 0, None
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        jobs = [(t, pool.submit(fetch, fetch_bounds(t))) for t in todo]
        for t, job in jobs:
            try:
                arr, transform, crs = job.result()
                check_reply(arr, transform, crs, t)
                manifest["tiles"][tile_name(t)] = write_tile(out, t, arr, transform, crs)
                save_manifest(out, manifest)
                done += 1
                say(f"  {tile_name(t)}  ({done}/{len(todo)})")
            except Exception as e:  # keep going so one bad tile does not waste the rest; raise at the end
                say(f"  {tile_name(t)}  FAILED: {e}")
                failure = failure or e
    if failure is not None:
        raise failure
    return done


# ---- reading ----
def _interp(arr, tr, lon, lat, method):
    col = (lon - tr.c) / tr.a - 0.5
    row = (lat - tr.f) / tr.e - 0.5
    h, w = arr.shape
    out = np.full(lon.shape, np.nan)
    if method == "nearest":
        i, j = np.floor(row + 0.5).astype(int), np.floor(col + 0.5).astype(int)
        ok = (i >= 0) & (i < h) & (j >= 0) & (j < w)
        out[ok] = arr[i[ok], j[ok]]
        return out
    if method != "bilinear":
        raise ValueError(f"unknown method {method!r}")
    i0, j0 = np.floor(row).astype(int), np.floor(col).astype(int)
    ok = (i0 >= 0) & (i0 < h - 1) & (j0 >= 0) & (j0 < w - 1)
    i, j, fr, fc = i0[ok], j0[ok], (row - i0)[ok], (col - j0)[ok]
    a = arr.astype("float64", copy=False)
    # a blank cell among the four makes the result blank (NaN times any weight stays NaN)
    out[ok] = (a[i, j] * (1 - fr) * (1 - fc) + a[i, j + 1] * (1 - fr) * fc
               + a[i + 1, j] * fr * (1 - fc) + a[i + 1, j + 1] * fr * fc)  # fmt: skip
    return out


class Ground:
    """10 m ground height at lon/lat points, read from the saved tiles."""

    def __init__(self, out=OUT):
        self.out = Path(out)
        self.manifest = load_manifest(self.out)
        self._cache: OrderedDict = OrderedDict()

    def _open(self, tile):
        tile = (int(tile[0]), int(tile[1]))
        if tile in self._cache:
            self._cache.move_to_end(tile)
            return self._cache[tile]
        name = tile_name(tile)
        entry, path = self.manifest["tiles"].get(name), self.out / name
        if entry is None or not path.exists():
            raise MissingTile(f"10 m ground tile {name} is missing from {self.out}: run python -m "
                              "src.pipeline.helene_dem10 (there is no fall-back to coarser ground)")  # fmt: skip
        if sha256(path) != entry["sha256"]:
            raise GroundError(f"{name} does not match the manifest: fetch it again with --force")
        with rasterio.open(path) as ds:
            arr, tr = ds.read(1), ds.transform
        if abs(tr.a - PX_DEG) > RES_TOL or abs(-tr.e - PX_DEG) > RES_TOL:
            raise GroundError(f"{name}: wrong resolution ({tr.a:.3g} degree cells, expected {PX_DEG:.3g})")
        if not _covers(arr.shape, tr, tile, margin_px=1):
            raise GroundError(f"{name} does not cover its tile")
        self._cache[tile] = (arr, tr)
        if len(self._cache) > CACHE:
            self._cache.popitem(last=False)
        return arr, tr

    def sample(self, lon, lat, tile=None, method="bilinear"):
        """Ground in metres at each point; NaN where a cell is blank or the point is not finite.

        `tile` forces one tile for every point (used to check that neighbouring tiles agree at a seam).
        `method="nearest"` returns the cell that holds the point; depths use the default, bilinear.
        """
        lon, lat = np.atleast_1d(np.asarray(lon, dtype=float)), np.atleast_1d(np.asarray(lat, dtype=float))
        out = np.full(lon.shape, np.nan)
        ok = np.flatnonzero(np.isfinite(lon) & np.isfinite(lat))
        if tile is not None:
            arr, tr = self._open(tile)
            out[ok] = _interp(arr, tr, lon[ok], lat[ok], method)
            return out
        ilat, ilon = tile_of(lon[ok], lat[ok])
        order = np.lexsort((ilon, ilat))
        ilat, ilon, ok = ilat[order], ilon[order], ok[order]
        cut = np.flatnonzero((np.diff(ilat) != 0) | (np.diff(ilon) != 0)) + 1
        for idx in np.split(np.arange(len(ok)), cut):
            if len(idx) == 0:
                continue
            arr, tr = self._open((ilat[idx[0]], ilon[idx[0]]))
            out[ok[idx]] = _interp(arr, tr, lon[ok[idx]], lat[ok[idx]], method)
        return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Fetch USGS 10 m ground tiles for the roads near the Helene high-water marks.")
    ap.add_argument("--list", action="store_true", help="print the tiles that are needed and stop")
    ap.add_argument("--force", action="store_true", help="fetch every tile again, even those already on disk")
    ap.add_argument("--workers", type=int, default=4, help="downloads at once (default 4)")
    ap.add_argument("--root", default=str(ROOT), help="project root (default: this checkout)")
    a = ap.parse_args(argv)

    from src.pipeline import helene_depth  # needs the marks and the sampled road points

    p = helene_depth.paths(a.root)
    tiles = helene_depth.needed_tiles(a.root)
    print(f"{len(tiles)} tiles hold a mark or a sampled road point", flush=True)
    if a.list:
        for t in tiles:
            print(" ", tile_name(t))
        return
    n = pull(tiles, out=p.tiles, force=a.force, workers=a.workers, say=lambda m: print(m, flush=True))
    size = sum(f.stat().st_size for f in Path(p.tiles).glob("t_*.tif")) / 1e6
    print(f"fetched {n}, {len(tiles) - n} already on disk; {size:.0f} MB in {p.tiles}")


if __name__ == "__main__":
    main()
