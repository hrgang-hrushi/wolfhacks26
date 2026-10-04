"""src/api.py serves only real columns, and its bbox query uses the spatial index."""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # the pipeline environment does not carry the web server

from src import api  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INVENTED = {"pv_rating", "pv_age", "name", "flood_rank", "drivers", "chip_url", "score", "city"}


@pytest.fixture(scope="module")
def store():
    path = ROOT / "handoff" / "predictions_geo.parquet"
    if not path.exists():
        pytest.skip("handoff/predictions_geo.parquet is not present")
    return api.Store(path)


def test_records_carry_only_real_columns(store):
    rec = store.record(0)
    assert not INVENTED & set(rec)
    assert set(rec) == {
        "seg_id", "pred_rate", "pred_years_to_poor", "pred_crack", "pred_flood",
        "in_helene_zone", "rate_heldout", "crack_heldout", "flood_heldout", "paths",
    }


def test_flood_is_blank_outside_the_helene_zone(store):
    outside = store.df.index[store.df.in_helene_zone == 0][0]
    inside = store.df.index[store.df.in_helene_zone == 1][0]
    assert store.record(int(outside))["pred_flood"] is None
    assert store.record(int(inside))["pred_flood"] is not None


def test_missing_years_to_poor_stays_missing(store):
    i = int(store.df.index[store.df.pred_years_to_poor.isna()][0])
    assert store.record(i)["pred_years_to_poor"] is None


def test_bbox_returns_roads_that_touch_the_box(store):
    box = (-78.70, 35.75, -78.60, 35.82)  # central Raleigh
    out = store.bbox(*box, limit=50)
    assert 0 < out["count"] <= 50 and out["matched"] >= out["count"]
    assert out["truncated"] == (out["matched"] > 50)
    for seg in out["segments"]:
        xs = [x for part in seg["paths"] for x, _ in part]
        ys = [y for part in seg["paths"] for _, y in part]
        assert min(xs) <= box[2] and max(xs) >= box[0] and min(ys) <= box[3] and max(ys) >= box[1]


def test_bbox_over_open_ocean_is_empty(store):
    assert store.bbox(-70.0, 30.0, -69.0, 31.0)["count"] == 0


def test_there_is_no_simulate_or_weather_endpoint():
    src = (ROOT / "src" / "api.py").read_text()
    assert '"/api/simulate"' not in src and '"/api/weather"' not in src
