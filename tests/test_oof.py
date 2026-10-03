import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_absolute_error

from src.model import common
from src.model.common import (PV, TR, add_folds, add_targets, check_not_too_good, naive_mae, oof, prep, score)


pytestmark = pytest.mark.usefixtures("small_models")


@pytest.fixture
def d(table):
    return add_folds(add_targets(table))


def test_O1_only_masked_rows_are_trained_on_or_predicted(d, monkeypatch):
    seen = []
    real_fit = common._fit
    monkeypatch.setattr(common, "_fit", lambda X, y, kind, seed: (seen.append(set(X.index)), real_fit(X, y, kind, seed))[1])
    mask = d.y_rate.notna()
    pred = oof(d, prep(d, PV + TR), d.y_rate, "l1", mask)
    labelled = set(d.index[mask])
    assert len(seen) == 5 and all(s <= labelled for s in seen)
    assert pred.notna().equals(mask)


def test_O2_no_row_is_predicted_by_a_model_trained_on_its_fold(d, monkeypatch):
    log = []
    real_fit, real_predict = common._fit, common._predict
    monkeypatch.setattr(common, "_fit", lambda X, y, kind, seed: (log.append(("fit", set(d.fold[X.index]))),
                                                                  real_fit(X, y, kind, seed))[1])
    monkeypatch.setattr(common, "_predict", lambda m, X, kind: (log.append(("predict", set(d.fold[X.index]), list(X.index))),
                                                               real_predict(m, X, kind))[1])
    mask = d.y_rate.notna()
    oof(d, prep(d, PV + TR), d.y_rate, "l1", mask)
    predicted = []
    for (_, train_folds), (_, test_folds, idx) in zip(log[0::2], log[1::2]):
        assert len(test_folds) == 1 and not (test_folds & train_folds)
        predicted += idx
    assert sorted(predicted) == sorted(d.index[mask])   # each labelled row exactly once


def test_O3_same_seed_gives_identical_predictions(d):
    X, mask = prep(d, PV + TR), d.y_rate.notna()
    a, b = oof(d, X, d.y_rate, "l1", mask), oof(d, X, d.y_rate, "l1", mask)
    assert a.equals(b)


def test_O4_an_empty_fold_is_skipped(d):
    mask = d.y_rate.notna() & (d.fold != 2)
    pred = oof(d, prep(d, PV + TR), d.y_rate, "l1", mask)
    assert pred.notna().equals(mask)


def test_O5_rating_plus_age_reproduces_the_target_and_prep_refuses_them(d):
    m = d.y_rate.notna()
    tr, te = m & (d.fold != 0), m & (d.fold == 0)
    cheat = ["pv_RTG_NBR", "pv_age_at_survey"]
    model = lgb.LGBMRegressor(objective="l1", n_estimators=300, verbose=-1, random_state=0).fit(d.loc[tr, cheat], d.y_rate[tr])
    cheat_mae = mean_absolute_error(d.y_rate[te], model.predict(d.loc[te, cheat]))
    honest = oof(d, prep(d, PV + TR), d.y_rate, "l1", m)
    honest_mae = mean_absolute_error(d.y_rate[te], honest[te])
    assert cheat_mae < honest_mae / 2          # the leak is real ...
    with pytest.raises(ValueError, match="pv_RTG_NBR"):
        prep(d, cheat)                         # ... and the production path cannot take it


def test_O6_naive_mae_uses_the_other_folds_median_only():
    t = pd.DataFrame({"fold": [0, 0, 1, 1, 2, 3, 4]})
    y = pd.Series([10.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    mask = pd.Series(True, index=t.index)
    # fold 0 is predicted with the median of the rest (0): error 10 each. The other folds are
    # predicted with a median that includes the two 10s, which is still 0: error 0.
    assert naive_mae(t, y, mask) == pytest.approx(20 / 7)


def test_O7_tripwire():
    with pytest.raises(RuntimeError, match="leaking"):
        check_not_too_good(0.96)
    check_not_too_good(0.95)
    check_not_too_good(float("nan"))


def test_O8_labels_confined_to_one_fold_give_blank_scores_not_an_error(d):
    mask = d.y_rate.notna() & (d.fold == 1)
    pred = oof(d, prep(d, PV + TR), d.y_rate, "l1", mask)
    assert pred.isna().all()
    s = score(d.y_rate, pred, mask, "l1")
    assert s["n_scored"] == 0 and np.isnan(s["mae"]) and np.isnan(s["spearman"])
    assert np.isnan(naive_mae(d, d.y_rate, mask))
    empty = pd.Series(False, index=d.index)
    assert np.isnan(score(d.y_crack, oof(d, prep(d, PV + TR), d.y_crack, "bin", empty), empty, "bin")["aucpr"])


def test_O9_a_fold_whose_training_labels_have_one_class_is_skipped(d, capsys):
    y = pd.Series(0.0, index=d.index)
    y[d.fold == 3] = np.tile([0.0, 1.0], len(d))[: (d.fold == 3).sum()]   # positives only in fold 3
    mask = pd.Series(True, index=d.index)
    pred = oof(d, prep(d, PV + TR), y, "bin", mask)
    assert pred[d.fold == 3].isna().all()       # its training rows are all negative
    assert pred[d.fold != 3].notna().all()
    assert "fold 3 skipped: one class" in capsys.readouterr().out


def test_score_matches_hand_worked_values():
    y = pd.Series([1.0, 2.0, 3.0, np.nan])
    pred = pd.Series([1.5, 2.0, 2.0, 9.0])
    s = score(y, pred, y.notna(), "l1")
    assert s["n_scored"] == 3 and s["mae"] == pytest.approx(0.5)
    assert np.isnan(score(y, pd.Series([1.0, 1.0, 1.0, 1.0]), y.notna(), "l1")["spearman"])   # constant prediction
    yb, pb = pd.Series([0.0, 1.0, 0.0, 1.0]), pd.Series([0.1, 0.9, 0.2, 0.8])
    assert score(yb, pb, yb.notna(), "bin")["aucpr"] == 1.0
