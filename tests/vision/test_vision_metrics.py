"""Scores and the comparison between arms (src/model/vision_metrics.py). Ids M1 to M11."""

import json
import math

import numpy as np
import pytest

from src.model import vision_metrics as M

HASHES = {"code": "c" * 64, "table": "t" * 64, "manifest": "m" * 64}


def test_m1_perfect_predictions():
    y = np.array([0.5, 1.0, 2.0, 4.0, np.nan])
    assert M.rate_metrics(y, y) == {"n_rate": 4, "rate_mae": 0.0, "rate_spearman": 1.0}
    assert M.mae([1.0, 2.0, 3.0], [2.0, 2.0, 5.0]) == pytest.approx(1.0)
    assert M.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    yc = np.array([0, 0, 1, 1, 0, 1], dtype=float)
    assert M.crack_metrics(yc, yc)["crack_aucpr"] == pytest.approx(1.0)
    assert M.crack_metrics(yc, yc)["crack_prevalence"] == pytest.approx(0.5)


def test_m2_constant_or_empty_inputs_give_nan_not_an_error():
    y = np.array([1.0, 2.0, 3.0])
    assert math.isnan(M.spearman(y, np.full(3, 7.0)))
    assert math.isnan(M.spearman(np.full(3, 2.0), y))
    assert M.mae(y, np.full(3, 7.0)) == pytest.approx(5.0)
    empty = np.array([])
    assert math.isnan(M.mae(empty, empty)) and math.isnan(M.spearman(empty, empty)) and math.isnan(M.aucpr(empty, empty))
    assert math.isnan(M.precision_at(empty, empty))
    assert math.isnan(M.aucpr(np.ones(5), np.arange(5.0)))   # one class only
    assert math.isnan(M.aucpr(np.zeros(5), np.arange(5.0)))
    all_nan = np.full(4, np.nan)
    assert M.rate_metrics(all_nan, y[:1].repeat(4))["n_rate"] == 0
    assert math.isnan(M.flood_metrics(all_nan, all_nan)["flood_p50"])
    assert M.flood_metrics(all_nan, all_nan)["n_flood"] == 0


def test_m3_random_scores_give_aucpr_near_prevalence():
    rng = np.random.default_rng(0)
    y = (rng.random(20_000) < 0.158).astype(float)
    got = M.crack_metrics(y, rng.random(20_000))
    assert abs(got["crack_aucpr"] - got["crack_prevalence"]) < 0.03
    assert got["crack_prevalence"] == pytest.approx(0.158, abs=0.01)


def test_m4_precision_at_50_on_a_hand_example():
    y = np.zeros(200)
    pred = np.arange(200, dtype=float)       # the 50 highest scores are rows 150..199
    y[160:190] = 1                            # 30 of those are positive
    y[:10] = 1                                # positives the ranking misses do not count
    assert M.precision_at(y, pred, 50) == pytest.approx(30 / 50)
    assert M.flood_metrics(y, pred)["flood_p50"] == pytest.approx(0.6)
    assert M.precision_at(np.array([1.0, 0.0]), np.array([0.9, 0.1]), 50) == pytest.approx(0.5)  # fewer than 50 rows
    assert M.precision_at([1, 0, np.nan], [0.2, 0.9, 5.0], 1) == 0.0  # a row with no label is not ranked


def test_m5_the_do_nothing_error_uses_training_fold_medians_only():
    y = np.array([1.0, 1.0, 1.0, 100.0, 100.0, np.nan])
    fold = np.array([0, 0, 0, 1, 1, 1])
    # fold 0 is predicted with the median of fold 1 (100); fold 1 with the median of fold 0 (1)
    assert M.naive_rate_mae(y, fold) == pytest.approx(99.0)
    # using the overall median (1.0) would give (0+0+0+99+99)/5 = 39.6: the function must not do that
    assert M.naive_rate_mae(y, fold) != pytest.approx(39.6)


