# Plan: real pothole evidence (reports, cameras, pothole head) (2026-10-03)

Run spec: `docs/specs/2026-10-03_pothole-evidence.md`. Branch `cctv-potholes` at `64609f1` (equal to `main`). Mode: standard.

All commands run from the worktree root `/Users/nathanstough/Desktop/Hack-NCSU/.claude/worktrees/cctv-potholes` with `PY=/Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python`. `data/raw`, `data/processed` and `data/chips` in the worktree are links to the shared folders. No `uv sync`, no bare `uv run`, no `git stash`, no `git add -A`.

## Grounding (current code this plan builds on)

- `src/model/common.py` (at `64609f1`): `PV` L29, `TR` L32, `BANNED_PREFIXES = ("y_", "pred_", "n_", "im_vit_")` L45, `check_features` L48, `write_atomic(path, write)` L97, `merge_one_to_one(d, other, name)` L110, `terrain_columns(d)` L137, `prep(d, cols)` L142, `oof(d, X, y, kind, mask, seed)` L162 (reads `d.fold`; skips and reports a fold with no test rows, no training rows or one class), `fit_all_predict(X, y, kind, mask, seed)` L183, `score(y, pred, mask, kind)` L197, `precision_at_k` L213, `N_ESTIMATORS = 400` L25 (read at call time), `SEED = 0` L24.
- `src/pipeline/helene_labels.py`: `CRS_M = "EPSG:32119"` L24, `MATCH_M = 30` L25, the `gpd.sjoin(..., predicate="dwithin", distance=...)` pattern L35.
- Midpoint rule: `shapely.line_interpolate_point(geom, 0.5, normalized=True)` in `src/pipeline/chips.py` L86 and `src/pipeline/features.py` L38; `length_m` from the EPSG:32119 geometry at `features.py` L40.
- `tests/conftest.py`: fixtures `table` L69 (2,000 rows, 40 blocks of 5 km, columns shaped like `segments.parquet`), `small_models` L63 (30 trees, opt-in), `write_dir` L90. Fixtures reach sub-folders automatically; nothing is imported from this file.
- `pyproject.toml`: `pillow` declared; markers `realdata` and `network` registered; `pythonpath = ["."]`.
- Shared data, read-only: `data/raw/ncdot_joined.parquet` (112,443 rows; `seg_id`, `ROUTE` (8 characters: class digit 1 = Interstate, 2 = US, 3 = NC, 4 = secondary; route number in characters 4 to 8), `YEAR_LAST_REHAB`, geometry EPSG:4326), `data/processed/segments_targets.parquet` (110 columns incl. `fold`, `split_block`, `length_m`, `tr_aadt`, `pv_RTG_NBR`, `pv_COUNTY`), `data/processed/predictions.parquet` (`pred_rate`, `pred_crack`, `rate_heldout`, `crack_heldout`), `data/processed/split.parquet`.
- Live sources (checked 2026-10-03): Charlotte `https://gis.charlottenc.gov/arcgis/rest/services/ODP/ServiceRequests311/MapServer/0` (fields `REQUEST_NO`, `REQUEST_TYPE`, `RECEIVED_DATE`, `LATITUDE`, `LONGITUDE`, `Shape`; 7,500 rows per request); Raleigh `https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/Ask_Raleigh_Requests/FeatureServer/0` (fields `NUMBER`, `SERVICE`, `REQUEST_TYPE`, `APPLIED_DATE`); cameras `https://services.arcgis.com/NuWFvHYDMVmmxMeM/ArcGIS/rest/services/NCDOT_Cameras/FeatureServer/0` (fields `CameraId`, `CameraStatus`, `ImageStatus`, `Highway`, `County`, `LocationName`, `Latitude`, `Longitude`, `ImageUrl`; 2,000 rows per request). Camera `Highway` has 91 distinct values such as `I-40`, `US-70 BUS`, `US 29`, `NC-540`, `Other`, `Edwards Mill`.
- City limits (checked 2026-10-03): US Census TIGERweb incorporated places, January 2026 vintage, `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4/query` with `where=STATE='37' AND BASENAME IN ('Charlotte','Raleigh')`, `outFields=NAME,BASENAME,STATE,GEOID`, `outSR=4326`, `f=geojson`. It returns two MultiPolygons (Charlotte GEOID 3712000, Raleigh GEOID 3755000). `NAME` carries the suffix " city", so the filter uses `BASENAME`. Charlotte publishes no city-limits layer of its own.
- Report fields (checked 2026-10-03): Charlotte `RECEIVED_DATE` is epoch milliseconds, `REQUEST_NO` is a unique integer, paging by `resultOffset` is supported (7,500 rows per request). Raleigh `APPLIED_DATE` is epoch milliseconds, `NUMBER` is a string such as `SRC0004609`, paging is supported (1,000 rows per request). No official page confirms that Charlotte's `CDOT POTHOLE REPAIR` type covers only city-maintained streets, so a city-street report within 30 m of a state road can be matched to it; the check therefore carries a sensitivity row that uses the `NCDOT POTHOLE REQUEST` type alone.

