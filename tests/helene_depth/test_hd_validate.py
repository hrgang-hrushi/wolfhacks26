"""The error number: hidden marks, taped depths, the gate against the 30 m ground (run spec D17-D21, D23)."""
import json

import numpy as np
import pandas as pd
import pytest

import hd_helpers as H
from src.pipeline import helene_dem10 as dem
from src.pipeline import helene_depth as hd

QUIET = dict(say=lambda *_: None)


def row_marks(tmp_path, n, step, tape_every=0, slope=0.005):
    """n marks in a row, `step` m apart, on a gently rising water line."""
    feats = [H.mark(i + 1, step * i, 0, 600 + slope * step * i, tape_m=2.0 if tape_every and i % tape_every == 0 else 0.0)
             for i in range(n)]  # fmt: skip
    return H.marks_from(tmp_path, feats)[0]


def guess(hm, mark_id, stretch):
    return hm[(hm.mark_id == mark_id) & (hm.stretch == stretch)].iloc[0]


def test_E1_a_hidden_marks_own_level_never_enters_its_guess(tmp_path):
    marks = row_marks(tmp_path, 5, 200)
    before = guess(hd.hidden_mark_test(marks), "3", 0)
    lifted = marks.assign(wse_m=np.where(marks.mark_id == "3", marks.wse_m + 10, marks.wse_m))
    after = guess(hd.hidden_mark_test(lifted), "3", 0)
    assert before.assessed and after.guess == pytest.approx(before.guess)  # the guess did not move
    assert after.miss == pytest.approx(before.miss - 10)  # only the truth it is scored against did
    assert before.guess == pytest.approx(602.0) and before.n_hidden == 1


def test_E2_a_hidden_stretch_hides_every_mark_inside_it(tmp_path):
    marks = row_marks(tmp_path, 7, 100)  # at 0, 100, ... 600 m; mark 4 is the middle one
    clean = guess(hd.hidden_mark_test(marks), "4", 250)
    inside = marks.mark_id.isin(["2", "3", "5", "6"])  # the four neighbours within 250 m
    poisoned = guess(hd.hidden_mark_test(marks.assign(wse_m=np.where(inside, marks.wse_m + 50, marks.wse_m))), "4", 250)
    assert clean.n_hidden == 5 and poisoned.guess == pytest.approx(clean.guess) == pytest.approx(601.5)
    assert clean.along_m == pytest.approx(300.0)  # guessed from the marks 300 m either side
    # with only the mark itself hidden, the poisoned neighbours do move the guess: the stretch is what protects it
    assert guess(hd.hidden_mark_test(marks.assign(wse_m=np.where(inside, marks.wse_m + 50, marks.wse_m))), "4", 0).guess > 640


def test_E3_typical_and_worst_tenth_miss_are_hand_checkable():
    st = hd.miss_stats([-1.0, 2.0, -3.0, 4.0, np.nan])
    assert st == {"n": 4, "median": 2.5, "p75": 3.25, "p90": pytest.approx(3.7), "bias": 0.5}
    assert hd.miss_stats([]) == {"n": 0, "median": None, "p75": None, "p90": None, "bias": None}


def test_E4_the_tape_tests_use_only_taped_marks(tmp_path):
    marks = row_marks(tmp_path, 9, 100, tape_every=3)  # marks 1, 4 and 7 are taped; the rest hold 0 = not measured
    g10 = marks.wse_m.values - 2.0
    t = hd.tape_tests(marks, g10, hd.hidden_mark_test(marks))
    assert t["ground_only"]["n"] == 3 and t["ground_only"]["median"] == pytest.approx(0.0, abs=1e-9)
    # had the zeros been read as "0 m deep", all nine marks would be in, each missing by 2 m
    assert t["typical_taped_depth_m"] == pytest.approx(2.0)
    g10[0] = np.nan  # a taped mark with no ground under it cannot be scored
    assert hd.tape_tests(marks, g10, hd.hidden_mark_test(marks))["ground_only"]["n"] == 2


def test_E5_the_end_to_end_number_uses_the_hidden_mark_guess(tmp_path):
    marks = row_marks(tmp_path, 9, 150, tape_every=3)
    g10 = marks.wse_m.values - 2.0
    hm = hd.hidden_mark_test(marks)
    honest = hd.tape_tests(marks, g10, hm)
    assert honest["end_to_end"]["n"] == 2  # marks 4 and 7; mark 1 is the first on its line and cannot be guessed
    assert honest["ground_only"]["n"] == 3
    off = hm.assign(guess=hm.guess + 0.7)  # the guesses are 0.7 m out; the marks' own levels are untouched
    moved = hd.tape_tests(marks, g10, off)
    assert moved["end_to_end"]["median"] == pytest.approx(honest["end_to_end"]["median"] + 0.7)
    assert moved["ground_only"] == honest["ground_only"]


