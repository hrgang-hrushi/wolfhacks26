"""Fine-tune comparison: the landed ViT trained with no augmentation, flips only, or the full set.

    uv run python -m src.model.vision_finetune --time-only          # time one complete job
    uv run python -m src.model.vision_finetune --jobs jobs.json     # run exactly the listed jobs
    uv run python -m src.model.vision_finetune --shuffled-control   # one fold on permuted labels
    uv run python -m src.model.vision_finetune --report             # assemble tables and the report

The model, optimiser, learning rates, batch size and loss are those of src/model/train_vit.py; the
arms differ only in the augmentation preset. Every arm trains a fixed number of epochs and is
scored on its held-out fold after the last one, once with a single view and once averaged over the
8 flips and turns. Everything is written under data/processed/vision/finetune/.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from src.model import augment
from src.model import vision_data as V
from src.model import vision_metrics as M
from src.model.vision_frozen import labels_for, shuffled_labels

ARMS = ("none", "flips", "full")
EPOCHS, BATCH, WORKERS = 6, 128, 16
LR_BACKBONE, LR_HEAD, WEIGHT_DECAY = 2e-5, 1e-3, 0.05  # train_vit.py lines 101 to 102
N_FOLDS = V.N_FOLDS
METRICS = ["rate_mae", "rate_spearman", "crack_aucpr"]
OOF_COLUMNS = ["seg_id", "fold", "im_vit_rate", "im_vit_crack", "im_vit_rate_8v", "im_vit_crack_8v"]
TIMING_PARTS = ("startup_s", "train_epoch_s", "score_epoch_s", "tta_s", "write_s")
REPORT_MIN, SAFETY = 5.0, 1.2


def default_net():
    from src.model import train_vit
    return train_vit.Net().to(train_vit.dev)


def masked_loss(out, r, c, m):
    """L1 on the rate plus binary cross-entropy on cracking, each over its labelled rows (train_vit.py 110 to 112)."""
    return (((out[:, 0] - r).abs() * m[:, 0]).sum() / m[:, 0].sum().clamp(min=1)
            + (F.binary_cross_entropy_with_logits(out[:, 1], c, reduction="none") * m[:, 1]).sum()
            / m[:, 1].sum().clamp(min=1))


def arm_config(arm: str, seed: int, epochs: int = EPOCHS, batch_size: int = BATCH) -> dict:
    """Training settings. Two arms differ in `preset` and in nothing else."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; choose from {ARMS}")
    return {"preset": arm, "seed": int(seed), "epochs": int(epochs), "batch_size": int(batch_size),
            "lr_backbone": LR_BACKBONE, "lr_head": LR_HEAD, "weight_decay": WEIGHT_DECAY, "shuffle_labels": False}


def pretrained_hash(net_factory) -> str:
    """Fingerprint of the backbone the factory hands out (the downloaded weights), taken at a fixed seed."""
    torch.manual_seed(0)
    net = net_factory()
    return V.weights_hash(net.b)


@torch.no_grad()
def predict_views(net, chips, rows, view_ids=(0,), batch: int = 512) -> np.ndarray:
    """Held-out outputs (n, 2) = [rate, cracking logit], averaged over the given views of each chip."""
    net.eval()
    dev = next(net.parameters()).device
    out = np.zeros((len(rows), 2), dtype="float64")
    for start in range(0, len(rows), batch):
        block = [chips[r] for r in rows[start:start + batch]]
        for k in view_ids:
            x = torch.from_numpy(V.to_model_input(np.stack([augment.view(c, k) for c in block]))).to(dev)
            with torch.autocast(dev.type, enabled=dev.type == "cuda"):
                o = net(x)
            out[start:start + len(block)] += o.float().cpu().numpy()
    return (out / len(view_ids)).astype("float32")


def epoch_scores(d, rows, pred) -> dict:
    yr, yc = d.y_rate.values[rows], d.y_crack.values[rows]
    return {"rate_mae": M.mae(yr, pred[:, 0]), "rate_spearman": M.spearman(yr, pred[:, 0]),
            "crack_aucpr": M.aucpr(yc, pred[:, 1])}


