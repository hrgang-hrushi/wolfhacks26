"""Targets + 5 km spatial-block CV + ablation ladder (LightGBM).

Usage: uv run python -m src.model.train_tabular
Writes: data/processed/segments_targets.parquet, data/processed/ablation.csv
"""
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, mean_absolute_error
from sklearn.model_selection import GroupKFold

P = Path("data/processed")
d = pd.read_parquet(P / "segments.parquet")

# ---- targets ----
rtg = d.pv_RTG_NBR.where(d.pv_RTG_NBR > 0)
age = d.pv_PVMNT_AGE
ok = (age >= 2) & (age <= 40) & rtg.notna()
d["y_rate"] = ((100 - rtg) / age).clip(lower=0).where(ok)
rate = d.y_rate.clip(lower=0.1)
d["y_years_to_poor"] = np.where(rtg < 60, 0, ((rtg - 60) / rate).clip(upper=50)).astype(float)
d.loc[~ok, "y_years_to_poor"] = np.nan
alg = d.pv_asph_ALGTR_MDRT_PCT.fillna(0) + d.pv_asph_ALGTR_HGH_PCT.fillna(0)
d["y_crack"] = (alg > 0).astype(float).where(d.pv_asph_ALGTR_HGH_PCT.notna())
print(f"rate labels: {d.y_rate.notna().sum():,}  median rate {d.y_rate.median():.2f}/yr")
print(f"crack labels: {d.y_crack.notna().sum():,}  prevalence {d.y_crack.mean():.3f}")
d.to_parquet(P / "segments_targets.parquet")

# ---- spatial folds: 5 km blocks ----
block = (d.mid_x // 5000).astype(int).astype(str) + "_" + (d.mid_y // 5000).astype(int).astype(str)
d["fold"] = -1
for k, (_, te) in enumerate(GroupKFold(5).split(d, groups=block)):
    d.iloc[te, d.columns.get_loc("fold")] = k

# ---- feature groups (no current-condition columns: they leak the target) ----
PV = ["pv_PVMNT_AGE", "pv_YEAR_LAST_REHAB", "pv_NUMBER_OF_LANES", "pv_SEC_WIDTH", "pv_SHOULDER_WIDTH",
      "pv_LENGTH", "pv_LAST_REHAB_TYPE", "pv_SURFACE", "pv_NC_SYSTEM_CODE", "pv_SUBDIVISION_RURAL_CODE",
      "pv_CURB", "pv_asph_PAVEMENT_TYPE", "pv_asph_RSRF_THCKNS_NBR"]
TR = ["tr_aadt", "tr_aadtt", "tr_su_pct", "tr_mu_pct", "tr_has_count", "tr_aadt_source"]
TN = [c for c in d.columns if c.startswith("tn_")]
base = [c for c in PV + TR if c in d.columns]
ladder = [("baseline: pavement + traffic", base)]
if TN:
    ladder.append(("+ terrain", base + TN))

def prep(cols):
    X = d[cols].copy()
    for c in X.columns:
        if not pd.api.types.is_numeric_dtype(X[c]) or X[c].dtype == bool:
            X[c] = X[c].astype("category")
    return X

def oof(X, y, objective, mask):
    pred = pd.Series(np.nan, index=d.index)
    prm = dict(objective=objective, n_estimators=400, learning_rate=0.05, num_leaves=63,
               min_child_samples=40, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
    for k in range(5):
        tr = mask & (d.fold != k)
        te = mask & (d.fold == k)
        m = lgb.LGBMRegressor(**prm) if objective == "l1" else lgb.LGBMClassifier(**prm)
        m.fit(X[tr], y[tr])
        pred[te] = m.predict(X[te]) if objective == "l1" else m.predict_proba(X[te])[:, 1]
    return pred

rows = []
zone = (d.in_helene_zone == 1) & d.y_helene_failed.notna()
for name, cols in ladder:
    X = prep(cols)
    m1 = d.y_rate.notna()
    p1 = oof(X, d.y_rate, "l1", m1)
    m2 = d.y_crack.notna()
    p2 = oof(X, d.y_crack, "binary", m2)
    p3 = oof(X, d.y_helene_failed, "binary", zone)
    top = p3[zone].nlargest(50).index
    rows.append(dict(
        model=name,
        rate_mae=mean_absolute_error(d.y_rate[m1], p1[m1]),
        rate_spearman=spearmanr(d.y_rate[m1], p1[m1])[0],
        crack_aucpr=average_precision_score(d.y_crack[m2], p2[m2]),
        flood_p50=d.y_helene_failed[top].mean(),
        flood_aucpr=average_precision_score(d.y_helene_failed[zone], p3[zone]),
    ))
    print(rows[-1], flush=True)

pd.DataFrame(rows).round(4).to_csv(P / "ablation.csv", index=False)
print(pd.DataFrame(rows).round(3).to_string())