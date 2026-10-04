"""Builders for the Helene depth tests: a small synthetic world measured in metres from one spot in Buncombe County."""
import json

import numpy as np
import pandas as pd
import rasterio
import shapely
from pyproj import Transformer
from rasterio.transform import Affine

from src.pipeline import helene_dem10 as dem
from src.pipeline import helene_depth as hd

LON0, LAT0 = -82.55, 35.55  # the middle of tile (355, -826)
TILE, TILE_E = (355, -826), (355, -825)
_TO_M = Transformer.from_crs(4326, hd.CRS_M, always_xy=True)
_TO_LL = Transformer.from_crs(hd.CRS_M, 4326, always_xy=True)
X0, Y0 = _TO_M.transform(LON0, LAT0)


def ll(x, y):
    """lon, lat of the spot x m east and y m north of the origin (state-plane metres)."""
    return _TO_LL.transform(X0 + np.asarray(x, dtype=float), Y0 + np.asarray(y, dtype=float))


def xy(lon, lat):
    x, y = _TO_M.transform(lon, lat)
    return x - X0, y - Y0


# ---- marks ----
def mark(i, x, y, level_m, stream="Alpha Creek", watershed="Test River", tape_m=0.0, quality="Good", n=None):
    lon, lat = ll(x, y)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": {"HWM_ID": i, "Stream": stream, "Watershed": watershed,
                           "Point_Number_on_Stream": i if n is None else n, "HWM_Elevation__ft_": level_m / hd.FT,
                           "Measured_Height__ft_": tape_m / hd.FT, "HWM_Quality": quality, "HWM_Type": "Mud Line"}}  # fmt: skip


def mk_marks(path, feats):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": list(feats)}))
    return path


def marks_from(tmp_path, feats):
    return hd.load_marks(mk_marks(tmp_path / "marks.geojson", feats))


def mk_line(group, pts, origin=False):
    """A stream line from (x, y, level) points in survey order. origin=True places it in the synthetic world."""
    d = pd.DataFrame(pts, columns=["x", "y", "wse_m"]).astype(float)
    if origin:
        d["x"], d["y"] = d.x + X0, d.y + Y0
    d["mark_id"] = [f"{group}{i}" for i in range(len(d))]
    return hd._line_from(group, d)


# ---- ground ----
def tile_grid(bounds):
    """The transform and the lon/lat of every cell centre for a window of the 1/3 arc-second grid."""
    w, s, e, n = bounds
    nx, ny = int(round((e - w) / dem.PX_DEG)), int(round((n - s) / dem.PX_DEG))
    tr = Affine(dem.PX_DEG, 0, w, 0, -dem.PX_DEG, n)
    lon = w + (np.arange(nx) + 0.5) * dem.PX_DEG
    lat = n - (np.arange(ny) + 0.5) * dem.PX_DEG
    return (tr, *np.meshgrid(lon, lat))


def tile_array(tile, fn, metric=True):
    tr, lon, lat = tile_grid(dem.fetch_bounds(tile))
    arr = fn(*xy(lon, lat)) if metric else fn(lon, lat)
    return np.asarray(arr, dtype="float32") * np.ones(lon.shape, dtype="float32"), tr


def mk_ground(folder, fn, tiles=(TILE,), metric=True, edit=None):
    """Write synthetic 10 m tiles whose ground is fn(x, y) in metres (or fn(lon, lat) when metric=False)."""
    manifest = dem.new_manifest()
    for t in tiles:
        arr, tr = tile_array(t, fn, metric)
        if edit is not None:
            edit(arr)
        manifest["tiles"][dem.tile_name(t)] = dem.write_tile(folder, t, arr, tr)
    dem.save_manifest(folder, manifest)
    return dem.Ground(folder)


def fake_fetch(fn, fail=(), metric=True):
    """A stand-in for the network call: ground from fn; raises for any tile in `fail`."""
    bad = {tuple(np.round(dem.fetch_bounds(t), 9)) for t in fail}

    def fetch(bounds):
        if tuple(np.round(bounds, 9)) in bad:
            raise RuntimeError("the network dropped")
        tr, lon, lat = tile_grid(bounds)
        arr = fn(*xy(lon, lat)) if metric else fn(lon, lat)
        return np.asarray(arr, dtype="float32") * np.ones(lon.shape, dtype="float32"), tr, "EPSG:4269"

    return fetch