def train_fold(d: pd.DataFrame, chips, k: int, cfg: dict, net_factory=None, usable=None, workers: int = WORKERS,
               log=print) -> dict:
    """Train on every usable labelled road outside fold k, then score fold k's usable roads after the last epoch."""
    usable = np.ones(len(d), dtype=bool) if usable is None else np.asarray(usable, dtype=bool)
    fold = d.fold.values
    labelled = d.y_rate.notna().values | d.y_crack.notna().values
    train_rows = np.where(usable & labelled & (fold != k))[0]
    held_rows = np.where(usable & (fold == k))[0]
    if len(train_rows) < cfg["batch_size"]:
        raise ValueError(f"fold {k}: {len(train_rows)} training roads is fewer than one batch of {cfg['batch_size']}")
    if len(held_rows) == 0:
        raise ValueError(f"fold {k}: no held-out roads to score")
    t0 = time.perf_counter()
    torch.manual_seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    net = (net_factory or default_net)()
    dev = next(net.parameters()).device
    opt = torch.optim.AdamW([{"params": net.b.parameters(), "lr": cfg["lr_backbone"]},
                             {"params": net.h.parameters(), "lr": cfg["lr_head"]}], weight_decay=cfg["weight_decay"])
    ds = V.ViewDataset(chips, d.y_rate.values, d.y_crack.values, preset=augment.PRESETS[cfg["preset"]],
                       seed=cfg["seed"], train=True, rows=train_rows)
    timing = {"startup_s": time.perf_counter() - t0, "train_epoch_s": 0.0, "score_epoch_s": 0.0}
    ops_applied, steps, history = [], [], []
    for epoch in range(cfg["epochs"]):
        t1 = time.perf_counter()
        ds.set_epoch(epoch)
        gen = torch.Generator().manual_seed(cfg["seed"] * 1000 + epoch)
        loader = torch.utils.data.DataLoader(ds, cfg["batch_size"], shuffle=True, generator=gen, num_workers=workers,
                                             drop_last=True)
        net.train()
        n_ops = n_steps = 0
        for x, r, c, m, _, ops in loader:
            x, r, c, m = x.to(dev), r.to(dev), c.to(dev), m.to(dev)
            with torch.autocast(dev.type, enabled=dev.type == "cuda"):
                out = net(x).float()
            loss = masked_loss(out, r, c, m)
            if not torch.isfinite(loss):
                raise RuntimeError(f"fold {k} epoch {epoch}: the loss is {loss.item()}; stopping before anything is saved")
            opt.zero_grad()
            loss.backward()
            opt.step()
            n_steps += 1
            n_ops += int(ops.sum())
        if n_steps == 0:
            raise RuntimeError(f"fold {k} epoch {epoch}: no optimiser step was taken")
        t2 = time.perf_counter()
        scores = epoch_scores(d, held_rows, predict_views(net, chips, held_rows, (0,)))
        timing["train_epoch_s"] += (t2 - t1) / cfg["epochs"]
        timing["score_epoch_s"] += (time.perf_counter() - t2) / cfg["epochs"]
        ops_applied.append(n_ops), steps.append(n_steps), history.append(scores)
        log(f"fold {k} {cfg['preset']} seed {cfg['seed']} epoch {epoch}: {n_steps} steps, loss {loss.item():.3f}, "
            + ", ".join(f"{a} {M.fmt(b)}" for a, b in scores.items()))
    t3 = time.perf_counter()
    pred_1 = predict_views(net, chips, held_rows, (0,))  # the last epoch's model, never an earlier one
    pred_8 = predict_views(net, chips, held_rows, tuple(range(augment.N_VIEWS)))
    timing["tta_s"] = time.perf_counter() - t3
    return {"rows": held_rows, "pred": pred_1, "pred_8v": pred_8, "ops_applied": ops_applied, "steps": steps,
            "history": history, "timing": timing, "n_train": int(len(train_rows))}


# ---------------------------------------------------------------- jobs on disk

def job_paths(out_root, arm: str, seed: int, fold: int, control: bool = False):
    base = Path(out_root) / "finetune" / ("control" if control else arm) / f"seed{seed}"
    return base / f"fold{fold}.parquet", base / f"fold{fold}.done.json"


def job_record(cfg: dict, fold: int, hashes: dict) -> dict:
    return {"config": {**cfg, "fold": int(fold)}, "hashes": dict(hashes)}


def job_is_complete(done_path, expected: dict) -> bool:
    """True only if the completion record exists, matches these settings and hashes, and its file is intact."""
    done_path = Path(done_path)
    if not done_path.exists():
        return False
    try:
        rec = json.loads(done_path.read_text())
    except ValueError:
        return False
    if rec.get("config") != expected["config"] or rec.get("hashes") != expected["hashes"]:
        return False
    for name, info in rec.get("files", {}).items():
        f = done_path.parent / name
        if not f.exists() or f.stat().st_size != info["size"] or V.file_sha256(f) != info["sha256"]:
            return False
    return bool(rec.get("files"))


