"""Fakes for the camera tests: a scripted HTTP session, a clock, JPEG bytes and three road segments."""
import io
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import requests
from PIL import Image
from shapely.geometry import LineString

NOW = datetime(2026, 10, 3, 19, 0, 0, tzinfo=timezone.utc)


class Resp:
    def __init__(self, status=200, body=b"", headers=None, payload=None):
        self.status_code, self.content, self.headers, self.payload = status, body, headers or {}, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        if self.payload is None:
            raise ValueError("not JSON")
        return self.payload


class Session:
    """Calls handler(url, params) for every GET and records (url, params, headers)."""

    def __init__(self, handler):
        self.handler, self.calls = handler, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        out = self.handler(url, params)
        if isinstance(out, Exception):
            raise out
        return out


class Clock:
    """A clock whose sleep() moves time forward and is recorded."""

    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def jpeg(seed=0, size=(160, 90), lo=0, hi=255):
    """JPEG bytes of random noise between lo and hi; a different seed gives different bytes."""
    a = np.random.default_rng(seed).integers(lo, hi, (size[1], size[0], 3), dtype="uint8")
    b = io.BytesIO()
    Image.fromarray(a).save(b, "JPEG", quality=90)
    return b.getvalue()


def image_resp(body, age_s=60, now=NOW):
    return Resp(body=body, headers={"Last-Modified": format_datetime(now - timedelta(seconds=age_s), usegmt=True)})


def cameras(n, hosts=("a.test", "b.test"), **over):
    d = pd.DataFrame({
        "camera_id": np.arange(1, n + 1), "status": "Active Streaming", "image_status": "Recent",
        "highway": "I-40", "county": "Wake", "location_name": [f"cam{i}" for i in range(1, n + 1)],
        "lat": 35.8, "lon": -78.6,
        "image_url": [f"https://{hosts[i % len(hosts)]}/snapshots/chan-{i + 1}_l.jpg" for i in range(n)],
        "seg_id": None, "seg_dist_m": np.nan, "match_rule": None})
    for k, v in over.items():
        d[k] = v
    return d


def arcgis(rows, count=None):
    """Handler for a fake ArcGIS layer holding `rows`; `count` overrides what the server claims."""
    def handler(url, params):
        if params.get("returnCountOnly"):
            return Resp(payload={"count": len(rows) if count is None else count})
        o, n = params["resultOffset"], params["resultRecordCount"]
        return Resp(payload={"features": [{"attributes": r} for r in rows[o:o + n]]})
    return handler


def review_base(path, n=17, size=(320, 180), round_id="r1"):
    """A data/raw/cctv folder with n saved stills for one round. Still i is a flat grey of level 10 + 10 * i,
    so a test can tell which still a sheet cell or a crop came from."""
    rows = []
    for i in range(n):
        f = path / str(100 + i) / "20261003T201800Z.jpg"
        f.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (10 + 10 * i,) * 3).save(f, quality=95)
        rows.append({"camera_id": 100 + i, "round": round_id, "file": f"{100 + i}/{f.name}", "status": "ok", "dark": False})
    pd.DataFrame(rows).to_parquet(path / "stills.parquet")
    return path, pd.DataFrame({"camera_id": [100 + i for i in range(n)]})


def grey_to_index(im):
    """Which still (0-based) an image made by review_base came from."""
    return round((np.asarray(im.convert("L")).mean() - 10) / 10)


@pytest.fixture
def fake():
    """The helpers above, for test modules (conftest files are not importable by name)."""
    from types import SimpleNamespace
    return SimpleNamespace(Resp=Resp, Session=Session, jpeg=jpeg, image_resp=image_resp, cameras=cameras,
                           arcgis=arcgis, NOW=NOW, review_base=review_base, grey_to_index=grey_to_index)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def segs():
    """Three segments near (-78.6, 35.8): I-40 running east-west, NC-55 crossing it, and a far US-1."""
    return gpd.GeoDataFrame({
        "seg_id": ["ncdot:10000040092:1.000", "ncdot:30000055092:2.000", "ncdot:20000001092:3.000"],
        "ROUTE": ["10000040", "30000055", "20000001"]},
        geometry=[LineString([(-78.61, 35.8), (-78.59, 35.8)]),
                  LineString([(-78.6, 35.79), (-78.6, 35.81)]),
                  LineString([(-78.5, 35.9), (-78.49, 35.9)])], crs="EPSG:4326")