def _hm(n, along, miss=0.4):
    return pd.DataFrame({"mark_id": [str(i) for i in range(n)], "group": "A", "stretch": 0, "assessed": True,
                         "guess": 600.0, "along_m": along, "n_hidden": 1, "miss": miss})  # fmt: skip


def test_E6_a_band_with_under_30_marks_says_too_few():
    few, enough = hd.band_table(_hm(29, 50.0))[0], hd.band_table(_hm(30, 50.0))[0]
    assert few["band"] == "0-100 m" and few["n"] == 29 and few["too_few"] and few["median"] == pytest.approx(0.4)
    assert enough["n"] == 30 and not enough["too_few"]
    # a mark guessed twice in one band (two stretches) counts once, by its smallest stretch
    twice = pd.concat([_hm(30, 50.0, miss=0.4), _hm(30, 60.0, miss=9.0).assign(stretch=250)])
    assert hd.band_table(twice)[0]["n"] == 30 and hd.band_table(twice)[0]["median"] == pytest.approx(0.4)
    edges = hd.band_table(_hm(4, [0.0, 100.0, 100.1, 1000.0]))  # 0 and 100 belong to the first band
    assert [b["n"] for b in edges] == [2, 1, 0, 1]


def flat_marks(tmp_path):
    return H.marks_from(tmp_path, [H.mark(i + 1, 100 * i, 0, 600.0, tape_m=2.0) for i in range(6)])[0]


def test_E7_if_10m_is_not_better_than_30m_the_build_refuses(tmp_path):
    marks = flat_marks(tmp_path)  # water at 600 m, taped 2 m deep: the true ground is 598 m
    exact, off_by_1 = H.mk_dem30(tmp_path / "exact.tif", lambda x, y: 598.0), H.mk_dem30(tmp_path / "off.tif", lambda x, y: 599.0)
    g10 = np.full(len(marks), 598.2)
    with pytest.raises(hd.DepthError, match="not better than the 30 m"):
        hd.gate_30m(marks, g10, exact)
    ok = hd.gate_30m(marks, g10, off_by_1)
    assert ok["passed"] and not ok["skipped"] and ok["n"] == 6
    assert ok["miss10"] == pytest.approx(0.2) and ok["miss30"] == pytest.approx(1.0)
    with pytest.raises(hd.DepthError, match="allowed 0.25"):  # better than 30 m, but still too far from the tape
        hd.gate_30m(marks, np.full(len(marks), 598.4), off_by_1)


def test_E8_the_range_resamples_whole_streams_and_repeats_for_the_same_seed():
    values = np.r_[0.0, np.full(99, 10.0)]
    groups = np.r_[["lonely"], np.full(99, "busy")]
    lo, hi = hd.boot_range(values, groups)
    assert (lo, hi) == (0.0, 10.0)  # resampling the 100 marks instead of the 2 streams would give 10 to 10
    assert hd.boot_range(values, groups) == [lo, hi] and hd.boot_range(values, groups, seed=1) == [lo, hi]
    rng = np.random.default_rng(5)
    v, g = rng.normal(0, 1, 300), rng.integers(0, 12, 300).astype(str)
    assert hd.boot_range(v, g, seed=0) == hd.boot_range(v, g, seed=0) != hd.boot_range(v, g, seed=1)
    assert hd.boot_range([], []) == [None, None]


def test_E9_poorly_graded_marks_are_scored_apart(mini_root):
    marks, _ = hd.load_marks(mini_root.p.marks)
    hm = hd.hidden_mark_test(marks)
    poor = set(marks.mark_id[~marks.draws])
    assert poor == {"41", "42"} and set(hm.mark_id[hm.stretch == -1]) == poor
    assert not set(hm.mark_id[hm.stretch >= 0]) & poor  # never among the marks the headline is built from
    ground = dem.Ground(mini_root.p.tiles)
    pre, _ = hd.pre_checks(marks, ground.sample(marks.lon.values, marks.lat.values), mini_root.p.dem30)
    assert pre["hidden_mark"]["poor_grades"]["n"] == 2 and pre["hidden_mark"]["overall"]["n"] == 36
    assert pre["hidden_mark"]["poor_grades"]["median"] > 0.4 > 0.1 > pre["hidden_mark"]["overall"]["median"]


def test_E10_two_runs_give_identical_files(mini_root):
    hd.run(mini_root.root, **QUIET)
    names = (hd.DEPTH, hd.POINTS, hd.VALID)
    first = {n: dem.sha256(mini_root.p.out / n) for n in names}
    hd.run(mini_root.root, **QUIET)
    assert {n: dem.sha256(mini_root.p.out / n) for n in names} == first
    assert "created_utc" not in json.loads((mini_root.p.out / hd.VALID).read_text())  # the time lives in the notes file only
    assert "created_utc" in json.loads((mini_root.p.out / hd.META).read_text())


