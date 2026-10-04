"""The data service: read-only, honest about blanks and limits, safe against bad input and a dead database."""
import io
import json
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient

from web.service import app as service
from web.service import queries
from web.tiger import build, config, export, schema

UTC = timezone.utc
NEXT_DAY = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
ROUTES = ["/api/health", "/api/summary", "/api/worklist", "/api/road", "/api/alerts", "/api/alerts/peaks",
          "/api/camera_history", "/api/stats", "/api/export/risk.csv", "/api/export/dictionary"]


def strict(response):
    """Parse the body the way a browser does: NaN and Infinity are errors."""
    def refuse(token):
        raise ValueError(f"{token} is not JSON")
    return json.loads(response.text, parse_constant=refuse)


def make_client(url, schema_name, clock=None, **settings):
    return TestClient(service.create_app(settings=service.Settings(url=url, schema=schema_name, **settings),
                                         clock=clock or (lambda: NEXT_DAY)))


@pytest.fixture(scope="module")
def built(fixture_root, dash):
    with dash.sunnyday_out(fixture_root):
        return build.build_all(fixture_root)


@pytest.fixture(scope="module")
def client(db_url, loaded_schema):
    with make_client(db_url, loaded_schema) as c:
        yield c


@pytest.fixture(scope="module")
def real_client(db_url, real_schema):
    with make_client(db_url, real_schema) as c:
        yield c


@pytest.fixture
def dead_client(dash):
    """The service started against an address where nothing listens, with one-second limits."""
    with make_client(dash.fake_url(), "unwatched", connect_timeout=1, pool_wait=1) as c:
        yield c


def params_for(path, built):
    roads = built.tables["roads"]
    return {"/api/road": {"seg_id": roads.seg_id.iloc[100]}, "/api/camera_history": {"camera_id": "BF_01"},
            "/api/alerts": {"as_of": "2026-09-27T15:30:00Z"}}.get(path, {})


# ------------------------------------------------------------------------------------------------ pure pieces (no database)

@pytest.mark.parametrize("value, want", [
    (float("nan"), None), (float("inf"), None), (float("-inf"), None), (1.5, 1.5), (None, None), (True, True), (7, 7),
    (Decimal("2.50"), 2.5), (Decimal("NaN"), None), ("text", "text"),
    (datetime(2026, 9, 24, 11, 6, tzinfo=UTC), "2026-09-24T11:06:00Z"),
    (datetime(2026, 9, 24, 7, 6, tzinfo=timezone(timedelta(hours=-4))), "2026-09-24T11:06:00Z"),
])
def test_A7_one_value_as_json(value, want):
    assert service.clean(value) == want


def test_A7_a_non_finite_number_never_reaches_a_reply():
    body = service.respond({"a": float("nan"), "b": [float("inf"), {"c": Decimal("Infinity")}], "d": (1, 2)}).body
    assert json.loads(body, parse_constant=lambda t: pytest.fail(t)) == {"a": None, "b": [None, {"c": None}], "d": [1, 2]}


def test_A9_an_alert_for_a_camera_with_no_camera_row_is_still_returned():
    """A reading whose camera is missing from the camera table must not turn the whole reply into an error."""
    class Cursor:
        def __init__(self, names, rows):
            self.description = [type("C", (), {"name": n}) for n in names]
            self._rows = rows

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

    t = datetime(2026, 9, 27, 15, 6, tzinfo=UTC)

    class Conn:
        def execute(self, query, params=None):
            text = query if isinstance(query, str) else str(query)
            if "FROM camera_hourly" in text:
                return Cursor(["camera_id", "is_replay"], [("GHOST", False)])
            if "FROM camera_readings" in text and "p_flooded DESC" in text:
                return Cursor(["time", "p_flooded", "depth_pred_cm", "depth_measured_cm", "replay_of"], [(t, 0.9, 9.0, None, None)])
            if "FROM camera_readings" in text:
                return Cursor(["time", "p_flooded", "depth_pred_cm", "depth_measured_cm"], [(t, 0.9, 9.0, None)])
            return Cursor(["x"], [])                                      # no camera row, no sensor alerts

    body = queries.alerts(Conn(), datetime(2026, 9, 27, 15, 30, tzinfo=UTC), NEXT_DAY)
    assert [a["camera_id"] for a in body["camera_alerts"]] == ["GHOST"]
    assert body["camera_alerts"][0]["name"] is None and body["camera_alerts"][0]["road"] is None


@pytest.mark.parametrize("text", ["2026-09-27T15:30:00", "yesterday", "", "2026-13-45T00:00:00Z"])
def test_A9_a_time_without_a_zone_or_that_does_not_parse_is_rejected(text):
    with pytest.raises(queries.BadRequest):
        queries.parse_time(text)


