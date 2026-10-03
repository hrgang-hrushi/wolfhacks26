"""Scores for the vision comparisons, and the comparison between arms.

Rate: MAE and Spearman, with the do-nothing MAE (training-fold median) beside them. Cracking:
AUC-PR next to prevalence. Flood: precision at 50 and AUC-PR inside the Helene zone. Differences
between arms are paired per fold and given a 95% interval by resampling whole 5 km blocks. An
empty or one-class subset scores NaN; nothing here raises on thin data.
"""

from __future__ import annotations

import math
import re
import warnings

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score

NAN = float("nan")
LOWER_IS_BETTER = {"rate_mae"}
METRIC_LABELS = {"rate_mae": "wear-rate error (MAE)", "rate_spearman": "wear-rate ranking (Spearman)",
                 "crack_aucpr": "cracking score (AUC-PR)", "flood_p50": "flood precision at 50",
                 "flood_aucpr": "flood score (AUC-PR)"}
HASH_KEYS = ("code", "table", "manifest")
MIN_BLOCKS = 30          # fewer blocks than this and a block bootstrap says nothing
CHANCE_SPEARMAN = 0.05   # a shuffled-label control must rank within this of 0
CHANCE_AUCPR = 0.02      # and score within this of prevalence


def _pair(y, pred):
    y, pred = np.asarray(y, dtype="float64"), np.asarray(pred, dtype="float64")
    keep = ~np.isnan(y) & ~np.isnan(pred)
    return y[keep], pred[keep]


def mae(y, pred) -> float:
    y, pred = _pair(y, pred)
    return float(np.abs(y - pred).mean()) if len(y) else NAN


def spearman(y, pred) -> float:
    y, pred = _pair(y, pred)
    if len(y) < 2 or np.ptp(y) == 0 or np.ptp(pred) == 0:
        return NAN
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(spearmanr(y, pred)[0])


def aucpr(y, pred) -> float:
    y, pred = _pair(y, pred)
    if len(y) == 0 or y.min() == y.max():
        return NAN
    return float(average_precision_score(y, pred))


def precision_at(y, pred, k=50) -> float:
    y, pred = _pair(y, pred)
    if len(y) == 0:
        return NAN
    top = np.argsort(-pred, kind="stable")[:k]
    return float(y[top].mean())


def rate_metrics(y, pred) -> dict:
    return {"n_rate": int(len(_pair(y, pred)[0])), "rate_mae": mae(y, pred), "rate_spearman": spearman(y, pred)}


def crack_metrics(y, pred) -> dict:
    yy, _ = _pair(y, pred)
    return {"n_crack": int(len(yy)), "crack_aucpr": aucpr(y, pred),
            "crack_prevalence": float(yy.mean()) if len(yy) else NAN}


def flood_metrics(y, pred) -> dict:
    yy, _ = _pair(y, pred)
    return {"n_flood": int(len(yy)), "flood_p50": precision_at(y, pred, 50), "flood_aucpr": aucpr(y, pred),
            "flood_prevalence": float(yy.mean()) if len(yy) else NAN}


METRIC_FNS = {"rate_mae": mae, "rate_spearman": spearman, "crack_aucpr": aucpr, "flood_p50": precision_at,
              "flood_aucpr": aucpr}


def naive_prediction(y, fold) -> np.ndarray:
    """For each fold, the median of the labelled rows in the other folds: the do-nothing prediction."""
    y, fold = np.asarray(y, dtype="float64"), np.asarray(fold)
    pred = np.full(len(y), np.nan)
    for k in np.unique(fold):
        train = y[(fold != k) & ~np.isnan(y)]
        if len(train):
            pred[fold == k] = np.median(train)
    return pred


def naive_rate_mae(y, fold) -> float:
    """MAE of the do-nothing prediction over all folds."""
    return mae(y, naive_prediction(y, fold))


def reference_by_fold(y_rate, y_crack, fold) -> dict:
    """Per fold: the do-nothing rate error and the share of cracking positives, to read the scores against."""
    y_rate, y_crack, fold = np.asarray(y_rate, "float64"), np.asarray(y_crack, "float64"), np.asarray(fold)
    naive = naive_prediction(y_rate, fold)
    out = {"rate_mae_do_nothing": {}, "crack_prevalence": {}}
    for k in sorted(np.unique(fold)):
        m = fold == k
        out["rate_mae_do_nothing"][str(int(k))] = mae(y_rate[m], naive[m])
        yc = y_crack[m][~np.isnan(y_crack[m])]
        out["crack_prevalence"][str(int(k))] = float(yc.mean()) if len(yc) else NAN
    return out


