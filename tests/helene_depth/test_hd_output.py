"""The output files, the notes file and the loader (run spec D14-D16, D22-D24)."""
import json
import shutil

import numpy as np
import pandas as pd
import pytest

import hd_helpers as H
from src.pipeline import helene_dem10 as dem
from src.pipeline import helene_depth as hd

QUIET = dict(say=lambda *_: None)


def by_name(tab):
    return tab.set_index("seg_id").rename(index={v: k for k, v in H.SEG.items()})


def test_F1_exact_columns_one_row_per_segment_in_table_order(built_root):
    tab = pd.read_parquet(built_root.p.out / hd.DEPTH)
    assert list(tab.columns) == hd.COLUMNS
    assert list(tab.seg_id) == list(pd.read_parquet(built_root.p.seg).seg_id) and tab.seg_id.is_unique and len(tab) == 12
    assert tab.y_helene_depth_assessed.dtype == bool
    assert all(tab[c].dtype == "float64" for c in hd._FLOATS) and all(tab[c].dtype == "int32" for c in hd._COUNTS)
    assert all(pd.api.types.is_string_dtype(tab[c]) for c in hd._TEXTS)
    t = by_name(tab)
    assert t.loc["low"].y_helene_depth_max_m == pytest.approx(1.6, abs=0.15) and t.loc["low"].y_helene_depth_band == "1 to 2 m"
    assert t.loc["low"].y_helene_depth_conf == "high" and t.loc["low"].y_helene_depth_stream == "Alpha Creek | Test River"
    assert t.loc["beta"].y_helene_depth_stream == "Beta Branch | Test River" and t.loc["beta"].y_helene_depth_max_m > 1
    assert 0 < t.loc["side"].y_helene_depth_wet_share < 0.5 and t.loc["side"].y_helene_depth_max_m > 1
    assert t.loc["bridge"].n_helene_depth_set_aside >= 3 and t.loc["bridge"].y_helene_depth_max_m == 0.0
    assert t.loc["multi"].y_helene_depth_assessed and t.loc["short"].n_helene_depth_points == 2
    pts = pd.read_parquet(built_root.p.out / hd.POINTS)
    assert set(pts.seg_id) <= set(tab.seg_id) and {"ground", "wse", "depth", "aside", "too_deep", "kept", "lift_m"} <= set(pts.columns)


def test_F2_an_unknown_or_repeated_seg_id_stops_the_write():
    per = hd.summarise(H.mk_pts([1.0, 1.0], seg_id="ncdot:X"), [H.mk_line("A", [(0, 0, 1.0), (9, 0, 1.0)])], [])
    assert list(hd.table(per, ["a", "ncdot:X", "b"]).seg_id) == ["a", "ncdot:X", "b"]
    with pytest.raises(hd.DepthError, match="not in the segment table"):
        hd.table(per, ["a", "b"])
    with pytest.raises(hd.DepthError, match="repeats"):
        hd.table(per, ["a", "ncdot:X", "a"])
    with pytest.raises(hd.DepthError, match="empty"):
        hd.table(per, [])
    with pytest.raises(hd.DepthError, match="summarised twice"):
        hd.table(pd.concat([per, per]), ["ncdot:X"])


def test_F3_not_assessed_is_blank_and_assessed_dry_is_zero(built_root):
    t = by_name(pd.read_parquet(built_root.p.out / hd.DEPTH))
    for name in ("far", "away", "empty"):  # too far to the side, another county, no geometry
        r = t.loc[name]
        assert not r.y_helene_depth_assessed and np.isnan(r.y_helene_depth_max_m) and np.isnan(r.y_helene_depth_wet_share)
        assert pd.isna(r.y_helene_depth_band) and pd.isna(r.y_helene_depth_conf) and r.n_helene_depth_marks == 0
    for name in ("high", "edge"):  # beside the stream but above the water
        r = t.loc[name]
        assert r.y_helene_depth_assessed and r.y_helene_depth_max_m == 0.0 and r.y_helene_depth_band == "dry"
    blank = t[~t.y_helene_depth_assessed]
    assert blank[hd._FLOATS].isna().all().all()  # a blank that had been filled with 0 would read as "dry"


