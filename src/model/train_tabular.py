"""Targets + 5 km spatial-block CV + ablation ladder (LightGBM).

Usage: uv run python -m src.model.train_tabular
Writes: data/processed/segments_targets.parquet, data/processed/split.parquet, data/processed/ablation.csv
"""
from pathlib import Path

import pandas as pd

from src.model.common import (PV, TR, add_folds, add_targets, attach_terrain, check_not_too_good, naive_mae, oof,
                              precision_at_k, prep, score, terrain_columns, write_atomic, write_split)


def main(p: Path = Path("data/processed")):
    d = pd.read_parquet(p / "segments.parquet")

    # ---- targets, spatial folds, terrain ----
    d = attach_terrain(add_folds(add_targets(d)), p)
    print(f"rate labels: {d.y_rate.notna().sum():,}  median rate {d.y_rate.median():.2f}/yr")
    print(f"crack labels: {d.y_crack.notna().sum():,}  prevalence {d.y_crack.mean():.3f}")
    write_atomic(p / "segments_targets.parquet", d.to_parquet)
    write_split(d, p / "split.parquet")

    TN = terrain_columns(d)
    base = [c for c in PV + TR if c in d.columns]
    ladder = [("baseline: pavement + traffic", base)]
    if TN:
        ladder.append(("+ terrain", base + TN))

    rows = []
    zone = (d.in_helene_zone == 1) & d.y_helene_failed.notna()
    for name, cols in ladder:
        X = prep(d, cols)
        m1 = d.y_rate.notna()
        p1 = oof(d, X, d.y_rate, "l1", m1)
        m2 = d.y_crack.notna()
        p2 = oof(d, X, d.y_crack, "bin", m2)
        p3 = oof(d, X, d.y_helene_failed, "bin", zone)
        s1 = score(d.y_rate, p1, m1, "l1")
        check_not_too_good(s1["spearman"])
        rows.append(dict(
            model=name,
            rate_mae=s1["mae"],
            rate_spearman=s1["spearman"],
            crack_aucpr=score(d.y_crack, p2, m2, "bin")["aucpr"],
            flood_p50=precision_at_k(d.y_helene_failed, p3, zone),
            flood_aucpr=score(d.y_helene_failed, p3, zone, "bin")["aucpr"],
            n_rate=int(m1.sum()),
            rate_mae_naive=naive_mae(d, d.y_rate, m1),
            crack_prevalence=d.y_crack[m2].mean(),
            n_scored=s1["n_scored"],
        ))
        print(rows[-1], flush=True)

    res = pd.DataFrame(rows)
    write_atomic(p / "ablation.csv", lambda f: res.round(4).to_csv(f, index=False))
    print(res.round(3).to_string())


if __name__ == "__main__":
    main()
