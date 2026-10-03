"""Matching reports to road segments and building the pothole labels."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from src.pipeline import pothole_labels as pl
from src.pipeline import pull_potholes

X, Y = 502000, 200000            # inside the default test city (x 500000-505000, y 195000-205000)
MILE = 1609.344
CDOT, NCDOT = "CDOT POTHOLE REPAIR", "NCDOT POTHOLE REQUEST"
PULLED = pd.Timestamp("2026-10-03 12:00:00")


def labels(fake, segs, reports, city=None, pulled=PULLED):
    segs, reports = fake.segs_m(segs), fake.reports_m(reports)
    where = pl.assign_city(segs, fake.city_m() if city is None else city)
    return pl.build_labels(segs, pl.match_reports(reports, segs), reports, where, pulled)


def test_L1_match_distance_is_in_metres(fake):
    segs = fake.segs_m([("a", X, Y, X + 1000, Y, None)])
    # Raleigh's points sit on the street (30 m); Charlotte's are address locations (60 m)
    m = pl.match_reports(fake.reports_m([(1, X + 500, Y + 29, "Pothole", "2025-06-01"), (2, X + 500, Y + 31, "Pothole", "2025-06-01"),
                                         (3, X + 500, Y + 59, CDOT, "2024-06-01"), (4, X + 500, Y + 61, CDOT, "2024-06-01")]), segs)
    assert m.report_id.tolist() == ["t:1", "t:3"] and m.dist_m.tolist() == pytest.approx([29, 59])
    assert pl.MATCH_M == {"charlotte": 60, "raleigh": 30}


def test_L2_report_near_two_segments_is_counted_once_on_the_nearest(fake):
    segs = [("a", X, Y, X + 1000, Y, None), ("b", X, Y + 20, X + 1000, Y + 20, None)]
    lab = labels(fake, segs, [(1, X + 500, Y + 8, CDOT, "2024-06-01"), (2, X + 500, Y + 10, CDOT, "2024-06-01")])
    assert lab.n_pothole_reports.tolist() == [2, 0]      # 8 m beats 12 m; a 10 m tie goes to the first seg_id
    assert lab.n_pothole_reports.sum() == 2


def test_L3_far_reports_stay_unmatched(fake, capsys):
    segs = fake.segs_m([("a", X, Y, X + 1000, Y, None)])
    reports = fake.reports_m([(1, X + 500, Y + 500, CDOT, "2024-06-01"), (2, X + 500, Y + 5, CDOT, "2024-06-01")])
    m = pl.match_reports(reports, segs)
    assert m.report_id.tolist() == ["t:2"]
    assert pl.match_summary(reports, m).to_dict("records") == [
        {"source": "charlotte", "request_type": CDOT, "reports": 2, "matched": 1, "unmatched": 1}]
    lab = pl.build_labels(segs, m, reports, pl.assign_city(segs, fake.city_m()), PULLED)
    assert lab.n_pothole_all_time.tolist() == [1]


def test_L4_blank_outside_the_city_zero_or_one_inside(fake):
    segs = [("in_hit", X, Y, X + 1000, Y, None), ("in_none", X, Y + 500, X + 1000, Y + 500, None),
            ("out_hit", X + 20000, Y, X + 21000, Y, None)]
    lab = labels(fake, segs, [(1, X + 500, Y + 5, CDOT, "2024-06-01"), (2, X + 20500, Y + 5, CDOT, "2024-06-01")])
    assert lab.pothole_city.fillna("-").tolist() == ["charlotte", "charlotte", "-"]
    assert lab.y_pothole_any.iloc[:2].tolist() == [1.0, 0.0]
    # the report beside the outside segment is real, yet its label stays blank: nobody collects reports there
    assert lab.n_pothole_all_time.iloc[2] == 1 and np.isnan(lab.y_pothole_any.iloc[2]) and np.isnan(lab.y_pothole_rate.iloc[2])
    assert np.isnan(lab.pothole_exposure_years.iloc[2]) and lab.n_pothole_reports.iloc[2] == 0


def test_L5_segment_straddling_the_city_edge_follows_its_midpoint(fake):
    segs = fake.segs_m([("mid_in", 504000, Y, 505500, Y, None), ("mid_out", 504800, Y, 507000, Y, None)])
    assert pl.assign_city(segs, fake.city_m()).tolist() == ["charlotte", None]


def test_L6_unknown_or_duplicate_seg_id_raises_and_order_is_kept(fake):
    segs = fake.segs_m([("ncdot:1:0.141", X, Y, X + 1000, Y, None), ("ncdot:1:0.298", X, Y + 500, X + 1000, Y + 500, None)])
    reports = fake.reports_m([(1, X + 500, Y + 5, CDOT, "2024-06-01")])
    city = pl.assign_city(segs, fake.city_m())
    drifted = pd.DataFrame({"report_id": ["t:1"], "seg_id": ["ncdot:1:0.1410"], "dist_m": [5.0]})
    with pytest.raises(ValueError, match="not in the segment table"):
        pl.build_labels(segs, drifted, reports, city, PULLED)
    twice = pd.concat([segs, segs.iloc[:1]], ignore_index=True)
    with pytest.raises(ValueError, match="nulls or duplicates"):
        pl.build_labels(twice, pl.match_reports(reports, segs), reports, list(city) + [city[0]], PULLED)
    lab = pl.build_labels(segs, pl.match_reports(reports, segs), reports, city, PULLED)
    assert lab.seg_id.tolist() == segs.seg_id.tolist() and list(lab.columns) == pl.LABEL_COLS


def test_L7_only_reports_between_the_exposure_start_and_the_pull_count(fake):
    segs = [("no_rehab", X, Y, X + 1000, Y, None), ("rehab_2024", X, Y + 500, X + 1000, Y + 500, 2024)]
    reports = [(1, X + 5, Y, CDOT, "2022-12-31 23:59"), (2, X + 5, Y, CDOT, "2023-01-01 00:00"),
               (3, X + 5, Y, CDOT, "2026-10-03 12:00"), (4, X + 5, Y, CDOT, "2026-10-04 12:00"),
               (5, X + 5, Y + 500, CDOT, "2024-12-31 23:59"), (6, X + 5, Y + 500, CDOT, "2025-01-01 00:00")]
    lab = labels(fake, segs, reports)
    assert lab.n_pothole_reports.tolist() == [2, 1]      # both ends of the window are inside it
    assert lab.n_pothole_all_time.tolist() == [4, 2]


def test_L8_exposure_years_per_city_and_rehab_year(fake):
    segs = [("clt", X, Y, X + 1000, Y, None), ("clt_2025", X, Y + 500, X + 1000, Y + 500, 2025.0),
            ("clt_2026", X, Y + 900, X + 1000, Y + 900, 2026), ("clt_old", X, Y + 1300, X + 1000, Y + 1300, 2010),
            ("ral", X + 50000, Y, X + 51000, Y, None), ("out", X + 90000, Y, X + 91000, Y, 2015)]
    both = pd.concat([fake.city_m(), fake.city_m(545000, 195000, 560000, 205000, "raleigh")], ignore_index=True)
    lab = labels(fake, segs, [(1, X + 5, Y + 900, CDOT, "2026-06-01")], city=both)
    assert lab.pothole_city.fillna("-").tolist() == ["charlotte"] * 4 + ["raleigh", "-"]
    years = lab.pothole_exposure_years
    assert years.iloc[:5].tolist() == pytest.approx([1371 / 365.25, 275 / 365.25, 0, 1371 / 365.25, 472 / 365.25])
    assert pl.WINDOW_START["raleigh"] == pd.Timestamp("2025-06-18")        # Raleigh's first pothole report
    assert np.isnan(years.iloc[5])
    assert np.isnan(lab.y_pothole_any.iloc[2]) and lab.n_pothole_reports.iloc[2] == 0   # resurfaced this year: not watched yet


def test_L9_zero_or_missing_length_gives_a_blank_rate_or_stops(fake, tmp_path):
    lab = labels(fake, [("point", X, Y, X, Y, None), ("mile", X, Y + 500, X + MILE, Y + 500, None)],
                 [(1, X, Y + 2, CDOT, "2024-06-01"), (2, X + 5, Y + 500, CDOT, "2024-06-01")])
    assert np.isnan(lab.y_pothole_rate.iloc[0]) and lab.y_pothole_any.iloc[0] == 1.0
    assert lab.y_pothole_rate.iloc[1] == pytest.approx(1 / (1371 / 365.25))
    assert np.isfinite(lab.y_pothole_rate.dropna()).all()
    segs, (lon, lat) = clt_segs(fake)                    # a segment with no shape at all stops the run
    segs = pd.concat([segs, segs.assign(seg_id="ncdot:no-shape", geometry=None)], ignore_index=True)
    raw = write_raw(fake, tmp_path, segs, [fake.clt(1, lon=lon, lat=lat)])
    with pytest.raises(ValueError, match="1 segments have no geometry"):
        pl.main(raw, tmp_path / "processed")


def test_L10_charlotte_report_types_are_separate_counts(fake):
    both = pd.concat([fake.city_m(), fake.city_m(545000, 195000, 560000, 205000, "raleigh")], ignore_index=True)
    segs = [("clt", X, Y, X + 1000, Y, None), ("ral", X + 50000, Y, X + 51000, Y, None)]
    reports = [(1, X + 5, Y, CDOT, "2024-06-01"), (2, X + 6, Y, CDOT, "2024-07-01"), (3, X + 7, Y, NCDOT, "2024-08-01"),
               (4, X + 50005, Y, "Pothole", "2025-09-01")]
    lab = labels(fake, segs, reports, city=both)
    assert lab[["n_pothole_reports", "n_pothole_cdot", "n_pothole_ncdot", "n_pothole_raleigh"]].values.tolist() == [[3, 2, 1, 0], [1, 0, 0, 1]]


def write_raw(fake, tmp_path, segs, charlotte):
    """A raw folder with the real schema: seg_id, YEAR_LAST_REHAB and geometry in EPSG:4326, no length column."""
    raw = tmp_path / "raw"
    pull_potholes.main(raw, session=fake.Session(fake.server(charlotte, [fake.ral(1)])), now=PULLED, sleep=lambda s: None)
    segs.to_crs(4326).to_parquet(raw / "ncdot_joined.parquet")
    return raw


def clt_segs(fake):
    """A one-mile segment in central Charlotte (inside the fake Census polygon) and its lon/lat midpoint."""
    x, y = gpd.GeoSeries.from_xy([-80.84], [35.22], crs=4326).to_crs(fake.CRS_M).iloc[0].coords[0]
    segs = fake.segs_m([("ncdot:10000077060:1.000", x - MILE / 2, y, x + MILE / 2, y, 2015)])
    return segs, (-80.84, 35.22)


def test_L11_missing_city_limits_raise(fake, tmp_path):
    segs, (lon, lat) = clt_segs(fake)
    with pytest.raises(ValueError, match="refusing to treat every segment as covered"):
        pl.assign_city(segs, fake.city_m().iloc[:0])
    raw = write_raw(fake, tmp_path, segs, [fake.clt(1, lon=lon, lat=lat)])
    (raw / "city_limits.parquet").unlink()
    with pytest.raises(ValueError, match="city_limits.parquet does not match"):
        pl.main(raw, tmp_path / "processed")
    (raw / "pothole_reports.meta.json").unlink()
    with pytest.raises(FileNotFoundError, match="run src.pipeline.pull_potholes first"):
        pl.main(raw, tmp_path / "processed")


def test_L12_failed_write_leaves_the_old_labels_intact(fake, tmp_path, monkeypatch):
    segs, (lon, lat) = clt_segs(fake)
    raw, out = write_raw(fake, tmp_path, segs, [fake.clt(1, lon=lon, lat=lat)]), tmp_path / "processed"
    pl.main(raw, out)
    before = (out / "pothole_labels.parquet").read_bytes()

    def half_write(self, path, **kw):
        open(path, "wb").write(b"half a file")
        raise OSError("Operation timed out")
    monkeypatch.setattr(pd.DataFrame, "to_parquet", half_write)
    with pytest.raises(OSError):
        pl.main(raw, out)
    monkeypatch.undo()
    assert (out / "pothole_labels.parquet").read_bytes() == before
    assert len(pd.read_parquet(out / "pothole_labels.parquet")) == 1


def test_L13_main_on_the_real_raw_schema_computes_length_from_geometry(fake, tmp_path):
    segs, (lon, lat) = clt_segs(fake)
    raw = write_raw(fake, tmp_path, segs, [fake.clt(1, lon=lon, lat=lat), fake.clt(2, NCDOT, lon=lon, lat=lat),
                                           fake.clt(3, lon=lon, lat=lat, ms=1600000000000)])   # 2020: before the window
    assert "length_m" not in gpd.read_parquet(raw / "ncdot_joined.parquet").columns
    pl.main(raw, tmp_path / "processed")
    lab = pd.read_parquet(tmp_path / "processed" / "pothole_labels.parquet")
    assert list(lab.columns) == pl.LABEL_COLS and "geometry" not in lab.columns and len(lab) == 1
    row = lab.iloc[0]
    assert (row.pothole_city, row.n_pothole_reports, row.n_pothole_ncdot, row.n_pothole_all_time) == ("charlotte", 2, 1, 3)
    assert row.y_pothole_rate == pytest.approx(2 / (1.0 * 1371 / 365.25), rel=1e-3)     # 2 reports, 1 mile, 3.75 years
    meta = json.loads((tmp_path / "processed" / "pothole_labels.meta.json").read_text())      # the match rate is kept, not only printed
    assert (meta["reports"], meta["matched"], meta["unmatched"]) == (4, 3, 1) and meta["match_m"] == pl.MATCH_M
    assert {(r["request_type"], r["matched"], r["unmatched"]) for r in meta["by_type"]} == {(CDOT, 2, 0), (NCDOT, 1, 0), ("Pothole", 0, 1)}


def test_L14_file_that_does_not_match_the_manifest_is_refused(fake, tmp_path):
    segs, (lon, lat) = clt_segs(fake)
    raw = write_raw(fake, tmp_path, segs, [fake.clt(1, lon=lon, lat=lat)])
    g = gpd.read_parquet(raw / "pothole_reports.parquet")
    pd.concat([g, g.assign(report_id="charlotte:999")]).to_parquet(raw / "pothole_reports.parquet")
    with pytest.raises(ValueError, match="pothole_reports.parquet does not match"):
        pl.main(raw, tmp_path / "processed")
    meta = json.loads((raw / "pothole_reports.meta.json").read_text())
    assert set(meta["sha256"]) == {"pothole_reports.parquet", "city_limits.parquet"}
