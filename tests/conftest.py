"""Fixtures: a small synthetic table shaped like data/processed/segments.parquet."""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString

from src.model import common


def make_table(n_blocks=40, per_block=50, seed=0):
    """40 blocks on an 8 x 5 grid of 5 km squares; the wear rate depends on lanes and traffic."""
    rng = np.random.default_rng(seed)
    n = n_blocks * per_block
    bx = 100 + (np.arange(n) // per_block) % 8
    by = 40 + (np.arange(n) // per_block) // 8
    lanes = rng.choice([2, 4, 6], n)
    aadt = rng.lognormal(8, 1, n)
    rehab = rng.integers(1995, 2024, n).astype(float)
    srvy = rng.choice([2023, 2024, 2025], n)
    age = srvy - rehab
    true_rate = 0.5 + 0.3 * lanes + 0.4 * np.log10(aadt) + rng.normal(0, 0.3, n)
    rating = np.clip(100 - true_rate * np.clip(age, 0, None), 1, 100)
    has_asph = rng.random(n) < 0.7
    crack = np.clip(2 * lanes + rng.normal(0, 4, n), 0, None).round()
    zone = (bx < 104).astype("int8")
    d = pd.DataFrame({
        "seg_id": [f"ncdot:{i:011d}:0.000" for i in range(n)],
        "pv_RTG_NBR": rating,
        "pv_PCS_SRVY_YR": srvy,
        "pv_YEAR_LAST_REHAB": np.where(rng.random(n) < 0.1, np.nan, rehab),
        "pv_PVMNT_AGE": 2025 - rehab,
        "pv_NUMBER_OF_LANES": lanes,
        "pv_SEC_WIDTH": 12 * lanes,
        "pv_SHOULDER_WIDTH": rng.choice([0.0, 2.0, 4.0], n),
        "pv_LENGTH": rng.uniform(0.1, 2.0, n),
        "pv_LAST_REHAB_TYPE": rng.choice(["AC Thin Overlay", "AC Major Rehabilitation", "Bituminous Treatment"], n),
        "pv_SURFACE": rng.choice(["Plant_Mix", "BST"], n),
        "pv_NC_SYSTEM_CODE": rng.choice(["Primary", "Secondary", "Interstate"], n),
        "pv_SUBDIVISION_RURAL_CODE": rng.choice(["N/A", "Rural", "Subdivision"], n),
        "pv_CURB": rng.choice(["Y", "N"], n),
        "pv_asph_PAVEMENT_TYPE": np.where(has_asph, "P", None),
        "pv_asph_RSRF_THCKNS_NBR": pd.Series([None] * n, dtype=object),
        "pv_asph_ALGTR_MDRT_PCT": np.where(has_asph, crack, np.nan),
        "pv_asph_ALGTR_HGH_PCT": np.where(has_asph, 0.0, np.nan),
        "tr_aadt": np.where(rng.random(n) < 0.5, aadt, np.nan),
        "tr_aadtt": aadt * 0.05,
        "tr_su_pct": rng.uniform(0, 10, n),
        "tr_mu_pct": rng.uniform(0, 10, n),
        "tr_has_count": rng.integers(0, 2, n),
        "tr_aadt_source": rng.choice(["none", "traffic_segments", "pavement_survey"], n),
        "y_helene_failed": ((rng.random(n) < 0.02 + 0.03 * (lanes == 2)) & (zone == 1)).astype("int8"),
        "in_helene_zone": zone,
        "mid_x": bx * 5000.0 + rng.uniform(0, 5000, n),
        "mid_y": by * 5000.0 + rng.uniform(0, 5000, n),
    })
    return d


@pytest.fixture
def small_models(monkeypatch):
    """30 trees instead of 400. Opt in per module, so tests/vision/ is not affected."""
    monkeypatch.setattr(common, "N_ESTIMATORS", 30)


@pytest.fixture
def table():
    return make_table()


def write_fixture_dir(path, d=None):
    """Write segments.parquet and segments_geom.parquet the way src.pipeline.features does."""
    d = make_table() if d is None else d
    path.mkdir(parents=True, exist_ok=True)
    d.to_parquet(path / "segments.parquet")
    lon, lat = -84 + d.mid_x / 1e6, 34 + d.mid_y / 1e6
    geom = [LineString([(x, y), (x + 0.001, y + 0.001)]) for x, y in zip(lon, lat)]
    gpd.GeoDataFrame({"seg_id": d.seg_id}, geometry=geom, crs="EPSG:4326").to_parquet(path / "segments_geom.parquet")
    return path


@pytest.fixture
def write_dir():
    return write_fixture_dir


TRACKED_MAP_FILE = Path("handoff/predictions_geo.parquet")


@pytest.fixture(scope="session")
def scripts_run(tmp_path_factory):
    """train_tabular then final_ablation, once, on a fixture directory with no embeddings file."""
    from src.model import final_ablation, train_tabular
    mp = pytest.MonkeyPatch()
    mp.setattr(common, "N_ESTIMATORS", 30)
    p = write_fixture_dir(tmp_path_factory.mktemp("run") / "processed")
    handoff = p.parent / "handoff"
    before = TRACKED_MAP_FILE.stat().st_mtime_ns if TRACKED_MAP_FILE.exists() else None
    train_tabular.main(p)
    first_csv = (p / "ablation.csv").read_bytes()
    final_ablation.main(p, handoff_dir=handoff)
    after = TRACKED_MAP_FILE.stat().st_mtime_ns if TRACKED_MAP_FILE.exists() else None
    yield dict(p=p, handoff=handoff, first_csv=first_csv, tracked_untouched=before == after)
    mp.undo()
