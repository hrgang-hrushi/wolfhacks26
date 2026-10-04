"""Hurricane Helene flood depth for road segments near the surveyed high-water marks.

    python -m src.pipeline.helene_dem10                   # 10 m ground tiles first
    python -m src.pipeline.helene_depth --validate-only   # error numbers only; writes nothing
    python -m src.pipeline.helene_depth                   # error numbers, then the depth files

Depth = the water level drawn between surveyed marks along a stream, minus the 10 m ground under the road.
Writes, in data/processed/:
    flood_helene_depth.parquet             one row per segment, in the order of segments.parquet
    flood_helene_depth_points.parquet      one row per sampled road point
    flood_helene_depth_validation.json     the error numbers
    flood_helene_depth.meta.json           settings, counts and fingerprints (written last)

Every output column but seg_id starts with y_ or n_, so src.model.common.check_features rejects it as a
model input: the depth is an outcome of the storm, not a clue. Decisions D1-D25 and the tests are in
docs/specs/2026-10-03_helene-depth-map.md; a plain guide is docs/features/HELENE_DEPTH_MAP.md.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

from src.pipeline import helene_dem10
from src.pipeline.helene_dem10 import sha256

ROOT = Path(__file__).resolve().parents[2]
CRS_M = "EPSG:32119"  # NC State Plane, metres
FT = 0.3048
BOX = (-84.4, 34.9, -81.0, 36.7)  # lon/lat box the marks must fall in
MARKS_URL = "https://services.arcgis.com/NuWFvHYDMVmmxMeM/arcgis/rest/services/USACE_HWMs_Helene/FeatureServer/0/query"
REQUIRED = ["HWM_ID", "Stream", "Watershed", "Point_Number_on_Stream", "HWM_Elevation__ft_",
            "Measured_Height__ft_", "HWM_Quality", "HWM_Type"]  # fmt: skip
BRIDGE_COLUMNS = ["Struct_Type", "LONG_DD", "LAT_DD"]
CULVERT = re.compile(r"culvert|pipe|rcbc|cmp|corrugated|aluminum|multi-plate", re.I)
RULES = ("bridge", "notch", "bank")

DEPTH = "flood_helene_depth.parquet"
POINTS = "flood_helene_depth_points.parquet"
VALID = "flood_helene_depth_validation.json"
META = "flood_helene_depth.meta.json"
OUTPUTS = (POINTS, DEPTH, VALID, META)  # staging and renaming order; the notes file goes last

# Every number the result depends on. Recorded in the notes file and pinned by a test.
SETTINGS = {
    "SPACING_M": 30.0,  # road points are at most this far apart
    "SIDE_CAP_M": 300.0,  # a road point farther than this from a stream line is not assessed
    "REACH_M": 1000.0,  # nor one whose nearest mark is farther than this along the line
    "MAX_LIFT_M": 2.0,  # nor one where the drawn level is more than this from the nearer mark's own level
    "HIGH_CONF_M": 250.0,  # nearest mark within this along the line: high confidence
    "END_CAP_M": 100.0,  # past the last mark of a line, a level is given only this close to it
    "MERGE_M": 1.0,  # marks closer than this become one point of the line
    "BRIDGE_M": 60.0,  # road points this close to a listed bridge are set aside
    "NOTCH_M": 3.0,  # so is a point this far below both neighbours one or two points away
    "BANK_RISE_M": 2.0,  # and a bank beside a set-aside point that climbs more than this per 30 m
    "MAX_DEPTH_M": 15.0,  # a deeper reading is not believed: the point is left out and counted
    "MAX_TOO_DEEP_SHARE": 0.005,  # more than this share of such points stops the run
    "TRIPWIRE_M": [-1.0, 3.0],  # allowed median of water minus ground at the marks
    "MAX_TAPE_MISS_M": 0.25,  # the 10 m ground must miss the taped depths by no more than this
    "BANDS_M": [0.3, 1.0, 2.0],
    "HOLD_STRETCHES_M": [0, 250, 500],
    "DIST_BANDS_M": [100, 250, 500, 1000],
    "MIN_BAND_N": 30,
    "BOOT_N": 1000,
    "SEED": 0,
    "NO_LINE_GRADES": ["Poor", "Very Poor"],
    "TILE_DEG": helene_dem10.TILE_DEG,
    "HALO_PX": helene_dem10.HALO_PX,
}
S = SETTINGS

COLUMNS = ["seg_id", "y_helene_depth_assessed", "y_helene_depth_max_m", "y_helene_depth_point_max_m",
           "y_helene_depth_wet_share", "y_helene_depth_band", "y_helene_depth_conf", "y_helene_depth_mark_dist_m",
           "y_helene_depth_typical_miss_m", "y_helene_depth_stream", "n_helene_depth_marks",
           "n_helene_depth_points", "n_helene_depth_set_aside"]  # fmt: skip
_FLOATS = ["y_helene_depth_max_m", "y_helene_depth_point_max_m", "y_helene_depth_wet_share",
           "y_helene_depth_mark_dist_m", "y_helene_depth_typical_miss_m"]  # fmt: skip
_TEXTS = ["y_helene_depth_band", "y_helene_depth_conf", "y_helene_depth_stream"]
_COUNTS = ["n_helene_depth_marks", "n_helene_depth_points", "n_helene_depth_set_aside"]

_TO_M = Transformer.from_crs(4326, CRS_M, always_xy=True)
_TO_LL = Transformer.from_crs(CRS_M, 4326, always_xy=True)


class DepthError(RuntimeError):
    """The depth map cannot be built or read honestly as asked."""


def paths(root=ROOT) -> SimpleNamespace:
    root = Path(root)
    raw, proc = root / "data" / "raw", root / "data" / "processed"
    return SimpleNamespace(marks=raw / "flood_usace_hwm_helene.geojson", bridges=raw / "helene_structures.parquet",
                           seg=proc / "segments.parquet", seg_geom=proc / "segments_geom.parquet",
                           dem30=proc / "dem" / "dem.tif", tiles=proc / helene_dem10.OUT.name, out=proc)  # fmt: skip


# ---- marks (D1-D3, D6) ----
def load_marks(path=None):
    """The surveyed marks, cleaned and in a fixed order. Returns (marks, counts of what was dropped)."""
    path = Path(path or paths().marks)
    if not path.exists():
        raise DepthError(f"marks file missing: {path} (it can be pulled again, no login, from {MARKS_URL})")
    try:
        g = gpd.read_file(path)
    except Exception as e:
        raise DepthError(f"{path.name} cannot be read as marks: {e}") from e
    if len(g) == 0:
        raise DepthError(f"{path.name} holds no marks")
    missing = [c for c in REQUIRED if c not in g.columns]
    if missing:
        raise DepthError(f"{path.name} lacks the column(s) {missing}")
    if g.crs is not None and g.crs.to_epsg() != 4326:
        g = g.to_crs(4326)
    has_point = (g.geometry.notna() & ~g.geometry.is_empty & (g.geometry.geom_type == "Point")).values
    lon, lat = np.full(len(g), np.nan), np.full(len(g), np.nan)
    lon[has_point], lat[has_point] = g.geometry[has_point].x, g.geometry[has_point].y
    ids = g["HWM_ID"]
    ids = np.where(ids.isna(), [f"row{i}" for i in range(len(g))], ids.astype(str))  # a blank id is not a repeat
    tape = pd.to_numeric(g["Measured_Height__ft_"], errors="coerce") * FT
    d = pd.DataFrame({
        "mark_id": ids,
        "stream": g["Stream"].fillna("?").astype(str).str.strip().values,
        "watershed": g["Watershed"].fillna("?").astype(str).str.strip().values,
        "point_no": pd.to_numeric(g["Point_Number_on_Stream"], errors="coerce").values,
        "wse_m": (pd.to_numeric(g["HWM_Elevation__ft_"], errors="coerce") * FT).values,
        "tape_m": tape.where(tape > 0).values,  # 0 means "not measured", never a depth of zero
        "quality": g["HWM_Quality"].fillna("").astype(str).str.strip().values,
        "kind": g["HWM_Type"].fillna("").astype(str).str.strip().values,
        "lon": lon, "lat": lat,
    })  # fmt: skip
    d["group"] = d["stream"] + " | " + d["watershed"]  # one name can be two creeks; the watershed tells them apart
    counts = {"read": int(len(d))}

    def drop(keep, why):
        nonlocal d
        counts[why] = int((~keep).sum())
        d = d[keep]

    drop(d.lon.between(BOX[0], BOX[2]) & d.lat.between(BOX[1], BOX[3]), "outside_box")
    drop(d.wse_m.notna() & (d.wse_m > 0), "no_water_height")
    drop(d.point_no.notna(), "no_point_number")
    drop(~d.mark_id.duplicated(keep="first"), "repeated_id")
    if len(d) == 0:
        raise DepthError(f"{path.name} holds no usable marks ({counts})")
    d = d.copy()
    d["x"], d["y"] = _TO_M.transform(d.lon.values, d.lat.values)
    d["draws"] = ~d.quality.str.lower().isin([q.lower() for q in S["NO_LINE_GRADES"]])
    d = d.sort_values(["group", "point_no", "mark_id"], kind="stable").reset_index(drop=True)
    counts.update(kept=int(len(d)), draw_the_line=int(d.draws.sum()), taped=int(d.tape_m.notna().sum()),
                  groups=int(d.group.nunique()))  # fmt: skip
    return d, counts


def tripwire(marks, g10) -> float:
    """Median of water minus ground at the line-drawing marks; outside the allowed range means wrong units."""
    diff = (marks.wse_m.values - np.asarray(g10, dtype=float))[marks.draws.values]
    diff = diff[np.isfinite(diff)]
    if len(diff) == 0:
        raise DepthError("no line-drawing mark has 10 m ground under it; nothing can be checked")
    med = float(np.median(diff))
    lo, hi = S["TRIPWIRE_M"]
    if not lo <= med <= hi:
        raise DepthError(f"units or datum wrong: water minus ground at the marks has a median of {med:.1f} m "
                         f"(allowed {lo} to {hi})")  # fmt: skip
    return med


# ---- stream lines and the level lookup (D7-D9) ----
@dataclass
class Line:
    """One stream's water line: its marks in survey order, as points with a station (m) and a level (m)."""

    group: str
    x: np.ndarray
    y: np.ndarray
    s: np.ndarray
    z: np.ndarray
    ids: list  # per point, the tuple of mark ids merged into it


