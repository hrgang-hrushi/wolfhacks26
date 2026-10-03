"""Fine-tune comparison (src/model/vision_finetune.py), with a small stand-in model on CPU. Ids F1 to F19, E15."""

import copy
import glob
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
import torch.nn as nn

from src.model import augment as A
from src.model import vision_data as V
from src.model import vision_finetune as Ft
from src.model import vision_frozen as Fz
from src.model import vision_metrics as M
from src.pipeline.chips import chip_path
from vision_helpers import REAL_CHIPS, ROOT, chips_for, make_table, tiny_net_factory

QUIET = lambda *a, **k: None  # noqa: E731
TIMING = {"startup_s": 3.0, "train_epoch_s": 30.0, "score_epoch_s": 5.0, "tta_s": 20.0, "write_s": 1.0}


@pytest.fixture(scope="module")
def data():
    d = make_table(n_blocks=30, per_block=12, seed=3)
    return d, chips_for(d)


def small_cfg(arm="full", seed=0, epochs=2, batch_size=8):
    return Ft.arm_config(arm, seed, epochs, batch_size)


def fit(data, arm="full", seed=0, epochs=2, k=0, factory=tiny_net_factory, **kw):
    d, chips = data
    return Ft.train_fold(d, chips, k, small_cfg(arm, seed, epochs), factory, workers=0, log=QUIET, **kw)


# ---------------------------------------------------------------- loss (F1, F2)

def test_f1_the_loss_skips_missing_labels_and_is_zero_for_a_target_with_none():
    torch.manual_seed(0)
    out, r, c = torch.randn(8, 2), torch.rand(8) * 3, (torch.rand(8) > 0.5).float()
    both = torch.ones(8, 2)
    only_rate = torch.tensor([[1.0, 0.0]] * 8)
    assert torch.isclose(Ft.masked_loss(out, r, c, only_rate), (out[:, 0] - r).abs().mean())  # cracking adds 0
    none = torch.zeros(8, 2)
    assert Ft.masked_loss(out, r, c, none).item() == 0.0  # not NaN from dividing by zero
    half = both.clone()
    half[:4, 0] = 0  # the first four roads have no rate label
    expected = (out[4:, 0] - r[4:]).abs().mean() + nn.functional.binary_cross_entropy_with_logits(out[:, 1], c)
    assert torch.isclose(Ft.masked_loss(out, r, c, half), expected)
    garbage_r = r.clone()
    garbage_r[:4] = 1e6  # what sits in a masked slot must not matter
    assert torch.isclose(Ft.masked_loss(out, garbage_r, c, half), expected)


def test_f2_the_loss_and_settings_equal_the_landed_training_script():
    torch.manual_seed(1)
    o, r, c = torch.randn(16, 2), torch.rand(16) * 3, (torch.rand(16) > 0.6).float()
    m = (torch.rand(16, 2) > 0.3).float()
    landed = ((o[:, 0] - r).abs() * m[:, 0]).sum() / m[:, 0].sum().clamp(min=1) \
        + (nn.functional.binary_cross_entropy_with_logits(o[:, 1], c, reduction="none")
           * m[:, 1]).sum() / m[:, 1].sum().clamp(min=1)  # train_vit.py lines 110 to 112, copied
    assert torch.equal(Ft.masked_loss(o, r, c, m), landed)
    source = (ROOT / "src" / "model" / "train_vit.py").read_text()
    for piece in ("((o[:, 0] - r).abs() * m[:, 0]).sum() / m[:, 0].sum().clamp(min=1)",
                  'binary_cross_entropy_with_logits(o[:, 1], c, reduction="none")',
                  '{"params": net.b.parameters(), "lr": 2e-5}', '{"params": net.h.parameters(), "lr": 1e-3}',
                  "weight_decay=0.05", "def loader(ds, shuffle, bs=128)", "drop_last=shuffle",
                  "[:3, 1:127, 1:127]"):
        assert piece in source, f"train_vit.py no longer contains: {piece}"
    assert (Ft.LR_BACKBONE, Ft.LR_HEAD, Ft.WEIGHT_DECAY, Ft.BATCH) == (2e-5, 1e-3, 0.05, 128)


