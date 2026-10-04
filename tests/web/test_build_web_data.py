"""The data layer behind the two dashboards: tiers, score, path encoding, shard grid, and a full build."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("build_web_data", ROOT / "scripts" / "build_web_data.py")
bwd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bwd)

CFG = bwd.load_priority()
NAN = float("nan")


def tier(ytp, crack, flood=0.0, hz=0):
    return int(bwd.tier_index([ytp], [crack], [flood], [hz], CFG)[0])


def test_tier_rules_follow_priority_json():
    assert tier(1.0, 0.0) == 0            # reaches Poor within a year
    assert tier(30.0, 0.6) == 0           # cracking alone is enough
    assert tier(30.0, 0.0, 0.5, hz=1) == 0  # flood counts inside the Helene zone
    assert tier(30.0, 0.0, 0.9, hz=0) == 3  # and is ignored outside it
    assert tier(3.0, 0.0) == 1
    assert tier(30.0, 0.4) == 1
    assert tier(5.0, 0.0) == 2
    assert tier(5.01, 0.39) == 3


def test_missing_years_to_poor_is_no_estimate_unless_another_rule_fires():
    assert tier(NAN, 0.1) == 4
    assert tier(NAN, 0.7) == 0
    assert tier(NAN, 0.45) == 1


def test_score_is_bounded_and_ignores_flood_outside_the_zone():
    s = bwd.priority_score([0.0, NAN, 50.0, 50.0], [1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 1.0, 1.0], [1, 0, 0, 1], CFG)
    w = CFG["score"]
    assert s[0] == pytest.approx(w["w_ytp"] + w["w_crack"] + w["w_flood"])
    assert s[1] == 0.0                     # no estimate contributes nothing
    assert s[2] == 0.0                     # flood outside the zone contributes nothing
    assert s[3] == pytest.approx(w["w_flood"])
    assert pytest.approx(1.0) == w["w_ytp"] + w["w_crack"] + w["w_flood"]


def test_path_round_trips_to_five_decimals():
    coords = np.array([[-78.638211, 35.779604], [-78.63801, 35.77999], [-78.6375, 35.7805]])
    flat = bwd.encode_path(coords)
    assert all(isinstance(v, int) for v in flat)
    assert np.allclose(bwd.decode_path(flat), np.round(coords, 5), atol=1e-9)


def test_path_drops_repeats_but_stays_drawable():
    same = np.array([[-80.0, 35.0], [-80.000001, 35.000001]])
    assert len(bwd.encode_path(same)) == 4  # two points even when they quantise to one


def test_cell_key_matches_the_client_formula():
    assert bwd.cell_key(-78.75, 35.75) == "405_503"
    assert bwd.cell_key(-78.750001, 35.749999) == "404_502"


def test_histograms_give_exact_threshold_counts():
    v = np.array([0.0, 0.5, 0.5000001, 1.0, 1.2, 49.9, 50.0])
    le = bwd.hist(v, 0.5, 50, "le")
    assert sum(le[:3]) == int((v <= 1.0).sum())
    c = np.array([0.0, 0.599, 0.6, 0.61, 0.9])
    ge = bwd.hist(c, 0.01, 1, "ge")
    assert sum(ge[60:]) == int((c >= 0.6).sum())


def test_route_label_uses_class_digit_and_number_only():
    assert bwd.route_label("40002748") == "SR 2748"
    assert bwd.route_label("10000040") == "I-40"
    assert bwd.route_label("20000070") == "US 70"
    assert bwd.route_label("30000012") == "NC 12"


def test_build_refuses_to_wipe_a_folder_it_did_not_write(tmp_path, monkeypatch):
    (tmp_path / "keep.txt").write_text("not ours")
    monkeypatch.setattr("sys.argv", ["build_web_data.py", "--out", str(tmp_path)])
    with pytest.raises(SystemExit):
        bwd.main()
    assert (tmp_path / "keep.txt").exists()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One full build from the committed handoff file (about 20 seconds)."""
    if not bwd.PRED.exists():
        pytest.skip("handoff/predictions_geo.parquet is not present")
    out = tmp_path_factory.mktemp("webdata")
    import sys

    argv, sys.argv = sys.argv, ["build_web_data.py", "--out", str(out)]
    try:
        bwd.main()
    finally:
        sys.argv = argv
    return out, json.loads((out / "stats.json").read_text())


