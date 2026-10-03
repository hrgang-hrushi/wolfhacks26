"""Pull public pothole reports for Charlotte and Raleigh, and the two city boundaries.

Usage:  uv run python -m src.pipeline.pull_potholes
Writes: data/raw/pothole_reports.parquet     one row per report: source, report_id, request_type,
                                             received_date (the server's timestamp read as UTC; Charlotte's
                                             look like local time, so they can be up to five hours off),
                                             point geometry (EPSG:4326)
        data/raw/city_limits.parquet         one polygon per city (US Census incorporated places)
        data/raw/pothole_reports.meta.json   written last: pull time, counts kept and dropped, and
                                             the sha256 of the two files above

Reports are complaints, not a survey: busy roads in crowded areas get reported more.
"""
import argparse
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from src.model.common import write_atomic
from src.pipeline.arcgis_fetch import UA, ArcGISError, fetch_all

RAW = Path("data/raw")
NC_BBOX = (-84.5, 33.7, -75.3, 36.7)  # lon min, lat min, lon max, lat max
MAX_DUP_SHARE = 0.01
SOURCES = {
    "charlotte": dict(
        url="https://gis.charlottenc.gov/arcgis/rest/services/ODP/ServiceRequests311/MapServer/0",
        where="REQUEST_TYPE IN ('CDOT POTHOLE REPAIR','NCDOT POTHOLE REQUEST')",
        types=("CDOT POTHOLE REPAIR", "NCDOT POTHOLE REQUEST"),
        id="REQUEST_NO", type="REQUEST_TYPE", date="RECEIVED_DATE", xy=("LONGITUDE", "LATITUDE"), page=5000),
    "raleigh": dict(
        url="https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/Ask_Raleigh_Requests/FeatureServer/0",
        where="SERVICE = 'Potholes & Sinkholes' AND REQUEST_TYPE = 'Pothole'",
        types=("Pothole",),
        id="NUMBER", type="REQUEST_TYPE", date="APPLIED_DATE", xy=None, page=1000),
}
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4/query"
CITIES = ("charlotte", "raleigh")
REPORT_COLS = ["source", "report_id", "request_type", "received_date", "geometry"]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fields(cfg):
    return [cfg["id"], cfg["type"], cfg["date"]] + list(cfg["xy"] or ())


def _usable(lon, lat):
    return (lon is not None and lat is not None and np.isfinite(lon) and np.isfinite(lat)
            and abs(lon) > 1e-9 and abs(lat) > 1e-9)


def clean(rows, source, now):
    """Located, dated, in-state, unique reports of the pothole types. Returns (GeoDataFrame, dropped counts)."""
    cfg, drop, seen, keep = SOURCES[source], Counter(), set(), []
    w, s, e, n = NC_BBOX
    for r in rows:
        if r.get(cfg["type"]) not in cfg["types"]:
            drop["wrong_type"] += 1
            continue
        lon, lat = r.get("lon"), r.get("lat")
        if not _usable(lon, lat) and cfg["xy"]:
            lon, lat = r.get(cfg["xy"][0]), r.get(cfg["xy"][1])
        if not _usable(lon, lat):
            drop["unlocated"] += 1
            continue
        if not (w <= lon <= e and s <= lat <= n):
            drop["out_of_state"] += 1
            continue
        if r.get(cfg["date"]) is None:
            drop["undated"] += 1
            continue
        when = pd.Timestamp(r[cfg["date"]], unit="ms")  # epoch milliseconds, read as UTC
        if when > now:
            drop["future"] += 1
            continue
        rid = f"{source}:{r[cfg['id']]}"
        if rid in seen:
            drop["duplicate"] += 1
            continue
        seen.add(rid)
        keep.append((source, rid, r[cfg["type"]], when, lon, lat))
    if rows and drop["duplicate"] > MAX_DUP_SHARE * len(rows):
        raise ValueError(f"{source}: {drop['duplicate']:,} duplicate report ids in {len(rows):,} rows")
    d = pd.DataFrame(keep, columns=["source", "report_id", "request_type", "received_date", "lon", "lat"])
    d["received_date"] = pd.to_datetime(d.received_date)
    g = gpd.GeoDataFrame(d.drop(columns=["lon", "lat"]), geometry=gpd.points_from_xy(d.lon, d.lat), crs="EPSG:4326")
    return g[REPORT_COLS], dict(drop)