def _line_from(group, d) -> Line:
    """d: one group's line-drawing marks, already in survey order."""
    verts = []  # [first x, first y, xs, ys, zs, ids]
    for x, y, z, mid in zip(d.x.values, d.y.values, d.wse_m.values, d.mark_id.values):
        if verts and math.hypot(x - verts[-1][0], y - verts[-1][1]) < S["MERGE_M"]:
            v = verts[-1]
            v[2].append(x), v[3].append(y), v[4].append(z), v[5].append(mid)
        else:
            verts.append([x, y, [x], [y], [z], [mid]])
    vx = np.array([np.mean(v[2]) for v in verts], dtype=float)
    vy = np.array([np.mean(v[3]) for v in verts], dtype=float)
    vz = np.array([np.mean(v[4]) for v in verts], dtype=float)
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(vx), np.diff(vy)))]) if len(verts) else np.zeros(0)
    return Line(group, vx, vy, s, vz, [tuple(v[5]) for v in verts])


def build_lines(marks) -> list:
    d = marks[marks.draws]
    return [_line_from(group, part) for group, part in d.groupby("group", sort=True)]


_PIECE_FIELDS = ("x0", "y0", "dx", "dy", "plen", "zk", "zk1", "k", "term_lo", "term_hi", "single")


def _line_pieces(line) -> dict:
    """One row per stretch between two neighbouring marks of a line; one row for a line with a single mark."""
    rows = []
    m = len(line.x)
    if m == 1:
        rows.append((line.x[0], line.y[0], 0.0, 0.0, 0.0, line.z[0], line.z[0], 0, True, True, True))
    for k in range(m - 1):
        seglen = float(line.s[k + 1] - line.s[k])
        if seglen <= 0:
            continue
        rows.append((line.x[k], line.y[k], (line.x[k + 1] - line.x[k]) / seglen, (line.y[k + 1] - line.y[k]) / seglen,
                     seglen, line.z[k], line.z[k + 1], k, k == 0, k + 1 == m - 1, False))  # fmt: skip
    cols = list(zip(*rows)) if rows else [[] for _ in _PIECE_FIELDS]
    out = {}
    for name, col in zip(_PIECE_FIELDS, cols):
        kind = bool if name in ("term_lo", "term_hi", "single") else int if name == "k" else float
        out[name] = np.array(col, dtype=kind)
    return out


def _concat(piece_list) -> dict:
    out = {f: np.concatenate([p[f] for p in piece_list]) if piece_list else np.zeros(0) for f in _PIECE_FIELDS}
    out["line"] = (np.concatenate([np.full(len(p["x0"]), i, dtype=int) for i, p in enumerate(piece_list)])
                   if piece_list else np.zeros(0, dtype=int))  # fmt: skip
    return out


