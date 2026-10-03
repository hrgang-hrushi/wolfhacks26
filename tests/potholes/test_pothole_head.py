"""The pothole head: trained on Charlotte, scored on held-out Charlotte blocks and on Raleigh."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from src.model import common
from src.model import pothole_head as ph

pytestmark = pytest.mark.usefixtures("small_models", "few_draws")


@pytest.fixture
def few_draws(monkeypatch):
    monkeypatch.setattr(ph, "GAP_DRAWS", 200)
SHARED = ("segments_targets.parquet", "split.parquet", "predictions.parquet")


def edit_labels(p, change):
    lab = pd.read_parquet(p / "pothole_labels.parquet")
    change(lab)
    lab.to_parquet(p / "pothole_labels.parquet")


def test_H1_label_or_pothole_columns_cannot_be_inputs(fake, table, tmp_path, monkeypatch):
    d = ph.load_table(fake.processed_dir(tmp_path / "p", table))
    for col in ("y_pothole_any", "y_pothole_rate", "n_pothole_reports", "n_pothole_ncdot", "pred_rate"):
        with pytest.raises(ValueError, match="banned model inputs"):
            common.prep(d, common.PV + [col])
    # the coverage flag and the exposure are not banned by prefix, so the head refuses them by name
    for col in ("pothole_city", "pothole_exposure_years"):
        monkeypatch.setattr(ph, "terrain_columns", lambda d, col=col: ["tn_elev", col])
        with pytest.raises(ValueError, match="pothole columns cannot be model inputs"):
            ph.run(tmp_path / "p")
    monkeypatch.undo()
    assert not [c for c in ph.features(d) if "pothole" in c or c.startswith(("y_", "n_", "pred_"))]


def test_H2_blank_labels_never_train(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    d = ph.load_table(p)
    train = ph.labelled(d, "charlotte")
    assert d.y_pothole_any[train].notna().all() and (d.pothole_city[train] == "charlotte").all()
    assert not train[d.pothole_city.isna()].any() and d.y_pothole_any[d.pothole_city.isna()].isna().all()
    res, _ = ph.run(p)
    assert res["n_train"] == int(train.sum()) < int((d.pothole_city == "charlotte").sum())


def test_H3_shared_block_folds_and_no_block_on_both_sides(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    d = ph.load_table(p)
    split = pd.read_parquet(p / "split.parquet").set_index("seg_id")
    assert (d.fold.values == split.fold.loc[d.seg_id].values).all()
    assert (d.fold == d.split_block.map(common.fold_of)).all()
    train = ph.labelled(d, "charlotte")
    for k in range(common.N_FOLDS):
        assert not set(d.split_block[train & (d.fold == k)]) & set(d.split_block[train & (d.fold != k)])
    assert d.fold[train].nunique() == common.N_FOLDS
    split = split.reset_index()                          # a targets table whose folds are not the shared split is refused
    split.loc[0, "fold"] = (split.fold[0] + 1) % common.N_FOLDS
    split.to_parquet(p / "split.parquet")
    with pytest.raises(ValueError, match="does not carry the folds in split.parquet"):
        ph.load_table(p)


def test_H4_no_raleigh_segment_trains_the_transfer_model(fake, table, tmp_path, monkeypatch):
    p = fake.processed_dir(tmp_path / "p", table)
    d, masks = ph.load_table(p), []
    real = ph.fit_all_predict
    monkeypatch.setattr(ph, "fit_all_predict", lambda X, y, kind, mask, seed=0: (masks.append(mask.copy()), real(X, y, kind, mask, seed))[1])
    real_oof = ph.oof
    monkeypatch.setattr(ph, "oof", lambda d, X, y, kind, mask, seed=0: (masks.append(mask.copy()), real_oof(d, X, y, kind, mask, seed))[1])
    res, pred = ph.run(p)
    assert len(masks) == 4
    for m in masks:                                     # every fit, held-out or full, is Charlotte only
        assert m.sum() > 0 and (d.pothole_city[m] == "charlotte").all()
    assert res["raleigh_transfer"]["head"]["n_scored"] == int(ph.labelled(d, "raleigh").sum()) > 0


def test_H5_segments_resurfaced_inside_the_window_are_excluded(fake, table, tmp_path):
    d = ph.load_table(fake.processed_dir(tmp_path / "p", table))
    clt, ral = d.pothole_city == "charlotte", d.pothole_city == "raleigh"
    train, test = ph.labelled(d, "charlotte"), ph.labelled(d, "raleigh")
    assert (clt & (d.pv_YEAR_LAST_REHAB >= 2023)).sum() > 0 and not train[clt & (d.pv_YEAR_LAST_REHAB >= 2023)].any()
    assert train[clt & (d.pv_YEAR_LAST_REHAB == 2022)].all() and train[clt & d.pv_YEAR_LAST_REHAB.isna()].all()
    assert test[ral & (d.pv_YEAR_LAST_REHAB == 2024)].all() and not test[ral & (d.pv_YEAR_LAST_REHAB >= 2025)].any()


def test_H6_one_class_fold_is_skipped_and_few_positives_are_flagged(fake, table, tmp_path, capsys):
    p = fake.processed_dir(tmp_path / "p", table)
    d = ph.load_table(p)
    fold0 = set(d.seg_id[d.fold == 0])

    def only_fold0_and_five_in_raleigh(lab):
        clt = lab.pothole_city == "charlotte"
        lab.loc[clt & ~lab.seg_id.isin(fold0), "y_pothole_any"] = 0.0
        ral = lab.index[lab.pothole_city == "raleigh"]
        lab.loc[ral, "y_pothole_any"] = 0.0
        lab.loc[ral[:5], "y_pothole_any"] = 1.0
    edit_labels(p, only_fold0_and_five_in_raleigh)
    res, pred = ph.run(p)
    assert "fold 0 skipped: one class in the training rows" in capsys.readouterr().out
    assert res["status"] == "ok" and res["too_few"] is True and res["raleigh_transfer"]["n_pos"] <= 5
    train = ph.labelled(ph.load_table(p), "charlotte")
    skipped = (train & (d.fold == 0)).values
    assert skipped.any() and pred.pred_pothole[skipped].notna().all()       # they still get the full model's value
    assert not pred.pothole_heldout[skipped].any()                           # and it is marked as not held out


def test_H7_every_method_is_scored_on_the_same_rows(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    res, _ = ph.run(p)
    d = ph.load_table(p)
    for part, city in (("charlotte_heldout", "charlotte"), ("raleigh_transfer", "raleigh")):
        e, mask = res[part], ph.labelled(d, city)
        assert e["n"] == int(mask.sum()) and e["head"]["n_scored"] == e["traffic_only"]["n_scored"] == e["n"]
        assert e["main_model"]["n_scored"] == e["n_common"] == int((mask & d.rate_heldout).sum()) < e["n"]
        assert all(e[m]["aucpr_common"] is not None for m in ph.METHODS)
        assert e["main_model"]["aucpr_common"] == pytest.approx(e["main_model"]["aucpr"])
        assert e["base_rate"] == pytest.approx(d.y_pothole_any[mask].mean())
        shared = mask & d.rate_heldout                   # hits in the top 50 are compared on the shared rows too
        top = d.pred_rate[shared].nlargest(50).index
        assert e["main_model"]["p_at_50_common"] == pytest.approx(d.y_pothole_any[top].mean())
        assert all(e[m]["p_at_50_common"] is not None for m in ph.METHODS)


def test_H8_two_runs_are_identical(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    (r1, p1), (r2, p2) = ph.run(p), ph.run(p)
    pd.testing.assert_frame_equal(p1, p2)
    assert r1 == r2


def test_H9_suspiciously_good_score_raises(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    t = pd.read_parquet(p / "segments_targets.parquet")
    lab = pd.read_parquet(p / "pothole_labels.parquet")
    t["tn_copy_of_answer"] = lab.y_pothole_any.fillna(0).values      # a leak the name-based bans cannot see
    t.to_parquet(p / "segments_targets.parquet")
    with pytest.raises(RuntimeError, match="probably leaking"):
        ph.run(p)


def test_H10_category_unseen_in_charlotte_does_not_crash(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    t = pd.read_parquet(p / "segments_targets.parquet")
    ral = (t.mid_x // 5000).between(104, 105)
    t.loc[ral, "pv_LAST_REHAB_TYPE"] = "A Treatment Charlotte Never Used"
    t.to_parquet(p / "segments_targets.parquet")
    res, pred = ph.run(p)
    assert res["status"] == "ok" and pred.pred_pothole[ral.values].notna().all()
    assert res["raleigh_transfer"]["head"]["aucpr"] is not None


def test_H11_flags_are_true_only_where_real(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    res, pred = ph.run(p)
    d = ph.load_table(p)
    assert list(pred.columns) == ["seg_id", "pred_pothole", "pothole_heldout", "pothole_tested_area", "pothole_city"]
    assert (pred.pothole_tested_area.values == d.pothole_city.notna().values).all()
    assert 0 < pred.pothole_tested_area.sum() < len(pred)
    assert pred.pred_pothole.notna().all() and pred.pothole_heldout.all()   # here every training row has a held-out value
    train = ph.labelled(d, "charlotte")
    X = common.prep(d, ph.features(d))
    oof = common.oof(d, X, d.y_pothole_any, "bin", train)
    assert np.allclose(pred.pred_pothole[train.values], oof[train])        # training rows carry the held-out value, not the fit


def test_H12_shared_files_are_untouched(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    before = {f: hashlib.sha256((p / f).read_bytes()).hexdigest() for f in SHARED}
    ph.main(p)
    assert {f: hashlib.sha256((p / f).read_bytes()).hexdigest() for f in SHARED} == before
    assert (p / "pothole_predictions.parquet").exists() and (p / "results" / "pothole_head.md").exists()
    out = json.loads((p / "results" / "pothole_head.json").read_text())
    assert out["inputs"]["segments_targets.parquet"] == before["segments_targets.parquet"] and "commit" in out


def test_H13_pass_means_something(fake, table, tmp_path):
    by_age, _ = ph.run(fake.processed_dir(tmp_path / "age", table, potholes="age"))
    e = by_age["charlotte_heldout"]
    assert by_age["beats_traffic"] is True and e["head"]["aucpr"] > e["traffic_only"]["aucpr"] + 0.1
    assert e["head"]["aucpr"] > e["base_rate"] + 0.1
    by_traffic, _ = ph.run(fake.processed_dir(tmp_path / "traffic", table, potholes="traffic"))
    e = by_traffic["charlotte_heldout"]
    assert e["head"]["aucpr"] <= e["traffic_only"]["aucpr"] + 0.05         # nothing to add beyond traffic


def test_H14_empty_charlotte_population_is_unavailable_not_a_loss(fake, table, tmp_path):
    p = fake.processed_dir(tmp_path / "p", table)
    edit_labels(p, lambda lab: lab.__setitem__("y_pothole_any", lab.y_pothole_any.where(lab.pothole_city != "charlotte")))
    ph.main(p)
    out = json.loads((p / "results" / "pothole_head.json").read_text())
    pred = pd.read_parquet(p / "pothole_predictions.parquet")
    assert out["status"] == "unavailable" and "no labelled Charlotte" in out["reason"]
    assert out["beats_traffic"] is None and out["distinguishable_from_traffic"] is None
    assert out["charlotte_heldout"] is None and out["raleigh_transfer"] is None        # null, not missing and not zero
    assert pred.pred_pothole.isna().all() and not pred.pothole_heldout.any()
    assert "unavailable" in (p / "results" / "pothole_head.md").read_text()


def test_H15_one_class_charlotte_population_is_unavailable(fake, table, tmp_path):
    res, pred = ph.run(fake.processed_dir(tmp_path / "p", table, potholes="none"))
    assert res["status"] == "unavailable" and "one class" in res["reason"] and res["n_train_pos"] == 0
    assert res["beats_traffic"] is None and pred.pred_pothole.isna().all() and not pred.pothole_heldout.any()


def test_H16_gap_to_the_traffic_only_model_comes_with_a_range(fake, table, tmp_path):
    by_age, _ = ph.run(fake.processed_dir(tmp_path / "age", table, potholes="age"))
    g = by_age["charlotte_heldout"]["head_minus_traffic"]
    e = by_age["charlotte_heldout"]
    assert g["gap"] == pytest.approx(e["head"]["aucpr"] - e["traffic_only"]["aucpr"]) and g["n_valid_draws"] == 200
    assert g["range"][0] < g["gap"] < g["range"][1] and g["range"][0] > 0 and by_age["distinguishable_from_traffic"] is True
    d = ph.load_table(tmp_path / "age")
    y, mask = d.y_pothole_any, ph.labelled(d, "charlotte")
    rng = np.random.default_rng(0)                       # two scores of equal skill: a small gap is not called a win
    truth = y.fillna(0) + rng.normal(0, 1, len(d))
    a, b = (pd.Series(truth + rng.normal(0, 1, len(d)), index=d.index) for _ in range(2))
    g = ph.gap_range(d, y, a, b, mask)
    assert abs(g["gap"]) < 0.05 and g["range"][0] < 0 < g["range"][1]
    assert ph.gap_range(d, y, a, a, mask, n=50) == {"gap": 0.0, "range": [0.0, 0.0], "n_valid_draws": 50}
    assert ph.gap_range(d, y, a, a, mask & False) == {"gap": None, "range": None, "n_valid_draws": 0}
    w = (d.split_block[mask] == d.split_block[mask].iloc[0]).values      # whole blocks: weights are constant inside a block
    assert w.any() and not w.all()
