"""Pins on the real marks, tiles and outputs. Skipped on machines without them (N13 also needs the internet)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import helene_dem10 as dem
from src.pipeline import helene_depth as hd

pytestmark = pytest.mark.realdata
P = hd.paths()
FIXTURE = Path(__file__).parent / "fixtures" / "usgs_point_ground.csv"

BILTMORE = "ncdot:21000025011:7.235"  # US 25 through Biltmore Village, beside the Swannanoa River
HILLTOP = "ncdot:20000025011:11.328"  # Pack Square, downtown Asheville, about 70 m above the river
BRIDGE_END = "ncdot:40001338011:0.000"  # SR 1338, which starts on bridge 100726 over Smith Mill Creek


@pytest.fixture(scope="module")
def real():
    for f in (P.marks, P.tiles / "manifest.json", P.out / hd.DEPTH, P.out / hd.META):
        if not f.exists():
            pytest.skip(f"{f} is not on this machine")
    tab = hd.load_depth()  # refuses a stale or mixed set of files
    return {"tab": tab.set_index("seg_id"), "validation": json.loads((P.out / hd.VALID).read_text()),
            "meta": json.loads((P.out / hd.META).read_text()), "points": pd.read_parquet(P.out / hd.POINTS),
            "marks": hd.load_marks(P.marks)}  # fmt: skip


def test_N1_mark_counts(real):
    marks, counts = real["marks"]
    assert counts["read"] == counts["kept"] == 2193 and counts["taped"] == 280
    # the file holds 99 spellings of stream names; one differs from another only by a trailing space
    assert marks.stream.nunique() == 98 and counts["groups"] == 101 and counts["draw_the_line"] == 1887
    assert len(hd.build_lines(marks)) == 95  # six streams have only poorly graded marks


def test_N2_the_30m_number_reproduces(real):
    v30 = real["validation"]["tape"]["vs_30m"]
    if v30["skipped"]:
        pytest.skip("built without the 30 m ground")
    assert v30["miss30"] == pytest.approx(0.61, abs=0.03) and v30["n"] == 280


def test_N3_10m_ground_beats_30m_on_the_taped_marks(real):
    v30 = real["validation"]["tape"]["vs_30m"]
    assert v30["miss10"] <= 0.25 and v30["passed"]
    if not v30["skipped"]:
        assert v30["miss10"] < v30["miss30"]


def test_N4_hidden_mark_miss(real):
    hm = real["validation"]["hidden_mark"]
    near = hm["by_band"][0]
    assert near["band"] == "0-100 m" and near["median"] <= 0.30 and not near["too_few"]
    assert hm["overall"]["median"] <= 0.50 and hm["overall"]["n"] >= 1000
    lo, hi = hm["overall"]["range95"]
    assert lo <= hm["overall"]["median"] <= hi
    assert all(not b["too_few"] for b in hm["by_band"])
    for b in hm["by_band"]:  # every distance band carries its own range
        assert b["range95"][0] <= b["median"] <= b["range95"][1]


def test_N5_end_to_end_miss_against_the_tape(real):
    e2e = real["validation"]["tape"]["end_to_end"]
    assert e2e["median"] <= 0.60 and e2e["n"] >= 150


def test_N6_saved_tiles_agree_with_the_usgs_point_lookup(real):
    marks, _ = real["marks"]
    ref = pd.read_csv(FIXTURE, dtype={"HWM_ID": str}).set_index("HWM_ID").ground_m
    ground = dem.Ground(P.tiles)
    # the USGS lookup returns the cell that holds the point, so compare like with like
    near = ground.sample(marks.lon.values, marks.lat.values, method="nearest")
    diff = np.abs(near - marks.mark_id.map(ref).values)
    assert np.isfinite(diff).all() and (diff <= 0.5).mean() >= 0.95
    assert np.isfinite(ground.sample(marks.lon.values, marks.lat.values)).all()  # every mark has ground under it


def test_N7_table_size_and_sane_depths(real):
    tab, pts = real["tab"], real["points"]
    assert len(tab) == 112_443 and tab.index.is_unique
    assert list(tab.index) == list(pd.read_parquet(P.seg, columns=["seg_id"]).seg_id)
    assessed = tab[tab.y_helene_depth_assessed]
    assert 500 <= len(assessed) <= 5000
    assert assessed.y_helene_depth_point_max_m.max() <= 15 and pts.depth[pts.kept].max() <= 15
    assert tab.loc[~tab.y_helene_depth_assessed, "y_helene_depth_max_m"].isna().all()
    assert real["validation"]["build"]["points_too_deep"] <= 5


def test_N8_biltmore_village_was_deep(real):
    r = real["tab"].loc[BILTMORE]
    assert r.y_helene_depth_assessed and r.y_helene_depth_max_m >= 2 and r.y_helene_depth_band == "over 2 m"


def test_N9_the_downtown_hilltop_is_dry_or_not_assessed(real):
    r = real["tab"].loc[HILLTOP]
    assert (not r.y_helene_depth_assessed) or r.y_helene_depth_max_m == 0


def test_N10_a_segment_that_starts_on_a_bridge_does_not_report_the_river_bed(real):
    pts = real["points"]
    first = pts[pts.seg_id == BRIDGE_END].sort_values(["part", "i"]).head(2)
    assert len(first) == 2 and first.near_bridge.all() and first.aside.all() and not first.kept.any()
    assert first.depth.max() > 3  # what would have been reported: river-bed ground read as the road
    r = real["tab"].loc[BRIDGE_END]
    assert r.n_helene_depth_set_aside >= 2 and not (r.y_helene_depth_max_m >= 1)


def test_N11_the_failed_roads_comparison_is_reported(real):
    lab = real["validation"]["labels_check"]
    assert lab["available"] and lab["wet_n"] > 100 and lab["dry_n"] > 100
    assert 0 <= lab["wet_failed_share"] <= 1 and 0 <= lab["dry_failed_share"] <= 1


def test_N12_shared_inputs_were_not_changed_by_the_run(real):
    meta = real["meta"]
    assert meta["inputs_before"] == meta["inputs_after"] and set(meta["inputs_before"]) == {"marks", "bridges", "segments", "segments_geom", "dem30"}
    assert dem.sha256(P.marks) == meta["inputs_before"]["marks"]
    assert dem.sha256(P.bridges) == meta["inputs_before"]["bridges"]
    assert dem.sha256(P.seg_geom) == meta["inputs_before"]["segments_geom"]
    if P.dem30.exists():  # the 30 m ground other code reads
        assert dem.sha256(P.dem30) == meta["inputs_before"]["dem30"]
    # segments.parquet is not compared with today's file: other work adds columns to it, and what matters
    # here, that it holds the same roads in the same order, is what load_depth checks
    assert meta["git_code_differs_from_commit"] is not True  # None where git could not be asked


@pytest.mark.network
def test_N13_a_live_tile_fetch_returns_10m_ground():
    tile = (355, -826)  # Asheville
    arr, transform, crs = dem._fetch(dem.fetch_bounds(tile))
    dem.check_reply(arr, transform, crs, tile)
    assert arr.shape[0] > 1080 and arr.shape[1] > 1080 and np.isfinite(arr).mean() > 0.99
    assert 500 < np.nanmedian(arr) < 900  # metres, not feet