## Step 0. Pre-flight

1. `git branch --show-current` must print `cctv-potholes`; `pwd` must be the worktree root; `git status --short` must show only this change's untracked docs.
2. Record fingerprints for AC8 in the session scratchpad: `shasum -a 256 data/processed/segments_targets.parquet data/processed/split.parquet data/processed/predictions.parquet data/raw/ncdot_joined.parquet data/raw/ncdot_master.parquet data/raw/ncdot_asphalt.parquet > <scratchpad>/shared_before.txt`.
3. Baseline: `$PY -m pytest -q -m "not realdata and not network"` must print `83 passed`.

## Step 1. `src/pipeline/arcgis_fetch.py` (new)

Count-checked paging shared by the report pull and the camera list (D2).

- `UA = {"User-Agent": "unwatched-roads-hackathon/0.1 (NC State student project)"}`, `PAUSE_S = 0.5`.
- `class ArcGISError(RuntimeError)`.
- `get_json(session, url, params)`: `session.get(url, params=params, headers=UA, timeout=60)`, `raise_for_status()`, parse JSON; raise `ArcGISError` if the body is not a JSON object or has an `error` key.
- `count(session, layer_url, where)`: `returnCountOnly=true`; raise if `count` is missing.
- `fetch_all(layer_url, where, out_fields, *, geometry, page, session=None, sleep=time.sleep)`: ask `count`; loop `resultOffset` with `orderByFields=OBJECTID`, `outSR=4326`, `f=json`; a page without a `features` list raises; the first feature must contain every name in `out_fields` or raise naming the missing ones; `sleep(PAUSE_S)` between pages; stop on an empty page; raise `ArcGISError` unless `len(rows) == count`. Returns a list of attribute dicts, with `lon` and `lat` added from the geometry when `geometry=True` (None when a feature has no geometry).

## Step 2. `src/pipeline/cctv.py` (new) and its tests, then one live round

Done first because stills need daylight.

