"""Pins on the real camera list. The live-server check runs only with `-m network`."""
from pathlib import Path

import pandas as pd
import pytest
import requests

from src.pipeline import cctv
from src.pipeline.arcgis_fetch import count

CAMS = Path("data/raw/cctv/cameras.parquet")


@pytest.mark.realdata
def test_N5_camera_list_on_disk():
    if not CAMS.exists():
        pytest.skip(f"{CAMS} is not on this machine")
    c = pd.read_parquet(CAMS)
    assert list(c.columns) == cctv.CAMERA_COLS and c.camera_id.is_unique
    assert len(c) >= 1_100 and (c.image_status == "Recent").sum() >= 900
    seg = pd.read_parquet("data/processed/segments_targets.parquet", columns=["seg_id"]).seg_id
    assert set(c.seg_id.dropna()) <= set(seg) and c.seg_dist_m.dropna().between(0, cctv.MAX_M).all()


@pytest.mark.network
def test_N5_live_camera_layer():
    s = requests.Session()
    assert count(s, cctv.LAYER, "1=1") >= 1_100
    assert count(s, cctv.LAYER, "ImageStatus = 'Recent'") >= 900
