"""Fixtures for the dashboard tests: a small folder shaped like the real data, and throwaway database schemas.

The dashboard needs a database driver and a web framework that live in web/.venv, not in the main environment.
Where they cannot be imported the test files here are left out of collection, so a plain `pytest` from another
chat's environment neither errors nor changes its count.

Database tests (marker `db`) run against a local TimescaleDB container and refuse any other host.
"""
import importlib.util
import json
import os
import secrets
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

_NEEDED = ("psycopg", "psycopg_pool", "fastapi", "httpx")
collect_ignore_glob = [] if all(importlib.util.find_spec(m) for m in _NEEDED) else ["test_dash_*.py"]

LOCAL_URL = "postgresql://postgres@127.0.0.1:55432/postgres"  # trust login on loopback only: no password exists
REAL_FILES = ["handoff/predictions_geo.parquet", "handoff/traffic_crash.parquet", "data/processed/segments.parquet",
              "data/processed/pothole_labels.parquet", "data/processed/flood_camera_depth.parquet",
              "data/raw/ncdot_joined.parquet", "data/raw/pothole_reports.parquet", "data/raw/sunnyday/levels"]
N_ROADS = 300
PULLED_AT = "2026-10-03T20:22:30"


def pytest_configure(config):
    config.addinivalue_line("markers", "db: needs the local TimescaleDB test container (see web/README.md)")


def fake_url(password="pw-marker", user="user-marker", host="127.0.0.1", port=1, db="postgres"):
    """A database address built from pieces, so no tracked file holds one whole."""
    return "postgresql" + "://" + user + ":" + password + "@" + f"{host}:{port}/{db}"


@contextmanager
def sunnyday_out(root):
    """Point the flood chat's sensor reader at `root` for one build or load, then put it back."""
    from src.pipeline import sunnyday
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sunnyday, "OUT", Path(root) / "data" / "raw" / "sunnyday")
        yield


# ---------------------------------------------------------------------------------------------- fixture folder