Code:
- `LAYER`, `FIELDS` as in Grounding. `MAX_M = 100`, `STALE_S = 900`, `MIN_BYTES = 2000`, `DARK_LUMA = 40`, `HOST_GAP_S = 1.0`, `MIN_FREE_GB = 2`, `BREAKER_MIN = 40`, `BREAKER_SHARE = 0.5`.
- `list_cameras(session=None)`: `fetch_all(LAYER, "1=1", FIELDS, geometry=False, page=1000)`; rename to `camera_id, status, image_status, highway, county, location_name, lat, lon, image_url`; a duplicate or null `camera_id` raises.
- `parse_highway(name)`: regex `^\s*(I|US|NC)[- ]?(\d+)`; returns `(class_digit, number)` with `I -> "1"`, `US -> "2"`, `NC -> "3"`, else `None`.
- `match_cameras(cams, segs, max_m=MAX_M)`: camera points and segments (`seg_id`, `ROUTE`, geometry) to EPSG:32119; `gpd.sjoin(points, segs, predicate="dwithin", distance=max_m)`; distance per pair; if `parse_highway` succeeds and some candidates have `ROUTE[0] == class_digit` and `int(ROUTE[3:8]) == number`, take the nearest of those (`match_rule = "route"`); else the nearest candidate (`"nearest"`); no candidate leaves `seg_id`, `seg_dist_m`, `match_rule` null. Ties break on `seg_id`. Prints matched, unmatched and by-rule counts.
- `write_cameras(cams, path)`: `common.write_atomic(path, cams.to_parquet)` with the D15 column order.
- `class Pacer(gap, clock, sleep)`: `wait(host)` sleeps until `gap` seconds since the last request to that host.
- `check_image(body)`: at least `MIN_BYTES`, starts `FF D8`, ends `FF D9`, and `PIL.Image.open(BytesIO(body)).verify()` succeeds; returns `(ok, reason, width, height, mean_luma)`.
- `image_time(headers, now)`: `Last-Modified` parsed to UTC; missing or unparsable gives `now` and the flag `no_image_time`.
- `collect_round(cams, out_dir, round_id, *, session, pacer, now, disk_free)`: refuse under `MIN_FREE_GB`; iterate cameras with `image_status == "Recent"` and a non-null URL; `pacer.wait(host)`; GET with `UA`, timeout 20; a request exception or non-200 logs `http_error`; `check_image` failure logs `not_image`; older than `STALE_S` logs `stale`; same sha1 as the camera's last saved row in `stills.parquet` logs `duplicate`; otherwise write `out_dir/{camera_id}/{image time %Y%m%dT%H%M%SZ}.jpg` via a `.tmp` name and `os.replace`. An existing file is never replaced: if that name already exists with different bytes the still is saved as `{time}_{first 8 of sha1}.jpg`. After `BREAKER_MIN` attempts, a failure share above `BREAKER_SHARE` sets a stop flag and leaves the loop. After the loop, whether it finished or was stopped, any sha1 saved in this round for three or more cameras marks those rows `placeholder` and deletes only the files this round wrote for them; then the round's rows, including every failed attempt, are appended to `stills.parquet`; only then is the stop raised. `dark` is set when `mean_luma < DARK_LUMA`. Appends the round's rows to `out_dir/stills.parquet` atomically (`camera_id, round, file, image_time, fetched, bytes, sha1, width, height, mean_luma, status, dark`).
- `main()`: `list` (pull, match, write `data/raw/cctv/cameras.parquet`) and `collect --rounds N --every S --limit N`. One failed camera never stops a round; the loop ends after N rounds.

Tests `tests/cctv/conftest.py` (fake session with scripted replies, fake clock, a tiny JPEG maker using Pillow, a 3-segment GeoDataFrame) and:
- `tests/cctv/test_cctv_collect.py`: K1 to K16 as in the spec. K7 also asserts that after the stop every attempt is in `stills.parquet` and every saved file has a log row. K16 sends different bytes with an unchanged `Last-Modified` and asserts both files exist and the first is byte-identical to before. K6 uses the fake clock and asserts gaps of at least 1.0 s per host, and a second assertion that a `Pacer(gap=0)` violates it. K13 runs `git check-ignore -q data/raw/cctv/1/x.jpg`. K14 runs `python -m src.pipeline.cctv --help`.
- `tests/cctv/test_cctv_match.py`: M1 to M5. M3 builds an `I-40` camera 20 m from an `NC` segment and 40 m from a `10000040` segment.

