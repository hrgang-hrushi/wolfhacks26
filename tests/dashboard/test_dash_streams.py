"""The time-stamped tables: camera readings, sensor levels, pothole reports."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import sunnyday
from web.tiger import build, schema

UTC = "UTC"


@pytest.fixture(scope="module")
def built(fixture_root, dash):
    with dash.sunnyday_out(fixture_root):
        return build.build_all(fixture_root)


@pytest.fixture(scope="module")
def real(real_root):
    return build.build_all(real_root)


def frames(root):
    return pd.read_parquet(Path(root) / "data/processed/flood_camera_depth.parquet")


# ------------------------------------------------------------------------------------------------ cameras: T1 to T5

def test_T1_readings_are_unique_on_site_time_and_file(built, fixture_root):
    r = built.tables["camera_readings"]
    src = frames(fixture_root)
    assert len(r) == len(src) == 190
    assert not r.duplicated(["site", "time", "file"]).any()
    assert src.duplicated(["station", "time_utc"]).sum() == 15          # every NCDOT still shares the station "NCDOT"
    assert not r.duplicated(["camera_id", "time"]).any()                 # the camera key loses nothing


def test_T1_a_camera_is_the_station_or_the_site_for_ncdot_stills(built):
    cams = built.tables["cameras"]
    assert len(cams) == 4 + 30 and cams.camera_id.is_unique
    assert cams.set_index("camera_id").loc["CB_01B", "site"] == "CB_01"   # two cameras, one site
    assert (cams.camera_id[cams.station == "NCDOT"] == cams.site[cams.station == "NCDOT"]).all()


def test_T1_a_repeated_reading_is_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    dash.rewrite(root, "data/processed/flood_camera_depth.parquet", lambda d: pd.concat([d, d.iloc[[0]]], ignore_index=True))
    with pytest.raises(ValueError, match="repeat"):
        build.build_cameras_and_readings(root)


def test_T1_a_camera_whose_position_changes_is_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")

    def move(d):
        d.loc[0, "lat"] = 1.0
        return d
    dash.rewrite(root, "data/processed/flood_camera_depth.parquet", move)
    with pytest.raises(ValueError, match="changes between readings"):
        build.build_cameras_and_readings(root)


def test_T2_times_are_utc_and_do_not_shift(built):
    r = built.tables["camera_readings"]
    assert str(r.time.dtype) == "datetime64[ns, UTC]"
    first = r[r.camera_id == "BF_01"].time.min()
    assert first == pd.Timestamp("2026-09-24 13:00", tz=UTC)
    row = next(build.to_rows(r[r.camera_id == "BF_01"].head(1), ["time"]))[0]
    assert (row.hour, row.minute, row.utcoffset().total_seconds()) == (13, 0, 0)
    for table in ("sensor_levels", "pothole_reports"):
        assert str(built.tables[table].time.dtype).endswith("UTC]")


@pytest.mark.parametrize("column, value", [("p_flooded", 1.2), ("p_flooded", -0.1), ("depth_pred_cm", -1.0), ("depth_measured_cm", -3.0)])
def test_T3_an_impossible_value_is_refused(column, value, fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")

    def plant(d):
        d.loc[1, column] = value
        return d
    dash.rewrite(root, "data/processed/flood_camera_depth.parquet", plant)
    with pytest.raises(ValueError, match="probability|negative depth"):
        build.build_cameras_and_readings(root)


def test_T4_readings_without_a_road_keep_a_blank_road(built, fixture_root):
    cams, r = built.tables["cameras"], built.tables["camera_readings"]
    src = frames(fixture_root)
    with_road = r.merge(cams[["camera_id", "seg_id"]], on="camera_id")
    assert len(with_road) == len(r)                                       # none dropped
    assert int(with_road.seg_id.isna().sum()) == int(src.seg_id.isna().sum()) == 125
    blank = next(build.to_rows(cams[cams.camera_id == "BF_01"], ["seg_id"]))[0]
    assert blank is None                                                  # not the word "nan", not a nearby road


def test_T5_known_dry_stills_keep_their_label(built):
    cams, r = built.tables["cameras"], built.tables["camera_readings"]
    assert cams.known_dry.tolist() == (cams.role == "extra").tolist() and cams.known_dry.sum() == 30
    dry = r[r.camera_id.isin(cams.camera_id[cams.known_dry])]
    assert len(dry) == 30 and int((dry.p_flooded >= 0.5).sum()) == 2      # the two planted false alarms


@pytest.mark.realdata
def test_T1_T4_T5_real_camera_numbers(real, real_root):
    cams, r = real.tables["cameras"], real.tables["camera_readings"]
    src = frames(real_root)
    assert len(r) == 3_093 and len(cams) == 1_004
    assert int(src.duplicated(["station", "time_utc"]).sum()) == 1_157
    assert r.time.min() == pd.Timestamp("2026-09-24 11:06", tz=UTC)
    joined = r.merge(cams, on="camera_id")
    assert int(joined.seg_id.isna().sum()) == 1_227
    dry = joined[joined.known_dry]
    assert len(dry) == 1_191 and len(joined) - len(dry) == 1_902
    # How many frames the reader flags depends on which model wrote the file (10 on dry stills with the first
    # reader, 9 after the flood chat's fine-tune on 2026-10-03), so the counts are checked against the file itself.
    flagged_dry = int((src[src.role == "extra"].p_flooded >= 0.5).sum())               # 0.5 is where the service flags
    assert int((dry.p_flooded >= 0.5).sum()) == flagged_dry and 0 < flagged_dry < 60      # false alarms stay under 5%
    assert int((joined[~joined.known_dry].p_flooded >= 0.5).sum()) == int((src[src.role == "cv"].p_flooded >= 0.5).sum()) > 100
    assert np.allclose(r.sort_values(["site", "time", "file"]).p_flooded.values,
                       src.sort_values(["site", "time_utc", "file"]).p_flooded.values)       # every value carried through


# ------------------------------------------------------------------------------------------------ potholes: T6 to T8

def test_T6_every_report_is_kept_once(built):
    p = built.tables["pothole_reports"]
    assert len(p) == 40 and p.report_id.is_unique and p.time.notna().all()
    assert set(p.source) == {"charlotte", "raleigh"}


def test_T6_a_repeated_report_id_is_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    dash.rewrite(root, "data/raw/pothole_reports.parquet", lambda d: pd.concat([d, d.iloc[[0]]], ignore_index=True))
    with pytest.raises(ValueError, match="repeated id"):
        build.build_pothole_reports(root)


def test_T6_report_files_that_do_not_match_their_manifest_are_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    path = root / "data/raw/pothole_reports.parquet"
    path.write_bytes(path.read_bytes() + b" ")                            # changed after the pull wrote its manifest
    with pytest.raises(ValueError, match="does not match"):
        build.build_pothole_reports(root)


def test_T7_per_road_counts_equal_the_label_file(built, fixture_root):
    p = built.tables["pothole_reports"]
    labels = pd.read_parquet(fixture_root / "data/processed/pothole_labels.parquet").set_index("seg_id").n_pothole_all_time
    counts = p.dropna(subset=["seg_id"]).groupby("seg_id").size().reindex(labels.index).fillna(0).astype(int)
    assert counts.tolist() == labels.tolist() and counts.sum() == 31 and counts.max() == 2
    assert (p.dist_m.dropna() <= 60).all()


def test_T7_a_stale_label_file_is_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")

    def stale(d):
        d.loc[d.n_pothole_all_time.idxmax(), "n_pothole_all_time"] += 1
        return d
    dash.rewrite(root, "data/processed/pothole_labels.parquet", stale)
    with pytest.raises(ValueError, match="disagrees with pothole_labels"):
        build.build_pothole_reports(root)


def test_T7_the_matcher_is_the_projects_own():
    from src.pipeline import pothole_labels
    src = Path("web/tiger/build.py").read_text()
    assert "pothole_labels.match_reports(" in src and "sjoin_nearest" not in src       # no second matcher
    assert build.CRS_M == pothole_labels.CRS_M


def test_T8_unmatched_reports_are_kept_with_a_blank_road(built):
    p = built.tables["pothole_reports"]
    unmatched = p[p.seg_id.isna()]
    assert len(unmatched) == 9 and unmatched.dist_m.isna().all()
    assert "raleigh:32" in unmatched.report_id.tolist()                    # about 55 m away: too far for Raleigh's 30 m
    assert all(v[0] is None for v in build.to_rows(unmatched, ["seg_id"]))


@pytest.mark.realdata
def test_T6_T7_T8_real_report_numbers(real, real_root):
    p = real.tables["pothole_reports"]
    assert len(p) == 17_790 and p.report_id.is_unique
    assert int(p.seg_id.notna().sum()) == 3_610 and int(p.seg_id.isna().sum()) == 14_180
    labels = pd.read_parquet(real_root / "data/processed/pothole_labels.parquet")
    assert int(labels.n_pothole_all_time.sum()) == 3_610
    assert p.time.min().year == 2016 and p.time.max() == pd.Timestamp("2026-10-02 21:17:55", tz=UTC)


# ------------------------------------------------------------------------------------------------ sensors: T9 to T11

def test_T9_sensor_rows_are_the_flood_chats_reader_station_by_station(built, fixture_root, dash):
    s = built.tables["sensor_levels"]
    with dash.sunnyday_out(fixture_root):
        for sid in ("BF_01", "CB_01", "DE_02", "ZZ_09"):
            _, lv = sunnyday.read_station(sid)
            mine = s[s.station == sid]
            assert len(mine) == len(lv) > 900
            assert np.allclose(mine.level_m.values, lv.level_m.values)
            assert mine.time.dt.tz_localize(None).tolist() == lv.level_time.tolist()
    assert "CB_01B" not in set(s.station)                                  # a camera with no sensor of its own
    assert (s.level_m < 9).all()                                           # the filtered 9.9 series was not read
    assert len(s) == 959 + 960 * 3


def test_T9_depth_on_the_road_follows_the_flood_chats_rule(built):
    s = built.tables["sensor_levels"].set_index("station")
    bf = s.loc["BF_01"]
    storm = bf[(bf.time >= pd.Timestamp("2026-09-26 13:00", tz=UTC)) & (bf.time < pd.Timestamp("2026-09-26 16:00", tz=UTC))]
    assert np.allclose(storm.depth_on_road_cm, (1.0 - sunnyday.ROAD_LEVEL_M["BF_01"]) * 100)       # 14 cm
    assert (bf[bf.level_m < sunnyday.ROAD_LEVEL_M["BF_01"]].depth_on_road_cm == 0).all()            # never negative
    assert (s.loc["DE_02"].depth_on_road_cm == 0).all() and "DE_02" in sunnyday.ALWAYS_DRY
    assert s.loc["ZZ_09"].depth_on_road_cm.isna().all() and s.loc["ZZ_09"].road_level_m.isna().all()  # no road height known


def test_T10_unique_on_station_and_time_and_bad_values_are_counted(built):
    s = built.tables["sensor_levels"]
    assert not s.duplicated(["station", "time"]).any()
    assert built.sensor_values_dropped == 1                               # the planted "n/a"
    assert s.level_m.notna().all()


def test_T10_a_repeated_time_in_a_station_file_is_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    path = root / "data/raw/sunnyday/levels/DE_02.json"
    doc = json.loads(path.read_text())
    obs = next(q for q in doc["features"][0]["properties"]["parameters"] if q["id"] == "water_level_raw")["observations"]
    obs["times"][1] = obs["times"][0]
    path.write_text(json.dumps(doc))
    with dash.sunnyday_out(root), pytest.raises(ValueError, match="repeat"):
        build.build_sensor_levels(root)


def test_T10_a_build_pointed_at_another_folder_than_the_reader_is_refused(fixture_root):
    with pytest.raises(ValueError, match="different folder"):
        build.build_sensor_levels(fixture_root)                            # the reader still points at the real folder


@pytest.mark.realdata
def test_T9_T10_real_sensor_numbers(real):
    s = real.tables["sensor_levels"]
    assert len(s) == 12_557 and s.station.nunique() == 10 and real.sensor_values_dropped == 0
    assert not s.duplicated(["station", "time"]).any()
    assert s.time.min().date() == pd.Timestamp("2026-09-24").date() and s.time.max().date() == pd.Timestamp("2026-09-28").date()


@pytest.mark.realdata
def test_T11_levels_equal_the_flood_chats_label_file_where_times_match(real, real_root):
    labels = pd.read_parquet(real_root / "data/raw/sunnyday/labels.parquet")
    if "level_m" not in labels.columns:
        pytest.skip("the label file carries no sensor level")
    cv = labels[(labels.role == "cv") & labels.level_m.notna()].copy()
    cv["station"] = cv.station.replace(sunnyday.LEVEL_FROM)               # a second camera reads its site's sensor
    cv["time"] = pd.to_datetime(cv.level_time).dt.tz_localize(UTC)
    m = cv.merge(real.tables["sensor_levels"], on=["station", "time"], how="left", suffixes=("_label", ""))
    assert len(m) == len(cv) > 1_000 and m.level_m.notna().all()          # every labelled level is a row we loaded
    assert np.allclose(m.level_m_label, m.level_m)


# ------------------------------------------------------------------------------------------------ T12, T13

@pytest.mark.parametrize("rel, builder", [
    ("data/processed/flood_camera_depth.parquet", build.build_cameras_and_readings),
    ("data/raw/pothole_reports.parquet", build.build_pothole_reports),
])
def test_T12_zero_rows_is_refused(rel, builder, fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    dash.rewrite(root, rel, lambda d: d.iloc[0:0])
    with pytest.raises(ValueError, match="no rows"):
        builder(root)


def test_T12_no_sensor_files_is_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    for f in (root / "data/raw/sunnyday/levels").glob("*.json"):
        f.unlink()
    with dash.sunnyday_out(root), pytest.raises(ValueError, match="no rows"):
        build.build_sensor_levels(root)


def test_T13_the_load_record_describes_every_file_that_was_read(built, fixture_root):
    names = set(built.fingerprints)
    assert set(build.SOURCES.values()) <= names and len(names) == len(build.SOURCES) + 5      # five sensor files
    assert all(len(v["sha256"]) == 64 and v["bytes"] > 0 for v in built.fingerprints.values())
    rows = {name: v["rows"] for name, v in built.fingerprints.items()}
    assert rows["handoff/predictions_geo.parquet"] == 300 and rows["data/raw/pothole_reports.parquet"] == 40
    assert rows["data/processed/flood_camera_depth.parquet"] == 190 and rows["data/raw/pothole_reports.meta.json"] is None
    assert rows["data/raw/sunnyday/levels/BF_01.json"] == 960 and rows["data/raw/sunnyday/levels/CB_01B.json"] == 0
    assert built.counts == {k: len(v) for k, v in built.tables.items()}
    assert list(built.tables) == list(schema.TABLES)


def test_T13_a_file_replaced_while_the_build_is_reading_is_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    def replace():                                                         # another pipeline rewrites a file mid-build
        dash.rewrite(root, "handoff/traffic_crash.parquet", lambda d: d.assign(cr_fatal_10yr=d.cr_fatal_10yr + 1))
    with dash.sunnyday_out(root), pytest.raises(ValueError, match="changed while they were being read"):
        build.build_all(root, _after_read=replace)
    with dash.sunnyday_out(root):
        assert build.build_all(root).counts["roads"] == dash.N_ROADS      # the same folder builds once it is still


def test_a_camera_matched_to_a_road_that_does_not_exist_is_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")

    def unknown_road(d):
        d.loc[d.station == "DE_02", "seg_id"] = "ncdot:99999999999:0.000"
        return d
    dash.rewrite(root, "data/processed/flood_camera_depth.parquet", unknown_road)
    with dash.sunnyday_out(root), pytest.raises(ValueError, match="not in the road table"):
        build.build_all(root)


def test_built_columns_are_the_tables_columns_in_order(built):
    for table, frame in built.tables.items():
        assert list(frame.columns) == schema.columns(table), table