# ---------------------------------------------------------------- arms (F3, F4)

def test_f3_changes_applied_none_zero_flips_and_full_above_zero(data):
    assert fit(data, "none")["ops_applied"] == [0, 0]
    flips, full = fit(data, "flips")["ops_applied"], fit(data, "full")["ops_applied"]
    assert all(n > 0 for n in flips) and all(n > 0 for n in full)
    assert sum(full) > sum(flips)  # flips changes at most one thing per sample; full up to four


def test_f4_arm_settings_differ_only_in_the_preset():
    cfgs = {arm: Ft.arm_config(arm, 0) for arm in Ft.ARMS}
    assert Ft.ARMS == ("none", "flips", "full") and set(A.PRESETS) == set(Ft.ARMS)
    for a in Ft.ARMS:
        for b in Ft.ARMS:
            assert {k for k in cfgs[a] if cfgs[a][k] != cfgs[b][k]} <= {"preset"}
    assert cfgs["none"]["preset"] == "none" and cfgs["full"]["epochs"] == 6 and cfgs["full"]["batch_size"] == 128
    with pytest.raises(ValueError, match="unknown arm"):
        Ft.arm_config("mixup", 0)


# ---------------------------------------------------------------- folds (F5, F16)

def test_f5_training_never_touches_the_held_out_fold(data, monkeypatch):
    d, chips = data
    seen = {}

    class Spy(V.ViewDataset):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            seen["rows"] = self.rows.copy()

    monkeypatch.setattr(V, "ViewDataset", Spy)
    for k in range(5):
        res = fit(data, "full", k=k, epochs=1)
        train_rows = seen["rows"]
        assert (d.fold.values[train_rows] != k).all() and (d.fold.values[res["rows"]] == k).all()
        assert not set(d.split_block.values[train_rows]) & set(d.split_block.values[res["rows"]])
        assert len(res["rows"]) == int((d.fold == k).sum())  # every road in the fold is scored, labelled or not
        labelled = d.y_rate.notna() | d.y_crack.notna()
        assert res["n_train"] == len(train_rows) == int((labelled & (d.fold != k)).sum())


def test_f5b_unusable_roads_are_neither_trained_on_nor_scored(data):
    d, _ = data
    usable = np.ones(len(d), dtype=bool)
    usable[np.where(d.fold.values == 0)[0][:3]] = False
    usable[np.where(d.fold.values == 1)[0][:5]] = False
    res = fit(data, "none", epochs=1, usable=usable)
    assert len(res["rows"]) == int((d.fold == 0).sum()) - 3 and usable[res["rows"]].all()


def test_f16_a_fold_too_small_for_one_batch_is_refused_and_a_stepless_epoch_raises(data, monkeypatch):
    d, chips = data
    with pytest.raises(ValueError, match="fewer than one batch"):
        Ft.train_fold(d, chips, 0, small_cfg(batch_size=10_000), tiny_net_factory, workers=0, log=QUIET)
    empty_fold = d[d.fold != 4].reset_index(drop=True)
    with pytest.raises(ValueError, match="no held-out roads"):
        Ft.train_fold(empty_fold, chips[(d.fold != 4).values], 4, small_cfg(), tiny_net_factory, workers=0, log=QUIET)
    monkeypatch.setattr(torch.utils.data, "DataLoader", lambda *a, **k: iter(()))
    with pytest.raises(RuntimeError, match="no optimiser step"):
        fit(data, "none", epochs=1)


# ---------------------------------------------------------------- training behaviour (F6 to F10)

class Capture:
    """A factory that keeps the net it built and a copy of its starting weights."""

    def __init__(self, make=tiny_net_factory):
        self.make = make

    def __call__(self):
        self.net = self.make()
        self.start = copy.deepcopy(self.net.state_dict())
        return self.net


