"""Terrain features at segment midpoints from dem.tif, no pysheds.
Writes data/processed/terrain.parquet: seg_id, tn_elev, tn_slope, tn_relief1k, tn_hand_proxy
"""
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window

P = Path("data/processed")
d = pd.read_parquet(P / "segments.parquet", columns=["seg_id", "mid_x", "mid_y"])
R = 17  # 17 px * 30 m ~ 510 m radius -> ~1 km window

with rasterio.open(P / "dem" / "dem.tif") as ds:
    rows, cols = rasterio.transform.rowcol(ds.transform, d.mid_x.values, d.mid_y.values)
    rows, cols = np.array(rows), np.array(cols)
    out = np.full((len(d), 4), np.nan, dtype="float32")
    for i in range(len(d)):
        r, c = rows[i], cols[i]
        if r < R or c < R or r >= ds.height - R or c >= ds.width - R:
            continue
        w = ds.read(1, window=Window(c - R, r - R, 2 * R + 1, 2 * R + 1)).astype("float32")
        if not np.isfinite(w[R, R]):
            continue
        gy, gx = np.gradient(w, 30.0)
        slope = np.hypot(gy[R, R], gx[R, R])
        out[i] = [w[R, R], slope, np.nanmax(w) - np.nanmin(w), w[R, R] - np.nanmin(w)]
        if i % 20000 == 0:
            print(i, flush=True)

t = pd.DataFrame(out, columns=["tn_elev", "tn_slope", "tn_relief1k", "tn_hand_proxy"])
t.insert(0, "seg_id", d.seg_id.values)
t.to_parquet(P / "terrain.parquet")
print(t.describe().round(2).to_string())