"""Frozen-model comparison (src/model/vision_frozen.py), with a small stand-in model. Ids E1 to E14."""

import glob
import json
import math

import numpy as np
import pandas as pd
import pytest
import torch
from sklearn.decomposition import PCA

from src.model import augment as A
from src.model import vision_data as V
from src.model import vision_frozen as Fz
from src.model import vision_metrics as M
from src.pipeline.chips import chip_path
from vision_helpers import REAL_CHIPS, chips_for, lopsided_chip, make_table, tiny_net_factory


def seeded_net():
    torch.manual_seed(0)
    return tiny_net_factory()


@pytest.fixture(scope="module")
def net():
    return seeded_net()


@pytest.fixture(scope="module")
def some_chips():
    return np.stack([lopsided_chip(i) for i in range(6)])


# ---------------------------------------------------------------- embedding (E1 to E6)

def test_e1_one_embedding_per_road_in_order(net, some_chips):
    e = Fz.embed(net, some_chips, (0,), batch=4)  # 6 chips in batches of 4: the short last batch is kept
    assert e.shape == (6, 1, 384) and e.dtype == np.float32
    for i in range(6):
        assert np.allclose(e[i, 0], Fz.embed(net, some_chips[i:i + 1], (0,))[0, 0], atol=1e-5)
    assert len({e[i, 0].tobytes() for i in range(6)}) == 6  # six different chips, six different rows


def test_e2_a_chip_embeds_the_same_alone_and_in_a_batch(net, some_chips):
    whole = Fz.embed(net, some_chips, A_VIEWS := tuple(range(8)), batch=512)
    small = Fz.embed(net, some_chips, A_VIEWS, batch=2)
    alone = Fz.embed(net, some_chips[3:4], A_VIEWS)
    assert np.allclose(whole, small, atol=1e-5) and np.allclose(whole[3], alone[0], atol=1e-5)


def test_e3_the_8_view_mean_is_taken_per_road(net, some_chips):
    e = Fz.embed(net, some_chips[:2], tuple(range(8)))
    for k in range(8):
        by_hand = Fz.embed(net, A.view(some_chips[0], k)[None], (0,))[0, 0]
        assert np.allclose(e[0, k], by_hand, atol=1e-5)  # column k really is view k of road 0
    mean_a, mean_b = e[0].mean(axis=0), e[1].mean(axis=0)
    assert not np.allclose(mean_a, mean_b, atol=1e-3)  # not an average across roads
    assert not np.allclose(mean_a, e.mean(axis=(0, 1)), atol=1e-3)


@pytest.mark.parametrize("k", range(8))
def test_e4_the_8_view_mean_ignores_how_the_chip_is_turned(net, some_chips, k):
    base = Fz.embed(net, some_chips[:1], tuple(range(8)))[0].mean(axis=0)
    turned = Fz.embed(net, A.view(some_chips[0], k)[None], tuple(range(8)))[0].mean(axis=0)
    assert np.allclose(base, turned, atol=1e-5)


def test_e5_one_view_and_eight_views_differ_on_a_lopsided_chip(net, some_chips):
    e = Fz.embed(net, some_chips[:1], tuple(range(8)))[0]
    assert not np.allclose(e[0], e.mean(axis=0), atol=1e-3)
    assert len({e[k].tobytes() for k in range(8)}) == 8  # the model sees 8 different pictures
    flat = Fz.embed(net, np.full((1, 4, 128, 128), 90, dtype=np.uint8), tuple(range(8)))[0]
    assert np.allclose(flat[0], flat.mean(axis=0), atol=1e-5)  # and the check is not vacuous


def test_e6_two_passes_are_identical_and_no_gradients_are_kept(some_chips):
    net = seeded_net()
    net.train()
    a = Fz.embed(net, some_chips, (0, 5))
    b = Fz.embed(net, some_chips, (0, 5))
    assert np.array_equal(a, b)
    assert not net.training and torch.is_grad_enabled()
    assert all(p.grad is None for p in net.parameters())


# ---------------------------------------------------------------- probe (E7 to E9, E12, E13)