def test_E11_a_missing_30m_file_refuses_unless_the_skip_is_asked_for_and_recorded(mini_root):
    mini_root.p.dem30.unlink()
    with pytest.raises(hd.DepthError, match="--skip-30m-check"):
        hd.run(mini_root.root, **QUIET)
    assert list(mini_root.p.out.glob("flood_helene_depth*")) == []
    with pytest.raises(SystemExit):  # the command line refuses the same way
        hd.main(["--root", str(mini_root.root)])
    hd.main(["--root", str(mini_root.root), "--skip-30m-check"])
    meta = json.loads((mini_root.p.out / hd.META).read_text())
    assert meta["skip_30m_check"] is True and meta["inputs_before"]["dem30"] is None and meta["inputs_after"]["dem30"] is None
    v30 = json.loads((mini_root.p.out / hd.VALID).read_text())["tape"]["vs_30m"]
    assert v30["skipped"] is True and v30["miss30"] is None and v30["miss10"] < 0.25
    assert len(hd.load_depth(mini_root.root)) == 12


def test_E12_the_saved_label_comparison_describes_the_written_table(built_root):
    saved = json.loads((built_root.p.out / hd.VALID).read_text())
    tab = pd.read_parquet(built_root.p.out / hd.DEPTH)
    lab = pd.read_parquet(built_root.p.seg)
    d = tab[tab.y_helene_depth_assessed].merge(lab, on="seg_id")
    wet, dry = d[d.y_helene_depth_max_m >= 0.3], d[d.y_helene_depth_max_m == 0]
    assert saved["labels_check"] == {"available": True, "wet_n": len(wet), "wet_failed_share": float(wet.y_helene_failed.mean()),
                                     "dry_n": len(dry), "dry_failed_share": float(dry.y_helene_failed.mean())}  # fmt: skip
    assert len(wet) >= 3 and len(dry) >= 2 and saved["labels_check"]["wet_failed_share"] > saved["labels_check"]["dry_failed_share"]
    assert saved["build"]["segments_assessed"] == int(tab.y_helene_depth_assessed.sum())
    built_root.p.seg.unlink()  # no label table: said so, not invented
    assert hd.labels_check(tab, built_root.p.seg) == {"available": False}


def test_E13_validate_only_creates_and_changes_no_file(mini_root, built_root, capsys):
    before = H.snapshot(mini_root.p.out)
    mini_root.p.bridges.unlink()  # it must stop before the bridge list is even read
    hd.main(["--root", str(mini_root.root), "--validate-only"])
    assert H.snapshot(mini_root.p.out) == before and not list(mini_root.p.out.glob("flood_helene_depth*"))
    assert "hidden marks: typical miss" in capsys.readouterr().out
    before = H.snapshot(built_root.p.out)  # and it leaves an existing set of outputs exactly as it was
    hd.main(["--root", str(built_root.root), "--validate-only"])
    assert H.snapshot(built_root.p.out) == before


def test_E14_no_evidence_means_refusal_not_a_pass(tmp_path, mini_root):
    untaped = H.marks_from(tmp_path, [H.mark(i + 1, 100 * i, 0, 600.0) for i in range(6)])[0]
    with pytest.raises(hd.DepthError, match="no taped mark"):
        hd.gate_30m(untaped, np.full(6, 598.0), tmp_path / "none.tif", skip=True)
    with pytest.raises(hd.DepthError, match="no line-drawing mark has 10 m ground"):
        hd.tripwire(untaped, np.full(6, np.nan))
    few = H.marks_from(tmp_path, [H.mark(i + 1, 100 * i, 0, 600.0, tape_m=2.0) for i in range(6)])[0]
    H.mk_dem30(tmp_path / "d.tif", lambda x, y: 599.0)
    with pytest.raises(hd.DepthError, match="no error number can be stated"):  # 4 guesses, 30 needed
        hd.pre_checks(few, np.full(6, 598.0), tmp_path / "d.tif")


def test_E15_an_empty_distance_band_reports_no_marks_and_gives_a_blank_typical_miss():
    bands = hd.band_table(_hm(40, 50.0))
    far = bands[3]
    assert far == {"band": "500-1000 m", "lo": 500, "hi": 1000, "n": 0, "median": None, "p90": None, "too_few": True}
    assert hd._typical_miss(bands, 50.0) == pytest.approx(0.4) and np.isnan(hd._typical_miss(bands, 700.0))
    pts = H.mk_pts([1.0, 1.0], along=[700.0, 700.0])
    r = hd.summarise(pts, [H.mk_line("A", [(0, 0, 1.0), (9, 0, 1.0)])], bands).iloc[0]
    assert r.y_helene_depth_max_m == 1.0 and np.isnan(r.y_helene_depth_typical_miss_m)
    near = hd.summarise(H.mk_pts([1.0, 1.0], along=[50.0, 50.0]), [H.mk_line("A", [(0, 0, 1.0), (9, 0, 1.0)])], bands).iloc[0]
    assert near.y_helene_depth_typical_miss_m == pytest.approx(0.4)
