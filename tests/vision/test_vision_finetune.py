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
TIMING = {"load_s": 60.0, "startup_s": 3.0, "train_epoch_s": 30.0, "score_epoch_s": 5.0, "tta_s": 20.0, "write_s": 1.0}


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


def test_f4b_what_training_actually_does_differs_between_arms_only_in_the_changes_applied(data, monkeypatch):
    seen = {}
    real_adamw, real_loader = torch.optim.AdamW, torch.utils.data.DataLoader

    def spy_adamw(groups, **kw):
        seen["optim"] = ([g["lr"] for g in groups], kw)
        return real_adamw(groups, **kw)

    def spy_loader(ds, batch_size, **kw):
        seen.setdefault("loader", []).append((batch_size, kw["shuffle"], kw["drop_last"],
                                              kw["generator"].initial_seed(), tuple(ds.rows)))
        return real_loader(ds, batch_size, **kw)

    monkeypatch.setattr(torch.optim, "AdamW", spy_adamw)
    monkeypatch.setattr(torch.utils.data, "DataLoader", spy_loader)
    runs = {}
    for arm in Ft.ARMS:
        seen.clear()
        res = fit(data, arm, seed=3, epochs=2)
        runs[arm] = (seen["optim"], seen["loader"], res["start_weights"], res["steps"], res["n_train"], tuple(res["rows"]))
    assert runs["none"] == runs["flips"] == runs["full"]  # optimiser, batches, order, rows, starting weights, steps
    assert runs["none"][0] == ([2e-5, 1e-3], {"weight_decay": 0.05})
    assert [b[:4] for b in runs["none"][1]] == [(8, True, True, 3000), (8, True, True, 3001)]


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
    res = fit(data, "none", epochs=1, factory=cap)
    end = cap.net.state_dict()
    backbone = [k for k in end if k.startswith("b.")]
    head = [k for k in end if k.startswith("h.")]
    assert backbone and head
    assert any(not torch.equal(end[k], cap.start[k]) for k in backbone), "the backbone is frozen"
    assert all(not torch.equal(end[k], cap.start[k]) for k in head)
    # the run measures the same thing itself, so a report can prove the backbone trained
    num = sum(float(((end[k] - cap.start[k]) ** 2).sum()) for k in backbone)
    den = sum(float((cap.start[k] ** 2).sum()) for k in backbone)
    assert res["backbone_change"] == pytest.approx((num / den) ** 0.5, rel=1e-4) and res["backbone_change"] > 0


def frozen_backbone_factory():
    net = tiny_net_factory()
    for p in net.b.parameters():
        p.requires_grad_(False)  # what lost gradients look like: the head learns, the backbone never moves
    return net


def test_f8b_a_backbone_that_does_not_move_is_measured_as_zero_and_voids_the_report(data, tmp_path):
    res = fit(data, "full", epochs=1, factory=frozen_backbone_factory)
    assert res["backbone_change"] == 0.0
    d, processed, cdir, out, base = build_inputs(tmp_path, seed=11)
    jobs = write_jobs(tmp_path / "jobs.json", [(a, 0, f) for a in Ft.ARMS for f in range(5)])
    with pytest.raises(ValueError, match="the backbone did not change in training"):
        Ft.main(base + ["--jobs", jobs, "--shuffled-control", "--report"], net_factory=frozen_backbone_factory, log=QUIET)
    assert not (out / "finetune" / "report.md").exists()


def test_the_gradient_scaler_is_off_on_cpu_and_on_for_cuda():
    cpu = Ft.grad_scaler(torch.device("cpu"))
    assert cpu.is_enabled() is False
    w = torch.nn.Parameter(torch.tensor([1.0]))
    opt = torch.optim.SGD([w], lr=0.5)
    loss = (w * 3).sum()
    cpu.scale(loss).backward()  # with the scaler off these three calls are a plain backward and step
    cpu.step(opt)
    cpu.update()
    assert w.item() == pytest.approx(1.0 - 0.5 * 3)
    if torch.cuda.is_available():
        assert Ft.grad_scaler(torch.device("cuda")).is_enabled() is True


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
    load_min = 1.2 * 60 / 60                           # the chips are loaded once
    full_min = load_min + 31 * per_job_min + 10        # 30 jobs, the control, the report
    reduced_min = load_min + 19 * per_job_min + 10
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
    # every part of a job is in the estimate: leaving any of them out would understate it
    for part in Ft.TIMING_PARTS:
        shorter = Ft.plan_grid({**TIMING, part: 0.0}, 1.0, 100.0, 6000)["minutes"]
        assert shorter < Ft.plan_grid(TIMING, 1.0, 100.0, 6000)["minutes"], part
    assert Ft.REPORT_MIN == 10.0


