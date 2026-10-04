# GENERATED from web/tiger/schema.py by scripts/sync_tiger_service.py. Edit that file, then rerun the script.
"""Tables, time-partitioned tables, running summaries and policies for the Tiger Data service.

The column lists here are the single source of truth: build.py produces exactly these columns, load.py copies
them by name, and the tests compare both against this file.

Checked on TimescaleDB 2.30.2 (2026-10-03):
- The extension lives in schema `public`, so the search path must be `<schema>, public` or time_bucket is not found.
- CREATE TABLE ... WITH (tsdb.hypertable ...) turns columnstore on and adds its own columnstore policy, first run a
  day later. That policy is kept; adding one by hand makes it run at once.
- A continuous aggregate can only be created inside or outside a transaction WITH NO DATA here, real-time aggregation
  is off unless materialized_only = false, and a refresh policy runs at once unless initial_start is in the future.
"""
import psycopg
from psycopg import sql

from tigersvc import config

F = "double precision"
ID = 'text COLLATE "C"'   # byte-order comparison: the database then sorts ids exactly as Python does
BUCKETS = ["fix_now", "within_1y", "within_5y", "later", "unknown"]
MANIFEST_STATUSES = ["loaded", "complete"]


def _f(name, extra=None):
    """A float column that refuses not-a-number and infinity. (`c >= 0` alone lets not-a-number through.)"""
    check = f"{name} <> 'NaN' AND {name} < 'Infinity' AND {name} > '-Infinity'"
    return (name, F, f"{check} AND {extra}" if extra else check)


def _seg(name="seg_id"):
    return (name, ID, f"{name} IS NULL OR {name} LIKE 'ncdot:%'")


ROADS = [
    ("seg_id", ID + " PRIMARY KEY", "seg_id LIKE 'ncdot:%'"),
    ("route_id", "text", None), ("route", "text", None), ("county_code", "text", None), ("county", "text", None),
    _f("beg_mp"), _f("end_mp"), ("from_desc", "text", None), ("to_desc", "text", None), _f("length_mi"),
    ("system", "text", None), ("division", "integer", None), ("lanes", "integer", None),
    _f("rating", "rating > 0 AND rating <= 100"), ("survey_year", "integer", None), ("last_rehab_year", "integer", None),
    ("last_rehab_type", "text", None), ("treatment", "text", None), _f("treatment_cost", "treatment_cost >= 0"),
    _f("pred_rate"), _f("pred_years_to_poor", "pred_years_to_poor >= 0"), _f("pred_crack"),
    _f("pred_flood"), ("flood_scored", "boolean NOT NULL", "flood_scored OR pred_flood IS NULL"),
    ("in_helene_zone", "boolean NOT NULL", None), ("rate_heldout", "boolean NOT NULL", None),
    ("crack_heldout", "boolean NOT NULL", None), ("flood_heldout", "boolean NOT NULL", None),
    ("helene_damaged", "boolean NOT NULL", None),
    ("repair_bucket", "text NOT NULL", "repair_bucket IN (" + ", ".join(f"'{b}'" for b in BUCKETS) + ")"),
    ("priority_rank", "integer NOT NULL", None),
    _f("crash_per_mvm"), _f("crash_per_mile_year"), _f("crash_cover"), ("fatal_10yr", "integer", None),
    ("serious_10yr", "integer", None), _f("ncdot_safety_score"), _f("aadt_best"), ("aadt_source", "text", None),
    ("pothole_city", "text", None), ("potholes_all_time", "integer", None), ("potholes_in_window", "integer", None),
    _f("mid_lon"), _f("mid_lat"), _f("min_lon"), _f("min_lat"), _f("max_lon"), _f("max_lat"),
]
ROAD_SHAPES = [("seg_id", ID + " PRIMARY KEY REFERENCES roads (seg_id)", None), ("geojson", "text NOT NULL", None)]
CAMERAS = [
    ("camera_id", ID + " PRIMARY KEY", None), ("site", "text NOT NULL", None), ("station", "text NOT NULL", None),
    ("name", "text", None), _f("lat"), _f("lon"), _seg(), _f("seg_dist_m"),
    ("role", "text NOT NULL", "role IN ('cv', 'extra')"), ("known_dry", "boolean NOT NULL", None),
]
CAMERA_READINGS = [
    ("time", "timestamptz NOT NULL", None), ("camera_id", ID + " NOT NULL", None), ("site", "text NOT NULL", None),
    _f("p_flooded", "p_flooded >= 0 AND p_flooded <= 1"), _f("depth_pred_cm", "depth_pred_cm >= 0"),
    _f("depth_measured_cm", "depth_measured_cm >= 0"), ("file", "text NOT NULL", None), ("run", "text", None),
    ("replay_of", "timestamptz", None),
]
SENSOR_LEVELS = [
    ("time", "timestamptz NOT NULL", None), ("station", "text NOT NULL", None), ("name", "text", None), _f("lat"), _f("lon"),
    ("level_m", F + " NOT NULL", _f("level_m")[2]), _f("road_level_m"), _f("depth_on_road_cm", "depth_on_road_cm >= 0"),
    ("replay_of", "timestamptz", None),
]
POTHOLE_REPORTS = [
    ("time", "timestamptz NOT NULL", None), ("report_id", "text NOT NULL", None), ("source", "text NOT NULL", None),
    ("request_type", "text", None), _seg(), _f("dist_m"), _f("lon"), _f("lat"),
]
TABLES = {"roads": ROADS, "road_shapes": ROAD_SHAPES, "cameras": CAMERAS, "camera_readings": CAMERA_READINGS,
          "sensor_levels": SENSOR_LEVELS, "pothole_reports": POTHOLE_REPORTS}   # load order: roads before road_shapes

