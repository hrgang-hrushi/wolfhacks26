"""One side table of crash and traffic columns per segment, for the model and the map.

Usage:  python -m src.pipeline.traffic_crash   (after pull_crashes and pull_probe_aadt)
Reads:  data/raw/crash_attached.parquet, data/raw/aadt_probe_attached.parquet, data/raw/ncdot_joined.parquet
Writes: data/processed/traffic_crash.parquet   one row per seg_id; cr_ and tr_ columns
        handoff/traffic_crash.parquet          the same table for the map (rounded, tracked in git);
                                               join it to handoff/predictions_geo.parquet on seg_id

Adds one column on top of the two inputs:
  cr_crash_per_mvm   crashes per million vehicle miles, 2021-2025:
                     crashes / (vehicles a day x 365 x 5 years x covered miles / 1,000,000).
                     Blank where there is no traffic number or no section score.
segments.parquet is not touched; join this file on seg_id.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.pipeline.milepost import RAW, load_segments, write_atomic
from src.pipeline.pull_crashes import SECTION_YEARS

OUT = Path("data/processed")
HANDOFF = Path("handoff")


def combine(segs, crash, traffic):
    d = segs[["seg_id", "seg_mi"]].merge(crash, on="seg_id", validate="one_to_one")
    d = d.merge(traffic, on="seg_id", validate="one_to_one")
    vehicle_miles = d.tr_aadt_best * 365 * SECTION_YEARS * d.seg_mi * d.cr_cover / 1e6
    d["cr_crash_per_mvm"] = (d.cr_crash_n / vehicle_miles).where(vehicle_miles > 0)
    return d.drop(columns="seg_mi")


def main(raw=RAW, out=OUT, handoff_dir=HANDOFF):
    d = combine(load_segments(raw), pd.read_parquet(raw / "crash_attached.parquet"),
                pd.read_parquet(raw / "aadt_probe_attached.parquet"))
    assert d.seg_id.is_unique and np.isfinite(d.cr_crash_per_mvm.dropna()).all()
    write_atomic(d, out / "traffic_crash.parquet")
    print(f"saved {out / 'traffic_crash.parquet'} {d.shape}")
    handoff_dir.mkdir(parents=True, exist_ok=True)
    num = d.select_dtypes("float").columns
    small = d.assign(**{c: d[c].round(3).astype("float32") for c in num})
    tmp = handoff_dir / "traffic_crash.parquet.tmp"
    small.to_parquet(tmp, compression="zstd")
    tmp.replace(handoff_dir / "traffic_crash.parquet")
    print(f"crash rate available for {d.cr_crash_per_mvm.notna().mean():.1%} of segments; "
          f"median {d.cr_crash_per_mvm.median():.2f}, 90th percentile {d.cr_crash_per_mvm.quantile(.9):.2f} "
          f"crashes per million vehicle miles")


if __name__ == "__main__":
    main()
