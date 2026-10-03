import pandas as pd
import pytest

from src.model.common import (BANNED_EXACT, PV, TR, add_targets, attach_terrain, check_features, merge_one_to_one,
                              prep, terrain_columns)


def test_X1_age_clue_is_age_at_survey():
    assert "pv_age_at_survey" in PV
    assert "pv_PVMNT_AGE" not in PV


def test_X2_baseline_lists_hold_no_banned_column():
    check_features(PV + TR)


@pytest.mark.parametrize("col", sorted(BANNED_EXACT) + ["y_rate", "y_helene_failed", "pred_rate", "n_ncgs_hwm",
                                                         "im_vit_rate"])
def test_X3_each_banned_name_and_prefix_raises(col):
    with pytest.raises(ValueError, match="banned"):
        check_features(["pv_SURFACE", col])


def test_X4_prep_rejects_banned_columns_and_casts_strings(table):
    d = add_targets(table)
    with pytest.raises(ValueError, match="pv_RTG_NBR"):
        prep(d, ["pv_SURFACE", "pv_RTG_NBR"])
    X = prep(d, ["pv_SURFACE", "pv_NUMBER_OF_LANES", "pv_asph_RSRF_THCKNS_NBR"])
    assert str(X.pv_SURFACE.dtype) == "category"
    assert str(X.pv_asph_RSRF_THCKNS_NBR.dtype) == "category"
    assert pd.api.types.is_numeric_dtype(X.pv_NUMBER_OF_LANES)


def test_X5_terrain_merge_keeps_both_copies_of_a_clashing_column(table, tmp_path):
    d = table.assign(tn_elev=1.0, tn_flowacc=2.0)
    pd.DataFrame({"seg_id": d.seg_id, "tn_elev": 9.0, "tn_hand_proxy": 3.0}).to_parquet(tmp_path / "terrain.parquet")
    out = attach_terrain(d, tmp_path)
    assert terrain_columns(out) == ["tn_elev", "tn_elev_d8", "tn_flowacc", "tn_hand_proxy"]
    assert (out.tn_elev == 9.0).all() and (out.tn_elev_d8 == 1.0).all()
    assert out.seg_id.tolist() == d.seg_id.tolist()
    assert attach_terrain(d, tmp_path / "nowhere") is d   # no terrain file: table unchanged


def test_X6_merge_rejects_null_or_duplicate_ids_and_keeps_order(table):
    other = pd.DataFrame({"seg_id": table.seg_id[::-1].values, "v": range(len(table))})
    out = merge_one_to_one(table, other, "other")
    assert out.seg_id.tolist() == table.seg_id.tolist() and out.index.equals(table.index)
    assert out.v.tolist() == list(range(len(table)))[::-1]
    dup = pd.concat([other, other.head(1)])
    with pytest.raises(ValueError, match="other"):
        merge_one_to_one(table, dup, "other")
    with pytest.raises(ValueError, match="table"):
        merge_one_to_one(pd.concat([table, table.head(1)]), other, "other")
    with pytest.raises(ValueError, match="other"):
        merge_one_to_one(table, other.assign(seg_id=other.seg_id.where(other.v > 0)), "other")