# time-partitioned tables: chunk size, the column old chunks are grouped by when compressed, and the unique key
HYPERTABLES = {
    "camera_readings": {"chunk": "1 day", "segmentby": "site", "unique": "site, time, file"},
    "sensor_levels": {"chunk": "1 day", "segmentby": "station", "unique": "station, time"},
    "pothole_reports": {"chunk": "1 year", "segmentby": "source", "unique": "report_id, time"},
}
# running summaries. is_replay keeps real and replayed rows of one camera and hour in separate summary rows.
# The values are hourly worst values, not one reading; first_reading and last_reading bound the hour's readings.
SUMMARIES = {
    "camera_hourly": {
        "table": "camera_readings", "end_offset": "1 hour", "every": "30 minutes",
        "select": "SELECT time_bucket(INTERVAL '1 hour', time) AS bucket, camera_id, (replay_of IS NOT NULL) AS is_replay, "
                  "max(p_flooded) AS worst_p_flooded, max(depth_pred_cm) AS worst_depth_pred_cm, "
                  "max(depth_measured_cm) AS worst_depth_measured_cm, count(*) AS readings, "
                  "min(time) AS first_reading, max(time) AS last_reading FROM camera_readings GROUP BY 1, 2, 3",
    },
    "sensor_hourly": {
        "table": "sensor_levels", "end_offset": "1 hour", "every": "30 minutes",
        "select": "SELECT time_bucket(INTERVAL '1 hour', time) AS bucket, station, (replay_of IS NOT NULL) AS is_replay, "
                  "max(level_m) AS highest_level_m, avg(level_m) AS mean_level_m, "
                  "max(depth_on_road_cm) AS worst_depth_on_road_cm, count(*) AS readings, "
                  "min(time) AS first_reading, max(time) AS last_reading FROM sensor_levels GROUP BY 1, 2, 3",
    },
    "pothole_monthly": {
        "table": "pothole_reports", "end_offset": "1 month", "every": "1 day",
        "select": "SELECT time_bucket(INTERVAL '1 month', time, 'UTC') AS bucket, seg_id, source, count(*) AS reports "
                  "FROM pothole_reports GROUP BY 1, 2, 3",
    },
}


class SetupRefused(RuntimeError):
    """The database would not accept something the load needs. The message says what, in plain words."""


