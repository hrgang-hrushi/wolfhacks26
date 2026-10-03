"""Route + milepost helpers shared by the crash and estimated-traffic pulls.

NCDOT's layers sit on one linear referencing system: an 11-digit route id (8-digit route plus a
3-digit county code) and a milepost along it. A crash section, a crash point or a traffic piece is
matched to a road segment by route and milepost, with no spatial snapping.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

AGOL = "https://services.arcgis.com/NuWFvHYDMVmmxMeM/ArcGIS/rest/services"
UA = {"User-Agent": "unwatched-roads-hackathon/0.1 (NC State student project)"}
RAW = Path("data/raw")


class LayerError(RuntimeError):
    pass


def _get(session, url, params, tries=4):
    """GET a JSON reply. A reply that is "200 OK" but carries an error object is an error too."""
    for i in range(tries):
        try:
            r = session.get(url, params=params, headers=UA, timeout=120)
            r.raise_for_status()
            j = r.json()
            if not isinstance(j, dict) or "error" in j:
                raise LayerError(f"{url}: {str(j)[:200]}")
            return j
        except (requests.RequestException, ValueError, LayerError):
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def fetch_table(layer_url, fields, *, oid="FID", window=2000, workers=4, session=None):
    """Every row's attributes, pulled in object-id windows. Raises unless rows == the server's count."""
    s = session or requests.Session()
    q = f"{layer_url}/query"
    n = int(_get(s, q, {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"])
    stats = ('[{"statisticType":"min","onStatisticField":"%s","outStatisticFieldName":"lo"},'
             '{"statisticType":"max","onStatisticField":"%s","outStatisticFieldName":"hi"}]' % (oid, oid))
    a = _get(s, q, {"where": "1=1", "outStatistics": stats, "f": "json"})["features"][0]["attributes"]
    edges = list(range(int(a["lo"]) - 1, int(a["hi"]), window)) + [int(a["hi"])]

    def one(lo_hi):
        lo, hi = lo_hi
        j = _get(s, q, {"where": f"{oid}>{lo} AND {oid}<={hi}", "outFields": ",".join(fields),
                        "returnGeometry": "false", "f": "json"})
        if j.get("exceededTransferLimit"):
            raise LayerError(f"{layer_url}: window {lo}-{hi} holds more rows than one reply carries")
        return [f["attributes"] for f in j.get("features", [])]

    with ThreadPoolExecutor(workers) as ex:
        rows = [r for part in ex.map(one, zip(edges[:-1], edges[1:])) for r in part]
    if len(rows) != n:
        raise LayerError(f"{layer_url}: received {len(rows):,} rows but the server counts {n:,}")
    return pd.DataFrame(rows, columns=fields)


def write_atomic(df, path):
    """Write to a temporary name, then swap it in (the Desktop folder is synced; in-place writes fail)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp)
    os.replace(tmp, path)


def route_key(s):
    """Route id as a nullable integer. Layers store it as text, float or int; junk becomes <NA>."""
    return pd.to_numeric(s, errors="coerce").round().astype("Int64")


def load_segments(raw=RAW):
    """seg_id, rid, BEG_MP, END_MP and length in miles for every road segment."""
    d = pd.read_parquet(raw / "ncdot_joined.parquet", columns=["seg_id", "ROUTEID", "BEG_MP", "END_MP"])
    d["rid"] = route_key(d.ROUTEID)
    d["seg_mi"] = d.END_MP - d.BEG_MP
    return d[["seg_id", "rid", "BEG_MP", "END_MP", "seg_mi"]]


def overlaps(segs, parts, beg, end):
    """One row per (segment, part) pair on the same route whose milepost ranges overlap.

    Returns the parts' columns plus seg_id, seg_mi and `ov`, the shared length in miles."""
    m = segs.dropna(subset=["rid"]).merge(parts.dropna(subset=["rid"]), on="rid", how="inner")
    m["ov"] = np.minimum(m.END_MP, m[end]) - np.maximum(m.BEG_MP, m[beg])
    return m[m.ov > 0].drop(columns=["rid", "BEG_MP", "END_MP"])


def points_on_segments(segs, pts, mp):
    """seg_id for each point: same route, BEG_MP <= milepost <= END_MP. Index-aligned to `pts`;
    <NA> where no segment holds the point. A point on a shared end belongs to the earlier segment."""
    p = pts[["rid", mp]].dropna().reset_index(names="_pt")
    m = p.merge(segs.dropna(subset=["rid"]), on="rid", how="inner")
    m = m[(m[mp] >= m.BEG_MP) & (m[mp] <= m.END_MP)].sort_values(["_pt", "BEG_MP"]).drop_duplicates("_pt")
    return m.set_index("_pt").seg_id.reindex(pts.index).astype("string")


def weighted_mean(m, value, weight="ov"):
    """Per-segment mean of `value` weighted by overlap, over the rows where the value is present."""
    ok = m[m[value].notna()]
    num = (ok[value] * ok[weight]).groupby(ok.seg_id).sum()
    return num / ok.groupby("seg_id")[weight].sum()
