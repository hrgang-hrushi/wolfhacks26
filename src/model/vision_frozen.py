"""Frozen-model comparison: read each chip once, or average the embedding over its 8 flips and turns.

    uv run python -m src.model.vision_frozen

Embeds every valid chip with the landed backbone (train_vit.Net, frozen), then scores two arms with a
small probe fitted per fold on the other four folds: `1view` (view 0) and `8view` (mean of the 8
view embeddings). Writes data/processed/vision/frozen/{metrics.json, report.md, oof_*.parquet,
emb_*.npy, index.parquet} and three by-products one level up: ndvi_stats.parquet and two files in
the vit_frozen.parquet format (seg_id, im_emb0..15) covering every chip.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from src.model import augment
from src.model import vision_data as V
from src.model import vision_metrics as M

VIEW_IDS = tuple(range(augment.N_VIEWS))
TARGETS = {"rate": ("y_rate", "pred_rate"), "crack": ("y_crack", "pred_crack"), "flood": ("y_helene_failed", "pred_flood")}
RIDGE_ALPHA, LOGIT_C = 1.0, 1.0


def default_net():
    from src.model import train_vit
    return train_vit.Net().to(train_vit.dev)


def device_of(net) -> torch.device:
    return next(net.parameters()).device


@torch.no_grad()
def embed(net, chips: np.ndarray, view_ids=VIEW_IDS, batch: int = 512) -> np.ndarray:
    """Embeddings of each chip under each view: float32 (N, len(view_ids), D), rows in the order given."""
    net.eval()
    dev = device_of(net)
    out = None
    for start in range(0, len(chips), batch):
        block = chips[start:start + batch]
        for j, k in enumerate(view_ids):
            x = torch.from_numpy(V.to_model_input(np.stack([augment.view(c, k) for c in block]))).to(dev)
            with torch.autocast(dev.type, enabled=dev.type == "cuda"):
                z = net(x, True)
            z = z.float().cpu().numpy()
            if out is None:
                out = np.empty((len(chips), len(view_ids), z.shape[1]), dtype="float32")
            out[start:start + len(block), j] = z
    return out


def target_mask(d: pd.DataFrame, target: str) -> np.ndarray:
    """Rows that carry a label for the target. Flood counts only inside the Helene zone."""
    col = TARGETS[target][0]
    if col not in d.columns:
        return np.zeros(len(d), dtype=bool)
    mask = d[col].notna().to_numpy()
    if target == "flood":
        if "in_helene_zone" not in d.columns:
            return np.zeros(len(d), dtype=bool)
        mask = mask & (d["in_helene_zone"].to_numpy() == 1)
    return mask


def probe(emb: np.ndarray, d: pd.DataFrame, usable=None):
    """Out-of-fold probe predictions for rate, cracking and flood. Returns (DataFrame, list of skipped folds).

    For fold k everything (scaling and the model) is fitted on usable labelled rows of the other
    folds only. A fold is skipped for a target, leaving its predictions NaN, when it has no rows to
    score, no labelled training rows, or one training class for a yes/no target.
    """
    usable = np.ones(len(d), dtype=bool) if usable is None else np.asarray(usable, dtype=bool)
    fold = d.fold.values
    out = pd.DataFrame({"seg_id": d.seg_id.values, "fold": fold})
    skips = []
    for target, (ycol, pcol) in TARGETS.items():
        pred = np.full(len(d), np.nan)
        labelled = target_mask(d, target)
        y = d[ycol].values.astype("float64") if ycol in d.columns else np.full(len(d), np.nan)
        scope = usable & ((d["in_helene_zone"].values == 1) if target == "flood" and "in_helene_zone" in d.columns
                          else np.ones(len(d), dtype=bool))
        if not labelled.any():
            skips.append(f"{target}: no labels")
            out[pcol] = pred
            continue
        for k in sorted(np.unique(fold)):
            tr, te = usable & labelled & (fold != k), scope & (fold == k)
            if not te.any():
                skips.append(f"{target} fold {k}: no rows to score")
            elif not tr.any():
                skips.append(f"{target} fold {k}: no labelled training rows")
            elif target != "rate" and len(np.unique(y[tr])) < 2:
                skips.append(f"{target} fold {k}: one class in training")
            else:
                scaler = StandardScaler().fit(emb[tr])
                if target == "rate":
                    model = Ridge(alpha=RIDGE_ALPHA).fit(scaler.transform(emb[tr]), y[tr])
                    pred[te] = model.predict(scaler.transform(emb[te]))
                else:
                    model = LogisticRegression(C=LOGIT_C, max_iter=1000).fit(scaler.transform(emb[tr]), y[tr])
                    pred[te] = model.predict_proba(scaler.transform(emb[te]))[:, 1]
        out[pcol] = pred
    return out, skips


def labels_for(d: pd.DataFrame, target: str) -> np.ndarray:
    """The target's labels with NaN wherever the row is out of scope, so metrics drop those rows."""
    col = TARGETS[target][0]
    y = d[col].values.astype("float64").copy() if col in d.columns else np.full(len(d), np.nan)
    y[~target_mask(d, target)] = np.nan
    return y


