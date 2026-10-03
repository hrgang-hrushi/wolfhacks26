"""Filter the raw Helene pulls to genuine Helene failure evidence.

Usage:  uv run python -m src.pipeline.helene_points
Reads:  data/raw/helene_{ncdot_tims,structures,ncgs_hwm,usgs_landslides,usace_hwm}.parquet
Writes: data/raw/helene_points.parquet   columns: source, evidence, geometry (EPSG:4326)
        data/raw/helene_clear_structures.parquet   inspected, no damage (known negatives)

evidence = "damage"  -> something physically failed at/near the road (strong label)
           "hazard"  -> landslide or flood mark nearby (weaker label)
Rules are deliberately simple and printed, so the team can argue with them.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAW = Path("data/raw")

# TIMS: all 1,502 rows are the Helene event, but most are closures/maintenance.
# Keep only rows whose free text describes the road or its support being lost.
TIMS_LOSS = (r"wash|flood|high water|landslide|rock ?slide|mud ?slide|slide|"
             r"bridge (?:out|collapse|damage|gone)|collapse|sink ?hole|undermin|storm damage|impass|"
             r"erosion|road (gone|out)|missing|destroy")

# Structures: serious damage words. Drift/debris-only and superficial do NOT count.
STRUCT_LOSS = (r"scour|washout|gone|missing|undermin|failed|settled|sink|fill|"
               r"erosion|severe|broken|collapse|pile|crutch")


def load(name):
    p = RAW / f"helene_{name}.parquet"
    return gpd.read_parquet(p) if p.exists() else None


def txt(df, cols):
    return df[[c for c in cols if c in df]].fillna("").astype(str).agg(" ".join, axis=1).str.lower()


def main():
    parts = []

    t = load("ncdot_tims")
    if t is not None:
        keep = txt(t, ["Reason", "Condition", "EventSubType", "Location"]).str.contains(TIMS_LOSS)
        print(f"tims: {len(t)} rows, {keep.sum()} describe road/structure loss")
        parts.append(t[keep][["geometry"]].assign(source="ncdot_tims", evidence="damage"))

    s = load("structures")
    if s is not None:
        status_bad = s["Status"].isin(["Likely Repair", "Likely Replace"])
        type_bad = txt(s, ["Damage_Type"]).str.contains(STRUCT_LOSS)
        bad = status_bad | type_bad
        print(f"structures: {len(s)} rows, {status_bad.sum()} repair/replace, "
              f"{bad.sum()} damaged by status or type")
        parts.append(s[bad][["geometry"]].assign(source="structures", evidence="damage"))
        clear = s[s["Status"] == "Inspected - No Damage"][["geometry"]]
        clear.to_parquet(RAW / "helene_clear_structures.parquet")
        print(f"structures: {len(clear)} inspected with no damage -> helene_clear_structures.parquet")

    h = load("ncgs_hwm")
    if h is not None:
        # file holds ~40 storms back to 1940s; only Helene counts
        is_h = h["storm_name"].fillna("").str.lower().str.startswith("hurricane helene")
        good = ~h["confidence"].fillna("").str.startswith(("VP", "Unknown"))
        print(f"ncgs_hwm: {len(h)} rows, {is_h.sum()} Helene, {(is_h & good).sum()} after dropping VP/unknown")
        parts.append(h[is_h & good][["geometry"]].assign(source="ncgs_hwm", evidence="hazard"))

    ls = load("usgs_landslides")
    if ls is not None:
        print(f"usgs_landslides: {len(ls)} rows (TN/VA points drop out at match time)")
        parts.append(ls[["geometry"]].assign(source="usgs_landslides", evidence="hazard"))

    u = load("usace_hwm")
    if u is not None:
        print(f"usace_hwm: {len(u)} rows (3 states; non-NC drop out at match time)")
        parts.append(u[["geometry"]].assign(source="usace_hwm", evidence="hazard"))

    out = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
    out.to_parquet(RAW / "helene_points.parquet")
    print("\n", out.groupby(["source", "evidence"]).size().to_string())
    print("saved", RAW / "helene_points.parquet")


if __name__ == "__main__":
    main()