def _roads(n=N_ROADS, seed=0):
    """n roads in three groups of n/3: the Helene zone in the west, Charlotte, Raleigh. One row per road."""
    from pyproj import Transformer
    rng = np.random.default_rng(seed)
    i = np.arange(n)
    per = n // 3
    group = np.minimum(i // per, 2)
    lon0 = np.array([-82.60, -80.90, -78.70])[group]
    lat0 = np.array([35.55, 35.20, 35.75])[group]
    k = i % per
    lon = lon0 + (k % 10) * 0.01
    lat = lat0 + (k // 10) * 0.01
    county = np.array(["011-Buncombe", "060-Mecklenburg", "092-Wake"])[group]
    route = np.array([f"4{j:07d}" for j in i])
    beg = (i % 7) * 0.5
    seg_id = np.array([f"ncdot:{r}{c[:3]}:{b:.3f}" for r, c, b in zip(route, county, beg)])
    zone = (group == 0).astype("int8")
    rating = rng.uniform(30, 100, n).round(1)
    rating[0] = 0.0                                   # a missing rating
    rate = rng.uniform(0.5, 3.0, n)
    years = np.where(rating <= 60, 0.0, np.minimum((rating - 60) / np.maximum(rate, 0.1), 50.0))
    stale = np.isin(i, [0, 7, 77, 150, 222, 299])     # no forecast: rating missing or older than the last rehab
    years = np.where(stale, np.nan, years)
    treat = np.where(i % 2 == 0, "Do Nothing", rng.choice(["Seal Cracks", "Wheelpath Patching", "Double Seal"], n))
    cost = np.where(treat == "Do Nothing", np.nan, rng.uniform(1000, 90000, n).round(2))
    cost[3] = 0.0                                     # a real zero cost (treat[3] is not "Do Nothing")
    lanes = rng.choice([2, 4, 6], n)
    lanes[5] = 0                                      # a missing lane count
    from_desc = np.array([f"SR-{1000 + j}" for j in i], dtype=object)
    from_desc[11] = 'Old "Mill" Rd,\tramp\\A'         # a quote, a comma, a tab and a backslash
    mid_x, mid_y = Transformer.from_crs("EPSG:4326", "EPSG:32119", always_xy=True).transform(lon + 0.001, lat + 0.0005)
    seg = pd.DataFrame({
        "seg_id": seg_id, "pv_COUNTY": county, "pv_ROUTE": route, "pv_ROUTEID": [r + c[:3] for r, c in zip(route, county)],
        "pv_BEG_MP": beg, "pv_END_MP": beg + 0.4, "pv_FROM_DESC": from_desc, "pv_TO_DESC": [f"SR-{2000 + j}" for j in i],
        "pv_LENGTH": rng.uniform(0.1, 2.0, n).round(3), "pv_NC_SYSTEM_CODE": rng.choice(["Primary", "Secondary", "Interstate"], n),
        "pv_DIVISION": group + 1, "pv_NUMBER_OF_LANES": lanes, "pv_RTG_NBR": rating, "pv_PCS_SRVY_YR": rng.choice([2023, 2024, 2025], n),
        "pv_YEAR_LAST_REHAB": np.where(i % 9 == 0, np.nan, rng.integers(1995, 2024, n).astype(float)),
        "pv_LAST_REHAB_TYPE": rng.choice(["AC Thin Overlay", "Bituminous Treatment"], n),
        "pv_PMS_TREATMENT_NAME": treat, "pv_TREATMENT_COST": cost,
        "in_helene_zone": zone, "y_helene_failed": ((i % 10 == 0) & (zone == 1)).astype("int8"),
        "y_helene_damage": ((i % 20 == 0) & (zone == 1)).astype("int8"),
        "mid_x": mid_x, "mid_y": mid_y,
    })
    pred = pd.DataFrame({
        "seg_id": seg_id, "pred_rate": rate, "pred_years_to_poor": years, "pred_crack": rng.uniform(0, 1, n),
        "pred_flood": rng.uniform(0, 1, n),              # filled for every road, in or out of the zone, like the real file
        "in_helene_zone": zone, "rate_heldout": i % 10 < 7, "crack_heldout": i % 10 < 6, "flood_heldout": zone == 1,
    })
    aadt = np.where(i % 6 == 0, np.nan, rng.lognormal(8, 1, n))
    crash = pd.DataFrame({
        "seg_id": seg_id,
        "cr_crash_per_mvm": np.where(np.isnan(aadt) | (i % 11 == 0), np.nan, rng.uniform(0, 5, n)).round(3).astype("float32"),
        "cr_crash_per_mi_yr": np.where(i % 11 == 0, np.nan, rng.uniform(0, 30, n)).round(3).astype("float32"),
        "cr_cover": np.where(i % 11 == 0, 0.0, 1.0).astype("float32"),
        "cr_fatal_10yr": rng.integers(0, 3, n).astype("int32"), "cr_serious_10yr": rng.integers(0, 5, n).astype("int32"),
        "cr_ncdot_score": np.where(i % 11 == 0, np.nan, rng.uniform(0, 100, n)).round(3).astype("float32"),
        "tr_aadt_best": aadt.round(3).astype("float32"),
        "tr_aadt_best_source": np.where(np.isnan(aadt), "none", np.where(i % 2 == 0, "count", "estimate")),
    })
    return seg, pred, crash, lon, lat


def _reports(seg_id, lon, lat):
    """Charlotte and Raleigh reports: on a road, twice on one road, just too far, and nowhere near a road."""
    rows = []

    def add(source, kind, x, y, when):
        rows.append((source, f"{source}:{len(rows) + 1}", kind, pd.Timestamp(when), x, y))

    per = N_ROADS // 3
    for n, j in enumerate(range(per, per + 20)):        # 20 Charlotte roads, about 11 m off the centreline
        kind = "CDOT POTHOLE REPAIR" if n % 2 == 0 else "NCDOT POTHOLE REQUEST"
        add("charlotte", kind, lon[j] + 0.001, lat[j] + 0.0006, f"{2016 + n % 11}-{1 + n % 12:02d}-15 09:26")
    add("charlotte", "CDOT POTHOLE REPAIR", lon[per] + 0.001, lat[per] + 0.0006, "2025-03-02 12:00")   # second on one road
    for n, j in enumerate(range(2 * per, 2 * per + 10)):  # 10 Raleigh roads
        add("raleigh", "Pothole", lon[j] + 0.001, lat[j] + 0.0006, f"2025-{7 + n % 5:02d}-{1 + n:02d} 08:00")
    add("raleigh", "Pothole", lon[2 * per + 10] + 0.001, lat[2 * per + 10] + 0.0005 + 0.0005, "2026-01-05 08:00")  # about 55 m: too far for Raleigh
    for n in range(8):                                   # nowhere near a state road
        add("charlotte", "CDOT POTHOLE REPAIR", -80.80 + n * 0.001, 35.305, f"2019-0{1 + n}-10 10:00")
    d = pd.DataFrame(rows, columns=["source", "report_id", "request_type", "received_date", "lon", "lat"])
    d["received_date"] = d.received_date.astype("datetime64[ms]")
    return d


def _camera_frames(seg_id):
    """Coastal cameras with real flags, two cameras sharing a site, and NCDOT stills that are known dry."""
    rows = []
    coastal = [("BF_01", "BF_01", "Front Street", 34.7159, -76.6640, None),
               ("CB_01", "CB_01", "Clam Shell Ln. 1", 34.0420, -77.8900, None),
               ("CB_01B", "CB_01", "Clam Shell Ln. 2", 34.0421, -77.8901, None),
               ("DE_02", "DE_02", "North River", 34.7900, -76.6100, seg_id[250])]
    for station, site, name, la, lo, seg in coastal:
        for day in ("2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27"):
            for t in pd.date_range(f"{day} 13:00", f"{day} 16:00", freq="20min"):
                p = 0.1
                if station == "BF_01" and day in ("2026-09-26", "2026-09-27"):
                    p = 0.9
                if station == "CB_01" and day == "2026-09-27":
                    p = 0.8
                if station == "BF_01" and day == "2026-09-25":      # flags early in the 14:00 hour, dry later in it
                    p = 0.95 if t == pd.Timestamp("2026-09-25 14:00") else 0.05
                rows.append((station, site, name, la, lo, seg, 12.0 if seg else np.nan, t,
                             f"frames/{station}/{station}_{t:%Y-%m-%dT%H%MZ}.jpg", "cv",
                             12.0 if p >= 0.5 else 0.0, p, round(10 * p, 3), "frozen_camera"))
    for k in range(30):                                   # NCDOT stills: pairs share a time; two false alarms
        cam = 5000 + k
        seg = seg_id[k] if k < 25 else None
        t = pd.Timestamp("2026-10-03 18:30") + pd.Timedelta(minutes=k // 2)
        p = 0.7 if k in (4, 9) else 0.01
        rows.append(("NCDOT", f"NCDOT_{cam}", f"CCTV-{cam}", 35.5 + k * 0.01, -79.0 - k * 0.01, seg, 20.0 if seg else np.nan, t,
                     f"../cctv/look/{cam}.jpg", "extra", np.nan, p, round(10 * p, 3), "frozen_camera"))
    d = pd.DataFrame(rows, columns=["station", "site", "name", "lat", "lon", "seg_id", "seg_dist_m", "time_utc", "file",
                                    "role", "depth_measured_cm", "p_flooded", "depth_pred_cm", "run"])
    d["time_utc"] = d.time_utc.astype("datetime64[ns]")
    return d


def _sensor_file(path, name, lon, lat, level, bad_at=None, raw=True):
    """One station file in the feed's layout: newest first, values as text, a filtered series before the raw one."""
    times = pd.date_range("2026-09-24 00:00", "2026-09-27 23:54", freq="6min")
    values = [f"{level(t):.6f}" for t in times]
    if bad_at is not None:
        values[bad_at] = "n/a"
    obs = {"times": [t.strftime("%Y-%m-%dT%H:%M:%S") for t in times][::-1], "values": values[::-1],
           "quality_levels": ["0"] * len(times)}
    params = [{"id": "water_level", "units": "m", "observations": {"times": obs["times"], "values": ["9.9"] * len(times)}}]
    if raw:
        params.append({"id": "water_level_raw", "units": "m", "observations": obs})
    params.append({"id": "webcam_img_url", "units": " ", "observations": {"times": [], "values": []}})
    doc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
           "properties": {"platform_id": f"SUNNYD_{path.stem}", "platform_short_name": name, "parameters": params}}]}
    path.write_text(json.dumps(doc))


