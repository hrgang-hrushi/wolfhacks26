"""Pulling the pothole reports, against fake Charlotte, Raleigh and Census servers."""
import json

import geopandas as gpd
import pandas as pd
import pytest

from src.pipeline import pothole_labels, pull_potholes
from src.pipeline.arcgis_fetch import PAUSE_S, UA, ArcGISError


def pull(fake, raw, charlotte, raleigh, sleeps=None, **kw):
    s = fake.Session(fake.server(charlotte, raleigh, **kw))
    pull_potholes.main(raw, session=s, now=fake.NOW, sleep=(sleeps.append if sleeps is not None else (lambda x: None)))
    return s


def written(raw):
    return sorted(f.name for f in raw.glob("*")) if raw.exists() else []


def test_P1_short_paging_raises_and_writes_nothing(fake, tmp_path):
    with pytest.raises(ArcGISError, match="received 3 rows but the server counts 5"):
        pull(fake, tmp_path / "raw", [fake.clt(i) for i in range(3)], [fake.ral(1)], counts={"charlotte": 5})
    assert written(tmp_path / "raw") == []


@pytest.mark.parametrize("payload,why", [
    ({"message": "As of May 27, 2026, information about API data can be found at ..."}, "no count"),
    ({"error": {"code": 400, "message": "Invalid query"}}, "Invalid query"),
    ([1, 2, 3], "not a JSON object"),
    (None, "not JSON")])
def test_P2_ok_reply_without_data_raises_and_writes_nothing(fake, tmp_path, payload, why):
    with pytest.raises(ArcGISError, match=why):
        pull(fake, tmp_path / "raw", fake.Resp(payload=payload), [fake.ral(1)])
    assert written(tmp_path / "raw") == []


def test_P3_missing_field_raises_and_names_it(fake, tmp_path):
    rows = [fake.clt(1)]
    del rows[0]["attributes"]["RECEIVED_DATE"]
    with pytest.raises(ArcGISError, match=r"fields missing from the reply: \['RECEIVED_DATE'\]"):
        pull(fake, tmp_path / "raw", rows, [fake.ral(1)])


def test_P4_reports_without_coordinates_are_dropped_and_counted():
    def row(i, lon, lat, alt=(None, None)):
        return {"REQUEST_NO": i, "REQUEST_TYPE": "CDOT POTHOLE REPAIR", "RECEIVED_DATE": 1717200000000,
                "lon": lon, "lat": lat, "LONGITUDE": alt[0], "LATITUDE": alt[1]}
    rows = [row(1, None, None), row(2, 0, 0, (0, 0)), row(3, float("nan"), 35.2),
            row(4, None, None, (-80.84, 35.22)), row(5, -80.84, 35.22)]
    g, drop = pull_potholes.clean(rows, "charlotte", pd.Timestamp("2026-10-03"))
    assert drop == {"unlocated": 3} and g.report_id.tolist() == ["charlotte:4", "charlotte:5"]
    assert not ((g.geometry.x.abs() < 1) | (g.geometry.y.abs() < 1)).any()      # nothing placed at 0,0


def test_P5_out_of_state_and_swapped_coordinates_are_dropped():
    def row(i, lon, lat):
        return {"REQUEST_NO": i, "REQUEST_TYPE": "CDOT POTHOLE REPAIR", "RECEIVED_DATE": 1717200000000,
                "lon": lon, "lat": lat, "LONGITUDE": None, "LATITUDE": None}
    g, drop = pull_potholes.clean([row(1, 35.22, -80.84), row(2, -120.0, 35.0), row(3, -80.84, 35.22)],
                                  "charlotte", pd.Timestamp("2026-10-03"))
    assert drop == {"out_of_state": 2} and g.report_id.tolist() == ["charlotte:3"]


def test_P6_only_the_three_pothole_types_survive(fake, tmp_path):
    raw = tmp_path / "raw"
    pull(fake, raw, [fake.clt(1), fake.clt(2, "NCDOT POTHOLE REQUEST"), fake.clt(3, "SINKHOLE"), fake.clt(4, None)],
         [fake.ral(1), fake.ral(2, "Sinkhole"), fake.ral(3, "Not sure")])
    g = gpd.read_parquet(raw / "pothole_reports.parquet")
    assert sorted(g.request_type.unique()) == ["CDOT POTHOLE REPAIR", "NCDOT POTHOLE REQUEST", "Pothole"]
    meta = json.loads((raw / "pothole_reports.meta.json").read_text())
    assert meta["sources"]["charlotte"]["dropped"] == {"wrong_type": 2}
    assert meta["sources"]["raleigh"]["dropped"] == {"wrong_type": 2}


