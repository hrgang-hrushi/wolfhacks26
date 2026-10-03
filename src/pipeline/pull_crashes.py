"""Attach NCDOT crash history to every state road segment.

Usage:  python -m src.pipeline.pull_crashes            (pull, then attach)
        python -m src.pipeline.pull_crashes --attach-only
Reads:  data/raw/ncdot_joined.parquet
Writes: data/raw/ncdot_section_scores.parquet   NCDOT section safety scores, 2021-2025 (no geometry)
        data/raw/ncdot_ka_crashes.parquet       fatal and serious-injury crash points, 2016-2025
        data/raw/crash_attached.parquet         one row per seg_id, cr_ columns

Two sources, both matched by route + milepost:
  Section scores: every state road cut into pieces of about half a mile, each with its crash counts
  for 2021-2025. A piece's crashes are shared out to our segments by the length they have in common.
  Crash points: each fatal (K) or serious-injury (A) crash, 2016-2025, with a route and milepost.

Columns written (prefix cr_):
  cr_cover            share of the segment's length that has a section score (0 to 1)
  cr_crash_n          crashes 2021-2025, all severities (fractional: shared out by length)
  cr_ka_n, cr_bc_n, cr_pdo_n   the same split: fatal + serious / other injury / property damage only
  cr_crash_per_mi_yr  crashes per mile per year over the covered length
  cr_ncdot_score      NCDOT's own combined safety score for the section (0 to 100, higher is worse)
  cr_fatal_10yr, cr_serious_10yr   crash points on the segment, 2016-2025 (whole numbers)
"""
import sys

import numpy as np
import pandas as pd

from src.pipeline.milepost import (AGOL, RAW, fetch_table, load_segments, overlaps, points_on_segments,
                                   route_key, weighted_mean, write_atomic)

SECTIONS = f"{AGOL}/NC_2021Thru2025SectionScores/FeatureServer/0"
SECTION_FIELDS = ["GISROUTE", "ST_MP_PT", "END_MP_PT", "CRASH_CNT", "KA_CNT", "BC_CNT", "PDO_CNT",
                  "CDR", "SI", "CRR", "COMBINED_S"]
SECTION_YEARS = 5
POINTS = f"{AGOL}/NC_FatalAndSeriousInjuryCrashes/FeatureServer/0"
POINT_FIELDS = ["Crash_ID", "GIS_RteTxt", "GIS_Milepo", "Longitude", "Latitude", "LOC_ERROR", "Date",
                "Crash_Seve", "Crash_Type", "Road_Condi", "Weather"]
COUNTS = {"CRASH_CNT": "cr_crash_n", "KA_CNT": "cr_ka_n", "BC_CNT": "cr_bc_n", "PDO_CNT": "cr_pdo_n"}


def attach_sections(segs, sec):
    """Share each section's crash counts out to the segments it overlaps, by length."""
    sec = sec.assign(rid=route_key(sec.GISROUTE), sec_mi=sec.END_MP_PT - sec.ST_MP_PT)
    m = overlaps(segs, sec[sec.sec_mi > 0], "ST_MP_PT", "END_MP_PT")
    share = m.ov / m.sec_mi
    out = pd.DataFrame({new: (m[old] * share).groupby(m.seg_id).sum() for old, new in COUNTS.items()})
    covered = m.groupby("seg_id").ov.sum()
    seg_mi = segs.set_index("seg_id").seg_mi
    out["cr_cover"] = (covered / seg_mi.reindex(covered.index)).clip(upper=1)
    out["cr_crash_per_mi_yr"] = out.cr_crash_n / covered / SECTION_YEARS
    out["cr_ncdot_score"] = weighted_mean(m, "COMBINED_S")
    out = out.reindex(segs.seg_id)
    out["cr_cover"] = out.cr_cover.fillna(0)
    return out.reset_index()


def attach_points(segs, pts):
    """Count the fatal and the serious-injury crash points that fall on each segment."""
    pts = pts.assign(rid=route_key(pts.GIS_RteTxt))
    seg_of = points_on_segments(segs, pts, "GIS_Milepo")
    n = pd.crosstab(seg_of, pts.Crash_Seve).reindex(columns=["K", "A"], fill_value=0)
    out = n.reindex(segs.seg_id, fill_value=0).rename(columns={"K": "cr_fatal_10yr", "A": "cr_serious_10yr"})
    out.columns.name = None
    return out.astype("int32").reset_index(), seg_of


def attach(segs, sec, pts):
    a = attach_sections(segs, sec)
    b, seg_of = attach_points(segs, pts)
    return a.merge(b, on="seg_id", validate="one_to_one"), seg_of


def report(segs, sec, pts, out, seg_of):
    n = len(out)
    print(f"\nsection scores: {len(sec):,} sections, {sec.CRASH_CNT.sum():,.0f} crashes 2021-2025")
    print(f"segments with a section score: {(out.cr_cover > 0).sum():,}/{n:,} ({(out.cr_cover > 0).mean():.1%}); "
          f"fully covered (>= 95% of length): {(out.cr_cover >= 0.95).mean():.1%}")
    print(f"crashes landed on our segments: {out.cr_crash_n.sum():,.0f} "
          f"({out.cr_crash_n.sum() / sec.CRASH_CNT.sum():.1%} of the state total)")
    print(f"segments sharing length with a section that had a crash: {(out.cr_crash_n > 0).mean():.1%}; "
          f"mean crashes per mile per year where covered: {out.cr_crash_per_mi_yr.mean():.2f}")
    ok = ~pts.LOC_ERROR.str.contains("NOT FOUND", na=False)   # blank and "NO ERROR" are both fine
    on_route = route_key(pts.GIS_RteTxt).isin(set(segs.rid.dropna()))
    print(f"\ncrash points: {len(pts):,} ({pts.Crash_Seve.eq('K').sum():,} fatal, {pts.Crash_Seve.eq('A').sum():,} "
          f"serious); located without error: {ok.mean():.1%}")
    print(f"on a route we have: {on_route.mean():.1%}; inside one of our segments: {seg_of.notna().mean():.1%}")
    print(f"segments with a fatal or serious crash in 10 years: "
          f"{((out.cr_fatal_10yr + out.cr_serious_10yr) > 0).mean():.1%}")


def main(attach_only=False):
    if not attach_only:
        write_atomic(fetch_table(SECTIONS, SECTION_FIELDS), RAW / "ncdot_section_scores.parquet")
        write_atomic(fetch_table(POINTS, POINT_FIELDS), RAW / "ncdot_ka_crashes.parquet")
    sec = pd.read_parquet(RAW / "ncdot_section_scores.parquet")
    pts = pd.read_parquet(RAW / "ncdot_ka_crashes.parquet")
    segs = load_segments()
    out, seg_of = attach(segs, sec, pts)
    assert len(out) == len(segs) and out.seg_id.is_unique
    write_atomic(out, RAW / "crash_attached.parquet")
    report(segs, sec, pts, out, seg_of)
    print("saved", RAW / "crash_attached.parquet", out.shape)


if __name__ == "__main__":
    main(attach_only="--attach-only" in sys.argv)
