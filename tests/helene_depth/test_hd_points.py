"""Road points, bridges, depth and the per-segment summary (run spec D10-D14)."""
import geopandas as gpd
import numpy as np
import pytest
import shapely

import hd_helpers as H
from src.pipeline import helene_depth as hd


def to_m(geom):
    return gpd.GeoSeries([geom], crs=4326).to_crs(hd.CRS_M).iloc[0]


def flat_line(level, y=50.0, x=(-100.0, 700.0)):
    return [H.mk_line("A", [(x[0], y, level), (x[1], y, level)], origin=True)]


def one(per, seg_id="r"):
    return per[per.seg_id == seg_id].iloc[0]


def test_D1_a_300_m_road_gets_11_points_30_m_apart():
    x, y, part, step = hd.segment_points(to_m(H.road((0, 0), (300, 0))))
    assert len(x) == 11 and step == pytest.approx(30.0, abs=1e-3)
    assert np.hypot(np.diff(x), np.diff(y)) == pytest.approx(30.0, abs=1e-3)  # metres: in degrees it would be 0.0003
    assert set(part) == {0}
    assert len(hd.segment_points(to_m(H.road((0, 0), (310, 0))))[0]) == 12  # never wider than 30 m


def test_D2_a_road_shorter_than_30_m_gets_both_ends():
    x, y, _, step = hd.segment_points(to_m(H.road((0, 0), (20, 0))))
    assert len(x) == 2 and step == pytest.approx(20.0, abs=1e-3)
    assert np.hypot(x[1] - x[0], y[1] - y[0]) == pytest.approx(20.0, abs=1e-3)


def test_D3_a_multi_part_road_is_walked_part_by_part_and_an_empty_one_is_counted():
    multi = shapely.MultiLineString([H.road((0, 0), (60, 0)), H.road((200, 0), (260, 0))])
    x, _, part, _ = hd.segment_points(to_m(multi))
    assert list(part) == [0, 0, 0, 1, 1, 1]
    assert len(hd.segment_points(shapely.LineString())[0]) == 0 and len(hd.segment_points(None)[0]) == 0
    # the gap between the two parts is not a pair: a segment kept only at the two inner ends is not assessed
    pts = H.mk_pts([2.0] * 6, kept=[0, 0, 1, 1, 0, 0], part=part)
    assert not one(hd.summarise(pts, [H.mk_line("A", [(0, 0, 1.0), (9, 0, 1.0)])], []), "s1").y_helene_depth_assessed
    seg = H.seg_table({"multi": multi, "empty": shapely.LineString()})
    pts, n_empty = hd.candidates(flat_line(100.0), seg)
    assert n_empty == 1 and set(pts.seg_id) == {"multi"} and list(pts.i) == [0, 1, 2, 0, 1, 2]


def test_D4_depth_is_water_level_minus_ground(tmp_path):
    ground = H.mk_ground(tmp_path, lambda x, y: 100.0)
    seg = H.seg_table({"r": H.road((0, 0), (300, 0))})
    pts, per, counts = hd.build(flat_line(101.5), ground, H.NO_BRIDGES, seg, [])
    assert pts.depth.values == pytest.approx(1.5, abs=1e-3) and pts.kept.all()
    r = one(per)
    assert r.y_helene_depth_assessed and r.y_helene_depth_max_m == pytest.approx(1.5, abs=1e-3)
    assert r.y_helene_depth_band == "1 to 2 m" and r.y_helene_depth_wet_share == 1.0 and r.n_helene_depth_marks == 2
    assert counts["segments_sampled"] == 1 and counts["points_kept"] == 11


def test_D5_water_below_the_ground_is_dry_never_negative(tmp_path):
    ground = H.mk_ground(tmp_path, lambda x, y: 103.0)
    pts, per, _ = hd.build(flat_line(101.5), ground, H.NO_BRIDGES, H.seg_table({"r": H.road((0, 0), (300, 0))}), [])
    assert (pts.depth == 0).all()
    r = one(per)
    assert r.y_helene_depth_assessed and r.y_helene_depth_max_m == 0.0 and r.y_helene_depth_band == "dry"
    assert r.y_helene_depth_wet_share == 0.0 and r.y_helene_depth_point_max_m == 0.0
    assert [hd.band(v) for v in (0, 0.29, 0.3, 0.99, 1.0, 2.0, 7)] == ["dry", "under 0.3 m", "0.3 to 1 m", "0.3 to 1 m", "1 to 2 m", "over 2 m", "over 2 m"]
    with pytest.raises(ValueError):
        hd.band(float("nan"))  # a missing depth is never given a band


