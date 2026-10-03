"""Crash counts and estimated traffic per segment."""
import numpy as np
import pandas as pd
import pytest

from src.pipeline import pull_crashes, pull_probe_aadt
from tests.crashes.conftest import R1, R2


def sections(rows):
    d = pd.DataFrame(rows, columns=["GISROUTE", "ST_MP_PT", "END_MP_PT", "CRASH_CNT", "KA_CNT", "COMBINED_S"])
    return d.assign(BC_CNT=0.0, PDO_CNT=d.CRASH_CNT - d.KA_CNT)


def test_C1_a_section_shares_its_crashes_by_length_and_nothing_is_counted_twice(segs):
    sec = sections([(R1, 0.0, 1.0, 10, 2, 50.0),      # all of a
                    (R1, 0.5, 1.5, 8, 0, 100.0),      # half a, half b
                    (R1, 1.5, 3.5, 20, 4, 0.0)])      # 25% b, 50% in the gap, 25% c
    out = pull_crashes.attach_sections(segs, sec).set_index("seg_id")
    assert out.cr_crash_n[["a", "b", "c"]].round(6).tolist() == [14.0, 9.0, 5.0] and np.isnan(out.cr_crash_n["z"])
    assert out.cr_ka_n[["a", "b", "c"]].round(6).tolist() == [2.0, 1.0, 1.0]
    assert out.cr_crash_n.sum() == pytest.approx(38 - 10)        # the 10 that fell in the gap are not handed out
    parts = (out.cr_ka_n + out.cr_bc_n + out.cr_pdo_n)[["a", "b", "c"]]
    assert parts.tolist() == pytest.approx([14.0, 9.0, 5.0])


def test_C2_cover_rate_and_score_use_the_covered_length(segs):
    sec = sections([(R1, 0.0, 0.5, 5, 0, 40.0), (R1, 3.0, 4.0, 10, 0, 80.0), (R1, 3.0, 4.0, 0, 0, 20.0)])
    out = pull_crashes.attach_sections(segs, sec).set_index("seg_id")
    assert out.cr_cover["a"] == 0.5 and out.cr_crash_per_mi_yr["a"] == pytest.approx(5 / 0.5 / 5)
    assert out.cr_ncdot_score["a"] == 40.0
    assert out.cr_cover["c"] == 1.0                      # two sections on the same stretch: capped
    assert out.cr_ncdot_score["c"] == 50.0


def test_C3_a_segment_without_a_section_is_unknown_not_zero(segs):
    out = pull_crashes.attach_sections(segs, sections([(R1, 0.0, 1.0, 3, 0, 10.0)]))
    assert out.seg_id.tolist() == segs.seg_id.tolist()
    z = out.set_index("seg_id").loc["z"]
    assert z.cr_cover == 0 and np.isnan(z.cr_crash_n) and np.isnan(z.cr_crash_per_mi_yr)


def test_C4_zero_length_sections_are_ignored(segs):
    out = pull_crashes.attach_sections(segs, sections([(R1, 0.5, 0.5, 7, 0, 10.0)]))
    assert out.cr_crash_n.isna().all() and np.isfinite(out.cr_cover).all()


def test_C5_crash_points_are_counted_by_severity_and_absent_means_zero(segs):
    pts = pd.DataFrame({"GIS_RteTxt": [str(R1), str(R1), str(R1), str(R2), "ROUTE NOT FOUND", str(R1)],
                        "GIS_Milepo": [0.2, 0.3, 1.7, 0.1, 0.2, 2.5],
                        "Crash_Seve": ["K", "A", "A", "K", "K", "K"]})
    out, seg_of = pull_crashes.attach_points(segs, pts)
    assert out.seg_id.tolist() == segs.seg_id.tolist()
    assert out.cr_fatal_10yr.tolist() == [1, 0, 0, 1] and out.cr_serious_10yr.tolist() == [1, 1, 0, 0]
    assert seg_of.notna().sum() == 4