def test_P7_dates(fake):
    day = 86400000
    now_ms = int(fake.NOW.value // 1_000_000)
    rows = [fake.clt(1, ms=1467365160000), fake.clt(2, ms=None), fake.clt(3, ms=now_ms + 2 * day), fake.clt(4, ms=now_ms)]
    flat = [dict(r["attributes"], lon=r["geometry"]["x"], lat=r["geometry"]["y"]) for r in rows]
    g, drop = pull_potholes.clean(flat, "charlotte", fake.NOW)
    assert drop == {"undated": 1, "future": 1}
    assert g.received_date.tolist() == [pd.Timestamp("2016-07-01 09:26:00"), fake.NOW]


def test_P8_one_row_per_report_id(fake):
    def flat(ids):
        return [dict(fake.clt(i)["attributes"], lon=-80.84, lat=35.22) for i in ids]
    g, drop = pull_potholes.clean(flat(list(range(199)) + [7]), "charlotte", fake.NOW)
    assert drop == {"duplicate": 1} and g.report_id.is_unique and len(g) == 199
    with pytest.raises(ValueError, match="10 duplicate report ids"):
        pull_potholes.clean(flat(list(range(190)) + list(range(10))), "charlotte", fake.NOW)


def test_P9_failed_write_leaves_the_old_files_intact(fake, tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    pull(fake, raw, [fake.clt(1)], [fake.ral(1)])
    before = {f: (raw / f).read_bytes() for f in written(raw)}

    def half_write(self, path, **kw):
        open(path, "wb").write(b"half a file")
        raise OSError("Operation timed out")
    monkeypatch.setattr(gpd.GeoDataFrame, "to_parquet", half_write)
    with pytest.raises(OSError):
        pull(fake, raw, [fake.clt(1), fake.clt(2)], [fake.ral(1)])
    monkeypatch.undo()
    assert {f: (raw / f).read_bytes() for f in before} == before
    assert len(pull_potholes.read_bundle(raw)[0]) == 2          # the old bundle still reads and still matches


def test_P10_output_columns_and_projection(fake, tmp_path):
    raw = tmp_path / "raw"
    pull(fake, raw, [fake.clt(1), fake.clt(2, shape=False)], [fake.ral(1)])
    g = gpd.read_parquet(raw / "pothole_reports.parquet")
    assert list(g.columns) == ["source", "report_id", "request_type", "received_date", "geometry"]
    assert g.crs.to_epsg() == 4326 and str(g.received_date.dtype).startswith("datetime64")
    assert g.report_id.tolist() == ["charlotte:1", "charlotte:2", "raleigh:SRC0000001"]
    lim = gpd.read_parquet(raw / "city_limits.parquet")
    assert sorted(lim.city) == ["charlotte", "raleigh"] and lim.crs.to_epsg() == 4326
    meta = json.loads((raw / "pothole_reports.meta.json").read_text())
    assert meta["pulled_at"] == fake.NOW.isoformat() and set(meta["sha256"]) == {"pothole_reports.parquet", "city_limits.parquet"}
    with pytest.raises(ArcGISError, match="expected one polygon each"):
        pull(fake, tmp_path / "raw2", [fake.clt(1)], [fake.ral(1)], limits=fake.tiger(("Charlotte",)))
    assert written(tmp_path / "raw2") == []


def test_P11_pause_between_pages_and_identifier_on_every_request(fake, tmp_path, monkeypatch):
    monkeypatch.setitem(pull_potholes.SOURCES["charlotte"], "page", 2)
    sleeps = []
    s = pull(fake, tmp_path / "raw", [fake.clt(i) for i in range(5)], [fake.ral(1)], sleeps=sleeps)
    assert sleeps == [PAUSE_S, PAUSE_S]                 # three Charlotte pages: a pause before the 2nd and 3rd
    assert len(s.calls) == 7 and all(h == UA for _, _, h in s.calls)
    assert "unwatched-roads" in UA["User-Agent"]


def test_P12_failure_before_the_manifest_leaves_a_bundle_the_label_step_refuses(fake, tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    pull(fake, raw, [fake.clt(1)], [fake.ral(1)])

    def boom(path):
        raise OSError("disk went away")
    monkeypatch.setattr(pull_potholes, "sha256_file", boom)
    with pytest.raises(OSError):                        # new report file is in place, the manifest is not
        pull(fake, raw, [fake.clt(1), fake.clt(2), fake.clt(3)], [fake.ral(1)])
    monkeypatch.undo()
    assert len(gpd.read_parquet(raw / "pothole_reports.parquet")) == 4
    with pytest.raises(ValueError, match="does not match pothole_reports.meta.json"):
        pothole_labels.main(raw, tmp_path / "processed")
    assert not (tmp_path / "processed" / "pothole_labels.parquet").exists()
