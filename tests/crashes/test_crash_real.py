"""Pins on the real crash and traffic pulls. Skipped on machines without the files."""
from pathlib import Path

import pandas as pd
import pytest

RAW, OUT = Path("data/raw"), Path("data/processed")
pytestmark = pytest.mark.realdata


def read(path):
    if not path.exists():
        pytest.skip(f"{path} is not on this machine")
    return pd.read_parquet(path)


def test_R1_crash_file_has_every_segment_once_and_no_crash_is_counted_twice():
    out, sec = read(RAW / "crash_attached.parquet"), read(RAW / "ncdot_section_scores.parquet")
    seg = read(RAW / "ncdot_joined.parquet")[["seg_id"]]
    assert len(out) == 112_443 and out.seg_id.tolist() == seg.seg_id.tolist()
    assert len(sec) == 181_023
    assert out.cr_crash_n.sum() <= sec.CRASH_CNT.sum()
    assert out.cr_crash_n.sum() / sec.CRASH_CNT.sum() > 0.95
    assert (out.cr_cover > 0).mean() > 0.94
    assert out.cr_cover.between(0, 1).all() and (out.cr_crash_n.dropna() >= 0).all()


def test_R2_crash_points_land_on_segments():
    out, pts = read(RAW / "crash_attached.parquet"), read(RAW / "ncdot_ka_crashes.parquet")
    assert len(pts) == 53_917 and set(pts.Crash_Seve) == {"K", "A"}
    landed = out.cr_fatal_10yr.sum() + out.cr_serious_10yr.sum()
    assert 0.80 < landed / len(pts) <= 1


def test_R3_estimate_fills_the_traffic_gap_and_agrees_with_counts_in_rank():
    t, c = read(RAW / "aadt_probe_attached.parquet"), read(RAW / "aadt_attached.parquet")
    assert len(t) == 112_443 and t.seg_id.is_unique
    assert c.tr_aadt.notna().mean() < 0.5 < 0.85 < t.tr_aadt_best.notna().mean()
    both = t.merge(c[["seg_id", "tr_aadt"]], on="seg_id").dropna(subset=["tr_aadt", "tr_aadt_est"])
    assert both.tr_aadt_est.corr(both.tr_aadt, method="spearman") > 0.9
    assert (t.tr_aadt_best[t.tr_aadt_best_source == "count"] ==
            both.set_index("seg_id").tr_aadt.reindex(t.seg_id[t.tr_aadt_best_source == "count"]).values).sum() > 50_000
    assert 0.9 < (both.tr_aadt_est_scaled / both.tr_aadt).median() < 1.1


def test_R4_side_table_joins_one_to_one_onto_the_feature_table():
    side, seg = read(OUT / "traffic_crash.parquet"), read(OUT / "segments.parquet")
    assert set(side.seg_id) == set(seg.seg_id) and side.seg_id.is_unique
    assert not (set(side.columns) & set(seg.columns)) - {"seg_id"}
    assert all(c.startswith(("cr_", "tr_")) for c in side.columns if c != "seg_id")
