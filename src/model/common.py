"""Shared pieces for the tabular models: targets, spatial folds, feature lists, out-of-fold fitting.

train_tabular.py, final_ablation.py and train_vit.py import from here so the label definitions,
the folds and the feature lists cannot drift apart.
"""
import os
import warnings
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, mean_absolute_error

BLOCK_M = 5000
N_FOLDS = 5
MIN_AGE, MAX_AGE = 2, 40
RATE_FLOOR = 0.1
YEARS_CAP = 50
POOR = 60
CRACK_PCT = 10
SEED = 0
N_ESTIMATORS = 400
LEAK_SPEARMAN = 0.95

# ---- feature groups (no current-condition columns: they leak the target) ----
PV = ["pv_age_at_survey", "pv_YEAR_LAST_REHAB", "pv_NUMBER_OF_LANES", "pv_SEC_WIDTH", "pv_SHOULDER_WIDTH",
      "pv_LENGTH", "pv_LAST_REHAB_TYPE", "pv_SURFACE", "pv_NC_SYSTEM_CODE", "pv_SUBDIVISION_RURAL_CODE",
      "pv_CURB", "pv_asph_PAVEMENT_TYPE", "pv_asph_RSRF_THCKNS_NBR"]
TR = ["tr_aadt", "tr_aadtt", "tr_su_pct", "tr_mu_pct", "tr_has_count", "tr_aadt_source"]

# measured in the same survey as the rating, or derived from a label
BANNED_EXACT = {
    "pv_RTG_NBR", "pv_GFP_CODE", "pv_AVERAGE_IRI", "pv_IRI_YEAR", "pv_AVERAGE_RUT_DEPTH",
    "pv_PMS_TREATMENT_NAME", "pv_TREATMENT_COST", "pv_PMS_BUDGET_GROUP_NAME", "pv_PCS_SRVY_YR",
    "pv_asph_RTG_NBR", "pv_asph_PMS_TREATMENT_NAME", "pv_asph_TREATMENT_COST", "pv_asph_PMS_BUDGET_GROUP_NAME",
    "pv_asph_SRVY_YR", "pv_asph_PCS_COMMENT", "pv_asph_PVD_SHLDR_COND_CD", "pv_asph_TRNSVRS_CD",
    "pv_asph_RUT_CD", "pv_asph_RVL_CD", "pv_asph_OXDTN_CD", "pv_asph_BLD_CD", "pv_asph_PTCH_CD",
    "pv_asph_RIDE_CD", "pv_asph_SHLDR_RPR_PCT", "pv_asph_ALGTR_NONE_PCT", "pv_asph_ALGTR_LOW_PCT",
    "pv_asph_ALGTR_MDRT_PCT", "pv_asph_ALGTR_HGH_PCT", "in_helene_zone",
}
# labels, predictions, Helene point counts, and ViT scores (stacking them needs nested out-of-fold generation)
BANNED_PREFIXES = ("y_", "pred_", "n_", "im_vit_")


def check_features(cols):
    bad = [c for c in cols if c in BANNED_EXACT or c.startswith(BANNED_PREFIXES)]
    if bad:
        raise ValueError(f"banned model inputs (they leak the target or are labels): {bad}")


check_features(PV + TR)


# ---- targets ----
def years_to_poor(rtg, rate):
    """Years until the rating reaches POOR at this rate: 0 if already below, rate floored, result capped."""
    rtg, rate = np.asarray(rtg, float), np.clip(np.asarray(rate, float), RATE_FLOOR, None)
    return np.where(rtg < POOR, 0.0, np.minimum((rtg - POOR) / rate, YEARS_CAP))


def add_targets(d):
    """Add pv_age_at_survey, y_rate, y_years_to_poor, y_crack. Rows are never dropped or reordered."""
    d = d.copy()
    rtg = d.pv_RTG_NBR.where(d.pv_RTG_NBR > 0)
    # PVMNT_AGE is counted to 2025, but a third of ratings were surveyed in 2023-24
    age = d.pv_PCS_SRVY_YR - d.pv_YEAR_LAST_REHAB
    d["pv_age_at_survey"] = age.where(age >= 0)
    ok = (age >= MIN_AGE) & (age <= MAX_AGE) & rtg.notna()
    d["y_rate"] = ((100 - rtg) / age.where(ok)).clip(lower=0)
    d["y_years_to_poor"] = years_to_poor(rtg, d.y_rate)
    d.loc[~ok, "y_years_to_poor"] = np.nan
    alg = d.pv_asph_ALGTR_MDRT_PCT.fillna(0) + d.pv_asph_ALGTR_HGH_PCT.fillna(0)
    d["y_crack"] = (alg > CRACK_PCT).astype(float).where(d.pv_asph_ALGTR_HGH_PCT.notna())
    return d


