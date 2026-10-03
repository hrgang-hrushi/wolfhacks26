"""Assemble the feature table: one row per segment, columns prefixed by group.

Usage:  uv run python -m src.pipeline.features
Writes: data/processed/segments.parquet
Terrain (tn_) is added only if the DEM rasters exist; chips are flagged by file presence.
"""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
DEM = ROOT / "data" / "processed" / "dem"
OUT = ROOT / "data" / "processed"
CRS_M = "EPSG:32119"


def sample(tif: Path, xs, ys):
    import rasterio
    with rasterio.open(tif) as ds:
        return np.array([v[0] for v in ds.sample(zip(xs, ys))], dtype="float32")


def main():
    seg = gpd.read_parquet(RAW / "ncdot_joined.parquet")
    print(f"{len(seg):,} segments; columns: {len(seg.columns)}")
    seg = seg.rename(columns={c: f"pv_{c}" for c in seg.columns
                              if c not in ("seg_id", "geometry")})

    seg = seg.merge(pd.read_parquet(RAW / "aadt_attached.parquet"), on="seg_id", how="left")
    seg = seg.merge(pd.read_parquet(RAW / "helene_labels.parquet"), on="seg_id", how="left")
    seg = seg.rename(columns={c: f"y_{c[2:]}" if c.startswith("y_") else c for c in seg.columns})

    # midpoints in state plane metres
    mid = shapely.line_interpolate_point(seg.geometry.to_crs(CRS_M).values, 0.5, normalized=True)
    seg["mid_x"], seg["mid_y"] = shapely.get_x(mid), shapely.get_y(mid)
    seg["length_m"] = seg.geometry.to_crs(CRS_M).length

    if (DEM / "slope.tif").exists() and (DEM / "flowacc.tif").exists():
        seg["tn_elev"] = sample(DEM / "dem.tif", seg.mid_x, seg.mid_y)
        seg["tn_slope"] = sample(DEM / "slope.tif", seg.mid_x, seg.mid_y)
        seg["tn_flowacc"] = np.log1p(sample(DEM / "flowacc.tif", seg.mid_x, seg.mid_y))
        print("terrain columns added")
    else:
        print("DEM rasters not found, skipping terrain (rerun after dem.py finishes)")

    from src.pipeline.chips import chip_path
    seg["im_has_chip"] = [chip_path(s).exists() for s in seg.seg_id]

    OUT.mkdir(parents=True, exist_ok=True)
    seg.drop(columns="geometry").to_parquet(OUT / "segments.parquet")
    gpd.GeoDataFrame(seg[["seg_id", "geometry"]]).to_parquet(OUT / "segments_geom.parquet")
    print(f"saved {OUT / 'segments.parquet'}  shape={seg.shape}")
    print("pv_ columns:", [c for c in seg.columns if c.startswith("pv_")][:40])


if __name__ == "__main__":
    main()