METRIC_TARGET = {"rate_mae": "rate", "rate_spearman": "rate", "crack_aucpr": "crack", "flood_p50": "flood",
                 "flood_aucpr": "flood"}


def score_arm(d: pd.DataFrame, oof: pd.DataFrame, metrics) -> dict:
    pooled, folds = {}, {}
    for m in metrics:
        target = METRIC_TARGET[m]
        y, pred = labels_for(d, target), oof[TARGETS[target][1]].values
        pooled[m] = M.METRIC_FNS[m](y, pred)
        folds[m] = M.by_fold(y, pred, d.fold.values, m)
    return {"pooled": pooled, "by_fold": folds}


def difference(d, oof_a, oof_b, metric, arm, vs, n_boot, spread=None) -> dict:
    """Arm a against arm b on one metric: per-fold paired differences and a block-bootstrap interval."""
    target = METRIC_TARGET[metric]
    y, col = labels_for(d, target), TARGETS[target][1]
    fold = d.fold.values
    paired = M.paired_diff(M.by_fold(y, oof_a[col].values, fold, metric), M.by_fold(y, oof_b[col].values, fold, metric))
    boot = M.block_bootstrap_diff(d.split_block.values, y, oof_a[col].values, oof_b[col].values, metric, n=n_boot)
    return {"arm": arm, "vs": vs, "metric": metric, **boot, "folds_up": paired["folds_up"],
            "folds_down": paired["folds_down"], "per_fold": paired["per_fold"],
            "seed_spread": float("nan") if spread is None else spread, "real": M.is_real(boot, spread)}


def shuffled_labels(d: pd.DataFrame, rows=None, seed: int = 0) -> pd.DataFrame:
    """A copy of d with each label column permuted among its labelled rows (all folds together).

    Fitting and scoring against these must give chance: if held-out rows leaked into fitting, the
    model would have seen their (permuted) labels and would score above chance.
    """
    rows = np.ones(len(d), dtype=bool) if rows is None else np.asarray(rows, dtype=bool)
    out, rng = d.copy(), np.random.default_rng(seed)
    for target, (ycol, _) in TARGETS.items():
        idx = np.where(target_mask(d, target) & rows)[0]
        if len(idx):
            out.iloc[idx, out.columns.get_loc(ycol)] = d[ycol].values[rng.permutation(idx)]
    return out


def vit_frozen_format(emb_2d: np.ndarray, seg_ids) -> pd.DataFrame:
    """The landed vit_frozen.parquet layout (train_vit.py lines 91 to 94): PCA to 16, random_state 0."""
    z = PCA(16, random_state=0).fit_transform(emb_2d)
    out = pd.DataFrame(z, columns=[f"im_emb{i}" for i in range(16)])
    out.insert(0, "seg_id", np.asarray(seg_ids))
    return out


def ndvi_table(chips, seg_ids, blank_frac, usable) -> pd.DataFrame:
    out = pd.DataFrame([augment.ndvi_stats(c) for c in chips])
    out.insert(0, "seg_id", np.asarray(seg_ids))
    out["blank_frac"], out["usable"] = blank_frac, usable
    return out


def write_parquet(path, df, out_root):
    return V.atomic_write(path, lambda tmp: df.to_parquet(tmp, index=False), out_root)


def write_text(path, text, out_root):
    return V.atomic_write(path, lambda tmp: Path(tmp).write_text(text), out_root)


