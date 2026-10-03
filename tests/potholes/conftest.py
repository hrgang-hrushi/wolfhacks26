"""Fakes for the pothole tests: scripted report servers, tiny road networks in state-plane metres,
and a processed-data folder shaped like the real one."""
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import requests
from shapely.geometry import LineString, Point, box, mapping

from src.model import common

CRS_M = "EPSG:32119"
NOW = pd.Timestamp("2026-10-03 12:00:00")
MS_2024 = 1717200000000   # 2024-06-01 00:00 UTC


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code, self.payload = status, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        if self.payload is None:
            raise ValueError("not JSON")
        return self.payload


class Session:
    """Calls handler(url, params) for every GET and records (url, params, headers)."""

    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        return self.handler(url, params)


def clt(i, kind="CDOT POTHOLE REPAIR", lon=-80.84, lat=35.22, ms=MS_2024, shape=True, **over):
    a = {"REQUEST_NO": i, "REQUEST_TYPE": kind, "RECEIVED_DATE": ms, "LONGITUDE": lon, "LATITUDE": lat}
    a.update(over)
    return {"attributes": a, "geometry": {"x": lon, "y": lat} if shape else None}


def ral(i, kind="Pothole", lon=-78.64, lat=35.78, ms=1753792227000):
    return {"attributes": {"NUMBER": f"SRC{i:07d}", "REQUEST_TYPE": kind, "APPLIED_DATE": ms},
            "geometry": {"x": lon, "y": lat}}


def tiger(cities=("Charlotte", "Raleigh")):
    shapes = {"Charlotte": box(-81.0, 35.0, -80.6, 35.4), "Raleigh": box(-78.8, 35.7, -78.5, 35.95)}
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"NAME": f"{c} city", "BASENAME": c, "STATE": "37", "GEOID": "37" + c[:3]},
         "geometry": mapping(shapes.get(c, box(0, 0, 1, 1)))} for c in cities]}


def server(charlotte, raleigh, limits=None, counts=None):
    """Fake Charlotte, Raleigh and Census servers. `counts` overrides the row count a layer claims."""
    limits = tiger() if limits is None else limits
    layers = {"gis.charlottenc.gov": ("charlotte", charlotte), "services.arcgis.com": ("raleigh", raleigh)}

    def handler(url, params):
        host = url.split("/")[2]
        if host == "tigerweb.geo.census.gov":
            return Resp(payload=limits)
        name, rows = layers[host]
        if isinstance(rows, Resp):
            return rows
        if params.get("returnCountOnly"):
            return Resp(payload={"count": (counts or {}).get(name, len(rows))})
        o, n = params["resultOffset"], params["resultRecordCount"]
        return Resp(payload={"features": rows[o:o + n]})
    return handler


def segs_m(rows):
    """Segments in state-plane metres from (seg_id, x0, y0, x1, y1, rehab_year) tuples."""
    return gpd.GeoDataFrame({"seg_id": [r[0] for r in rows], "YEAR_LAST_REHAB": [r[5] for r in rows]},
                            geometry=[LineString([(r[1], r[2]), (r[3], r[4])]) for r in rows], crs=CRS_M)


def reports_m(rows):
    """Reports in state-plane metres from (id, x, y, request_type, date) tuples."""
    return gpd.GeoDataFrame({
        "source": ["raleigh" if r[3] == "Pothole" else "charlotte" for r in rows],
        "report_id": [f"t:{r[0]}" for r in rows], "request_type": [r[3] for r in rows],
        "received_date": pd.to_datetime([r[4] for r in rows])},
        geometry=[Point(r[1], r[2]) for r in rows], crs=CRS_M)


def city_m(x0=500000, y0=195000, x1=505000, y1=205000, name="charlotte"):
    return gpd.GeoDataFrame({"city": [name]}, geometry=[box(x0, y0, x1, y1)], crs=CRS_M)


def processed_dir(path, table, potholes="age", seed=0):
    """A folder like data/processed: targets with folds, pothole labels, held-out predictions and the split.
    Blocks 100-103 are Charlotte, 104-105 Raleigh, the rest outside. `potholes` picks what drives reports:
    "age" (old pavement), "traffic" (busy roads) or "none" (no reports at all)."""
    rng = np.random.default_rng(seed)
    d = common.add_folds(common.add_targets(table))
    d["length_m"] = d.pv_LENGTH * 1609.344
    bx = (d.mid_x // 5000).astype(int)
    city = np.where(bx < 104, "charlotte", np.where(bx < 106, "raleigh", None))
    age = d.pv_age_at_survey.fillna(d.pv_age_at_survey.median())
    z = {"age": (age - 15) / 6, "traffic": (np.log10(d.tr_aadt.fillna(3000)) - 3.5) * 3,
         "none": np.full(len(d), -50.0)}[potholes]
    hit = rng.random(len(d)) < 1 / (1 + np.exp(-(z - 0.5)))
    n = np.where(hit, rng.integers(1, 4, len(d)), 0)
    years = np.where(city == "charlotte", 3.75, np.where(city == "raleigh", 1.42, np.nan))
    in_city = pd.notna(city)
    lab = pd.DataFrame({
        "seg_id": d.seg_id, "pothole_city": city, "pothole_exposure_years": years,
        "n_pothole_reports": np.where(in_city, n, 0),
        "n_pothole_cdot": np.where(city == "charlotte", n, 0), "n_pothole_ncdot": 0,
        "n_pothole_raleigh": np.where(city == "raleigh", n, 0), "n_pothole_all_time": np.where(in_city, n, 0)})
    lab["n_pothole_ncdot"] = np.where((city == "charlotte") & (rng.random(len(d)) < 0.3), lab.n_pothole_cdot, 0)
    lab["y_pothole_rate"] = np.where(in_city, lab.n_pothole_reports / (d.pv_LENGTH * years), np.nan)
    lab["y_pothole_any"] = np.where(in_city, (lab.n_pothole_reports > 0).astype(float), np.nan)
    pred = pd.DataFrame({"seg_id": d.seg_id, "pred_rate": d.y_rate.fillna(1.0) + rng.normal(0, 0.3, len(d)),
                         "pred_crack": rng.random(len(d)), "rate_heldout": d.y_rate.notna().values,
                         "crack_heldout": d.y_crack.notna().values})
    path.mkdir(parents=True, exist_ok=True)
    d.to_parquet(path / "segments_targets.parquet")
    common.write_split(d, path / "split.parquet")
    lab.to_parquet(path / "pothole_labels.parquet")
    pred.to_parquet(path / "predictions.parquet")
    return path


@pytest.fixture
def fake():
    """The helpers above, for test modules (conftest files are not importable by name)."""
    return SimpleNamespace(Resp=Resp, Session=Session, clt=clt, ral=ral, tiger=tiger, server=server, segs_m=segs_m,
                           reports_m=reports_m, city_m=city_m, processed_dir=processed_dir, NOW=NOW, CRS_M=CRS_M,
                           MS_2024=MS_2024)
