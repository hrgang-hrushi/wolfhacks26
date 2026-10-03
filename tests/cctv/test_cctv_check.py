"""The camera check: damage seen on camera against the rankings."""
import json

import numpy as np
import pandas as pd
import pytest

from src.model import cctv_check as cc
from src.pipeline.cctv_review import GRADE_COLS


def world(tmp_path, n=60, heldout=None, damaged=None, unmatched=(), views=None, damages=None, roads="Primary"):
    """n cameras, one per segment. Segment i has rating 100 - i (so i = n-1 is the worst-rated),
    pred_rate i / 10 and pred_crack i / n. `damaged` picks which cameras show cracks."""
    cctv, p = tmp_path / "cctv", tmp_path / "processed"
    cctv.mkdir(parents=True), p.mkdir(parents=True)
    seg = [f"ncdot:{i:011d}:0.000" for i in range(n)]
    heldout = np.ones(n, bool) if heldout is None else np.asarray(heldout)
    damaged = np.arange(n) >= n * 2 // 3 if damaged is None else np.asarray(damaged)
    pd.DataFrame({"seg_id": seg, "pv_RTG_NBR": 100.0 - np.arange(n), "pv_NC_SYSTEM_CODE": roads}
                 ).to_parquet(p / "segments_targets.parquet")
    for i in range(n):                                  # the graded stills exist, as the validator requires
        (cctv / str(i)).mkdir()
        (cctv / str(i) / "x.jpg").write_bytes(b"jpg")
    pd.DataFrame({"seg_id": seg, "pred_rate": np.arange(n) / 10, "pred_crack": np.arange(n) / n,
                  "rate_heldout": heldout, "crack_heldout": True}).to_parquet(p / "predictions.parquet")
    pd.DataFrame({"camera_id": range(n), "seg_id": [None if i in unmatched else s for i, s in enumerate(seg)]}
                 ).to_parquet(cctv / "cameras.parquet")
    views = ["clear"] * n if views is None else views
    damages = ["cracks_or_patches" if d else "none" for d in damaged] if damages is None else damages
    pd.DataFrame([(i, f"{i}/x.jpg", views[i], damages[i] if views[i] == "clear" else "", 1, "claude", "2026-10-03")
                  for i in range(n)], columns=GRADE_COLS).to_csv(cctv / "grades.csv", index=False)
    return cctv, p


def by_score(cctv, p):
    d, left_out = cc.load(cctv, p)
    return {s: cc.shares(d, s) for s in cc.SCORES}, left_out, d


def test_X1_only_heldout_predictions_are_used(tmp_path):
    heldout = np.arange(60) % 2 == 0
    r, _, d = by_score(*world(tmp_path, heldout=heldout))
    assert r["pred_rate"]["n"] == 30 and r["rating"]["n"] == 60 and r["pred_crack"]["n"] == 60
    s = d.set_index("camera_id").score_pred_rate.sort_index()
    assert s[~heldout].isna().all() and s[heldout].notna().all()


def test_X2_under_thirty_cameras_gives_no_ratio(tmp_path):
    r, _, _ = by_score(*world(tmp_path, n=29))
    for s in ("rating", "pred_rate", "pred_crack"):
        assert r[s] == {"score": s, "roads": "all", "n": 29, "too_few": True, "share_damaged": None,
                        "worst_third": None, "best_third": None, "ratio": None}
    assert by_score(*world(tmp_path / "b", n=30))[0]["rating"]["too_few"] is False


