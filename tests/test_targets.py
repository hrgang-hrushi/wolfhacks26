import numpy as np
import pandas as pd
import pytest

from src.model.common import RATE_FLOOR, YEARS_CAP, add_targets, years_to_poor


def rows(**cols):
    n = len(next(iter(cols.values())))
    base = dict(pv_RTG_NBR=[85.0] * n, pv_PCS_SRVY_YR=[2025] * n, pv_YEAR_LAST_REHAB=[2017.0] * n,
                pv_asph_ALGTR_MDRT_PCT=[0.0] * n, pv_asph_ALGTR_HGH_PCT=[0.0] * n)
    return pd.DataFrame({**base, **cols})


def test_T1_age_is_counted_to_the_survey_year_not_2025():
    d = add_targets(rows(pv_PCS_SRVY_YR=[2023], pv_YEAR_LAST_REHAB=[2015.0], pv_RTG_NBR=[84.0]))
    assert d.pv_age_at_survey[0] == 8
    assert d.y_rate[0] == (100 - 84) / 8


def test_T2_label_needs_age_between_2_and_40():
    d = add_targets(rows(pv_PCS_SRVY_YR=[2025] * 4, pv_YEAR_LAST_REHAB=[2024.0, 2023.0, 1985.0, 1984.0]))
    assert d.y_rate.notna().tolist() == [False, True, True, False]
    assert d.y_years_to_poor.notna().tolist() == [False, True, True, False]


def test_T3_resurfaced_after_survey_or_no_rehab_year_gives_no_label():
    d = add_targets(rows(pv_PCS_SRVY_YR=[2023, 2025], pv_YEAR_LAST_REHAB=[2024.0, np.nan]))
    assert d.y_rate.isna().all()
    assert d.pv_age_at_survey.isna().all()
    assert len(d) == 2


def test_T4_rating_zero_gives_no_label():
    d = add_targets(rows(pv_RTG_NBR=[0.0, 50.0]))
    assert d.y_rate.notna().tolist() == [False, True]


def test_T5_rate_arithmetic():
    d = add_targets(rows(pv_RTG_NBR=[85.0, 100.0]))
    assert d.y_rate.tolist() == [1.875, 0.0]


def test_T6_years_to_poor_floor_cap_and_already_poor():
    d = add_targets(rows(pv_RTG_NBR=[85.0, 59.0, 100.0, 60.5]))
    assert round(d.y_years_to_poor[0], 3) == 13.333   # (85 - 60) / 1.875
    assert d.y_years_to_poor[1] == 0                  # already below 60
    assert d.y_years_to_poor[2] == 50                 # rate 0: capped at 50
    assert d.y_years_to_poor[3] == 0.5 / (39.5 / 8)


def test_T6b_rate_floor_and_cap_in_years_to_poor():
    assert (RATE_FLOOR, YEARS_CAP) == (0.1, 50)
    got = years_to_poor(pd.Series([62.0, 62.0, 100.0, 59.9, np.nan]), pd.Series([0.01, 0.5, 0.2, 5.0, 1.0]))
    assert got[0] == pytest.approx(20)     # 2 points at the 0.1 floor, not 200 years at 0.01
    assert got[1] == pytest.approx(4)      # above the floor the rate is used as is
    assert got[2] == 50                    # 40 / 0.2 = 200, capped
    assert got[3] == 0                     # already below 60
    assert np.isnan(got[4])                # no rating, no forecast


def test_T7_cracking_is_strictly_above_10_percent():
    d = add_targets(rows(pv_asph_ALGTR_MDRT_PCT=[10.0, 11.0, 4.0, 0.0], pv_asph_ALGTR_HGH_PCT=[0.0, 0.0, 7.0, 0.0]))
    assert d.y_crack.tolist() == [0.0, 1.0, 1.0, 0.0]


def test_T8_cracking_is_blank_without_asphalt_data():
    d = add_targets(rows(pv_asph_ALGTR_MDRT_PCT=[np.nan, 20.0], pv_asph_ALGTR_HGH_PCT=[np.nan, np.nan]))
    assert d.y_crack.isna().all()


def test_T9_rows_are_never_dropped_or_reordered(table):
    d = add_targets(table)
    assert d.seg_id.tolist() == table.seg_id.tolist()
    assert d.index.equals(table.index)
    assert "pv_age_at_survey" not in table.columns   # input is not mutated
