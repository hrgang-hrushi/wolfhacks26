"""The map predictions: out-of-fold wherever the model was trained on that segment."""
import numpy as np
import pandas as pd
import pytest

from src.model.common import PV, TR, heldout_then_model, oof, prep, terrain_columns

pytestmark = pytest.mark.usefixtures("small_models")


def test_P1_P2_P3_map_predictions_are_out_of_fold_where_a_label_exists(scripts_run):
    d = pd.read_parquet(scripts_run["p"] / "segments_targets.parquet")
    out = pd.read_parquet(scripts_run["p"] / "predictions.parquet")
    assert out.seg_id.tolist() == d.seg_id.tolist()
    X = prep(d, [c for c in PV + TR if c in d.columns] + terrain_columns(d))
    zone = (d.in_helene_zone == 1) & d.y_helene_failed.notna()
    for t, y, kind, mask in (("rate", d.y_rate, "l1", d.y_rate.notna()), ("crack", d.y_crack, "bin", d.y_crack.notna()),
                             ("flood", d.y_helene_failed, "bin", zone)):
        expect = oof(d, X, y, kind, mask)
        held = out[f"{t}_heldout"]
        assert held.equals(expect.notna()) and held.equals(mask)             # P3
        assert np.allclose(out[f"pred_{t}"][mask], expect[mask])              # P1: the out-of-fold value
        assert out[f"pred_{t}"][~mask].notna().all()                          # P2: unlabelled rows still predicted
    assert out.columns.tolist() == ["seg_id", "mid_x", "mid_y", "pred_rate", "pred_years_to_poor", "pred_crack",
                                    "pred_flood", "in_helene_zone", "rate_heldout", "crack_heldout", "flood_heldout"]


def test_P4_a_labelled_row_in_a_skipped_fold_is_not_marked_held_out():
    oof_pred = pd.Series([0.2, np.nan, 0.4])
    pred, held = heldout_then_model(oof_pred, np.array([9.0, 8.0, 7.0]))
    assert pred.tolist() == [0.2, 8.0, 0.4]
    assert held.tolist() == [True, False, True]
