"""Replay a real storm so the database can be seen updating.

Usage:  python -m web.tiger.replay [--minutes 10] [--start 2026-09-27T15:00:00Z --end 2026-09-27T16:00:00Z]
        python -m web.tiger.replay --clear

The real readings are from late September, so nothing changes on its own during a demo. This copies the real sensor
and camera rows of a storm window into the same tables with every time moved forward by the same amount, so the
window ends now, and feeds them in a few at a time. The hourly summaries and the alert follow as the rows arrive. The default window
is the storm's peak hour (7 camera flags and 6 sensor alerts in the real data); with a one-hour window every batch lands
inside the last hour, so the alert reads as live from the first batch.

Every replayed row keeps its original time in `replay_of`. Replayed rows are labelled wherever the service shows
them, are left out of the check command and of the peak hours, and are removed by --clear.

After each batch the two hourly summaries are refreshed over the hours the batch touched: real-time aggregation only
adds rows newer than the last refreshed hour, so rows put into an hour that was already refreshed would otherwise
stay invisible.
"""
import argparse
import time as clock_time
from datetime import datetime, timedelta, timezone

import psycopg

from web.tiger import config

DEFAULT_START = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)     # the peak hour of the late-September flooding
DEFAULT_END = datetime(2026, 9, 27, 16, 0, tzinfo=timezone.utc)
HOURLY = ("camera_hourly", "sensor_hourly")
COPY = {
    "sensor_levels": "INSERT INTO sensor_levels (time, station, name, lat, lon, level_m, road_level_m, depth_on_road_cm, replay_of) "
                     "SELECT time + %(shift)s, station, name, lat, lon, level_m, road_level_m, depth_on_road_cm, time "
                     "FROM sensor_levels WHERE replay_of IS NULL AND time > %(a)s AND time <= %(b)s ON CONFLICT DO NOTHING",
    "camera_readings": "INSERT INTO camera_readings (time, camera_id, site, p_flooded, depth_pred_cm, depth_measured_cm, file, run, replay_of) "
                       "SELECT time + %(shift)s, camera_id, site, p_flooded, depth_pred_cm, depth_measured_cm, file, run, time "
                       "FROM camera_readings WHERE replay_of IS NULL AND time > %(a)s AND time <= %(b)s ON CONFLICT DO NOTHING",
}


def _hour(t):
    return t.replace(minute=0, second=0, microsecond=0)


def _refresh(admin, lo, hi):
    """Refresh both hourly summaries over [lo's hour, hi's hour + 1 h)."""
    for view in HOURLY:
        admin.execute("CALL refresh_continuous_aggregate(%s, %s::timestamptz, %s::timestamptz)",
                      [view, _hour(lo), _hour(hi) + timedelta(hours=1)])


def replay(url, *, window_start=DEFAULT_START, window_end=DEFAULT_END, now=None, minutes=10.0, batches=None, schema=None,
           sleep=clock_time.sleep):
    """Feed the window's rows in, shifted to end at `now`. Returns the counts and the shift."""
    if window_end <= window_start:
        raise ValueError("the window must end after it starts")
    schema = schema or config.schema_name()
    now = now or datetime.now(timezone.utc)
    shift = now - window_end
    batches = batches or max(1, int(round(minutes * 6)))               # about one batch every ten seconds
    pause = minutes * 60.0 / batches
    span = (window_end - window_start) / batches
    counts = {table: 0 for table in COPY}
    in_window = {}
    conn = config.connect(url, schema=schema)
    admin = config.connect(url, autocommit=True, schema=schema)
    try:
        status = conn.execute("SELECT status FROM load_manifest ORDER BY id DESC LIMIT 1").fetchone()
        conn.commit()
        if not status or status[0] != "complete":
            raise RuntimeError("the latest load is not complete: load first, then replay")
        for table in COPY:
            in_window[table] = conn.execute(f"SELECT count(*) FROM {table} WHERE replay_of IS NULL AND time >= %s AND time <= %s",
                                            [window_start, window_end]).fetchone()[0]
        conn.commit()
        for i in range(batches):
            a = window_start + span * i - (timedelta(microseconds=1) if i == 0 else timedelta(0))   # the first batch includes the start
            b = window_end if i == batches - 1 else window_start + span * (i + 1)
            for table, statement in COPY.items():
                counts[table] += conn.execute(statement, {"shift": shift, "a": a, "b": b}).rowcount
            conn.commit()
            _refresh(admin, a + shift, b + shift)
            if i < batches - 1:
                sleep(pause)
    finally:
        conn.close()
        admin.close()
    # a replayed row that would land exactly on an existing row's key is left out, never written over it
    skipped = {table: in_window[table] - counts[table] for table in COPY}
    return {"rows": counts, "skipped": skipped, "shift_seconds": shift.total_seconds(), "window": [window_start, window_end],
            "lands": [window_start + shift, now], "batches": batches}


def clear(url, schema=None):
    """Remove every replayed row and bring the hourly summaries back to the real data."""
    schema = schema or config.schema_name()
    conn = config.connect(url, schema=schema)
    admin = config.connect(url, autocommit=True, schema=schema)
    try:
        lo, hi = conn.execute("SELECT min(t), max(t) FROM (SELECT time AS t FROM sensor_levels WHERE replay_of IS NOT NULL "
                              "UNION ALL SELECT time FROM camera_readings WHERE replay_of IS NOT NULL) x").fetchone()
        removed = {table: conn.execute(f"DELETE FROM {table} WHERE replay_of IS NOT NULL").rowcount for table in COPY}
        conn.commit()
        if lo is not None:
            _refresh(admin, lo, hi)
    finally:
        conn.close()
        admin.close()
    return removed


def main(argv=None):
    ap = argparse.ArgumentParser(description="Replay a real storm window into the database, labelled as a replay.")
    ap.add_argument("--minutes", type=float, default=10.0, help="how long the replay takes on the clock")
    ap.add_argument("--start", default=None, help="window start, e.g. 2026-09-27T15:00:00Z")
    ap.add_argument("--end", default=None, help="window end, e.g. 2026-09-27T16:00:00Z")
    ap.add_argument("--clear", action="store_true", help="remove every replayed row")
    ap.add_argument("--schema", default=None)
    args = ap.parse_args(argv)

    def when(text, default):
        if not text:
            return default
        t = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if t.tzinfo is None:
            raise SystemExit("times must carry a zone, for example a trailing Z")
        return t
    try:
        url = config.database_url()
        if args.clear:
            print("removed", clear(url, args.schema))
            return 0
        out = replay(url, window_start=when(args.start, DEFAULT_START), window_end=when(args.end, DEFAULT_END),
                     minutes=args.minutes, schema=args.schema)
    except config.ConfigError as e:
        print(e)
        return 2
    except (config.DatabaseUnavailable, psycopg.Error) as e:
        print(config.describe(e))
        return 2
    except RuntimeError as e:
        print(e)
        return 1
    if any(out["skipped"].values()):
        print(f"left out {out['skipped']}: a row already sits at that time")
    print(f"replayed {out['rows']} in {out['batches']} batches; the window now ends at {out['lands'][1]:%Y-%m-%d %H:%M} UTC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
