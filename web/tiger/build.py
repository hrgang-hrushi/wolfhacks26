"""Turn the project's files into the tables the database holds. No database is touched here.

Reads (all read-only):
  handoff/predictions_geo.parquet, handoff/traffic_crash.parquet, data/processed/segments.parquet,
  data/processed/pothole_labels.parquet, data/processed/flood_camera_depth.parquet,
  data/raw/ncdot_joined.parquet, data/raw/pothole_reports.parquet (+ its manifest and city limits),
  data/raw/sunnyday/levels/*.json

Rules that keep the tables honest:
  - one row per road, and every per-road file must hold exactly the same roads;
  - a blank stays blank (never 0); not-a-number becomes blank; infinity is refused;
  - flood risk is blank outside the Helene zone, where the model's number means nothing;
  - only ids starting `ncdot:` are accepted, so a city street can never look scored;
  - a reading or a report without a matched state road keeps a blank road;
  - times carry a time zone (UTC);
  - the pothole matcher and the sensor reader are the project's own, not second versions.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pandas.api import types as ptypes
from pyproj import Transformer

from src.pipeline import pothole_labels, sunnyday
from src.pipeline.pull_potholes import read_bundle, sha256_file
from web.tiger import schema

SOURCES = {
    "predictions": "handoff/predictions_geo.parquet",
    "traffic_crash": "handoff/traffic_crash.parquet",
    "segments": "data/processed/segments.parquet",
    "pothole_labels": "data/processed/pothole_labels.parquet",
    "camera_depth": "data/processed/flood_camera_depth.parquet",
    "ncdot_joined": "data/raw/ncdot_joined.parquet",
    "pothole_reports": "data/raw/pothole_reports.parquet",
    "pothole_meta": "data/raw/pothole_reports.meta.json",
    "city_limits": "data/raw/city_limits.parquet",
}
SENSOR_DIR = "data/raw/sunnyday/levels"
CRS_M = pothole_labels.CRS_M
# rank: bucket, then years to Poor, then rating (lowest first), then predicted wear (fastest first), then id.
# Crash rate is shown on the dashboard and is deliberately not a key here.
RANK_KEYS = ("bucket_order", "pred_years_to_poor", "rating", "-pred_rate", "seg_id")
SEGMENT_COLUMNS = ["seg_id", "pv_ROUTEID", "pv_ROUTE", "pv_COUNTY", "pv_BEG_MP", "pv_END_MP", "pv_FROM_DESC", "pv_TO_DESC",
                   "pv_LENGTH", "pv_NC_SYSTEM_CODE", "pv_DIVISION", "pv_NUMBER_OF_LANES", "pv_RTG_NBR", "pv_PCS_SRVY_YR",
                   "pv_YEAR_LAST_REHAB", "pv_LAST_REHAB_TYPE", "pv_PMS_TREATMENT_NAME", "pv_TREATMENT_COST",
                   "in_helene_zone", "y_helene_failed", "mid_x", "mid_y"]


def fingerprints(root):
    """{relative path: {sha256, bytes}} for every file the build reads."""
    root = Path(root)
    files = list(SOURCES.values()) + sorted(str(p.relative_to(root)) for p in (root / SENSOR_DIR).glob("*.json"))
    return {f: {"sha256": sha256_file(root / f), "bytes": (root / f).stat().st_size} for f in files}


def same_ids(left, right, name):
    """Both tables must hold exactly the same roads, once each. A missing road is refused, not filled with blanks."""
    for label, d in (("predictions", left), (name, right)):
        if d.seg_id.isna().any() or d.seg_id.duplicated().any():
            raise ValueError(f"{label}: seg_id has blanks or duplicates")
    a, b = set(left.seg_id), set(right.seg_id)
    if a != b:
        raise ValueError(f"{name} does not hold the same roads as the predictions: {len(a - b)} missing, {len(b - a)} extra")


def repair_bucket(years):
    """fix_now: 0 years. within_1y: up to 1. within_5y: up to 5. later: above 5. unknown: blank."""
    y = np.asarray(years, dtype="float64")
    return np.select([np.isnan(y), y <= 0, y <= 1, y <= 5], ["unknown", "fix_now", "within_1y", "within_5y"], default="later")


def rank(d):
    """1 = fix first. Sorted by RANK_KEYS, blanks last."""
    keys = d[["pred_years_to_poor", "rating", "seg_id"]].copy()
    keys["bucket_order"] = pd.Series(d.repair_bucket.values, index=d.index).map({b: i for i, b in enumerate(schema.BUCKETS)})
    keys["neg_rate"] = -d.pred_rate
    order = keys.sort_values(["bucket_order", "pred_years_to_poor", "rating", "neg_rate", "seg_id"],
                             na_position="last", kind="mergesort").index
    out = pd.Series(np.arange(1, len(d) + 1), index=order)
    return out.reindex(d.index).astype("int64").values


def _int(s):
    """Whole numbers that may be blank."""
    return pd.to_numeric(s, errors="coerce").round().astype("Int64")


def _f3(s):
    """float32 values that were rounded to 3 decimals come back as clean float64."""
    return pd.to_numeric(s, errors="coerce").astype("float64").round(3)


def _read_predictions(root):
    g = gpd.read_parquet(Path(root) / SOURCES["predictions"])
    if g.crs is None or g.crs.to_epsg() != 4326:
        raise ValueError("predictions_geo.parquet is not in EPSG:4326")
    if g.geometry.isna().any() or g.geometry.is_empty.any():
        raise ValueError("predictions_geo.parquet has roads without a shape")
    return g


def build_roads(root, pred=None):
    """One row per road, in the column order of schema.ROADS."""
    root = Path(root)
    pred = _read_predictions(root) if pred is None else pred
    seg = pd.read_parquet(root / SOURCES["segments"], columns=SEGMENT_COLUMNS)
    crash = pd.read_parquet(root / SOURCES["traffic_crash"])
    pot = pd.read_parquet(root / SOURCES["pothole_labels"])
    for name, d in (("segments", seg), ("traffic_crash", crash), ("pothole_labels", pot)):
        same_ids(pred, d, name)
    bad = pred.seg_id[~pred.seg_id.astype(str).str.startswith("ncdot:")]
    if len(bad):
        raise ValueError(f"{len(bad)} ids do not start with ncdot: (city streets are not scored), e.g. {bad.head(3).tolist()}")
    seg, crash, pot = (d.set_index("seg_id").reindex(pred.seg_id.values) for d in (seg, crash, pot))
    zone = pred.in_helene_zone.values == 1
    if not np.array_equal(zone, seg.in_helene_zone.values == 1):
        raise ValueError("in_helene_zone differs between the predictions and the segment table")

    county = seg.pv_COUNTY.astype(str).str.split("-", n=1, expand=True)
    lon, lat = Transformer.from_crs(CRS_M, "EPSG:4326", always_xy=True).transform(seg.mid_x.values, seg.mid_y.values)
    bounds = pred.geometry.bounds
    out = pd.DataFrame({
        "seg_id": pred.seg_id.values,
        "route_id": seg.pv_ROUTEID.values, "route": seg.pv_ROUTE.values,
        "county_code": county[0].values, "county": county[1].values,
        "beg_mp": seg.pv_BEG_MP.values, "end_mp": seg.pv_END_MP.values,
        "from_desc": seg.pv_FROM_DESC.values, "to_desc": seg.pv_TO_DESC.values,
        "length_mi": seg.pv_LENGTH.values, "system": seg.pv_NC_SYSTEM_CODE.values,
        "division": _int(seg.pv_DIVISION).values,
        "lanes": _int(seg.pv_NUMBER_OF_LANES.where(seg.pv_NUMBER_OF_LANES > 0)).values,      # 0 means missing
        "rating": seg.pv_RTG_NBR.where(seg.pv_RTG_NBR > 0).values,                           # 0 means missing
        "survey_year": _int(seg.pv_PCS_SRVY_YR).values, "last_rehab_year": _int(seg.pv_YEAR_LAST_REHAB).values,
        "last_rehab_type": seg.pv_LAST_REHAB_TYPE.values,
        "treatment": seg.pv_PMS_TREATMENT_NAME.values, "treatment_cost": seg.pv_TREATMENT_COST.values,
        "pred_rate": pred.pred_rate.values, "pred_years_to_poor": pred.pred_years_to_poor.values,
        "pred_crack": pred.pred_crack.values,
        "pred_flood": np.where(zone, pred.pred_flood.values, np.nan),                         # blank outside the zone
        "flood_scored": zone, "in_helene_zone": zone,
        "rate_heldout": pred.rate_heldout.values.astype(bool), "crack_heldout": pred.crack_heldout.values.astype(bool),
        "flood_heldout": pred.flood_heldout.values.astype(bool),
        "helene_damaged": seg.y_helene_failed.values == 1,                                    # not y_helene_damage
    })
    out["repair_bucket"] = repair_bucket(out.pred_years_to_poor)
    out["priority_rank"] = rank(out)
    out = out.assign(
        crash_per_mvm=_f3(crash.cr_crash_per_mvm).values, crash_per_mile_year=_f3(crash.cr_crash_per_mi_yr).values,
        crash_cover=_f3(crash.cr_cover).values, fatal_10yr=_int(crash.cr_fatal_10yr).values,
        serious_10yr=_int(crash.cr_serious_10yr).values, ncdot_safety_score=_f3(crash.cr_ncdot_score).values,
        aadt_best=_f3(crash.tr_aadt_best).values, aadt_source=crash.tr_aadt_best_source.values,
        pothole_city=pot.pothole_city.values, potholes_all_time=_int(pot.n_pothole_all_time).values,
        potholes_in_window=_int(pot.n_pothole_reports).values,
        mid_lon=np.round(lon, 6), mid_lat=np.round(lat, 6),
        min_lon=bounds.minx.round(6).values, min_lat=bounds.miny.round(6).values,
        max_lon=bounds.maxx.round(6).values, max_lat=bounds.maxy.round(6).values,
    )
    return _checked(out, "roads")


def build_road_shapes(root, pred=None):
    """seg_id and the road's line as GeoJSON text, coordinates to 6 decimals (about 10 cm)."""
    pred = _read_predictions(root) if pred is None else pred
    geoms = pred.geometry.values
    snapped = shapely.set_precision(geoms, 1e-6)
    snapped = np.where(shapely.is_empty(snapped), geoms, snapped)      # a line shorter than the grid keeps its points
    out = pd.DataFrame({"seg_id": pred.seg_id.values, "geojson": shapely.to_geojson(snapped)})
    return _checked(out, "road_shapes")


