# GENERATED from web/service/queries.py by scripts/sync_tiger_service.py. Edit that file, then rerun the script.
"""The service's SQL. Every value is a bound parameter; the only names put into a query come from the fixed
dictionaries below. Every function takes an open connection whose search path is the dashboard's schema.

The running summaries (camera_hourly, sensor_hourly, pothole_monthly) do the time-series work; the plain tables
(roads, cameras) say where things are. The alert query joins the two.
"""
import json
import re
from datetime import datetime, timedelta, timezone

from psycopg import sql

from tigersvc import export
from tigersvc import schema as tables

FLOODED_CM = 2.0      # the flood chat's rule (src/model/flood_camera.py): under 2 cm is wet, not flooded
FLAG_P = 0.5          # a camera frame is flagged at this probability
MAX_PAGE = 500
SEG_ID = re.compile(r"^ncdot:[0-9A-Za-z]+:[0-9]+\.[0-9]{3}$")
SORTS = {"rank": "priority_rank", "rating": "rating", "years_to_poor": "pred_years_to_poor", "wear_rate": "pred_rate",
         "crack_risk": "pred_crack", "flood_risk": "pred_flood", "cost": "treatment_cost"}
DIRECTIONS = {"asc": "ASC", "desc": "DESC"}
ROAD_COLUMNS = tables.columns("roads")
CAMERA_FLAG_CAVEAT = export.CAMERA_FLAG_CAVEAT


class BadRequest(ValueError):
    """The caller sent something the service does not accept."""


class NotFound(LookupError):
    """Nothing in the database matches."""


def _dicts(cur):
    names = [c.name for c in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _one(conn, query, params=None):
    row = conn.execute(query, params).fetchone()
    return row[0] if row else None


def manifest(conn):
    """The latest load record, or None when nothing has been loaded."""
    cur = conn.execute("SELECT id, status, started_at, finished_at, row_counts, compression, code_version, "
                       "timescaledb_version FROM load_manifest ORDER BY id DESC LIMIT 1")
    rows = _dicts(cur)
    return rows[0] if rows else None


def manifest_status(conn):
    m = manifest(conn)
    return (m["id"], m["status"]) if m else (None, "empty")


def road_item(r):
    """One road as the service returns it: each prediction carries its held-out flag; flood says when it is not scored."""
    return {
        "seg_id": r["seg_id"], "rank": r["priority_rank"], "bucket": r["repair_bucket"],
        "route": r["route"], "route_id": r["route_id"], "county": r["county"], "system": r["system"],
        "from": r["from_desc"], "to": r["to_desc"], "beg_mp": r["beg_mp"], "end_mp": r["end_mp"], "length_mi": r["length_mi"],
        "lanes": r["lanes"], "rating": r["rating"], "survey_year": r["survey_year"],
        "last_rehab_year": r["last_rehab_year"], "last_rehab_type": r["last_rehab_type"],
        "years_to_poor": r["pred_years_to_poor"],
        "wear_rate": {"value": r["pred_rate"], "heldout": r["rate_heldout"]},
        "crack_risk": {"value": r["pred_crack"], "heldout": r["crack_heldout"]},
        "flood_risk": {"value": r["pred_flood"], "scored": r["flood_scored"], "heldout": r["flood_heldout"],
                       "note": None if r["flood_scored"] else "not scored: outside the Helene zone"},
        "in_helene_zone": r["in_helene_zone"], "helene_damaged": r["helene_damaged"] if r["in_helene_zone"] else None,
        "treatment": r["treatment"], "treatment_cost": r["treatment_cost"],
        "crash": {"per_million_vehicle_miles": r["crash_per_mvm"], "per_mile_year": r["crash_per_mile_year"],
                  "fatal_10yr": r["fatal_10yr"], "serious_10yr": r["serious_10yr"], "used_in_rank": False},
        "traffic": {"vehicles_per_day": r["aadt_best"], "source": r["aadt_source"]},
        "potholes": {"city": r["pothole_city"], "all_time": r["potholes_all_time"], "in_window": r["potholes_in_window"],
                     "note": None if r["pothole_city"] else "no city collects reports here: zero means not recorded"},
        "mid": [r["mid_lon"], r["mid_lat"]],
        "bbox": [r["min_lon"], r["min_lat"], r["max_lon"], r["max_lat"]],
    }


def worklist(conn, *, bucket=None, county=None, system=None, in_zone=None, sort="rank", direction="asc", limit=50, offset=0):
    """A page of roads, worst first by default. Ties always break by seg_id, so pages never overlap or skip."""
    if sort not in SORTS:
        raise BadRequest(f"sort must be one of {sorted(SORTS)}")
    if direction not in DIRECTIONS:
        raise BadRequest("direction must be asc or desc")
    if bucket is not None and bucket not in tables.BUCKETS:
        raise BadRequest(f"bucket must be one of {tables.BUCKETS}")
    if limit < 1 or offset < 0:
        raise BadRequest("limit must be at least 1 and offset at least 0")
    limit = min(limit, MAX_PAGE)
    where, params = [], []
    for column, value in (("repair_bucket", bucket), ("county", county), ("system", system), ("in_helene_zone", in_zone)):
        if value is not None:
            where.append(sql.SQL("{} = %s").format(sql.Identifier(column)))
            params.append(value)
    clause = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where) if where else sql.SQL("")
    total = _one(conn, sql.SQL("SELECT count(*) FROM roads") + clause, params)
    query = (sql.SQL("SELECT {} FROM roads").format(sql.SQL(", ").join(map(sql.Identifier, ROAD_COLUMNS))) + clause
             + sql.SQL(" ORDER BY {} {} NULLS LAST, seg_id LIMIT %s OFFSET %s").format(
                 sql.Identifier(SORTS[sort]), sql.SQL(DIRECTIONS[direction])))
    rows = _dicts(conn.execute(query, params + [limit, offset]))
    return {"total": total, "limit": limit, "offset": offset, "sort": sort, "direction": direction,
            "roads": [road_item(r) for r in rows]}