def by_fold(y, pred, fold, metric: str) -> dict:
    """The metric on each fold's rows, keyed by fold number as a string."""
    fn, fold = METRIC_FNS[metric], np.asarray(fold)
    y, pred = np.asarray(y, dtype="float64"), np.asarray(pred, dtype="float64")
    return {str(int(k)): fn(y[fold == k], pred[fold == k]) for k in sorted(np.unique(fold))}


def paired_diff(a_by_fold: dict, b_by_fold: dict) -> dict:
    """Per-fold a minus b, their mean, and how many folds point each way. Folds with a NaN are left out."""
    diffs = {k: a_by_fold[k] - b_by_fold[k] for k in sorted(a_by_fold) if k in b_by_fold
             and not (math.isnan(a_by_fold[k]) or math.isnan(b_by_fold[k]))}
    vals = list(diffs.values())
    return {"per_fold": diffs, "mean": float(np.mean(vals)) if vals else NAN,
            "folds_up": int(sum(v > 0 for v in vals)), "folds_down": int(sum(v < 0 for v in vals))}


def block_bootstrap_diff(blocks, y, pred_a, pred_b, metric: str, n=1000, seed=0) -> dict:
    """metric(a) - metric(b) on all rows, with a 95% interval from resampling whole blocks with replacement."""
    fn = METRIC_FNS[metric]
    y, pred_a, pred_b = (np.asarray(v, dtype="float64") for v in (y, pred_a, pred_b))
    keep = ~np.isnan(y) & ~np.isnan(pred_a) & ~np.isnan(pred_b)
    blocks = np.asarray(blocks)[keep]
    y, pred_a, pred_b = y[keep], pred_a[keep], pred_b[keep]
    point = fn(y, pred_a) - fn(y, pred_b) if len(y) else NAN
    if len(y) == 0:
        return {"diff": NAN, "lo": NAN, "hi": NAN, "n_boot": 0, "n_blocks": 0}
    order = np.argsort(blocks, kind="stable")
    _, starts = np.unique(blocks[order], return_index=True)
    groups = np.split(order, starts[1:])
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        idx = np.concatenate([groups[g] for g in rng.integers(len(groups), size=len(groups))])
        d = fn(y[idx], pred_a[idx]) - fn(y[idx], pred_b[idx])
        if not math.isnan(d):
            out.append(d)
    lo, hi = (float(v) for v in np.percentile(out, [2.5, 97.5])) if out else (NAN, NAN)
    return {"diff": float(point), "lo": lo, "hi": hi, "n_boot": len(out), "n_blocks": len(groups)}


def interval_excludes_zero(d: dict) -> bool:
    """Whether the interval is entirely on one side of 0. Too few blocks to resample gives no usable interval."""
    if d.get("n_blocks", MIN_BLOCKS) < MIN_BLOCKS or math.isnan(d["lo"]) or math.isnan(d["hi"]):
        return False
    return d["lo"] > 0 or d["hi"] < 0


def seed_spread(values) -> float:
    """Largest gap between matched runs that differ only in seed."""
    vals = [v for v in values if not math.isnan(v)]
    return float(max(vals) - min(vals)) if len(vals) >= 2 else NAN


def is_real(diff: dict, spread: float | None = None, require_spread: bool = False) -> bool:
    """A difference counts only if its interval excludes 0 and it exceeds the seed-to-seed spread.

    With require_spread (the fine-tune, where two runs of the same arm differ), a missing spread
    means the difference cannot be judged, so it does not count.
    """
    if not interval_excludes_zero(diff):
        return False
    if spread is None or math.isnan(spread):
        return not require_spread
    return abs(diff["diff"]) > spread


def control_at_chance(control: dict, crack_prevalence: float) -> bool:
    """The shuffled-label control: ranking near 0 and the cracking score near prevalence."""
    rho, ap = control.get("rate_spearman", NAN), control.get("crack_aucpr", NAN)
    if math.isnan(rho) or math.isnan(ap) or math.isnan(crack_prevalence):
        return False
    return abs(rho) < CHANCE_SPEARMAN and abs(ap - crack_prevalence) < CHANCE_AUCPR


def compare(result_a: dict, result_b: dict) -> None:
    """Refuse to compare results made from different roads, code or labels. A missing fingerprint is a difference."""
    a, b = result_a.get("hashes", {}), result_b.get("hashes", {})
    bad = [k for k in HASH_KEYS if not a.get(k) or a.get(k) != b.get(k)]
    if bad:
        raise ValueError(f"results are not comparable: different {', '.join(bad)} hash")


