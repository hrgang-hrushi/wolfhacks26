"""The combined side table and the model comparison."""
import numpy as np
import pandas as pd
import pytest

from src.model import traffic_crash_ablation as tca
from src.model.common import add_folds, add_targets, check_features
from src.pipeline import traffic_crash
from tests.conftest import make_table


def test_B1_crash_rate_is_crashes_per_million_vehicle_miles_over_the_covered_length(segs):
    crash = pd.DataFrame({"seg_id": segs.seg_id, "cr_crash_n": [10.0, 4.0, np.nan, 0.0],
                          "cr_cover": [1.0, 0.5, 0.0, 1.0]})
    traffic = pd.DataFrame({"seg_id": segs.seg_id, "tr_aadt_best": [1000.0, 2000.0, 500.0, np.nan]})
    d = traffic_crash.combine(segs, crash, traffic).set_index("seg_id")
    assert d.cr_crash_per_mvm["a"] == pytest.approx(10 / (1000 * 365 * 5 * 1.0 / 1e6))
    assert d.cr_crash_per_mvm["b"] == pytest.approx(4 / (2000 * 365 * 5 * 0.5 / 1e6))
    assert np.isnan(d.cr_crash_per_mvm["c"]) and np.isnan(d.cr_crash_per_mvm["z"])   # no score; no traffic
    assert "seg_mi" not in d.columns and d.index.tolist() == segs.seg_id.tolist()


def test_B1b_main_writes_the_side_table_and_a_map_copy_with_the_same_rows(segs, tmp_path, monkeypatch):
    raw, out, handoff = tmp_path / "raw", tmp_path / "processed", tmp_path / "handoff"
    raw.mkdir(), out.mkdir()
    pd.DataFrame({"seg_id": segs.seg_id, "cr_crash_n": [10.0, 4.0, np.nan, 0.0],
                  "cr_cover": [1.0, 0.5, 0.0, 1.0]}).to_parquet(raw / "crash_attached.parquet")
    pd.DataFrame({"seg_id": segs.seg_id, "tr_aadt_best": [1000.0, 2000.0, 500.0, np.nan],
                  "tr_aadt_best_source": ["count", "estimate", "estimate", "none"]}
                 ).to_parquet(raw / "aadt_probe_attached.parquet")
    monkeypatch.setattr(traffic_crash, "load_segments", lambda raw: segs)
    traffic_crash.main(raw, out, handoff)
    full, small = pd.read_parquet(out / "traffic_crash.parquet"), pd.read_parquet(handoff / "traffic_crash.parquet")
    assert small.seg_id.tolist() == full.seg_id.tolist() == segs.seg_id.tolist()
    assert list(small.columns) == list(full.columns)
    assert np.allclose(small.cr_crash_per_mvm, full.cr_crash_per_mvm, atol=1e-3, equal_nan=True)
    assert not list(handoff.glob("*.tmp"))


def test_B2_the_new_columns_are_allowed_model_inputs():
    check_features(tca.TE + tca.CR + tca.BOTH)


def test_B3_block_range_sees_a_real_improvement_and_not_a_fake_one():
    rng = np.random.default_rng(0)
    n = 4000
    blocks = pd.Series(rng.integers(0, 80, n).astype(str))
    y = pd.Series(rng.normal(0, 1, n))
    mask = pd.Series(True, index=y.index)
    ref = y + rng.normal(0, 1.0, n)
    lo, hi = tca.block_range(blocks, y, ref, y + rng.normal(0, 0.5, n), mask, "l1", n=100)
    assert hi < 0                                                   # lower error, clear of zero
    lo, hi = tca.block_range(blocks, y, ref, y + rng.normal(0, 1.0, n), mask, "l1", n=100)
    assert lo < 0 < hi                                              # same quality: range crosses zero
    yb = pd.Series((rng.random(n) < 0.2).astype(float))
    lo, hi = tca.block_range(blocks, yb, pd.Series(rng.random(n)), yb + rng.normal(0, 0.3, n), mask, "bin", n=100)
    assert lo > 0


def test_B4_block_range_is_repeatable_and_ignores_rows_without_a_prediction():
    rng = np.random.default_rng(1)
    n = 500
    blocks, y = pd.Series(rng.integers(0, 20, n).astype(str)), pd.Series(rng.normal(0, 1, n))
    ref, new = y + rng.normal(0, 1, n), y + rng.normal(0, 1, n)
    mask = pd.Series(True, index=y.index)
    first = tca.block_range(blocks, y, ref, new, mask, "l1", n=50)
    assert first == tca.block_range(blocks, y, ref, new, mask, "l1", n=50)
    holes = new.copy()
    holes[:10] = np.nan
    assert np.isfinite(tca.block_range(blocks, y, ref, holes, mask, "l1", n=50)).all()


def test_B5_the_comparison_runs_end_to_end_and_the_first_row_is_the_reference(tmp_path, small_models):
    d = add_folds(add_targets(make_table()))
    rng = np.random.default_rng(2)
    d["tn_elev"] = rng.uniform(0, 900, len(d))
    d.to_parquet(tmp_path / "segments_targets.parquet")
    side = pd.DataFrame({"seg_id": d.seg_id})
    for c in tca.TE + tca.CR + tca.BOTH:
        side[c] = rng.uniform(0, 10, len(d))
    side["tr_aadt_best_source"] = rng.choice(["count", "estimate", "none"], len(d))
    side.to_parquet(tmp_path / "traffic_crash.parquet")
    tca.main(tmp_path)
    res = pd.read_csv(tmp_path / "results" / "traffic_crash_ablation.csv")
    assert res.model.tolist() == ["map model today", "+ estimated traffic", "+ crashes", "+ both"]
    assert (res.loc[0, ["rate_mae_change", "rate_mae_lo", "rate_mae_hi"]] == 0).all()
    assert res.n_inputs.is_monotonic_increasing and res.rate_mae.notna().all()
    assert (res.rate_mae_lo[1:] <= res.rate_mae_hi[1:]).all()
    md = (tmp_path / "results" / "traffic_crash_ablation.md").read_text()
    assert md.count("\n") == 6 and "range" in md