def _pieces(lines) -> dict:
    return _concat([_line_pieces(line) for line in lines])


def _live_geoms(lines) -> list:
    """The parts of the lines within REACH_M along the line of a mark, as geometries (for picking nearby roads)."""
    reach, geoms = S["REACH_M"], []
    for line in lines:
        if len(line.x) == 1:
            geoms.append(shapely.Point(line.x[0], line.y[0]))
        for k in range(len(line.x) - 1):
            a, b = np.array([line.x[k], line.y[k]]), np.array([line.x[k + 1], line.y[k + 1]])
            length = float(np.hypot(*(b - a)))
            if length <= 0:
                continue
            if length <= 2 * reach:
                geoms.append(shapely.LineString([a, b]))
            else:  # a long gap between marks: only its first and last REACH_M can give a level
                d = (b - a) / length
                geoms.append(shapely.LineString([a, a + d * reach]))
                geoms.append(shapely.LineString([b - d * reach, b]))
    return geoms


def _locate(P, lines, px, py, chunk=500) -> pd.DataFrame:
    px, py = np.atleast_1d(np.asarray(px, dtype=float)), np.atleast_1d(np.asarray(py, dtype=float))
    n = len(px)
    out = {"assessed": np.zeros(n, bool), "wse": np.full(n, np.nan), "along_m": np.full(n, np.nan),
           "side_m": np.full(n, np.nan), "lift_m": np.full(n, np.nan), "end_rule": np.zeros(n, bool),
           "high": np.zeros(n, bool), "line": np.full(n, -1), "v0": np.full(n, -1), "v1": np.full(n, -1)}  # fmt: skip
    if len(P["x0"]) and n:
        new_line = np.r_[True, np.diff(P["line"]) != 0]
        starts = np.flatnonzero(new_line)  # the first piece of each line
        col = np.cumsum(new_line) - 1  # piece -> its line's column
        idx = np.arange(len(P["x0"]))
        for a in range(0, n, chunk):
            b = min(n, a + chunk)
            qx, qy = px[a:b, None], py[a:b, None]
            u = (qx - P["x0"]) * P["dx"] + (qy - P["y0"]) * P["dy"]  # metres along each piece
            uc = np.clip(u, 0, P["plen"])
            side = np.hypot(qx - (P["x0"] + uc * P["dx"]), qy - (P["y0"] + uc * P["dy"]))
            side = np.where(np.isfinite(side), side, np.inf)
            # A line speaks only through its own nearest spot to the point. If that spot may not give a level
            # (too far from a mark, past the end, or on a steep stretch) the line is silent: the point is never
            # slid along the line to a mark that would answer.
            best = np.minimum.reduceat(side, starts, axis=1)
            cand = np.minimum.reduceat(np.where(side == best[:, col], idx, len(idx) - 1), starts, axis=1)
            rows = np.arange(b - a)[:, None]
            cu, cuc, plen = u[rows, cand], uc[rows, cand], P["plen"][cand]
            hi_end = cu > plen
            at_end = ((cu < 0) & P["term_lo"][cand]) | (hi_end & P["term_hi"][cand]) | P["single"][cand]
            along = np.minimum(cuc, plen - cuc)
            # how far the road point is from the nearest mark: along the line to the spot beside the point,
            # then across to it. Where the nearest spot is a mark itself (a bend, or the end of the line) that
            # is the straight line to the mark. A point far to the side of a mark is not "at" the mark.
            dist = np.hypot(along, best)  # along is 0 on a mark, so this is then the straight line to it
            # how far the drawn level has moved from the nearer mark's own level: between two marks that differ
            # by many metres (a dam, a fall, a steep reach) a straight line is a guess
            slope = np.divide(np.abs(P["zk1"][cand] - P["zk"][cand]), plen, out=np.zeros_like(plen), where=plen > 0)
            lift = np.where(at_end, 0.0, along * slope)
            valid = (best <= S["SIDE_CAP_M"]) & np.where(at_end, best <= S["END_CAP_M"],
                                                         (along <= S["REACH_M"]) & (lift <= S["MAX_LIFT_M"]))  # fmt: skip
            masked = np.where(valid, best, np.inf)
            w = np.argmin(masked, axis=1)  # the nearest line that speaks; equal distances go to the first in group order
            r = np.arange(b - a)
            ok = np.isfinite(masked[r, w])
            j, end = cand[r, w], at_end[r, w]
            frac = np.divide(cuc[r, w], plen[r, w], out=np.zeros(b - a), where=plen[r, w] > 0)
            wse = P["zk"][j] + (P["zk1"][j] - P["zk"][j]) * frac
            k = P["k"][j]
            # the marks the level was drawn from: both ends of the stretch, or, where the spot is a mark
            # itself (a bend, an end, or a foot landing exactly on a mark), that one mark alone
            on_hi = (frac >= 1) & ~P["single"][j]
            sole = P["single"][j] | (frac <= 0) | on_hi
            v0 = np.where(P["single"][j], 0, np.where(on_hi, k + 1, k))
            sl = slice(a, b)
            out["assessed"][sl] = ok
            out["wse"][sl] = np.where(ok, wse, np.nan)
            out["along_m"][sl] = np.where(ok, dist[r, w], np.nan)
            out["side_m"][sl] = np.where(ok, masked[r, w], np.nan)
            out["lift_m"][sl] = np.where(ok, lift[r, w], np.nan)
            out["end_rule"][sl] = ok & end
            out["high"][sl] = ok & ~end & (dist[r, w] <= S["HIGH_CONF_M"])
            out["line"][sl] = np.where(ok, P["line"][j], -1)
            out["v0"][sl] = np.where(ok, v0, -1)
            out["v1"][sl] = np.where(ok & ~sole, k + 1, -1)
    df = pd.DataFrame(out)
    names = np.array([line.group for line in lines] + [None], dtype=object)
    df["group"] = names[df["line"].values]
    return df


def locate(lines, px, py, chunk=500) -> pd.DataFrame:
    """For each point: is it assessed, the water level, and how far the nearest mark is along the line."""
    return _locate(_pieces(lines), lines, px, py, chunk)


def marks_behind(lines, line, v0, v1) -> set:
    """The ids of the marks whose levels a located point was drawn from."""
    if line < 0:
        return set()
    ids = set(lines[line].ids[v0])
    if v1 >= 0:
        ids |= set(lines[line].ids[v1])
    return ids