def summary(conn):
    m = manifest(conn)
    buckets = dict(conn.execute("SELECT repair_bucket, count(*) FROM roads GROUP BY 1").fetchall())
    totals = conn.execute(
        "SELECT count(*), sum(length_mi), count(*) FILTER (WHERE in_helene_zone), "
        "count(*) FILTER (WHERE rate_heldout), count(*) FILTER (WHERE crack_heldout), count(*) FILTER (WHERE flood_heldout), "
        "sum(treatment_cost) FILTER (WHERE repair_bucket = 'fix_now'), "
        "count(*) FILTER (WHERE repair_bucket = 'fix_now' AND treatment_cost IS NULL) FROM roads").fetchone()
    return {
        "load": {"status": m["status"] if m else "empty", "finished_at": m["finished_at"] if m else None},
        "roads": totals[0], "miles": totals[1],
        "buckets": {b: buckets.get(b, 0) for b in tables.BUCKETS},
        "bucket_rules": {"fix_now": "predicted years to Poor is 0: the rating is already at or below 60",
                         "within_1y": "above 0 up to 1 year", "within_5y": "above 1 up to 5 years", "later": "above 5 years",
                         "unknown": "no forecast: the rating is missing or older than the last resurfacing"},
        "rank": "bucket, then years to Poor, then rating (lowest first), then predicted wear (fastest first); crash rate is not used",
        "in_helene_zone": totals[2],
        "heldout": {"wear_rate": totals[3], "crack_risk": totals[4], "flood_risk": totals[5]},
        "fix_now_cost": {"ncdot_estimate_total": totals[6], "roads_without_an_estimate": totals[7],
                         "note": "NCDOT's figure; its unit is not documented"},
        "what_this_cannot_claim": export.CAVEATS,
    }