def test_A9_a_time_is_read_in_utc():
    assert queries.parse_time("2026-09-27T15:30:00Z") == datetime(2026, 9, 27, 15, 30, tzinfo=UTC)
    assert queries.parse_time("2026-09-27T11:30:00-04:00") == datetime(2026, 9, 27, 15, 30, tzinfo=UTC)


def test_the_flooded_depth_is_the_flood_chats_own_number():
    line = re.search(r"^FLOODED_CM = ([0-9.]+)", Path("src/model/flood_camera.py").read_text(), re.M)
    assert line and float(line.group(1)) == queries.FLOODED_CM            # copied, because that module imports PyTorch


def test_A5_the_only_names_that_can_reach_a_query_are_fixed():
    assert set(queries.SORTS.values()) <= set(schema.columns("roads"))
    assert set(queries.DIRECTIONS.values()) == {"ASC", "DESC"}
    src = Path("web/service/queries.py").read_text()
    assert ".format(" in src and " % " not in src and 'f"SELECT' not in src.replace('f"SELECT time, ', "")   # no values formatted into SQL


def test_A14_every_route_is_get_only_by_construction():
    methods = {r.path: r.methods for r in service.app.routes if getattr(r, "path", "").startswith("/api/")}
    assert set(methods) == set(ROUTES) and all(m == {"GET"} for m in methods.values())


def test_the_service_does_not_connect_or_read_settings_when_imported(monkeypatch, tmp_path):
    monkeypatch.delenv(config.ENV_KEY, raising=False)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    assert service.create_app() is not None                               # building the app needs no settings


def test_S3_the_service_refuses_to_start_without_its_setting_and_names_it(monkeypatch, tmp_path):
    monkeypatch.delenv(config.ENV_KEY, raising=False)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    with pytest.raises(config.ConfigError, match=config.ENV_KEY):
        with TestClient(service.create_app()):
            pass


# ------------------------------------------------------------------------------------------------ A12, A13, S2: no database needed

def test_A12_a_dead_database_gives_a_503_quickly_and_leaks_nothing(dead_client):
    started = time.time()
    r = dead_client.get("/api/worklist")
    took = time.time() - started
    assert r.status_code == 503 and took < 2.0                             # the one-second limit plus one second
    body = strict(r)
    assert body["error"] == "database unavailable" and body["kind"] in ("network", "unavailable")
    for secret in ("pw-marker", "user-marker", "127.0.0.1", "postgresql"):
        assert secret not in r.text


@pytest.mark.parametrize("path", ["/api/health", "/api/summary", "/api/stats", "/api/road?seg_id=ncdot:1:0.000",
                                  "/api/alerts", "/api/export/risk.csv"])
def test_A12_every_database_route_fails_the_same_way(path, dead_client):
    r = dead_client.get(path)
    assert r.status_code == 503 and strict(r)["error"] == "database unavailable" and "marker" not in r.text


def test_A12_routes_that_need_no_database_still_answer(dead_client):
    assert dead_client.get("/api/export/dictionary").status_code == 200


def test_S2_the_pool_log_line_for_a_failed_connection_is_scrubbed(dash, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="psycopg.pool"):
        with make_client(dash.fake_url(), "unwatched", connect_timeout=1, pool_wait=1) as c:
            c.get("/api/health")
            time.sleep(0.5)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert caplog.records, "the pool logged nothing, so this test proves nothing"
    assert "database connection problem" in text
    for secret in ("pw-marker", "user-marker", "127.0.0.1", "port 1"):
        assert secret not in text
    assert all(r.exc_info is None for r in caplog.records)


def test_A13_without_a_list_any_site_may_read_but_never_with_credentials(dead_client):
    r = dead_client.get("/api/export/dictionary", headers={"Origin": "https://anything.example"})
    assert r.headers["access-control-allow-origin"] == "*" and "access-control-allow-credentials" not in r.headers


def test_A13_with_a_list_only_those_sites_get_the_header(dash):
    allowed = "https://roads.example"
    with make_client(dash.fake_url(), "unwatched", connect_timeout=1, pool_wait=1, allowed_origins=[allowed]) as c:
        ok = c.get("/api/export/dictionary", headers={"Origin": allowed})
        other = c.get("/api/export/dictionary", headers={"Origin": "https://evil.example"})
    assert ok.headers["access-control-allow-origin"] == allowed
    assert "access-control-allow-origin" not in other.headers
    assert "access-control-allow-credentials" not in ok.headers and "access-control-allow-credentials" not in other.headers