@pytest.fixture(scope="module")
def planted():
    d = make_table(n_blocks=60, per_block=20, seed=1)
    emb = Fz.embed(seeded_net(), chips_for(d), tuple(range(8)))
    return d, emb.mean(axis=1)


def test_e7_the_model_that_scores_a_fold_never_sees_that_fold(planted, monkeypatch):
    d, emb = planted
    tagged = np.hstack([emb, d.fold.values[:, None].astype("float32")])  # last column: the row's fold
    calls = []

    class SpyScaler(Fz.StandardScaler):
        def fit(self, X, y=None):
            calls.append(("fit", set(np.unique(X[:, -1]).astype(int))))
            return super().fit(X, y)

        def transform(self, X, copy=None):
            calls.append(("transform", set(np.unique(X[:, -1]).astype(int))))
            return super().transform(X, copy)

    monkeypatch.setattr(Fz, "StandardScaler", SpyScaler)
    oof, skips = Fz.probe(tagged, d)
    assert not skips
    fits = [i for i, c in enumerate(calls) if c[0] == "fit"]
    assert len(fits) == 5 * 3  # five folds, three targets
    for i in fits:
        train_folds = calls[i][1]
        scored = calls[i + 2][1]  # fit, transform(train), transform(held-out)
        assert calls[i + 1] == ("transform", train_folds)
        assert len(scored) == 1 and not scored & train_folds
        assert train_folds == set(range(5)) - scored


def test_e7b_shuffling_a_held_out_folds_labels_does_not_change_its_predictions(planted):
    d, emb = planted
    oof, _ = Fz.probe(emb, d)
    changed = d.copy()
    in_fold = np.where(d.fold.values == 0)[0]
    rng = np.random.default_rng(0)
    for col in ("y_rate", "y_crack"):
        changed.iloc[in_fold, changed.columns.get_loc(col)] = d[col].values[rng.permutation(in_fold)]
    oof2, _ = Fz.probe(emb, changed)
    for col in ("pred_rate", "pred_crack"):
        assert np.array_equal(oof[col].values[in_fold], oof2[col].values[in_fold])  # fold 0's model is unchanged
        others = d.fold.values != 0
        assert not np.allclose(oof[col].values[others], oof2[col].values[others])  # the labels do matter elsewhere


def test_e8_real_labels_score_and_shuffled_labels_score_at_chance(planted):
    d, emb = planted
    oof, _ = Fz.probe(emb, d)
    real = Fz.score_arm(d, oof, ["rate_spearman", "crack_aucpr"])["pooled"]
    prevalence = float(np.nanmean(d.y_crack.values))
    assert real["rate_spearman"] > 0.5 and real["crack_aucpr"] > prevalence + 0.2
    shuffled = Fz.shuffled_labels(d, seed=0)
    assert not shuffled.y_rate.equals(d.y_rate)
    assert sorted(shuffled.y_rate.dropna()) == sorted(d.y_rate.dropna())  # the same labels, moved between roads
    assert (shuffled.y_rate.isna() == d.y_rate.isna()).all()
    oof_s, _ = Fz.probe(emb, shuffled)
    chance = Fz.score_arm(shuffled, oof_s, ["rate_spearman", "crack_aucpr"])["pooled"]
    assert abs(chance["rate_spearman"]) < 0.1
    assert abs(chance["crack_aucpr"] - float(np.nanmean(shuffled.y_crack.values))) < 0.1


def test_e9_each_usable_road_is_predicted_once(planted):
    d, emb = planted
    usable = np.ones(len(d), dtype=bool)
    usable[[3, 40, 500]] = False
    oof, _ = Fz.probe(emb, d, usable)
    assert list(oof.seg_id) == list(d.seg_id) and not oof.seg_id.duplicated().any()
    assert oof.pred_rate.notna().values.tolist() == usable.tolist()  # labelled or not, every usable road has a score
    assert oof.pred_crack.notna().values.tolist() == usable.tolist()
    zone = d.in_helene_zone.values == 1
    assert oof.pred_flood.notna().values.tolist() == (usable & zone).tolist()  # flood is scored inside the zone only