def run_job(d, chips, usable, arm, seed, fold, ctx, epochs=EPOCHS, batch_size=BATCH, control=False, workers=WORKERS,
            log=print) -> str:
    """Train and score one (arm, seed, fold). Returns 'skipped' if a valid completion record already exists."""
    cfg = arm_config(arm, seed, epochs, batch_size)
    cfg["shuffle_labels"] = bool(control)
    parquet, done = job_paths(ctx["out_root"], arm, seed, fold, control)
    expected = job_record(cfg, fold, ctx["hashes"])
    if job_is_complete(done, expected):
        log(f"skip {parquet.parent.parent.name} seed {seed} fold {fold}: already complete")
        return "skipped"
    table = shuffled_labels(d, usable, seed=seed) if control else d
    res = train_fold(table, chips, fold, cfg, ctx["net_factory"], usable, workers, log)
    t0 = time.perf_counter()
    rows = res["rows"]
    oof = pd.DataFrame({"seg_id": d.seg_id.values[rows], "fold": d.fold.values[rows],
                        "im_vit_rate": res["pred"][:, 0], "im_vit_crack": res["pred"][:, 1],
                        "im_vit_rate_8v": res["pred_8v"][:, 0], "im_vit_crack_8v": res["pred_8v"][:, 1]})[OOF_COLUMNS]
    V.atomic_write(parquet, lambda tmp: oof.to_parquet(tmp, index=False), ctx["out_root"])
    res["timing"]["write_s"] = time.perf_counter() - t0
    scores = {"1view": epoch_scores(table, rows, res["pred"]), "8view": epoch_scores(table, rows, res["pred_8v"])}
    record = {**expected, "files": {parquet.name: {"size": parquet.stat().st_size, "sha256": V.file_sha256(parquet)}},
              "ops_applied": res["ops_applied"], "steps": res["steps"], "history": res["history"],
              "timing": res["timing"], "n_train": res["n_train"], "n_scored": int(len(rows)), "scores": scores}
    V.atomic_write(done, lambda tmp: Path(tmp).write_text(json.dumps(record, indent=1)), ctx["out_root"])  # written last
    return "ran"


# ---------------------------------------------------------------- schedule

def full_schedule():
    return [(arm, seed, fold) for seed in (0, 1) for arm in ARMS for fold in range(N_FOLDS)]


def reduced_schedule():
    """Seed 0 for every arm and fold (complete out-of-fold tables), plus seed 1 on fold 0 for each arm."""
    return [(arm, 0, fold) for arm in ARMS for fold in range(N_FOLDS)] + [(arm, 1, 0) for arm in ARMS]


def job_seconds(timing: dict, epochs: int = EPOCHS) -> float:
    return SAFETY * (timing["startup_s"] + epochs * (timing["train_epoch_s"] + timing["score_epoch_s"])
                     + timing["tta_s"] + timing["write_s"])


def plan_grid(timing: dict, dph: float, cap_left: float, minutes_left: float, epochs: int = EPOCHS,
              reserve_min: float = 20.0) -> dict:
    """The largest schedule that fits the time and money left, keeping reserve_min for copying results and teardown."""
    missing = [p for p in TIMING_PARTS if p not in timing]
    if missing:
        raise ValueError(f"timing lacks {missing}")
    per_job = job_seconds(timing, epochs) / 60.0
    tried = []
    for name, jobs in (("full", full_schedule()), ("reduced", reduced_schedule())):
        minutes = (len(jobs) + 1) * per_job + REPORT_MIN  # + 1: the shuffled-label control
        cost = minutes / 60.0 * dph
        tried.append(f"{name}: {minutes:.0f} min, ${cost:.2f}")
        if minutes <= minutes_left - reserve_min and cost <= cap_left:
            return {"schedule": name, "jobs": [list(j) for j in jobs], "minutes": minutes, "cost": cost}
    raise ValueError(f"no schedule fits {minutes_left:.0f} min (less {reserve_min:.0f} reserved) and ${cap_left:.2f}: "
                     + "; ".join(tried))


# ---------------------------------------------------------------- report

def load_done(out_root, arm, seed, fold, control=False):
    parquet, done = job_paths(out_root, arm, seed, fold, control)
    if not done.exists():
        return None, None
    return json.loads(done.read_text()), parquet


def assemble(out_root, arm: str, seed: int = 0) -> pd.DataFrame:
    """The arm's out-of-fold table from its five fold files. Raises if a fold is missing."""
    parts = []
    for fold in range(N_FOLDS):
        rec, parquet = load_done(out_root, arm, seed, fold)
        if rec is None:
            raise ValueError(f"arm {arm} seed {seed} is missing fold {fold}")
        part = pd.read_parquet(parquet)
        if not (part.fold == fold).all():
            raise ValueError(f"arm {arm} seed {seed} fold {fold}: predictions carry another fold")
        parts.append(part)
    out = pd.concat(parts, ignore_index=True)
    if out.seg_id.duplicated().any():
        raise ValueError(f"arm {arm} seed {seed}: a road is predicted more than once")
    return out[OOF_COLUMNS]


