"""The water line along each stream and the level a road point takes from it (run spec D7-D9)."""
import random

import numpy as np
import pytest

import hd_helpers as H
from src.pipeline import helene_depth as hd


def at(lines, x, y):
    return hd.locate(lines, [x], [y]).iloc[0]


def test_C1_distances_along_the_line_are_in_metres(tmp_path):
    a, b = H.mark(1, 0, 0, 600.0), H.mark(2, 0, 0, 601.0)
    b["geometry"]["coordinates"][0] += 0.01  # 0.01 degree of longitude, about 905 m at this latitude
    (line,) = hd.build_lines(H.marks_from(tmp_path, [a, b])[0])
    assert 880 < line.s[1] < 930


def test_C2_level_between_two_marks_is_a_straight_line():
    lines = [H.mk_line("A", [(0, 0, 100.0), (400, 0, 104.0)])]
    r = at(lines, 100, 0)
    assert r.assessed and r.wse == pytest.approx(101.0) and r.along_m == pytest.approx(100.0) and r.side_m == pytest.approx(0.0)


def test_C3_a_point_takes_its_level_from_the_nearest_spot_on_the_line():
    lines = [H.mk_line("A", [(0, 0, 100.0), (400, 0, 104.0), (400, 400, 108.0)])]
    r = at(lines, 200, 50)  # foot at (200, 0), half way between the first two marks
    assert r.wse == pytest.approx(102.0) and r.side_m == pytest.approx(50.0) and (r.v0, r.v1) == (0, 1)
    r = at(lines, 450, 300)  # nearest spot is on the second leg, three quarters up
    assert r.wse == pytest.approx(107.0) and (r.v0, r.v1) == (1, 2)
    r = at(lines, 450, -30)  # outside the bend: the corner mark itself
    assert r.wse == pytest.approx(104.0) and r.along_m == pytest.approx(0.0) and not r.end_rule


def test_C4_between_two_streams_the_nearer_live_one_wins():
    b = H.mk_line("B", [(0, 200, 110.0), (400, 200, 110.0)])
    r = at([H.mk_line("A", [(0, 0, 100.0), (400, 0, 100.0)]), b], 200, 60)
    assert r.group == "A" and r.wse == pytest.approx(100.0) and r.side_m == pytest.approx(60.0)
    # stream A's marks are now 3 km apart, so the spot beside the point is more than 1 km from either: A is
    # silent there, and the farther stream, which has marks close by, answers instead
    r = at([H.mk_line("A", [(-1300, 0, 100.0), (1700, 0, 100.0)]), b], 200, 60)
    assert r.group == "B" and r.wse == pytest.approx(110.0) and r.side_m == pytest.approx(140.0)


def test_C5_two_marks_at_one_spot_are_averaged(tmp_path):
    feats = [H.mark(1, 0, 0, 100.0), H.mark(2, 0, 0, 102.0), H.mark(3, 300, 0, 103.0)]
    (line,) = hd.build_lines(H.marks_from(tmp_path, feats)[0])
    assert len(line.x) == 2 and line.z[0] == pytest.approx(101.0) and line.ids[0] == ("1", "2")
    r = hd.locate([line], [line.x[0] + 150], [line.y[0] + 5]).iloc[0]
    assert np.isfinite(r.wse) and r.wse == pytest.approx(102.0)  # no divide-by-zero from the doubled spot


def test_C6_a_stream_with_one_mark_gives_a_level_only_close_to_it():
    lines = [H.mk_line("A", [(0, 0, 100.0)])]
    r = at(lines, 99, 0)
    assert r.assessed and r.end_rule and not r.high and r.wse == pytest.approx(100.0) and (r.v0, r.v1) == (0, -1)
    assert not at(lines, 101, 0).assessed


def test_C7_past_the_last_mark_a_level_is_given_only_within_100_m(monkeypatch):
    lines = [H.mk_line("A", [(0, 0, 100.0), (400, 0, 104.0)])]
    r = at(lines, 499, 0)
    assert r.assessed and r.end_rule and not r.high and r.wse == pytest.approx(104.0)  # the last mark's own level
    assert not at(lines, 501, 0).assessed and np.isnan(at(lines, 501, 0).wse)
    assert not at(lines, -101, 0).assessed and at(lines, -99, 0).wse == pytest.approx(100.0)
    # marks close together: 150 m past the last one is within 300 m of the one before it, and still gets nothing
    close = [H.mk_line("A", [(0, 0, 100.0), (150, 0, 100.5), (300, 0, 101.0)])]
    assert not at(close, 450, 0).assessed and at(close, 390, 0).wse == pytest.approx(101.0)
    monkeypatch.setitem(hd.SETTINGS, "END_CAP_M", 1e9)  # without the cap the line would be stretched past its end
    assert at(lines, 501, 0).assessed