def _checked(d, table):
    want = schema.columns(table)
    if list(d.columns) != want:
        raise ValueError(f"{table}: built columns differ from the table's column list")
    if len(d) == 0:
        raise ValueError(f"{table}: no rows")
    floats = d.select_dtypes(include="float")
    bad = [c for c in floats.columns if np.isinf(floats[c].to_numpy(dtype="float64", na_value=np.nan)).any()]
    if bad:
        raise ValueError(f"{table}: infinity in {bad}")
    return d


def build_cameras_and_readings(root):
    """(cameras, camera_readings) from the flood reader's output. A camera is the station, or the site for NCDOT stills."""
    d = pd.read_parquet(Path(root) / SOURCES["camera_depth"])
    if len(d) == 0:
        raise ValueError("camera_readings: no rows")
    d = d.assign(camera_id=np.where(d.station == "NCDOT", d.site, d.station))
    if d.time_utc.isna().any():
        raise ValueError("camera readings without a time")
    if not d.role.isin(["cv", "extra"]).all():
        raise ValueError("camera readings with an unknown role")
    if ((d.p_flooded < 0) | (d.p_flooded > 1)).any():
        raise ValueError("camera readings with a flood probability outside 0 to 1")
    if (d.depth_pred_cm < 0).any() or (d.depth_measured_cm < 0).any():
        raise ValueError("camera readings with a negative depth")
    if d.duplicated(["site", "time_utc", "file"]).any():
        raise ValueError("camera readings repeat a (site, time, file)")
    per_camera = ["site", "station", "name", "lat", "lon", "seg_id", "seg_dist_m", "role"]
    changing = d.groupby("camera_id")[per_camera].nunique(dropna=False).max()
    if (changing > 1).any():
        raise ValueError(f"a camera's {changing[changing > 1].index.tolist()} changes between readings")
    cams = d.drop_duplicates("camera_id")[["camera_id"] + per_camera].sort_values("camera_id").reset_index(drop=True)
    cams["known_dry"] = cams.role == "extra"          # NCDOT stills taken on dry roads; never a confirmed flood
    readings = pd.DataFrame({
        "time": pd.to_datetime(d.time_utc).dt.tz_localize("UTC"),          # the file's times are UTC without a zone
        "camera_id": d.camera_id.values, "site": d.site.values, "p_flooded": d.p_flooded.values,
        "depth_pred_cm": d.depth_pred_cm.values, "depth_measured_cm": d.depth_measured_cm.values,
        "file": d.file.values, "run": d.run.values,
        "replay_of": pd.Series(pd.NaT, index=d.index, dtype="datetime64[ns, UTC]"),
    }).sort_values(["time", "camera_id", "file"]).reset_index(drop=True)
    return _checked(cams, "cameras"), _checked(readings, "camera_readings")