def road(conn, seg_id):
    if not seg_id or not SEG_ID.match(seg_id):
        raise BadRequest("seg_id must look like ncdot:40002748092:0.940")
    rows = _dicts(conn.execute(sql.SQL("SELECT {} FROM roads WHERE seg_id = %s").format(
        sql.SQL(", ").join(map(sql.Identifier, ROAD_COLUMNS))), [seg_id]))
    if not rows:
        raise NotFound(f"no state road has the id {seg_id}")
    out = road_item(rows[0])
    shape = _one(conn, "SELECT geojson FROM road_shapes WHERE seg_id = %s", [seg_id])
    out["shape"] = json.loads(shape) if shape else None
    out["potholes"]["by_month"] = _dicts(conn.execute(
        "SELECT bucket AS month, source, reports FROM pothole_monthly WHERE seg_id = %s ORDER BY bucket, source", [seg_id]))
    out["cameras"] = _dicts(conn.execute(
        "SELECT c.camera_id, c.name, c.lat, c.lon, c.role, c.known_dry, c.seg_dist_m, h.bucket AS latest_hour, "
        "h.worst_p_flooded, h.worst_depth_pred_cm, h.readings FROM cameras c LEFT JOIN LATERAL ("
        "SELECT bucket, worst_p_flooded, worst_depth_pred_cm, readings FROM camera_hourly "
        "WHERE camera_id = c.camera_id AND NOT is_replay ORDER BY bucket DESC LIMIT 1) h ON true "
        "WHERE c.seg_id = %s ORDER BY c.camera_id", [seg_id]))
    return out


def parse_time(text, name="as_of"):
    """A time with a zone (or Z). A time without one is refused: it would be read in whatever zone the server is in."""
    try:
        t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise BadRequest(f"{name} must be a time like 2026-09-27T15:30:00Z") from None
    if t.tzinfo is None:
        raise BadRequest(f"{name} must carry a time zone, for example a trailing Z")
    return t.astimezone(timezone.utc)


def latest_reading(conn):
    """The newest reading of any kind, replayed rows included. None when the tables are empty."""
    return _one(conn, "SELECT greatest((SELECT max(time) FROM camera_readings), (SELECT max(time) FROM sensor_levels))")


def _reading(row, keys):
    return None if row is None else {k: row[k] for k in keys}