def test_m6_per_fold_and_pooled_values_match_hand_calculation():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    pred = np.array([1.0, 3.0, 3.0, 8.0])
    fold = np.array([0, 0, 1, 1])
    assert M.by_fold(y, pred, fold, "rate_mae") == {"0": 0.5, "1": 2.0}
    assert M.mae(y, pred) == pytest.approx(1.25)
    yc, pc = np.array([0.0, 1.0, 1.0, 0.0]), np.array([0.1, 0.9, 0.2, 0.8])
    assert M.by_fold(yc, pc, fold, "crack_aucpr") == {"0": 1.0, "1": 0.5}


def test_m7_identical_arms_give_a_difference_of_exactly_zero():
    rng = np.random.default_rng(1)
    y, pred = rng.normal(size=500), rng.normal(size=500)
    blocks = rng.integers(0, 40, size=500)
    fold = blocks % 5
    for metric in ("rate_mae", "rate_spearman"):
        a = M.by_fold(y, pred, fold, metric)
        d = M.paired_diff(a, dict(a))
        assert d["mean"] == 0.0 and set(d["per_fold"].values()) == {0.0} and d["folds_up"] == d["folds_down"] == 0
        b = M.block_bootstrap_diff(blocks, y, pred, pred.copy(), metric, n=200)
        assert b["diff"] == 0.0 and b["lo"] == 0.0 and b["hi"] == 0.0
        assert not M.interval_excludes_zero(b) and not M.is_real(b)


def test_m8_a_planted_gain_is_detected():
    rng = np.random.default_rng(2)
    y = rng.normal(size=3000)
    blocks = rng.integers(0, 150, size=3000)
    good = y + rng.normal(scale=0.5, size=3000)
    weak = y + rng.normal(scale=1.5, size=3000)
    d = M.block_bootstrap_diff(blocks, y, good, weak, "rate_spearman", n=300)
    assert d["diff"] > 0.15 and d["lo"] > 0 and M.interval_excludes_zero(d) and M.is_real(d)
    e = M.block_bootstrap_diff(blocks, y, good, weak, "rate_mae", n=300)
    assert e["diff"] < 0 and e["hi"] < 0  # lower error for the better arm
    assert not M.is_real(d, spread=d["diff"] + 0.01)  # smaller than the seed-to-seed spread: not counted
    assert M.is_real(d, spread=0.01)
    pf = M.paired_diff(M.by_fold(y, good, blocks % 5, "rate_spearman"), M.by_fold(y, weak, blocks % 5, "rate_spearman"))
    assert pf["folds_up"] == 5 and pf["folds_down"] == 0 and pf["mean"] > 0.15


def test_m9_the_bootstrap_resamples_whole_blocks_and_repeats_with_its_seed(monkeypatch):
    rng = np.random.default_rng(3)
    blocks = np.repeat(np.arange(30), 20)
    y = rng.normal(size=600)
    a, b = y + rng.normal(scale=0.3, size=600), y + rng.normal(scale=0.4, size=600)
    r1 = M.block_bootstrap_diff(blocks, y, a, b, "rate_mae", n=100, seed=5)
    r2 = M.block_bootstrap_diff(blocks, y, a, b, "rate_mae", n=100, seed=5)
    r3 = M.block_bootstrap_diff(blocks, y, a, b, "rate_mae", n=100, seed=6)
    assert r1 == r2 and (r1["lo"], r1["hi"]) != (r3["lo"], r3["hi"]) and r1["n_blocks"] == 30
    seen = []

    def spy(yy, pp):
        seen.append(np.asarray(yy).copy())
        return 0.0

    monkeypatch.setitem(M.METRIC_FNS, "rate_mae", spy)
    tagged = blocks.astype(float)  # make y carry its block id so a resample can be inspected
    M.block_bootstrap_diff(blocks, tagged, a, b, "rate_mae", n=5, seed=0)
    for sample in seen[2::2]:  # the first two calls are the point estimate
        ids, counts = np.unique(sample, return_counts=True)
        assert len(sample) == 600 and (counts % 20 == 0).all()  # blocks come whole, 20 rows at a time
        assert len(ids) < 30  # with replacement: some blocks repeat, some are left out


