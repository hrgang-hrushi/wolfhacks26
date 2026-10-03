"""The check of rankings against pothole reports."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from src.model import pothole_check as pc


def frame(n=100, blocks=10, city="charlotte"):
    """n one-mile segments watched for one year, all without a traffic count, scores 0..n-1."""
    return pd.DataFrame({
        "seg_id": [f"s{i}" for i in range(n)], "pothole_city": city, "pothole_exposure_years": 1.0,
        "length_m": pc.M_PER_MILE, "mile_years": 1.0, "tr_aadt": np.nan,
        "split_block": [f"b{i % blocks}" for i in range(n)], "n_pothole_reports": 0, "n_pothole_ncdot": 0,
        "score_rating": np.arange(n, dtype=float)})


def test_C1_rows_without_the_heldout_flag_are_excluded(fake, table, tmp_path):
    d = pc.load(fake.processed_dir(tmp_path / "p", table))
    clt = pc.population(d) & (d.pothole_city == "charlotte")
    assert 0 < (clt & d.rate_heldout).sum() < clt.sum()                 # the fixture has both kinds
    assert d.score_pred_rate[~d.rate_heldout].isna().all() and d.score_pred_rate[d.rate_heldout].notna().all()
    assert d.score_pred_crack[~d.crack_heldout].isna().all()
    assert pc.check(d, "charlotte", "pred_rate")["n_segments"] == int((clt & d.rate_heldout).sum())
    assert pc.check(d, "charlotte", "rating")["n_segments"] == int(clt.sum())


def test_C2_reports_driven_by_traffic_alone_show_no_adjusted_lift(fake, table, tmp_path):
    d = pc.load(fake.processed_dir(tmp_path / "p", table, potholes="none"))
    clt = d.pothole_city == "charlotte"
    band = pc.traffic_band(d[clt])
    rng = np.random.default_rng(0)
    d.loc[clt, "n_pothole_reports"] = rng.poisson(band.map({"t1": 0.2, "t2": 1.0, "t3": 3.0, "none": 1.0}).values)
    d["score_pred_rate"] = d.tr_aadt                    # a "model" that only knows how busy the road is
    r = pc.check(d, "charlotte", "pred_rate")
    assert r["raw_lift"] > 1.5                          # looks impressive city-wide
    assert 0.7 < r["adjusted_lift"] < 1.4               # and is nothing once traffic is held level
    assert r["range"][0] < 1 < r["range"][1]


def test_C3_band_too_small_for_fifths_is_left_out_with_a_reason():
    d = frame(120)
    d.loc[:79, "tr_aadt"] = np.arange(80) + 100.0       # three traffic thirds of 26-27 segments, 40 without a count
    r = pc.check(d, "charlotte", "rating")
    assert sorted(b["group"] for b in r["excluded_bands"]) == ["none", "t1", "t2", "t3"]
    assert all("fewer than 50" in b["why"] for b in r["excluded_bands"])
    assert r["adjusted_lift"] is None and r["bands"] and r["n_segments"] == 120
    assert pc.check(frame(100), "charlotte", "rating")["excluded_bands"] == []


def test_C4_hand_worked_lift():
    d = frame(100)
    d.loc[d.score_rating >= 80, ["n_pothole_reports", "mile_years"]] = [3, 2.0]     # worst fifth: 60 reports, 40 mile-years
    d.loc[d.score_rating < 20, "n_pothole_reports"] = 1                             # best fifth: 20 reports, 20 mile-years
    r = pc.check(d, "charlotte", "rating")
    assert r["adjusted_lift"] == pytest.approx(1.5) and r["raw_lift"] == pytest.approx(1.5)
    assert (r["n_segments"], r["n_reports"], r["mile_years"]) == (100, 80, 120.0)
    d.loc[d.score_rating < 20, "n_pothole_reports"] = 0
    assert pc.check(d, "charlotte", "rating")["adjusted_lift"] is None              # nothing to divide by


def test_C5_range_resamples_whole_blocks_and_repeats(fake, table, tmp_path):
    d = frame(100)
    d["n_pothole_reports"] = np.random.default_rng(1).poisson(1 + d.score_rating / 40)
    fifth, _ = pc.fifths(d.score_rating, pd.Series("none", index=d.index))
    totals = pc.block_totals(d, fifth, "n_pothole_reports")
    times = np.array([2, 0, 1, 3, 0, 1, 1, 0, 2, 0])
    stacked = pd.concat([d[d.split_block == f"b{i}"] for i, k in enumerate(times) for _ in range(k)])
    assert pc.draw_lift(totals, times) == pytest.approx(pc.lift(stacked, fifth[stacked.index], "n_pothole_reports"))
    once = d[d.split_block.isin([f"b{i}" for i in np.flatnonzero(times)])]                # isin would lose the repeats
    assert pc.draw_lift(totals, times) != pytest.approx(pc.lift(once, fifth[once.index], "n_pothole_reports"))
    a, b = pc.block_range(d, fifth, "n_pothole_reports"), pc.block_range(d, fifth, "n_pothole_reports")
    assert a == b and a[1] == pc.N_DRAWS and a[0][0] < pc.lift(d, fifth, "n_pothole_reports") < a[0][1]
    assert pc.block_range(d, fifth, "n_pothole_reports", seed=1)[0] != a[0]


def test_C6_stale_or_mismatched_predictions_are_refused(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    pred = pd.read_parquet(p / "predictions.parquet")
    pred.drop(columns=["rate_heldout", "crack_heldout"]).to_parquet(p / "predictions.parquet")
    with pytest.raises(ValueError, match="predates the held-out flags"):
        pc.load(p)
    pd.concat([pred, pred.iloc[:1]]).to_parquet(p / "predictions.parquet")
    with pytest.raises(ValueError, match="predictions.parquet does not cover the same segments"):
        pc.load(p)
    pred.iloc[1:].to_parquet(p / "predictions.parquet")
    with pytest.raises(ValueError, match="predictions.parquet does not cover the same segments"):
        pc.load(p)
    pred.to_parquet(p / "predictions.parquet")
    lab = pd.read_parquet(p / "pothole_labels.parquet")
    lab.iloc[1:].to_parquet(p / "pothole_labels.parquet")
    with pytest.raises(ValueError, match="pothole_labels.parquet does not cover the same segments"):
        pc.load(p)


def test_C7_low_rating_and_high_prediction_both_mean_worst():
    s = pc.add_scores(pd.DataFrame({"pv_RTG_NBR": [0.0, 40.0, 95.0], "pred_rate": [9.0, 3.0, 0.5], "pred_crack": [.9, .5, .1],
                                    "rate_heldout": [True, True, False], "crack_heldout": [True, None, True]}))
    assert np.isnan(s.score_rating[0]) and s.score_rating[1] > s.score_rating[2]     # 40 is worse than 95; 0 is "no rating"
    assert s.score_pred_rate.tolist()[:2] == [9.0, 3.0] and np.isnan(s.score_pred_rate[2])
    assert np.isnan(s.score_pred_crack[1])
    d = frame(100).drop(columns="score_rating")
    d["pv_RTG_NBR"] = np.linspace(100, 30, 100)                                       # s99 has the lowest rating
    d["n_pothole_reports"] = (d.pv_RTG_NBR < 45).astype(int) * 4 + 1
    d = pc.add_scores(d.assign(pred_rate=1.0, pred_crack=0.5, rate_heldout=True, crack_heldout=True))
    assert pc.check(d, "charlotte", "rating")["adjusted_lift"] > 3


def test_C8_result_is_traceable_repeatable_and_swapped_in_whole(fake, table, tmp_path, monkeypatch):
    p = fake.processed_dir(tmp_path / "p", table)
    pc.main(p)
    out = json.loads((p / "results" / "pothole_check.json").read_text())
    for f in ("pothole_labels.parquet", "predictions.parquet", "segments_targets.parquet"):
        assert out["inputs"][f] == hashlib.sha256((p / f).read_bytes()).hexdigest()
    assert "commit" in out and len(out["rows"]) == 9 and (p / "results" / "pothole_check.md").exists()
    pc.main(p)
    again = json.loads((p / "results" / "pothole_check.json").read_text())
    assert {k: v for k, v in again.items() if k != "generated"} == {k: v for k, v in out.items() if k != "generated"}

    def boom(a, b):
        raise OSError("Operation timed out")
    second = (p / "results" / "pothole_check.json").read_bytes()
    monkeypatch.setattr(pc.os, "replace", boom)
    with pytest.raises(OSError):
        pc.main(p)
    assert (p / "results" / "pothole_check.json").read_bytes() == second


def test_C9_segments_without_a_traffic_count_form_their_own_band(fake, table, tmp_path):
    d = pc.load(fake.processed_dir(tmp_path / "p", table))
    clt = pc.population(d) & (d.pothole_city == "charlotte")
    r = pc.check(d, "charlotte", "rating")
    bands = {b["band"]: b["n"] for b in r["bands"]}
    assert set(bands) == {"none", "t1", "t2", "t3"} and bands["none"] == int((clt & d.tr_aadt.isna()).sum()) > 50
    assert sum(bands.values()) == r["n_segments"] == int(clt.sum())      # nobody dropped for lacking a count


def test_C10_sensitivity_row_counts_only_the_state_road_reports(fake, table, tmp_path):
    d = pc.load(fake.processed_dir(tmp_path / "p", table))
    clt = pc.population(d) & (d.pothole_city == "charlotte")
    both, ncdot = pc.check(d, "charlotte", "rating"), pc.check(d, "charlotte", "rating", "ncdot_only")
    assert ncdot["n_reports"] == int(d.n_pothole_ncdot[clt].sum()) < both["n_reports"] == int(d.n_pothole_reports[clt].sum())
    assert ncdot["reports"] == "ncdot_only" and ncdot["n_segments"] == both["n_segments"]


def test_C11_no_reports_gives_blank_lifts_without_an_error(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table, potholes="none")
    pc.main(p)
    out = json.loads((p / "results" / "pothole_check.json").read_text())
    for r in out["rows"]:
        assert r["n_reports"] == 0 and r["raw_lift"] is None and r["adjusted_lift"] is None and r["range"] is None
        assert r["n_valid_draws"] == 0 and "resamples" in r["range_note"]