def test_F4_a_failed_write_leaves_the_old_files_intact(built_root):
    before = H.snapshot(built_root.p.out)
    tab, pts = pd.read_parquet(built_root.p.out / hd.DEPTH), pd.read_parquet(built_root.p.out / hd.POINTS)

    class Broken:
        def to_parquet(self, *a, **k):
            raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        hd.write_outputs(built_root.p.out, tab, Broken(), {"x": 1}, {"sha256": {}})
    assert H.snapshot(built_root.p.out) == before  # same bytes, and no .tmp left behind
    assert not list(built_root.p.out.glob("*.tmp"))


def test_F5_the_loader_refuses_an_output_that_changed(built_root):
    assert len(hd.load_depth(built_root.root)) == 12
    meta = json.loads((built_root.p.out / hd.META).read_text())
    assert set(meta["sha256"]) == {hd.DEPTH, hd.POINTS, hd.VALID, "marks", "bridges", "manifest", "seg_ids"}
    assert meta["sha256"][hd.DEPTH] == dem.sha256(built_root.p.out / hd.DEPTH)
    assert meta["inputs_before"] == meta["inputs_after"] and meta["inputs_before"]["marks"] == dem.sha256(built_root.p.marks)
    with open(built_root.p.out / hd.DEPTH, "ab") as f:
        f.write(b" ")
    with pytest.raises(hd.DepthError, match="flood_helene_depth.parquet"):
        hd.load_depth(built_root.root)
    (built_root.p.out / hd.META).unlink()
    with pytest.raises(hd.DepthError, match="no depth map"):
        hd.load_depth(built_root.root)


def test_F6_the_settings_are_recorded_and_pinned(built_root):
    pinned = {
        "SPACING_M": 30.0, "SIDE_CAP_M": 300.0, "REACH_M": 1000.0, "MAX_LIFT_M": 2.0, "HIGH_CONF_M": 250.0,
        "END_CAP_M": 100.0, "MERGE_M": 1.0, "BRIDGE_M": 60.0, "NOTCH_M": 3.0, "BANK_RISE_M": 2.0,
        "MAX_DEPTH_M": 15.0, "MAX_TOO_DEEP_SHARE": 0.005, "TRIPWIRE_M": [-1.0, 3.0], "MAX_TAPE_MISS_M": 0.25,
        "BANDS_M": [0.3, 1.0, 2.0], "HOLD_STRETCHES_M": [0, 250, 500], "DIST_BANDS_M": [100, 250, 500, 1000],
        "MIN_BAND_N": 30, "BOOT_N": 1000, "SEED": 0, "NO_LINE_GRADES": ["Poor", "Very Poor"],
        "TILE_DEG": 0.1, "HALO_PX": 3,
    }  # fmt: skip
    assert hd.SETTINGS == pinned  # changing a number means changing it here too, on purpose
    assert json.loads((built_root.p.out / hd.META).read_text())["settings"] == pinned
    assert json.loads((built_root.p.out / hd.VALID).read_text())["settings"] == pinned


def test_F7_every_output_column_is_banned_as_a_model_input():
    from src.model.common import check_features

    cols = [c for c in hd.COLUMNS if c != "seg_id"]
    assert all(c.startswith(("y_", "n_")) for c in cols)
    with pytest.raises(ValueError) as e:
        check_features(cols)
    assert all(c in str(e.value) for c in cols)
    for c in cols:  # each one on its own, so none hides behind another
        with pytest.raises(ValueError):
            check_features(["pv_LENGTH", c])


def test_F8_only_our_own_files_can_be_written(tmp_path):
    for name in ("segments.parquet", "flood_camera_depth.parquet", "predictions.parquet", "terrain.parquet"):
        with pytest.raises(hd.DepthError, match="only flood_helene_depth"):
            hd._own(tmp_path / name)
    assert all(hd._own(tmp_path / name).name.startswith("flood_helene_depth") for name in hd.OUTPUTS)
    assert hd.OUTPUTS[-1] == hd.META and dem.OUT.name == "dem10_helene" and hd.paths().tiles == dem.OUT
    assert hd.paths().out.name == "processed"