def columns(table):
    return [name for name, _, _ in TABLES[table]]


def _column_sql(spec):
    name, kind, check = spec
    return f"{name} {kind}" + (f" CHECK ({check})" if check else "")


def statements():
    """(label, SQL) in order. Each is safe to run twice. Names are unqualified: setup sets the search path first."""
    out = []
    for table in ("roads", "road_shapes", "cameras"):
        body = ", ".join(_column_sql(s) for s in TABLES[table])
        out.append((f"table {table}", f"CREATE TABLE IF NOT EXISTS {table} ({body})"))
    out.append(("table load_manifest",
                "CREATE TABLE IF NOT EXISTS load_manifest (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
                "started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, "
                "status text NOT NULL CHECK (status IN ('loaded', 'complete')), sources jsonb NOT NULL, "
                "row_counts jsonb NOT NULL, compression jsonb, code_version text, timescaledb_version text)"))
    out.append(("index roads by bucket", "CREATE INDEX IF NOT EXISTS roads_bucket_rank ON roads (repair_bucket, priority_rank)"))
    out.append(("index roads by county", "CREATE INDEX IF NOT EXISTS roads_county ON roads (county)"))
    for table, h in HYPERTABLES.items():
        body = ", ".join(_column_sql(s) for s in TABLES[table]) + f", UNIQUE ({h['unique']})"
        out.append((f"time-partitioned table {table}",
                    f"CREATE TABLE IF NOT EXISTS {table} ({body}) WITH (tsdb.hypertable, tsdb.partition_column = 'time', "
                    f"tsdb.chunk_interval = '{h['chunk']}', tsdb.segmentby = '{h['segmentby']}', tsdb.orderby = 'time DESC')"))
    for view, s in SUMMARIES.items():
        out.append((f"running summary {view}",
                    f"CREATE MATERIALIZED VIEW IF NOT EXISTS {view} WITH (timescaledb.continuous, "
                    f"timescaledb.materialized_only = false) AS {s['select']} WITH NO DATA"))
        # the first run is set in the future, so adding the policy starts nothing
        out.append((f"refresh policy for {view}",
                    f"SELECT add_continuous_aggregate_policy('{view}', start_offset => NULL, "
                    f"end_offset => INTERVAL '{s['end_offset']}', schedule_interval => INTERVAL '{s['every']}', "
                    f"initial_start => now() + INTERVAL '{s['every']}', if_not_exists => true)"))
    return out


def jobs(conn, schema):
    """(job_id, proc_name, hypertable_name, config, scheduled) for the schema's background jobs."""
    return conn.execute("SELECT job_id, proc_name, hypertable_name, config, scheduled FROM timescaledb_information.jobs "
                        "WHERE hypertable_schema = %s ORDER BY proc_name, hypertable_name", [schema]).fetchall()


def setup(conn, schema, schedule_jobs=True, extra_statements=()):
    """Create everything. Safe to run twice. Needs an autocommit connection: summaries cannot be refreshed in a transaction."""
    if not conn.autocommit:
        raise SetupRefused("setup needs an autocommit connection")
    info = config.probe(conn)
    version = config.parse_version(info["timescaledb_version"])
    if not version:
        raise SetupRefused("the database has no TimescaleDB extension")
    if version[:2] < config.MIN_TIMESCALE:
        raise SetupRefused(f"TimescaleDB {info['timescaledb_version']} is too old: 2.20 or newer is needed")
    try:
        conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        config.apply_session(conn, schema=schema)
    except psycopg.Error as e:
        raise SetupRefused(f"the database refused schema {schema}: {config._reason(e)}") from None
    for label, text in list(statements()) + list(extra_statements):
        try:
            conn.execute(text)
        except psycopg.Error as e:
            raise SetupRefused(f"the database refused {label}: {config._reason(e)}") from None
    if not schedule_jobs:
        for job_id, *_ in jobs(conn, schema):
            conn.execute("SELECT alter_job(%s, scheduled => false)", [job_id])
    return info