# ---- spatial folds: 5 km blocks ----
def block_id(mid_x, mid_y):
    return (mid_x // BLOCK_M).astype(int).astype(str) + "_" + (mid_y // BLOCK_M).astype(int).astype(str)


def fold_of(block):
    # a hash of the block id, so a block's fold never depends on which other rows are in the table
    return zlib.crc32(block.encode()) % N_FOLDS


def add_folds(d):
    d = d.copy()
    d["split_block"] = block_id(d.mid_x, d.mid_y)
    d["fold"] = d.split_block.map(fold_of).astype(int)
    return d


def write_atomic(path, write):
    """Call write(tmp) then swap it in, so a failed write leaves the previous file intact."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    write(tmp)
    os.replace(tmp, path)


def write_split(d, path):
    write_atomic(path, d[["seg_id", "split_block", "fold"]].to_parquet)


# ---- merges ----
def merge_one_to_one(d, other, name):
    """Left-merge other onto d by seg_id, keeping d's rows, order and index."""
    for side, f in (("table", d), (name, other)):
        if f.seg_id.isna().any() or f.seg_id.duplicated().any():
            raise ValueError(f"{side}: seg_id has nulls or duplicates")
    clash = sorted(set(d.columns) & set(other.columns) - {"seg_id"})
    if clash:  # pandas would rename both to _x/_y and the feature lists would silently lose them
        raise ValueError(f"{name}: columns already in the table: {clash}")
    out = d.merge(other, on="seg_id", how="left", validate="one_to_one")
    assert len(out) == len(d) and (out.seg_id.values == d.seg_id.values).all()
    out.index = d.index
    return out


def attach_terrain(d, p):
    """Merge terrain.parquet if present. On a name clash its column wins; the table's copy gets _d8."""
    f = Path(p) / "terrain.parquet"
    if not f.exists():
        return d
    t = pd.read_parquet(f)
    clash = [c for c in t.columns if c.startswith("tn_") and c in d.columns]
    taken = [f"{c}_d8" for c in clash if f"{c}_d8" in d.columns]
    if taken:
        raise ValueError(f"terrain.parquet: cannot rename onto existing columns {taken}")
    return merge_one_to_one(d.rename(columns={c: f"{c}_d8" for c in clash}), t, "terrain.parquet")


def terrain_columns(d):
    return sorted(c for c in d.columns if c.startswith("tn_"))


# ---- fitting ----
def prep(d, cols):
    check_features(cols)
    X = d[cols].copy()
    for c in X.columns:
        if not pd.api.types.is_numeric_dtype(X[c]) or X[c].dtype == bool:
            X[c] = X[c].astype("category")
    return X


def _fit(X, y, kind, seed):
    # imported here, not at the top: on macOS LightGBM and PyTorch each load their own OpenMP runtime
    # and the process crashes if LightGBM is loaded before PyTorch runs. train_vit.py imports this
    # module for the folds and must not pull LightGBM in.
    import lightgbm as lgb
    prm = dict(n_estimators=N_ESTIMATORS, learning_rate=0.05, num_leaves=63, min_child_samples=40,
               subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=seed)
    m = lgb.LGBMRegressor(objective="l1", **prm) if kind == "l1" else lgb.LGBMClassifier(**prm)
    return m.fit(X, y)


def _predict(m, X, kind):
    return m.predict(X) if kind == "l1" else m.predict_proba(X)[:, 1]


def oof(d, X, y, kind, mask, seed=SEED):
    """Out-of-fold predictions for the masked rows (kind: "l1" or "bin"). A fold that cannot be
    fitted or has nothing to predict is skipped and its rows stay NaN."""
    pred = pd.Series(np.nan, index=d.index)
    for k in range(N_FOLDS):
        tr, te = mask & (d.fold != k), mask & (d.fold == k)
        why = None
        if te.sum() == 0:
            why = "no held-out rows"
        elif tr.sum() == 0:
            why = "no training rows"
        elif kind == "bin" and y[tr].nunique() < 2:
            why = "one class in the training rows"
        if why:
            if mask.any():
                print(f"fold {k} skipped: {why}", flush=True)
            continue
        pred[te] = _predict(_fit(X[tr], y[tr], kind, seed), X[te], kind)
    return pred


def fit_all_predict(X, y, kind, mask, seed=SEED):
    """Fit on the masked rows, predict every row. NaN if there is nothing to fit."""
    if mask.sum() == 0 or (kind == "bin" and y[mask].nunique() < 2):
        return np.full(len(X), np.nan)
    return _predict(_fit(X[mask], y[mask], kind, seed), X, kind)


def heldout_then_model(oof_pred, full_pred):
    """Out-of-fold value where one exists, otherwise the full-model value. Returns (pred, is_heldout)."""
    is_heldout = oof_pred.notna()
    return oof_pred.where(is_heldout, pd.Series(np.asarray(full_pred), index=oof_pred.index)), is_heldout


# ---- scoring ----
def score(y, pred, mask, kind):
    """Metrics over masked rows that have a prediction. NaN, not an error, when there is nothing to score."""
    ok = mask & pred.notna()
    n = int(ok.sum())
    if kind == "l1":
        if n == 0:
            return dict(n_scored=0, mae=np.nan, spearman=np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # constant input gives NaN, which is the answer we want
            rho = spearmanr(y[ok], pred[ok])[0] if n > 1 else np.nan
        return dict(n_scored=n, mae=mean_absolute_error(y[ok], pred[ok]), spearman=rho)
    if n == 0 or y[ok].nunique() < 2:
        return dict(n_scored=n, aucpr=np.nan)
    return dict(n_scored=n, aucpr=average_precision_score(y[ok], pred[ok]))


def precision_at_k(y, pred, mask, k=50):
    top = pred[mask & pred.notna()].nlargest(k).index
    return y[top].mean() if len(top) else np.nan


def naive_mae(d, y, mask):
    """MAE of predicting each fold with the median of the other folds: the do-nothing reference."""
    pred = pd.Series(np.nan, index=d.index)
    for k in range(N_FOLDS):
        tr, te = mask & (d.fold != k), mask & (d.fold == k)
        if tr.sum() and te.sum():
            pred[te] = y[tr].median()
    return score(y, pred, mask, "l1")["mae"]


def check_not_too_good(spearman):
    if spearman == spearman and spearman > LEAK_SPEARMAN:
        raise RuntimeError(f"rate Spearman {spearman:.3f} is above {LEAK_SPEARMAN}: an input is probably leaking the target")