def make_fixture_root(root):
    """Write the small folder. Layout and column names follow the real files."""
    import geopandas as gpd
    from shapely.geometry import LineString, box
    from src.pipeline import pothole_labels
    from src.pipeline.pull_potholes import sha256_file

    root = Path(root)
    for d in ("handoff", "data/processed", "data/raw/sunnyday/levels"):
        (root / d).mkdir(parents=True, exist_ok=True)
    seg, pred, crash, lon, lat = _roads()
    geom = [LineString([(x, y), (x + 0.002, y + 0.001)]) for x, y in zip(lon, lat)]
    seg.to_parquet(root / "data/processed/segments.parquet")
    gpd.GeoDataFrame(pred, geometry=geom, crs="EPSG:4326").to_parquet(root / "handoff/predictions_geo.parquet")
    crash.to_parquet(root / "handoff/traffic_crash.parquet")
    gpd.GeoDataFrame({"seg_id": seg.seg_id, "YEAR_LAST_REHAB": seg.pv_YEAR_LAST_REHAB}, geometry=geom,
                     crs="EPSG:4326").to_parquet(root / "data/raw/ncdot_joined.parquet")

    rep = _reports(seg.seg_id.values, lon, lat)
    gpd.GeoDataFrame(rep[["source", "report_id", "request_type", "received_date"]],
                     geometry=gpd.points_from_xy(rep.lon, rep.lat), crs="EPSG:4326").to_parquet(root / "data/raw/pothole_reports.parquet")
    gpd.GeoDataFrame({"city": ["charlotte", "raleigh"], "geoid": ["3712000", "3755000"]},
                     geometry=[box(-80.95, 35.15, -80.75, 35.35), box(-78.75, 35.70, -78.55, 35.90)],
                     crs="EPSG:4326").to_parquet(root / "data/raw/city_limits.parquet")
    meta = {"pulled_at": PULLED_AT, "sha256": {n: sha256_file(root / "data/raw" / n)
                                               for n in ("pothole_reports.parquet", "city_limits.parquet")}}
    (root / "data/raw/pothole_reports.meta.json").write_text(json.dumps(meta))
    pothole_labels.main(raw=root / "data/raw", processed=root / "data/processed")   # the real matcher writes the labels

    _camera_frames(seg.seg_id.values).to_parquet(root / "data/processed/flood_camera_depth.parquet")

    storm = lambda t: t.day in (26, 27) and 13 <= t.hour < 16
    lv = root / "data/raw/sunnyday/levels"
    _sensor_file(lv / "BF_01.json", "Front Street", -76.6640, 34.7159, lambda t: 1.0 if storm(t) else 0.5, bad_at=100)
    _sensor_file(lv / "CB_01.json", "Clam Shell Ln. 1", -77.8900, 34.0420, lambda t: 0.9 if (t.day == 27 and 13 <= t.hour < 16) else 0.4)
    _sensor_file(lv / "CB_01B.json", "Clam Shell Ln. 2", -77.8901, 34.0421, lambda t: 0.0, raw=False)   # no sensor of its own
    _sensor_file(lv / "DE_02.json", "North River", -76.6100, 34.7900, lambda t: 0.3)                    # always dry
    _sensor_file(lv / "ZZ_09.json", "No Road Height", -76.5000, 34.7000, lambda t: 0.6)                 # no road height known
    return root