def mk_dem30(path, fn, x=(-2600.0, 6100.0), y=(-800.0, 3300.0)):
    """A 30 m ground file in state-plane metres, like data/processed/dem/dem.tif."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nx, ny = int((x[1] - x[0]) / 30), int((y[1] - y[0]) / 30)
    cx = x[0] + (np.arange(nx) + 0.5) * 30
    cy = y[1] - (np.arange(ny) + 0.5) * 30
    gx, gy = np.meshgrid(cx, cy)
    arr = (np.asarray(fn(gx, gy), dtype="float32") * np.ones(gx.shape, dtype="float32"))
    with rasterio.open(path, "w", driver="GTiff", count=1, dtype="float32", nodata=np.nan, height=ny, width=nx,
                       crs=hd.CRS_M, transform=Affine(30, 0, X0 + x[0], 0, -30, Y0 + y[1])) as ds:  # fmt: skip
        ds.write(arr, 1)
    return path


# ---- roads and bridges ----
def road(*pts):
    """A road through (x, y) points of the synthetic world, as a lon/lat line."""
    lon, lat = ll([p[0] for p in pts], [p[1] for p in pts])
    return shapely.LineString(np.c_[lon, lat])


def seg_table(roads):
    """roads: {seg_id: geometry in lon/lat}. Shaped like segments_geom.parquet."""
    return pd.DataFrame({"seg_id": list(roads), "geometry": [shapely.to_wkb(g) for g in roads.values()]})


def mk_bridges(path, rows):
    """rows: (x, y, type). Shaped like data/raw/helene_structures.parquet."""
    lon, lat = ll([r[0] for r in rows], [r[1] for r in rows]) if rows else ([], [])
    pd.DataFrame({"Struct_No": [str(9000 + i) for i in range(len(rows))], "Struct_Type": [r[2] for r in rows],
                  "Over_Waterway_": "Yes", "LONG_DD": np.asarray(lon, dtype=float),
                  "LAT_DD": np.asarray(lat, dtype=float)}).to_parquet(path)  # fmt: skip
    return path


NO_BRIDGES = (np.zeros(0), np.zeros(0))


def mk_pts(depth, kept=None, part=None, along=None, high=None, group=None, aside=None, seg_id="s1"):
    """Road points as `summarise` expects them, for hand-worked cases."""
    n = len(depth)
    kept = np.ones(n, dtype=bool) if kept is None else np.asarray(kept, dtype=bool)
    return pd.DataFrame({
        "seg_id": seg_id, "part": np.zeros(n, dtype=int) if part is None else part, "i": np.arange(n),
        "depth": np.asarray(depth, dtype=float), "kept": kept,
        "along_m": np.zeros(n) if along is None else np.asarray(along, dtype=float),
        "high": np.ones(n, dtype=bool) if high is None else np.asarray(high, dtype=bool),
        "end_rule": False, "group": ["A"] * n if group is None else group,
        "line": 0, "v0": 0, "v1": 1, "aside": np.zeros(n, dtype=bool) if aside is None else np.asarray(aside, dtype=bool),
    })  # fmt: skip


# ---- the synthetic project root ----
def valley(x, y):
    """Two parallel valleys: Alpha along y = 0, Beta along y = 2,500; floors rise 5 m per km going east."""
    a = 598 + 0.005 * (x + 2000) + 0.02 * np.abs(y)
    b = 628 + 0.005 * (x + 2000) + 0.02 * np.abs(y - 2500)
    return np.minimum(a, b)


def world_marks():
    """20 marks per stream every 200 m, water 2 m above the valley floor; every second mark taped; 2 Poor marks."""
    feats = []
    for k in range(20):
        x = -2000 + 200 * k
        feats.append(mark(1 + k, x, 0, 600 + 0.005 * (x + 2000), tape_m=2.0 if k % 2 else 0.0))
        feats.append(mark(21 + k, x, 2500, 630 + 0.005 * (x + 2000), stream="Beta Branch", n=1 + k,
                          tape_m=2.0 if k % 2 else 0.0))  # fmt: skip
    feats.append(mark(41, -900, 30, 606.0, quality="Poor", n=101))
    feats.append(mark(42, 300, -30, 612.0, quality="Very Poor", n=102))
    return feats


SEG = {name: f"ncdot:{i:011d}:0.000" for i, name in enumerate(
    ["away", "low", "side", "high", "far", "bridge", "tile2", "beta", "multi", "short", "edge", "empty"], start=1)}  # fmt: skip


def world_roads():
    return {
        SEG["away"]: road((50000, 0), (50500, 0)),  # another county
        SEG["low"]: road((-1000, 20), (-400, 20)),  # along the Alpha valley floor: about 1.6 m of water
        SEG["side"]: road((0, 0), (0, 600)),  # climbs out of the valley: one low end
        SEG["high"]: road((-500, 200), (0, 200)),  # near the stream but 4 m above it: dry
        SEG["far"]: road((-500, 1000), (0, 1000)),  # too far to the side: not assessed
        SEG["bridge"]: road((500, -200), (500, 200)),  # crosses the stream on a listed bridge
        SEG["tile2"]: road((1700, 50), (5500, 50)),  # touches the stream, then runs into the next tile
        SEG["beta"]: road((-1000, 2520), (-400, 2520)),  # along the Beta valley floor
        SEG["multi"]: shapely.MultiLineString([road((-1500, 10), (-1300, 10)), road((-1200, -10), (-1100, -10))]),
        SEG["short"]: road((100, 10), (120, 10)),
        SEG["edge"]: road((-1900, 250), (-1700, 250)),
        SEG["empty"]: shapely.LineString(),
    }


FAILED = ("low", "side", "beta")


def build_root(root, with_dem30=True):
    """A complete small project: marks, 10 m tiles, bridge list, segment tables and (optionally) 30 m ground."""
    p = hd.paths(root)
    p.marks.parent.mkdir(parents=True, exist_ok=True)
    p.out.mkdir(parents=True, exist_ok=True)
    mk_marks(p.marks, world_marks())
    mk_ground(p.tiles, valley, tiles=(TILE, TILE_E))
    mk_bridges(p.bridges, [(500, 0, "Bridge"), (-700, 20, "Concrete Box Culvert"), (-900, 20, "Pipe or Culvert")])
    roads = world_roads()
    seg_table(roads).to_parquet(p.seg_geom)
    pd.DataFrame({"seg_id": list(roads), "y_helene_failed": [int(k in {SEG[f] for f in FAILED}) for k in roads],
                  "in_helene_zone": 1}).to_parquet(p.seg)  # fmt: skip
    if with_dem30:
        mk_dem30(p.dem30, lambda x, y: valley(x, y) + 1.0)  # a metre off, so the 10 m ground wins the comparison
    return p


def snapshot(folder):
    """{file name: sha256} of every file directly in a folder."""
    return {f.name: dem.sha256(f) for f in sorted(folder.iterdir()) if f.is_file()}
