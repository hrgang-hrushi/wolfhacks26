"""A pothole head: predict whether a segment gets a pothole report, from the main model's clues.

Usage:  uv run python -m src.model.pothole_head
Reads:  data/processed/segments_targets.parquet, pothole_labels.parquet, predictions.parquet
Writes: data/processed/pothole_predictions.parquet        seg_id, pred_pothole, pothole_heldout,
                                                          pothole_tested_area, pothole_city
        data/processed/results/pothole_head.json and pothole_head.md

Trained on Charlotte only. Scored two ways: on Charlotte blocks the model did not train on (the
shared 5 km folds), and on Raleigh, which it never sees. Beside it, on the same rows: a traffic-only
model (traffic counts plus segment length: reports follow traffic and longer segments catch more of
them, so this is the bar to beat), the main model's held-out wear prediction used as a ranking, and
the base rate. The gap to the traffic-only model comes with a range from resampling whole 5 km
blocks. Outside the two cities nothing is tested.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from src.model.common import (PV, SEED, TR, fit_all_predict, merge_one_to_one, oof, precision_at_k, prep, score,
                              terrain_columns, write_atomic)
from src.model.pothole_check import N_DRAWS, commit, fingerprint, write_results

P = Path("data/processed")
TRAIN_CITY, TEST_CITY = "charlotte", "raleigh"
# a segment resurfaced inside a city's report window was watched for less time than the rest
WINDOW_YEAR = {"charlotte": 2023, "raleigh": 2025}
TRAFFIC_ONLY = TR + ["pv_LENGTH"]
MIN_POS = 20           # fewer positives than this in the test city is too few to trust
LEAK_AUCPR = 0.9
GAP_DRAWS = N_DRAWS
METHODS = ("head", "traffic_only", "main_model")


def load_table(p):
    p = Path(p)
    d = merge_one_to_one(pd.read_parquet(p / "segments_targets.parquet"),
                         pd.read_parquet(p / "pothole_labels.parquet"), "pothole_labels.parquet")
    split = pd.read_parquet(p / "split.parquet").set_index("seg_id")
    if (set(split.index) != set(d.seg_id) or (split.fold.loc[d.seg_id].values != d.fold.values).any()
            or (split.split_block.loc[d.seg_id].values != d.split_block.values).any()):
        raise ValueError("segments_targets.parquet does not carry the folds in split.parquet: rebuild both with the model scripts")
    pred = pd.read_parquet(p / "predictions.parquet", columns=["seg_id", "pred_rate", "rate_heldout"])
    return merge_one_to_one(d, pred, "predictions.parquet")


def features(d):
    cols = PV + TR + terrain_columns(d)
    bad = [c for c in cols if "pothole" in c]
    if bad:
        raise ValueError(f"pothole columns cannot be model inputs: {bad}")
    return cols


def labelled(d, city):
    """Segments of the city with a label and a full report window (not resurfaced inside it)."""
    rehab = d.pv_YEAR_LAST_REHAB
    return (d.pothole_city == city) & d.y_pothole_any.notna() & (rehab.isna() | (rehab < WINDOW_YEAR[city]))


def evaluate(y, preds, mask):
    """Each method on its own rows and on the rows every method has, with the base rate beside them."""
    common_rows = mask & pd.concat([preds[m].notna() for m in METHODS], axis=1).all(axis=1)
    out = {"n": int(mask.sum()), "n_pos": int(y[mask].sum()), "base_rate": float(y[mask].mean()) if mask.any() else None,
           "n_common": int(common_rows.sum()),
           "base_rate_common": float(y[common_rows].mean()) if common_rows.any() else None}
    for m in METHODS:
        s, c = score(y, preds[m], mask, "bin"), score(y, preds[m], common_rows, "bin")
        out[m] = {"n_scored": s["n_scored"], "aucpr": none_if_nan(s["aucpr"]),
                  "p_at_50": none_if_nan(precision_at_k(y, preds[m], mask)), "aucpr_common": none_if_nan(c["aucpr"]),
                  "p_at_50_common": none_if_nan(precision_at_k(y, preds[m], common_rows))}
    return out


def gap_range(d, y, a, b, mask, n=None, seed=SEED):
    """AUC-PR of a minus AUC-PR of b on the masked rows, with a 95% range from resampling whole
    5 km blocks (a block drawn twice counts twice). A draw without both classes is dropped."""
    ok = mask & a.notna() & b.notna()
    yy, aa, bb = y[ok].values, a[ok].values, b[ok].values
    if len(yy) == 0 or len(set(yy)) < 2:
        return {"gap": None, "range": None, "n_valid_draws": 0}
    block, names = pd.factorize(d.split_block[ok])
    rng, gaps = np.random.default_rng(seed), []
    for _ in range(GAP_DRAWS if n is None else n):
        w = np.bincount(rng.integers(0, len(names), len(names)), minlength=len(names))[block]
        if (w * yy).sum() == 0 or (w * (1 - yy)).sum() == 0:
            continue
        gaps.append(average_precision_score(yy, aa, sample_weight=w) - average_precision_score(yy, bb, sample_weight=w))
    rng95 = [float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))] if gaps else None
    return {"gap": float(average_precision_score(yy, aa) - average_precision_score(yy, bb)), "range": rng95,
            "n_valid_draws": len(gaps)}


def none_if_nan(x):
    return None if x is None or x != x else float(x)


def run(p=P, seed=SEED):
    """(results, predictions). Nothing is written here."""
    d = load_table(p)
    y = d.y_pothole_any
    train, test = labelled(d, TRAIN_CITY), labelled(d, TEST_CITY)
    res = {"train_city": TRAIN_CITY, "test_city": TEST_CITY, "n_train": int(train.sum()),
           "n_train_pos": int(y[train].sum()), "features": features(d)}
    pred = pd.DataFrame({"seg_id": d.seg_id, "pred_pothole": np.nan, "pothole_heldout": False,
                         "pothole_tested_area": d.pothole_city.notna().values, "pothole_city": d.pothole_city})
    if train.sum() == 0 or y[train].nunique() < 2:
        why = "no labelled Charlotte segments" if train.sum() == 0 else "Charlotte labels are all one class"
        res.update(status="unavailable", reason=why, beats_traffic=None, distinguishable_from_traffic=None,
                   too_few=None, charlotte_heldout=None, raleigh_transfer=None)
        return res, pred

    X, Xt = prep(d, features(d)), prep(d, TRAFFIC_ONLY)
    main_rank = d.pred_rate.where(d.rate_heldout.fillna(False).astype(bool))
    held = {"head": oof(d, X, y, "bin", train, seed), "traffic_only": oof(d, Xt, y, "bin", train, seed),
            "main_model": main_rank}
    full = {"head": pd.Series(fit_all_predict(X, y, "bin", train, seed), index=d.index),
            "traffic_only": pd.Series(fit_all_predict(Xt, y, "bin", train, seed), index=d.index),
            "main_model": main_rank}
    res["charlotte_heldout"] = evaluate(y, held, train)
    res["raleigh_transfer"] = evaluate(y, full, test)
    for part in ("charlotte_heldout", "raleigh_transfer"):
        a = res[part]["head"]["aucpr"]
        if a is not None and a > LEAK_AUCPR:
            raise RuntimeError(f"pothole head AUC-PR {a:.3f} on {part} is above {LEAK_AUCPR}: an input is probably leaking")
    h, t = res["charlotte_heldout"]["head"]["aucpr"], res["charlotte_heldout"]["traffic_only"]["aucpr"]
    gap = gap_range(d, y, held["head"], held["traffic_only"], train, seed=seed)
    res["charlotte_heldout"]["head_minus_traffic"] = gap
    res.update(status="ok", reason=None, beats_traffic=None if h is None or t is None else bool(h > t),
               distinguishable_from_traffic=None if gap["range"] is None else bool(gap["range"][0] > 0),
               too_few=bool(res["raleigh_transfer"]["n_pos"] < MIN_POS))

    # out-of-fold value where one exists, otherwise the Charlotte-fit model's value
    value = held["head"].where(held["head"].notna(), full["head"])
    pred["pred_pothole"] = value.values
    pred["pothole_heldout"] = (value.notna() & ~(train & held["head"].isna())).values
    return res, pred


def render(res):
    if res["status"] != "ok":
        return f"Pothole head unavailable: {res['reason']}.\n"
    out = ["| Test | Method | Segments scored | AUC-PR | AUC-PR on shared rows | Hits in top 50 on shared rows |",
           "|---|---|---|---|---|---|"]
    for part, name in (("charlotte_heldout", "Charlotte, held-out blocks"), ("raleigh_transfer", "Raleigh, never seen")):
        e = res[part]
        for m in METHODS:
            r = e[m]
            cells = ["" if v is None else f"{v:.3f}" for v in (r["aucpr"], r["aucpr_common"], r["p_at_50_common"])]
            out.append(f"| {name} | {m} | {r['n_scored']:,} | {cells[0]} | {cells[1]} | {cells[2]} |")
        out.append(f"| {name} | base rate | {e['n']:,} | {e['base_rate']:.3f} | "
                   f"{'' if e['base_rate_common'] is None else format(e['base_rate_common'], '.3f')} | |")
    g = res["charlotte_heldout"]["head_minus_traffic"]
    rng = "no range" if g["range"] is None else f"95% range {g['range'][0]:+.3f} to {g['range'][1]:+.3f}"
    out.append(f"\nHead minus traffic-only on held-out Charlotte: {g['gap']:+.3f} ({rng}); "
               f"distinguishable from the traffic-only model: {res['distinguishable_from_traffic']}. "
               f"Raleigh positives: {res['raleigh_transfer']['n_pos']}"
               f"{' (too few to trust)' if res['too_few'] else ''}.\n")
    return "\n".join(out)


def main(p=P):
    p = Path(p)
    res, pred = run(p)
    res.update(generated=pd.Timestamp.now("UTC").isoformat(), commit=commit(),
               inputs={f: fingerprint(p / f) for f in ("pothole_labels.parquet", "predictions.parquet",
                                                       "segments_targets.parquet")})
    write_atomic(p / "pothole_predictions.parquet", pred.to_parquet)
    write_results(p / "results" / "pothole_head.json", res, render(res))
    print(render(res))
    print("saved", p / "pothole_predictions.parquet", "and", p / "results" / "pothole_head.json")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    main()