def test_A13_the_list_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example, https://b.example")
    assert service._origins(service.Settings()) == ["https://a.example", "https://b.example"]
    monkeypatch.delenv("ALLOWED_ORIGINS")
    assert service._origins(service.Settings()) == ["*"]


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_A14_write_requests_are_rejected(method, dead_client):
    for path in ("/api/worklist", "/api/road", "/api/alerts", "/api/export/risk.csv"):
        assert getattr(dead_client, method)(path).status_code == 405


# ------------------------------------------------------------------------------------------------ A1 to A8 (database)

@pytest.mark.db
def test_A1_bucket_counts_equal_the_built_table(client, built):
    want = built.tables["roads"].repair_bucket.value_counts().to_dict()
    body = strict(client.get("/api/summary"))
    assert {b: n for b, n in body["buckets"].items() if n} == want and body["roads"] == len(built.tables["roads"])
    assert body["load"]["status"] == "complete" and len(body["what_this_cannot_claim"]) >= 5
    for bucket, n in want.items():
        assert strict(client.get("/api/worklist", params={"bucket": bucket, "limit": 1}))["total"] == n


@pytest.mark.db
@pytest.mark.realdata
def test_A1_real_bucket_counts_from_the_service(real_client):
    body = strict(real_client.get("/api/summary"))
    assert body["buckets"] == {"fix_now": 4_432, "within_1y": 794, "within_5y": 4_699, "later": 100_875, "unknown": 1_643}
    assert body["heldout"] == {"wear_rate": 77_422, "crack_risk": 68_349, "flood_risk": 32_558}
    assert body["roads"] == 112_443 and body["in_helene_zone"] == 32_558
    first = strict(real_client.get("/api/worklist", params={"limit": 3}))
    assert [r["rank"] for r in first["roads"]] == [1, 2, 3] and all(r["bucket"] == "fix_now" for r in first["roads"])


@pytest.mark.db
def test_A2_pages_do_not_overlap_or_skip(client, built):
    roads = built.tables["roads"]
    seen = []
    for offset in range(0, len(roads), 70):
        page = strict(client.get("/api/worklist", params={"limit": 70, "offset": offset}))
        seen += [r["seg_id"] for r in page["roads"]]
    assert seen == roads.sort_values("priority_rank").seg_id.tolist()      # every road once, worst first


@pytest.mark.db
def test_A2_ties_break_by_id(client, built):
    roads = built.tables["roads"]
    got = [r["seg_id"] for r in strict(client.get("/api/worklist", params={"sort": "years_to_poor", "bucket": "fix_now",
                                                                         "limit": 500}))["roads"]]
    fix_now = roads[roads.repair_bucket == "fix_now"]
    assert len(got) == len(fix_now) > 10 and got == sorted(fix_now.seg_id)   # all at 0 years: the order is the id
    down = [r["seg_id"] for r in strict(client.get("/api/worklist", params={"sort": "rating", "direction": "desc", "limit": 5}))["roads"]]
    assert down == roads.sort_values(["rating", "seg_id"], ascending=[False, True]).seg_id.head(5).tolist()


@pytest.mark.db
def test_A3_page_size_is_capped(client, built):
    body = strict(client.get("/api/worklist", params={"limit": 1_000_000}))
    assert body["limit"] == queries.MAX_PAGE == 500 and len(body["roads"]) == min(500, len(built.tables["roads"]))


@pytest.mark.db
@pytest.mark.realdata
def test_A3_one_request_never_returns_every_road(real_client):
    body = strict(real_client.get("/api/worklist", params={"limit": 1_000_000}))
    assert len(body["roads"]) == 500 and body["total"] == 112_443


@pytest.mark.db
@pytest.mark.parametrize("params", [{"limit": 0}, {"offset": -1}, {"limit": "many"}])
def test_A3_a_bad_page_request_is_rejected(params, client):
    assert client.get("/api/worklist", params=params).status_code in (400, 422)


@pytest.mark.db
@pytest.mark.parametrize("hostile", ["'; DROP TABLE roads; --", "Wake' OR '1'='1", '"; DELETE FROM roads; --'])
def test_A4_hostile_filter_text_is_only_ever_a_value(hostile, client, built):
    for field in ("county", "system"):
        body = strict(client.get("/api/worklist", params={field: hostile}))
        assert body["total"] == 0 and body["roads"] == []
    assert strict(client.get("/api/summary"))["roads"] == len(built.tables["roads"])     # the table is still there, whole


@pytest.mark.db
@pytest.mark.parametrize("params", [{"sort": "priority_rank; DROP TABLE roads"}, {"sort": "seg_id"}, {"sort": ""},
                                    {"direction": "sideways"}, {"direction": "asc; DROP TABLE roads"}, {"bucket": "x' OR '1'='1"}])