def test_C8_no_level_more_than_1_km_along_the_line_from_a_mark():
    lines = [H.mk_line("A", [(0, 0, 100.0), (2500, 0, 102.5)])]  # a gentle river: the level rule is not in play
    r = at(lines, 999, 10)
    assert r.assessed and r.wse == pytest.approx(100.999) and r.along_m == pytest.approx(999.0)
    assert not at(lines, 1001, 10).assessed  # not slid back to the 1,000 m point
    assert not at(lines, 1250, 10).assessed
    r = at(lines, 1501, 10)  # within 1 km of the upstream mark
    assert r.assessed and r.wse == pytest.approx(101.501) and r.along_m == pytest.approx(999.0)


def test_C9_confidence_is_high_within_250_m_of_a_mark():
    lines = [H.mk_line("A", [(0, 0, 100.0), (1000, 0, 101.0)])]
    assert at(lines, 249, 5).high
    r = at(lines, 251, 5)
    assert r.assessed and not r.high
    assert at(lines, 751, 5).high  # 249 m from the other mark


def test_C10_a_point_too_far_to_the_side_is_not_assessed_rather_than_dry():
    lines = [H.mk_line("A", [(0, 0, 100.0), (400, 0, 104.0)])]
    assert at(lines, 200, 299).assessed
    r = at(lines, 200, 301)
    assert not r.assessed and np.isnan(r.wse) and r.line == -1 and r.group is None
    assert not hd.locate([], [0.0], [0.0]).assessed.any()  # no lines at all: nothing is assessed


def test_C11_the_count_of_marks_behind_a_point(tmp_path):
    feats = [H.mark(1, 0, 0, 100.0), H.mark(2, 0, 0, 102.0), H.mark(3, 300, 0, 103.0), H.mark(4, 600, 0, 104.0)]
    lines = hd.build_lines(H.marks_from(tmp_path, feats)[0])
    x0, y0 = lines[0].x[0], lines[0].y[0]

    def behind(dx, dy):
        r = hd.locate(lines, [x0 + dx], [y0 + dy]).iloc[0]
        return hd.marks_behind(lines, int(r.line), int(r.v0), int(r.v1))

    assert behind(450, 5) == {"3", "4"}  # between two marks
    assert behind(650, 0) == {"4"}  # past the last mark
    assert behind(150, 5) == {"1", "2", "3"}  # one end is two marks merged
    assert hd.marks_behind(lines, -1, -1, -1) == set()


def test_C12_shuffled_rows_give_the_same_lines(tmp_path):
    feats = H.world_marks()
    a = hd.build_lines(H.marks_from(tmp_path, feats)[0])
    random.Random(3).shuffle(feats)
    b = hd.build_lines(H.marks_from(tmp_path, feats)[0])
    assert [line.group for line in a] == [line.group for line in b] == ["Alpha Creek | Test River", "Beta Branch | Test River"]
    for la, lb in zip(a, b):
        assert la.ids == lb.ids
        for f in ("x", "y", "s", "z"):
            assert np.array_equal(getattr(la, f), getattr(lb, f))


def test_C13_no_level_where_the_drawn_line_strays_far_from_the_nearer_mark(monkeypatch):
    # two marks 600 m apart that differ by 30 m: a dam, a fall or a steep reach lies between them, and a
    # straight line across it is a guess. A level is given only while it is within 2 m of the nearer mark's own
    lines = [H.mk_line("A", [(0, 0, 100.0), (600, 0, 130.0)])]
    r = at(lines, 30, 5)
    assert r.assessed and r.wse == pytest.approx(101.5) and r.lift_m == pytest.approx(1.5)
    assert not at(lines, 50, 5).assessed and np.isnan(at(lines, 50, 5).wse)  # 2.5 m from the mark's level: blank
    assert not at(lines, 300, 5).assessed
    r = at(lines, 580, 5)  # 1 m below the upper mark
    assert r.assessed and r.wse == pytest.approx(129.0) and r.lift_m == pytest.approx(1.0)
    # the blank point is not handed the mark's level by another route: no slide back along the line
    longer = [H.mk_line("A", [(-400, 0, 99.0), (0, 0, 100.0), (600, 0, 130.0)])]
    assert not at(longer, 50, 5).assessed
    gentle = [H.mk_line("A", [(0, 0, 100.0), (600, 0, 103.0)])]  # the same gap with a 3 m difference is fine throughout
    assert at(gentle, 300, 5).assessed and at(gentle, 300, 5).lift_m == pytest.approx(1.5)
    monkeypatch.setitem(hd.SETTINGS, "MAX_LIFT_M", 1e9)  # without the rule the middle of the steep gap gets a level
    assert at(lines, 300, 5).wse == pytest.approx(115.0)