# ---- road points (D10) ----
def segment_points(geom, spacing=None):
    """x, y, part and step (m) along one road: even spacing of at most `spacing`, both ends included."""
    spacing = S["SPACING_M"] if spacing is None else spacing
    xs, ys, parts, steps = [], [], [], []
    if geom is not None and not geom.is_empty:
        lines = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom] if geom.geom_type == "LineString" else []
        for p, line in enumerate(lines):
            length = line.length
            if not length > 0:
                continue
            n = max(2, math.ceil(length / spacing - 1e-6) + 1)
            pts = shapely.line_interpolate_point(line, np.linspace(0.0, length, n))
            xs.append(shapely.get_x(pts)), ys.append(shapely.get_y(pts))
            parts.append(np.full(n, p)), steps.append(np.full(n, length / (n - 1)))
    if not xs:
        return np.zeros(0), np.zeros(0), np.zeros(0, dtype=int), np.zeros(0)
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(parts), np.concatenate(steps)


def load_segments(seg_path=None, geom_path=None) -> pd.DataFrame:
    """seg_id and WKB geometry (EPSG:4326) in the order of the segment table."""
    p = paths()
    seg_path, geom_path = Path(seg_path or p.seg), Path(geom_path or p.seg_geom)
    for f in (seg_path, geom_path):
        if not f.exists():
            raise DepthError(f"segment file missing: {f}")
    ids = pd.read_parquet(seg_path, columns=["seg_id"])
    geom = pd.read_parquet(geom_path, columns=["seg_id", "geometry"])
    if len(ids) == 0 or not ids.seg_id.is_unique or not geom.seg_id.is_unique:
        raise DepthError("the segment table is empty or repeats a seg_id")
    if set(ids.seg_id) != set(geom.seg_id):
        raise DepthError(f"{seg_path.name} and {geom_path.name} do not hold the same seg_ids")
    return ids.merge(geom, on="seg_id", how="left", validate="one_to_one")


def candidates(lines, seg):
    """Every sampled point of every road within SIDE_CAP_M of a live line part.

    Returns (points, number of empty geometries). The tile list and the build both come from here, so
    they cannot disagree about which points exist.
    """
    cols = ["seg_id", "part", "i", "x", "y", "lon", "lat", "step_m"]
    empty = pd.DataFrame({c: pd.Series(dtype=object if c == "seg_id" else int if c in ("part", "i") else float) for c in cols})
    geoms = shapely.from_wkb(seg["geometry"].values)
    blank = shapely.is_missing(geoms) | shapely.is_empty(geoms)
    n_empty = int(blank.sum())
    live = _live_geoms(lines)
    if not live:
        return empty, n_empty
    piece_geoms = np.array(live, dtype=object)
    # cheap first cut in lon/lat, then the exact distance test in metres
    lb = shapely.bounds(piece_geoms)
    lon, lat = _TO_LL.transform(np.r_[lb[:, 0], lb[:, 2], lb[:, 0], lb[:, 2]], np.r_[lb[:, 1], lb[:, 3], lb[:, 3], lb[:, 1]])
    pad = 0.02
    b = shapely.bounds(geoms)
    near = ~blank & (b[:, 2] >= lon.min() - pad) & (b[:, 0] <= lon.max() + pad) & (b[:, 3] >= lat.min() - pad) & (b[:, 1] <= lat.max() + pad)
    idx = np.flatnonzero(near)
    if len(idx) == 0:
        return empty, n_empty
    geoms_m = gpd.GeoSeries(geoms[idx], crs=4326).to_crs(CRS_M).values
    tree = shapely.STRtree(piece_geoms)
    hit = np.unique(tree.query(geoms_m, predicate="dwithin", distance=S["SIDE_CAP_M"])[0])
    rows = []
    seg_ids = seg["seg_id"].values
    for h in hit:  # table order, since idx and hit are sorted
        x, y, part, step = segment_points(geoms_m[h])
        if len(x) == 0:
            continue
        i = np.concatenate([np.arange(c) for c in np.bincount(part)[np.unique(part)]])
        rows.append(pd.DataFrame({"seg_id": seg_ids[idx[h]], "part": part, "i": i, "x": x, "y": y, "step_m": step}))
    if not rows:
        return empty, n_empty
    pts = pd.concat(rows, ignore_index=True)
    pts["lon"], pts["lat"] = _TO_LL.transform(pts.x.values, pts.y.values)
    return pts[cols], n_empty


def needed_tiles(root=ROOT) -> list:
    """The ground tiles that hold a mark or a sampled road point."""
    p = paths(root)
    marks, _ = load_marks(p.marks)
    pts, _ = candidates(build_lines(marks), load_segments(p.seg, p.seg_geom))
    return helene_dem10.tiles_needed(np.r_[marks.lon.values, pts.lon.values], np.r_[marks.lat.values, pts.lat.values])


# ---- bridges (D12) ----
def is_bridge(kind) -> bool:
    """A listed structure is a bridge unless its type names a culvert or pipe; a blank type counts as a bridge."""
    return not CULVERT.search("" if kind is None or (isinstance(kind, float) and math.isnan(kind)) else str(kind))


def load_bridges(path=None):
    """x, y (EPSG:32119) of every listed bridge."""
    path = Path(path or paths().bridges)
    if not path.exists():
        raise DepthError(f"bridge list missing: {path} (make it with python -m src.pipeline.pull_helene structures)")
    d = pd.read_parquet(path)
    missing = [c for c in BRIDGE_COLUMNS if c not in d.columns]
    if missing:
        raise DepthError(f"{path.name} lacks the column(s) {missing}")
    lon, lat = pd.to_numeric(d["LONG_DD"], errors="coerce"), pd.to_numeric(d["LAT_DD"], errors="coerce")
    keep = d["Struct_Type"].map(is_bridge).values & np.isfinite(lon.values) & np.isfinite(lat.values)
    x, y = _TO_M.transform(lon.values[keep], lat.values[keep])
    return np.asarray(x, dtype=float), np.asarray(y, dtype=float)


def near_bridges(x, y, bx, by) -> np.ndarray:
    if len(bx) == 0 or len(x) == 0:
        return np.zeros(len(x), dtype=bool)
    from scipy.spatial import cKDTree

    dist, _ = cKDTree(np.c_[bx, by]).query(np.c_[x, y], k=1)
    return dist <= S["BRIDGE_M"]