def test_A4_A5_a_sort_or_bucket_outside_the_list_is_rejected(params, client, built):
    r = client.get("/api/worklist", params=params)
    assert r.status_code == 400 and "must be" in strict(r)["error"]
    assert strict(client.get("/api/summary"))["roads"] == len(built.tables["roads"])


@pytest.mark.db
def test_A5_every_listed_sort_works(client):
    for sort in queries.SORTS:
        for direction in queries.DIRECTIONS:
            assert client.get("/api/worklist", params={"sort": sort, "direction": direction, "limit": 3}).status_code == 200


@pytest.mark.db
def test_A6_a_road_is_found_by_an_id_with_colons_and_dots(client, built):
    roads = built.tables["roads"].set_index("seg_id")
    seg_id = roads.index[100]
    body = strict(client.get("/api/road", params={"seg_id": seg_id}))
    assert body["seg_id"] == seg_id and body["county"] == roads.loc[seg_id, "county"]
    assert body["shape"]["type"] == "LineString" and len(body["shape"]["coordinates"]) >= 2
    assert sum(m["reports"] for m in body["potholes"]["by_month"]) == body["potholes"]["all_time"] == 2
    assert body["crash"]["used_in_rank"] is False


@pytest.mark.db
def test_A6_a_road_with_a_camera_lists_it(client, built):
    cams = built.tables["cameras"]
    seg_id = cams.set_index("camera_id").loc["DE_02", "seg_id"]
    body = strict(client.get("/api/road", params={"seg_id": seg_id}))
    assert [c["camera_id"] for c in body["cameras"]] == ["DE_02"] and body["cameras"][0]["readings"] > 0


@pytest.mark.db
@pytest.mark.parametrize("seg_id, status", [("ncdot:99999999999:0.000", 404), ("ncdot:1", 400), ("city:12345", 400), ("", 400),
                                            ("ncdot:1:0.000' OR '1'='1", 400), ("ncdot:../../etc:0.000", 400)])
def test_A6_unknown_is_not_found_and_malformed_is_rejected(seg_id, status, client):
    r = client.get("/api/road", params={"seg_id": seg_id})
    assert r.status_code == status and "error" in strict(r)


@pytest.mark.db
@pytest.mark.realdata
def test_A6_real_roads_by_id(real_client):
    first = strict(real_client.get("/api/road", params={"seg_id": "ncdot:20000013008:0.141"}))
    assert first["county"] == "Bertie"
    r = strict(real_client.get("/api/road", params={"seg_id": "ncdot:40002748092:0.940"}))
    assert (r["county"], r["rating"], r["from"], r["to"], r["bucket"]) == ("Wake", 73.4, "SR-2755", "SR-1006", "later")
    assert round(r["wear_rate"]["value"], 2) == 1.62 and r["wear_rate"]["heldout"] is True
    assert r["flood_risk"] == {"value": None, "scored": False, "heldout": False, "note": "not scored: outside the Helene zone"}
    assert r["traffic"] == {"vehicles_per_day": 1600.0, "source": "count"}


@pytest.mark.db
def test_A7_every_route_returns_strict_json(client, built):
    for path in ROUTES:
        r = client.get(path, params=params_for(path, built))
        assert r.status_code == 200, path
        if path.endswith(".csv"):
            assert r.headers["content-type"].startswith("text/csv")
        else:
            assert isinstance(strict(r), dict), path
            assert "NaN" not in r.text and "Infinity" not in r.text


@pytest.mark.db
def test_A7_blanks_are_null(client, built):
    roads = built.tables["roads"]
    blank = roads[roads.pred_years_to_poor.isna()].seg_id.iloc[1]
    body = strict(client.get("/api/road", params={"seg_id": blank}))
    assert body["years_to_poor"] is None and body["bucket"] == "unknown"
    no_cost = roads[roads.treatment_cost.isna()].seg_id.iloc[0]
    assert strict(client.get("/api/road", params={"seg_id": no_cost}))["treatment_cost"] is None
    assert strict(client.get("/api/road", params={"seg_id": roads.seg_id.iloc[0]}))["rating"] is None      # the missing rating


