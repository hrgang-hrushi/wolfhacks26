"""Check the rankings against real pothole reports.

Usage:  uv run python -m src.model.pothole_check
Reads:  data/processed/segments_targets.parquet, pothole_labels.parquet, predictions.parquet
Writes: data/processed/results/pothole_check.json and pothole_check.md

For each city and each score (NCDOT's rating, the held-out wear prediction, the held-out cracking
prediction): reports per mile per year on the worst-ranked fifth of segments divided by the best
fifth. Busy roads get reported more whatever their condition, so the fifths are cut inside groups
of roads with similar traffic ("adjusted"); the plain city-wide figure is given beside it ("raw").
"""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from src.model.common import SEED, merge_one_to_one

P = Path("data/processed")
M_PER_MILE = 1609.344
MIN_BAND = 50          # fewer scored segments than this cannot be cut into fifths
N_DRAWS = 1000
MIN_VALID_DRAWS = 500
SCORES = {"rating": "NCDOT rating (low is worse)", "pred_rate": "held-out predicted wear rate",
          "pred_crack": "held-out predicted cracking"}
PRED_COLS = ["pred_rate", "pred_crack", "rate_heldout", "crack_heldout"]
# Charlotte's CDOT reports are city-street repairs that happen to sit beside a state road;
# its NCDOT requests are the ones filed against state roads.
REPORT_SETS = {"all": "n_pothole_reports", "ncdot_only": "n_pothole_ncdot"}


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def commit():
    """Short hash of the code that ran, with "-dirty" when src/ had uncommitted or untracked changes."""
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "src"], capture_output=True, text=True).stdout.strip()
    return (head + ("-dirty" if dirty else "")) or None


def write_results(path, obj, md):
    """The JSON and its markdown rendering, each swapped in whole."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    for f, text in ((path, json.dumps(obj, indent=1)), (path.with_suffix(".md"), md)):
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, f)


def add_scores(d):
    """score_* columns where higher always means worse. Model scores only where they are held out."""
    d = d.copy()
    d["score_rating"] = (-d.pv_RTG_NBR).where(d.pv_RTG_NBR > 0)
    d["score_pred_rate"] = d.pred_rate.where(d.rate_heldout.fillna(False).astype(bool))
    d["score_pred_crack"] = d.pred_crack.where(d.crack_heldout.fillna(False).astype(bool))
    return d


def load(p):
    p = Path(p)
    t = pd.read_parquet(p / "segments_targets.parquet",
                        columns=["seg_id", "split_block", "tr_aadt", "pv_RTG_NBR", "length_m"])
    lab = pd.read_parquet(p / "pothole_labels.parquet")
    pred = pd.read_parquet(p / "predictions.parquet")
    missing = [c for c in PRED_COLS if c not in pred.columns]
    if missing:
        raise ValueError(f"predictions.parquet has no {missing}: it predates the held-out flags, regenerate it")
    for name, f in (("pothole_labels.parquet", lab), ("predictions.parquet", pred)):
        if f.seg_id.duplicated().any() or set(f.seg_id) != set(t.seg_id):
            raise ValueError(f"{name} does not cover the same segments as segments_targets.parquet")
    d = merge_one_to_one(merge_one_to_one(t, lab, "pothole_labels.parquet"), pred[["seg_id"] + PRED_COLS],
                         "predictions.parquet")
    d["mile_years"] = d.length_m / M_PER_MILE * d.pothole_exposure_years
    return add_scores(d)


def population(d):
    return d.pothole_city.notna() & (d.pothole_exposure_years > 0) & (d.length_m > 0)


def traffic_band(d):
    """Within each city: thirds of tr_aadt by rank, and "none" for segments without a count."""
    band = pd.Series("none", index=d.index)
    for _, g in d[d.tr_aadt.notna()].groupby("pothole_city"):
        band[g.index] = "t" + np.ceil(3 * g.tr_aadt.rank(method="first") / len(g)).astype(int).astype(str)
    return band


def fifths(score, groups):
    """1 (best) to 5 (worst) by rank inside each group; 0 where the score is blank or the group is too small."""
    out = pd.Series(0, index=score.index)
    small = []
    for key, s in score.dropna().groupby(groups):
        if len(s) < MIN_BAND:
            small.append({"group": key, "n": int(len(s)), "why": f"fewer than {MIN_BAND} scored segments"})
            continue
        out[s.index] = np.ceil(5 * s.rank(method="first") / len(s)).astype(int)
    return out, small


def rate(count, mile_years):
    return count / mile_years if mile_years > 0 else None


def ratio(worst, best):
    return worst / best if worst is not None and best else None


def lift(d, fifth, count_col):
    w, b = d[fifth == 5], d[fifth == 1]
    return ratio(rate(w[count_col].sum(), w.mile_years.sum()), rate(b[count_col].sum(), b.mile_years.sum()))


def block_totals(d, fifth, count_col):
    """Per 5 km block: reports and mile-years in the worst and best fifths (columns wc, wm, bc, bm)."""
    w, b = d[fifth == 5], d[fifth == 1]
    return pd.DataFrame({"wc": w.groupby("split_block")[count_col].sum(), "wm": w.groupby("split_block").mile_years.sum(),
                         "bc": b.groupby("split_block")[count_col].sum(), "bm": b.groupby("split_block").mile_years.sum()},
                        index=sorted(d.split_block.unique())).fillna(0.0)


def draw_lift(totals, times):
    """Lift when block i is counted times[i] times: the same as stacking each block's rows that often."""
    wc, wm, bc, bm = (totals[c].values @ times for c in ("wc", "wm", "bc", "bm"))
    return ratio(rate(wc, wm), rate(bc, bm))