Live run (daylight only; skip the collect and say so if after 18:30 local):
1. `$PY -m src.pipeline.cctv list` and check at least 1,100 cameras, at least 900 recent, match counts printed.
2. `$PY -m src.pipeline.cctv collect --rounds 1` (about 1,000 requests, about 60 MB, about 4 minutes).
3. Send the flood-depth chat the paths and column lists of `cameras.parquet` and `stills.parquet`.

## Step 3. `src/pipeline/pull_potholes.py` (new) and its tests, then the live pull

Code:
- `SOURCES`: Charlotte `where = "REQUEST_TYPE IN ('CDOT POTHOLE REPAIR','NCDOT POTHOLE REQUEST')"`, id `REQUEST_NO`, type `REQUEST_TYPE`, date `RECEIVED_DATE`, fallback coordinates `LONGITUDE`/`LATITUDE`, page 5000. Raleigh `where = "SERVICE = 'Potholes & Sinkholes' AND REQUEST_TYPE = 'Pothole'"`, id `NUMBER`, date `APPLIED_DATE`, page 1000.
- `NC_BBOX = (-84.5, 33.7, -75.3, 36.7)`.
- `clean(rows, source, now)`: re-check the request type against the source's allowed set (others dropped and counted as `wrong_type`); coordinates from the geometry, else the fallback fields; drop and count `unlocated` (null, non-finite or zero), `out_of_state` (outside `NC_BBOX`), `undated` (null date), `future` (later than `now`, which becomes `pulled_at`), `duplicate` (repeat `report_id`; more than 1% duplicates raises). Dates: epoch milliseconds to UTC, stored as a naive UTC timestamp. Returns a GeoDataFrame with the D4 columns and a counts dict.
- `pull_city_limits(session)`: one GET of the TIGERweb query in Grounding with `UA`; `city = BASENAME.lower()`; exactly the two cities with one non-empty polygon or multipolygon each, else raise.
- `main(raw=Path("data/raw"), session=None, now=None)`: pull both sources, `clean`, concatenate, write `pothole_reports.parquet` and `city_limits.parquet` with `common.write_atomic`, and LAST `pothole_reports.meta.json` (`pulled_at`, per-source server count, kept count, each dropped count, and the sha256 of both parquet files) via a `.tmp` file and `os.replace`. The meta file is the bundle's manifest: a reader that finds a parquet whose sha256 differs from the manifest refuses. Nothing is written if any pull raises.