def alerts(conn, as_of=None, now=None, hours=2):
    """Camera flags and sensor alerts for the clock hour holding `as_of` and, with hours=2 (the default), the hour before.

    The hourly summaries pick the cameras and stations; for those few, the raw readings up to `as_of` give the worst
    reading and the latest reading, each with its own time. A camera whose only flag is after `as_of` is not listed."""
    if hours not in (1, 2):
        raise BadRequest("hours must be 1 or 2")
    now = now or datetime.now(timezone.utc)
    given = as_of is not None
    as_of = as_of or latest_reading(conn)
    base = {"as_of": as_of, "as_of_was_given": given, "caveat": CAMERA_FLAG_CAVEAT, "flag_at": FLAG_P, "flooded_cm": FLOODED_CM,
            "camera_alerts": [], "sensor_alerts": []}
    if as_of is None:
        return {**base, "live": False, "window_start": None}
    hour = as_of.replace(minute=0, second=0, microsecond=0)
    start = hour - timedelta(hours=hours - 1)
    base.update(window_start=start, window_hours=hours, live=bool(timedelta(0) <= now - as_of <= timedelta(hours=1)))

    cams = _dicts(conn.execute(
        "SELECT DISTINCT h.camera_id, h.is_replay FROM camera_hourly h WHERE h.bucket >= %s AND h.bucket <= %s AND h.worst_p_flooded >= %s",
        [start, hour, FLAG_P]))
    reading_keys = ["time", "p_flooded", "depth_pred_cm", "depth_measured_cm"]
    for c in cams:
        params = [c["camera_id"], start, as_of, c["is_replay"]]
        scope = "FROM camera_readings WHERE camera_id = %s AND time >= %s AND time <= %s AND (replay_of IS NOT NULL) = %s"
        worst = _dicts(conn.execute(f"SELECT time, p_flooded, depth_pred_cm, depth_measured_cm, replay_of {scope} "
                                    "ORDER BY p_flooded DESC NULLS LAST, time LIMIT 1", params))
        if not worst or worst[0]["p_flooded"] is None or worst[0]["p_flooded"] < FLAG_P:
            continue                                                  # its flag came after `as_of`
        latest = _dicts(conn.execute(f"SELECT time, p_flooded, depth_pred_cm, depth_measured_cm {scope} "
                                     "ORDER BY time DESC LIMIT 1", params))
        found = _dicts(conn.execute(
            "SELECT c.camera_id, c.name, c.lat, c.lon, c.role, c.known_dry, c.seg_id, c.seg_dist_m, r.route, r.county, "
            "r.rating, r.repair_bucket, r.priority_rank FROM cameras c LEFT JOIN roads r ON r.seg_id = c.seg_id "
            "WHERE c.camera_id = %s", [c["camera_id"]]))
        info = found[0] if found else {"camera_id": c["camera_id"], "name": None, "lat": None, "lon": None, "role": None,
                                       "known_dry": False, "seg_id": None, "seg_dist_m": None}   # a reading with no camera row
        base["camera_alerts"].append({
            "camera_id": info["camera_id"], "name": info["name"], "lat": info["lat"], "lon": info["lon"],
            "role": info["role"], "known_dry": info["known_dry"],
            "note": "NCDOT still taken on a dry road: a known false alarm" if info["known_dry"] else None,
            "replay": c["is_replay"], "replay_of": worst[0]["replay_of"],
            "road": None if info["seg_id"] is None else {
                "seg_id": info["seg_id"], "distance_m": info["seg_dist_m"], "route": info["route"], "county": info["county"],
                "rating": info["rating"], "bucket": info["repair_bucket"], "rank": info["priority_rank"]},
            "worst": _reading(worst[0], reading_keys), "latest": _reading(latest[0], reading_keys),
        })
    base["camera_alerts"].sort(key=lambda a: (a["known_dry"], -a["worst"]["p_flooded"], a["camera_id"]))

    stations = _dicts(conn.execute(
        "SELECT DISTINCT h.station, h.is_replay FROM sensor_hourly h WHERE h.bucket >= %s AND h.bucket <= %s AND h.worst_depth_on_road_cm >= %s",
        [start, hour, FLOODED_CM]))
    sensor_keys = ["time", "depth_on_road_cm", "level_m"]
    for s in stations:
        params = [s["station"], start, as_of, s["is_replay"]]
        scope = "FROM sensor_levels WHERE station = %s AND time >= %s AND time <= %s AND (replay_of IS NOT NULL) = %s"
        worst = _dicts(conn.execute(f"SELECT time, depth_on_road_cm, level_m, name, lat, lon, road_level_m, replay_of {scope} "
                                    "ORDER BY depth_on_road_cm DESC NULLS LAST, time LIMIT 1", params))
        if not worst or worst[0]["depth_on_road_cm"] is None or worst[0]["depth_on_road_cm"] < FLOODED_CM:
            continue
        latest = _dicts(conn.execute(f"SELECT time, depth_on_road_cm, level_m {scope} ORDER BY time DESC LIMIT 1", params))
        base["sensor_alerts"].append({
            "station": s["station"], "name": worst[0]["name"], "lat": worst[0]["lat"], "lon": worst[0]["lon"],
            "road_level_m": worst[0]["road_level_m"], "replay": s["is_replay"], "replay_of": worst[0]["replay_of"],
            "note": "measured water level above the road height read off camera frames (good to about 5 cm)",
            "worst": _reading(worst[0], sensor_keys), "latest": _reading(latest[0], sensor_keys),
        })
    base["sensor_alerts"].sort(key=lambda a: (-a["worst"]["depth_on_road_cm"], a["station"]))
    return base


def alert_peaks(conn, limit=10):
    """The hours with the most alerts, for a storm replay. Known-dry cameras are counted apart; replayed rows are left out."""
    if limit < 1:
        raise BadRequest("limit must be at least 1")
    rows = _dicts(conn.execute(
        "WITH cam AS (SELECT h.bucket, count(*) FILTER (WHERE NOT c.known_dry) AS camera_flags, "
        "count(*) FILTER (WHERE c.known_dry) AS known_dry_flags FROM camera_hourly h JOIN cameras c USING (camera_id) "
        "WHERE NOT h.is_replay AND h.worst_p_flooded >= %s GROUP BY 1), "
        "sen AS (SELECT bucket, count(*) AS sensor_alerts FROM sensor_hourly WHERE NOT is_replay "
        "AND worst_depth_on_road_cm >= %s GROUP BY 1) "
        "SELECT bucket AS hour, coalesce(cam.camera_flags, 0) AS camera_flags, coalesce(sen.sensor_alerts, 0) AS sensor_alerts, "
        "coalesce(cam.known_dry_flags, 0) AS known_dry_flags FROM cam FULL JOIN sen USING (bucket) "
        "ORDER BY coalesce(cam.camera_flags, 0) + coalesce(sen.sensor_alerts, 0) DESC, bucket DESC LIMIT %s",
        [FLAG_P, FLOODED_CM, min(limit, 100)]))
    for r in rows:
        r["as_of"] = r["hour"] + timedelta(minutes=59, seconds=59)
    return {"hours": rows, "note": "ranked by camera flags from cameras not known dry, plus sensor alerts, counted in that "
                                   "one hour; ask /api/alerts with the given as_of and hours=1 to see exactly that hour"}