# ---------------------------------------------------------------------------------------------- fixtures

@pytest.fixture(scope="session")
def fixture_root(tmp_path_factory):
    """Read-only by convention: a test that needs to change a file copies the folder first."""
    return make_fixture_root(tmp_path_factory.mktemp("dash") / "root")


@pytest.fixture(scope="session")
def real_root():
    """The worktree root, when the shared data files are on this machine."""
    root = Path(".").resolve()
    missing = [f for f in REAL_FILES if not (root / f).exists()]
    if missing:
        pytest.skip(f"{missing[0]} is not on this machine")
    return root


def open_test_database(env):
    """The checks every database test session starts with. Returns the address. Never drops anything."""
    from web.tiger import config
    url = env.get("TIGER_TEST_DATABASE_URL") or LOCAL_URL
    remote_ok = env.get("TIGER_TEST_ALLOW_REMOTE") == "1"
    if not remote_ok:
        config.require_local(url, env=env)
    try:
        conn = config.connect(url, autocommit=True, connect_timeout=3)
    except config.DatabaseUnavailable:
        pytest.skip("local test database is not running (see web/README.md)")
    try:
        if not remote_ok:
            config.assert_local(conn)
    finally:
        conn.close()
    return url


@pytest.fixture(scope="session")
def db_url():
    with pytest.MonkeyPatch.context() as mp:
        for key in [k for k in os.environ if k.startswith("PG")]:
            mp.delenv(key)
        yield open_test_database(os.environ)


