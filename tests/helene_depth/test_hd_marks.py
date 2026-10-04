"""Reading the surveyed marks (run spec D1-D3)."""
import json

import numpy as np
import pytest

import hd_helpers as H
from src.pipeline import helene_depth as hd


def test_A1_feet_become_metres(tmp_path):
    f = H.mark(1, 0, 0, 0.0)
    f["properties"]["HWM_Elevation__ft_"] = 2100.75
    marks, _ = H.marks_from(tmp_path, [f])
    assert marks.wse_m.iloc[0] == pytest.approx(640.31, abs=0.005)


def test_A2_a_taped_height_of_zero_is_blank_not_a_depth_of_zero(tmp_path):
    a, b = H.mark(1, 0, 0, 600.0), H.mark(2, 100, 0, 600.5)
    a["properties"]["Measured_Height__ft_"] = 0
    b["properties"]["Measured_Height__ft_"] = 2.5
    marks, counts = H.marks_from(tmp_path, [a, b])
    assert np.isnan(marks.tape_m.iloc[0]) and marks.tape_m.iloc[1] == pytest.approx(0.762)
    assert counts["taped"] == 1


def test_A3_a_mark_outside_the_box_is_dropped_and_counted(tmp_path):
    out = H.mark(2, 0, 0, 600.0)
    out["geometry"]["coordinates"] = [-80.0, 35.5]  # east of the box
    nowhere = H.mark(3, 0, 0, 600.0)
    nowhere["geometry"] = None
    marks, counts = H.marks_from(tmp_path, [H.mark(1, 0, 0, 600.0), out, nowhere])
    assert list(marks.mark_id) == ["1"] and counts["outside_box"] == 2


def test_A4_two_creeks_with_one_name_stay_separate(tmp_path):
    feats = [H.mark(i, 100 * i, 0, 600 + i, stream="Cane Creek", watershed="French Broad River") for i in (1, 2, 3)]
    feats += [H.mark(10 + i, 100 * i, 3000, 700 + i, stream="Cane Creek", watershed="Nolichucky River", n=i) for i in (1, 2, 3)]
    marks, counts = H.marks_from(tmp_path, feats)
    assert marks.stream.nunique() == 1  # by name alone they would be one creek
    lines = hd.build_lines(marks)
    assert counts["groups"] == 2 and [line.group for line in lines] == ["Cane Creek | French Broad River", "Cane Creek | Nolichucky River"]
    assert all(len(line.x) == 3 and np.all(np.diff(line.s) < 150) for line in lines)  # no 3 km jump inside a line


def test_A5_a_missing_column_stops_the_run_and_is_named(tmp_path):
    f = H.mark(1, 0, 0, 600.0)
    del f["properties"]["Watershed"]
    with pytest.raises(hd.DepthError, match="Watershed"):
        H.marks_from(tmp_path, [f])


def test_A6_an_empty_or_missing_file_stops_the_run(tmp_path):
    with pytest.raises(hd.DepthError, match="no marks"):
        H.marks_from(tmp_path, [])
    with pytest.raises(hd.DepthError, match="missing"):
        hd.load_marks(tmp_path / "nowhere.geojson")
    only_bad = H.mark(1, 0, 0, 0.0)  # every mark unusable is as bad as none
    with pytest.raises(hd.DepthError, match="no usable marks"):
        H.marks_from(tmp_path, [only_bad])


def test_A7_a_blank_or_zero_water_height_is_dropped_and_counted(tmp_path):
    zero, blank = H.mark(2, 100, 0, 0.0), H.mark(3, 200, 0, 600.0)
    blank["properties"]["HWM_Elevation__ft_"] = None
    marks, counts = H.marks_from(tmp_path, [H.mark(1, 0, 0, 600.0), zero, blank])
    assert list(marks.mark_id) == ["1"] and counts["no_water_height"] == 2


def test_A8_a_repeated_mark_id_is_used_once(tmp_path):
    first, again = H.mark(7, 0, 0, 600.0), H.mark(7, 50, 0, 650.0)
    marks, counts = H.marks_from(tmp_path, [first, again, H.mark(8, 100, 0, 601.0)])
    assert list(marks.mark_id) == ["7", "8"] and counts["repeated_id"] == 1
    assert marks.wse_m.iloc[0] == pytest.approx(600.0)  # the first one in the file is the one kept


def test_A9_poorly_graded_marks_do_not_draw_the_line(tmp_path, monkeypatch):
    feats = [H.mark(1, 0, 0, 600.0), H.mark(2, 100, 0, 650.0, quality="Poor"),
             H.mark(3, 200, 0, 660.0, quality="Very Poor"), H.mark(4, 300, 0, 603.0, quality="Fair")]  # fmt: skip
    marks, counts = H.marks_from(tmp_path, feats)
    assert list(marks.draws) == [True, False, False, True] and counts["draw_the_line"] == 2
    (line,) = hd.build_lines(marks)
    assert list(line.z) == pytest.approx([600.0, 603.0])
    # without the rule the two bad marks would bend the line
    monkeypatch.setitem(hd.SETTINGS, "NO_LINE_GRADES", [])
    (line,) = hd.build_lines(H.marks_from(tmp_path, feats)[0])
    assert list(line.z) == pytest.approx([600.0, 650.0, 660.0, 603.0])


def test_A10_point_numbers_sort_as_numbers(tmp_path):
    feats = [H.mark(1, 900, 0, 609.0, n="10"), H.mark(2, 100, 0, 601.0, n="2"), H.mark(3, 0, 0, 600.0, n="1")]
    path = H.mk_marks(tmp_path / "m.geojson", feats)
    assert all(isinstance(f["properties"]["Point_Number_on_Stream"], str) for f in json.loads(path.read_text())["features"])
    marks, _ = hd.load_marks(path)
    assert list(marks.point_no) == [1, 2, 10]  # as text, "10" would come before "2"
    (line,) = hd.build_lines(marks)
    assert list(line.z) == pytest.approx([600.0, 601.0, 609.0])
