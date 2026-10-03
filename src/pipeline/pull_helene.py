"""Pull Hurricane Helene point records for the flood-label head.

Usage:  uv run python -m src.pipeline.pull_helene [ncdot ncgs_hwm structures usgs_landslides usace_hwm]
Writes: data/raw/helene_<source>.parquet  (points, EPSG:4326)
Prints: record count + columns for each source, so you can paste the report.

NOT TESTED against the live services (written without network access to them).
Field names are discovered at runtime, nothing is hard-coded except URLs.
"""
import io
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

RAW = Path("data/raw")
RAW.mkdir(parents=True, exist_ok=True)

AGS = "https://services.arcgis.com/NuWFvHYDMVmmxMeM/ArcGIS/rest/services"
ARCGIS_LAYERS = {
    # historical Helene incidents (NOT the live feed): road closures, washouts, debris
    "ncdot_tims": f"{AGS}/State_Maintained_Historical_TIMS_Incidents_Hurricane_Helene/FeatureServer/0",
    # high-water marks hosted by NCDOT, source NC Geological Survey
    "ncgs_hwm": f"{AGS}/Helene_HWM_NCGS/FeatureServer/0",
    # bridges/culverts in the Helene area with inspection status
    "structures": f"{AGS}/2024_NCDOT_SMU_Post_Helene_Structure_Inspection_Status/FeatureServer/0",
}
SCIENCEBASE_ITEM = "https://www.sciencebase.gov/catalog/item/674634a1d34e6d1dac3abddc?format=json"
USACE_ZIP = ("https://media.defense.gov/2025/Aug/08/2003775269/-1/-1/1/"
             "FINAL_HURRICANE_HELENE_HWM_PRODUCTS.ZIP/FINAL_HURRICANE_HELENE_HWM_PRODUCTS.ZIP")


def fetch_arcgis_points(layer_url: str) -> gpd.GeoDataFrame:
    """Page through an ArcGIS feature layer, request WGS84, build points."""
    rows, offset = [], 0
    while True:
        r = requests.get(f"{layer_url}/query", params={
            "where": "1=1", "outFields": "*", "returnGeometry": "true",
            "outSR": 4326, "f": "json", "resultOffset": offset,
            "resultRecordCount": 1000,
        }, timeout=120)
        r.raise_for_status()
        j = r.json()
        if "error" in j:
            raise RuntimeError(j["error"])
        feats = j.get("features", [])
        for f in feats:
            g = f.get("geometry") or {}
            if "x" in g and "y" in g:
                rows.append({**f["attributes"], "geometry": Point(g["x"], g["y"])})
        offset += len(feats)
        if not feats or not j.get("exceededTransferLimit"):
            break
    return gpd.GeoDataFrame(rows, crs="EPSG:4326")


def fetch_usgs_landslides() -> gpd.GeoDataFrame:
    item = requests.get(SCIENCEBASE_ITEM, timeout=60).json()
    urls = [f["downloadUri"] for f in item.get("files", [])
            if f["name"].lower().endswith(".geojson")]
    if not urls:
        raise RuntimeError("no geojson on the ScienceBase item; check item files")
    return gpd.read_file(urls[0]).to_crs(4326)


def fetch_usace_hwm() -> gpd.GeoDataFrame:
    manual = RAW / "usace_hwm.zip"  # fallback: download in a browser, save here
    if manual.exists():
        content = manual.read_bytes()
    else:
        r = requests.get(USACE_ZIP, timeout=300, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                                  "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"})
        content = r.content
        if not content.startswith(b"PK"):
            raise RuntimeError(
                f"got {r.status_code} {r.headers.get('content-type')} instead of a zip; "
                f"download the ZIP in a browser and save it as {manual}")
    z = zipfile.ZipFile(io.BytesIO(content))
    names = z.namelist()
    print("  zip contents:", *names[:40], sep="\n    ")
    z.extractall(RAW / "_usace_hwm")
    root = RAW / "_usace_hwm"
    for pat in ("*.shp", "*.geojson", "*.gpkg"):
        hits = list(root.rglob(pat))
        if hits:
            return gpd.read_file(hits[0]).to_crs(4326)
    gdbs = list(root.rglob("*.gdb"))
    if gdbs:
        return gpd.read_file(gdbs[0]).to_crs(4326)
    # fall back to Excel with lat/lon columns
    for x in root.rglob("*.xls*"):
        df = pd.read_excel(x)
        lat = next((c for c in df.columns if "lat" in str(c).lower()), None)
        lon = next((c for c in df.columns if "lon" in str(c).lower()), None)
        if lat and lon:
            return gpd.GeoDataFrame(
                df, geometry=gpd.points_from_xy(df[lon], df[lat]), crs="EPSG:4326")
    raise RuntimeError("no spatial file found in USACE zip; inspect _usace_hwm/")


def main(which):
    jobs = {
        **{k: (lambda u=u: fetch_arcgis_points(u)) for k, u in ARCGIS_LAYERS.items()},
        "usgs_landslides": fetch_usgs_landslides,
        "usace_hwm": fetch_usace_hwm,
    }
    for name in which or jobs:
        print(f"\n== {name}")
        try:
            gdf = jobs[name]()
        except Exception as e:  # keep going so one dead source doesn't block the rest
            print("  FAILED:", repr(e))
            continue
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
        for c in gdf.columns:  # parquet-safe: no mixed-type object columns
            if c != "geometry" and gdf[c].dtype == object:
                gdf[c] = gdf[c].astype(str)
        out = RAW / f"helene_{name}.parquet"
        gdf.to_parquet(out)
        b = gdf.total_bounds
        print(f"  records: {len(gdf)}  bounds(lon/lat): {b.round(3).tolist()}")
        print("  columns:", list(gdf.columns))
        print("  saved:", out)


if __name__ == "__main__":
    main(sys.argv[1:])