def test_C6_attach_returns_one_row_per_segment_with_only_cr_columns(segs):
    pts = pd.DataFrame({"GIS_RteTxt": [str(R1)], "GIS_Milepo": [0.2], "Crash_Seve": ["K"]})
    out, _ = pull_crashes.attach(segs, sections([(R1, 0.0, 1.0, 3, 1, 10.0)]), pts)
    assert out.seg_id.tolist() == segs.seg_id.tolist()
    assert all(c.startswith("cr_") for c in out.columns if c != "seg_id")


def probe(rows):
    return pd.DataFrame(rows, columns=["RouteID", "BegMP", "EndMP", "Estimated", "Lower_95_P", "Upper_95_P"])


def counts(segs, values):
    return pd.DataFrame({"seg_id": segs.seg_id, "tr_aadt": values})


def test_T1_estimate_is_the_length_weighted_mean_and_zero_means_no_estimate(segs):
    p = probe([(R1, 0.0, 0.25, 1000, 500, 2000), (R1, 0.25, 1.0, 200, 100, 400), (R1, 1.0, 2.0, 0, 0, 100)])
    out = pull_probe_aadt.attach(segs, p, counts(segs, [np.nan] * 4)).set_index("seg_id")
    assert out.tr_aadt_est["a"] == pytest.approx(0.25 * 1000 + 0.75 * 200)
    assert out.tr_aadt_est_lo["a"] == pytest.approx(0.25 * 500 + 0.75 * 100)
    assert np.isnan(out.tr_aadt_est["b"]) and out.tr_aadt_est_cover["b"] == 0
    assert out.tr_aadt_est_cover["a"] == 1.0


def test_T2_a_real_count_wins_over_the_estimate(segs):
    p = probe([(R1, 0.0, 1.0, 300, 100, 500), (R1, 1.0, 2.0, 700, 500, 900)])
    out = pull_probe_aadt.attach(segs, p, counts(segs, [5000.0, np.nan, np.nan, 80.0]))
    assert out.seg_id.tolist() == segs.seg_id.tolist()
    assert out.tr_aadt_best.tolist()[:2] == [5000.0, 700.0] and np.isnan(out.tr_aadt_best[2])
    assert out.tr_aadt_best_source.tolist() == ["count", "estimate", "none", "count"]
    assert "tr_aadt" not in out.columns            # that column already lives in aadt_attached.parquet


def test_T3_two_pieces_on_one_stretch_average_and_cover_stays_at_one(segs):
    p = probe([(R1, 3.0, 4.0, 400, 0, 0), (R1, 3.0, 4.0, 600, 0, 0)])
    out = pull_probe_aadt.attach(segs, p, counts(segs, [np.nan] * 4)).set_index("seg_id")
    assert out.tr_aadt_est["c"] == 500 and out.tr_aadt_est_cover["c"] == 1.0


def test_T4_rescaling_puts_the_estimate_on_the_count_scale_and_keeps_the_order():
    rng = np.random.default_rng(0)
    est = pd.Series(np.sort(rng.uniform(10, 10_000, 400)))
    count = (est * 2).where(np.arange(400) % 2 == 0)             # half the rows have a count, twice the estimate
    out = pull_probe_aadt.rescale(est, count)
    assert out.notna().all() and out.is_monotonic_increasing
    inner = out[10:-10] / est[10:-10]
    assert inner.between(1.7, 2.3).all()


def test_T5_rescaling_is_per_group_and_falls_back_when_a_group_has_too_few_counts():
    est = pd.Series(np.tile(np.linspace(100, 1000, 100), 3))
    group = pd.Series(np.repeat(["x", "y", "tiny"], 100))
    count = pd.Series(np.where(group == "x", est * 2, est * 4))
    count[group == "tiny"] = np.nan
    count[250] = 123.0                                           # one count is not enough for its own curve
    out = pull_probe_aadt.rescale(est, count, group)
    assert (out[group == "x"] / est[group == "x"]).round(3).eq(2).all()
    assert (out[group == "y"] / est[group == "y"]).round(3).eq(4).all()
    assert (out[group == "tiny"] / est[group == "tiny"]).between(2, 4).all()


def test_T6_with_too_few_counts_the_estimate_is_left_alone():
    est, count = pd.Series([100.0, 200.0, np.nan]), pd.Series([900.0, np.nan, 5.0])
    assert pull_probe_aadt.rescale(est, count).equals(est)