def test_f14_a_flood_target_is_refused():
    assert Ft.parse_targets("rate,crack") == ("rate", "crack")
    for bad in ("rate,crack,flood", "flood", "rate"):
        with pytest.raises(ValueError, match="two outputs"):
            Ft.parse_targets(bad)


# ---------------------------------------------------------------- the whole runner (F12, F17 to F19, E15)

def build_inputs(tmp, seed=4):
    d = make_table(n_blocks=30, per_block=12, seed=seed)
    processed, cdir, out = tmp / "processed", tmp / "chips", tmp / "vision"
    processed.mkdir(), cdir.mkdir()
    d.to_parquet(processed / "segments_targets.parquet")
    chips = chips_for(d)
    chips[7, :, :40, :] = 0  # one blank chip
    for seg_id, c in zip(d.seg_id, chips):
        np.save(cdir / chip_path(seg_id).name, c)
    base = ["--processed", str(processed), "--chips", str(cdir), "--out", str(out), "--epochs", "1", "--batch", "8",
            "--workers", "0", "--boot", "30"]
    return d, processed, cdir, out, base


def write_jobs(path, jobs):
    path.write_text(json.dumps([list(j) for j in jobs]))
    return str(path)


@pytest.fixture(scope="module")
def grid(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("grid")
    d, processed, cdir, out, base = build_inputs(tmp)
    frozen = Fz.main(processed, cdir, out, net_factory=lambda: (torch.manual_seed(0), tiny_net_factory())[1],
                     n_boot=30, log=QUIET)
    frozen_files = {p: p.read_bytes() for p in (out / "frozen").iterdir()}
    jobs = write_jobs(tmp / "jobs.json", Ft.reduced_schedule())
    done = Ft.main(base + ["--jobs", jobs, "--shuffled-control", "--report"], net_factory=tiny_net_factory, log=QUIET)
    ctx = {"out_root": out, "hashes": done["report"]["hashes"], "net_factory": tiny_net_factory}
    return {"d": d, "out": out, "base": base, "jobs": jobs, "outcomes": done["jobs"], "control": done["control"],
            "results": done["report"], "frozen": frozen, "frozen_files": frozen_files, "tmp": tmp, "ctx": ctx}


def test_f17b_the_runner_executes_exactly_the_jobs_listed(grid):
    assert grid["outcomes"] == ["ran"] * 18 and grid["control"] == "ran"
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
    assert set(rec["timing"]) == set(Ft.TIMING_PARTS) - {"load_s"} and all(v >= 0 for v in rec["timing"].values())
    assert rec["hashes"]["code"] == V.code_hash() and rec["n_scored"] > 0 and rec["steps"][0] > 0
    assert len(rec["start_weights"]) == 64 and rec["start_weights"] != rec["hashes"]["weights"]
    assert rec["backbone_change"] > 0  # recorded per job: the backbone really was trained
    other_seed = json.loads((out / "finetune" / "full" / "seed1" / "fold0.done.json").read_text())
    same_seed = json.loads((out / "finetune" / "none" / "seed0" / "fold2.done.json").read_text())
    assert rec["start_weights"] == same_seed["start_weights"] != other_seed["start_weights"]  # arms start identical
    produced = [p for p in grid["tmp"].rglob("*") if p.is_file() and p.suffix in {".parquet", ".json", ".md", ".npy"}
                and "vision" not in p.parts and p.parent.name not in {"chips", "processed"} and p.name != "jobs.json"]
    assert not produced and not list(out.rglob("*.tmp"))  # nothing written outside the output root


def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    elif isinstance(o, float) and not math.isnan(o):
        yield round(o, 4)


def test_report_tables_differences_and_control(grid):
    r = grid["results"]
    assert list(r["arms"]) == ["none", "none+8view", "flips", "flips+8view", "full", "full+8view"]
    assert len(r["differences"]) == 5 * 3 and {x["vs"] for x in r["differences"]} == {"none"}
    assert all(x["spread_required"] for x in r["differences"])
    assert r["counts"]["changes_applied_none"] == 0  # AC6
    assert r["counts"]["changes_applied_flips"] > 0 and r["counts"]["changes_applied_full"] > 0
    assert r["counts"]["segments_compared"] == len(grid["d"]) - 1
    control = r["controls"]["shuffled labels, full, fold 0"]
    assert set(control) == {"rate_mae", "rate_spearman", "crack_aucpr", "crack_prevalence", "at_chance"}
    assert control["at_chance"] == (abs(control["rate_spearman"]) < 0.05
                                    and abs(control["crack_aucpr"] - control["crack_prevalence"]) < 0.02)
    assert set(r["reference_by_fold"]["rate_mae_do_nothing"]) == set("01234")
    assert r["hashes"] == json.loads((grid["out"] / "finetune" / "none" / "seed0" / "fold0.done.json").read_text())["hashes"]
    saved = json.loads((grid["out"] / "finetune" / "metrics.json").read_text())
    report = (grid["out"] / "finetune" / "report.md").read_text()
    printed = M.report_numbers(report)
    assert len(printed) > 60 and set(round(p, 4) for p in printed) <= set(leaves(saved))
    assert "Held-out score after each epoch" in report and "| none+8view |" in report
    assert "What the scores are read against, per fold" in report and "at_chance" in report


def test_the_shuffled_control_really_trains_on_permuted_labels(grid, monkeypatch):
    d = grid["d"]
    seen = {}

    def spy(table, chips, fold, cfg, *a, **k):
        seen["table"], seen["cfg"] = table, cfg
        raise RuntimeError("stop here")

    monkeypatch.setattr(Ft, "train_fold", spy)
    usable = np.ones(len(d), dtype=bool)
    ctx = {**grid["ctx"], "out_root": grid["tmp"] / "elsewhere"}
    with pytest.raises(RuntimeError, match="stop here"):
        Ft.run_job(d, None, usable, "full", 0, 0, ctx, 1, 8, control=True, workers=0, log=QUIET)
    t = seen["table"]
    assert seen["cfg"]["shuffle_labels"] is True
    assert not t.y_rate.equals(d.y_rate) and not t.y_crack.equals(d.y_crack)       # the labels moved
    assert sorted(t.y_rate.dropna()) == sorted(d.y_rate.dropna())                  # the same labels, on other roads
    assert (t.y_rate.isna() == d.y_rate.isna()).all() and list(t.seg_id) == list(d.seg_id)
    with pytest.raises(RuntimeError, match="stop here"):
        Ft.run_job(d, None, usable, "full", 0, 0, ctx, 1, 8, control=False, workers=0, log=QUIET)
    assert seen["table"] is d and seen["cfg"]["shuffle_labels"] is False


def test_f18_the_seed_spread_uses_matched_runs_only(grid):
    spread = Ft.matched_seed_spread(grid["ctx"], "rate_mae", 1, 8)
    assert spread["folds"] == [0] and spread["n_pairs"] == 3  # seed 1 ran on fold 0 only, for the three arms
    gaps = []
    for arm in Ft.ARMS:
        a = json.loads((grid["out"] / "finetune" / arm / "seed0" / "fold0.done.json").read_text())["scores"]["1view"]
        b = json.loads((grid["out"] / "finetune" / arm / "seed1" / "fold0.done.json").read_text())["scores"]["1view"]
        gaps.append(abs(a["rate_mae"] - b["rate_mae"]))
    assert spread["spread"] == pytest.approx(max(gaps))
    assert grid["results"]["seed_spread"]["rate_mae"] == spread
    for x in grid["results"]["differences"]:
        s = grid["results"]["seed_spread"][x["metric"]]["spread"]
        assert x["seed_spread"] == s
        assert x["real"] == (M.interval_excludes_zero(x) and abs(x["diff"]) > s)  # must also beat the seed spread


def test_f18b_without_a_second_seed_no_difference_is_called_real(tmp_path):
    d, processed, cdir, out, base = build_inputs(tmp_path, seed=6)
    jobs = write_jobs(tmp_path / "jobs.json", [(a, 0, f) for a in Ft.ARMS for f in range(5)])  # seed 0 only
    r = Ft.main(base + ["--jobs", jobs, "--shuffled-control", "--report"], net_factory=tiny_net_factory, log=QUIET)["report"]
    assert all(math.isnan(s["spread"]) and s["n_pairs"] == 0 for s in r["seed_spread"].values())
    assert not any(x["real"] for x in r["differences"])
    report = (out / "finetune" / "report.md").read_text()
    assert report.count("not judged (no seed spread)") == 15
    assert "| better |" not in report and "| worse |" not in report


def test_report_refuses_stale_damaged_or_missing_inputs(tmp_path):
    d, processed, cdir, out, base = build_inputs(tmp_path, seed=7)
    jobs = write_jobs(tmp_path / "jobs.json", Ft.reduced_schedule())
    with pytest.raises(ValueError, match="missing fold 0"):
        Ft.main(base + ["--report"], net_factory=tiny_net_factory, log=QUIET)
    Ft.main(base + ["--jobs", jobs], net_factory=tiny_net_factory, log=QUIET)
    with pytest.raises(ValueError, match="control has not been run"):
        Ft.main(base + ["--report"], net_factory=tiny_net_factory, log=QUIET)
    Ft.main(base + ["--shuffled-control"], net_factory=tiny_net_factory, log=QUIET)
    ok = Ft.main(base + ["--report"], net_factory=tiny_net_factory, log=QUIET)["report"]
    assert ok["counts"]["changes_applied_none"] == 0

    parquet, done = Ft.job_paths(out, "flips", 0, 2)
    good_record, good_file = done.read_text(), parquet.read_bytes()
    rec = json.loads(good_record)

    def expect_refusal(match="does not match the current"):
        with pytest.raises(ValueError, match=match):
            Ft.main(base + ["--report"], net_factory=tiny_net_factory, log=QUIET)

    for key in ("code", "table", "manifest", "weights"):  # results made from other code, labels, roads or weights
        done.write_text(json.dumps({**rec, "hashes": {**rec["hashes"], key: "0" * 64}}))
        expect_refusal()
    done.write_text(json.dumps({**rec, "config": {**rec["config"], "epochs": 99}}))  # other settings
    expect_refusal()
    done.write_text(good_record)
    table = pd.read_parquet(parquet)
    table["im_vit_rate"] += 100.0  # the predictions were altered after the record was written
    table.to_parquet(parquet, index=False)
    expect_refusal()
    parquet.write_bytes(good_file)
    for malformed in ("[1, 2, 3]", "{ not json", '"just a string"'):  # a record that is not even a record
        done.write_text(malformed)
        expect_refusal("rerun that job, or delete the record")
    done.write_text(good_record)
    Ft.main(base + ["--report"], net_factory=tiny_net_factory, log=QUIET)  # restored: accepted again

    _, seed1 = Ft.job_paths(out, "none", 1, 0)  # a stale seed-1 record must not feed the seed spread
    seed1_text = seed1.read_text()
    seed1.write_text(json.dumps({**json.loads(seed1_text), "hashes": {**rec["hashes"], "code": "0" * 64}}))
    expect_refusal()
    seed1.write_text(seed1_text)
    _, control = Ft.job_paths(out, "full", 0, 0, control=True)
    control.write_text(json.dumps({**json.loads(control.read_text()), "hashes": {**rec["hashes"], "table": "0" * 64}}))
    expect_refusal()


def test_f19_resume_skips_only_a_job_whose_completion_record_validates(grid):
    out = grid["out"]
    parquet, done = Ft.job_paths(out, "flips", 0, 3)
    rec = json.loads(done.read_text())
    expected = Ft.expected_record("flips", 0, 3, rec["hashes"], 1, 8)
    assert Ft.job_is_complete(done, expected)
    assert not Ft.job_is_complete(done, Ft.expected_record("flips", 0, 3, rec["hashes"], 2, 8))   # epochs
    assert not Ft.job_is_complete(done, Ft.expected_record("flips", 0, 3, rec["hashes"], 1, 16))  # batch
    assert not Ft.job_is_complete(done, Ft.expected_record("full", 0, 3, rec["hashes"], 1, 8))    # arm
    assert not Ft.job_is_complete(done, Ft.expected_record("flips", 0, 3, rec["hashes"], 1, 8, control=True))
    for key in ("code", "table", "manifest", "weights"):
        assert not Ft.job_is_complete(done, Ft.expected_record("flips", 0, 3, {**rec["hashes"], key: "x"}, 1, 8))
    assert not Ft.job_is_complete(out / "finetune" / "flips" / "seed0" / "fold9.done.json", expected)  # no record
    original, done_text = parquet.read_bytes(), done.read_text()
    try:
        parquet.write_bytes(original + b"x")
        assert not Ft.job_is_complete(done, expected)  # altered
        parquet.unlink()
        assert not Ft.job_is_complete(done, expected)  # missing
        # a record that vouches for some other file does not vouch for this fold's predictions
        other = parquet.with_name("something_else.parquet")
        other.write_bytes(original)
        done.write_text(json.dumps({**rec, "files": {other.name: rec["files"][parquet.name]}}))
        assert not Ft.job_is_complete(done, expected)
        other.unlink()
        parquet.write_bytes(original)
        for broken in ("{ not json", "[1, 2, 3]", json.dumps({**rec, "files": {parquet.name: {"size": 1}}}),
                       json.dumps({**rec, "files": None}), json.dumps({k: v for k, v in rec.items() if k != "files"})):
            done.write_text(broken)
            assert Ft.job_is_complete(done, expected) is False  # malformed: not complete, and no exception
    finally:
        parquet.write_bytes(original)
        done.write_text(done_text)
    assert Ft.job_is_complete(done, expected)
    # rerunning the same job list skips everything; a new job in the list runs
    again = Ft.main(grid["base"] + ["--jobs", grid["jobs"]], net_factory=tiny_net_factory, log=QUIET)
    assert again == {"jobs": ["skipped"] * 18}
    extra = write_jobs(grid["tmp"] / "extra.json", [("none", 0, 0), ("none", 1, 1)])
    assert Ft.main(grid["base"] + ["--jobs", extra], net_factory=tiny_net_factory, log=QUIET)["jobs"] == ["skipped", "ran"]


def test_e15_frozen_and_fine_tune_results_do_not_overwrite_each_other(grid):
    out = grid["out"]
    for path, content in grid["frozen_files"].items():
        assert path.read_bytes() == content, f"{path.name} changed after the fine-tune stage"
    for folder in ("frozen", "finetune"):
        assert (out / folder / "metrics.json").exists() and (out / folder / "report.md").exists()
    assert json.loads((out / "frozen" / "metrics.json").read_text())["kind"] == "frozen"
    assert json.loads((out / "finetune" / "metrics.json").read_text())["kind"] == "finetune"
    M.compare(grid["frozen"], grid["results"])  # same roads, code and labels: the two stages are comparable


def test_the_report_alone_does_not_load_the_chips(grid, monkeypatch):
    def no_chips(*a, **k):
        raise AssertionError("the report loaded the chips")

    monkeypatch.setattr(V, "load_chips", no_chips)
    again = Ft.main(grid["base"] + ["--report"], net_factory=tiny_net_factory, log=QUIET)["report"]
    assert again["arms"]["full"]["pooled"] == grid["results"]["arms"]["full"]["pooled"]
    assert again["counts"]["segments_compared"] == len(grid["d"]) - 1  # the blank chip is still left out


def test_time_only_times_every_part_and_writes_no_results(grid):
    before = {p: p.stat().st_mtime_ns for p in (grid["out"] / "finetune").rglob("*.done.json")}
    timing = Ft.main(grid["base"][:6] + ["--batch", "8", "--workers", "0", "--time-only"],
                     net_factory=tiny_net_factory, log=QUIET)
    assert set(Ft.TIMING_PARTS) <= set(timing) and timing["n_train"] > 0
    assert all(timing[p] > 0 for p in Ft.TIMING_PARTS)   # each part is measured, none is a constant
    assert timing["write_s"] != 2.0 and (grid["out"] / "finetune" / "timing" / "fold0.parquet").exists()
    saved = json.loads((grid["out"] / "finetune" / "timing.json").read_text())
    assert saved["train_epoch_s"] == timing["train_epoch_s"]
    Ft.plan_grid(saved, dph=0.87, cap_left=14.0, minutes_left=400)  # the timing file feeds the planner as is
    assert {p: p.stat().st_mtime_ns for p in (grid["out"] / "finetune").rglob("*.done.json")} == before
    for clash in (["--report"], ["--shuffled-control"], ["--jobs", grid["jobs"]]):
        with pytest.raises(SystemExit):
            Ft.main(grid["base"] + ["--time-only"] + clash, net_factory=tiny_net_factory, log=QUIET)
    with pytest.raises(SystemExit):
        Ft.main(grid["base"], net_factory=tiny_net_factory, log=QUIET)  # no mode chosen


def test_the_planners_own_output_is_accepted_as_the_job_list(tmp_path):
    d, processed, cdir, out, base = build_inputs(tmp_path, seed=8)
    timing = {"load_s": 1.0, "startup_s": 1.0, "train_epoch_s": 1.0, "score_epoch_s": 1.0, "tta_s": 1.0, "write_s": 1.0}
    plan = Ft.plan_grid(timing, dph=1.0, cap_left=10.0, minutes_left=600)
    plan["jobs"] = plan["jobs"][:2]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))  # the dict plan_grid returns, written as is
    done = Ft.main(base + ["--jobs", str(path)], net_factory=tiny_net_factory, log=QUIET)
    assert done == {"jobs": ["ran", "ran"]}
    assert Ft.job_paths(out, *plan["jobs"][1])[1].exists()


