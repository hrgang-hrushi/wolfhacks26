"""server/main.py is the API the hosted site calls. Its labels come from the road's own id, and blanks stay blank."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # the pipeline environment does not carry the web server

ROOT = Path(__file__).resolve().parents[2]
# server/ is the hosted API's own root. It goes last on the path so nothing here shadows the repo's packages.
sys.path.append(str(ROOT / "server"))
import main  # noqa: E402


@pytest.fixture(scope="module")
def store():
    path = ROOT / "server" / "predictions_geo.parquet"
    if not path.exists():
        pytest.skip("server/predictions_geo.parquet is not present")
    return main.Store(path)


def test_route_and_county_come_from_the_id():
    assert main.route_label("20000013008") == "US 13"
    assert main.route_label("10000040092") == "I-40"
    assert main.route_label("40002748092") == "SR 2748"
    assert main.county_name("20000013008") == "Bertie"
    assert main.county_name("40002748092") == "Wake"
    assert main.county_name("40002748000") is None and main.county_name("x") is None
    assert len(main.NC_COUNTIES) == 100 and main.NC_COUNTIES == sorted(main.NC_COUNTIES)


def test_a_record_is_named_after_its_own_route(store):
    rec = store.record(0)
    route_id = rec["seg_id"].split(":")[1]
    assert rec["name"].startswith(main.route_label(route_id))
    assert main.county_name(route_id) in rec["name"]
    assert rec["city"] in {m[0] for m in main.METROS}


def test_a_missing_forecast_stays_missing(store):
    i = int(store.df.index[store.df.pred_years_to_poor.isna()][0])
    rec = store.record(i)
    assert rec["years_to_poor"] is None and rec["pred_years_to_poor"] is None
    assert rec["score"] is None and rec["pv_rating"] is None


def test_flood_label_follows_the_score_not_just_the_zone(store):
    df = store.df
    outside = int(df.index[df.in_helene_zone == 0][0])
    low = int(df.index[(df.in_helene_zone == 1) & (df.pred_flood < 0.1)][0])
    high = int(df.index[(df.in_helene_zone == 1) & (df.pred_flood >= main.HIGH_FLOOD)][0])
    assert store.record(outside)["pred_flood"] is None
    assert store.record(outside)["flood_rank"].startswith("Not scored")
    assert store.record(low)["flood_rank"].startswith("Lower")
    assert store.record(high)["flood_rank"].startswith("High")


def test_a_statewide_box_is_spread_over_the_state(store):
    out = store.bbox(-84.5, 33.7, -75.2, 36.7, limit=600)
    assert out["count"] == 600 and out["truncated"] and out["matched"] == len(store)
    lngs = [seg["path"][0][0] for seg in out["segments"]]
    assert min(lngs) < -83.0 and max(lngs) > -76.5  # mountains to coast, not one corner


def test_bbox_returns_roads_that_touch_the_box(store):
    box = (-78.70, 35.75, -78.60, 35.82)  # central Raleigh
    out = store.bbox(*box, limit=50)
    assert 0 < out["count"] <= 50 and out["matched"] >= out["count"]
    for seg in out["segments"]:
        xs = [x for part in seg["paths"] for x, _ in part]
        ys = [y for part in seg["paths"] for _, y in part]
        assert min(xs) <= box[2] and max(xs) >= box[0] and min(ys) <= box[3] and max(ys) >= box[1]


def test_every_part_of_a_split_road_is_returned(store):
    multi = next(i for i, g in enumerate(store.geoms) if g.geom_type != "LineString")
    rec = store.record(multi)
    assert len(rec["paths"]) > 1 and rec["path"] == rec["paths"][0]


def test_requests_are_capped_and_checked():
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    assert client.get("/api/segments", params={"limit": main.MAX_LIMIT + 1}).status_code == 422
    assert client.get("/api/segments/bbox", params={"minx": "nan", "miny": 35, "maxx": -78, "maxy": 36}).status_code == 422
    assert client.get("/api/segments/bbox", params={"minx": -78, "miny": 35, "maxx": -79, "maxy": 36}).status_code == 422
    assert client.get("/api/health").json()["status"] == "ok"


def test_tiger_routes_are_absent_without_the_setting():
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    if main.TIGER_STATE == "not configured":
        assert client.get("/api/tiger/status").json() == {"configured": False, "state": "not configured"}
        assert client.get("/api/tiger/health").status_code == 404
    assert client.get("/api/stats").status_code == 200          # the road API works either way


def test_tiger_service_attaches_and_reports_an_unreachable_database(monkeypatch):
    """With the setting present the service mounts at once, and a database that does not answer is a clean 503."""
    pytest.importorskip("psycopg_pool")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TIGER_DATABASE_URL", "postgresql://nobody@127.0.0.1:9/none")   # nothing listens on port 9
    api = FastAPI()
    assert main._attach_tiger(api) == "attached"
    reply = TestClient(api).get("/api/tiger/health")
    assert reply.status_code == 503
    body = reply.json()
    assert body["error"] == "database unavailable" and "127.0.0.1" not in reply.text