def test_m9b_seed_spread_uses_only_real_numbers():
    assert M.seed_spread([0.41, 0.44]) == pytest.approx(0.03)
    assert M.seed_spread([0.41, 0.44, float("nan")]) == pytest.approx(0.03)
    assert math.isnan(M.seed_spread([0.41])) and math.isnan(M.seed_spread([]))


def sample_results():
    rng = np.random.default_rng(4)

    def arm():
        return {"pooled": {"rate_mae": float(rng.uniform(0.5, 1)), "rate_spearman": float(rng.uniform(0.1, 0.5)),
                           "crack_aucpr": float(rng.uniform(0.2, 0.4))},
                "by_fold": {m: {str(k): float(rng.uniform(0.1, 1)) for k in range(5)}
                            for m in ("rate_mae", "rate_spearman", "crack_aucpr")}}

    return {"title": "Frozen model: 1 view against the average of 8", "metrics": ["rate_mae", "rate_spearman", "crack_aucpr"],
            "hashes": dict(HASHES), "counts": {"roads_with_a_photo": 112_000, "excluded_as_blank": 37},
            "reference": {"rate_mae_do_nothing": 0.8123, "crack_prevalence": 0.1575},
            "arms": {"1view": arm(), "8view": arm()},
            "differences": [{"arm": "8view", "vs": "1view", "metric": "rate_mae", "diff": -0.0123, "lo": -0.0201,
                             "hi": -0.0044, "folds_up": 0, "folds_down": 5, "seed_spread": float("nan"), "real": True},
                            {"arm": "8view", "vs": "1view", "metric": "crack_aucpr", "diff": 0.0011, "lo": -0.0032,
                             "hi": 0.0051, "folds_up": 3, "folds_down": 2, "seed_spread": float("nan"), "real": False}],
            "controls": {"shuffled labels": {"rate_spearman": 0.0031, "crack_aucpr": 0.1581}},
            "skips": ["fold 3 flood: one class in training"], "notes": ["folds: crc32(split_block) % 5"]}


def leaves(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from leaves(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from leaves(v)
    elif isinstance(obj, float) and not math.isnan(obj):
        yield obj


def test_m10_every_number_in_the_report_is_a_number_in_the_results():
    results = json.loads(json.dumps(sample_results()))  # as read back from the results file
    report = M.render_report(results)
    printed = M.report_numbers(report)
    allowed = {round(v, 4) for v in leaves(results)}
    assert len(printed) >= 2 * 3 + 2 * 15 + 6  # pooled cells, per-fold cells, the difference rows
    assert all(round(p, 4) in allowed for p in printed), [p for p in printed if round(p, 4) not in allowed]
    for arm in results["arms"].values():
        for v in arm["pooled"].values():
            assert M.fmt(v) in report
    assert "112,000" in report and "| better |" in report and "| no measurable difference |" in report
    assert "folds skipped: 1" in report and "one class in training" in report
    assert all(h in report for h in HASHES.values())
    assert M.fmt(float("nan")) == "n/a" and M.fmt(None) == "n/a" and M.fmt(3) == "3" and M.fmt(0.5) == "0.5000"


def test_m10b_a_worse_result_is_called_worse():
    r = sample_results()
    r["differences"] = [dict(r["differences"][0], diff=0.02, lo=0.01, hi=0.03),          # higher error
                        dict(r["differences"][1], diff=-0.02, lo=-0.03, hi=-0.01, real=True)]  # lower score
    report = M.render_report(r)
    assert report.count("| worse |") == 2 and "| better |" not in report


@pytest.mark.parametrize("key", ["code", "table", "manifest"])
def test_m11_results_with_different_fingerprints_are_refused(key):
    a, b = {"hashes": dict(HASHES)}, {"hashes": dict(HASHES)}
    M.compare(a, b)
    b["hashes"][key] = "x" * 64
    with pytest.raises(ValueError, match=key):
        M.compare(a, b)
    del b["hashes"][key]
    with pytest.raises(ValueError, match=key):
        M.compare(a, b)
