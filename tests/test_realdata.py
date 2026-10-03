"""Pins on the real feature table. Skipped on machines without data/processed/segments.parquet."""
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.model.common import PV, TR, add_folds, add_targets

SEG = Path("data/processed/segments.parquet")
RAW_FOR_TARGETS = ["pv_RTG_NBR", "pv_PCS_SRVY_YR", "pv_YEAR_LAST_REHAB", "pv_asph_ALGTR_MDRT_PCT",
                   "pv_asph_ALGTR_HGH_PCT"]
pytestmark = pytest.mark.realdata


@pytest.fixture(scope="module")
def d():
    if not SEG.exists():
        pytest.skip(f"{SEG} is not on this machine")
    cols = ["seg_id", "mid_x", "mid_y", "in_helene_zone", "y_helene_failed"] + RAW_FOR_TARGETS
    return add_folds(add_targets(pd.read_parquet(SEG, columns=cols)))


def test_R1_label_counts(d):
    assert len(d) == 112_443 and d.seg_id.is_unique
    assert d.y_rate.notna().sum() == 77_422
    assert d.y_crack.notna().sum() == 68_349
    assert d.y_crack.sum() == 10_766


def test_R2_blocks_and_fold_balance(d):
    assert d.split_block.nunique() == 5_040
    share = d.fold[d.y_rate.notna()].value_counts(normalize=True)
    assert sorted(share.index) == [0, 1, 2, 3, 4]
    assert share.between(0.15, 0.25).all(), share.to_dict()


def test_R3_every_fold_has_helene_positives_in_the_zone(d):
    zone = d.in_helene_zone == 1
    assert (d.y_helene_failed[zone].groupby(d.fold[zone]).sum() > 0).all()
    assert d.y_crack.groupby(d.fold).sum().min() > 0


def test_R4_baseline_features_and_raw_target_inputs_exist(d):
    if not SEG.exists():
        pytest.skip(f"{SEG} is not on this machine")
    raw = set(pq.read_schema(SEG).names)
    assert set(RAW_FOR_TARGETS) <= raw
    after_targets = raw | {"pv_age_at_survey"}
    assert [c for c in PV + TR if c not in after_targets] == []
    assert "pv_age_at_survey" in d.columns