def test_f6_the_saved_predictions_come_from_the_last_epoch(data, monkeypatch):
    calls, real = [], Ft.predict_views

    def spy(net, chips, rows, view_ids=(0,), batch=512):
        out = real(net, chips, rows, view_ids, batch)
        calls.append((V.weights_hash(net), tuple(view_ids), out.copy()))
        return out

    monkeypatch.setattr(Ft, "predict_views", spy)
    res = fit(data, "full", epochs=3)
    hashes = [c[0] for c in calls]
    assert [c[1] for c in calls] == [(0,), (0,), (0,), (0,), tuple(range(8))]  # one per epoch, then the two final ones
    assert len(set(hashes[:3])) == 3                    # the weights moved every epoch
    assert hashes[3] == hashes[4] == hashes[2]          # the final scores use the last epoch's weights
    assert np.array_equal(res["pred"], calls[3][2]) and np.array_equal(res["pred_8v"], calls[4][2])
    assert not np.array_equal(res["pred"], calls[0][2])  # not the first epoch's
    assert len(res["history"]) == 3 and set(res["history"][0]) == {"rate_mae", "rate_spearman", "crack_aucpr"}


def nan_factory():
    net = tiny_net_factory()
    with torch.no_grad():
        net.h.bias.fill_(float("nan"))
    return net


def test_f7_a_nan_loss_raises_and_writes_nothing(data, tmp_path):
    d, chips = data
    ctx = {"out_root": tmp_path / "vision", "hashes": {"code": "c", "table": "t", "manifest": "m", "weights": "w"},
           "net_factory": nan_factory}
    with pytest.raises(RuntimeError, match="the loss is nan"):
        Ft.run_job(d, chips, None, "full", 0, 0, ctx, epochs=1, batch_size=8, workers=0, log=QUIET)
    assert not list((tmp_path / "vision").rglob("*")) if (tmp_path / "vision").exists() else True


def test_f8_one_epoch_changes_both_the_backbone_and_the_head(data):
    cap = Capture()
    fit(data, "none", epochs=1, factory=cap)
    end = cap.net.state_dict()
    backbone = [k for k in end if k.startswith("b.")]
    head = [k for k in end if k.startswith("h.")]
    assert backbone and head
    assert any(not torch.equal(end[k], cap.start[k]) for k in backbone), "the backbone is frozen"
    assert all(not torch.equal(end[k], cap.start[k]) for k in head)


def train_loss(net, d, chips, rows):
    ds = V.ViewDataset(chips, d.y_rate.values, d.y_crack.values, rows=rows)
    x, r, c, m, _, _ = (torch.stack(t) for t in zip(*[ds[i] for i in range(len(ds))]))
    net.eval()
    with torch.no_grad():
        return float(Ft.masked_loss(net(x).float(), r, c, m))


def test_f9_the_loop_drives_the_loss_down_on_32_samples():
    d = make_table(n_blocks=10, per_block=8, seed=5)
    chips = chips_for(d)
    keep = np.concatenate([np.where((d.fold.values != 0) & d.y_rate.notna().values)[0][:32],
                           np.where(d.fold.values == 0)[0][:8]])
    d32, c32 = d.iloc[keep].reset_index(drop=True), chips[keep]
    train_rows = np.where(d32.fold.values != 0)[0]
    assert len(train_rows) == 32
    cap = Capture()
    cfg = {**small_cfg("none", 0, epochs=150, batch_size=8), "lr_head": 1e-2, "lr_backbone": 1e-3}
    res = Ft.train_fold(d32, c32, 0, cfg, cap, workers=0, log=QUIET)
    assert res["steps"] == [4] * 150  # 32 samples in batches of 8: steps really happened
    start_net = tiny_net_factory()
    start_net.load_state_dict(cap.start)
    before, after = train_loss(start_net, d32, c32, train_rows), train_loss(cap.net, d32, c32, train_rows)
    assert after < 0.2 * before, f"loss went from {before:.3f} to {after:.3f}"


def test_f10_the_same_seed_repeats_and_another_seed_differs(data):
    a, b, c = fit(data, "full", seed=0), fit(data, "full", seed=0), fit(data, "full", seed=1)
    assert np.array_equal(a["pred"], b["pred"]) and np.array_equal(a["pred_8v"], b["pred_8v"])
    assert a["ops_applied"] == b["ops_applied"]
    assert not np.array_equal(a["pred"], c["pred"])


# ---------------------------------------------------------------- view averaging at scoring time (F11)