def _raw_series_length(path):
    """Values in the station's own raw series, before the reader drops any that do not parse."""
    feats = json.loads(Path(path).read_text()).get("features") or []
    for q in (feats[0]["properties"]["parameters"] if feats else []):
        if q["id"] == "water_level_raw" and q["observations"]["times"]:
            return len(q["observations"]["times"])
    return 0


def build_sensor_levels(root):
    """(sensor_levels, values dropped). Rows come from the flood chat's own reader, one call per station file."""
    root = Path(root)
    if (root / "data/raw/sunnyday").resolve() != Path(sunnyday.OUT).resolve():
        raise ValueError("the sensor reader points at a different folder than this build")
    parts, dropped = [], 0
    for path in sorted((root / SENSOR_DIR).glob("*.json")):
        sid = path.stem
        meta, lv = sunnyday.read_station(sid)
        dropped += _raw_series_length(path) - len(lv)
        if len(lv) == 0:
            continue                                                       # a camera with no sensor of its own
        road = sunnyday.ROAD_LEVEL_M.get(sid)
        depth = ((lv.level_m - road) * 100).clip(lower=0) if road is not None else pd.Series(np.nan, index=lv.index)
        if sid in sunnyday.ALWAYS_DRY:
            depth = pd.Series(0.0, index=lv.index)
        parts.append(pd.DataFrame({
            "time": pd.to_datetime(lv.level_time).dt.tz_localize("UTC"), "station": sid, "name": meta.get("name"),
            "lat": float(meta["lat"]), "lon": float(meta["lon"]), "level_m": lv.level_m.values,
            "road_level_m": np.nan if road is None else float(road), "depth_on_road_cm": depth.values,
            "replay_of": pd.Series(pd.NaT, index=lv.index, dtype="datetime64[ns, UTC]"),
        }))
    if not parts:
        raise ValueError("sensor_levels: no rows")
    out = pd.concat(parts, ignore_index=True).sort_values(["time", "station"]).reset_index(drop=True)
    if out.duplicated(["station", "time"]).any():
        raise ValueError("sensor readings repeat a (station, time)")
    return _checked(out, "sensor_levels"), int(dropped)