def matched_seed_spread(out_root, metric: str) -> dict:
    """Largest seed-0 against seed-1 gap per metric, over arms, on folds that both seeds ran (single-view scores)."""
    gaps, folds_used = [], set()
    for arm in ARMS:
        for fold in range(N_FOLDS):
            a, _ = load_done(out_root, arm, 0, fold)
            b, _ = load_done(out_root, arm, 1, fold)
            if a and b:
                gaps.append(M.seed_spread([a["scores"]["1view"][metric], b["scores"]["1view"][metric]]))
                folds_used.add(fold)
    gaps = [g for g in gaps if not np.isnan(g)]
    return {"spread": float(max(gaps)) if gaps else float("nan"), "folds": sorted(folds_used), "n_pairs": len(gaps)}


def report(d, usable, ctx, n_boot=1000, log=print) -> dict:
    out_root = Path(ctx["out_root"])
    out = out_root / "finetune"
    d_u = d[usable].reset_index(drop=True)
    arms, tables = {}, {}
    for arm in ARMS:
        oof = assemble(out_root, arm, 0)
        V.atomic_write(out / f"oof_{arm}.parquet", lambda tmp, o=oof: o.to_parquet(tmp, index=False), out_root)
        aligned = d_u[["seg_id"]].merge(oof, on="seg_id", how="left", validate="one_to_one")
        if aligned.im_vit_rate.isna().any():
            raise ValueError(f"arm {arm}: {int(aligned.im_vit_rate.isna().sum())} compared roads have no prediction")
        for suffix, name in (("", arm), ("_8v", f"{arm}+8view")):
            tables[name] = pd.DataFrame({"pred_rate": aligned[f"im_vit_rate{suffix}"].values,
                                         "pred_crack": aligned[f"im_vit_crack{suffix}"].values})
    yr, yc, fold = labels_for(d_u, "rate"), labels_for(d_u, "crack"), d_u.fold.values
    col = {"rate_mae": "pred_rate", "rate_spearman": "pred_rate", "crack_aucpr": "pred_crack"}
    y_of = {"rate_mae": yr, "rate_spearman": yr, "crack_aucpr": yc}
    for name, t in tables.items():
        arms[name] = {"pooled": {m: M.METRIC_FNS[m](y_of[m], t[col[m]].values) for m in METRICS},
                      "by_fold": {m: M.by_fold(y_of[m], t[col[m]].values, fold, m) for m in METRICS}}
    spreads = {m: matched_seed_spread(out_root, m) for m in METRICS}
    differences = []
    for name in tables:
        if name == "none":
            continue
        for m in METRICS:
            a, b = tables[name][col[m]].values, tables["none"][col[m]].values
            paired = M.paired_diff(M.by_fold(y_of[m], a, fold, m), M.by_fold(y_of[m], b, fold, m))
            boot = M.block_bootstrap_diff(d_u.split_block.values, y_of[m], a, b, m, n=n_boot)
            differences.append({"arm": name, "vs": "none", "metric": m, **boot, "folds_up": paired["folds_up"],
                                "folds_down": paired["folds_down"], "per_fold": paired["per_fold"],
                                "seed_spread": spreads[m]["spread"], "real": M.is_real(boot, spreads[m]["spread"])})
    counts, epoch_rows = {"segments_compared": int(len(d_u))}, []
    for arm in ARMS:
        recs = [load_done(out_root, arm, 0, f)[0] for f in range(N_FOLDS)]
        counts[f"changes_applied_{arm}"] = int(sum(sum(r["ops_applied"]) for r in recs))
        n_epochs = len(recs[0]["history"])
        for e in range(n_epochs):
            epoch_rows.append([arm, e] + [float(np.nanmean([r["history"][e][m] for r in recs])) for m in METRICS])
    if counts["changes_applied_none"] != 0:
        raise ValueError("the arm without augmentation applied changes; the comparison is void")
    controls = {}
    rec, _ = load_done(out_root, "full", 0, 0, control=True)
    if rec:
        controls["shuffled labels, full, fold 0"] = dict(rec["scores"]["1view"])
    results = {
        "title": "Fine-tune: no augmentation, flips only, full", "kind": "finetune", "metrics": METRICS,
        "hashes": dict(ctx["hashes"]), "counts": counts,
        "reference": {"rate_mae_do_nothing": M.naive_rate_mae(yr, fold),
                      "crack_prevalence": float(np.nanmean(yc)) if (~np.isnan(yc)).any() else float("nan")},
        "arms": arms, "differences": differences, "controls": controls, "skips": [],
        "tables": [{"title": "Held-out score after each epoch (seed 0, mean of the five folds, one view)",
                    "columns": ["Arm", "Epoch"] + [M.METRIC_LABELS[m] for m in METRICS], "rows": epoch_rows}],
        "seed_spread": spreads,
        "notes": ["folds: fold = crc32(split_block) % 5, read from segments_targets.parquet",
                  "arms differ only in the augmentation preset; '+8view' is the same model scored on the average of 8 views",
                  "the last epoch is scored, never the best one; the per-epoch table is for reading only",
                  "a difference is the arm minus 'none'; for the error (MAE) lower is better, for the others higher is better",
                  "seed spread: largest gap between seed 0 and seed 1 on folds both ran: "
                  + ", ".join(f"{m} over folds {s['folds']}" for m, s in spreads.items())],
    }
    V.atomic_write(out / "metrics.json", lambda tmp: Path(tmp).write_text(json.dumps(results, indent=1)), out_root)
    V.atomic_write(out / "report.md", lambda tmp: Path(tmp).write_text(M.render_report(json.loads(json.dumps(results)))),
                   out_root)
    log(f"wrote {out / 'report.md'}")
    return results