@pytest.mark.db
def test_A8_every_prediction_carries_its_flag_and_flood_says_when_it_is_not_scored(client, built):
    roads = built.tables["roads"].set_index("seg_id")
    page = strict(client.get("/api/worklist", params={"limit": 500}))["roads"]
    assert len(page) == len(roads)
    for r in page:
        src = roads.loc[r["seg_id"]]
        assert r["wear_rate"]["heldout"] == bool(src.rate_heldout) and r["crack_risk"]["heldout"] == bool(src.crack_heldout)
        assert r["flood_risk"]["scored"] == bool(src.in_helene_zone) and r["flood_risk"]["heldout"] == bool(src.flood_heldout)
        if src.in_helene_zone:
            assert r["flood_risk"]["value"] is not None and r["flood_risk"]["note"] is None
        else:
            assert r["flood_risk"]["value"] is None and "not scored" in r["flood_risk"]["note"]
    assert {r["flood_risk"]["scored"] for r in page} == {True, False}


@pytest.mark.db
def test_no_city_street_is_ever_returned(client):
    page = strict(client.get("/api/worklist", params={"limit": 500}))["roads"]
    assert all(r["seg_id"].startswith("ncdot:") for r in page)


# ------------------------------------------------------------------------------------------------ A9, A10, A11: alerts

def recompute_alerts(built, as_of):
    """Which cameras and stations should be listed for `as_of`, straight from the built tables."""
    as_of = pd.Timestamp(as_of)
    start = as_of.floor("h") - pd.Timedelta(hours=1)
    r = built.tables["camera_readings"]
    r = r[(r.time >= start) & (r.time <= as_of)]
    cams = r.groupby("camera_id").p_flooded.max()
    s = built.tables["sensor_levels"]
    s = s[(s.time >= start) & (s.time <= as_of)]
    stations = s.groupby("station").depth_on_road_cm.max()
    return (cams[cams >= queries.FLAG_P].round(9).to_dict(), stations[stations >= queries.FLOODED_CM].round(9).to_dict(),
            r, s)


@pytest.mark.db
def test_A9_alerts_say_when_they_are_for_and_what_a_flag_means(client):
    body = strict(client.get("/api/alerts", params={"as_of": "2026-09-27T15:30:00Z"}))
    assert body["as_of"] == "2026-09-27T15:30:00Z" and body["window_start"] == "2026-09-27T14:00:00Z"
    assert body["live"] is False and body["as_of_was_given"] is True       # the clock says the next day
    assert "not a confirmed flood" in body["caveat"] and body["flag_at"] == 0.5 and body["flooded_cm"] == 2.0
    for alert in body["camera_alerts"]:
        assert alert["worst"]["time"] and alert["latest"]["time"] and alert["worst"]["p_flooded"] >= 0.5


@pytest.mark.db
def test_A9_with_no_time_given_it_is_the_latest_reading_and_live_follows_the_clock(db_url, loaded_schema, built):
    latest = max(built.tables["camera_readings"].time.max(), built.tables["sensor_levels"].time.max())
    clock = {"now": latest.to_pydatetime() + timedelta(minutes=20)}
    with make_client(db_url, loaded_schema, clock=lambda: clock["now"]) as c:
        body = strict(c.get("/api/alerts"))
        assert pd.Timestamp(body["as_of"]) == latest and body["as_of_was_given"] is False and body["live"] is True
        clock["now"] = latest.to_pydatetime() + timedelta(hours=1, minutes=1)
        assert strict(c.get("/api/alerts"))["live"] is False               # an hour-old reading is not "now"
        clock["now"] = latest.to_pydatetime() - timedelta(minutes=5)
        assert strict(c.get("/api/alerts"))["live"] is False               # nor is a reading from the future


@pytest.mark.db
def test_A9_an_early_flag_and_a_later_dry_reading_each_keep_their_own_time(client):
    body = strict(client.get("/api/alerts", params={"as_of": "2026-09-25T14:50:00Z"}))
    bf = next(a for a in body["camera_alerts"] if a["camera_id"] == "BF_01")
    assert bf["worst"] == {"time": "2026-09-25T14:00:00Z", "p_flooded": 0.95, "depth_pred_cm": 9.5, "depth_measured_cm": 12.0}
    assert bf["latest"]["time"] == "2026-09-25T14:40:00Z" and bf["latest"]["p_flooded"] == 0.05      # dry now, and it says so


@pytest.mark.db
def test_A9_the_window_is_two_hours_unless_one_is_asked_for(client):
    two = strict(client.get("/api/alerts", params={"as_of": "2026-09-25T15:10:00Z"}))
    one = strict(client.get("/api/alerts", params={"as_of": "2026-09-25T15:10:00Z", "hours": 1}))
    assert (two["window_start"], two["window_hours"]) == ("2026-09-25T14:00:00Z", 2)
    assert (one["window_start"], one["window_hours"]) == ("2026-09-25T15:00:00Z", 1)
    assert [a["camera_id"] for a in two["camera_alerts"]] == ["BF_01"] and one["camera_alerts"] == []    # its flag was at 14:00
    for bad in (0, 3, 24):
        assert client.get("/api/alerts", params={"hours": bad}).status_code == 400


