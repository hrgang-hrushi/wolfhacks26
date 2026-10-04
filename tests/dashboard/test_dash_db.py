"""The database: setup, load, running summaries, compression, the check command. All need the local test database."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from web.service import app as service
from web.tiger import build, config, load, replay, schema, verify

pytestmark = pytest.mark.db
UTC = "UTC"


@pytest.fixture
def run(db_url):
    """run(schema)(query, params) -> rows, on a connection that is closed afterwards."""
    opened = []

    def for_schema(name, **kw):
        conn = config.connect(db_url, autocommit=True, schema=name, **kw)
        config.assert_local(conn)
        opened.append(conn)
        return lambda query, params=None: conn.execute(query, params).fetchall()
    yield for_schema
    for conn in opened:
        conn.close()


@pytest.fixture(scope="module")
def built(fixture_root, dash):
    with dash.sunnyday_out(fixture_root):
        return build.build_all(fixture_root)


def jobs(q, name):
    return q("SELECT job_id, proc_name, hypertable_name, config, scheduled FROM timescaledb_information.jobs "
             "WHERE hypertable_schema = %s ORDER BY proc_name, hypertable_name", [name])


def counts(q):
    return {t: q(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t)))[0][0] for t in schema.TABLES}


# ------------------------------------------------------------------------------------------------ D1, D2, D2b, D3b

def test_D1_the_time_stamped_tables_are_time_partitioned(loaded_schema, run):
    q = run(loaded_schema)
    hyper = dict(q("SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables WHERE hypertable_schema = %s",
                   [loaded_schema]))
    user_tables = {t for t in hyper if not t.startswith("_")}
    assert user_tables == set(schema.HYPERTABLES)                         # roads, cameras and shapes are plain tables
    assert all(hyper[t] >= 2 for t in schema.HYPERTABLES)                 # split into several chunks by time


def objects(q, name):
    tables = sorted(r[0] for r in q("SELECT table_name FROM information_schema.tables WHERE table_schema = %s", [name]))
    views = sorted(r[0] for r in q("SELECT view_name FROM timescaledb_information.continuous_aggregates WHERE view_schema = %s", [name]))
    policies = sorted((p, h, json.dumps(c, sort_keys=True)) for _, p, h, c, _ in jobs(q, name))
    return tables, views, policies


def test_D2_setup_twice_gives_no_error_and_the_same_objects(db_url, fresh_schema, run):
    q = run(fresh_schema)
    before, rows_before = objects(q, fresh_schema), counts(q)
    conn = config.connect(db_url, autocommit=True)
    try:
        schema.setup(conn, fresh_schema, schedule_jobs=False)
        schema.setup(conn, fresh_schema, schedule_jobs=False)
    finally:
        conn.close()
    assert objects(q, fresh_schema) == before and counts(q) == rows_before


def test_D2b_the_jobs_are_exactly_the_expected_policies(loaded_schema, run):
    q = run(loaded_schema)
    found = {(p, h): (c, s) for _, p, h, c, s in jobs(q, loaded_schema)}
    assert set(found) == {("policy_compression", t) for t in schema.HYPERTABLES} | \
                        {("policy_refresh_continuous_aggregate", v) for v in schema.SUMMARIES}
    assert found[("policy_compression", "pothole_reports")][0]["compress_after"] == "360 days"
    assert found[("policy_compression", "camera_readings")][0]["compress_after"] == "1 day"
    assert found[("policy_refresh_continuous_aggregate", "camera_hourly")][0]["end_offset"] == "01:00:00"
    assert found[("policy_refresh_continuous_aggregate", "pothole_monthly")][0]["end_offset"] == "1 mon"
    assert all(c["start_offset"] is None for (p, _), (c, _) in found.items() if p.startswith("policy_refresh"))
    assert not any(scheduled for _, scheduled in found.values())           # paused in a test schema


def test_D2b_adding_the_policies_starts_nothing(db_url, empty_schema, run):
    conn = config.connect(db_url, autocommit=True)
    try:
        schema.setup(conn, empty_schema, schedule_jobs=True)
    finally:
        conn.close()
    q = run(empty_schema)
    rows = q("SELECT j.proc_name, j.scheduled, j.next_start > now(), coalesce(s.total_runs, 0) FROM timescaledb_information.jobs j "
             "LEFT JOIN timescaledb_information.job_stats s USING (job_id) WHERE j.hypertable_schema = %s", [empty_schema])
    assert len(rows) == 6
    assert all(scheduled and in_future and runs == 0 for _, scheduled, in_future, runs in rows)


def test_D3b_the_summaries_include_rows_newer_than_their_last_refresh(loaded_schema, run):
    rows = dict(run(loaded_schema)("SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates "
                                   "WHERE view_schema = %s", [loaded_schema]))
    assert rows == {v: False for v in schema.SUMMARIES}


# ------------------------------------------------------------------------------------------------ D3, D4, D5

def test_D3_loading_twice_gives_identical_counts(db_url, fresh_schema, fixture_root, run, dash, built):
    q = run(fresh_schema)
    first = counts(q)
    summaries = [q(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(v)))[0][0] for v in schema.SUMMARIES]
    dash.load_fixture(db_url, fixture_root, fresh_schema)
    assert counts(q) == first == built.counts
    assert [q(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(v)))[0][0] for v in schema.SUMMARIES] == summaries
    assert q("SELECT status FROM load_manifest ORDER BY id") == [("complete",), ("complete",)]


@pytest.mark.parametrize("point", ["copy", "refresh_one", "refresh"])
def test_D4_a_load_stopped_after_the_copy_is_not_marked_complete(point, db_url, empty_schema, fixture_root, run, dash, built):
    s = dash.load_fixture(db_url, fixture_root, empty_schema, stop_after=point)
    q = run(empty_schema)
    assert s["status"] == "loaded" and q("SELECT status FROM load_manifest ORDER BY id DESC LIMIT 1") == [("loaded",)]
    assert counts(q) == built.counts                                       # the rows are in; only the summaries lag
    with dash.sunnyday_out(fixture_root):
        results = {c.name: c for c in verify.run(db_url, empty_schema, fixture_root)}
    assert not results["load record"].ok


def test_D4_a_load_that_fails_inside_the_transaction_keeps_the_previous_data(db_url, fresh_schema, fixture_root, run, dash,
                                                                              monkeypatch, built):
    q = run(fresh_schema)
    real_copy = load.copy_table

    def fail_on_the_fourth_table(cur, table, frame):
        real_copy(cur, table, frame.head(5) if table == "camera_readings" else frame)
        if table == "camera_readings":
            raise RuntimeError("the connection dropped mid-copy")
    monkeypatch.setattr(load, "copy_table", fail_on_the_fourth_table)
    with pytest.raises(RuntimeError, match="mid-copy"):
        dash.load_fixture(db_url, fixture_root, fresh_schema)
    assert counts(q) == built.counts                                       # the truncate and the partial copy were undone
    assert q("SELECT id, status FROM load_manifest ORDER BY id") == [(1, "complete")]


def test_D4_a_first_load_that_fails_leaves_nothing(db_url, empty_schema, fixture_root, run, dash):
    def boom():
        raise RuntimeError("stopped before the commit")
    with dash.sunnyday_out(fixture_root), pytest.raises(RuntimeError, match="before the commit"):
        load.load(db_url, fixture_root, schema=empty_schema, schedule_jobs=False, _before_commit=boom)
    q = run(empty_schema)
    assert set(counts(q).values()) == {0} and q("SELECT count(*) FROM load_manifest") == [(0,)]


def test_D4_an_unknown_stop_point_is_refused(db_url, fixture_root):
    with pytest.raises(ValueError, match="stop_after"):
        load.load(db_url, fixture_root, schema="test_never_created", stop_after="halfway")


def test_D5_database_counts_equal_the_built_tables(loaded_schema, run, built):
    assert counts(run(loaded_schema)) == built.counts
    manifest = run(loaded_schema)("SELECT row_counts, sources FROM load_manifest ORDER BY id DESC LIMIT 1")[0]
    assert manifest[0] == built.counts and manifest[1] == built.fingerprints


@pytest.mark.realdata
def test_D5_real_counts_in_the_database(real_schema, run):
    assert counts(run(real_schema)) == {"roads": 112_443, "road_shapes": 112_443, "cameras": 1_004, "camera_readings": 3_093,
                                        "sensor_levels": 12_557, "pothole_reports": 17_790}


# ------------------------------------------------------------------------------------------------ D6, D7

def test_D6_every_road_reads_back_equal(loaded_schema, db_url, fixture_root, dash):
    with dash.sunnyday_out(fixture_root):
        results = {c.name: c for c in verify.run(db_url, loaded_schema, fixture_root)}
    assert results["road values"].ok and "200 roads" in results["road values"].detail


def test_D6_awkward_text_survives_the_copy(loaded_schema, run, built):
    want = built.tables["roads"].from_desc.iloc[11]
    assert "\t" in want and '"' in want and "\\" in want and "," in want
    assert run(loaded_schema)("SELECT from_desc FROM roads WHERE seg_id = %s", [built.tables["roads"].seg_id.iloc[11]]) == [(want,)]


@pytest.mark.realdata
def test_D6_the_readme_example_road_reads_back(real_schema, db_url, real_root, run):
    row = run(real_schema)("SELECT county, rating, survey_year, last_rehab_year, round(pred_rate::numeric, 2), "
                           "round(pred_years_to_poor::numeric, 1), repair_bucket, rate_heldout, pred_flood, aadt_best "
                           "FROM roads WHERE seg_id = %s", [verify.EXAMPLE_ROAD])[0]
    assert row[:3] == ("Wake", 73.4, 2025) and row[3] == 2010
    assert (float(row[4]), float(row[5]), row[6], row[7], row[8], row[9]) == (1.62, 8.3, "later", True, None, 1600.0)
    results = {c.name: c for c in verify.run(db_url, real_schema, real_root)}
    assert all(c.ok for c in results.values()), [c for c in results.values() if not c.ok]
    assert results["road values"].detail.split()[0] in ("200", "201")      # 200 at random, plus the example unless drawn


def test_D7_blanks_are_null_in_the_database(loaded_schema, run, built):
    q, roads = run(loaded_schema), built.tables["roads"]
    for column in ("pred_years_to_poor", "treatment_cost", "pred_flood", "rating", "lanes", "pothole_city"):
        got = q(sql.SQL("SELECT count(*) FROM roads WHERE {} IS NULL").format(sql.Identifier(column)))[0][0]
        assert got == int(roads[column].isna().sum()) > 0, column
    assert q("SELECT count(*) FROM roads WHERE pred_years_to_poor = 0 AND repair_bucket = 'unknown'") == [(0,)]
    assert q("SELECT count(*) FROM cameras WHERE seg_id IS NULL") == [(int(built.tables["cameras"].seg_id.isna().sum()),)]
    assert q("SELECT count(*) FROM cameras WHERE lower(seg_id) = 'nan'") == [(0,)]
    assert q("SELECT count(*) FROM pothole_reports WHERE seg_id IS NULL") == [(9,)]


@pytest.mark.realdata
def test_D7_real_blank_counts_in_the_database(real_schema, run):
    q = run(real_schema)
    assert q("SELECT count(*) FILTER (WHERE pred_years_to_poor IS NULL), count(*) FILTER (WHERE treatment_cost IS NULL), "
             "count(*) FILTER (WHERE pred_flood IS NULL) FROM roads") == [(1_643, 63_021, 79_885)]
    assert dict(q("SELECT repair_bucket, count(*) FROM roads GROUP BY 1")) == {
        "fix_now": 4_432, "within_1y": 794, "within_5y": 4_699, "later": 100_875, "unknown": 1_643}
    assert q("SELECT count(*) FILTER (WHERE rate_heldout), count(*) FILTER (WHERE crack_heldout), "
             "count(*) FILTER (WHERE flood_heldout) FROM roads") == [(77_422, 68_349, 32_558)]


@pytest.mark.parametrize("statement", [
    "INSERT INTO sensor_levels (time, station, level_m) VALUES (now(), 'X', 'NaN')",
    "INSERT INTO sensor_levels (time, station, level_m) VALUES (now(), 'X', 'Infinity')",
    "INSERT INTO sensor_levels (time, station, level_m, depth_on_road_cm) VALUES (now(), 'X', 1, 'NaN')",   # a bare >= 0 would let this in
    "INSERT INTO camera_readings (time, camera_id, site, file, p_flooded) VALUES (now(), 'X', 'X', 'f', 1.5)",
    "INSERT INTO cameras (camera_id, site, station, role, known_dry, seg_id) VALUES ('X', 'X', 'X', 'cv', false, 'city:1')",
    "INSERT INTO cameras (camera_id, site, station, role, known_dry, seg_id) VALUES ('X', 'X', 'X', 'cv', false, 'NaN')",
    "INSERT INTO roads (seg_id, flood_scored, in_helene_zone, rate_heldout, crack_heldout, flood_heldout, helene_damaged, "
    "repair_bucket, priority_rank) VALUES ('city:1', false, false, false, false, false, false, 'later', 1)",
    "UPDATE roads SET pred_flood = 0.5 WHERE NOT flood_scored",            # a flood score outside the zone
])
def test_D7_the_tables_refuse_what_the_loader_should_never_send(statement, fresh_schema, run):
    with pytest.raises(psycopg.errors.CheckViolation):
        run(fresh_schema)(statement)


# ------------------------------------------------------------------------------------------------ D8

def test_D8_changing_a_source_file_after_a_load_makes_the_check_fail_and_name_it(db_url, empty_schema, fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    dash.load_fixture(db_url, root, empty_schema)
    with dash.sunnyday_out(root):
        assert all(c.ok for c in verify.run(db_url, empty_schema, root))
    dash.rewrite(root, "data/raw/pothole_reports.parquet", lambda d: d.iloc[:-1])      # one report fewer
    with dash.sunnyday_out(root):
        results = {c.name: c for c in verify.run(db_url, empty_schema, root)}
    changed = results["files unchanged since the load"]
    assert not changed.ok and "data/raw/pothole_reports.parquet" in changed.detail
    assert not results["comparison with the files"].ok and "row counts" not in results    # it stops there, cleanly


# ------------------------------------------------------------------------------------------------ D9

def test_D9_time_ranges_equal_the_files(loaded_schema, run, built):
    q = run(loaded_schema)
    for table in schema.HYPERTABLES:
        lo, hi = q(sql.SQL("SELECT min(time), max(time) FROM {}").format(sql.Identifier(table)))[0]
        assert pd.Timestamp(lo) == built.tables[table].time.min() and pd.Timestamp(hi) == built.tables[table].time.max()


def test_D9_a_session_in_another_time_zone_reads_the_same_instant(db_url, loaded_schema):
    conn = config.connect(db_url, autocommit=True, schema=loaded_schema)
    try:
        conn.execute("SET TIME ZONE 'America/New_York'")
        first = conn.execute("SELECT min(time) AT TIME ZONE 'UTC' FROM camera_readings WHERE camera_id = 'BF_01'").fetchone()[0]
    finally:
        conn.close()
    assert (first.day, first.hour, first.minute) == (24, 13, 0)             # 13:00 UTC in the file, 13:00 UTC here


def test_D9_every_connection_this_code_opens_is_in_utc(db_url):
    conn = config.connect(db_url, autocommit=True)
    try:
        assert conn.execute("SHOW TIME ZONE").fetchone()[0] == "UTC"
    finally:
        conn.close()


# ------------------------------------------------------------------------------------------------ D10, D11, D12

def test_D10_D11_every_summary_equals_a_recompute(db_url, loaded_schema, built):
    conn = config.connect(db_url, autocommit=True, schema=loaded_schema)
    try:
        results = {c.name: c for c in verify.summary_checks(conn, built)}
        first_day = conn.execute("SELECT count(*) FROM camera_hourly WHERE bucket < '2026-09-25 00:00+00'").fetchone()[0]
        oldest = conn.execute("SELECT min(bucket), sum(reports) FROM pothole_monthly").fetchone()
        no_road = conn.execute("SELECT sum(reports) FROM pothole_monthly WHERE seg_id IS NULL").fetchone()[0]
    finally:
        conn.close()
    assert all(c.ok for c in results.values()), results
    assert first_day > 0                                                   # the first day is summarised, not only recent data
    assert oldest[0].year == 2016 and int(oldest[1]) == len(built.tables["pothole_reports"]) == 40
    assert int(no_road) == 9                                               # reports without a road are counted too


def test_D10_the_comparison_can_fail(db_url, loaded_schema, built):
    from types import SimpleNamespace
    wrong = dict(built.tables)
    wrong["camera_readings"] = built.tables["camera_readings"].assign(p_flooded=lambda d: d.p_flooded * 0.5)
    conn = config.connect(db_url, autocommit=True, schema=loaded_schema)
    try:
        results = {c.name: c for c in verify.summary_checks(conn, SimpleNamespace(tables=wrong))}
    finally:
        conn.close()
    assert not results["summary camera_hourly"].ok and results["summary sensor_hourly"].ok


@pytest.mark.realdata
def test_D10_D11_real_summaries(real_schema, run):
    q = run(real_schema)
    assert q("SELECT count(*) FROM camera_hourly")[0][0] == 1_825
    assert q("SELECT count(*) FROM sensor_hourly")[0][0] == 1_200
    assert [int(v) for v in q("SELECT count(*), sum(reports) FROM pothole_monthly")[0]] == [2_796, 17_790]


def test_D12_a_new_reading_shows_in_the_summary_without_a_refresh(fresh_schema, run):
    q = run(fresh_schema)
    latest = q("SELECT max(time) FROM camera_readings")[0][0]
    new = latest + pd.Timedelta(hours=1)
    bucket = pd.Timestamp(new).floor("h").to_pydatetime()
    assert q("SELECT count(*) FROM camera_hourly WHERE bucket = %s AND camera_id = 'BF_01'", [bucket]) == [(0,)]
    q("INSERT INTO camera_readings (time, camera_id, site, p_flooded, depth_pred_cm, file) VALUES (%s, 'BF_01', 'BF_01', 0.97, 9.7, 'new') "
      "RETURNING 1", [new])
    assert q("SELECT worst_p_flooded, readings, is_replay FROM camera_hourly WHERE bucket = %s AND camera_id = 'BF_01'",
             [bucket]) == [(0.97, 1, False)]


# ------------------------------------------------------------------------------------------------ D13, D14, D15

QUERIES = ["SELECT camera_id, count(*), max(p_flooded), min(time) FROM camera_readings GROUP BY 1 ORDER BY 1",
           "SELECT station, count(*), round(avg(level_m)::numeric, 6), max(depth_on_road_cm) FROM sensor_levels GROUP BY 1 ORDER BY 1",
           "SELECT source, date_trunc('year', time), count(*) FROM pothole_reports GROUP BY 1, 2 ORDER BY 1, 2"]


def test_D13_compression_is_real_and_changes_no_answer(db_url, empty_schema, fixture_root, run, dash):
    s = dash.load_fixture(db_url, fixture_root, empty_schema, compress=False)
    q = run(empty_schema)
    assert all(c["compressed_chunks"] == 0 and c["ratio"] is None and c["bytes_before"] is None for c in s["compression"].values())
    before = [q(text) for text in QUERIES]
    conn = config.connect(db_url, autocommit=True, schema=empty_schema)
    try:
        load.compress_chunks(conn)
        stats = load.compression_stats(conn)
    finally:
        conn.close()
    assert [q(text) for text in QUERIES] == before
    for table, c in stats.items():
        assert 1 <= c["compressed_chunks"] < c["chunks"], table            # old chunks compressed, the newest left open
        assert c["bytes_before"] > 0 and c["bytes_after"] > 0
        assert c["ratio"] == round(c["bytes_before"] / c["bytes_after"], 2)
    in_db = q("SELECT number_compressed_chunks, before_compression_total_bytes FROM hypertable_columnstore_stats('sensor_levels')")[0]
    assert (in_db[0], in_db[1]) == (stats["sensor_levels"]["compressed_chunks"], stats["sensor_levels"]["bytes_before"])


def test_D13_the_load_record_keeps_the_measured_sizes(loaded_schema, run):
    comp, status = run(loaded_schema)("SELECT compression, status FROM load_manifest ORDER BY id DESC LIMIT 1")[0]
    assert status == "complete" and set(comp) == set(schema.HYPERTABLES)
    assert all(c["compressed_chunks"] >= 1 and c["ratio"] is not None for c in comp.values())


def test_D14_a_refused_feature_stops_setup_with_a_plain_message(db_url, empty_schema):
    conn = config.connect(db_url, autocommit=True)
    try:
        with pytest.raises(schema.SetupRefused, match="the database refused the PostGIS extension"):
            schema.setup(conn, empty_schema, extra_statements=[("the PostGIS extension", "CREATE EXTENSION postgis")])
    finally:
        conn.close()


def test_D14_setup_needs_a_connection_that_commits_each_statement(db_url, empty_schema):
    conn = config.connect(db_url)
    try:
        with pytest.raises(schema.SetupRefused, match="autocommit"):
            schema.setup(conn, empty_schema)
    finally:
        conn.close()


@pytest.mark.parametrize("version, message", [("2.19.3", "too old"), (None, "no TimescaleDB")])
def test_D14_an_old_or_missing_extension_is_refused(version, message, db_url, empty_schema, monkeypatch):
    real = config.probe
    monkeypatch.setattr(config, "probe", lambda conn: {**real(conn), "timescaledb_version": version})
    conn = config.connect(db_url, autocommit=True)
    try:
        with pytest.raises(schema.SetupRefused, match=message):
            schema.setup(conn, empty_schema)
    finally:
        conn.close()


def test_D14_storage_used_is_reported(db_url, empty_schema, fixture_root, dash):
    s = dash.load_fixture(db_url, fixture_root, empty_schema)
    assert s["database_size_bytes"] > 1_000_000 and s["timescaledb_version"]
    conn = config.connect(db_url, autocommit=True)
    try:
        info = config.probe(conn)
    finally:
        conn.close()
    assert info["database_size_bytes"] > 0 and info["max_connections"] > 0 and info["timescaledb_schema"] == "public"


def test_D15_the_database_orders_ids_as_python_does(loaded_schema, run, built):
    ids = [r[0] for r in run(loaded_schema)("SELECT seg_id FROM roads ORDER BY seg_id")]
    assert ids == sorted(built.tables["roads"].seg_id.tolist())


@pytest.mark.realdata
def test_D15_real_ids_sort_the_same_in_both(real_schema, run):
    ids = [r[0] for r in run(real_schema)("SELECT seg_id FROM roads ORDER BY seg_id")]
    assert len(ids) == 112_443 and ids == sorted(ids)
    collation = run(real_schema)("SELECT collation_name FROM information_schema.columns WHERE table_schema = %s "
                                 "AND table_name = 'roads' AND column_name = 'seg_id'", [real_schema])
    assert collation == [("C",)]


def test_the_search_path_includes_the_extension_schema(db_url, loaded_schema):
    conn = config.connect(db_url, autocommit=True, schema=loaded_schema)
    try:
        path = conn.execute("SHOW search_path").fetchone()[0]
        assert path.replace('"', "") == f"{loaded_schema}, public"
        conn.execute("SELECT time_bucket(INTERVAL '1 hour', now())")       # not found when the path lacks the extension's schema
    finally:
        conn.close()
    bare = config.connect(db_url, autocommit=True)
    try:
        bare.execute(sql.SQL("SET search_path = {}").format(sql.Identifier(loaded_schema)))
        with pytest.raises(psycopg.errors.UndefinedFunction):
            bare.execute("SELECT time_bucket(INTERVAL '1 hour', now())")
    finally:
        bare.close()


# ------------------------------------------------------------------------------------------------ S4

def test_S4_a_load_changes_no_source_file(db_url, empty_schema, fixture_root, dash):
    before = build.fingerprints(fixture_root)
    listing = sorted(str(p.relative_to(fixture_root)) for p in fixture_root.rglob("*") if p.is_file())
    dash.load_fixture(db_url, fixture_root, empty_schema)
    assert build.fingerprints(fixture_root) == before
    assert sorted(str(p.relative_to(fixture_root)) for p in fixture_root.rglob("*") if p.is_file()) == listing   # and adds none


def test_S4_the_loader_has_no_code_that_writes_a_data_file():
    import inspect
    sources = {m: Path(f"web/tiger/{m}.py").read_text() for m in ("build", "verify", "replay")}
    # load.py also holds dump(), which writes the console files into a folder the caller names; everything else in it is checked
    sources.update({f"load.{f.__name__}": inspect.getsource(f) for f in (load.load, load.copy_table, load.refresh,
                                                                         load.compress_chunks, load.compression_stats)})
    for name, src in sources.items():                  # (copy.write_row sends a row to the database; it writes no file)
        assert not any(call in src for call in (".to_parquet(", ".to_csv(", "open(", ".write_text(", ".write_bytes(")), name


# ------------------------------------------------------------------------------------------------ the console fallback

def test_the_files_for_tigers_browser_console_load_the_same_data(db_url, empty_schema, fixture_root, tmp_path, dash, monkeypatch, built):
    """When the database port is blocked: CSV files and two SQL scripts, run by hand in the console over 443."""
    monkeypatch.delenv(config.SCHEMA_KEY, raising=False)
    with dash.sunnyday_out(fixture_root):
        assert load.dump(fixture_root, tmp_path, schema=empty_schema) == built.counts
    assert f"SET search_path = {empty_schema}, public;" in (tmp_path / "setup.sql").read_text()   # the schema asked for
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([f"{t}.csv" for t in schema.TABLES] + ["setup.sql", "after_load.sql"])
    conn = config.connect(db_url, autocommit=True)
    try:
        config.assert_local(conn)
        for line in (tmp_path / "setup.sql").read_text().splitlines():
            conn.execute(line)
        for job_id, *_ in schema.jobs(conn, empty_schema):
            conn.execute("SELECT alter_job(%s, scheduled => false)", [job_id])
        assert conn.execute("SELECT status FROM load_manifest ORDER BY id DESC LIMIT 1").fetchone() == ("loaded",)
        assert conn.execute("SELECT count(*) FROM roads").fetchone() == (0,)      # setup empties the tables: a reload is clean
        for table in schema.TABLES:
            text = (tmp_path / f"{table}.csv").read_text()
            assert text.splitlines()[0] == ",".join(schema.columns(table))
            with conn.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(
                    sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, schema.columns(table))))) as copy:
                copy.write(text)
            assert conn.execute("SELECT status FROM load_manifest ORDER BY id DESC LIMIT 1").fetchone() == ("loaded",)
        for line in (tmp_path / "after_load.sql").read_text().splitlines():
            conn.execute(line)
        assert conn.execute("SELECT status FROM load_manifest ORDER BY id DESC LIMIT 1").fetchone() == ("complete",)
    finally:
        conn.close()
    with dash.sunnyday_out(fixture_root):
        results = verify.run(db_url, empty_schema, fixture_root)
    assert all(c.ok for c in results), [c for c in results if not c.ok]      # the same checks as a direct load


# ------------------------------------------------------------------------------------------------ X1 to X5: the storm replay

NOW = datetime(2026, 10, 4, 15, 0, tzinfo=timezone.utc)
W_START = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)            # the tests replay four hours of the fixture's storm
W_END = datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc)
SHIFT = NOW - W_END


def do_replay(db_url, name, now=NOW, **kw):
    naps = []
    kw = {"window_start": W_START, "window_end": W_END, **kw}
    out = replay.replay(db_url, now=now, minutes=1, batches=4, schema=name, sleep=naps.append, **kw)
    return out, naps


def in_window(frame):
    return frame[(frame.time >= pd.Timestamp(W_START)) & (frame.time <= pd.Timestamp(W_END))]


def service_client(db_url, name, now):
    return TestClient(service.create_app(settings=service.Settings(url=db_url, schema=name), clock=lambda: now))


def test_X1_the_window_is_copied_shifted_to_end_now_and_labelled(db_url, fresh_schema, run, built):
    q = run(fresh_schema)
    before = counts(q)
    out, naps = do_replay(db_url, fresh_schema)
    cams, sens = in_window(built.tables["camera_readings"]), in_window(built.tables["sensor_levels"])
    assert out["rows"] == {"sensor_levels": len(sens), "camera_readings": len(cams)} == {"sensor_levels": 164, "camera_readings": 40}
    assert out["skipped"] == {"sensor_levels": 0, "camera_readings": 0}
    assert naps == [15.0, 15.0, 15.0]                                      # one minute in four batches: three pauses
    for table, originals in (("camera_readings", cams), ("sensor_levels", sens)):
        rows = q(sql.SQL("SELECT time, replay_of FROM {} WHERE replay_of IS NOT NULL").format(sql.Identifier(table)))
        assert len(rows) == len(originals) and all(t - was == SHIFT for t, was in rows)
        assert sorted(pd.Timestamp(was) for _, was in rows) == sorted(originals.time)
        assert q(sql.SQL("SELECT max(time) FROM {}").format(sql.Identifier(table)))[0][0] == NOW     # the window ends now
        assert q(sql.SQL("SELECT count(*) FROM {} WHERE replay_of IS NULL").format(sql.Identifier(table)))[0][0] == before[table]


def test_X1_a_replay_needs_a_complete_load(db_url, empty_schema, fixture_root, dash):
    dash.load_fixture(db_url, fixture_root, empty_schema, stop_after="copy")
    with pytest.raises(RuntimeError, match="not complete"):
        do_replay(db_url, empty_schema)


def test_X2_after_a_replay_the_alert_is_live_and_says_it_is_a_replay(db_url, fresh_schema, run):
    q = run(fresh_schema)
    do_replay(db_url, fresh_schema)
    assert q("SELECT sum(readings) FROM camera_hourly WHERE is_replay")[0][0] == 40      # summarised without any refresh by the test
    assert q("SELECT sum(readings) FROM sensor_hourly WHERE is_replay")[0][0] == 164
    with service_client(db_url, fresh_schema, NOW + timedelta(minutes=1)) as c:
        body = c.get("/api/alerts").json()
        assert body["as_of"] == "2026-10-04T15:00:00Z" and body["live"] is True
        assert sorted(a["camera_id"] for a in body["camera_alerts"]) == ["BF_01", "CB_01"]
        assert sorted(a["station"] for a in body["sensor_alerts"]) == ["BF_01", "CB_01"]
        assert all(a["replay"] is True and a["replay_of"].startswith("2026-09-27T") for a in body["camera_alerts"] + body["sensor_alerts"])
        hours = [h["hour"] for h in c.get("/api/alerts/peaks", params={"limit": 100}).json()["hours"]]
        assert not any(h.startswith("2026-10-04") for h in hours)          # a replay is never a peak
        assert c.get("/api/stats").json()["replay_rows"] == 204
        history = c.get("/api/camera_history", params={"camera_id": "BF_01", "start": "2026-10-04T00:00:00Z"}).json()["hours"]
        assert history and all(h["replay"] is True for h in history)


def test_X3_clearing_leaves_exactly_the_original_rows(db_url, fresh_schema, fixture_root, run, dash, built):
    q = run(fresh_schema)
    summaries_before = [q("SELECT * FROM camera_hourly ORDER BY 1, 2, 3"), q("SELECT * FROM sensor_hourly ORDER BY 1, 2, 3")]
    out, _ = do_replay(db_url, fresh_schema)
    assert replay.clear(db_url, fresh_schema) == out["rows"]
    assert counts(q) == built.counts
    assert q("SELECT count(*) FROM camera_hourly WHERE is_replay") == [(0,)] and q("SELECT count(*) FROM sensor_hourly WHERE is_replay") == [(0,)]
    assert [q("SELECT * FROM camera_hourly ORDER BY 1, 2, 3"), q("SELECT * FROM sensor_hourly ORDER BY 1, 2, 3")] == summaries_before
    with dash.sunnyday_out(fixture_root):
        results = verify.run(db_url, fresh_schema, fixture_root)
    assert all(c.ok for c in results), [c for c in results if not c.ok]
    assert replay.clear(db_url, fresh_schema) == {"sensor_levels": 0, "camera_readings": 0}       # clearing twice is harmless


def test_X4_a_second_replay_in_the_same_hour_shows_up(db_url, fresh_schema, run):
    q = run(fresh_schema)
    do_replay(db_url, fresh_schema)
    again, _ = do_replay(db_url, fresh_schema)
    assert again["rows"] == {"sensor_levels": 0, "camera_readings": 0}     # the same moment again adds nothing
    replay.clear(db_url, fresh_schema)
    do_replay(db_url, fresh_schema)                                        # after a clear, in the same clock hour
    assert q("SELECT sum(readings) FROM camera_hourly WHERE is_replay")[0][0] == 40
    later = NOW + timedelta(minutes=20)                                    # and once more, twenty minutes on, without a clear
    more, _ = do_replay(db_url, fresh_schema, now=later)
    assert more["rows"]["camera_readings"] == 40
    assert q("SELECT sum(readings) FROM camera_hourly WHERE is_replay")[0][0] == 80      # rows put into already-refreshed hours are seen
    assert q("SELECT sum(readings) FROM sensor_hourly WHERE is_replay")[0][0] == q("SELECT count(*) FROM sensor_levels WHERE replay_of IS NOT NULL")[0][0]
    with service_client(db_url, fresh_schema, later) as c:
        body = c.get("/api/alerts").json()
        assert body["as_of"] == "2026-10-04T15:20:00Z" and body["live"] is True and len(body["camera_alerts"]) == 2


def test_X5_a_replay_in_an_hour_that_holds_real_rows_leaves_them_alone(db_url, fresh_schema, fixture_root, run, dash):
    q = run(fresh_schema)
    real_rows = "SELECT * FROM {} WHERE NOT is_replay ORDER BY 1, 2, 3"
    before = [q(real_rows.format(v)) for v in ("camera_hourly", "sensor_hourly")]
    with service_client(db_url, fresh_schema, NOW) as c:
        peaks_before = c.get("/api/alerts/peaks", params={"limit": 100}).json()
    mixed_now = datetime(2026, 9, 26, 16, 3, tzinfo=timezone.utc)          # the replay lands on 26 September, where real rows are,
    out, _ = do_replay(db_url, fresh_schema, now=mixed_now)                # three minutes off the sensors' six-minute grid
    assert out["rows"] == {"sensor_levels": 164, "camera_readings": 40} and not any(out["skipped"].values())
    for view, key in (("camera_hourly", "camera_id"), ("sensor_hourly", "station")):
        mixed = q(f"SELECT count(*) FROM (SELECT bucket, {key} FROM {view} GROUP BY 1, 2 HAVING count(DISTINCT is_replay) = 2) m")
        assert mixed[0][0] > 0, view                                       # one hour, real and replayed side by side
    assert [q(real_rows.format(v)) for v in ("camera_hourly", "sensor_hourly")] == before
    with service_client(db_url, fresh_schema, NOW) as c:
        assert c.get("/api/alerts/peaks", params={"limit": 100}).json() == peaks_before
    with dash.sunnyday_out(fixture_root):
        results = {c.name: c for c in verify.run(db_url, fresh_schema, fixture_root)}
    assert all(c.ok for c in results.values()), [c for c in results.values() if not c.ok]
    assert results["storm replay rows"].detail.startswith("204 present")


def test_X5_a_replayed_row_never_overwrites_a_real_one_and_the_count_left_out_is_reported(db_url, fresh_schema, run):
    q = run(fresh_schema)
    real = q("SELECT station, time, level_m FROM sensor_levels ORDER BY 1, 2")
    exactly_a_day = datetime(2026, 9, 26, 16, 0, tzinfo=timezone.utc)      # every shifted sensor time meets a real reading
    out, _ = do_replay(db_url, fresh_schema, now=exactly_a_day)
    assert out["rows"]["sensor_levels"] == 0 and out["skipped"]["sensor_levels"] == 164
    assert out["rows"]["camera_readings"] == 40 and out["skipped"]["camera_readings"] == 0     # another file name: no clash
    assert q("SELECT station, time, level_m FROM sensor_levels ORDER BY 1, 2") == real


def test_X2_with_the_default_window_the_alert_is_live_from_the_first_batch(db_url, fresh_schema):
    assert (replay.DEFAULT_START, replay.DEFAULT_END) == (datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc), W_END)
    seen = []
    with service_client(db_url, fresh_schema, NOW) as c:
        replay.replay(db_url, now=NOW, minutes=1, batches=4, schema=fresh_schema,
                      sleep=lambda seconds: seen.append(c.get("/api/alerts").json()))
        seen.append(c.get("/api/alerts").json())
    assert len(seen) == 4 and all(b["live"] for b in seen)                # every batch lands inside the last hour
    assert [b["as_of"] for b in seen] == sorted(b["as_of"] for b in seen) and seen[-1]["as_of"] == "2026-10-04T15:00:00Z"
    assert all(a["replay"] for b in seen for a in b["camera_alerts"] + b["sensor_alerts"]) and seen[-1]["camera_alerts"]


def test_X_an_upside_down_window_is_refused(db_url):
    with pytest.raises(ValueError, match="end after it starts"):
        replay.replay(db_url, window_start=replay.DEFAULT_END, window_end=replay.DEFAULT_START, schema="test_never_created")
