# Tiger Data database and data service

Status: built and tested on a local TimescaleDB on 2026-10-03. Not yet loaded into the real Tiger Data service (the connection setting was not on the machine and the venue network blocks the service's port). No frontend reads it yet. Living document; the run spec for the first build is `docs/specs/2026-10-03_tiger-dashboard.md` and its plan is `docs/reports/2026-10-03_tiger-dashboard-plan.md`. How to run each command is in `web/tiger/README.md`.

## What it is

The predictions for all 112,443 state road segments, the camera flood readings, the water-level sensor readings and the pothole reports, held in one Tiger Data (Postgres + TimescaleDB) database, with a small read-only service in front of it. It builds no pages.

It serves end goal 1 (a ranked repair list with flood alerts) and end goal 2 (a per-road risk file a map company can download).

## What is in the database

| Table | Rows | What it holds |
|---|---|---|
| `roads` | 112,443 | One row per state road segment: where it is, its 2023 to 2025 rating, NCDOT's recommended treatment and cost, the predictions with their held-out flags, the repair bucket and rank, crash rate, traffic, pothole counts, midpoint and bounding box |
| `road_shapes` | 112,443 | The road's line as GeoJSON text |
| `cameras` | 1,004 | One row per camera: name, position, matched road if any (958 have one), and whether its stills are known dry (993 NCDOT cameras) |
| `camera_readings` | 3,093 | Time-stamped: the flood reader's output per camera frame |
| `sensor_levels` | 12,557 | Time-stamped: water level every 6 minutes at 10 coastal stations, and depth on the road |
| `pothole_reports` | 17,790 | Time-stamped: Charlotte and Raleigh reports, with the matched state road where there is one (3,610) |
| `load_manifest` | one per load | What was loaded: file fingerprints, row counts, code version, compression figures, status |

The three time-stamped tables are TimescaleDB hypertables, split into chunks by time (a day, a day, a year) and compressed once a chunk is old. The other tables are ordinary tables.

Running summaries the database keeps up to date (continuous aggregates, with rows newer than the last refresh included):

| Summary | One row per | Rows | Holds |
|---|---|---|---|
| `camera_hourly` | camera, hour, real or replayed | 1,825 | Worst flood probability, worst predicted depth, worst measured depth, number of readings, first and last reading time |
| `sensor_hourly` | station, hour, real or replayed | 1,200 | Highest and mean level, worst depth on the road, first and last reading time |
| `pothole_monthly` | road, source and month | 2,796 | Number of reports |

The values in the hourly summaries are the worst of the hour, not one reading.

## Rules that keep it honest

- A road's flood risk is blank outside the Helene zone, and the table refuses a value there. The model learned from one storm in western North Carolina.
- A blank years-to-Poor means unknown (1,643 roads), never zero.
- Every prediction carries a held-out flag. True means the model that made it never saw that road.
- A camera flag is a signal to check, not a confirmed flood. On cameras the reader had never seen, 85% of its flags were right; it wrongly flagged 9 of 1,191 NCDOT stills taken on dry roads. Those stills are labelled known dry wherever they appear.
- City streets are not in the database. Only ids starting `ncdot:` are accepted.
- Crash rate is shown and never used in the rank.
- Readings and reports with no matched state road keep a blank road. Nothing is moved to a farther road.
- Not-a-number and infinity cannot be stored: every number column refuses them.
- NCDOT's treatment cost has no documented unit. Traffic is an estimate where marked. Charlotte report times can be up to five hours off.

## The repair buckets

| Bucket | Rule | Roads |
|---|---|---|
| `fix_now` | predicted years to Poor is 0 (the rating is already at or below 60) | 4,432 |
| `within_1y` | above 0 up to 1 | 794 |
| `within_5y` | above 1 up to 5 | 4,699 |
| `later` | above 5 | 100,875 |
| `unknown` | blank | 1,643 |

Rank: bucket, then years to Poor, then rating (lowest first), then predicted wear rate (fastest first), then `seg_id`.

## The data service

All routes are GET and return JSON, except the risk-file download. Blanks are `null`. Times are UTC, ISO 8601 with `Z`. The service's own `/docs` page lists every route and lets you try it.

| Route | Parameters | Returns |
|---|---|---|
| `/api/health` | none | whether the database answers and the latest load's status |
| `/api/summary` | none | bucket counts, totals, the load's status and the fixed caveats |
| `/api/worklist` | `bucket`, `county`, `system`, `in_zone`, `sort`, `direction`, `limit` (at most 500), `offset` | a page of roads, worst first, with a total count |
| `/api/road` | `seg_id` | one road in full, its shape, its monthly pothole counts and any cameras on it |
| `/api/alerts` | `as_of` (a UTC time; defaults to the latest reading), `hours` (2 by default, or 1) | camera flags and sensor alerts for that clock hour and, with `hours=2`, the hour before |
| `/api/alerts/peaks` | `limit` | the hours with the most alerts, known-dry cameras counted separately; ask `/api/alerts` with the row's `as_of` and `hours=1` to see exactly that hour |
| `/api/camera_history` | `camera_id`, `start`, `end` | hourly worst values for one camera |
| `/api/stats` | none | what the database is doing: rows, chunks, compressed bytes before and after, summaries, jobs, size, version |
| `/api/export/risk.csv` | none | the risk file |
| `/api/export/dictionary` | none | what each risk-file column means |

`sort` is one of `rank`, `rating`, `years_to_poor`, `wear_rate`, `crack_risk`, `flood_risk`, `cost`. `seg_id` looks like `ncdot:40002748092:0.940` and always travels as a query parameter.

Replies other than 200:

| Status | Body | When |
|---|---|---|
| 400 | `{"error": "..."}` | a parameter outside what the route accepts |
| 404 | `{"error": "..."}` | no road or camera has that id |
| 503 | `{"error": "loading", "load_status": ...}` | the latest load has not finished, or a load is copying and holds the tables; `/api/health`, `/api/summary` and `/api/stats` still answer and report the status |
| 503 | `{"error": "database unavailable", "kind": "network" or "login" or "unavailable"}` | the database cannot be reached |

One road in `/api/worklist` (the worst-ranked road in the real data, shortened):

```json
{"seg_id": "ncdot:10400095064:11.913", "rank": 1, "bucket": "fix_now", "route": "10400095", "county": "Nash",
 "system": "Interstate", "from": "Ramp 424", "to": "Ramp 424", "length_mi": 0.018, "rating": 8.2, "survey_year": 2025,
 "years_to_poor": 0.0,
 "wear_rate": {"value": -0.118, "heldout": false},
 "crack_risk": {"value": 0.006, "heldout": false},
 "flood_risk": {"value": null, "scored": false, "heldout": false, "note": "not scored: outside the Helene zone"},
 "treatment": "Concrete Reconstruction - 12\" JCP", "treatment_cost": 79474.9152,
 "crash": {"per_million_vehicle_miles": null, "per_mile_year": null, "fatal_10yr": 0, "serious_10yr": 0, "used_in_rank": false},
 "traffic": {"vehicles_per_day": null, "source": "none"}, "mid": [-77.9, 35.9]}
```

`/api/alerts?as_of=2026-09-27T15:30:00Z` returns an envelope and two lists:

```json
{"as_of": "2026-09-27T15:30:00Z", "as_of_was_given": true, "window_start": "2026-09-27T14:00:00Z", "window_hours": 2,
 "live": false, "flag_at": 0.5, "flooded_cm": 2.0, "caveat": "A camera flag is a signal to check, not a confirmed flood. ...",
 "camera_alerts": [...], "sensor_alerts": [...]}
```

`live` is true only when `as_of` is within the last hour of the real clock. One camera alert (shortened); the worst reading and the latest reading each carry their own time:

```json
{"camera_id": "CB_03", "name": "Oystershell Ln.", "lat": 34.0435, "lon": -77.8894, "role": "cv", "known_dry": false,
 "replay": false, "road": null,
 "worst": {"time": "2026-09-27T15:06:00Z", "p_flooded": 0.9997, "depth_pred_cm": 23.1, "depth_measured_cm": 19.3},
 "latest": {"time": "2026-09-27T15:18:00Z", "p_flooded": 0.9997, "depth_pred_cm": 22.9, "depth_measured_cm": 19.0}}
```

With no `as_of` the real data gives only NCDOT stills from 2026-10-03, all labelled known dry. The real floods are 2026-09-24 to 2026-09-28; `/api/alerts/peaks` puts 2026-09-27 15:00 first (7 camera flags and 6 sensor alerts).

## The risk file

`risk_roads.csv`, one row per road, sorted by `seg_id`: 112,443 rows, 20,144,430 bytes. Columns: `seg_id`, `route_id`, `route`, `county`, `beg_mp`, `end_mp`, `from_desc`, `to_desc`, `length_mi`, `mid_lon`, `mid_lat`, `rating`, `survey_year`, `wear_rate_pred`, `wear_rate_heldout`, `years_to_poor`, `repair_bucket`, `crack_risk`, `crack_heldout`, `flood_risk`, `flood_scored`, `flood_heldout`. An empty field means unknown or not scored. The route and mileposts let a map company place a road; a version with road shapes is not built. The download and the file written by `python -m web.tiger.export` are byte-identical.

Whether crash rate belongs in this file is an open question for the user.

## Storm replay

The real readings are from late September, so nothing in the database changes on its own during a demo. `python -m web.tiger.replay` copies the real sensor and camera rows of the storm's peak hour (2026-09-27 15:00 to 16:00 UTC) into the tables with their times shifted to end now, a few at a time. The hourly summaries and `/api/alerts` update as the rows arrive, and the alert reads as live from the first batch. Every replayed row keeps its original time in `replay_of` and is labelled as a replay wherever it appears. Replayed rows never count toward the peak hours or the check command. A replayed row that would land exactly on an existing row's time is left out, never written over it, and the command reports how many it left out. `--clear` removes them.

## Reaching the real database

The venue network blocks the port Tiger services listen on. In order: test the port (`--check`); use a phone hotspot; else load through Tiger's browser console from files the loader writes (`--dump-dir`). The service itself has to run on a host that can reach the database and is reached by a page over 443. Hosting, pushing and the domain need the user's yes.

## Where things are

| Piece | File |
|---|---|
| Connection settings and error handling | `web/tiger/config.py` |
| Files to tables | `web/tiger/build.py` |
| Table and summary definitions | `web/tiger/schema.py` |
| Load | `web/tiger/load.py` |
| Check | `web/tiger/verify.py` |
| Risk file | `web/tiger/export.py` |
| Storm replay | `web/tiger/replay.py` |
| Service | `web/service/app.py`, `web/service/queries.py` |
| How to run | `web/tiger/README.md` |
| Tests | `tests/dashboard/` |
| Dependencies | `web/requirements.txt`, installed in `web/.venv` |

## Results (2026-10-03, local TimescaleDB 2.30.2 on PostgreSQL 17.11)

| Measure | Value |
|---|---|
| Build the tables from the files | 3.1 s |
| Copy into the database | 4.9 s |
| Whole load, with summaries and compression | 8.4 s |
| Check command | 16 of 16 checks passed, about 4 s |
| Database size | 122 MB (`roads` 53 MB, `road_shapes` 41 MB) |
| Service replies | 4 to 81 ms per route; the 20 MB download in 1.5 s |

Compression, read from the database after the load:

| Table | Chunks compressed | Before | After | Ratio |
|---|---|---|---|---|
| `camera_readings` | 5 of 6 | 729,088 bytes | 507,904 bytes | 1.44 |
| `sensor_levels` | 3 of 5 | 1,777,664 bytes | 352,256 bytes | 5.05 |
| `pothole_reports` | 9 of 11 | 3,637,248 bytes | 1,220,608 bytes | 2.98 |

These tables are small, so the saving is a few megabytes; the 112,443 roads and their shapes are ordinary tables and are not compressed. The figures for the real Tiger service will be recorded here when it is loaded.

Tests: 335 in `tests/dashboard`. 206 need no database and pass. 124 need the local database and pass. 5 need the real service; they run only with `TIGER_LIVE_TESTS=1` and have not been run.