def test_f11_the_8_view_prediction_is_the_mean_of_the_view_predictions(data):
    d, chips = data
    torch.manual_seed(0)
    net = tiny_net_factory()
    rows = np.arange(6)
    avg = Ft.predict_views(net, chips, rows, tuple(range(8)))
    each = np.stack([Ft.predict_views(net, chips, rows, (k,)) for k in range(8)])
    assert avg.shape == (6, 2) and np.allclose(avg, each.mean(axis=0), atol=1e-5)
    assert np.abs(avg - each[0]).max() > 1e-4  # averaging changes the answer (an untrained net: small, not zero)
    assert np.allclose(Ft.predict_views(net, chips, rows, (0,)), each[0])
    turned = np.stack([A.view(chips[i], 3) for i in rows])
    assert np.allclose(Ft.predict_views(net, turned, rows, tuple(range(8))), avg, atol=1e-5)
    assert np.allclose(Ft.predict_views(net, chips, rows, tuple(range(8)), batch=4), avg, atol=1e-5)


# ---------------------------------------------------------------- schedule and budget (F13, F17)

def test_f17_the_reduced_schedule_keeps_seed_0_everywhere():
    full, reduced = Ft.full_schedule(), Ft.reduced_schedule()
    assert len(full) == 30 and len(set(full)) == 30
    assert {(a, f) for a, s, f in full if s == 0} == {(a, f) for a in Ft.ARMS for f in range(5)}
    assert {(a, f) for a, s, f in reduced if s == 0} == {(a, f) for a in Ft.ARMS for f in range(5)}
    assert sorted(j for j in reduced if j[1] == 1) == sorted((a, 1, 0) for a in Ft.ARMS)
    assert len(reduced) == 18


def test_f13_the_schedule_must_fit_the_time_and_money_left():
    per_job_min = 1.2 * (3 + 6 * 35 + 20 + 1) / 60  # 4.68 minutes
    assert Ft.job_seconds(TIMING) / 60 == pytest.approx(per_job_min)
    full_min = 31 * per_job_min + 5       # 150.1 minutes: 30 jobs, the control, the report
    reduced_min = 19 * per_job_min + 5    # 93.9 minutes
    roomy = Ft.plan_grid(TIMING, dph=1.0, cap_left=10.0, minutes_left=full_min + 21)
    assert roomy["schedule"] == "full" and len(roomy["jobs"]) == 30 and roomy["minutes"] == pytest.approx(full_min)
    assert roomy["cost"] == pytest.approx(full_min / 60)
    # the 20-minute reserve for copying results and teardown is kept back
    tight = Ft.plan_grid(TIMING, dph=1.0, cap_left=10.0, minutes_left=full_min + 19)
    assert tight["schedule"] == "reduced" and len(tight["jobs"]) == 18
    # money binds as well as time
    poor = Ft.plan_grid(TIMING, dph=1.0, cap_left=full_min / 60 - 0.01, minutes_left=600)
    assert poor["schedule"] == "reduced"
    with pytest.raises(ValueError, match="no schedule fits"):
        Ft.plan_grid(TIMING, dph=1.0, cap_left=10.0, minutes_left=reduced_min + 19)
    with pytest.raises(ValueError, match="no schedule fits"):
        Ft.plan_grid(TIMING, dph=1.0, cap_left=reduced_min / 60 - 0.01, minutes_left=600)
    with pytest.raises(ValueError, match="timing lacks"):
        Ft.plan_grid({"train_epoch_s": 30.0}, 1.0, 10.0, 600)
    # every part of a job is in the estimate: leaving out scoring would understate it
    assert Ft.job_seconds({**TIMING, "score_epoch_s": 0.0, "tta_s": 0.0}) < Ft.job_seconds(TIMING)


def test_f14_a_flood_target_is_refused():
    assert Ft.parse_targets("rate,crack") == ("rate", "crack")
    for bad in ("rate,crack,flood", "flood", "rate"):
        with pytest.raises(ValueError, match="two outputs"):
            Ft.parse_targets(bad)


# ---------------------------------------------------------------- the whole runner (F12, F17 to F19, E15)