def test_e12_a_fold_without_training_labels_or_with_one_class_is_skipped_and_counted(planted):
    d, emb = planted
    only_fold_0 = d.copy()
    only_fold_0.loc[only_fold_0.fold != 0, "y_crack"] = np.nan  # fold 0 then has nothing to train on
    oof, skips = Fz.probe(emb, only_fold_0)
    assert "crack fold 0: no labelled training rows" in skips
    assert oof.pred_crack[only_fold_0.fold == 0].isna().all() and oof.pred_crack[only_fold_0.fold == 1].notna().all()

    one_class = d.copy()
    one_class["y_crack"] = np.where(one_class.fold == 2, 1.0, 0.0)  # every fold but 2 is all zeros
    oof, skips = Fz.probe(emb, one_class)
    assert skips == ["crack fold 2: one class in training"]
    assert oof.pred_crack[one_class.fold == 2].isna().all() and oof.pred_crack[one_class.fold != 2].notna().all()
    assert oof.pred_rate.notna().all()  # the other targets are untouched
    scored = Fz.score_arm(one_class, oof, ["crack_aucpr"])
    assert math.isnan(scored["by_fold"]["crack_aucpr"]["2"])
    results = {"title": "t", "metrics": ["crack_aucpr"], "hashes": {"code": "c"}, "arms": {"a": scored}, "skips": skips}
    report = M.render_report(results)
    assert "folds skipped: 1" in report and "crack fold 2: one class in training" in report


def test_e13_a_flood_subset_with_no_rows_gives_nan_not_an_error(planted):
    d, emb = planted
    no_zone = d.assign(in_helene_zone=0)
    oof, skips = Fz.probe(emb, no_zone)
    assert "flood: no labels" in skips and oof.pred_flood.isna().all()
    scored = Fz.score_arm(no_zone, oof, ["flood_p50", "flood_aucpr"])["pooled"]
    assert math.isnan(scored["flood_p50"]) and math.isnan(scored["flood_aucpr"])
    no_columns = d.drop(columns=["y_helene_failed", "in_helene_zone"])
    oof, skips = Fz.probe(emb, no_columns)
    assert "flood: no labels" in skips and oof.pred_rate.notna().all()
    assert not Fz.target_mask(no_columns, "flood").any()


# ---------------------------------------------------------------- the whole runner (E10, E14)

@pytest.fixture(scope="module")
def frozen_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("frozen")
    d = make_table(n_blocks=40, per_block=15, seed=2)
    processed, cdir, out = tmp / "processed", tmp / "chips", tmp / "vision"
    processed.mkdir(), cdir.mkdir()
    d.to_parquet(processed / "segments_targets.parquet")
    chips = chips_for(d)
    chips[5, :, :32, :] = 0    # 25% blank
    chips[77, :, :, :16] = 0   # 12.5% blank
    for i, (seg_id, c) in enumerate(zip(d.seg_id, chips)):
        if i != 9:             # road 9 has no chip at all
            np.save(cdir / chip_path(seg_id).name, c)
    results = Fz.main(processed, cdir, out, net_factory=seeded_net, n_boot=40, log=lambda *a: None)
    return d, out, results