def camera_history(conn, camera_id, start=None, end=None):
    cam = _dicts(conn.execute("SELECT camera_id, name, lat, lon, role, known_dry, seg_id FROM cameras WHERE camera_id = %s",
                              [camera_id]))
    if not cam:
        raise NotFound(f"no camera has the id {camera_id}")
    where, params = ["camera_id = %s"], [camera_id]
    if start is not None:
        where.append("bucket >= %s")
        params.append(start)
    if end is not None:
        where.append("bucket <= %s")
        params.append(end)
    hours = _dicts(conn.execute(
        "SELECT bucket AS hour, is_replay AS replay, worst_p_flooded, worst_depth_pred_cm, worst_depth_measured_cm, readings, "
        "first_reading, last_reading FROM camera_hourly WHERE " + " AND ".join(where) + " ORDER BY bucket, is_replay LIMIT 2000",
        params))
    return {"camera": cam[0], "hours": hours, "note": "hourly worst values, not single readings"}


def stats(conn, schema):
    """What the database is doing: rows, chunks, compressed bytes, summaries, jobs, size."""
    hyper = {}
    for table in tables.HYPERTABLES:
        rows = _one(conn, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
        c = conn.execute(sql.SQL("SELECT total_chunks, number_compressed_chunks, before_compression_total_bytes, "
                                 "after_compression_total_bytes FROM hypertable_columnstore_stats({})")
                         .format(sql.Literal(table))).fetchone() or (0, 0, None, None)
        hyper[table] = {"rows": rows, "chunks": c[0] or 0, "compressed_chunks": c[1] or 0,
                        "bytes_before": c[2], "bytes_after": c[3],
                        "compression_ratio": round(float(c[2]) / float(c[3]), 2) if c[2] and c[3] else None,
                        "chunk_interval": tables.HYPERTABLES[table]["chunk"]}
    live = dict(conn.execute("SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates "
                             "WHERE view_schema = %s", [schema]).fetchall())
    summaries = {v: {"rows": _one(conn, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(v))),
                     "includes_rows_newer_than_last_refresh": live.get(v) is False, "over": tables.SUMMARIES[v]["table"]}
                 for v in tables.SUMMARIES}
    jobs = [{"job": p, "on": h, "scheduled": s, "settings": cfg} for _, p, h, cfg, s in tables.jobs(conn, schema)]
    plain = {t: _one(conn, sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))) for t in ("roads", "road_shapes", "cameras")}
    replay = _one(conn, "SELECT (SELECT count(*) FROM camera_readings WHERE replay_of IS NOT NULL) + "
                        "(SELECT count(*) FROM sensor_levels WHERE replay_of IS NOT NULL)")
    return {"time_partitioned_tables": hyper, "running_summaries": summaries, "background_jobs": jobs, "plain_tables": plain,
            "replay_rows": replay, "database_size_bytes": _one(conn, "SELECT pg_database_size(current_database())"),
            "timescaledb_version": _one(conn, "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"),
            "postgres_version": _one(conn, "SHOW server_version"), "load": manifest(conn)}


def risk_page(conn, after, size):
    """One page of the risk file's rows after the id `after`, in id order."""
    query = sql.SQL("SELECT {} FROM roads WHERE seg_id > %s ORDER BY seg_id LIMIT %s").format(
        sql.SQL(", ").join(map(sql.Identifier, export.SOURCE_COLUMNS)))
    return conn.execute(query, [after, size]).fetchall()