def block_range(d, fifth, count_col, n=N_DRAWS, seed=SEED):
    """95% range from resampling whole blocks with replacement. Fifths stay as cut on the full data."""
    totals = block_totals(d, fifth, count_col)
    rng = np.random.default_rng(seed)
    draws = [draw_lift(totals, np.bincount(rng.integers(0, len(totals), len(totals)), minlength=len(totals)))
             for _ in range(n)]
    valid = [x for x in draws if x is not None]
    if len(valid) < MIN_VALID_DRAWS:
        return None, len(valid), f"only {len(valid)} of {n} resamples had reports in the best fifth"
    return [float(np.percentile(valid, 2.5)), float(np.percentile(valid, 97.5))], len(valid), None


def check(d, city, score, reports="all"):
    """One result row: a city, a score and a report set."""
    count_col = REPORT_SETS[reports]
    z = d[population(d) & (d.pothole_city == city) & d[f"score_{score}"].notna()].copy()
    z["band"] = traffic_band(z)
    by_band, small = fifths(z[f"score_{score}"], z.band)
    city_wide, too_small = fifths(z[f"score_{score}"], pd.Series("city", index=z.index))
    rng, n_valid, note = block_range(z, by_band, count_col) if len(z) else (None, 0, "no scored segments")
    bands = [{"band": b, "n": int(len(g)), "reports": int(g[count_col].sum()),
              "lift": lift(g, by_band[g.index], count_col)} for b, g in z.groupby("band")]
    return {"city": city, "score": score, "reports": reports, "n_segments": int(len(z)),
            "n_reports": int(z[count_col].sum()), "mile_years": float(z.mile_years.sum()),
            "raw_lift": lift(z, city_wide, count_col), "adjusted_lift": lift(z, by_band, count_col),
            "range": rng, "n_valid_draws": n_valid, "range_note": note, "bands": bands,
            "excluded_bands": small + too_small}


def fmt(x, digits=2):
    return "" if x is None else f"{x:.{digits}f}"


def render(rows):
    out = ["| City | Score | Reports | Segments | Reports counted | Raw lift | Adjusted lift | 95% range |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        rng = "" if r["range"] is None else f"{r['range'][0]:.2f} to {r['range'][1]:.2f}"
        out.append(f"| {r['city']} | {SCORES[r['score']]} | {r['reports']} | {r['n_segments']:,} | {r['n_reports']:,} "
                   f"| {fmt(r['raw_lift'])} | {fmt(r['adjusted_lift'])} | {rng} |")
    return "\n".join(out) + "\n\nLift = reports per mile per year on the worst-ranked fifth divided by the best fifth.\n"


def main(p=P):
    p = Path(p)
    d = load(p)
    rows = [check(d, city, score) for city in ("charlotte", "raleigh") for score in SCORES]
    rows += [check(d, "charlotte", score, "ncdot_only") for score in SCORES]
    out = {"generated": pd.Timestamp.now("UTC").isoformat(), "commit": commit(),
           "inputs": {f: fingerprint(p / f) for f in ("pothole_labels.parquet", "predictions.parquet",
                                                      "segments_targets.parquet")},
           "rows": rows}
    write_results(p / "results" / "pothole_check.json", out, render(rows))
    print(render(rows))
    print("saved", p / "results" / "pothole_check.json")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    main()
