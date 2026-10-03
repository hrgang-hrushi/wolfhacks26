"""Attach NCDOT traffic-segment AADT to every state road segment.

Usage:  uv run python -m src.pipeline.pull_aadt
Reads:  data/raw/ncdot_joined.parquet   (seg_id, ROUTEID, BEG_MP, END_MP, asph_AADT)
Writes: data/raw/ncdot_aadt_segments.parquet   raw NCDOT traffic segments (no geometry)
        data/raw/aadt_attached.parquet         one row per seg_id, tr_ columns

Join: same ROUTEID, then the traffic segment whose milepost range overlaps ours the most.
No spatial matching, because both tables use NCDOT's linear referencing.

Columns written (README prefix tr_):
  tr_aadt          best available AADT (traffic segments first, pavement survey second)
  tr_aadtt         truck AADT (traffic segments only)
  tr_su_pct, tr_mu_pct   single / multi-unit truck share
  tr_aadt_source   "traffic_segments" | "pavement_survey" | "none"
  tr_has_count     1 if tr_aadt is not null
"""
from pathlib import Path

import numpy as np
import pandas as pd
import requests

RAW = Path("data/raw")
BASE = "https://services.arcgis.com/NuWFvHYDMVmmxMeM/ArcGIS/rest/services/NCDOT_AADT_Traffic_Segmentation/FeatureServer"
LAYERS = {1: "secondary_non_system", 2: "primaries", 3: "interstates"}
KEEP = ["RouteID", "BeginMP", "EndMP", "AADT", "AADTT", "SU_PCT", "MU_PCT", "SOURCE"]


def fetch_layer(layer_id: int) -> pd.DataFrame:
    rows, offset = [], 0
    while True:
        r = requests.get(f"{BASE}/{layer_id}/query", params={
            "where": "1=1", "outFields": ",".join(KEEP), "returnGeometry": "false",
            "f": "json", "resultOffset": offset, "resultRecordCount": 1000,
        }, timeout=120)
        r.raise_for_status()
        j = r.json()
        if "error" in j:
            raise RuntimeError(j["error"])
        feats = j.get("features", [])
        rows += [f["attributes"] for f in feats]
        offset += len(feats)
        if not feats or not j.get("exceededTransferLimit"):
            break
    return pd.DataFrame(rows)


def norm_route(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str[-8:]

def attach(segs: pd.DataFrame, tr: pd.DataFrame) -> pd.DataFrame:
    """Best-overlap join of traffic segments onto road segments."""
    s = segs[["seg_id", "ROUTEID", "BEG_MP", "END_MP"]].copy()
    s["rid"] = norm_route(s["ROUTEID"])
    t = tr.copy()
    t["rid"] = norm_route(t["RouteID"])
    m = s.merge(t, on="rid", how="inner")
    lo = np.maximum(m["BEG_MP"], m["BeginMP"])
    hi = np.minimum(m["END_MP"], m["EndMP"])
    m["overlap"] = hi - lo
    m = m[m["overlap"] > 0]
    # tie-break: prefer rows that actually carry a count
    m["has"] = m["AADT"].fillna(0).gt(0)
    m = m.sort_values(["seg_id", "has", "overlap"], ascending=[True, False, False])
    best = m.drop_duplicates("seg_id")
    return best[["seg_id", "AADT", "AADTT", "SU_PCT", "MU_PCT", "SOURCE"]]


def main():
    parts = []
    for lid, name in LAYERS.items():
        d = fetch_layer(lid)
        d["layer"] = name
        print(f"layer {lid} {name}: {len(d):,} rows")
        parts.append(d)
    tr = pd.concat(parts, ignore_index=True)
    tr.to_parquet(RAW / "ncdot_aadt_segments.parquet")

    segs = pd.read_parquet(RAW / "ncdot_joined.parquet",
                           columns=["seg_id", "ROUTEID", "BEG_MP", "END_MP", "asph_AADT"])
    routes_ok = norm_route(segs.ROUTEID).isin(set(norm_route(tr.RouteID)))
    print(f"\nsegments whose ROUTEID exists in traffic table: {routes_ok.mean():.1%}")

    best = attach(segs, tr)
    out = segs[["seg_id", "asph_AADT"]].merge(best, on="seg_id", how="left")
    ts = out["AADT"].where(out["AADT"] > 0)          # 0 means "no data" at NCDOT
    sv = out["asph_AADT"].where((out["asph_AADT"] > 0) & ~out["asph_AADT"].isin([550, 5500]))
    out["tr_aadt"] = ts.fillna(sv)
    out["tr_aadt_source"] = np.where(ts.notna(), "traffic_segments",
                                     np.where(sv.notna(), "pavement_survey", "none"))
    out["tr_aadtt"] = out["AADTT"]
    out["tr_su_pct"] = out["SU_PCT"]
    out["tr_mu_pct"] = out["MU_PCT"]
    out["tr_has_count"] = out["tr_aadt"].notna().astype("int8")
    res = out[["seg_id", "tr_aadt", "tr_aadtt", "tr_su_pct", "tr_mu_pct",
               "tr_aadt_source", "tr_has_count"]]
    res.to_parquet(RAW / "aadt_attached.parquet")

    n = len(res)
    print(f"\nbefore: {sv.notna().sum():,}/{n:,} have AADT ({sv.notna().mean():.1%}) from pavement survey")
    print(f"after:  {res.tr_has_count.sum():,}/{n:,} have AADT ({res.tr_has_count.mean():.1%})")
    print(res.tr_aadt_source.value_counts().to_string())
    both = ts.notna() & sv.notna()
    if both.any():
        print(f"\nwhere both exist ({both.sum():,} segments): "
              f"{(ts[both] == sv[both]).mean():.1%} identical, "
              f"median ratio traffic/survey = {(ts[both] / sv[both]).median():.2f}")
    print("\ntraffic-segment AADT, most common values:")
    print(ts.value_counts().head(5).to_string())
    print("saved", RAW / "aadt_attached.parquet")


if __name__ == "__main__":
    main()