def test_D6_a_road_with_one_low_end_reports_the_low_end_not_the_midpoint(tmp_path):
    ground = H.mk_ground(tmp_path, lambda x, y: 105.0 - 0.01 * x)  # 105 m at the west end, 99 m at the east end
    pts, per, _ = hd.build(flat_line(100.0), ground, H.NO_BRIDGES, H.seg_table({"r": H.road((0, 0), (600, 0))}), [])
    r = one(per)
    assert 0.6 < r.y_helene_depth_max_m < 1.0 and r.y_helene_depth_point_max_m == pytest.approx(1.0, abs=0.05)
    midpoint = pts.iloc[len(pts) // 2]
    assert midpoint.depth == 0.0  # what a midpoint-only reading would have reported
    assert 0 < r.y_helene_depth_wet_share < 0.25


def test_D7_points_near_a_bridge_are_set_aside_but_not_near_a_culvert(tmp_path):
    path = H.mk_bridges(tmp_path / "s.parquet", [(0, 0, "Bridge"), (1000, 0, "Concrete Box Culvert"), (2000, 0, "Pipe or Culvert")])
    bx, by = hd.load_bridges(path)
    assert len(bx) == 1  # the culvert and the pipe carry the road on fill: the ground there is the road
    px, py = np.array([20.0, 59.0, 61.0, 1000.0]) + H.X0, np.full(4, H.Y0)
    assert list(hd.near_bridges(px, py, bx, by)) == [True, True, False, False]
    assert not hd.near_bridges(px, py, *H.NO_BRIDGES).any()


def flat_part(n):
    return np.zeros(n, dtype=int), np.full(n, 30.0), np.zeros(n, dtype=bool)


def test_D8_a_sharp_notch_is_set_aside_but_a_gentle_sag_is_not():
    dip = [100.0] * 4 + [96.0] + [100.0] * 4
    assert list(np.flatnonzero(hd.set_aside(dip, *flat_part(9)))) == [4]
    wide = [100.0] * 3 + [96.0, 96.0] + [100.0] * 3  # two points wide: the neighbours two away see it
    assert list(np.flatnonzero(hd.set_aside(wide, *flat_part(8)))) == [3, 4]
    sag = [100, 99.5, 99, 98.5, 98, 98.5, 99, 99.5, 100]
    assert not hd.set_aside(sag, *flat_part(9)).any()
    assert not hd.set_aside([96.0] * 9, *flat_part(9)).any()  # a road that is low all along is a real low road
    part = np.array([0, 0, 0, 0, 1, 1, 1, 1, 1])  # the dip is the first point of another part: no notch across parts
    assert not hd.set_aside([100.0] * 4 + [96.0] + [100.0] * 4, part, np.full(9, 30.0), np.zeros(9, dtype=bool)).any()
    # blank ground decides nothing: a blank point is not a notch, and a blank neighbour proves none
    assert not hd.set_aside([100.0, 100.0, np.nan, 100.0, 100.0], *flat_part(5)).any()
    assert not hd.set_aside([np.nan, np.nan, 96.0, np.nan, np.nan], *flat_part(5)).any()


def test_D9_a_steep_bank_beside_a_set_aside_point_is_set_aside_too():
    part, step, _ = flat_part(5)
    seed = np.array([True, False, False, False, False])
    assert list(hd.set_aside([599, 603, 608, 608, 608], part, step, seed)) == [True, True, False, False, False]
    assert list(hd.set_aside([599, 599.2, 599.3, 599.3, 599.3], part, step, seed)) == [True, False, False, False, False]
    # it works in both directions, and a bank that is still climbing at the end of the road keeps its last point
    seed_end = np.array([False, False, False, False, True])
    assert list(hd.set_aside([608, 608, 608, 603, 599], part, step, seed_end)) == [False, False, False, True, True]
    assert list(hd.set_aside([599, 603, 608, 613, 618], part, step, seed)) == [True, True, True, True, False]
    assert list(hd.set_aside([599, 603, 608, 608, 608], part, step, seed, rules=("bridge",))) == list(seed)


def bank(x, y):
    return 599.0 + 9.0 * np.clip(x / 60.0, 0, 1)  # river bed under a bridge at x = 0, road level from x = 60


def test_D10_without_the_bridge_rules_the_bridge_reading_becomes_the_depth(tmp_path):
    ground = H.mk_ground(tmp_path, bank)
    seg = H.seg_table({"r": H.road((0, 0), (300, 0))})
    bridges = hd.load_bridges(H.mk_bridges(tmp_path / "s.parquet", [(0, 0, "Bridge")]))
    lines = flat_line(604.4)
    _, off, _ = hd.build(lines, ground, bridges, seg, [], rules=())
    assert one(off).y_helene_depth_point_max_m > 5 and one(off).y_helene_depth_max_m > 0.5  # the river bed, read as road
    pts, on, counts = hd.build(lines, ground, bridges, seg, [])
    assert one(on).y_helene_depth_max_m == 0.0 and one(on).y_helene_depth_band == "dry"
    assert one(on).n_helene_depth_set_aside >= 2 and counts["points_set_aside"] == pts.aside.sum()
    assert not pts.kept[pts.aside].any()


LINE = [H.mk_line("A", [(0, 0, 1.0), (9, 0, 1.0)])]


def test_D11_one_lone_deep_point_cannot_set_the_headline():
    r = one(hd.summarise(H.mk_pts([0, 0, 3, 0, 0]), LINE, []), "s1")
    assert r.y_helene_depth_max_m == 0.0 and r.y_helene_depth_point_max_m == 3.0 and r.y_helene_depth_band == "dry"
    r = one(hd.summarise(H.mk_pts([0, 2, 3, 0]), LINE, []), "s1")
    assert r.y_helene_depth_max_m == 2.0 and r.y_helene_depth_band == "over 2 m"


def test_D12_share_under_water_leaves_set_aside_points_out_of_both_sides():
    pts = H.mk_pts([1.0, 0.0, 9.0, 0.5], kept=[1, 1, 0, 1], aside=[0, 0, 1, 0])
    r = one(hd.summarise(pts, LINE, []), "s1")
    assert r.y_helene_depth_wet_share == pytest.approx(2 / 3)  # 2 wet of 3 kept; the bridge point is in neither
    assert r.n_helene_depth_points == 3 and r.n_helene_depth_set_aside == 1 and r.y_helene_depth_point_max_m == 1.0


def test_D13_a_missing_bridge_list_stops_the_run_and_names_the_file(tmp_path, mini_root):
    with pytest.raises(hd.DepthError, match="nowhere.parquet"):
        hd.load_bridges(tmp_path / "nowhere.parquet")
    bad = tmp_path / "bad.parquet"
    H.mk_bridges(bad, [(0, 0, "Bridge")])
    import pandas as pd

    pd.read_parquet(bad).drop(columns="Struct_Type").to_parquet(bad)
    with pytest.raises(hd.DepthError, match="Struct_Type"):
        hd.load_bridges(bad)
    mini_root.p.bridges.unlink()  # the whole command refuses too, and writes nothing
    with pytest.raises(hd.DepthError, match="helene_structures.parquet"):
        hd.run(mini_root.root, say=lambda *_: None)
    assert list(mini_root.p.out.glob("flood_helene_depth*")) == []


def test_D14_a_segment_with_no_neighbouring_kept_points_is_blank_not_zero():
    per = hd.summarise(H.mk_pts([2.0] * 5, kept=[1, 0, 1, 0, 1]), LINE, [])
    r = one(per, "s1")
    assert not r.y_helene_depth_assessed and r.n_helene_depth_points == 3
    row = hd.table(per, ["s0", "s1"]).set_index("seg_id").loc["s1"]
    assert not row.y_helene_depth_assessed and np.isnan(row.y_helene_depth_max_m)
    assert row.isna()["y_helene_depth_band"] and row.isna()["y_helene_depth_conf"]


def test_D15_messy_structure_types_are_sorted_into_bridges_and_culverts():
    culverts = ["Concrete Box Culvert", "Pipe or Culvert", "RC Arch Culvert", "CM Pipe Arch", "RCBC", "3 sided RCBC",
                "CMP", "CMPA", "CMP Arch", "Corrugated Metal Arch", "Aluminum plate arch", "Multi-Plate Arch Pipe",
                "aluminum arch culvert"]  # fmt: skip
    bridges = ["Bridge", "Arch Spandrel", "RC Luten Arch", "Timber on I Beam", "Cored Slab", "PCG", "Steel Thru Truss",
               "Plate Girder", "", None, float("nan")]  # fmt: skip
    assert [k for k in culverts if hd.is_bridge(k)] == []
    assert [k for k in bridges if not hd.is_bridge(k)] == []


def test_D16_ties_and_two_streams_are_settled_by_fixed_rules():
    pts = H.mk_pts([1, 1, 0, 1, 1], along=[10, 20, 0, 400, 500], high=[1, 1, 1, 0, 0], group=["A", "A", "A", "B", "B"])
    r = one(hd.summarise(pts, LINE, []), "s1")  # two pairs tie at 1 m: the first in road order speaks
    assert r.y_helene_depth_max_m == 1.0 and r.y_helene_depth_mark_dist_m == 20.0
    assert r.y_helene_depth_conf == "high" and r.y_helene_depth_stream == "A"
    pts = H.mk_pts([0.5, 2.0, 0], along=[10, 300, 0], high=[1, 0, 1], group=["A", "B", "B"])
    r = one(hd.summarise(pts, LINE, []), "s1")  # the stream of the deeper point of the pair; low if either is low
    assert r.y_helene_depth_stream == "B" and r.y_helene_depth_conf == "low" and r.y_helene_depth_mark_dist_m == 300.0
    dry = H.mk_pts([0, 0, 0, 0], along=[10, 20, 30, 400], high=[1, 1, 0, 0], group=["Beta", "Beta", "Alpha", "Alpha"])
    r = one(hd.summarise(dry, LINE, []), "s1")  # dry and split evenly: the alphabetically first stream
    assert r.y_helene_depth_stream == "Alpha" and r.y_helene_depth_mark_dist_m == 25.0 and r.y_helene_depth_conf == "high"
