"""Tying cameras to road segments."""
import pandas as pd
import pytest

from src.pipeline import cctv

I40, NC55 = "ncdot:10000040092:1.000", "ncdot:30000055092:2.000"


def test_M1_distances_are_in_metres(fake, segs):
    cams = fake.cameras(1, lat=35.80045, lon=-78.605)        # 0.00045 degrees of latitude is about 50 m
    out = cctv.match_cameras(cams, segs)
    assert out.seg_id.tolist() == [I40] and 45 < out.seg_dist_m.iloc[0] < 55


def test_M2_camera_far_from_every_road_is_left_blank(fake, segs, capsys):
    cams = fake.cameras(2, lat=[35.85, 35.80045], lon=[-78.55, -78.605])
    out = cctv.match_cameras(cams, segs)
    assert "1 matched within 100 m" in capsys.readouterr().out and int(out.seg_id.isna().sum()) == 1   # counted, and kept in the file
    assert out.seg_id.isna().tolist() == [True, False]
    assert out.match_rule.isna().tolist() == [True, False] and out.seg_dist_m.isna().tolist() == [True, False]


def test_M3_camera_named_for_a_route_beats_a_nearer_cross_street(fake, segs):
    # about 18 m east of NC-55 and 44 m north of I-40
    cams = fake.cameras(2, lat=35.8004, lon=-78.5998, highway=["I-40", "Other"])
    out = cctv.match_cameras(cams, segs)
    assert out.seg_id.tolist() == [I40, NC55] and out.match_rule.tolist() == ["route", "nearest"]
    assert out.seg_dist_m.iloc[0] > out.seg_dist_m.iloc[1]


@pytest.mark.parametrize("name,parsed", [("I-40", ("1", 40)), ("US-70 BUS", ("2", 70)), ("US 29", ("2", 29)),
                                         ("NC-540", ("3", 540)), ("nc-12", ("3", 12)), ("Other", None),
                                         ("Edwards Mill", None), (None, None), ("", None)])
def test_M4_odd_highway_names_fall_back_to_nearest(fake, segs, name, parsed):
    assert cctv.parse_highway(name) == parsed
    out = cctv.match_cameras(fake.cameras(1, lat=35.8004, lon=-78.5998, highway=name), segs)
    assert out.seg_id.tolist() == [I40 if parsed == ("1", 40) else NC55]


def test_M5_camera_file_contract(fake, segs, tmp_path):
    cams = fake.cameras(3, lat=[35.80045, 35.85, 35.8004], lon=[-78.605, -78.55, -78.5998])
    cctv.write_cameras(cctv.match_cameras(cams, segs), tmp_path / "cctv" / "cameras.parquet")
    back = pd.read_parquet(tmp_path / "cctv" / "cameras.parquet")
    assert list(back.columns) == cctv.CAMERA_COLS == ["camera_id", "status", "image_status", "highway", "county",
                                                      "location_name", "lat", "lon", "image_url", "seg_id",
                                                      "seg_dist_m", "match_rule"]
    assert back.camera_id.is_unique and len(back) == 3
    assert set(back.seg_id.dropna()) <= set(segs.seg_id)
