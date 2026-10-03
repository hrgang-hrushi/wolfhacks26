"""Final ablation ladder + predictions for the map.
Usage: uv run python -m src.model.final_ablation
Writes: data/processed/ablation_final.csv, data/processed/predictions.parquet
"""
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, mean_absolute_error
from sklearn.model_selection import GroupKFold

P = Path("data/processed")
d = pd.read_parquet(P / "segments_targets.parquet")
d = d.merge(pd.read_parquet(P / "terrain.parquet"), on="seg_id", how="left")
emb = pd.read_parquet(P / "vit_frozen.parquet")
d = d.merge(emb, on="seg_id", how="left")
d["has_chip"] = d.im_emb0.notna()

block = (d.mid_x // 5000).astype(int).astype(str) + "_" + (d.mid_y // 5000).astype(int).astype(str)
d["fold"] = -1
for k, (_, te) in enumerate(GroupKFold(5).split(d, groups=block)):
    d.iloc[te, d.columns.get_loc("fold")] = k

PV = ["pv_PVMNT_AGE", "pv_YEAR_LAST_REHAB", "pv_NUMBER_OF_LANES", "pv_SEC_WIDTH", "pv_SHOULDER_WIDTH",
      "pv_LENGTH", "pv_LAST_REHAB_TYPE", "pv_SURFACE", "pv_NC_SYSTEM_CODE", "pv_SUBDIVISION_RURAL_CODE",
      "pv_CURB", "pv_asph_PAVEMENT_TYPE", "pv_asph_RSRF_THCKNS_NBR"]
TR = ["tr_aadt", "tr_aadtt", "tr_su_pct", "tr_mu_pct", "tr_has_count", "tr_aadt_source"]
TN = ["tn_elev", "tn_slope", "tn_relief1k", "tn_hand_proxy"]
EM = [f"im_emb{i}" for i in range(16)]
base = [c for c in PV + TR if c in d.columns]


def prep(cols):
    X = d[cols].copy()
    for c in X.columns:
        if not pd.api.types.is_numeric_dtype(X[c]) or X[c].dtype == bool:
            X[c] = X[c].astype("category")
    return X


def oof(X, y, kind, mask):
    pred = pd.Series(np.nan, index=d.index)
    prm = dict(n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=40,
               subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
    for k in range(5):
        tr, te = mask & (d.fold != k), mask & (d.fold == k)
        if te.sum() == 0 or tr.sum() == 0:
            continue
        if kind == "l1":
            m = lgb.LGBMRegressor(objective="l1", **prm).fit(X[tr], y[tr])
            pred[te] = m.predict(X[te])
        else:
            m = lgb.LGBMClassifier(**prm).fit(X[tr], y[tr])
            pred[te] = m.predict_proba(X[te])[:, 1]
    return pred


def evaluate(name, cols, subset):
    X = prep(cols)
    m1 = d.y_rate.notna() & subset
    m2 = d.y_crack.notna() & subset
    zone = (d.in_helene_zone == 1) & d.y_helene_failed.notna() & subset
    p1, p2, p3 = oof(X, d.y_rate, "l1", m1), oof(X, d.y_crack, "bin", m2), oof(X, d.y_helene_failed, "bin", zone)
    top = p3[zone].nlargest(50).index
    row = dict(model=name, n_rate=int(m1.sum()),
               rate_mae=mean_absolute_error(d.y_rate[m1], p1[m1]),
               rate_spearman=spearmanr(d.y_rate[m1], p1[m1])[0],
               crack_aucpr=average_precision_score(d.y_crack[m2], p2[m2]),
               crack_prevalence=d.y_crack[m2].mean(),
               n_flood_zone=int(zone.sum()),
               flood_p50=d.y_helene_failed[top].mean() if len(top) else np.nan,
               flood_aucpr=average_precision_score(d.y_helene_failed[zone], p3[zone]) if zone.sum() else np.nan)
    print(row, flush=True)
    return row


allseg = pd.Series(True, index=d.index)
chip = d.has_chip
rows = [evaluate("ALL: baseline", base, allseg),
        evaluate("ALL: + terrain", base + TN, allseg),
        evaluate("CHIPPED: baseline", base, chip),
        evaluate("CHIPPED: + terrain", base + TN, chip),
        evaluate("CHIPPED: + frozen DINOv2", base + TN + EM, chip)]
res = pd.DataFrame(rows).round(4)
res.to_csv(P / "ablation_final.csv", index=False)
print(res.to_string())

# predictions for the map: final model on everything (terrain, no embedding so it covers every segment)
X = prep(base + TN)
out = d[["seg_id", "mid_x", "mid_y"]].copy()
prm = dict(n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=40,
           subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
m = d.y_rate.notna()
out["pred_rate"] = lgb.LGBMRegressor(objective="l1", **prm).fit(X[m], d.y_rate[m]).predict(X)
rate = out.pred_rate.clip(lower=0.1)
rtg = d.pv_RTG_NBR.where(d.pv_RTG_NBR > 0)
out["pred_years_to_poor"] = np.where(rtg < 60, 0, ((rtg - 60) / rate).clip(upper=50))
m = d.y_crack.notna()
out["pred_crack"] = lgb.LGBMClassifier(**prm).fit(X[m], d.y_crack[m]).predict_proba(X)[:, 1]
zone = (d.in_helene_zone == 1) & d.y_helene_failed.notna()
out["pred_flood"] = lgb.LGBMClassifier(**prm).fit(X[zone], d.y_helene_failed[zone]).predict_proba(X)[:, 1]
out["in_helene_zone"] = d.in_helene_zone
out.to_parquet(P / "predictions.parquet")
print("saved predictions.parquet", out.shape)