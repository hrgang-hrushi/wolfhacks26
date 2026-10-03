"""Pins on the real pothole pull and labels. Skipped on machines without the data; the live-server
checks run only with `-m network`."""
import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from src.pipeline import pull_potholes
from src.pipeline.arcgis_fetch import count

RAW, P = Path("data/raw"), Path("data/processed")


@pytest.fixture(scope="module")
def meta():
    f = RAW / "pothole_reports.meta.json"
    if not f.exists():
        pytest.skip(f"{f} is not on this machine")
    return json.loads(f.read_text())


@pytest.mark.realdata
def test_N1_charlotte_rows_equal_the_servers_count(meta):
    c = meta["sources"]["charlotte"]
    assert c["server_count"] >= 24_824 and c["kept"] + sum(c["dropped"].values()) == c["server_count"]


@pytest.mark.network
def test_N1_live_charlotte_count_has_not_shrunk(meta):
    cfg = pull_potholes.SOURCES["charlotte"]
    assert count(requests.Session(), cfg["url"], cfg["where"]) >= meta["sources"]["charlotte"]["server_count"]


@pytest.mark.realdata
def test_N2_located_charlotte_reports(meta):
    reports, limits, _ = pull_potholes.read_bundle(RAW)          # also proves the files match their manifest
    assert meta["sources"]["charlotte"]["kept"] >= 17_441 and reports.report_id.is_unique
    assert (reports.source == "charlotte").sum() == meta["sources"]["charlotte"]["kept"]
    assert sorted(limits.city) == ["charlotte", "raleigh"]


@pytest.mark.realdata
def test_N3_raleigh_potholes(meta):
    r = meta["sources"]["raleigh"]
    assert r["server_count"] >= 351 and r["by_type"] == {"Pothole": r["kept"]}


@pytest.mark.network
def test_N3_live_raleigh_count_has_not_shrunk(meta):
    cfg = pull_potholes.SOURCES["raleigh"]
    assert count(requests.Session(), cfg["url"], cfg["where"]) >= meta["sources"]["raleigh"]["server_count"]


@pytest.mark.realdata
def test_N4_label_table_covers_every_segment():
    f = P / "pothole_labels.parquet"
    if not f.exists():
        pytest.skip(f"{f} is not on this machine")
    lab = pd.read_parquet(f)
    seg = pd.read_parquet(P / "segments_targets.parquet", columns=["seg_id"])
    assert len(lab) == 112_443 and lab.seg_id.tolist() == seg.seg_id.tolist()
    assert set(lab.pothole_city.dropna()) == {"charlotte", "raleigh"}
    assert lab.y_pothole_any[lab.pothole_city.isna()].isna().all()        # blank outside the two cities
    assert lab.y_pothole_any[lab.pothole_city.notna() & (lab.pothole_exposure_years > 0)].isin([0.0, 1.0]).all()
    assert (lab.n_pothole_reports == lab.n_pothole_cdot + lab.n_pothole_ncdot + lab.n_pothole_raleigh).all()