def build_pothole_reports(root):
    """Every located report, with its state road where the project's matcher finds one."""
    root = Path(root)
    reports, _limits, _meta = read_bundle(root / "data/raw")
    if len(reports) == 0:
        raise ValueError("pothole_reports: no rows")
    if reports.report_id.duplicated().any() or reports.received_date.isna().any():
        raise ValueError("pothole reports with a repeated id or a blank date")
    segs = gpd.read_parquet(root / SOURCES["ncdot_joined"], columns=["seg_id", "YEAR_LAST_REHAB", "geometry"]).to_crs(CRS_M)
    matched = pothole_labels.match_reports(reports.to_crs(CRS_M), segs)   # the same call as pothole_labels.main()
    labels = pd.read_parquet(root / SOURCES["pothole_labels"], columns=["seg_id", "n_pothole_all_time"])
    counts = labels.seg_id.map(matched.groupby("seg_id").size()).fillna(0).astype(int)
    if not np.array_equal(counts.values, labels.n_pothole_all_time.values):
        raise ValueError("report matching disagrees with pothole_labels.parquet: the label file is stale or the inputs changed")
    m = reports.merge(matched, on="report_id", how="left", validate="one_to_one")
    out = pd.DataFrame({
        "time": pd.to_datetime(m.received_date).dt.tz_localize("UTC"),     # read as UTC by the pull
        "report_id": m.report_id.values, "source": m.source.values, "request_type": m.request_type.values,
        "seg_id": m.seg_id.values, "dist_m": m.dist_m.values,
        "lon": m.geometry.x.values, "lat": m.geometry.y.values,
    }).sort_values(["time", "report_id"]).reset_index(drop=True)
    return _checked(out, "pothole_reports")