def set_aside(ground, part, step_m, near_bridge, rules=RULES) -> np.ndarray:
    """Which points of one road sit on or under a bridge, where the ground data shows the river bed."""
    g = np.asarray(ground, dtype=float)
    part, step_m = np.asarray(part), np.asarray(step_m, dtype=float)
    n = len(g)
    aside = np.zeros(n, dtype=bool)
    if "bridge" in rules:
        aside |= np.asarray(near_bridge, dtype=bool)
    if "notch" in rules:
        for k in (1, 2):
            if n > 2 * k:
                mid = slice(k, n - k)
                same = (part[:-2 * k] == part[mid]) & (part[2 * k:] == part[mid])
                with np.errstate(invalid="ignore"):
                    aside[mid] |= same & (g[mid] <= np.minimum(g[:-2 * k], g[2 * k:]) - S["NOTCH_M"])
    if "bank" in rules:
        steep = S["BANK_RISE_M"] * step_m / 30.0
        for i in np.flatnonzero(aside):  # the seeds; points added below are not seeds themselves
            for step in (-1, 1):
                j = i
                while True:
                    nxt, beyond = j + step, j + 2 * step
                    if not (0 <= nxt < n and 0 <= beyond < n) or part[nxt] != part[i] or part[beyond] != part[i]:
                        break
                    # set the next point aside only while the climb goes on past it: the top is kept
                    if g[nxt] - g[j] > steep[i] and g[beyond] - g[nxt] > steep[i]:
                        aside[nxt] = True
                        j = nxt
                    else:
                        break
    return aside


# ---- depth and the per-segment summary (D11, D13, D14) ----
def band(depth) -> str:
    if depth != depth:
        raise ValueError("no depth to put in a band")
    if depth <= 0:
        return "dry"
    a, b, c = S["BANDS_M"]
    return f"under {a:g} m" if depth < a else f"{a:g} to {b:g} m" if depth < b else f"{b:g} to {c:g} m" if depth < c else f"over {c:g} m"


def _typical_miss(band_tab, dist) -> float:
    for row in band_tab or []:
        if row["lo"] < dist <= row["hi"] or (dist == 0 and row["lo"] == 0):
            return float("nan") if row["too_few"] or row["median"] is None else float(row["median"])
    return float("nan")


def summarise(pts, lines, band_tab) -> pd.DataFrame:
    """One row per sampled segment. Ties go to the first pair in road order."""
    rows = []
    for seg_id, d in pts.groupby("seg_id", sort=False):
        kept, depth, part = d.kept.values, d.depth.values, d.part.values
        along, high, group = d.along_m.values, d.high.values, d.group.values
        row = {"seg_id": seg_id, "y_helene_depth_assessed": False, "n_helene_depth_marks": 0,
               "n_helene_depth_points": int(kept.sum()), "n_helene_depth_set_aside": int(d.aside.sum())}  # fmt: skip
        pair = kept[:-1] & kept[1:] & (part[:-1] == part[1:])
        if pair.any():
            pair_idx = np.flatnonzero(pair)
            pair_depth = np.minimum(depth[:-1], depth[1:])[pair]
            head = float(pair_depth.max())
            if head > 0:  # the pair that set the headline also supplies the distance, confidence and stream
                a = int(pair_idx[int(np.argmax(pair_depth))])
                b = a + 1
                dist = float(max(along[a], along[b]))
                conf = "high" if high[a] and high[b] else "low"
                stream = group[a] if depth[a] >= depth[b] else group[b]
            else:
                dist = float(np.median(along[kept]))
                conf = "high" if high[kept].mean() >= 0.5 else "low"
                names, n = np.unique(group[kept].astype(str), return_counts=True)
                stream = names[n == n.max()][0]  # np.unique sorts, so a tie goes to the alphabetically first
            behind = set()
            for line, v0, v1 in {(int(a_), int(b_), int(c_)) for a_, b_, c_ in zip(d.line.values[kept], d.v0.values[kept], d.v1.values[kept])}:
                behind |= marks_behind(lines, line, v0, v1)
            row.update({
                "y_helene_depth_assessed": True, "y_helene_depth_max_m": head,
                "y_helene_depth_point_max_m": float(depth[kept].max()),
                "y_helene_depth_wet_share": float((depth[kept] > 0).mean()),
                "y_helene_depth_band": band(head), "y_helene_depth_conf": conf,
                "y_helene_depth_mark_dist_m": dist, "y_helene_depth_typical_miss_m": _typical_miss(band_tab, dist),
                "y_helene_depth_stream": stream, "n_helene_depth_marks": len(behind),
            })  # fmt: skip
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def build(lines, ground, bridges, seg, band_tab, rules=RULES):
    """Road points, their depths and the per-segment summary. Returns (points, per segment, counts)."""
    pts, n_empty = candidates(lines, seg)
    pts["ground"] = ground.sample(pts.lon.values, pts.lat.values) if len(pts) else np.zeros(0)
    pts = pd.concat([pts, locate(lines, pts.x.values, pts.y.values)], axis=1)
    usable = pts.assessed.values & np.isfinite(pts.ground.values)
    pts["depth"] = np.where(usable, np.maximum(pts.wse.values - pts.ground.values, 0.0), np.nan)
    pts["near_bridge"] = near_bridges(pts.x.values, pts.y.values, *bridges)
    aside = np.zeros(len(pts), dtype=bool)
    for _, pos in pts.groupby("seg_id", sort=False).indices.items():
        aside[pos] = set_aside(pts.ground.values[pos], pts.part.values[pos], pts.step_m.values[pos],
                               pts.near_bridge.values[pos], rules)  # fmt: skip
    pts["aside"] = aside
    # a reading deeper than MAX_DEPTH_M is not a flood depth: the point sits in a lower valley than the
    # stream it was matched to, or on a bridge no rule caught. It is left out and counted; many of them
    # mean something is wrong with the inputs, and that stops the run
    pts["too_deep"] = usable & ~aside & (pts.depth.values > S["MAX_DEPTH_M"])
    pts["kept"] = usable & ~aside & ~pts.too_deep.values
    deep = pts[pts.too_deep]
    if len(deep) > S["MAX_TOO_DEEP_SHARE"] * max(1, int((usable & ~aside).sum())):
        worst = deep.sort_values("depth", ascending=False).iloc[0]
        raise DepthError(f"{len(deep)} road points in {deep.seg_id.nunique()} segment(s) read deeper than "
                         f"{S['MAX_DEPTH_M']} m (worst: {worst.seg_id} at {worst.depth:.1f} m): too many to be the odd "
                         "stray point, so a bridge list, a tile or the marks are wrong; nothing is built")  # fmt: skip
    per = summarise(pts, lines, band_tab)
    counts = {"segments_sampled": int(pts.seg_id.nunique()), "points_sampled": int(len(pts)),
              "points_kept": int(pts.kept.sum()), "points_set_aside": int(pts.aside.sum()),
              "points_too_deep": int(pts.too_deep.sum()), "segments_with_too_deep": int(deep.seg_id.nunique()),
              "points_without_ground": int((pts.assessed & ~np.isfinite(pts.ground)).sum()),
              "empty_geometries": n_empty}  # fmt: skip
    return pts, per, counts


