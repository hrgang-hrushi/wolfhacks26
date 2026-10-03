"""Route + milepost matching and the count-checked layer pull."""
import pandas as pd
import pytest

from src.pipeline import milepost
from src.pipeline.milepost import LayerError, fetch_table, overlaps, points_on_segments, route_key, weighted_mean
from tests.crashes.conftest import R1, R2


def test_M1_route_key_reads_text_float_and_int_and_blanks_junk():
    k = route_key(pd.Series(["40001001008", 40001001008.0, 40001001008, "ROUTE NOT FOUND", None]))
    assert k[:3].tolist() == [R1, R1, R1] and k[3:].isna().all()


def test_M2_overlap_is_the_shared_length(segs):
    parts = pd.DataFrame({"rid": pd.array([R1, R1, R2], dtype="Int64"), "s": [0.5, 2.5, 0.0], "e": [1.5, 3.25, 9.0]})
    m = overlaps(segs, parts, "s", "e")
    got = {(r.seg_id, r.s): round(r.ov, 6) for r in m.itertuples()}
    assert got == {("a", 0.5): 0.5, ("b", 0.5): 0.5, ("c", 2.5): 0.25, ("z", 0.0): 0.5}


def test_M3_parts_that_only_touch_or_sit_on_another_route_do_not_match(segs):
    parts = pd.DataFrame({"rid": pd.array([R1, R1, 99, None], dtype="Int64"),
                          "s": [2.0, 2.2, 0.0, 0.0], "e": [3.0, 2.8, 1.0, 1.0]})   # touches b and c; in the gap
    assert overlaps(segs, parts, "s", "e").empty


def test_M4_points_go_to_the_segment_that_holds_their_milepost(segs):
    pts = pd.DataFrame({"rid": pd.array([R1, R1, R1, R2, 99, None], dtype="Int64"),
                        "mp": [0.2, 1.0, 2.5, 0.5, 0.2, 0.2]}, index=[10, 11, 12, 13, 14, 15])
    got = points_on_segments(segs, pts, "mp")
    assert got.index.tolist() == pts.index.tolist()
    # 1.0 is the end of a and the start of b: it counts once, for a. 2.5 is in the gap.
    assert got.tolist()[:4] == ["a", "a", pd.NA, "z"] and got[14:].isna().all()


def test_M5_weighted_mean_ignores_missing_values():
    m = pd.DataFrame({"seg_id": ["a", "a", "a", "b"], "v": [10.0, 30.0, None, None], "ov": [1.0, 3.0, 9.0, 1.0]})
    w = weighted_mean(m, "v")
    assert w.to_dict() == {"a": 25.0}


def test_M6_fetch_pulls_every_window_and_checks_the_count(fake_session):
    rows = [{"FID": i, "v": i * 2} for i in range(3, 5004)]          # ids need not start at 1
    s = fake_session(rows)
    d = fetch_table("http://layer", ["FID", "v"], window=2000, workers=2, session=s)
    assert sorted(d.FID) == list(range(3, 5004)) and (d.v == d.FID * 2).all()
    assert sum("outFields" in c for c in s.calls) == 3


def test_M7_fetch_fails_when_rows_do_not_equal_the_server_count(fake_session):
    rows = [{"FID": i} for i in range(1, 11)]
    with pytest.raises(LayerError, match="received 10 rows but the server counts 12"):
        fetch_table("http://layer", ["FID"], session=fake_session(rows, count=12))


def test_M8_fetch_fails_when_a_window_is_cut_short(fake_session):
    rows = [{"FID": i} for i in range(1, 11)]
    with pytest.raises(LayerError, match="more rows than one reply carries"):
        fetch_table("http://layer", ["FID"], window=10, session=fake_session(rows, limit=5))


def test_M9_an_error_reply_is_retried_then_raised(fake_session, monkeypatch):
    monkeypatch.setattr(milepost.time, "sleep", lambda s: None)
    rows = [{"FID": i} for i in range(1, 4)]
    assert len(fetch_table("http://layer", ["FID"], session=fake_session(rows, fail_first=2))) == 3
    with pytest.raises(LayerError, match="busy"):
        fetch_table("http://layer", ["FID"], session=fake_session(rows, fail_first=99))