@pytest.mark.db
def test_A9_a_flag_that_comes_after_the_asked_time_is_not_listed(client):
    before = strict(client.get("/api/alerts", params={"as_of": "2026-09-26T12:59:00Z"}))
    after = strict(client.get("/api/alerts", params={"as_of": "2026-09-26T13:00:00Z"}))
    assert "BF_01" not in [a["camera_id"] for a in before["camera_alerts"]]      # its first flag is at 13:00
    assert "BF_01" in [a["camera_id"] for a in after["camera_alerts"]]


@pytest.mark.db
@pytest.mark.parametrize("as_of", ["2026-09-27T15:30:00Z", "2026-09-26T14:10:00Z", "2026-09-24T13:20:00Z", "2026-10-03T18:40:00Z"])
def test_A10_alerts_equal_a_recompute_from_the_files(as_of, client, built):
    cams, stations, _, _ = recompute_alerts(built, as_of)
    body = strict(client.get("/api/alerts", params={"as_of": as_of}))
    assert {a["camera_id"]: round(a["worst"]["p_flooded"], 9) for a in body["camera_alerts"]} == cams
    assert {a["station"]: round(a["worst"]["depth_on_road_cm"], 9) for a in body["sensor_alerts"]} == stations


@pytest.mark.db
def test_A10_the_storm_hour_has_both_kinds_of_alert(client):
    body = strict(client.get("/api/alerts", params={"as_of": "2026-09-27T15:30:00Z"}))
    assert sorted(a["camera_id"] for a in body["camera_alerts"]) == ["BF_01", "CB_01"]
    assert sorted(a["station"] for a in body["sensor_alerts"]) == ["BF_01", "CB_01"]
    assert all(a["road"] is None and a["name"] and a["lat"] for a in body["camera_alerts"])     # no state road: named and placed
    assert round(next(a for a in body["sensor_alerts"] if a["station"] == "BF_01")["worst"]["depth_on_road_cm"], 6) == 14.0


@pytest.mark.db
@pytest.mark.realdata
def test_A10_real_storm_hour_equals_a_recompute(real_client, real_root):
    real = build.build_all(real_root)
    cams, stations, _, _ = recompute_alerts(real, "2026-09-27T15:30:00Z")
    body = strict(real_client.get("/api/alerts", params={"as_of": "2026-09-27T15:30:00Z"}))
    assert sorted(a["camera_id"] for a in body["camera_alerts"]) == sorted(cams) and len(cams) >= 3
    assert sorted(a["station"] for a in body["sensor_alerts"]) == sorted(stations) and len(stations) >= 3
    assert not any(a["known_dry"] for a in body["camera_alerts"])


@pytest.mark.db
def test_A11_known_dry_flags_are_labelled_and_listed_last(client):
    body = strict(client.get("/api/alerts", params={"as_of": "2026-10-03T18:40:00Z"}))
    dry = [a for a in body["camera_alerts"] if a["known_dry"]]
    assert sorted(a["camera_id"] for a in dry) == ["NCDOT_5004", "NCDOT_5009"]
    assert all("known false alarm" in a["note"] and a["role"] == "extra" for a in dry)
    assert all(a["road"] and a["road"]["seg_id"].startswith("ncdot:") and a["road"]["bucket"] for a in dry)   # joined to the road table


@pytest.mark.db
def test_A11_the_peak_hours_leave_known_dry_flags_out_of_the_ranking(client):
    hours = strict(client.get("/api/alerts/peaks", params={"limit": 50}))["hours"]
    top = hours[0]
    assert top["hour"].startswith("2026-09-27T") and top["camera_flags"] == 2 and top["sensor_alerts"] == 2
    dry_hour = next(h for h in hours if h["hour"] == "2026-10-03T18:00:00Z")
    assert dry_hour["camera_flags"] == 0 and dry_hour["known_dry_flags"] == 2
    assert hours.index(dry_hour) > 0                                        # two false alarms do not make a peak
    for hour in hours:                                                     # asking for exactly that hour gives exactly that count
        one = strict(client.get("/api/alerts", params={"as_of": hour["as_of"], "hours": 1}))
        assert one["window_start"] == hour["hour"] and one["window_hours"] == 1
        assert len(one["sensor_alerts"]) == hour["sensor_alerts"]
        assert len([a for a in one["camera_alerts"] if not a["known_dry"]]) == hour["camera_flags"]
        assert len([a for a in one["camera_alerts"] if a["known_dry"]]) == hour["known_dry_flags"]