def test_a_stale_record_is_found_before_any_training_and_the_report_never_rewrites_the_chip_index(tmp_path, monkeypatch):
    d, processed, cdir, out, base = build_inputs(tmp_path, seed=9)
    jobs = write_jobs(tmp_path / "jobs.json", Ft.reduced_schedule())
    Ft.main(base + ["--jobs", jobs, "--shuffled-control", "--report"], net_factory=tiny_net_factory, log=QUIET)
    index_before = (out / "chip_index.parquet").read_bytes()

    _, old = Ft.job_paths(out, "flips", 1, 3)  # a seed-1 record left over from an earlier, fuller schedule
    old.parent.mkdir(parents=True, exist_ok=True)
    rec = json.loads(Ft.job_paths(out, "flips", 0, 3)[1].read_text())
    old.write_text(json.dumps({**rec, "hashes": {**rec["hashes"], "code": "0" * 64}}))
    trained = []
    monkeypatch.setattr(Ft, "train_fold", lambda *a, **k: trained.append(1))
    one_more = write_jobs(tmp_path / "more.json", [("none", 1, 1)])
    with pytest.raises(ValueError, match="flips/seed1/fold3.done.json does not match .*different code hash"):
        Ft.main(base + ["--jobs", one_more, "--report"], net_factory=tiny_net_factory, log=QUIET)
    assert trained == []  # refused before the first job, not after an hour of training
    monkeypatch.undo()
    # a stale record that IS about to be redone is not a reason to refuse
    redo = write_jobs(tmp_path / "redo.json", [("flips", 1, 3)])
    assert Ft.main(base + ["--jobs", redo, "--report"], net_factory=tiny_net_factory, log=QUIET)["jobs"] == ["ran"]

    # the report on a machine that holds fewer chips must refuse without touching the saved index
    for f in sorted(cdir.glob("*.npy"))[50:]:
        f.unlink()
    with pytest.raises(ValueError):
        Ft.main(base + ["--report"], net_factory=tiny_net_factory, log=QUIET)
    assert (out / "chip_index.parquet").read_bytes() == index_before


def test_parallel_bootstraps_give_the_sequential_answer():
    rng = np.random.default_rng(0)
    y = rng.normal(size=600)
    blocks = rng.integers(0, 60, size=600)
    tasks = [(blocks, y, y + rng.normal(scale=s, size=600), y + rng.normal(scale=1.0, size=600), m, 40)
             for s, m in ((0.3, "rate_mae"), (0.5, "rate_spearman"), (0.8, "rate_mae"))]
    assert Ft.run_bootstraps(tasks, 2) == Ft.run_bootstraps(tasks, 1) == [M.block_bootstrap_diff(*t) for t in tasks]
    assert Ft.run_bootstraps(tasks[:1], 16) == Ft.run_bootstraps(tasks[:1], 0)  # never more workers than tasks


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
    # under half precision the backbone only learns if its gradients survive: this is the check that they do
    assert res["backbone_change"] > 1e-4, f"the backbone barely moved on the GPU: {res['backbone_change']}"
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