Tests `tests/potholes/conftest.py` (fake session, report-row maker, a square "city" polygon over part of the `table` fixture's grid, a helper that turns the `table` fixture into a segment GeoDataFrame in EPSG:4326 with a known projected length) and `tests/potholes/test_pothole_pull.py`: P1 to P12. P12 fails the write after the reports file is replaced and before the manifest, then asserts the label step refuses the mismatched bundle.

Live run: `$PY -m src.pipeline.pull_potholes`; check the printed server counts equal the rows received and the meta file lists the drops.

## Step 4. `src/pipeline/pothole_labels.py` (new) and its tests, then the live labels

Code:
- `WINDOW_START = {"charlotte": "2023-01-01", "raleigh": "2025-05-01"}`, `MATCH_M = 30`, `CRS_M = "EPSG:32119"`.
- `assign_city(segs_m, limits_m)`: midpoint by the shared rule, `within` the city polygon; null otherwise. A missing or empty limits table raises.
- `match_reports(reports_m, segs_m)`: `gpd.sjoin_nearest(reports, segs, max_distance=MATCH_M, distance_col="dist_m")`, then keep one row per `report_id` ordered by `dist_m`, `seg_id`. Prints matched and unmatched counts per source.
- `exposure_start(city, rehab_year)`: the later of the city's window start and 1 January of `rehab_year + 1`; the window start when the rehab year is null.
- `build_labels(segs, reports, limits, pulled_at)`: one row per segment in input order with the D9 columns. `length_m` is computed here as `segs.to_crs(CRS_M).length` (the `features.py` L40 convention; the raw table has no length column in metres). `n_pothole_reports` counts matched reports with `exposure start <= received_date <= pulled_at`; the three per-type counts likewise; `n_pothole_all_time` counts every matched report; `pothole_exposure_years = max(0, (pulled_at - start).days / 365.25)`, null outside a city; `y_pothole_rate = n / (length_m / 1609.344 * exposure_years)` with null when either factor is not positive; `y_pothole_any = float(n > 0)` inside a city with positive exposure, null otherwise. Any matched `seg_id` not in the segment table raises.
- `main(raw, processed)`: reads `ncdot_joined.parquet` (`seg_id`, `YEAR_LAST_REHAB`, geometry), the reports, the limits and `pulled_at` from the meta file, after checking both parquet files against the sha256 values in the manifest (mismatch or missing manifest raises); writes `data/processed/pothole_labels.parquet` atomically; prints segments per city, positives per city and the match rate.

Tests `tests/potholes/test_pothole_labels.py`: L1 to L14. L7 pins both ends (a report one day before the exposure start and one day after `pulled_at` are not counted; reports on the two boundary days are). L13 runs `main()` on a fixture directory holding the real raw schema (`seg_id`, `YEAR_LAST_REHAB`, geometry, no length column) and checks the rate against a hand-worked length. L14 a parquet that does not match the manifest is refused.

Live run: `$PY -m src.pipeline.pothole_labels`; check 112,443 rows and blank labels outside the two cities.

## Step 5. `src/model/pothole_check.py` (new) and its tests, then the live check

Code:
- `load(p)`: `segments_targets.parquet` columns `seg_id, split_block, tr_aadt, pv_RTG_NBR, length_m`; `common.merge_one_to_one` with the labels and with `predictions.parquet[seg_id, pred_rate, pred_crack, rate_heldout, crack_heldout]`. Gates (D11): required columns present, unique `seg_id`, identical segment sets; otherwise `ValueError`. Population mask: `pothole_city` not null, exposure and length positive.
- Scores: `rating` = `-pv_RTG_NBR` where the rating is above 0; `pred_rate` where `rate_heldout`; `pred_crack` where `crack_heldout`. Higher always means worse.
- `traffic_band(d)`: per city, `"none"` when `tr_aadt` is null, else thirds by rank.
- `fifth(d, score)`: within city and band, rank to five groups; bands under `MIN_BAND = 50` scored rows are excluded and listed with the reason.
- `lift(d, score)`: reports and mile-years summed over the worst and best fifths; `adjusted` pools the within-band fifths, `raw` cuts fifths over the whole city; a zero denominator gives null.
- `block_range(d, score, n=1000, seed=0)`: draw block ids with replacement and build each draw by concatenating every drawn block's rows once per time it was drawn (a block drawn twice counts twice; `isin` filtering is not used). Bands and fifths are fixed from the full data, not recomputed per draw. A draw whose adjusted lift is undefined (no reports in the best fifth, or no mile-years) is dropped. Returns the 2.5 and 97.5 percentiles and `n_valid_draws`; under 500 valid draws the range is null with the reason.
- Sensitivity: for Charlotte the whole calculation is repeated with `n_pothole_ncdot` in place of `n_pothole_reports` and reported as a separate row.
- `main(p=Path("data/processed"))`: per city, score and report set write `results/pothole_check.json` (n, reports, mile-years, raw, adjusted, range, per-band rows, excluded bands, sha256 of the labels and predictions files, git commit, timestamp) and `pothole_check.md`, both atomically.

Tests `tests/potholes/test_pothole_check.py`: C1 to C11 (C5 also checks that a block drawn twice contributes its rows twice; C10: the sensitivity row counts only the NCDOT-type reports; C11: a population with no reports gives null lifts and a null range without an error). C2 builds reports from traffic alone and asserts raw lift above 1.5 and adjusted lift between 0.7 and 1.4.

Live run: `$PY -m src.model.pothole_check`, twice, comparing the JSON apart from the timestamp (AC7).

## Step 6. `src/model/pothole_head.py` (new) and its tests, then the live head

Code:
- `load_table(p)`: `segments_targets.parquet` merged one-to-one with the labels and with the four prediction columns; `terrain_columns(d)` for the terrain set.
- `features(d)`: `PV + TR + terrain_columns(d)`; raises if any name contains `pothole`; `common.prep` applies the shared ban.
- Masks: `train_clt` = Charlotte, label not null, rehab year below 2023 or null; `test_ral` = Raleigh, label not null, rehab year below 2025 or null.
- Held-out Charlotte: `oof(d, X, y, "bin", train_clt)` for the head and for the traffic-only inputs `TR + ["pv_LENGTH"]`. Transfer: `fit_all_predict(X, y, "bin", train_clt)` scored on `test_ral`, for both input sets. Main-model ranking: `pred_rate` where `rate_heldout`.
- Scoring: `score(..., "bin")` and `precision_at_k(k=50)` for each method on (a) all labelled rows of the set and (b) the rows where every method has a value, so the comparison rows are identical; base rate and positive count beside them. `beats_traffic` from (a) on Charlotte. `too_few` when Raleigh positives are under 20. AUC-PR above `LEAK_AUCPR = 0.9` raises.
- Availability: when `train_clt` is empty or has one class, nothing can be fitted. The results then carry `status = "unavailable"` with the reason, every metric and `beats_traffic` are null (not false), and `pred_pothole` is null for every segment. Otherwise `status = "ok"`.
- Predictions: out-of-fold value where it exists, else the Charlotte-fit model's value; `pothole_heldout` is true only where `pred_pothole` is not null AND the value did not come from a model that trained on that row (so it is false for `train_clt` rows without an out-of-fold value and for every row without a prediction); `pothole_tested_area` = `pothole_city` not null. Written atomically to `pothole_predictions.parquet`; results to `results/pothole_head.json` and `.md` with fingerprints and commit.
- `main(p=Path("data/processed"))`.

Tests `tests/potholes/test_pothole_head.py`: H1 to H15, using `small_models`. H14 an empty Charlotte population and H15 a one-class Charlotte population each give `status = "unavailable"`, null metrics, null predictions and no `pothole_heldout` row set true. H12 hashes the fixture directory's `segments_targets.parquet`, `split.parquet` and `predictions.parquet` before and after `main`. H13 builds two tables: potholes driven by `pv_age_at_survey` (head AUC-PR above traffic-only) and by `tr_aadt` alone (head not above traffic-only by more than 0.02).

Live run: `$PY -m src.model.pothole_head`, twice (AC7).

## Step 7. `src/pipeline/cctv_review.py` (new), its tests, then grading

Code:
- `build(round_id, sample=400, seed=0)`: from `stills.parquet`, saved non-dark stills of the round, a seeded sample; writes `data/raw/cctv/review/{round}/sheets/sheet_NN.jpg` (4 by 4 cells of 392 by 220, index label in each cell) and `manifest.csv` with exactly `index, camera_id, file`.
- `crops(round_id, clear_indices, cap=160, seed=0)`: for clear views, the bottom 60% of the frame at full size, longest side capped at 1,568 pixels, as `crops/{index}.jpg`; `--repeat 40` writes a shuffled second set under `repeat/{repeat_index}.jpg` and `repeat_key.csv` (`repeat_index, camera_id, file`), which the graders never see.
- `assemble(manifest, triage, damage, repeat_key, repeat_damage)`: joins the triage and damage answers to `(camera_id, file)` through `manifest.csv` for pass 1 and through `repeat_key.csv` for pass 2, so both passes are keyed by the same `(camera_id, file)`; an index missing from its key raises.
- `validate_grades(grades, cameras, base)`: exact columns; `view` in `clear | far | unusable`; `damage` in `none | cracks_or_patches | pothole | cant_tell` for clear views and empty otherwise; `pass` in 1 or 2; known `camera_id`; existing file; no duplicate (`camera_id`, `file`, `pass`). Any violation raises with the row.
- `agreement(grades)`: pairs pass 1 and pass 2 on `(camera_id, file)`; raises if no still is in both passes; returns the pair count, raw agreement and Cohen's kappa on `damage`.
- `main()`: `build`, `crops`, `assemble`, `validate`, `agreement`.

Tests `tests/cctv/test_cctv_review.py`: G1 to G7. G7 runs the whole repeat path on fixture stills: build, crops with `--repeat`, answers keyed by the shuffled repeat indices, `assemble`, `validate`, `agreement`, and checks every pair joins the same still.

Grading (the user chose Claude as the grader):
1. `$PY -m src.pipeline.cctv_review build --sample 400`.
2. View triage: two helper agents each read half of the sheets and return `index,view` using the rubric: clear = daylight, dry, at least one lane of pavement large in the near part of the frame and not blocked; far = road visible but small, distant or partly blocked; unusable = rain, fog, drops on the lens, glare, dark, or no road.
3. `crops` for the clear views (cap 160), then four helper agents grade 40 crops each and return `index,damage`; a fifth grades the 40 repeats. Rubric: pothole = an open hole or broken-out patch in the travelled lane; cracks_or_patches = visible cracking, sealed cracks or patch repairs; none = uniform surface; cant_tell otherwise. Helpers see only the image and its index.
4. `assemble` the answers into `data/raw/cctv/grades.csv` (pass 2 mapped back through `repeat_key.csv`), then run `validate` and `agreement`.

## Step 8. `src/model/cctv_check.py` (new) and its tests, then the live check

Code: merge `cameras.parquet`, pass-1 grades (one row per camera: its graded still), and the scores from step 5 plus `pred_pothole` when `pothole_predictions.parquet` exists; population = matched cameras with a clear view and a decided grade; for each score separately, first keep only cameras whose segment has that score (and, for model scores, its held-out flag true), then count them: under `MIN_CAMERAS = 30` that score gets `too_few` and no ratio; otherwise thirds are cut on those cameras and the share with visible damage in the worst and best thirds and their ratio are reported; unmatched and undecided counts reported; writes `results/cctv_check.json` and `.md` atomically with fingerprints.

Tests `tests/cctv/test_cctv_check.py`: X1 to X5. X5 has 40 graded cameras of which 10 have a held-out rate prediction: that score is `too_few` while the rating score, present for all 40, gets a ratio.

## Step 9. Guards, real-data pins, regression

1. `tests/potholes/test_pothole_guards.py`: R1 (`--help` for the eight new modules), R2 (no `* 2*` files under `src` or `tests`), R3 (`git diff --name-only 64609f1 -- <D20 files>` is empty; the readme is checked under both names, `readme` and `README.md`, because `main` renamed it at `baa0d4e`).
2. `tests/potholes/test_pothole_real.py` and `tests/cctv/test_cctv_real.py`: N1 to N3 and N5 under `network` (server count queries), N4 under `realdata`.
3. `$PY -m pytest -q -m "not realdata and not network"` (AC1), then `-m realdata`, then `-m network tests/potholes tests/cctv`.
4. Join regression without writing shared data: `pull_ncdot --join-only` rewrites `data/raw/ncdot_joined.parquet` (its `main` L183), so it is NOT run. Instead a one-off `$PY -c` reads the cached `ncdot_master.parquet` and `ncdot_asphalt.parquet`, calls `src.pipeline.pull_ncdot.join_layers` (L112) in memory and asserts 112,443 rows, 68,531 asphalt rows and 68,349 matched.
5. `shasum -a 256` of the six files recorded in step 0 must be unchanged (AC8).
6. `git diff --stat 64609f1..HEAD` and `git status --short` list only this change's files.

## Step 10. Docs and commits

1. Fill the run spec's Results section: counts, match rate, the check table, the head table, camera counts, grading agreement, and one plain-English paragraph the user can paste into `README.md`.
2. Doc-sync sweep: grep the spec, this plan and the memory notes for claims this change overturns (for example "needs a key").
3. Commit on `cctv-potholes` with explicit paths, after `git diff --cached --name-only`: `feat: NCDOT camera list, segment match and still collector`; `feat: pothole reports, labels, check and head`; `feat: camera still review and check`; `docs: pothole evidence spec, plan and results`. No merge into `main`, no push.

## Step 11. Post-commit

1. Claude critique agent against the audit rubric, the run spec, this plan, its review file and `git diff 64609f1...HEAD`; fix and loop until acceptable.
2. `bash ~/.claude/review-audit.sh docs/specs/2026-10-03_pothole-evidence.md`; fix findings, commit, re-audit; record both verdicts in the run spec.
3. Present results to the user.

## Risks

- Daylight ends about 18:45 local. If step 2's live round cannot run before 18:30, the collector is still built and tested, and the live round, grading and camera check move to the next morning; the spec's AC6 is then reported as pending.
- Rain in central NC lowers today's share of clear views; the stop rule (1 in 5 clear) was passed at 2:35 pm (58 of 200).
- Raleigh has few reports on state roads; the transfer score may carry the "too few" flag.
- The shared folders are written by other chats. This change writes only its own files there and proves it with the fingerprints in step 9.
- Grading by helper agents is not a script. The grades file, the stills and the agreement figure are what make it checkable.

## Codex plan review (2026-10-03) and how each finding was handled

Review file: `docs/reports/2026-10-03_pothole-evidence-plan-review.md`. Ten findings, all accepted.

1. Regression command overwrites shared data. Accepted. `pull_ncdot --join-only` is no longer run; the join is checked in memory through `join_layers`, and the three raw NCDOT files joined the fingerprint list (steps 0 and 9). The run spec's AC8 was reworded to match.
2. `length_m` never established. Accepted. `build_labels` computes it from the projected geometry; test L13 runs `main()` on the real raw schema (step 4).
3. Reports beyond the window. Accepted. Cleaning drops anything after `pulled_at`; labels count only `start <= received_date <= pulled_at`; L7 pins both ends (steps 3 and 4).
4. Collector loses its log when stopped. Accepted. The stop is raised only after placeholder handling and the log write; K7 checks the log and the files (step 2).
5. File names can overwrite earlier evidence. Accepted. An existing file is never replaced; changed bytes with the same image time get a suffixed name; placeholder deletion touches only the current round's files; test K16 (step 2).
6. Double grading has no identity step. Accepted. `repeat_key.csv` plus `assemble` key both passes by `(camera_id, file)`; `agreement` raises on an empty pairing; test G7 (step 7).
7. Missing head predictions marked held out. Accepted. `pothole_heldout` requires a prediction; an unfittable Charlotte population gives `status = "unavailable"` with null metrics; tests H14 and H15 (step 6).
8. Camera sample gate per score. Accepted. Each score filters to its own usable cameras before counting and cutting thirds; test X5 (step 8).
9. Bootstrap multiplicity. Accepted. Draws repeat a block's rows per selection, undefined draws are dropped and counted, under 500 valid draws gives a null range; C5 extended, C11 added (step 5).
10. The three report files can disagree. Accepted. The meta file is written last as a manifest with the sha256 of both parquet files, and the label step refuses a mismatch; tests P12 and L14 (steps 3 and 4).

Tests after the review: 83 in the frozen design plus C10, C11, H14, H15, K16, L13, L14, P12, G7, X5 = 93.