def table(per, seg_ids) -> pd.DataFrame:
    """The per-segment file: one row per seg_id, in the given order; blank where not assessed."""
    seg_ids = pd.Series(np.asarray(seg_ids, dtype=object), name="seg_id")
    if len(seg_ids) == 0 or not seg_ids.is_unique:
        raise DepthError("the seg_id list is empty or repeats an id")
    if not per.seg_id.is_unique:
        raise DepthError("a segment was summarised twice")
    unknown = sorted(set(per.seg_id) - set(seg_ids))
    if unknown:
        raise DepthError(f"{len(unknown)} seg_id(s) are not in the segment table, e.g. {unknown[:3]}")
    out = seg_ids.to_frame().merge(per, on="seg_id", how="left", validate="one_to_one")
    out["y_helene_depth_assessed"] = out["y_helene_depth_assessed"].eq(True)
    for c in _FLOATS:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")  # blank stays blank: never 0
    for c in _TEXTS:
        out[c] = out[c].astype("string")
    for c in _COUNTS:
        out[c] = out[c].fillna(0).astype("int32")
    return out[COLUMNS]


# ---- error tests (D17-D21) ----
def miss_stats(miss) -> dict:
    m = np.asarray(miss, dtype=float)
    m = m[np.isfinite(m)]
    if len(m) == 0:
        return {"n": 0, "median": None, "p75": None, "p90": None, "bias": None}
    a = np.abs(m)
    return {"n": int(len(m)), "median": float(np.median(a)), "p75": float(np.quantile(a, 0.75)),
            "p90": float(np.quantile(a, 0.9)), "bias": float(np.median(m))}  # fmt: skip


def boot_range(values, groups, n=None, seed=None) -> list:
    """95% range of the typical miss, resampling whole stream groups (marks on one stream share errors)."""
    n, seed = S["BOOT_N"] if n is None else n, S["SEED"] if seed is None else seed
    values, groups = np.asarray(values, dtype=float), np.asarray(groups, dtype=object)
    ok = np.isfinite(values)
    values, groups = np.abs(values[ok]), groups[ok]
    if len(values) == 0:
        return [None, None]
    names = np.unique(groups.astype(str))
    by = [values[groups.astype(str) == g] for g in names]
    rng = np.random.default_rng(seed)
    meds = [float(np.median(np.concatenate([by[i] for i in rng.integers(0, len(by), len(by))]))) for _ in range(n)]
    return [float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975))]


def hidden_mark_test(marks) -> pd.DataFrame:
    """Hide each mark (or a stretch of marks around it) and guess its level from what is left.

    Uses the code that serves road points. stretch = -1 rows are the marks that never draw a line.
    """
    lines = build_lines(marks)
    cached = [_line_pieces(line) for line in lines]
    index = {line.group: i for i, line in enumerate(lines)}
    station = {mid: line.s[v] for line in lines for v, ids in enumerate(line.ids) for mid in ids}
    rows = []
    draws = marks[marks.draws]
    for group, d in draws.groupby("group", sort=True):
        li = index[group]
        st = d.mark_id.map(station).values.astype(float)
        ids = d.mark_id.values
        for stretch in S["HOLD_STRETCHES_M"]:
            for r in range(len(d)):
                hide = (ids == ids[r]) if stretch == 0 else (np.abs(st - st[r]) <= stretch)
                rebuilt = _line_from(group, d[~hide])
                lines2 = lines[:li] + [rebuilt] + lines[li + 1:]
                P = _concat(cached[:li] + [_line_pieces(rebuilt)] + cached[li + 1:])
                loc = _locate(P, lines2, [d.x.values[r]], [d.y.values[r]]).iloc[0]
                rows.append((ids[r], group, stretch, bool(loc.assessed), float(loc.wse), float(loc.along_m), int(hide.sum())))
    poor = marks[~marks.draws]
    if len(poor):
        loc = locate(lines, poor.x.values, poor.y.values)
        rows += [(mid, g, -1, bool(a), float(w), float(al), 0) for mid, g, a, w, al in
                 zip(poor.mark_id.values, poor.group.values, loc.assessed.values, loc.wse.values, loc.along_m.values)]  # fmt: skip
    hm = pd.DataFrame(rows, columns=["mark_id", "group", "stretch", "assessed", "guess", "along_m", "n_hidden"])
    hm["miss"] = hm.guess - hm.mark_id.map(marks.set_index("mark_id").wse_m)
    return hm


def band_table(hm) -> list:
    """Typical miss by distance to the nearest remaining mark; per mark and band, the smallest stretch counts."""
    edges = [0] + list(S["DIST_BANDS_M"])
    d = hm[(hm.stretch >= 0) & hm.assessed].copy()
    d["band"] = np.searchsorted(edges[1:], d.along_m.values, side="left")  # (lo, hi], with 0 in the first band
    d = d[d.band < len(edges) - 1].sort_values(["mark_id", "band", "stretch"], kind="stable").drop_duplicates(["mark_id", "band"])
    out = []
    for b in range(len(edges) - 1):
        rows = d[d.band == b]
        st = miss_stats(rows.miss)
        out.append({"band": f"{edges[b]}-{edges[b + 1]} m", "lo": edges[b], "hi": edges[b + 1], "n": st["n"],
                    "median": st["median"], "p90": st["p90"], "range95": boot_range(rows.miss, rows.group),
                    "too_few": st["n"] < S["MIN_BAND_N"]})  # fmt: skip
    return out