def build_all(root, _after_read=None):
    """Every table, the fingerprints of the files they came from, and the counts.

    Fingerprints are taken before and after reading; a file that changed in between refuses the build, so the
    load record always describes the bytes that were read. `_after_read` is a hook for the test of that."""
    root = Path(root)
    before = fingerprints(root)
    pred = _read_predictions(root)
    roads = build_roads(root, pred)
    shapes = build_road_shapes(root, pred)
    cameras, readings = build_cameras_and_readings(root)
    sensors, dropped = build_sensor_levels(root)
    potholes = build_pothole_reports(root)
    if _after_read is not None:
        _after_read()
    after = fingerprints(root)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    if changed:
        raise ValueError(f"source files changed while they were being read: {changed}")
    known = set(roads.seg_id)
    for name, d in (("cameras", cameras), ("pothole_reports", potholes)):
        unknown = set(d.seg_id.dropna()) - known
        if unknown:
            raise ValueError(f"{name}: {len(unknown)} matched roads are not in the road table, e.g. {sorted(unknown)[:3]}")
    tables = {"roads": roads, "road_shapes": shapes, "cameras": cameras, "camera_readings": readings,
              "sensor_levels": sensors, "pothole_reports": potholes}
    return SimpleNamespace(tables=tables, fingerprints=before, counts={k: len(v) for k, v in tables.items()},
                           sensor_values_dropped=dropped)


def _plain(v):
    """One cell as a plain Python value, blank as None."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, (float, np.floating)):
        v = float(v)
        if v != v:
            return None
        if v in (float("inf"), float("-inf")):
            raise ValueError("infinity")
        return v
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, pd.Timestamp):
        if v.tzinfo is None:
            raise ValueError("a time without a zone")
        return v.to_pydatetime()
    return v


def to_rows(df, columns):
    """Tuples for the database, columns picked by name. Blank is None; a time without a zone or infinity raises."""
    cols = []
    for c in columns:
        s = df[c]
        try:
            if ptypes.is_datetime64_any_dtype(s):
                if getattr(s.dt, "tz", None) is None:
                    raise ValueError("a time without a zone")
                cols.append([None if v is pd.NaT else v.to_pydatetime() for v in s])
            elif ptypes.is_float_dtype(s) and not ptypes.is_extension_array_dtype(s):
                a = s.to_numpy(dtype="float64")
                if np.isinf(a).any():
                    raise ValueError("infinity")
                cols.append([None if v != v else v for v in a.tolist()])
            else:
                cols.append([_plain(v) for v in s.tolist()])
        except ValueError as e:
            raise ValueError(f"{c}: {e}") from None
    return zip(*cols)