def main(processed=None, chips_dir=None, out_root=None, net_factory=None, batch=512, n_boot=1000, log=print) -> dict:
    out_root = Path(V.OUT_ROOT if out_root is None else out_root)
    out = out_root / "frozen"
    code = V.check_shipped_code()
    table = V.load_table(processed)
    d = V.chipped(table, chips_dir)
    d = d[d.has_chip].reset_index(drop=True)
    if len(d) == 0:
        raise ValueError("no segment in the table has a chip")
    log(f"{len(d):,} of {len(table):,} segments have a chip; loading")
    chips, blank = V.load_chips(d.seg_id.values, chips_dir)
    usable = V.usable_mask(blank)
    log(f"{int((~usable).sum()):,} chips are more than {V.MAX_BLANK:.0%} blank and are left out of the comparison")

    write_parquet(out_root / "ndvi_stats.parquet", ndvi_table(chips, d.seg_id.values, blank, usable), out_root)
    net = (net_factory or default_net)()
    weights = V.weights_hash(net)
    emb = embed(net, chips, VIEW_IDS, batch)
    arms_emb = {"1view": emb[:, 0], "8view": emb.mean(axis=1)}
    log(f"embedded {emb.shape[0]:,} chips x {emb.shape[1]} views, {emb.shape[2]} numbers each")
    write_parquet(out_root / "vit_frozen_statewide.parquet", vit_frozen_format(arms_emb["1view"], d.seg_id.values), out_root)
    write_parquet(out_root / "vit_frozen_statewide_8view.parquet", vit_frozen_format(arms_emb["8view"], d.seg_id.values),
                  out_root)
    V.save_npy(out / "emb_view0.npy", arms_emb["1view"], out_root)
    V.save_npy(out / "emb_mean8.npy", arms_emb["8view"], out_root)
    write_parquet(out / "index.parquet", pd.DataFrame({"seg_id": d.seg_id.values, "fold": d.fold.values,
                                                       "blank_frac": blank, "usable": usable}), out_root)

    has_flood = bool(target_mask(d, "flood")[usable].any())
    metrics = ["rate_mae", "rate_spearman", "crack_aucpr"] + (["flood_p50", "flood_aucpr"] if has_flood else [])
    arms, oofs, skips = {}, {}, []
    for name, e in arms_emb.items():
        oofs[name], sk = probe(e, d, usable)
        skips += [f"{name}: {s}" for s in sk]
        arms[name] = score_arm(d, oofs[name], metrics)
        write_parquet(out / f"oof_{name}.parquet", oofs[name], out_root)
        log(f"{name}: " + ", ".join(f"{m} {M.fmt(arms[name]['pooled'][m])}" for m in metrics))
    differences = [difference(d, oofs["8view"], oofs["1view"], m, "8view", "1view", n_boot) for m in metrics]

    shuffled = shuffled_labels(d, usable, seed=0)
    control_oof, _ = probe(arms_emb["8view"], shuffled, usable)
    control = score_arm(shuffled, control_oof, metrics)["pooled"]
    yr, yc = labels_for(d, "rate"), labels_for(d, "crack")
    yr[~usable], yc[~usable] = np.nan, np.nan
    results = {
        "title": "Frozen model: one view against the average of 8", "kind": "frozen", "metrics": metrics,
        "hashes": {"code": code, "table": V.table_hash(table), "manifest": V.manifest_hash(d.seg_id.values[usable]),
                   "weights": weights},
        "counts": {"segments_in_table": len(table), "segments_with_a_chip": len(d),
                   "left_out_as_blank": int((~usable).sum()), "segments_compared": int(usable.sum()),
                   "rate_labels_compared": int((~np.isnan(yr)).sum()), "crack_labels_compared": int((~np.isnan(yc)).sum()),
                   "chip_pairs_overlapping_across_folds": V.cross_fold_neighbours(d[usable])},
        "reference": {"rate_mae_do_nothing": M.naive_rate_mae(yr, d.fold.values),
                      "crack_prevalence": float(np.nanmean(yc)) if (~np.isnan(yc)).any() else float("nan")},
        "arms": arms, "differences": differences,
        "controls": {"shuffled labels, 8view": {**control, "crack_prevalence": float(np.nanmean(labels_for(shuffled, "crack")[usable]))}},
        "skips": skips,
        "notes": ["folds: fold = crc32(split_block) % 5, read from segments_targets.parquet",
                  f"probe: standardise, Ridge(alpha={RIDGE_ALPHA}) for rate, LogisticRegression(C={LOGIT_C}) for cracking and flood; "
                  "fitted per fold on the other folds only",
                  "a difference is 8view minus 1view; for the error (MAE) lower is better, for the others higher is better"],
    }
    V.atomic_write(out / "metrics.json", lambda tmp: Path(tmp).write_text(json.dumps(results, indent=1)), out_root)
    write_text(out / "report.md", M.render_report(json.loads(json.dumps(results))), out_root)
    log(f"wrote {out / 'report.md'}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--processed", type=Path, default=None)
    ap.add_argument("--chips", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args()
    main(a.processed, a.chips, a.out, batch=a.batch, n_boot=a.boot)