# ---------------------------------------------------------------- report

def fmt(x) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    if isinstance(x, (bool, np.bool_)):
        return "yes" if x else "no"
    if isinstance(x, str):
        return x
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    return f"{float(x):.4f}"


def _verdict(d: dict) -> str:
    spread = d.get("seed_spread")
    if d.get("spread_required") and (spread is None or math.isnan(spread)):
        return "not judged (no seed spread)"
    if not d.get("real"):
        return "no measurable difference"
    better = (d["diff"] < 0) == (d["metric"] in LOWER_IS_BETTER)
    return "better" if better else "worse"


def render_report(results: dict) -> str:
    """Markdown built only from the results dict, so every number in it is a number in the results file."""
    metrics = results["metrics"]
    lines = [f"# {results['title']}", ""]
    lines += [f"- {k}: {fmt(v)}" for k, v in results.get("counts", {}).items()]
    lines += [f"- {k}: {fmt(v)}" for k, v in results.get("reference", {}).items()]
    lines += [f"- {note}" for note in results.get("notes", [])]
    lines += ["", "## Scores on held-out squares (all folds pooled)", "",
              "| Arm | " + " | ".join(METRIC_LABELS[m] for m in metrics) + " |", "|---|" + "---|" * len(metrics)]
    for arm, r in results["arms"].items():
        lines.append(f"| {arm} | " + " | ".join(fmt(r["pooled"].get(m)) for m in metrics) + " |")
    lines += ["", "## Per fold", ""]
    for m in metrics:
        folds = sorted({k for r in results["arms"].values() for k in r["by_fold"].get(m, {})})
        lines += [f"**{METRIC_LABELS[m]}**", "", "| Arm | " + " | ".join(f"fold {k}" for k in folds) + " |",
                  "|---|" + "---|" * len(folds)]
        for arm, r in results["arms"].items():
            lines.append(f"| {arm} | " + " | ".join(fmt(r["by_fold"].get(m, {}).get(k)) for k in folds) + " |")
        lines.append("")
    if results.get("differences"):
        lines += ["## Differences", "",
                  "| Arm | Against | Measure | Difference | 95% interval | Folds up / down | Seed spread | Verdict |",
                  "|---|---|---|---|---|---|---|---|"]
        for d in results["differences"]:
            lines.append(f"| {d['arm']} | {d['vs']} | {METRIC_LABELS[d['metric']]} | {fmt(d['diff'])} | "
                         f"{fmt(d['lo'])} to {fmt(d['hi'])} | {fmt(d['folds_up'])} / {fmt(d['folds_down'])} | "
                         f"{fmt(d.get('seed_spread'))} | {_verdict(d)} |")
        lines.append("")
    ref = results.get("reference_by_fold")
    if ref:
        folds = sorted({k for v in ref.values() for k in v})
        lines += ["## What the scores are read against, per fold", "", "| Reference | " + " | ".join(f"fold {k}" for k in folds) + " |",
                  "|---|" + "---|" * len(folds)]
        lines += [f"| {name} | " + " | ".join(fmt(v.get(k)) for k in folds) + " |" for name, v in ref.items()]
        lines.append("")
    for t in results.get("tables", []):
        lines += [f"## {t['title']}", "", "| " + " | ".join(t["columns"]) + " |", "|---|" + "---|" * (len(t["columns"]) - 1)]
        lines += ["| " + " | ".join(c if isinstance(c, str) else fmt(c) for c in row) + " |" for row in t["rows"]]
        lines.append("")
    if results.get("controls"):
        lines += ["## Controls", ""]
        for name, c in results["controls"].items():
            lines.append(f"- {name}: " + ", ".join(f"{k} {fmt(v)}" for k, v in c.items()))
        lines.append("")
    skips = results.get("skips", [])
    lines += ["## Skipped", "", f"- folds skipped: {fmt(len(skips))}"] + [f"- {s}" for s in skips] + [""]
    lines += ["## Fingerprints", ""] + [f"- {k}: `{v}`" for k, v in results["hashes"].items()]
    return "\n".join(lines) + "\n"


_NUMBER = re.compile(r"(?<![\w.`-])-?\d[\d,]*\.\d{4}(?![\w.])")


def report_numbers(text: str):
    """Every 4-decimal number printed in a report (used to check the report against the results)."""
    body = text.split("## Fingerprints")[0]
    return [float(tok.replace(",", "")) for tok in _NUMBER.findall(body)]