def _corr(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def tape_tests(marks, g10, hm) -> dict:
    """Against the taped depths: (a) the mark's own level minus ground; (b) the hidden-mark guess minus ground."""
    m = marks.assign(g10=np.asarray(g10, dtype=float))
    taped = m[m.tape_m.notna() & np.isfinite(m.g10)]
    own = taped.wse_m - taped.g10
    ground_only = {**miss_stats(own - taped.tape_m), "corr": _corr(own, taped.tape_m)}
    guess = hm[(hm.stretch == 0) & hm.assessed].set_index("mark_id").guess
    e2e = taped[taped.draws & taped.mark_id.isin(guess.index)]
    est = e2e.mark_id.map(guess) - e2e.g10
    end_to_end = {**miss_stats(est - e2e.tape_m), "corr": _corr(est, e2e.tape_m),
                  "range95": boot_range(est - e2e.tape_m, e2e.group)}  # fmt: skip
    typical = float(taped.tape_m.median()) if len(taped) else None
    return {"typical_taped_depth_m": typical, "ground_only": ground_only, "end_to_end": end_to_end}


def gate_30m(marks, g10, dem30=None, skip=False) -> dict:
    """Refuse unless the 10 m ground beats the 30 m ground on the taped marks, and misses by little."""
    dem30 = Path(dem30 or paths().dem30)
    m = marks.assign(g10=np.asarray(g10, dtype=float))
    taped = m[m.tape_m.notna() & np.isfinite(m.g10)]
    if len(taped) == 0:
        raise DepthError("no taped mark has 10 m ground under it: the ground cannot be checked, so nothing is built")
    cap = S["MAX_TAPE_MISS_M"]
    miss10 = float(np.median(np.abs(taped.wse_m - taped.g10 - taped.tape_m)))
    if not dem30.exists():
        if not skip:
            raise DepthError(f"30 m ground missing ({dem30}): make it with python -m src.pipeline.dem, or rerun "
                             "with --skip-30m-check to go without the comparison")  # fmt: skip
        if miss10 > cap:
            raise DepthError(f"the 10 m ground misses the taped depths by {miss10:.2f} m (allowed {cap})")
        return {"skipped": True, "n": int(len(taped)), "miss10": miss10, "miss30": None, "passed": True}
    import rasterio

    with rasterio.open(dem30) as ds:
        if ds.crs is not None and ds.crs.to_epsg() != int(CRS_M.split(":")[1]):
            x, y = Transformer.from_crs(4326, ds.crs, always_xy=True).transform(taped.lon.values, taped.lat.values)
        else:
            x, y = taped.x.values, taped.y.values
        g30 = np.array([v[0] for v in ds.sample(list(zip(x, y)))], dtype=float)
        if ds.nodata is not None and not np.isnan(ds.nodata):
            g30[g30 == ds.nodata] = np.nan
    both = taped[np.isfinite(g30)]
    g30 = g30[np.isfinite(g30)]
    if len(both) == 0:
        raise DepthError("no taped mark has both 10 m and 30 m ground: the comparison cannot be made")
    miss10 = float(np.median(np.abs(both.wse_m - both.g10 - both.tape_m)))
    miss30 = float(np.median(np.abs(both.wse_m.values - g30 - both.tape_m.values)))
    if not miss10 < miss30:
        raise DepthError(f"the 10 m ground is not better than the 30 m ground on the {len(both)} taped marks "
                         f"({miss10:.2f} m against {miss30:.2f} m): not built")  # fmt: skip
    if miss10 > cap:
        raise DepthError(f"the 10 m ground misses the taped depths by {miss10:.2f} m (allowed {cap})")
    return {"skipped": False, "n": int(len(both)), "miss10": miss10, "miss30": miss30, "passed": True}


def pre_checks(marks, g10, dem30=None, skip_30m=False):
    """Everything that can refuse, before any road is touched. Returns (first part of the validation, band table)."""
    trip = tripwire(marks, g10)
    hm = hidden_mark_test(marks)
    loo = hm[hm.stretch == 0]
    got = loo[loo.assessed]
    if len(got) < S["MIN_BAND_N"]:
        raise DepthError(f"only {len(got)} marks could be guessed from their neighbours (need {S['MIN_BAND_N']}): "
                         "no error number can be stated, so nothing is built")  # fmt: skip
    bands = band_table(hm)
    poor = hm[(hm.stretch == -1) & hm.assessed]
    by_group = [{"group": g, **{k: v for k, v in miss_stats(d.miss).items() if k in ("n", "median")}}
                for g, d in got.groupby("group", sort=True)]  # fmt: skip
    pre = {
        "ground": {"water_minus_ground_median_m": trip},
        "hidden_mark": {
            "overall": {**miss_stats(got.miss), "range95": boot_range(got.miss, got.group),
                        "no_guess": int((~loo.assessed).sum())},
            "by_band": bands,
            "poor_grades": {**miss_stats(poor.miss), "no_guess": int(((hm.stretch == -1) & ~hm.assessed).sum())},
            "by_group": by_group,
        },
        "tape": {**tape_tests(marks, g10, hm), "vs_30m": gate_30m(marks, g10, dem30, skip_30m)},
        "settings": SETTINGS,
    }  # fmt: skip
    return pre, bands


def labels_check(tab, seg_path=None) -> dict:
    """Share of segments marked failed in Helene, for those with at least 0.3 m of water against dry ones."""
    seg_path = Path(seg_path or paths().seg)
    try:
        lab = pd.read_parquet(seg_path, columns=["seg_id", "y_helene_failed"])
    except Exception:
        return {"available": False}
    d = tab[tab.y_helene_depth_assessed].merge(lab, on="seg_id", how="left")
    d = d[d.y_helene_failed.notna()]
    wet, dry = d[d.y_helene_depth_max_m >= S["BANDS_M"][0]], d[d.y_helene_depth_max_m == 0]

    def share(x):
        return None if len(x) == 0 else float((x.y_helene_failed == 1).mean())

    return {"available": True, "wet_n": int(len(wet)), "wet_failed_share": share(wet),
            "dry_n": int(len(dry)), "dry_failed_share": share(dry)}  # fmt: skip


def finish_validation(pre, tab, seg_path, counts) -> dict:
    """Add what needs the built table, so the saved numbers always describe the table that is written."""
    assessed = tab[tab.y_helene_depth_assessed]
    build = {**counts, "segments": int(len(tab)), "segments_assessed": int(len(assessed)),
             "segments_wet": int((assessed.y_helene_depth_max_m > 0).sum()),
             "by_band": {str(k): int(v) for k, v in assessed.y_helene_depth_band.value_counts().sort_index().items()}}  # fmt: skip
    return {**pre, "build": build, "labels_check": labels_check(tab, seg_path)}


# ---- output, notes file, loader (D16, D22-D24) ----
def _own(path) -> Path:
    """Refuse to write anything that is not this change's own file."""
    path = Path(path)
    if not path.name.startswith("flood_helene_depth"):
        raise DepthError(f"refusing to write {path.name}: only flood_helene_depth* files are ours")
    return path


def seg_id_hash(seg_ids) -> str:
    import hashlib

    return hashlib.sha256("\n".join(map(str, seg_ids)).encode()).hexdigest()


def fingerprints(files: dict) -> dict:
    """sha256 per file; None for one that is absent."""
    return {name: sha256(path) if Path(path).exists() else None for name, path in files.items()}


def write_outputs(out, tab, pts, validation, meta) -> None:
    """Stage all four files, then swap them in together, notes last. A failure leaves the old files alone."""
    out = Path(out)
    final = {name: _own(out / name) for name in OUTPUTS}
    tmp = {name: path.with_name(path.name + ".tmp") for name, path in final.items()}
    try:
        pts.to_parquet(tmp[POINTS], index=False)
        tab.to_parquet(tmp[DEPTH], index=False)
        tmp[VALID].write_text(json.dumps(validation, indent=1, sort_keys=True))
        meta = {**meta, "sha256": {**meta.get("sha256", {}), **{n: sha256(tmp[n]) for n in (POINTS, DEPTH, VALID)}}}
        tmp[META].write_text(json.dumps(meta, indent=1, sort_keys=True))
    except BaseException:
        for t in tmp.values():
            t.unlink(missing_ok=True)
        raise
    for name in OUTPUTS:
        os.replace(tmp[name], final[name])


def load_depth(root=ROOT) -> pd.DataFrame:
    """The per-segment table, refused if any file of the set or any input has changed since it was built."""
    p = paths(root)
    meta_path = p.out / META
    if not meta_path.exists():
        raise DepthError(f"no depth map at {p.out}: run python -m src.pipeline.helene_depth")
    recorded = json.loads(meta_path.read_text()).get("sha256", {})
    now = fingerprints({DEPTH: p.out / DEPTH, POINTS: p.out / POINTS, VALID: p.out / VALID,
                        "marks": p.marks, "manifest": p.tiles / "manifest.json"})  # fmt: skip
    now["seg_ids"] = seg_id_hash(pd.read_parquet(p.seg, columns=["seg_id"]).seg_id) if p.seg.exists() else None
    changed = [k for k, v in now.items() if v is None or recorded.get(k) != v]
    if changed:
        raise DepthError(f"the depth map does not match its notes file ({', '.join(changed)} changed or missing): "
                         "rebuild it with python -m src.pipeline.helene_depth")  # fmt: skip
    return pd.read_parquet(p.out / DEPTH)


def _commit(root):
    """(commit, dirty): the commit the checkout is on, and whether these two scripts differ from it."""
    def git(*args):
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20)
        return r.stdout if r.returncode == 0 else None

    try:
        head = git("rev-parse", "HEAD")
        changed = git("status", "--porcelain", "--", "src/pipeline/helene_depth.py", "src/pipeline/helene_dem10.py")
        return (head.strip() or None if head else None), (None if head is None or changed is None else bool(changed.strip()))
    except Exception:
        return None, None


