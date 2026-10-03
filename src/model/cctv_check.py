"""Check the rankings against what graded camera stills show.

Usage:  uv run python -m src.model.cctv_check
Reads:  data/raw/cctv/cameras.parquet, data/raw/cctv/grades.csv
        data/processed/segments_targets.parquet, predictions.parquet, pothole_predictions.parquet (if present)
Writes: data/processed/results/cctv_check.json and cctv_check.md

For each score: the share of cameras showing damage (cracks, patches or a pothole) on the
worst-ranked third of camera segments against the best third. Only clear views with a decided
grade count, and each score is judged on the cameras that have that score held out.

Interstates are both better rated and less often damaged, so a ratio over all cameras mostly
restates the road class. The same comparison is therefore given inside interstates and inside
the other roads; those rows are the ones that speak to the ranking.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.model.pothole_check import PRED_COLS, add_scores, commit, fingerprint, write_results
from src.pipeline.cctv_review import DECIDED, decided, validate_grades

CCTV = Path("data/raw/cctv")
P = Path("data/processed")
MIN_CAMERAS = 30       # fewer cameras than this with a given score is too few to compare thirds
SCORES = {"rating": "NCDOT rating (low is worse)", "pred_rate": "held-out predicted wear rate",
          "pred_crack": "held-out predicted cracking", "pred_pothole": "pothole head (untested outside the two cities)"}
DAMAGED = ("cracks_or_patches", "pothole")
ROADS = ("all", "interstate", "other")


def load(cctv=CCTV, p=P):
    """(one row per graded camera with its segment's scores, counts of what was left out)."""
    cctv, p = Path(cctv), Path(p)
    grades = pd.read_csv(cctv / "grades.csv", keep_default_na=False)
    cams = pd.read_parquet(cctv / "cameras.parquet", columns=["camera_id", "seg_id"])
    validate_grades(grades, cams, cctv, files=False)      # the stills themselves are not needed here
    seg = pd.read_parquet(p / "segments_targets.parquet", columns=["seg_id", "pv_RTG_NBR", "pv_NC_SYSTEM_CODE"]).merge(
        pd.read_parquet(p / "predictions.parquet", columns=["seg_id"] + PRED_COLS), on="seg_id", validate="one_to_one")
    seg = add_scores(seg)
    f = p / "pothole_predictions.parquet"
    if f.exists():
        h = pd.read_parquet(f, columns=["seg_id", "pred_pothole", "pothole_heldout"])
        seg = seg.merge(h.assign(score_pred_pothole=h.pred_pothole.where(h.pothole_heldout))[["seg_id", "score_pred_pothole"]],
                        on="seg_id", how="left", validate="one_to_one")
    else:
        seg["score_pred_pothole"] = np.nan
    g = decided(grades).merge(cams, on="camera_id", how="left")
    d = g.merge(seg, on="seg_id", how="left")
    d["damaged"] = d.damage.isin(DAMAGED)
    d["roads"] = np.where(d.pv_NC_SYSTEM_CODE == "Interstate", "interstate", "other")
    first = grades[grades["pass"] == 1]
    left_out = {"graded_stills": int(len(first)), "not_clear": int((first["view"] != "clear").sum()),
                "clear_undecided": int(((first["view"] == "clear") & ~first.damage.isin(DECIDED)).sum()),
                "unmatched_cameras": int(d.seg_id.isna().sum())}
    return d, left_out


def shares(d, score, roads="all"):
    """Damage share on the worst and best thirds of the cameras that have this score, for one road group."""
    z = d[d.seg_id.notna() & d[f"score_{score}"].notna() & ((d.roads == roads) | (roads == "all"))]
    out = {"score": score, "roads": roads, "n": int(len(z)), "too_few": bool(len(z) < MIN_CAMERAS),
           "share_damaged": None, "worst_third": None, "best_third": None, "ratio": None}
    if out["too_few"]:
        return out
    third = np.ceil(3 * z[f"score_{score}"].rank(method="first") / len(z))
    worst, best = float(z.damaged[third == 3].mean()), float(z.damaged[third == 1].mean())
    out.update(share_damaged=float(z.damaged.mean()), worst_third=worst, best_third=best, ratio=worst / best if best else None)
    return out


def render(rows, left_out):
    out = ["| Roads | Score | Cameras | Showing damage | Worst third | Best third | Ratio |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["too_few"]:
            out.append(f"| {r['roads']} | {SCORES[r['score']]} | {r['n']} | too few to compare | | | |")
        else:
            ratio = "" if r["ratio"] is None else f"{r['ratio']:.2f}"
            out.append(f"| {r['roads']} | {SCORES[r['score']]} | {r['n']} | {r['share_damaged']:.0%} | {r['worst_third']:.0%} "
                       f"| {r['best_third']:.0%} | {ratio} |")
    return "\n".join(out) + f"\n\nLeft out: {left_out}\n"


def main(cctv=CCTV, p=P):
    cctv, p = Path(cctv), Path(p)
    d, left_out = load(cctv, p)
    rows = [shares(d, s, roads) for roads in ROADS for s in SCORES]
    files = {"grades.csv": cctv, "cameras.parquet": cctv, "predictions.parquet": p, "segments_targets.parquet": p,
             "pothole_predictions.parquet": p}
    out = {"generated": pd.Timestamp.now("UTC").isoformat(), "commit": commit(), "left_out": left_out,
           "cameras": int(len(d)), "damage_counts": d.damage.value_counts().to_dict(),
           "inputs": {f: fingerprint(d_ / f) for f, d_ in files.items() if (d_ / f).exists()},
           "rows": rows}
    write_results(p / "results" / "cctv_check.json", out, render(rows, left_out))
    print(render(rows, left_out))
    print("saved", p / "results" / "cctv_check.json")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    main()
