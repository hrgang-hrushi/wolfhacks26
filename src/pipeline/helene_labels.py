"""Label each state road segment: did a Helene failure point fall within 30 m?

Usage:  uv run python -m src.pipeline.helene_labels
Reads:  data/raw/ncdot_joined.parquet          (segments, seg_id + LineString, EPSG:4326)
        data/raw/helene_points.parquet         (from helene_points.py)
        data/raw/helene_structures.parquet     (used only to mark where NCDOT looked)
Writes: data/raw/helene_labels.parquet         (no geometry; one row per seg_id)

Columns:
  y_helene_damage   1 if a damage point (TIMS loss, damaged structure) is within 30 m
  y_helene_hazard   1 if a landslide / high-water-mark point is within 30 m
  y_helene_failed   1 if either (the README definition: any point within 30 m)
  n_<source>        count of points per source within 30 m
  in_helene_zone    1 if the segment is within 5 km of any inspected structure.
                    Segments outside the zone have NO label coverage: a 0 there means
                    "unrecorded", not "survived". Train the flood head on in_helene_zone==1.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAW = Path("data/raw")
CRS_M = "EPSG:32119"  # NAD83 / North Carolina (meters)
MATCH_M = 30
ZONE_M = 5000


def main():
    segs = gpd.read_parquet(RAW / "ncdot_joined.parquet")[["seg_id", "geometry"]].to_crs(CRS_M)
    pts = gpd.read_parquet(RAW / "helene_points.parquet").to_crs(CRS_M)
    print(f"{len(segs):,} segments, {len(pts):,} evidence points")

    # any segment within 30 m of a point (not just the nearest one: dual carriageways)
    hit = gpd.sjoin(pts, segs, predicate="dwithin", distance=MATCH_M, how="inner")
    print(f"{hit.index.nunique():,} points land within {MATCH_M} m of a segment "
          f"({hit.seg_id.nunique():,} distinct segments)")

    out = pd.DataFrame({"seg_id": segs.seg_id.values})
    for ev in ("damage", "hazard"):
        n = hit[hit.evidence == ev].groupby("seg_id").size()
        out[f"y_helene_{ev}"] = out.seg_id.map(n).fillna(0).gt(0).astype("int8")
    out["y_helene_failed"] = (out.y_helene_damage | out.y_helene_hazard).astype("int8")
    for src, g in hit.groupby("source"):
        out[f"n_{src}"] = out.seg_id.map(g.groupby("seg_id").size()).fillna(0).astype("int16")

    # where did NCDOT actually look? segments near any inspected structure
    st = gpd.read_parquet(RAW / "helene_structures.parquet").to_crs(CRS_M)
    near = gpd.sjoin(st, segs, predicate="dwithin", distance=ZONE_M, how="inner")
    zone = set(near.seg_id)
    out["in_helene_zone"] = out.seg_id.isin(zone).astype("int8")

    out.to_parquet(RAW / "helene_labels.parquet")
    z = out[out.in_helene_zone == 1]
    print(f"\nin_helene_zone: {len(z):,} segments")
    print(f"failed (damage): {out.y_helene_damage.sum():,} total, {z.y_helene_damage.sum():,} in zone")
    print(f"failed (hazard): {out.y_helene_hazard.sum():,} total, {z.y_helene_hazard.sum():,} in zone")
    print(f"failed (any):    {out.y_helene_failed.sum():,} total, {z.y_helene_failed.sum():,} in zone "
          f"({100 * z.y_helene_failed.mean():.1f}% of zone)")
    print("saved", RAW / "helene_labels.parquet")


if __name__ == "__main__":
    main()