@pytest.mark.db
@pytest.mark.realdata
def test_A11_real_default_alerts_are_all_labelled_known_dry(real_client):
    body = strict(real_client.get("/api/alerts"))                           # the latest readings are the dry NCDOT stills
    assert body["camera_alerts"] and all(a["known_dry"] and a["note"] for a in body["camera_alerts"])
    top = strict(real_client.get("/api/alerts/peaks", params={"limit": 1}))["hours"][0]
    assert top["hour"].startswith("2026-09-2") and top["camera_flags"] + top["sensor_alerts"] >= 6


@pytest.mark.db
def test_camera_history_is_hourly_worst_values(client, built):
    body = strict(client.get("/api/camera_history", params={"camera_id": "BF_01", "start": "2026-09-26T00:00:00Z",
                                                            "end": "2026-09-26T23:00:00Z"}))
    assert [h["hour"] for h in body["hours"]] == [f"2026-09-26T{h}:00:00Z" for h in (13, 14, 15, 16)]
    assert all(h["worst_p_flooded"] == 0.9 for h in body["hours"]) and body["hours"][0]["readings"] == 3
    assert client.get("/api/camera_history", params={"camera_id": "NOPE"}).status_code == 404
    assert client.get("/api/camera_history").status_code == 400
    assert client.get("/api/camera_history", params={"camera_id": "BF_01", "start": "2026-09-26"}).status_code == 400


# ------------------------------------------------------------------------------------------------ A14, A15, A16

@pytest.mark.db
def test_A14_the_services_own_connection_cannot_write(client):
    pool = client.app.state.pool
    with pool.connection() as conn:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("INSERT INTO sensor_levels (time, station, level_m) VALUES (now(), 'X', 1.0)")
    with pool.connection() as conn:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("TRUNCATE roads, road_shapes")
    with pool.connection() as conn:
        assert conn.execute("SHOW transaction_isolation").fetchone()[0] == "repeatable read"
        assert conn.execute("SHOW TIME ZONE").fetchone()[0] == "UTC"


@pytest.mark.db
def test_A15_stats_are_what_the_database_reports(client, db_url, loaded_schema, built):
    body = strict(client.get("/api/stats"))
    conn = config.connect(db_url, autocommit=True, schema=loaded_schema)
    try:
        for table, got in body["time_partitioned_tables"].items():
            row = conn.execute(f"SELECT total_chunks, number_compressed_chunks, before_compression_total_bytes, "
                               f"after_compression_total_bytes FROM hypertable_columnstore_stats('{table}')").fetchone()
            assert (got["chunks"], got["compressed_chunks"], got["bytes_before"], got["bytes_after"]) == tuple(row)
            assert got["rows"] == built.counts[table] and got["compression_ratio"] == round(row[2] / row[3], 2)
    finally:
        conn.close()
    assert set(body["running_summaries"]) == set(schema.SUMMARIES)
    assert all(s["includes_rows_newer_than_last_refresh"] and s["rows"] > 0 for s in body["running_summaries"].values())
    assert len(body["background_jobs"]) == 6 and body["load"]["status"] == "complete" and body["replay_rows"] == 0
    assert body["plain_tables"]["roads"] == len(built.tables["roads"]) and body["database_size_bytes"] > 0


@pytest.mark.db
def test_A15_stats_show_blanks_when_nothing_is_compressed(db_url, empty_schema, fixture_root, dash):
    dash.load_fixture(db_url, fixture_root, empty_schema, compress=False)
    with make_client(db_url, empty_schema) as c:
        tables_ = strict(c.get("/api/stats"))["time_partitioned_tables"]
    assert all(t["compressed_chunks"] == 0 and t["compression_ratio"] is None and t["bytes_before"] is None for t in tables_.values())


@pytest.mark.db
@pytest.mark.parametrize("point", ["copy", "refresh_one", "refresh"])
def test_A16_while_a_load_is_not_complete_the_data_routes_say_loading(point, db_url, empty_schema, fixture_root, dash, built):
    dash.load_fixture(db_url, fixture_root, empty_schema, stop_after=point)
    with make_client(db_url, empty_schema) as c:
        for path in ("/api/worklist", "/api/road", "/api/alerts", "/api/alerts/peaks", "/api/camera_history", "/api/export/risk.csv"):
            r = c.get(path, params=params_for(path, built))
            assert r.status_code == 503 and strict(r) == {"error": "loading", "load_status": "loaded",
                                                          "detail": "a load is in progress or has not finished; try again shortly"}, path
        assert strict(c.get("/api/summary"))["load"]["status"] == "loaded"
        assert strict(c.get("/api/health"))["load_status"] == "loaded"
        assert strict(c.get("/api/stats"))["load"]["status"] == "loaded"


