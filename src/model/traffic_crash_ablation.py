"""Do estimated traffic and crash history improve the predictions?

Usage:  python -m src.model.traffic_crash_ablation   (after src.model.train_tabular and src.pipeline.traffic_crash)
Reads:  data/processed/segments_targets.parquet, data/processed/traffic_crash.parquet
Writes: data/processed/results/traffic_crash_ablation.csv and .md

Same folds, targets and model settings as final_ablation.py. The first row is the model behind the
map today (pavement + traffic counts + terrain); each later row adds one group of columns to it.
The range beside each change is a 95% interval from resampling whole 5 km blocks: a change whose
range crosses zero is not distinguishable from noise.

The crash counts cover 2021-2025, which runs past Helene (September 2024). A road the storm closed
has fewer crashes afterwards, so the flood numbers of the crash rows are not a clean test.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from src.model.common import (PV, TR, check_not_too_good, merge_one_to_one, oof, precision_at_k, prep, score,
                              terrain_columns, write_atomic)

TE = ["tr_aadt_est", "tr_aadt_best", "tr_aadt_best_source"]
CR = ["cr_crash_n", "cr_ka_n", "cr_crash_per_mi_yr", "cr_ncdot_score", "cr_fatal_10yr", "cr_serious_10yr",
      "cr_cover"]
BOTH = ["cr_crash_per_mvm"]     # needs a traffic number and a crash count
N_BOOT = 300


def block_range(blocks, y, ref, new, mask, kind, n=N_BOOT, seed=0):
    """95% range of (new - ref) on the metric, resampling whole blocks. kind: "l1" (MAE) or "bin" (AUC-PR)."""
    ok = (mask & ref.notna() & new.notna()).values
    codes, uniq = pd.factorize(blocks[ok])
    yv, a, b = y[ok].values, ref[ok].values, new[ok].values
    rng, diffs = np.random.default_rng(seed), []
    for _ in range(n):
        w = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))[codes]
        if kind == "l1":
            diffs.append(np.average(np.abs(yv - b), weights=w) - np.average(np.abs(yv - a), weights=w))
        elif len(np.unique(yv[w > 0])) == 2:
            diffs.append(average_precision_score(yv, b, sample_weight=w)
                         - average_precision_score(yv, a, sample_weight=w))
    return tuple(np.percentile(diffs, [2.5, 97.5])) if diffs else (np.nan, np.nan)


def to_markdown(res):
    def change(r, m):
        if r.model == res.model[0]:
            return ""
        return f" ({r[m + '_change']:+.3f}, range {r[m + '_lo']:+.3f} to {r[m + '_hi']:+.3f})"

    lines = ["| Model | Wear: typical miss (lower is better) | Cracking: ranking score (higher is better) | "
             "Flood: ranking score (higher is better) | Flood: damaged among top 50 |", "|---|---|---|---|---|"]
    for r in res.itertuples(index=False):
        r = pd.Series(r._asdict())
        lines.append(f"| {r.model} | {r.rate_mae:.3f}{change(r, 'rate_mae')} | {r.crack_aucpr:.3f}"
                     f"{change(r, 'crack_aucpr')} | {r.flood_aucpr:.3f}{change(r, 'flood_aucpr')} | "
                     f"{r.flood_p50 * 50:.0f} |")
    return "\n".join(lines) + "\n"


def main(p: Path = Path("data/processed")):
    d = pd.read_parquet(p / "segments_targets.parquet")
    d = merge_one_to_one(d, pd.read_parquet(p / "traffic_crash.parquet"), "traffic_crash.parquet")
    base = [c for c in PV + TR if c in d.columns] + terrain_columns(d)
    targets = dict(rate=(d.y_rate, "l1", d.y_rate.notna()),
                   crack=(d.y_crack, "bin", d.y_crack.notna()),
                   flood=(d.y_helene_failed, "bin", (d.in_helene_zone == 1) & d.y_helene_failed.notna()))
    arms = [("map model today", base), ("+ estimated traffic", base + TE), ("+ crashes", base + CR),
            ("+ both", base + TE + CR + BOTH)]

    rows, ref = [], None
    for name, cols in arms:
        X = prep(d, cols)
        pr = {t: oof(d, X, y, kind, m) for t, (y, kind, m) in targets.items()}
        ref = ref or pr
        s = score(d.y_rate, pr["rate"], targets["rate"][2], "l1")
        check_not_too_good(s["spearman"])
        row = dict(model=name, n_inputs=len(cols), rate_mae=s["mae"], rate_spearman=s["spearman"],
                   crack_aucpr=score(d.y_crack, pr["crack"], targets["crack"][2], "bin")["aucpr"],
                   flood_aucpr=score(d.y_helene_failed, pr["flood"], targets["flood"][2], "bin")["aucpr"],
                   flood_p50=precision_at_k(d.y_helene_failed, pr["flood"], targets["flood"][2]))
        for t, metric in (("rate", "rate_mae"), ("crack", "crack_aucpr"), ("flood", "flood_aucpr")):
            y, kind, m = targets[t]
            lo, hi = (0.0, 0.0) if pr is ref else block_range(d.split_block, y, ref[t], pr[t], m, kind)
            row.update({f"{metric}_change": row[metric] - rows[0][metric] if rows else 0.0,
                        f"{metric}_lo": lo, f"{metric}_hi": hi})
        print(row, flush=True)
        rows.append(row)

    res = pd.DataFrame(rows).round(4)
    (p / "results").mkdir(exist_ok=True)
    write_atomic(p / "results" / "traffic_crash_ablation.csv", lambda f: res.to_csv(f, index=False))
    write_atomic(p / "results" / "traffic_crash_ablation.md", lambda f: Path(f).write_text(to_markdown(res)))
    print(to_markdown(res))


if __name__ == "__main__":
    main()