def test_every_road_lands_in_exactly_one_shard(built):
    out, stats = built
    assert stats["total"] == 112_443
    assert sum(c["n"] for c in stats["cells"].values()) == stats["total"]
    assert sum(stats["tiers"].values()) == stats["total"]
    ids = set()
    for f in (out / "shards").glob("*.json"):
        shard = json.loads(f.read_text())
        assert len(shard["segs"]) == stats["cells"][shard["cell"]]["n"]
        ids.update(s["id"] for s in shard["segs"])
    assert len(ids) == stats["total"]


def test_flood_is_shipped_only_inside_the_helene_zone(built):
    out, stats = built
    zone = 0
    for f in (out / "shards").glob("*.json"):
        for s in json.loads(f.read_text())["segs"]:
            assert ("flood" in s) == (s["hz"] == 1)
            zone += s["hz"]
    assert zone == stats["helene"]["zone"] == 32_558


def test_shard_tiers_recomputed_from_shipped_values_match_stats(built):
    """The client recomputes tiers from the rounded numbers in the shards; the counts must agree."""
    out, stats = built
    ytp, crack, flood, hz = [], [], [], []
    for f in (out / "shards").glob("*.json"):
        for s in json.loads(f.read_text())["segs"]:
            ytp.append(NAN if s["ytp"] is None else s["ytp"])
            crack.append(s["crack"])
            flood.append(s.get("flood", 0.0))
            hz.append(s["hz"])
    counts = np.bincount(bwd.tier_index(ytp, crack, flood, hz, CFG), minlength=5).tolist()
    assert counts == list(stats["tiers"].values())


def test_no_invented_fields_reach_the_dashboards(built):
    out, _ = built
    banned = {"pv_rating", "pv_age", "name", "flood_rank", "drivers", "chip_url", "score", "city"}
    shard = json.loads(next((out / "shards").glob("*.json")).read_text())
    assert set(shard["segs"][0]) <= {"id", "path", "paths", "rate", "ytp", "crack", "flood", "hz", "ho"}
    for name in ("ranked.json", "storm.json"):
        rows = json.loads((out / name).read_text())["rows"]
        assert not banned & set(rows[0])


def test_backtest_reproduces_the_readme_claim(built):
    out, stats = built
    if not bwd.HELENE.exists():
        assert stats["backtest"] is None and not (out / "backtest.json").exists()
        pytest.skip("data/raw/helene_labels.parquet is not present on this machine")
    bt = json.loads((out / "backtest.json").read_text())
    assert bt["n"] == 50 and len(bt["rows"]) == 50
    assert bt["damaged"] == sum(r["failed"] for r in bt["rows"]) == 18
    assert all(r["ho"] & 4 for r in bt["rows"])       # every one is a held-out flood score
    assert 1.5 < bt["expected_by_chance"] < 2.5       # "about 2 by chance"
    floods = [r["flood"] for r in bt["rows"]]
    assert floods == sorted(floods, reverse=True)


def test_featured_road_matches_the_readme_example(built):
    _, stats = built
    if not stats["has_join"]:
        pytest.skip("data/raw/ncdot_joined.parquet is not present on this machine")
    f = stats["featured"]
    assert f["id"].startswith("ncdot:40002748092:")
    assert f["data"]["rtg"] == f["readme"]["rating"] == 73.4
    assert f["data"]["rate"] == f["readme"]["wear_predicted"] == 1.62
    assert round(f["data"]["ytp"]) == f["readme"]["years_to_poor"]
    assert round(f["data"]["crack_top_pct"]) == f["readme"]["crack_top_pct"]