def pull_city_limits(session):
    r = session.get(TIGER, params={"where": "STATE='37' AND BASENAME IN ('Charlotte','Raleigh')",
                                   "outFields": "NAME,BASENAME,STATE,GEOID", "outSR": 4326, "f": "geojson"},
                    headers=UA, timeout=120)
    r.raise_for_status()
    j = r.json()
    if not isinstance(j, dict) or "error" in j or not isinstance(j.get("features"), list):
        raise ArcGISError(f"city limits: no features in the reply: {str(j)[:200]}")
    g = gpd.GeoDataFrame.from_features(j["features"], crs="EPSG:4326") if j["features"] else gpd.GeoDataFrame()
    city = g.BASENAME.str.lower() if len(g) else pd.Series(dtype=object)
    if sorted(city) != sorted(CITIES) or g.geometry.is_empty.any() or g.geometry.isna().any():
        raise ArcGISError(f"city limits: expected one polygon each for {CITIES}, got {sorted(city)}")
    return gpd.GeoDataFrame({"city": city.values, "geoid": g.GEOID.values}, geometry=g.geometry.values, crs="EPSG:4326")


def read_bundle(raw=RAW):
    """(reports, city limits, meta). Refuses files that do not match the manifest written with them."""
    raw = Path(raw)
    meta_file = raw / "pothole_reports.meta.json"
    if not meta_file.exists():
        raise FileNotFoundError(f"{meta_file} is missing: run src.pipeline.pull_potholes first")
    meta = json.loads(meta_file.read_text())
    for name, want in meta["sha256"].items():
        if not (raw / name).exists() or sha256_file(raw / name) != want:
            raise ValueError(f"{raw / name} does not match {meta_file.name}: rerun src.pipeline.pull_potholes")
    return gpd.read_parquet(raw / "pothole_reports.parquet"), gpd.read_parquet(raw / "city_limits.parquet"), meta


def main(raw=RAW, session=None, now=None, sleep=time.sleep):
    raw = Path(raw)
    session = session or requests.Session()
    now = now or pd.Timestamp.now("UTC").tz_localize(None)
    parts, meta = [], {"pulled_at": now.isoformat(), "sources": {}}
    for name, cfg in SOURCES.items():
        rows = fetch_all(cfg["url"], cfg["where"], fields(cfg), geometry=True, page=cfg["page"],
                         session=session, sleep=sleep)
        g, drop = clean(rows, name, now)
        meta["sources"][name] = {"server_count": len(rows), "kept": len(g), "dropped": drop,
                                 "by_type": g.request_type.value_counts().to_dict()}
        print(f"{name}: server {len(rows):,}, kept {len(g):,}, dropped {drop}", flush=True)
        parts.append(g)
    limits = pull_city_limits(session)
    reports = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")

    # everything is in hand before the first write; the manifest goes last and ties the files together
    raw.mkdir(parents=True, exist_ok=True)
    write_atomic(raw / "pothole_reports.parquet", reports.to_parquet)
    write_atomic(raw / "city_limits.parquet", limits.to_parquet)
    meta["sha256"] = {f: sha256_file(raw / f) for f in ("pothole_reports.parquet", "city_limits.parquet")}
    tmp = raw / "pothole_reports.meta.json.tmp"
    tmp.write_text(json.dumps(meta, indent=1))
    os.replace(tmp, raw / "pothole_reports.meta.json")
    print(f"saved {raw / 'pothole_reports.parquet'}: {len(reports):,} located reports")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    main()