def run(root=ROOT, validate_only=False, skip_30m=False, say=print) -> dict:
    """The whole command. Every path hangs off `root`, so the tests drive it on a synthetic project."""
    p = paths(root)
    shared = {"marks": p.marks, "bridges": p.bridges, "segments": p.seg, "segments_geom": p.seg_geom, "dem30": p.dem30}
    before = fingerprints(shared)
    marks, mark_counts = load_marks(p.marks)
    ground = helene_dem10.Ground(p.tiles)
    g10 = ground.sample(marks.lon.values, marks.lat.values)
    pre, bands = pre_checks(marks, g10, p.dem30, skip_30m)
    pre["marks"] = mark_counts
    hm, tape = pre["hidden_mark"], pre["tape"]
    say(f"marks: {mark_counts['kept']} kept, {mark_counts['draw_the_line']} draw the line, {mark_counts['groups']} streams")
    v30 = tape["vs_30m"]
    say(f"taped depths: 10 m ground misses by {v30['miss10']:.2f} m"
        + (" (30 m comparison skipped)" if v30["skipped"] else f", 30 m ground by {v30['miss30']:.2f} m") + f", {v30['n']} marks")
    say(f"hidden marks: typical miss {hm['overall']['median']:.2f} m over {hm['overall']['n']} marks")
    for row in bands:
        say(f"  nearest mark {row['band']:>11}: " + ("too few marks" if row["too_few"] else f"{row['median']:.2f} m") + f"  (n={row['n']})")
    e2e = tape["end_to_end"]
    say(f"end to end against the tape: {e2e['median']:.2f} m over {e2e['n']} marks" if e2e["n"] else "end to end against the tape: no marks")
    if validate_only:
        return pre  # before the bridge list is read and before anything is written

    lines = build_lines(marks)
    bridges = load_bridges(p.bridges)
    seg = load_segments(p.seg, p.seg_geom)
    pts, per, counts = build(lines, ground, bridges, seg, bands)
    tab = table(per, seg.seg_id.values)
    validation = finish_validation(pre, tab, p.seg, counts)
    after = fingerprints(shared)
    if after != before:
        changed = [k for k in shared if before[k] != after[k]]
        raise DepthError(f"a shared input changed while this ran ({changed}); nothing was written")
    commit, dirty = _commit(root)
    meta = {
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit, "git_code_differs_from_commit": dirty, "settings": SETTINGS, "marks": mark_counts, "build": validation["build"],
        "skip_30m_check": bool(skip_30m), "inputs_before": before, "inputs_after": after,
        "headline": {"hidden_mark_median_m": hm["overall"]["median"], "tape_end_to_end_median_m": e2e["median"],
                     "tape_ground_only_median_m": tape["ground_only"]["median"]},
        "sha256": {"marks": before["marks"], "bridges": before["bridges"],
                   "manifest": sha256(p.tiles / "manifest.json"), "seg_ids": seg_id_hash(seg.seg_id.values)},
    }  # fmt: skip
    write_outputs(p.out, tab, pts, validation, meta)
    b = validation["build"]
    say(f"roads: {b['segments_sampled']} sampled, {b['segments_assessed']} assessed, {b['segments_wet']} with water; "
        f"{b['points_set_aside']} points set aside as bridges")
    say(f"wrote {DEPTH}, {POINTS}, {VALID}, {META} in {p.out}")
    return validation


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Helene flood depth for road segments near the surveyed high-water marks.")
    ap.add_argument("--validate-only", action="store_true", help="print the error numbers and stop; writes nothing")
    ap.add_argument("--skip-30m-check", action="store_true",
                    help="go without the 10 m against 30 m comparison when the 30 m ground is absent (recorded)")  # fmt: skip
    ap.add_argument("--root", default=str(ROOT), help="project root (default: this checkout)")
    a = ap.parse_args(argv)
    try:
        run(a.root, validate_only=a.validate_only, skip_30m=a.skip_30m_check)
    except (DepthError, helene_dem10.GroundError) as e:
        print(f"refused: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