@pytest.fixture(scope="module")
def grid(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("grid")
    d = make_table(n_blocks=30, per_block=12, seed=4)
    processed, cdir, out = tmp / "processed", tmp / "chips", tmp / "vision"
    processed.mkdir(), cdir.mkdir()
    d.to_parquet(processed / "segments_targets.parquet")
    chips = chips_for(d)
    chips[7, :, :40, :] = 0  # one blank chip
    for seg_id, c in zip(d.seg_id, chips):
        np.save(cdir / chip_path(seg_id).name, c)
    base = ["--processed", str(processed), "--chips", str(cdir), "--out", str(out), "--epochs", "1", "--batch", "8",
            "--workers", "0", "--boot", "30"]
    frozen = Fz.main(processed, cdir, out, net_factory=lambda: (torch.manual_seed(0), tiny_net_factory())[1],
                     n_boot=30, log=QUIET)
    frozen_files = {p: p.read_bytes() for p in (out / "frozen").iterdir()}
    jobs = tmp / "jobs.json"
    jobs.write_text(json.dumps([list(j) for j in Ft.reduced_schedule()]))
    outcomes = Ft.main(base + ["--jobs", str(jobs)], net_factory=tiny_net_factory, log=QUIET)
    Ft.main(base + ["--shuffled-control"], net_factory=tiny_net_factory, log=QUIET)
    results = Ft.main(base + ["--report"], net_factory=tiny_net_factory, log=QUIET)
    return {"d": d, "out": out, "base": base, "jobs": jobs, "outcomes": outcomes, "results": results, "frozen": frozen,
            "frozen_files": frozen_files, "tmp": tmp}


def test_f17b_the_runner_executes_exactly_the_jobs_listed(grid):
    assert grid["outcomes"] == ["ran"] * 18
    done = sorted(p.relative_to(grid["out"] / "finetune").as_posix()
                  for p in (grid["out"] / "finetune").rglob("*.done.json") if "control" not in p.parts)
    expected = sorted(f"{a}/seed{s}/fold{f}.done.json" for a, s, f in Ft.reduced_schedule())
    assert done == expected


def test_f12_outputs_columns_one_row_per_road_and_fingerprints(grid):
    d, out = grid["d"], grid["out"]
    for arm in Ft.ARMS:
        oof = pd.read_parquet(out / "finetune" / f"oof_{arm}.parquet")
        assert list(oof.columns) == ["seg_id", "fold", "im_vit_rate", "im_vit_crack", "im_vit_rate_8v", "im_vit_crack_8v"]
        assert len(oof) == len(d) - 1 and not oof.seg_id.duplicated().any()  # every road but the blank one, once
        assert d.seg_id[7] not in set(oof.seg_id) and oof.notna().all().all()
        assert (oof.set_index("seg_id").fold == d.set_index("seg_id").fold.loc[oof.seg_id]).all()
        for fold in range(5):
            part = pd.read_parquet(out / "finetune" / arm / "seed0" / f"fold{fold}.parquet")
            assert (part.fold == fold).all()  # a fold's predictions come from the model that held it out
    rec = json.loads((out / "finetune" / "full" / "seed0" / "fold2.done.json").read_text())
    assert rec["config"] == {**Ft.arm_config("full", 0, 1, 8), "fold": 2}
    assert set(rec["hashes"]) == {"code", "table", "manifest", "weights"} and all(len(h) == 64 for h in rec["hashes"].values())
    f = out / "finetune" / "full" / "seed0" / "fold2.parquet"
    assert rec["files"] == {"fold2.parquet": {"size": f.stat().st_size, "sha256": V.file_sha256(f)}}
    assert set(rec["timing"]) == set(Ft.TIMING_PARTS) and all(v >= 0 for v in rec["timing"].values())
    assert rec["hashes"]["code"] == V.code_hash() and rec["n_scored"] > 0 and rec["steps"][0] > 0
    produced = [p for p in grid["tmp"].rglob("*") if p.is_file() and p.suffix in {".parquet", ".json", ".md", ".npy"}
                and "vision" not in p.parts and p.parent.name not in {"chips", "processed"} and p.name != "jobs.json"]
    assert not produced and not list(out.rglob("*.tmp"))  # nothing written outside the output root


def test_report_tables_differences_and_control(grid):
    r = grid["results"]
    assert list(r["arms"]) == ["none", "none+8view", "flips", "flips+8view", "full", "full+8view"]
    assert len(r["differences"]) == 5 * 3 and {x["vs"] for x in r["differences"]} == {"none"}
    assert r["counts"]["changes_applied_none"] == 0  # AC6
    assert r["counts"]["changes_applied_flips"] > 0 and r["counts"]["changes_applied_full"] > 0
    assert r["counts"]["segments_compared"] == len(grid["d"]) - 1
    assert "shuffled labels, full, fold 0" in r["controls"]
    assert r["hashes"] == json.loads((grid["out"] / "finetune" / "none" / "seed0" / "fold0.done.json").read_text())["hashes"]
    saved = json.loads((grid["out"] / "finetune" / "metrics.json").read_text())
    report = (grid["out"] / "finetune" / "report.md").read_text()

    def leaves(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from leaves(v)
        elif isinstance(o, list):
            for v in o:
                yield from leaves(v)
        elif isinstance(o, float) and not math.isnan(o):
            yield round(o, 4)

    printed = M.report_numbers(report)
    assert len(printed) > 60 and set(round(p, 4) for p in printed) <= set(leaves(saved))
    assert "Held-out score after each epoch" in report and "| none+8view |" in report


def test_f18_the_seed_spread_uses_matched_runs_only(grid):
    spread = Ft.matched_seed_spread(grid["out"], "rate_mae")
    assert spread["folds"] == [0] and spread["n_pairs"] == 3  # seed 1 ran on fold 0 only, for the three arms
    a = json.loads((grid["out"] / "finetune" / "none" / "seed0" / "fold0.done.json").read_text())["scores"]["1view"]
    b = json.loads((grid["out"] / "finetune" / "none" / "seed1" / "fold0.done.json").read_text())["scores"]["1view"]
    assert spread["spread"] >= abs(a["rate_mae"] - b["rate_mae"]) - 1e-12
    assert grid["results"]["seed_spread"]["rate_mae"] == spread
    assert all(x["seed_spread"] == grid["results"]["seed_spread"][x["metric"]]["spread"] for x in grid["results"]["differences"])


def test_f19_resume_skips_only_a_job_whose_completion_record_validates(grid):
    out = grid["out"]
    parquet, done = Ft.job_paths(out, "flips", 0, 3)
    rec = json.loads(done.read_text())
    expected = Ft.job_record(Ft.arm_config("flips", 0, 1, 8), 3, rec["hashes"])
    assert Ft.job_is_complete(done, expected)
    assert not Ft.job_is_complete(done, Ft.job_record(Ft.arm_config("flips", 0, 2, 8), 3, rec["hashes"]))   # epochs
    assert not Ft.job_is_complete(done, Ft.job_record(Ft.arm_config("flips", 0, 1, 16), 3, rec["hashes"]))  # batch
    assert not Ft.job_is_complete(done, Ft.job_record(Ft.arm_config("full", 0, 1, 8), 3, rec["hashes"]))    # arm
    shuffled = {**Ft.arm_config("flips", 0, 1, 8), "shuffle_labels": True}
    assert not Ft.job_is_complete(done, Ft.job_record(shuffled, 3, rec["hashes"]))
    for key in ("code", "table", "manifest", "weights"):
        assert not Ft.job_is_complete(done, Ft.job_record(Ft.arm_config("flips", 0, 1, 8), 3, {**rec["hashes"], key: "x"}))
    assert not Ft.job_is_complete(out / "finetune" / "flips" / "seed0" / "fold9.done.json", expected)  # no record
    original = parquet.read_bytes()
    try:
        parquet.write_bytes(original + b"x")
        assert not Ft.job_is_complete(done, expected)  # altered
        parquet.unlink()
        assert not Ft.job_is_complete(done, expected)  # missing
    finally:
        parquet.write_bytes(original)
    done_text = done.read_text()
    try:
        done.write_text("{ not json")
        assert not Ft.job_is_complete(done, expected)
    finally:
        done.write_text(done_text)
    assert Ft.job_is_complete(done, expected)
    # rerunning the same job list skips everything; a new job in the list runs
    again = Ft.main(grid["base"] + ["--jobs", str(grid["jobs"])], net_factory=tiny_net_factory, log=QUIET)
    assert again == ["skipped"] * 18
    extra = grid["tmp"] / "extra.json"
    extra.write_text(json.dumps([["none", 0, 0], ["none", 1, 1]]))
    assert Ft.main(grid["base"] + ["--jobs", str(extra)], net_factory=tiny_net_factory, log=QUIET) == ["skipped", "ran"]


def test_e15_frozen_and_fine_tune_results_do_not_overwrite_each_other(grid):
    out = grid["out"]
    for path, content in grid["frozen_files"].items():
        assert path.read_bytes() == content, f"{path.name} changed after the fine-tune stage"
    for folder in ("frozen", "finetune"):
        assert (out / folder / "metrics.json").exists() and (out / folder / "report.md").exists()
    assert json.loads((out / "frozen" / "metrics.json").read_text())["kind"] == "frozen"
    assert json.loads((out / "finetune" / "metrics.json").read_text())["kind"] == "finetune"
    M.compare(grid["frozen"], grid["results"])  # same roads, code and labels: the two stages are comparable


def test_report_refuses_a_missing_fold(grid, tmp_path):
    d = grid["d"]
    usable = np.ones(len(d), dtype=bool)
    with pytest.raises(ValueError, match="missing fold 0"):
        Ft.report(d, usable, {"out_root": tmp_path, "hashes": {}}, n_boot=5, log=QUIET)


def test_time_only_writes_timing_and_no_results(grid):
    timing = Ft.main(grid["base"][:6] + ["--batch", "8", "--workers", "0", "--time-only"],
                     net_factory=tiny_net_factory, log=QUIET)
    assert set(Ft.TIMING_PARTS) <= set(timing) and timing["n_train"] > 0
    saved = json.loads((grid["out"] / "finetune" / "timing.json").read_text())
    assert saved["train_epoch_s"] == timing["train_epoch_s"]
    Ft.plan_grid(saved, dph=0.87, cap_left=14.0, minutes_left=400)  # the timing file feeds the planner as is


# ---------------------------------------------------------------- the real model (F15, GPU box only)

@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs the cloud GPU box")
def test_f15_the_real_model_learns_32_real_chips_and_reports_its_timing():
    files = sorted(glob.glob(str(REAL_CHIPS / "*.npy")))[:40]
    assert len(files) == 40, "need 40 chips on the box"
    chips = np.stack([np.load(f) for f in files])
    brightness = chips[:, :3].mean(axis=(1, 2, 3))
    d = pd.DataFrame({"seg_id": [Path(f).stem for f in files], "fold": [1] * 32 + [0] * 8,
                      "y_rate": (brightness - brightness.mean()) / brightness.std() + 2.0,
                      "y_crack": (brightness > np.median(brightness)).astype(float)})
    cap = Capture(Ft.default_net)
    res = Ft.train_fold(d, chips, 0, Ft.arm_config("none", 0, epochs=30, batch_size=8), cap, workers=0, log=QUIET)
    assert res["steps"] == [4] * 30 and next(cap.net.parameters()).device.type == "cuda"
    start = Ft.default_net()
    start.load_state_dict(cap.start)
    rows = np.arange(32)
    ds = V.ViewDataset(chips, d.y_rate.values, d.y_crack.values, rows=rows)
    x, r, c, m, _, _ = (torch.stack(t).cuda() for t in zip(*[ds[i] for i in range(32)]))

    def loss_of(net):
        net.eval()
        with torch.no_grad():
            return float(Ft.masked_loss(net(x).float(), r, c, m))

    before, after = loss_of(start), loss_of(cap.net)
    assert after < 0.6 * before, f"loss went from {before:.3f} to {after:.3f}"
    assert set(res["timing"]) >= {"startup_s", "train_epoch_s", "score_epoch_s", "tta_s"}
    assert all(res["timing"][k] > 0 for k in ("train_epoch_s", "score_epoch_s", "tta_s"))