def test_F9_a_reading_deeper_than_15_m_is_left_out_and_many_of_them_stop_the_run(tmp_path, monkeypatch):
    def pit(x, y):
        return np.where((x > 280) & (x < 320) & (np.abs(y) < 20), 580.0, 600.0)  # one hole, 20 m below a flat plain

    ground = H.mk_ground(tmp_path, pit)
    lines = [H.mk_line("A", [(x, 50, 600.5) for x in (-100, 900, 1900, 2900)], origin=True)]
    seg = H.seg_table({f"r{k}": H.road((0, 30 * k), (2000, 30 * k)) for k in range(4)})
    pts, per, counts = hd.build(lines, ground, H.NO_BRIDGES, seg, [], rules=())
    assert counts["points_too_deep"] == 1 and counts["segments_with_too_deep"] == 1 and len(pts) == 272
    deep = pts[pts.too_deep].iloc[0]
    assert deep.seg_id == "r0" and deep.depth == pytest.approx(20.5, abs=0.01) and not deep.kept
    assert pts.depth[pts.kept].max() < 15 and pts.kept.sum() == 271
    assert per.y_helene_depth_point_max_m.max() == pytest.approx(0.5, abs=1e-3)  # the 20 m reading set no depth
    monkeypatch.setitem(hd.SETTINGS, "MAX_TOO_DEEP_SHARE", 0.001)  # 1 in 272 is now too many to be a stray point
    with pytest.raises(hd.DepthError, match=r"read deeper than 15.0 m \(worst: r0 at 20.5 m\)"):
        hd.build(lines, ground, H.NO_BRIDGES, seg, [], rules=())


def test_F10_the_loader_refuses_when_an_input_has_changed_since_the_build(built_root):
    p = built_root.p
    hd.load_depth(built_root.root)
    for path, word in ((p.marks, "marks"), (p.tiles / "manifest.json", "manifest")):
        keep = path.read_bytes()
        path.write_bytes(keep + b"\n")
        with pytest.raises(hd.DepthError, match=word):
            hd.load_depth(built_root.root)
        path.write_bytes(keep)
        hd.load_depth(built_root.root)
    seg = pd.read_parquet(p.seg)
    seg.iloc[:-1].to_parquet(p.seg)  # the segment table lost a road
    with pytest.raises(hd.DepthError, match="seg_ids"):
        hd.load_depth(built_root.root)
    seg.assign(extra=1).to_parquet(p.seg)  # a new column on the same roads is not a change that matters
    hd.load_depth(built_root.root)


def test_F11_a_write_that_fails_part_way_leaves_the_old_set_and_a_mixed_set_is_refused(built_root, tmp_path, monkeypatch):
    out = built_root.p.out
    old = H.snapshot(out)
    old_copy = tmp_path / "old"
    shutil.copytree(out, old_copy, ignore=shutil.ignore_patterns("dem*"))
    monkeypatch.setitem(hd.SETTINGS, "SPACING_M", 20.0)  # the second build differs from the first
    real = pd.DataFrame.to_parquet

    def fail_on_depth(self, path, *a, **k):
        if str(path).endswith(hd.DEPTH + ".tmp"):
            raise OSError("the sync daemon locked the file")
        return real(self, path, *a, **k)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_on_depth)
    with pytest.raises(OSError, match="locked"):
        hd.run(built_root.root, **QUIET)
    assert H.snapshot(out) == old and not list(out.glob("*.tmp"))  # points were staged, never swapped in
    monkeypatch.setattr(pd.DataFrame, "to_parquet", real)
    hd.run(built_root.root, **QUIET)
    new = H.snapshot(out)
    assert new[hd.POINTS] != old[hd.POINTS] and len(hd.load_depth(built_root.root)) == 12
    for name in (hd.DEPTH, hd.VALID, hd.META):  # a crash between renames: new points, everything else old
        shutil.copy(old_copy / name, out / name)
    with pytest.raises(hd.DepthError, match="flood_helene_depth_points.parquet"):
        hd.load_depth(built_root.root)