def new_schema():
    return "test_" + secrets.token_hex(6)


def drop_schema(url, schema):
    from psycopg import sql
    from web.tiger import config
    if not schema.startswith("test_"):
        raise RuntimeError(f"refusing to drop {schema}: not a test schema")
    conn = config.connect(url, autocommit=True)
    try:
        config.assert_local(conn)
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
    finally:
        conn.close()


def load_fixture(url, root, schema, **kw):
    from web.tiger import load
    with sunnyday_out(root):
        return load.load(url, root=root, schema=schema, schedule_jobs=False, **kw)


@pytest.fixture(scope="module")
def loaded_schema(db_url, fixture_root):
    """The fixture folder loaded once per test module. Tests must not change it; use fresh_schema for that."""
    schema = new_schema()
    try:
        load_fixture(db_url, fixture_root, schema)
        yield schema
    finally:
        drop_schema(db_url, schema)


@pytest.fixture
def fresh_schema(db_url, fixture_root):
    """The fixture folder loaded for one test that changes data."""
    schema = new_schema()
    try:
        load_fixture(db_url, fixture_root, schema)
        yield schema
    finally:
        drop_schema(db_url, schema)


@pytest.fixture
def empty_schema(db_url):
    """A schema name with nothing loaded; dropped afterwards."""
    schema = new_schema()
    try:
        yield schema
    finally:
        drop_schema(db_url, schema)


@pytest.fixture(scope="session")
def real_schema(db_url, real_root):
    """The real files loaded once for the whole session. Read-only."""
    from web.tiger import load
    schema = new_schema()
    try:
        load.load(db_url, root=real_root, schema=schema, schedule_jobs=False)
        yield schema
    finally:
        drop_schema(db_url, schema)


def copy_root(src, dst):
    """A private copy of the fixture folder for a test that changes a file."""
    import shutil
    shutil.copytree(src, Path(dst))
    return Path(dst)


def refresh_report_manifest(root):
    """After a test rewrites the report files: make their manifest match again."""
    from src.pipeline.pull_potholes import sha256_file
    raw = Path(root) / "data/raw"
    meta = json.loads((raw / "pothole_reports.meta.json").read_text())
    meta["sha256"] = {n: sha256_file(raw / n) for n in meta["sha256"]}
    (raw / "pothole_reports.meta.json").write_text(json.dumps(meta))


def rewrite(root, rel, change):
    """Read one parquet file of a copied folder, change it, write it back (geometry files keep their geometry)."""
    import geopandas as gpd
    path = Path(root) / rel
    try:
        d = gpd.read_parquet(path)
    except ValueError:                     # no geometry column
        d = pd.read_parquet(path)
    change(d).to_parquet(path)
    if rel.startswith("data/raw/pothole_reports") or rel.startswith("data/raw/city_limits"):
        refresh_report_manifest(root)


@pytest.fixture(scope="session")
def dash():
    """Helpers for the tests (a conftest cannot be imported by name)."""
    return SimpleNamespace(fake_url=fake_url, sunnyday_out=sunnyday_out, make_fixture_root=make_fixture_root,
                           open_test_database=open_test_database, new_schema=new_schema, drop_schema=drop_schema,
                           load_fixture=load_fixture, copy_root=copy_root, rewrite=rewrite,
                           refresh_report_manifest=refresh_report_manifest, LOCAL_URL=LOCAL_URL, N_ROADS=N_ROADS)