def test_e10_both_arms_are_scored_on_the_same_roads(frozen_run):
    d, out, results = frozen_run
    a, b = pd.read_parquet(out / "frozen" / "oof_1view.parquet"), pd.read_parquet(out / "frozen" / "oof_8view.parquet")
    assert list(a.seg_id) == list(b.seg_id)
    for col in ("pred_rate", "pred_crack", "pred_flood"):
        assert (a[col].isna() == b[col].isna()).all()
    index = pd.read_parquet(out / "frozen" / "index.parquet")
    assert results["hashes"]["manifest"] == V.manifest_hash(index.seg_id[index.usable])
    assert results["counts"] == {**results["counts"], "segments_in_table": 600, "segments_with_a_chip": 599,
                                 "left_out_as_blank": 2, "segments_compared": 597}
    assert set(results["arms"]) == {"1view", "8view"} and len(results["differences"]) == len(results["metrics"]) == 5
    assert all(d_["arm"] == "8view" and d_["vs"] == "1view" for d_ in results["differences"])
    assert set(results["hashes"]) == {"code", "table", "manifest", "weights"}
    assert all(len(h) == 64 for h in results["hashes"].values())
    saved = json.loads((out / "frozen" / "metrics.json").read_text())
    assert saved["arms"]["8view"]["pooled"]["rate_mae"] == results["arms"]["8view"]["pooled"]["rate_mae"]
    report = (out / "frozen" / "report.md").read_text()
    printed = M.report_numbers(report)

    def leaves(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from leaves(v)
        elif isinstance(o, list):
            for v in o:
                yield from leaves(v)
        elif isinstance(o, float) and not math.isnan(o):
            yield round(o, 4)

    assert printed and set(round(p, 4) for p in printed) <= set(leaves(saved))
    control = saved["controls"]["shuffled labels, 8view"]
    assert abs(control["rate_spearman"]) < 0.15 and saved["arms"]["8view"]["pooled"]["rate_spearman"] > 0.5


def test_e14_by_products_cover_every_valid_chip_blank_ones_included(frozen_run):
    d, out, results = frozen_run
    with_chip = [s for i, s in enumerate(d.seg_id) if i != 9]
    ndvi = pd.read_parquet(out / "ndvi_stats.parquet")
    assert list(ndvi.seg_id) == with_chip
    assert {"im_ndvi_mean", "im_ndvi_std", "im_impervious_frac", "im_bright_var", "blank_frac", "usable"} <= set(ndvi.columns)
    assert int((~ndvi.usable).sum()) == 2 and set(ndvi.seg_id[~ndvi.usable]) == {d.seg_id[5], d.seg_id[77]}
    assert ndvi.blank_frac[ndvi.seg_id == d.seg_id[5]].iloc[0] == pytest.approx(0.25)
    for name, emb_file in (("vit_frozen_statewide.parquet", "emb_view0.npy"),
                           ("vit_frozen_statewide_8view.parquet", "emb_mean8.npy")):
        f = pd.read_parquet(out / name)
        assert list(f.columns) == ["seg_id"] + [f"im_emb{i}" for i in range(16)]  # the landed vit_frozen layout
        assert list(f.seg_id) == with_chip and f.notna().all().all()
        emb = np.load(out / "frozen" / emb_file)
        assert emb.shape == (599, 384)
        assert np.allclose(f.iloc[:, 1:].values, PCA(16, random_state=0).fit_transform(emb), atol=1e-4)
    assert not list(out.rglob("*.tmp"))
    produced = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert produced == {"ndvi_stats.parquet", "vit_frozen_statewide.parquet", "vit_frozen_statewide_8view.parquet",
                        "frozen/emb_view0.npy", "frozen/emb_mean8.npy", "frozen/index.parquet",
                        "frozen/oof_1view.parquet", "frozen/oof_8view.parquet", "frozen/metrics.json",
                        "frozen/report.md"}


def test_e14b_a_table_with_no_chips_is_refused(tmp_path):
    d = make_table(n_blocks=6, per_block=4)
    (tmp_path / "p").mkdir(), (tmp_path / "c").mkdir()
    d.to_parquet(tmp_path / "p" / "segments_targets.parquet")
    with pytest.raises(ValueError, match="no segment in the table has a chip"):
        Fz.main(tmp_path / "p", tmp_path / "c", tmp_path / "v", net_factory=seeded_net, log=lambda *a: None)


# ---------------------------------------------------------------- the real model (E11, GPU box only)

@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs the cloud GPU box")
def test_e11_the_real_weights_give_384_numbers_per_road_on_the_gpu():
    files = sorted(glob.glob(str(REAL_CHIPS / "*.npy")))[:8]
    assert files, "no chips on the box"
    chips = np.stack([np.load(f) for f in files])
    net = Fz.default_net()
    assert Fz.device_of(net).type == "cuda"
    e = Fz.embed(net, chips, tuple(range(8)))
    assert e.shape == (len(files), 8, 384) and np.isfinite(e).all()
    assert len(V.weights_hash(net)) == 64
    base = e.mean(axis=1)[0]
    turned = Fz.embed(net, A.view(chips[0], 3)[None], tuple(range(8)))[0].mean(axis=0)
    assert np.allclose(base, turned, atol=5e-2)  # half precision on the GPU: loose, but the same road