def test_X3_unmatched_cameras_are_excluded_and_counted(tmp_path):
    r, left_out, d = by_score(*world(tmp_path, unmatched=(0, 1, 2, 59)))
    assert left_out["unmatched_cameras"] == 4 and len(d) == 60 and r["rating"]["n"] == 56
    views = ["far" if i < 10 else "unusable" if i < 15 else "clear" for i in range(60)]
    damages = ["cant_tell" if i < 20 else "pothole" if i >= 50 else "none" for i in range(60)]
    r, left_out, d = by_score(*world(tmp_path / "b", views=views, damages=damages))
    assert left_out == {"graded_stills": 60, "not_clear": 15, "clear_undecided": 5, "unmatched_cameras": 0}
    assert len(d) == 40 and r["rating"]["n"] == 40 and d.damaged.sum() == 10
    cctv, p = world(tmp_path / "c")
    g = pd.read_csv(cctv / "grades.csv", keep_default_na=False)
    g.loc[0, "view"] = "blurry"
    g.to_csv(cctv / "grades.csv", index=False)
    with pytest.raises(ValueError, match="bad grade rows"):          # the check refuses a grades file the validator would
        cc.load(cctv, p)


def test_X4_hand_worked_shares(tmp_path):
    damaged = [i >= 50 or i in (0, 1, 2, 3, 4) for i in range(60)]      # worst third: 10 of 20; best third: 5 of 20
    r, _, _ = by_score(*world(tmp_path, damaged=damaged))
    for s in ("rating", "pred_rate", "pred_crack"):
        assert (r[s]["worst_third"], r[s]["best_third"], r[s]["ratio"]) == pytest.approx((0.5, 0.25, 2.0))
        assert r[s]["share_damaged"] == pytest.approx(15 / 60)
    none_best = [i >= 50 for i in range(60)]
    assert by_score(*world(tmp_path / "b", damaged=none_best))[0]["rating"]["ratio"] is None


def test_X5_sample_size_gate_is_applied_per_score(tmp_path):
    cctv, p = world(tmp_path, n=40, heldout=np.arange(40) < 10, damaged=[i >= 26 or i < 3 for i in range(40)])
    r, _, _ = by_score(cctv, p)
    assert (r["pred_rate"]["n"], r["pred_rate"]["too_few"], r["pred_rate"]["ratio"]) == (10, True, None)
    assert r["rating"]["n"] == 40 and r["rating"]["too_few"] is False and r["rating"]["ratio"] is not None
    assert r["pred_pothole"]["n"] == 0 and r["pred_pothole"]["too_few"] is True      # no head file: no claim
    pd.DataFrame({"seg_id": pd.read_parquet(p / "segments_targets.parquet").seg_id, "pred_pothole": np.arange(40) / 40,
                  "pothole_heldout": np.arange(40) >= 5}).to_parquet(p / "pothole_predictions.parquet")
    assert by_score(cctv, p)[0]["pred_pothole"]["n"] == 35
    cc.main(cctv, p)
    out = json.loads((p / "results" / "cctv_check.json").read_text())
    assert [(x["roads"], x["score"]) for x in out["rows"]] == [(r, s) for r in cc.ROADS for s in cc.SCORES]
    assert out["cameras"] == 40 and set(out["inputs"]) == {"grades.csv", "cameras.parquet", "predictions.parquet",
                                                           "segments_targets.parquet", "pothole_predictions.parquet"}
    assert "too few to compare" in (p / "results" / "cctv_check.md").read_text()


def test_X6_road_class_is_not_mistaken_for_ranking_skill(tmp_path):
    # 40 well-rated interstates with almost no damage, then 40 other roads where every second camera
    # shows damage whatever the rating: the ranking tells nothing inside either class
    roads = ["Interstate"] * 40 + ["Primary"] * 40
    damaged = [i in (0, 20) if i < 40 else i % 2 == 1 for i in range(80)]
    d, _ = cc.load(*world(tmp_path, n=80, roads=roads, damaged=damaged))
    pooled, other, inter = (cc.shares(d, "rating", r) for r in cc.ROADS[:1] + ("other", "interstate"))
    assert pooled["ratio"] > 3                           # over all cameras it looks like the rating works
    assert other["n"] == 40 and 0.7 < other["ratio"] < 1.4      # inside the other roads there is nothing
    assert inter["n"] == 40 and inter["worst_third"] == 0
    assert set(d.roads) == {"interstate", "other"}