# ---------------------------------------------------------------- command line

def load_context(processed=None, chips_dir=None, out_root=None, net_factory=None, log=print):
    out_root = Path(V.OUT_ROOT if out_root is None else out_root)
    net_factory = net_factory or default_net
    code = V.check_shipped_code()
    table = V.load_table(processed)
    d = V.chipped(table, chips_dir)
    d = d[d.has_chip].reset_index(drop=True)
    if len(d) == 0:
        raise ValueError("no segment in the table has a chip")
    chips, blank = V.load_chips(d.seg_id.values, chips_dir)
    usable = V.usable_mask(blank)
    log(f"{len(d):,} segments with a chip, {int(usable.sum()):,} compared ({int((~usable).sum()):,} left out as blank)")
    hashes = {"code": code, "table": V.table_hash(table), "manifest": V.manifest_hash(d.seg_id.values[usable]),
              "weights": pretrained_hash(net_factory)}
    return d, chips, usable, {"out_root": out_root, "hashes": hashes, "net_factory": net_factory}


def parse_targets(text: str):
    targets = tuple(t.strip() for t in text.split(",") if t.strip())
    if set(targets) != {"rate", "crack"}:
        raise ValueError(f"the fine-tune has two outputs, rate and crack; got {targets}. "
                         "A flood output is not part of this model.")
    return targets


def main(argv=None, net_factory=None, log=print):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--time-only", action="store_true")
    mode.add_argument("--jobs", type=Path)
    mode.add_argument("--shuffled-control", action="store_true")
    mode.add_argument("--report", action="store_true")
    ap.add_argument("--targets", default="rate,crack")
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--processed", type=Path, default=None)
    ap.add_argument("--chips", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    parse_targets(a.targets)
    d, chips, usable, ctx = load_context(a.processed, a.chips, a.out, net_factory, log)
    if a.time_only:
        cfg = arm_config("full", 0, 1, a.batch)
        t0 = time.perf_counter()
        res = train_fold(d, chips, 0, cfg, ctx["net_factory"], usable, a.workers, log)
        timing = {**res["timing"], "write_s": 2.0, "wall_s": time.perf_counter() - t0, "n_train": res["n_train"],
                  "n_scored": int(len(res["rows"])), "batch_size": a.batch}
        V.atomic_write(ctx["out_root"] / "finetune" / "timing.json",
                       lambda tmp: Path(tmp).write_text(json.dumps(timing, indent=1)), ctx["out_root"])
        log(json.dumps(timing))
        return timing
    if a.jobs:
        jobs = [tuple(j) for j in json.loads(a.jobs.read_text())]
        outcomes = [run_job(d, chips, usable, arm, int(seed), int(fold), ctx, a.epochs, a.batch, False, a.workers, log)
                    for arm, seed, fold in jobs]
        log(f"{outcomes.count('ran')} jobs ran, {outcomes.count('skipped')} skipped")
        return outcomes
    if a.shuffled_control:
        return run_job(d, chips, usable, "full", 0, 0, ctx, a.epochs, a.batch, True, a.workers, log)
    return report(d, usable, ctx, a.boot, log)


if __name__ == "__main__":
    main()