@pytest.mark.db
def test_A16_while_a_load_holds_the_tables_the_reply_is_loading_not_an_error(db_url, fresh_schema):
    holder = config.connect(db_url, schema=fresh_schema)                   # what a load's copy step does: lock, then work
    try:
        holder.execute("LOCK TABLE roads IN ACCESS EXCLUSIVE MODE")
        with make_client(db_url, fresh_schema, lock_timeout_ms=300) as c:
            started = time.time()
            r = c.get("/api/worklist")
            assert r.status_code == 503 and strict(r)["error"] == "loading" and time.time() - started < 3
            assert strict(c.get("/api/health"))["ok"] is True              # the load record itself is not locked
    finally:
        holder.rollback()
        holder.close()
    with make_client(db_url, fresh_schema) as c:
        assert c.get("/api/worklist").status_code == 200                   # and it answers again once the lock is gone


@pytest.mark.db
def test_A16_a_database_with_nothing_loaded_says_so(db_url, empty_schema):
    conn = config.connect(db_url, autocommit=True)
    try:
        schema.setup(conn, empty_schema, schedule_jobs=False)
    finally:
        conn.close()
    with make_client(db_url, empty_schema) as c:
        r = c.get("/api/worklist")
        assert r.status_code == 503 and strict(r)["load_status"] == "empty"
        assert strict(c.get("/api/health"))["load_status"] == "empty"


# ------------------------------------------------------------------------------------------------ A17, E8: the download

def pool_idle(pool):
    stats = pool.get_stats()
    return stats.get("pool_available", 0) == stats.get("pool_size", -1)


@pytest.mark.db
def test_E8_the_download_is_the_file_byte_for_byte(client, built):
    want = io.BytesIO()
    export.write_risk_csv(export.rows_from_frame(built.tables["roads"]), want)
    r = client.get("/api/export/risk.csv")
    assert r.status_code == 200 and r.content == want.getvalue()
    assert r.headers["content-disposition"] == 'attachment; filename="risk_roads.csv"'
    assert strict(client.get("/api/export/dictionary"))["columns"][0]["name"] == "seg_id"


@pytest.mark.db
@pytest.mark.realdata
def test_E8_the_real_download_is_the_real_file(real_client, real_root, tmp_path):
    rows, size, sha = export.export(real_root, tmp_path)
    r = real_client.get("/api/export/risk.csv")
    assert rows == 112_443 and len(r.content) == size and r.content == (tmp_path / export.FILE_NAME).read_bytes()


@pytest.mark.db
def test_A17_no_connection_is_held_while_the_client_reads(client, monkeypatch):
    monkeypatch.setattr(service, "RISK_PAGE", 50)
    pool = client.app.state.pool
    pages = client.app.state.risk_pages()
    first = next(pages)
    assert first[0].startswith("ncdot:") and pool_idle(pool)               # between rows nothing is checked out
    for _ in range(120):
        next(pages)
    assert pool_idle(pool)
    pages.close()                                                          # the client goes away
    assert pool_idle(pool)


@pytest.mark.db
def test_A17_a_failure_part_way_stops_the_stream_and_holds_nothing(client, monkeypatch):
    monkeypatch.setattr(service, "RISK_PAGE", 50)
    real_page, calls = queries.risk_page, []

    def fail_on_the_third_page(conn, after, size):
        calls.append(after)
        if len(calls) == 3:
            raise psycopg.OperationalError("the connection dropped")
        return real_page(conn, after, size)
    monkeypatch.setattr(queries, "risk_page", fail_on_the_third_page)
    pages = client.app.state.risk_pages()
    got = []
    with pytest.raises(psycopg.OperationalError):
        for row in pages:
            got.append(row)
    assert len(got) == 100 and pool_idle(client.app.state.pool)


@pytest.mark.db
def test_A17_a_load_that_replaces_the_data_mid_download_stops_the_stream(db_url, fresh_schema, fixture_root, dash, monkeypatch):
    monkeypatch.setattr(service, "RISK_PAGE", 50)
    with make_client(db_url, fresh_schema) as c:
        pages = c.app.state.risk_pages()
        for _ in range(60):
            next(pages)
        dash.load_fixture(db_url, fixture_root, fresh_schema)             # a second, complete load
        with pytest.raises(service.Loading):
            for _ in pages:
                pass
        assert pool_idle(c.app.state.pool)


def test_A17_a_failure_before_the_first_byte_is_a_503(dead_client):
    r = dead_client.get("/api/export/risk.csv")
    assert r.status_code == 503 and strict(r)["error"] == "database unavailable"
    assert "content-disposition" not in r.headers
