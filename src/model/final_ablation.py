"""Final ablation ladder + predictions for the map.
Usage: uv run python -m src.model.final_ablation   (after src.model.train_tabular)
Writes: data/processed/ablation_final.csv, data/processed/predictions.parquet, handoff/predictions_geo.parquet
"""
from pathlib import Path

import pandas as pd

from src.model.common import (PV, TR, check_not_too_good, fit_all_predict, heldout_then_model, merge_one_to_one,
                              naive_mae, oof, precision_at_k, prep, score, terrain_columns, write_atomic,
                              years_to_poor)

SIMPLIFY_M = 3  # the map file is tracked in git; 3 m keeps it under 20 MB and is invisible at map zoom


def export_geo(pred, p, handoff_dir):
    """Join the predictions to the segment geometry and write the file the map reads."""
    import geopandas as gpd
    geom = gpd.read_parquet(p / "segments_geom.parquet")[["seg_id", "geometry"]]
    if set(geom.seg_id) != set(pred.seg_id):   # a left merge would drop or blank segments without a word
        raise ValueError(f"segments_geom.parquet and the predictions cover different segments: "
                         f"{len(set(pred.seg_id) - set(geom.seg_id))} without geometry, "
                         f"{len(set(geom.seg_id) - set(pred.seg_id))} without predictions")
    geo = merge_one_to_one(geom, pred.drop(columns=["mid_x", "mid_y"]), "predictions")
    geo["geometry"] = geo.geometry.to_crs("EPSG:32119").simplify(SIMPLIFY_M).to_crs(geom.crs)
    handoff_dir.mkdir(parents=True, exist_ok=True)
    write_atomic(handoff_dir / "predictions_geo.parquet", lambda f: geo.to_parquet(f, compression="zstd"))
    print("saved", handoff_dir / "predictions_geo.parquet", geo.shape)


def main(p: Path = Path("data/processed"), handoff_dir: Path = Path("handoff")):
    d = pd.read_parquet(p / "segments_targets.parquet")
    if not {"split_block", "fold"} <= set(d.columns):
        raise SystemExit("segments_targets.parquet has no folds: rerun `uv run python -m src.model.train_tabular`")

    has_emb = (p / "vit_frozen.parquet").exists()
    if has_emb:
        d = merge_one_to_one(d, pd.read_parquet(p / "vit_frozen.parquet"), "vit_frozen.parquet")
    else:
        print("vit_frozen.parquet not found: skipping the imagery-subset rows", flush=True)

    TN = terrain_columns(d)
    EM = [c for c in (f"im_emb{i}" for i in range(16)) if c in d.columns]
    base = [c for c in PV + TR if c in d.columns]
    targets = [("rate", d.y_rate, "l1"), ("crack", d.y_crack, "bin"), ("flood", d.y_helene_failed, "bin")]

    def masks(subset):
        return dict(rate=d.y_rate.notna() & subset, crack=d.y_crack.notna() & subset,
                    flood=(d.in_helene_zone == 1) & d.y_helene_failed.notna() & subset)

    def evaluate(name, cols, subset):
        X, m = prep(d, cols), masks(subset)
        pr = {t: oof(d, X, y, kind, m[t]) for t, y, kind in targets}
        s1 = score(d.y_rate, pr["rate"], m["rate"], "l1")
        check_not_too_good(s1["spearman"])
        row = dict(model=name, n_rate=int(m["rate"].sum()),
                   rate_mae=s1["mae"],
                   rate_spearman=s1["spearman"],
                   crack_aucpr=score(d.y_crack, pr["crack"], m["crack"], "bin")["aucpr"],
                   crack_prevalence=d.y_crack[m["crack"]].mean(),
                   n_flood_zone=int(m["flood"].sum()),
                   flood_p50=precision_at_k(d.y_helene_failed, pr["flood"], m["flood"]),
                   flood_aucpr=score(d.y_helene_failed, pr["flood"], m["flood"], "bin")["aucpr"],
                   rate_mae_naive=naive_mae(d, d.y_rate, m["rate"]),
                   n_scored=s1["n_scored"])
        print(row, flush=True)
        return row, pr

    if not TN:
        print("no tn_ columns: skipping the terrain rows; the map model is the baseline", flush=True)
    allseg = pd.Series(True, index=d.index)
    row, held = evaluate("ALL: baseline", base, allseg)
    rows = [row]
    if TN:
        row, held = evaluate("ALL: + terrain", base + TN, allseg)
        rows.append(row)
    if has_emb:
        chip = d.im_emb0.notna()
        rows.append(evaluate("CHIPPED: baseline", base, chip)[0])
        if TN:
            rows.append(evaluate("CHIPPED: + terrain", base + TN, chip)[0])
        rows.append(evaluate("CHIPPED: + frozen DINOv2", base + TN + EM, chip)[0])
    res = pd.DataFrame(rows).round(4)
    write_atomic(p / "ablation_final.csv", lambda f: res.to_csv(f, index=False))
    print(res.to_string())

    # predictions for the map: the last ALL row's model (terrain if present; no embedding, so it covers
    # every segment). A segment the model was trained on gets its out-of-fold value; the *_heldout flags
    # say which values those are.
    X, m = prep(d, base + TN), masks(allseg)
    out = d[["seg_id", "mid_x", "mid_y"]].copy()
    flags = {}
    for t, y, kind in targets:
        out[f"pred_{t}"], flags[f"{t}_heldout"] = heldout_then_model(held[t], fit_all_predict(X, y, kind, m[t]))
    # no forecast where the rating is 0 or predates the last resurfacing: it describes the old surface
    rtg = d.pv_RTG_NBR.where((d.pv_RTG_NBR > 0) & ~(d.pv_PCS_SRVY_YR < d.pv_YEAR_LAST_REHAB))
    out["pred_years_to_poor"] = pd.Series(years_to_poor(rtg, out.pred_rate), index=d.index).where(rtg.notna())
    out["in_helene_zone"] = d.in_helene_zone
    out = out[["seg_id", "mid_x", "mid_y", "pred_rate", "pred_years_to_poor", "pred_crack", "pred_flood",
               "in_helene_zone"]].assign(**flags)
    write_atomic(p / "predictions.parquet", out.to_parquet)
    print("saved predictions.parquet", out.shape)

    if (p / "segments_geom.parquet").exists():
        export_geo(out, p, handoff_dir)


if __name__ == "__main__":
    main()
