# Plan: Tiger Data database and data service for the repair dashboard (2026-10-03)

Run spec: `docs/specs/2026-10-03_tiger-dashboard.md` (decisions D1 to D21, acceptance criteria AC1 to AC8, test IDs). Branch `tiger-dashboard` at `65162c5`. Mode: deep (three exploration agents, one critique agent, then Codex). The critique's findings and how each was handled are at the end.

Working directory for every command: `/Users/nathanstough/Desktop/Hack-NCSU/.claude/worktrees/tiger-dashboard`. `MAINPY=/Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python`. `py` is a shell function, `py() { PYTHONPATH=web/.venv/lib/python3.11/site-packages "$MAINPY" "$@"; }`, defined at the start of every shell that uses it (a plain variable holding a command and its arguments does not split in zsh). `data/raw`, `data/chips` and `data/processed` are symlinks to the shared folders: never delete or replace them. No `uv sync`, no bare `uv run`, no `git stash`, no `git add -A`; commits name their paths. No credential is printed, logged, committed or pasted. Local test database: `postgresql://postgres@127.0.0.1:55432/postgres` (container `tiger-dashboard-testdb`, trust login on 127.0.0.1 only, so no password exists).

## Grounding (current code and measured behaviour this plan builds on)

- `src/pipeline/pothole_labels.py:34` `CRS_M = "EPSG:32119"`; `:37` `MATCH_M = {"charlotte": 60, "raleigh": 30}` (a report whose `source` is anything else raises `KeyError`); `:58` `match_reports(reports_m, segs_m)` returns `report_id, seg_id, dist_m`, one row per matched report; `:115` `main()` reads `data/raw/ncdot_joined.parquet` (`seg_id, YEAR_LAST_REHAB, geometry`), converts both inputs to `CRS_M` and calls `match_reports`. Run read-only on 2026-10-03: 3,610 matches, per-road counts equal `n_pothole_all_time` for all 112,443 roads.
- `src/pipeline/pull_potholes.py:116` `read_bundle(raw)` returns `(reports, city_limits, meta)` and raises when a file's sha256 differs from `meta["sha256"]`; `:50` `sha256_file(path)`.
- `src/model/common.py:96` `write_atomic(path, write)`. That module imports numpy, pandas, scipy and scikit-learn at the top, so nothing the service imports may import it. `:19-21` `RATE_FLOOR = 0.1`, `YEARS_CAP = 50`, `POOR = 60`.
- `src/model/final_ablation.py:97` builds `pred_years_to_poor` (blank where the rating is 0 or older than the last resurfacing); `:13` `SIMPLIFY_M = 3`.
- `src/pipeline/sunnyday.py:129` `read_station(sid)` returns `(meta, levels)` with `level_time`, `level_m` from the first `water_level_raw` series of `OUT / "levels" / f"{sid}.json"`; only values are coerced, so a time that does not parse raises. `:33` `OUT`; `:46` `ROAD_LEVEL_M`; `:50` `ALWAYS_DRY = {"DE_02", "NB_02"}`; `:51` `LEVEL_FROM = {"CB_01B": "CB_01"}`; `:187-189` the depth rule `((level_m - road) * 100).clip(lower=0)`, 0 for always-dry stations. Run read-only: 12,557 rows, 10 stations, no repeated times, nothing dropped.
- `src/model/flood_camera.py:41` `FLOODED_CM = 2.0`. That module imports PyTorch, so the constant is copied, not imported, and a test reads the source line to keep the copy honest. A camera flag is `p_flooded >= 0.5`.
- `tests/test_repo_guards.py:18` (G4) is the pattern for "importing X in a fresh process does not load LightGBM". `tests/potholes/test_pothole_guards.py:11` `NOT_OURS` and `:36` (R3) are the pattern for "this branch did not change file X", using `git merge-base HEAD main`.
- `pyproject.toml:37-43`: `testpaths = ["tests"]`, `pythonpath = ["."]`, markers `realdata` and `network`; no strict markers. There is no `tests/__init__.py`, so test file names must be unique across all test folders. `tests/conftest.py` imports geopandas, pandas and `src.model.common` for every test; its `make_table` lacks most columns this change needs.
- `.gitignore:2` `data/raw/*`, `:11` `.venv/`, `:16` `data/processed/`. `web/.venv` is ignored; `web/out`, `.env` and `web/.env` are not. `git check-ignore data/raw/tiger.env` fails in the worktree ("beyond a symbolic link").
- Data facts are in the run spec's "Facts measured". Extra facts measured for this plan: `flood_camera_depth.parquet` has 1,004 cameras when the camera is `station`, or `site` where `station == "NCDOT"`; name, position, road and role are constant per camera; `(camera, time)` is unique. Flagged cameras per hour peak at 8 on 2026-09-27 15:00 (real) and 8 on 2026-10-03 20:00 (all known-dry NCDOT stills). The README's example road is `ncdot:40002748092:0.940` (`pred_rate` 1.623395, `pred_years_to_poor` 8.254305). `pv_RTG_NBR == 0` on 3 rows and `pv_NUMBER_OF_LANES == 0` on 5 rows mean missing. `pv_TREATMENT_COST == 0` on 8 rows is real. `segments.parquet` has both `y_helene_failed` (1,266 in the zone, the spec's number) and `y_helene_damage` (1,062); only the first is used. All 112,443 ids match `^ncdot:[0-9A-Za-z]+:[0-9]+\.[0-9]{3}$`.
- Local TimescaleDB 2.30.2, run on 2026-10-03 (by this chat and again by the critique agent):
  - The extension lives in schema `public`. With `search_path` set to another schema alone, `time_bucket` and every policy function are "not found". The path must be `<schema>, public`.
  - `CREATE TABLE ... WITH (tsdb.hypertable, tsdb.partition_column, tsdb.chunk_interval, tsdb.segmentby, tsdb.orderby)` works with `IF NOT EXISTS`, turns columnstore on, and adds a columnstore policy whose first run is a day later (`compress_after` equal to the chunk interval for a one-day table, 360 days for a one-year table).
  - A policy added by hand runs at once unless it is given `initial_start`. With `initial_start` in the future, `add_continuous_aggregate_policy` and `add_columnstore_policy` did not run (0 runs, 0 compressed chunks).
  - A continuous aggregate can be created inside a transaction only `WITH NO DATA`; `CREATE MATERIALIZED VIEW IF NOT EXISTS` works; real-time aggregation needs `timescaledb.materialized_only = false`; `refresh_continuous_aggregate` cannot run inside a transaction block; grouping by a column that is not the segment-by column works; `time_bucket(INTERVAL '1 month', time, 'UTC')` works; rows with a blank group column are kept.
  - `convert_to_columnstore` is a procedure, called once per chunk from `show_chunks(table, older_than => <time>)`. `hypertable_columnstore_stats` returns blanks when nothing is compressed.
  - One `TRUNCATE` naming hypertables and plain tables with a foreign key works in a transaction and rolls back. The summary shows old rows until refreshed with `(NULL, NULL)`.
  - `CHECK (c <> 'NaN' AND c < 'Infinity' AND c > '-Infinity')` refuses not-a-number and infinity and accepts NULL. A one-sided check such as `c >= 0` accepts not-a-number.
  - `text COLLATE "C"` orders ids as Python does. A time without a zone is shifted by the session's time zone. `SET default_transaction_read_only = on` refuses writes. `alter_job(job_id, scheduled => false)` pauses a job. `DROP SCHEMA ... CASCADE` removes hypertables, summaries and jobs.
  - Building all shapes as GeoJSON at 6 decimals takes under a second and gives about 29 MB.

## Step 0. Pre-flight

1. `git branch --show-current` prints `tiger-dashboard`; `pwd` is the worktree; `git status --short` lists only this change's files. Stop if not.
2. Send the coordination chat this change's file list (run spec "What will change") and the note that it writes new files only under `data/processed/export/`.
3. Fingerprints: `shasum -a 256` of every source file in step 3's `SOURCES`, saved to the scratchpad as `sources_before.txt` (for S4 and AC7).
4. Baseline: `$MAINPY -m pytest tests -q -m "not network" --ignore=tests/vision --ignore=tests/potholes --ignore=tests/cctv --ignore=tests/crashes` must print `89 passed`. If the count differs before any change, record it and use the recorded count as the baseline.
5. `docker ps --filter name=tiger-dashboard-testdb` shows the container up; if not, `colima start` then `docker start tiger-dashboard-testdb`.
6. `df -h /System/Volumes/Data`: stop and report if under 5 GB is free.

## Step 1. Environment (`web/requirements.txt`, `web/.venv`)

- `web/requirements.txt`: `psycopg[binary]>=3.2`, `psycopg-pool>=3.2`, `fastapi>=0.115`, `uvicorn>=0.30`, `httpx>=0.27` (tests only, marked by a comment).
- `uv venv web/.venv --python $MAINPY`, then `uv pip install --python web/.venv/bin/python -r web/requirements.txt`. Neither command touches `pyproject.toml` or `uv.lock` (checked by S5).
- Check: `py -c "import psycopg, psycopg_pool, fastapi, httpx, pandas; print(psycopg.__version__)"` and `web/.venv/bin/python -c "import psycopg, fastapi"`. `git status --short` must not list anything under `web/.venv`.
- Known side effect: with `py`, the copies of pydantic, anyio, typing-extensions, idna and certifi in `web/.venv` come before the main environment's. Only the dashboard tests and tools run that way; the base suite runs with `$MAINPY` alone.
- If the driver does not import under `py`, fall back to `uv run --no-project --with-requirements web/requirements.txt --python $MAINPY` and record it as a deviation.

## Step 2. `web/__init__.py`, `web/tiger/__init__.py` (both empty), `web/tiger/config.py` (new); `tests/dashboard/conftest.py`, `test_dash_secrets.py`

`config.py` (imports only the standard library and psycopg):
- `ENV_KEY = "TIGER_DATABASE_URL"`, `ENV_FILE = Path("data/raw/tiger.env")`, `SCHEMA_KEY = "TIGER_SCHEMA"` (default `unwatched`).
- `read_env_file(path)`: `KEY=VALUE` lines, `#` comments, surrounding quotes stripped. `database_url(env=os.environ, env_file=ENV_FILE)`: the environment wins, then the file; missing or empty raises `ConfigError("TIGER_DATABASE_URL is not set (environment or data/raw/tiger.env)")`. No default.
- `class DatabaseUnavailable(Exception)` with `kind` in `network | login | unavailable` and a fixed message per kind. `classify(exc)`: a timeout or refused connection gives `network`; sqlstate `28P01` or `28000` gives `login`; anything else `unavailable`. `str(exc)` of the driver error is never used.
- `connect(url, *, autocommit=False, read_only=False, connect_timeout=5, statement_timeout_ms=None, schema=None)`: opens the connection, then runs `SET TIME ZONE 'UTC'`, the read-only and time-limit settings, and `SET search_path = <schema>, <extension schema>` where the extension schema is read from `pg_extension` (`public` locally); driver errors are re-raised as `DatabaseUnavailable` `from None`.
- `require_local(url)`: parses with `psycopg.conninfo.conninfo_to_dict`, so the query string is included, and raises unless every `host` is `localhost`, `127.0.0.1`, `::1` or a socket path, every `hostaddr` (when given) is a loopback address, and no `service` or `passfile` is named. `assert_local(conn)`: after connecting and before any change, raises unless `conn.info.hostaddr` is a loopback address or the connection is a socket.
- `reachability(url, timeout=5)`: returns `ok`, `network` or `login`.
- `probe(conn)`: TimescaleDB version and schema, `pg_available_extensions` for `postgis` and `vector`, `max_connections`, `pg_database_size`.
- `try_features(conn)`: in a schema `probe_<8 hex>` that it drops in a `finally`: one hypertable with the step 5 create syntax, twenty rows, one continuous aggregate `WITH NO DATA` with real-time on, one refresh, one refresh policy with a future `initial_start`, one `convert_to_columnstore`, one read of `hypertable_columnstore_stats`. Returns which of those the service accepted.
- CLI: `python -m web.tiger.config --check` prints only `ok`, `network` or `login`; `--probe` prints the probe and the feature results. Neither prints the address.

`tests/dashboard/conftest.py`:
- At the top: if `psycopg` or `fastapi` cannot be imported, `collect_ignore_glob = ["test_dash_*.py"]`, so a plain `pytest` from another chat's environment collects nothing here and its counts do not move.
- `pytest_configure` registers the `db` marker.
- `fake_url(password="pw-marker")`: builds a database address by joining pieces, so no tracked file contains one whole.
- `db_url` (session): `TIGER_TEST_DATABASE_URL` or the local container address; deletes every `PG*` variable; calls `require_local` unless `TIGER_TEST_ALLOW_REMOTE=1`; connects, calls `assert_local`, skips with the reason "local test database is not running (see web/README.md)" when the connection is refused. It never drops a schema it did not create: there is no automatic sweep of old `test_` schemas, because age does not show that another session has finished. Each fixture drops its own schema in a `finally`; `web/README.md` gives the manual command for clearing leftovers.
- `fixture_root` (session, read-only): a small folder with the real layout and about 300 roads, built by helper functions in the conftest (about an hour of work; the list of what each file needs is in the critique section, finding 9). Planted cases: blank years, a blank cost, a zero cost, a zero rating, roads outside the zone with a flood score, readings without a road, two cameras sharing a site, known-dry stills, an always-dry station, a station without a sensor, a sensor value that does not parse, reports with and without a road from both cities, and a road description holding a tab, a quote and a backslash. Its pothole labels come from the real `match_reports` on the fixture reports; its report manifest's sha256 values are computed from the fixture files.
- `sunnyday_out(root)`: a context manager using `pytest.MonkeyPatch.context()` that points `src.pipeline.sunnyday.OUT` at a folder for the length of one build or load. It is never left in place, because real-data tests in the same session need the real folder.
- `new_schema(db_url)`: returns a fresh `test_<12 hex>` name. `loaded_schema` (module, `db`, read-only by convention): loaded from `fixture_root` with jobs paused; dropped in a `finally`. `fresh_schema` (function, `db`): the same, for tests that change data. `real_schema` (session, `db` and `realdata`, read-only): one load of the real files.

`test_dash_secrets.py`, the tests whose code exists at this step: S1 (the grep of tracked files for `postgres(ql)?://[^\s:@/]+:[^\s@/]+@`, and the `data/raw/*` rule read from `.gitignore`), S2's config half (a failed `connect` to a closed port on 127.0.0.1 with `fake_url` gives a `DatabaseUnavailable` whose text has neither the marker password, the user nor the port), S3's config half, S5 (`git diff --quiet main -- pyproject.toml uv.lock`), S8 (including an address with `host=localhost` and a remote `hostaddr`, refused before any connection is made), S11 (starting a test session leaves an existing `test_` schema alone), S9 (the R3 pattern with `NOT_OURS` = `src/`, `pyproject.toml`, `uv.lock`, `.gitignore`, `README.md`, `handoff/`, `tests/conftest.py`, `tests/test_*.py`, and the four other test folders).

Run: `py -m pytest tests/dashboard/test_dash_secrets.py -q`.

## Step 2b. Probe the real service as early as possible

Needs `TIGER_DATABASE_URL` in `data/raw/tiger.env`, which the user fills in. That folder is shared, so every chat on this Mac can read the file; the user is told this when asked. If the file is absent, go on with step 3 and come back here at each later step boundary.

1. `py -m web.tiger.config --check`. Tell the user at once if the answer is `network` or `login`.
2. If `ok`: `py -m web.tiger.config --probe` and record the output for L4. A feature the service refuses is reported to the user before more is built on it.
3. If `network`: ask the user for a phone hotspot and retry. If there is none, try the browser console with the user (over 443): in the SQL editor, the statements of `try_features` one at a time, and the file import with a one-row CSV. What works there decides whether step 11's console path is usable.

## Step 3. `web/tiger/schema.py` (column lists only) and `web/tiger/build.py` (roads), with `test_dash_roads.py`

`schema.py` first holds only the column specifications, as ordered lists of `(name, sql_type, extra_check)`: `ROADS`, `ROAD_SHAPES`, `CAMERAS`, `CAMERA_READINGS`, `SENSOR_LEVELS`, `POTHOLE_REPORTS`. `columns(table)` returns the names. Every id column is `text COLLATE "C"`. Every `double precision` column gets `CHECK (c <> 'NaN' AND c < 'Infinity' AND c > '-Infinity')`, with any range check added on top.

`build.py` (pandas, geopandas, pyproj; never imported by the service):
- `SOURCES`: logical name to relative path for every file read. `fingerprints(root)`: `{path: {"sha256", "bytes"}}` via `sha256_file`, including each sensor file.
- `same_ids(left, right, name)`: raises when either side has a duplicated `seg_id` or the two id sets differ (R1, R2).
- `repair_bucket(years)`: vectorised D5 rule. `RANK_KEYS = ("bucket_order", "pred_years_to_poor", "rating", "-pred_rate", "seg_id")`; `rank(d)` sorts by them with blanks last and returns 1..N (R4, R12).
- `build_roads(root)`: reads the four per-road files, checks `same_ids` on each, and maps columns exactly as follows.

| `roads` column | Source | Rule |
|---|---|---|
| `seg_id` | `predictions_geo.seg_id` | must start `ncdot:` |
| `route_id`, `route` | `segments.pv_ROUTEID`, `pv_ROUTE` | |
| `county_code`, `county` | `segments.pv_COUNTY` | `"092-Wake"` split at the first dash |
| `beg_mp`, `end_mp`, `from_desc`, `to_desc` | `pv_BEG_MP`, `pv_END_MP`, `pv_FROM_DESC`, `pv_TO_DESC` | |
| `length_mi`, `system`, `division` | `pv_LENGTH`, `pv_NC_SYSTEM_CODE`, `pv_DIVISION` | |
| `lanes` | `pv_NUMBER_OF_LANES` | 0 becomes blank |
| `rating` | `pv_RTG_NBR` | 0 becomes blank |
| `survey_year`, `last_rehab_year`, `last_rehab_type` | `pv_PCS_SRVY_YR`, `pv_YEAR_LAST_REHAB`, `pv_LAST_REHAB_TYPE` | |
| `treatment`, `treatment_cost` | `pv_PMS_TREATMENT_NAME`, `pv_TREATMENT_COST` | blank cost stays blank; a real 0 stays 0 |
| `pred_rate`, `pred_years_to_poor`, `pred_crack` | `predictions_geo` | |
| `pred_flood` | `predictions_geo.pred_flood` | blank where `in_helene_zone != 1` |
| `flood_scored`, `in_helene_zone` | `predictions_geo.in_helene_zone == 1` | must equal `segments.in_helene_zone` |
| `rate_heldout`, `crack_heldout`, `flood_heldout` | `predictions_geo` | |
| `helene_damaged` | `segments.y_helene_failed == 1` | not `y_helene_damage` |
| `repair_bucket`, `priority_rank` | computed | D5 |
| `crash_per_mvm`, `crash_per_mile_year`, `crash_cover` | `traffic_crash.cr_crash_per_mvm`, `cr_crash_per_mi_yr`, `cr_cover` | float32 to float64, rounded to 3 decimals |
| `fatal_10yr`, `serious_10yr`, `ncdot_safety_score` | `cr_fatal_10yr`, `cr_serious_10yr`, `cr_ncdot_score` | |
| `aadt_best`, `aadt_source` | `tr_aadt_best`, `tr_aadt_best_source` | |
| `pothole_city`, `potholes_all_time`, `potholes_in_window` | `pothole_labels.pothole_city`, `n_pothole_all_time`, `n_pothole_reports` | |
| `mid_lon`, `mid_lat` | `segments.mid_x`, `mid_y` | EPSG:32119 to EPSG:4326 with pyproj |
| `min_lon`, `min_lat`, `max_lon`, `max_lat` | `predictions_geo.geometry` | bounds |

  Refusals: an id not starting `ncdot:`; infinity in any float; a column list different from `schema.columns("roads")`.
- `build_road_shapes(root)`: `seg_id`, `geojson` (coordinates rounded to 6 decimals, fixed key order).
- `to_rows(df, columns)`: selects the columns by name, yields tuples; `pd.isna` becomes `None`; numpy scalars become Python values; a time without a zone raises; infinity raises (S7, R7, R11).

`test_dash_roads.py`: R1 to R12 and S7. R11 checks the built column names and order against `schema.columns("roads")` and that `to_rows` on a frame with shuffled columns yields the same tuples. R12 checks that no rank key names a crash column and that a table whose crash rate runs opposite to the rank sorts the same as one with the crash column shuffled. Fixture-based tests run on `fixture_root`; the real counts (R1, R3 to R6, R8, R10) are `realdata` tests on the shared files.

Run: `py -m pytest tests/dashboard/test_dash_roads.py -q`.

## Step 4. `web/tiger/build.py` (time-stamped tables), with `test_dash_streams.py`

- `build_cameras(root)` and `build_camera_readings(root)` from `flood_camera_depth.parquet`. `camera_id` is `station`, or `site` where `station == "NCDOT"`. `cameras`: one row per camera (`camera_id`, `site`, `station`, `name`, `lat`, `lon`, `seg_id`, `seg_dist_m`, `role`, `known_dry` = role is `extra`); refuses when any of those differs within a camera. Readings: `time` (`time_utc` localised to UTC), `camera_id`, `site`, `p_flooded`, `depth_pred_cm`, `depth_measured_cm`, `file`, `run`, `replay_of` (blank). Refuses a probability outside 0 to 1, a negative depth, a repeated `(site, time, file)`, and zero rows (T1 to T5, T12).
- `build_sensor_levels(root)`: refuses unless `(root / "data/raw/sunnyday").resolve()` equals `sunnyday.OUT.resolve()`, then calls `sunnyday.read_station(sid)` for every `levels/*.json`. Columns: `time` (UTC), `station`, `name`, `lat`, `lon`, `level_m`, `road_level_m`, `depth_on_road_cm` (the rule at `sunnyday.py:187-189`), `replay_of` (blank). Returns beside the table the number of values the reader dropped (the file's series length minus the rows) (T9, T10, T11).
- `build_pothole_reports(root)`: `read_bundle`, the `main()` call sequence, a left merge of the matches onto the reports, `time` = `received_date` localised to UTC, `lon`, `lat`, `seg_id` and `dist_m` blank when unmatched. Refuses when per-road counts differ from `n_pothole_all_time` (T6 to T8).
- `build_all(root, _after_read=None)`: takes `fingerprints(root)`, builds every table, takes the fingerprints again and raises if any file changed in between, so the manifest always describes the bytes that were read. Returns the tables, the fingerprints and the counts. `_after_read` is a hook for T13 only.

`test_dash_streams.py`: T1 to T13. T13 replaces a source file through the hook while the build runs and expects a refusal. T10 plants a value that does not parse in a fixture sensor file and expects one dropped and counted; on the real files the dropped count is 0. Fixture builds run inside `sunnyday_out(fixture_root)`. The real counts are `realdata` tests.

Run: `py -m pytest tests/dashboard/test_dash_streams.py -q`.

## Step 5. `web/tiger/schema.py` (statements), `web/tiger/load.py` (new), with `test_dash_db.py`

`schema.py` gains:
- `SetupRefused`, raised with a plain message when `probe` shows no TimescaleDB or a version under 2.20, or when a statement is refused (D14).
- `statements(schema)`: an ordered list, each safe to run twice:
  - `CREATE SCHEMA IF NOT EXISTS`.
  - `roads`, `road_shapes` (`seg_id` references `roads`), `cameras`, `load_manifest` (`id` identity, `started_at`, `finished_at`, `status`, `sources jsonb`, `row_counts jsonb`, `compression jsonb`, `code_version`, `timescaledb_version`), all `CREATE TABLE IF NOT EXISTS`, with `CREATE INDEX IF NOT EXISTS` on `roads (repair_bucket, priority_rank)` and `roads (county)`.
  - The three hypertables with `WITH (tsdb.hypertable, tsdb.partition_column = 'time', tsdb.chunk_interval = ..., tsdb.segmentby = ..., tsdb.orderby = 'time DESC')`: `camera_readings` (`'1 day'`, `site`, `UNIQUE (site, time, file)`), `sensor_levels` (`'1 day'`, `station`, `UNIQUE (station, time)`), `pothole_reports` (`'1 year'`, `source`, `UNIQUE (report_id, time)`). The columnstore policy each create adds is kept as it is (first run a day later); none is added by hand.
  - Three continuous aggregates, `CREATE MATERIALIZED VIEW IF NOT EXISTS ... WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS ... WITH NO DATA`: `camera_hourly` (grouped by `time_bucket(INTERVAL '1 hour', time)`, `camera_id` and `is_replay` = `replay_of IS NOT NULL`; worst `p_flooded`, worst `depth_pred_cm`, worst `depth_measured_cm`, readings, first and last reading time), `sensor_hourly` (grouped by hour, `station` and `is_replay`; highest and mean `level_m`, worst `depth_on_road_cm`, readings, first and last reading time). Grouping by `is_replay` keeps real and replayed rows of one camera and hour in separate summary rows, so either can be left out without touching the other. The columns are named as hourly worst values; they are not one reading. Then `pothole_monthly` (`time_bucket(INTERVAL '1 month', time, 'UTC')`, `seg_id`, `source`; reports).
  - Refresh policies with a first run in the future, so adding them starts nothing: `SELECT add_continuous_aggregate_policy(view, start_offset => NULL, end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '30 minutes', initial_start => now() + INTERVAL '30 minutes', if_not_exists => true)` (`'1 month'` and `'1 day'` for the monthly view).
- `setup(conn, schema, schedule_jobs=True)`: needs an autocommit connection (raises otherwise); sets the search path to `<schema>, <extension schema>`; runs `probe` then the statements; with `schedule_jobs=False` runs `alter_job(job_id, scheduled => false)` for the schema's jobs.

`load.py`:
- `load(url, root=Path("."), schema=None, *, schedule_jobs=True, compress=True, stop_after=None)`:
  1. `tables = build.build_all(root)` (all refusals happen before the database is touched).
  2. Autocommit connection: `setup`.
  3. Transaction connection: one `TRUNCATE` naming all six data tables; `COPY <table> (<columns>) FROM STDIN` per table with `cursor.copy(...)` and `copy.write_row` over `to_rows`; `INSERT INTO load_manifest` with status `loaded`. Commit. An exception anywhere rolls back.
  4. Autocommit: `CALL refresh_continuous_aggregate(view, NULL, NULL)` for the three views.
  5. Autocommit, when `compress`: for each hypertable, `SELECT show_chunks(table, older_than => <latest time in the table minus one chunk interval>)` then `CALL convert_to_columnstore(chunk, if_not_columnstore => true)` per chunk; read `hypertable_columnstore_stats(table)`.
  6. `UPDATE load_manifest SET status = 'complete', finished_at = now(), compression = ...`.
  `stop_after` in `{"copy", "refresh_one", "refresh"}` exists only so D4 and A16 can stop a load at a known point (after the copy, after the first summary's refresh, after all three).
- `dump(root, out_dir)`: per-table CSV files (header, empty field for blank, times as ISO with `+00:00`), `setup.sql` (the statements) and `after_load.sql` (each refresh as its own statement, a `DO` block converting chunks, the manifest row). Built only if step 2b shows the console path is needed and usable.
- CLI: `python -m web.tiger.load [--schema S] [--dump-dir DIR]`; prints row counts, timings, the compression figures and the manifest status, never the address.

`test_dash_db.py` (all `db`): D1, D2, D2b, D3, D3b, D4, D5, D6, D7, D9 to D15, and S4. Tests that change data (D3, D4, D12, D13) use `fresh_schema`; the rest read `loaded_schema` or `real_schema`. D2b compares `(proc_name, hypertable_name, config)` of the schema's jobs with the expected list, not job ids. D4: `stop_after="copy"` and `stop_after="refresh_one"` leave status `loaded`; a further case makes the fourth table's rows raise mid-copy and checks the counts are those of the earlier load. D12 inserts a reading one hour after the latest time and reads the summary without a refresh. D13 loads with `compress=False`, asserts zero compressed chunks and saves three query answers, then converts and compares. D15 reads `SELECT seg_id FROM roads ORDER BY seg_id` from `real_schema` and compares with `sorted()`.

Added to `test_dash_secrets.py` here: S3's loader half, S4, and S10 (the load CLI run in a fresh process, once against a closed local port and once against the local database, with a marker password in the address; the captured output contains neither the marker nor the user name).

Run: `py -m pytest tests/dashboard -q -m db -k "dash_db or S4 or S10"`.

## Step 6. `web/tiger/verify.py` (new), with D8 and `test_dash_live.py`

- `checks(conn, schema, root)` returns `(name, ok, detail)` rows, in this order: manifest status is `complete`; manifest fingerprints equal `fingerprints(root)`, and on a mismatch the check names the file and the later checks that need a rebuild are skipped with that reason; the four row counts; NULL counts (years, cost); bucket counts; held-out counts; Helene numbers; earliest and latest time per table; each summary equals a pandas recompute from the built tables (merged with blanks kept, totals compared). Replay rows are left out of every one of these: the counts and time ranges read `replay_of IS NULL`, and the summary comparisons read `NOT is_replay`; at least one compressed chunk per hypertable; 200 seeded random roads plus `ncdot:40002748092:0.940` equal the built table.
- CLI: `python -m web.tiger.verify [--schema S]`; prints one line per check and exits 1 on any failure, 2 on a connection failure with the kind (`network` or `login`). It also prints how many replay rows are present.
- D8 (in `test_dash_db.py`): copy `fixture_root` to a new folder, load from the copy, change one byte of a source file in the copy, run verify: it fails and names the file.
- `test_dash_live.py` (all `network`): L1 (`reachability` against the real address tells `network` from `login`; the unit half, with a closed local port and a wrong local login, is a normal test in `test_dash_secrets.py`), L2 (verify exits 0 against Tiger), L4 (the probe output is recorded), L3 and L5 skip with the reason "needs the user's yes on hosting" until a `DASHBOARD_URL` variable is set.

Run: `py -m pytest tests/dashboard -q -m db -k D8`.

## Step 7. `web/tiger/export.py` (new), with `test_dash_export.py`

`export.py` imports only the standard library at the top; pandas is imported inside `rows_from_frame` and the CLI, so the service can import the writer.
- `RISK_COLUMNS`: ordered `(name, description, unit)`: `seg_id`, `route_id`, `route`, `county`, `beg_mp`, `end_mp`, `from_desc`, `to_desc`, `length_mi`, `mid_lon`, `mid_lat`, `rating`, `survey_year`, `wear_rate_pred`, `wear_rate_heldout`, `years_to_poor`, `repair_bucket`, `crack_risk`, `crack_heldout`, `flood_risk`, `flood_scored`, `flood_heldout`. Crash rate is left out: whether it belongs in the risk file is an open question for the user. `dictionary()` returns the columns plus the D18 caveats.
- `format_value(v)`: `None` gives an empty field; booleans `true` or `false`; floats `repr(round(v, 6))`; integers plain.
- `iter_risk_csv(rows, batch=2000)`: the one writer. It yields encoded byte chunks (header first), formatting with `csv.writer` and `lineterminator="\n"` over an iterator of tuples in `RISK_COLUMNS` order. `write_risk_csv(rows, fh)` writes those chunks to a file. The download streams the same chunks.
- `rows_from_frame(roads)`: sorted by `seg_id` with Python's plain string order.
- `atomic(path, write)`: its own few lines (temporary name, `os.replace`, and the temporary file removed when `write` raises). It does not import `src.model.common` (E7).
- CLI: `python -m web.tiger.export [--out data/processed/export]` writes `risk_roads.csv` and `risk_dictionary.json` from the built tables; no database needed.

`test_dash_export.py`: E1 to E7. E4 compares the written header with a list typed out in the test, and checks every column has a description. E8 is added in step 8.

Run: `py -m pytest tests/dashboard/test_dash_export.py -q`.

## Step 8. `web/service/__init__.py`, `queries.py`, `app.py` (new), with `test_dash_service.py`

`queries.py` (SQL text constants and one function per route; every value is a bound parameter; identifiers come only from fixed dictionaries):
- `SORTS` and `FILTERS` dictionaries; `worklist(conn, *, bucket, county, system, in_zone, limit, offset, sort, direction)` always ends `ORDER BY <sort>, seg_id`; `limit = min(limit, 500)`.
- `summary`; `road` (road row, shape, monthly pothole counts from `pothole_monthly`, cameras on the road with their latest hour from `camera_hourly`); `alerts(conn, as_of, now)` (camera flags from `camera_hourly` joined to `cameras` and, where the camera has a road, to `roads` for its rating and bucket; sensor alerts from `sensor_hourly` at `FLOODED_CM`; each item says whether it is a replay; the summary picks which cameras and stations are listed, and for those few a lookup in the raw table gives the worst reading with its own time and the latest reading with its own time, so a peak value is never shown with another reading's time, and a camera that flagged early in the hour and is dry now shows both); `alert_peaks(conn, limit)` (hours ranked by sensor alerts plus camera flags from cameras not marked known dry, with the known-dry count shown separately; only `NOT is_replay` summary rows are read); `camera_history`; `stats` (per hypertable: rows, chunks, compressed chunks, before and after bytes, ratio or null; summaries with their row counts and real-time setting; jobs; database size; TimescaleDB version; the latest manifest); `risk_rows(conn)` (a server-side cursor, `ORDER BY seg_id`); `manifest_status(conn)`.

`app.py`:
- `create_app(pool=None, *, clock=None, settings=None)`. `settings` holds `connect_timeout` (5), the pool wait (5), `statement_timeout_ms` (8000), `lock_timeout_ms` (3000), `allowed_origins`, `schema`.
- Lifespan: when no pool is passed, `database_url()` (a missing key stops the start and names it) and `pool = psycopg_pool.ConnectionPool(url, min_size=1, max_size=4, timeout=settings.pool_wait, kwargs={"connect_timeout": settings.connect_timeout}, configure=configure, open=False)`, then `pool.open(wait=False)`, and `pool.close()` on shutdown. (`wait` belongs to `open()`, not to the constructor.) `configure(conn)` runs `SET default_transaction_read_only = on`, the two time limits, `SET TIME ZONE 'UTC'`, `SET search_path = <schema>, <extension schema>`, then commits.
- `respond(data)`: converts non-finite floats to `None`, `Decimal` to float, times to ISO with `Z`; `json.dumps(..., allow_nan=False)`.
- Routes: the ten GET routes of D13. `seg_id` is validated against `^ncdot:[0-9A-Za-z]+:[0-9]+\.[0-9]{3}$` (400 when malformed, 404 when unknown). `as_of` must parse as a time with a zone or `Z`. The download: the route takes a connection from the pool, opens the read transaction, checks the loading guard and executes the server-side cursor before any header is sent, so a failure at that point is a normal 503. It then returns a `StreamingResponse` (with a `Content-Disposition` file name) over a generator that yields `export.iter_risk_csv(rows)` and, in a `finally`, closes the cursor, ends the transaction and gives the connection back to the pool. That `finally` also runs when the client disconnects or a row fails part-way. FastAPI's `/docs` page stays on as the stand-in page while no frontend is wired.
- Logging: the pool's background workers log failed connections with the driver's text, which names the host, port and user. A filter on the `psycopg.pool` and `psycopg` loggers replaces each such record's message with the fixed text for its kind and drops the exception text.
- Loading guard: every route except `/api/health`, `/api/summary` and `/api/stats` runs inside one `REPEATABLE READ, READ ONLY` transaction that first reads the latest `load_manifest` status; unless it is `complete` the route returns 503 `{"error": "loading"}`. The query then runs in that same transaction, so a reply never mixes two loads. The three exempt routes report the status.
- Errors: `DatabaseUnavailable`, any `psycopg.Error` and `PoolTimeout` give 503 `{"error": "database unavailable", "kind": ...}`; nothing from the driver's text is returned. Any other method than GET gives 405.
- CORS middleware: `allowed_origins` when set, else `*`; `allow_credentials=False`; methods `GET` only.
- `app = create_app()` at module level does not connect or read configuration; the lifespan does.
- Start command (documented in `web/README.md`): `web/.venv/bin/uvicorn web.service.app:app --host 0.0.0.0 --port 8000 --workers 1`.

`test_dash_service.py`: A1 to A16 with `fastapi.testclient.TestClient`. Tests that need SQL use `loaded_schema` or `real_schema` (`db`). The client is used as a context manager so the lifespan and the real pool run. A9 passes a fixed clock; a second case checks that with no `as_of` the reply's "as of" is the latest reading in the database; a third plants an early flag followed by a later dry reading in one hour and expects the worst reading with the early time and the latest reading with the later time. A16 runs `/api/road`, `/api/alerts` and `/api/worklist` against a load stopped after the copy and one stopped after the first refresh and expects the loading reply, while `/api/summary` reports the status. A17: a database failure before the first byte of the download gives a 503; a row that raises part-way, and a client that stops reading, both leave no connection checked out of the pool. A12 uses a closed local port and settings with a 1 second limit, and asserts a 503 in under 2 seconds with no host, user or port in the body. A14's second half takes a connection from the service's pool and attempts an `INSERT`, expecting the database's read-only refusal. A7 walks every route and parses the body with a parser that raises on `NaN` and `Infinity`; a unit case feeds `respond` a not-a-number and an infinity.

Added elsewhere here: E8 in `test_dash_export.py` (`db`: the download equals the file written from the same data); in `test_dash_secrets.py`, S2's service half, S3's service half, S10's service half (the real service started in a fresh process against a closed local port and against the local database with a user that does not exist; the captured output, background pool logs included, and the replies contain neither the marker password, the user name, the host nor the port), and S6 (two fresh processes: `py` importing `web.tiger.build` and `web.tiger.load` loads neither `lightgbm` nor `torch`; `web/.venv/bin/python` importing `web.service.app` succeeds and does not load `pandas`), and a check that `FLOODED_CM` in `queries.py` equals the value on the source line of `src/model/flood_camera.py`.

Run: `py -m pytest tests/dashboard -q` then with `-m db`.

## Step 9. `web/tiger/replay.py` (new): a labelled storm replay, so the database visibly updates

This step is an addition made on the critique's advice (run spec D21). It is the only part of the plan that shows the summaries and the alert updating while someone watches. The user can strike it at the plan review; nothing else depends on it.

- `replay(url, *, window_start, window_end, now, minutes, schema, sleep=time.sleep)`: reads the real `sensor_levels` and `camera_readings` rows whose time is in the window (default 2026-09-27 12:00 to 16:00 UTC, the measured peak), shifts every time by the same amount so the window's end lands on `now`, and inserts them in time order over `minutes` of wall-clock time, each row carrying `replay_of` = its original time, with `ON CONFLICT DO NOTHING`. After each batch it refreshes the two hourly summaries over the hours the batch touched (on an autocommit connection). Real-time aggregation only adds rows newer than the last refreshed hour, so without that refresh a second replay in an hour that was already refreshed would stay invisible. It uses a normal read-write connection; the service stays read-only.
- `clear(url, schema)`: deletes every row with `replay_of` set and refreshes the two hourly summaries over the hours those rows covered.
- CLI: `python -m web.tiger.replay [--minutes 10] [--clear]`.
- Tests in `test_dash_db.py` (`db`, `fresh_schema`, with the clock and the sleep passed in): X1 the rows inserted equal the rows in the window, the latest lands on `now`, and each carries its original time; X2 after a replay the default alerts are `live: true`, every replayed item is marked as a replay, and the summaries include the new rows without a refresh; X3 `clear` leaves exactly the original rows and verify passes again; X4 replay, clear, then replay again inside the same clock hour: the second replay's rows show in the summaries and the alerts; X5 a replay whose shifted times fall in an hour that also holds real rows leaves the real rows' summary values unchanged, and the peak hours and verify are the same as before the replay.

## Step 10. Local end to end on the real files

1. `TIGER_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/postgres py -m web.tiger.load` then `... -m web.tiger.verify`: every check passes. Record row counts, load time, database size and the compression figures.
2. `py -m web.tiger.export`; run it twice and compare `shasum` (AC6).
3. Start the service against the local database; fetch every route once with `curl`; check the bucket counts (AC4), the alerts as of `2026-09-27T15:30:00Z`, `/api/alerts/peaks`, `/api/stats`, and that the CSV download equals the file. Run a two-minute replay and watch `/api/alerts` change; then `--clear` and verify again.
4. Full dashboard suites: `py -m pytest tests/dashboard -q -m "not db and not network"` (AC1) and `py -m pytest tests/dashboard -q -m db` (AC2). Record the counts.

## Step 11. Load the real Tiger service

Depends on step 2b. If the service was never reachable and the console path was not usable, this step is skipped and the change is reported as "built and tested locally, not loaded".

1. Reachable (directly or on the hotspot): `py -m web.tiger.load`; `py -m web.tiger.verify` (AC3); `py -m pytest tests/dashboard/test_dash_live.py -q -m network -k "L1 or L2 or L4"`.
2. Console path, only if step 2b showed it works: build `dump`, then `py -m web.tiger.load --dump-dir <scratchpad>/tiger_dump`; with the user in the Tiger console: `setup.sql`, the CSV imports, `after_load.sql`. Verify cannot run from this network in that case, so the checks are run as SQL in the console and reported as such.
3. Record storage used and the compression ratio (AC5).

## Step 12. Gated on the user's yes (nothing here is done without it)

- Hosting: the service needs a public host that can reach Tiger's port and serve HTTPS. Proposal: a free web service on Render running the start command, with `TIGER_DATABASE_URL` and `ALLOWED_ORIGINS` set in the host's own settings by the user. It needs the branch on GitHub, which is a push and needs its own yes. After it is live: L3, and a warm-up request before the demo because a free host sleeps.
- Domain: the user registers it under the hackathon's GoDaddy Registry instructions. Three name proposals and the DNS record the host asks for (a CNAME to the host's address) are given when the host is chosen. Then L5.
- Frontend: when the user shares where it is, replace its data calls with the contract in `docs/features/TIGER_DASHBOARD.md` and add the storm-replay control from `/api/alerts/peaks`.
- Demo checklist an hour before: hotspot ready, warm-up request, replay started, `/api/stats` open, and a screen recording of the Tiger console running a query as a fallback.

## Step 13. Guards and regression

- `$MAINPY -m pytest tests -q -m "not network" --ignore=tests/vision --ignore=tests/potholes --ignore=tests/cctv --ignore=tests/crashes --ignore=tests/dashboard`: the step 0 baseline (AC7).
- The same command without `--ignore=tests/dashboard`: the same count, because the dashboard conftest ignores its test files when the driver cannot be imported.
- `shasum -a 256` of the sources equals `sources_before.txt` (AC7, S4).
- `git diff --stat 65162c5..HEAD` and `git status --short`: only files under "What will change".
- `git grep -nE "postgres(ql)?://[^[:space:]:@/]+:[^[:space:]@/]+@"` prints nothing (AC8).

## Step 14. Docs and commits

- `docs/features/TIGER_DASHBOARD.md`: fill "How to run it", example replies and "Results" (counts, compression, storage, timings).
- `web/README.md`: setup, the key names without values, commands, the start command, the local test database.
- Run spec: Results, Deviations, the README paragraph for the user to paste, and what was not done.
- Commits on `tiger-dashboard` with explicit paths and conventional prefixes: `docs:` (spec, plan, review, feature doc), `feat:` (code and tests, split by step where it helps), `docs:` (results). No push.

## Step 15. Post-commit

Claude critique against the audit rubric, looped until Acceptable; then `bash ~/.claude/review-audit.sh docs/specs/2026-10-03_tiger-dashboard.md`; findings fixed and recorded in the run spec. Tell the coordination chat the change is finished.

## Risks

- The real database may be unreachable from this network. Mitigation: step 2b finds out early; the change is still testable locally and is reported honestly if not loaded.
- The free plan may refuse a feature or differ from the local version. Mitigation: `probe` and `try_features` run first; nothing depends on PostGIS.
- Compression on tables this small may save little. Mitigation: the measured figure is reported as it is; chunk sizes were chosen so several chunks exist. Only the time-stamped tables compress; the road table is an ordinary table.
- The default alert view shows only known-dry flags from 2026-10-03. Mitigation: `as_of`, `/api/alerts/peaks` that ranks without known-dry cameras, sensor alerts from measured depth, and the labelled replay.
- A load locks the tables for its transaction. Mitigation: never load during the demo; the service has a lock time limit.
- Disk is 97% full (about 15 GB free). Mitigation: the step 0 check; `web/.venv` is small; the export is about 15 MB.
- The test fixture folder is the largest single piece of test work (about an hour). Mitigation: it is built once in step 2 and reused by every later step.
- The frontend is unseen. Mitigation: a written contract and `/docs`; wiring is a gated step.

## Critique (Claude, 2026-10-03) and how each finding was handled

1. Search path without `public` breaks every TimescaleDB function (blocker). Accepted: the path is `<schema>, <extension schema>` in `connect`, `setup` and the service (steps 2, 5, 8).
2. A columnstore policy added by hand runs at once (blocker). Accepted: the automatic policy is kept and none is added by hand; refresh policies get a future `initial_start` (step 5). Confirmed on the local database after the critique.
3. `export.atomic` wrapping `write_atomic` would pull pandas, scipy and scikit-learn into the service. Accepted: `export.py` has its own atomic write and imports pandas lazily; `FLOODED_CM` is copied, not imported (steps 7, 8).
4. Tests scheduled before the code they import. Accepted: each test is added in the step that creates its module (S3, S6, S10, D8, E8 moved).
5. The real service was probed last. Accepted: step 2b, with `try_features`. The third fallback of D17 (loading from the host) had no step and is removed from the spec.
6. Fixtures shared changed state; a function-scoped patch fed wider fixtures. Accepted: `fresh_schema` for tests that change data, D8 on a copy, `sunnyday_out` as a context manager.
7. A one-sided range check accepts not-a-number. Accepted: every float column has the three-part check (step 3).
8. Source columns not named, and two Helene columns exist. Accepted: the mapping table in step 3.
9. The fixture folder was underestimated. Accepted: budgeted in step 2. Needed per file: segments (`make_table` plus `pv_ROUTEID`, `pv_ROUTE`, `pv_COUNTY`, `pv_BEG_MP`, `pv_END_MP`, `pv_FROM_DESC`, `pv_TO_DESC`, `pv_DIVISION`, `pv_TREATMENT_COST`, `pv_PMS_TREATMENT_NAME`); `predictions_geo` (geometry consistent with `mid_x`, `mid_y`, four predictions, three flags); `traffic_crash`; `ncdot_joined` (`seg_id`, `YEAR_LAST_REHAB`, the same geometry); `city_limits` (a `city` column, not empty); `pothole_reports` (`source` only `charlotte` or `raleigh`); the manifest JSON (`sha256`, `pulled_at`); the 14 `flood_camera_depth` columns; sensor JSON (`features[0].properties.platform_short_name`, `parameters[id=water_level_raw].observations.{times,values}`, `geometry.coordinates`).
10. Verify would crash inside `read_bundle` before naming the changed file. Accepted: fingerprints are checked first (step 6).
11. The secret grep would match the test's own fake address; S2 needed DNS. Accepted: `fake_url` joins pieces; a closed local port is used.
12. Other chats' plain `pytest` would run these tests; the stale-schema sweep could drop a concurrent session's schema. Accepted: `collect_ignore_glob`; only schemas over an hour old are dropped.
13. Job ids change. Accepted: D2b compares names and settings.
14. T10 can only plant a bad value. Accepted as written in step 4.
15. AC8's log and the default "as of" had no test. Accepted: S10 and A9's second case.
16. `tiger.env` is readable by every chat. Accepted: said to the user in step 2b.
- Tests that could not fail (R11, E4, half of R12). Accepted: reworked in steps 3 and 7.
- Cut list: the GeoJSON-lines risk file and its route are cut. `/api/camera_history`, verify's recompute and the frozen P2 tests are kept; the console dump is built only if step 2b says it is needed.
- "Nothing changes during the demo". Accepted as step 9, flagged for the user to keep or strike.

## Codex plan review (2026-10-03) and how each finding was handled

The review is `docs/reports/2026-10-03_tiger-dashboard-plan-review.md`: eight findings marked critical and three suggestions. All eleven are accepted.

1. The pool constructor has no `wait` argument. Accepted: the pool is built closed, then `pool.open(wait=False)`; its wait time comes from the settings; the service tests run the lifespan with the real pool (step 8).
2. A full refresh can hide replay rows put into an hour that is already refreshed. Accepted: the replay and its clear refresh the hours they touch after each batch; X4 replays twice in one hour, with a clear between (step 9).
3. One flag per summary row cannot separate real and replayed rows in the same hour. Accepted: both hourly summaries group by `is_replay`, the peak hours and verify read only the real rows, and X5 tests a mixed hour (steps 5, 6, 8, 9).
4. The local-only guard missed `hostaddr`. Accepted: `require_local` checks `host`, `hostaddr`, `service` and `passfile` before connecting, `assert_local` checks the open connection's address before any change, and S8 has a conflicting `host` and `hostaddr` case (step 2).
5. The pool's background logs can carry connection details. Accepted: a logging filter on the driver's loggers, and S10 starts the real service against a closed port and a refused login and checks the captured logs (step 8).
6. The streamed download's ownership and failure behaviour were not defined. Accepted: `iter_risk_csv` is the single writer; the route opens the cursor before sending headers and releases it in a `finally`; A17 covers a failure before the first byte, a failure part-way and a client that stops reading (steps 7, 8).
7. A reload could show a mix of two loads. Accepted: every data route checks the load status inside the same read transaction as its query and answers "loading" unless it is `complete`; D4 and A16 stop a load after the copy and after the first refresh (steps 5, 8).
8. An hour-old test schema may still be in use. Accepted: the automatic sweep is removed; S11 checks an existing `test_` schema survives a session start (step 2).
9. Alert times had no defined meaning. Accepted: the summaries are labelled as hourly worst values and carry first and last reading times; the alert reply looks up the worst and the latest reading, each with its own time; A9's third case plants an early flag followed by a dry reading (steps 5, 8).
10. The fingerprints could describe different bytes from those loaded. Accepted: fingerprints are taken before and after the build and a change refuses the load; T13 (step 4).
11. `$PY` does not split in zsh. Accepted: `py` is a shell function, written out at the top of this plan.
