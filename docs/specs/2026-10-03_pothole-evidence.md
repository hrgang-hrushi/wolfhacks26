# Run spec: real pothole evidence (reports, cameras, pothole head) (2026-10-03)

Status: executed 2026-10-03 on branch `cctv-potholes` (not merged, not pushed); results at the end. The Decisions and the test list below are the frozen design plus the additions from the Codex plan review; everything that changed at execution or after the critique is listed under Deviations, not edited in above (three parenthetical pointers excepted). No hashes of the P1 and P2 texts were recorded, so the freeze rests on this statement and on git history from `48568da` on. P1 frozen 2026-10-03, P2 frozen 2026-10-03 (standard mode). Plan reviewed by Codex 2026-10-03: ten findings, all accepted (tests C11, H14, H15, K16, L13, L14, P12, G7 and X5 added; AC8 reworded so the regression check never rewrites shared data). Branch `cctv-potholes`, which contains `model-hardening` at `64609f1` (fast-forward merge, approved by the user).

## Problem

The main model predicts wear, cracking and flood failure from clues. It never sees a real pothole. `PLAN.md` says "Cameras: OUT"; the user overrode that on 2026-10-03 on the condition that the main plan is not slowed.

Two sources of real evidence exist and need no key:

1. City pothole reports. Charlotte 311 has 24,824 pothole records since 2016 (17,441 with coordinates; 2,423 are requests on state roads). Raleigh has 435 "Potholes & Sinkholes" requests since May 2025 (351 potholes).
2. NCDOT traffic cameras. NCDOT's open ArcGIS layer lists 1,158 cameras with coordinates and a still-image URL; 993 had a recent image on 2026-10-03. A look at 200 random stills at 2:35 pm found 58 with near, clear pavement (cracks and patches visible at full size), 85 with the road too far away or partly blocked, and 57 unusable (mostly rain). No open pothole was seen.

Known limits, stated up front: reports are complaints, so they follow traffic and population; they cover two cities; cameras pan and zoom; 61% of sampled cameras sit on interstates.

## Solution

Four parts, in order of value. Every part writes its own new files and reads the shared tables read-only.

1. Pull the reports and match each to its nearest state road segment.
2. A check: reports per mile per year against NCDOT's rating and the main model's held-out predictions, between roads with similar traffic.
3. A pothole head: a separate LightGBM model on the main model's clues, trained on Charlotte, scored on held-out Charlotte blocks and on Raleigh. It may lose to the baselines; the result is reported either way.
4. Cameras: a polite collector, a camera-to-segment match, stills graded for visible damage by Claude (the user's choice: "you can be vision model"), and a second check from those grades.

## Decisions

- **D1 Report sources and types.** Charlotte: `ServiceRequests311/MapServer/0`, request types `CDOT POTHOLE REPAIR` and `NCDOT POTHOLE REQUEST`. Raleigh: `Ask_Raleigh_Requests/FeatureServer/0`, service `Potholes & Sinkholes`, request type `Pothole`. The type filter is applied in the query and re-checked on the rows received.
- **D2 Count-checked paging.** Every ArcGIS pull first asks the server for the row count, pages in a fixed order, and raises unless the rows received equal that count. A reply with an `error` key, or without a `features` list, raises. Nothing is written on failure. Requests carry an identifying User-Agent and pause between pages.
- **D3 Located reports only.** A report is kept when its longitude and latitude are finite and inside the North Carolina bounding box. Unlocated, out-of-box, undated, future-dated (after the pull time) and duplicate reports are dropped and counted in `pothole_reports.meta.json`. That file is written last and records the sha256 of the report and city-limit files; the label step refuses a file that does not match it.
- **D4 Report table.** `data/raw/pothole_reports.parquet`: `source`, `report_id` (`{source}:{id}`), `request_type`, `received_date`, point geometry in EPSG:4326. One row per `report_id`.
- **D5 City limits.** `data/raw/city_limits.parquet` holds one official polygon per city, from US Census TIGERweb incorporated places (January 2026 vintage; Charlotte publishes no layer of its own). If it cannot be fetched the run stops; there is no fallback to "everywhere".
- **D6 Matching.** In EPSG:32119. A report goes to the single nearest segment within 30 m (the `PLAN.md` distance); ties are broken by `seg_id` order. Unmatched reports are counted. (Changed at execution for Charlotte: see Deviations 1.)
- **D7 Coverage.** `pothole_city` is the city whose polygon contains the segment's midpoint (the midpoint rule of `chips.py` and `features.py`), else null. Outside a city a zero means "not recorded", so the label is blank there.
- **D8 Window and exposure.** City windows start 2023-01-01 (Charlotte) and 2025-05-01 (Raleigh) and end at the pull date. (Raleigh's start was changed after the first critique: see Deviations 2.) A segment's exposure starts at the later of the window start and 1 January of the year after `YEAR_LAST_REHAB` (window start when the rehab year is unknown). Only reports received from that date up to the pull time count. `pothole_exposure_years` is recorded per segment.
- **D9 Label table.** `data/processed/pothole_labels.parquet`, one row per segment in the segment table's order, no geometry: `seg_id`, `pothole_city`, `pothole_exposure_years`, `n_pothole_reports`, `n_pothole_cdot`, `n_pothole_ncdot`, `n_pothole_raleigh`, `n_pothole_all_time`, `y_pothole_rate` (reports per mile per year; blank when length or exposure is not positive), `y_pothole_any` (1.0 or 0.0 inside a city with positive exposure, blank otherwise). The `y_` and `n_` prefixes put these under the shared banned-input rule.
- **D10 Check.** Population: segments inside a city with positive exposure and length. Scores, each used where it exists: NCDOT rating (low is worse), held-out `pred_rate`, held-out `pred_crack`. Within each city and traffic band (thirds of `tr_aadt`, plus a "no count" band), segments are cut into fifths by score. Lift = reports per mile-year in the worst fifth divided by the best fifth, pooled across bands. A band with fewer than 50 segments is left out with a reason. The 95% range comes from resampling whole 5 km blocks (1,000 draws, seed 0; a block drawn twice counts twice; undefined draws are dropped and counted; under 500 valid draws the range is blank). The unadjusted lift is reported beside it. Because no official page confirms that Charlotte's `CDOT POTHOLE REPAIR` type is limited to city streets, the Charlotte check is repeated with the `NCDOT POTHOLE REQUEST` type alone as a sensitivity row.
- **D11 Check gates.** The predictions file must have `pred_rate`, `pred_crack`, `rate_heldout`, `crack_heldout`, unique `seg_id`, and the same segments as the label table; otherwise the check refuses. Rows whose held-out flag is false are never used.
- **D12 Head.** Inputs: `PV + TR +` the terrain columns, through `common.prep`, plus a guard that rejects any column whose name contains `pothole`. Target: `y_pothole_any`. Training rows: Charlotte segments with a label whose exposure covers the whole window (rehab year before 2023, or unknown). Scored two ways: out-of-fold on the shared 5 km folds inside Charlotte, and a Charlotte-only model applied to Raleigh (rehab year before 2025, or unknown).
- **D13 Baselines and pass rule.** On identical rows: a traffic-only model (`TR + pv_LENGTH`), the main model's held-out `pred_rate` as a ranking, and the base rate. The head "beats traffic" when its AUC-PR on held-out Charlotte rows is above the traffic-only model's. A Raleigh score with fewer than 20 positives is flagged "too few to trust". An AUC-PR above 0.9 raises as a probable leak.
- **D14 Head outputs.** `data/processed/pothole_predictions.parquet`: `seg_id`, `pred_pothole`, `pothole_heldout` (false only where the value came from a model that trained on that row), `pothole_tested_area` (inside a city), `pothole_city`. A prediction flag is true only where a prediction exists. When Charlotte has no rows or one class to train on, the result is `status = "unavailable"` with null metrics, which is distinct from a head that loses. `data/processed/results/pothole_head.json` and `.md`. The head never writes `segments.parquet`, `segments_targets.parquet`, `split.parquet` or `predictions.parquet`.
- **D15 Camera list.** `data/raw/cctv/cameras.parquet`, one row per camera: `camera_id`, `status`, `image_status`, `highway`, `county`, `location_name`, `lat`, `lon`, `image_url`, `seg_id`, `seg_dist_m`, `match_rule`. This file is the contract with the flood-depth chat.
- **D16 Camera to segment.** Candidates are segments within 100 m. When the camera's highway name parses to a route class and number (`I`, `US`, `NC`) and a candidate has that class and number, the nearest such candidate wins (`match_rule = route`); otherwise the nearest candidate (`nearest`); with no candidate the match is blank.
- **D17 Collector.** Fetches only cameras whose image is marked recent. At most one request per second per image server; identifying User-Agent. A reply is saved only if it is a complete, decodable JPEG. Stale images (older than 15 minutes), repeats of the camera's last saved image, and placeholder images (the same bytes from three or more cameras in a round) are not kept. Files are written to a temporary name then renamed, as `data/raw/cctv/{camera_id}/{image time, UTC}.jpg`. An existing still is never overwritten. Dark frames are flagged. The run refuses to start with under 2 GB free and stops a round when more than half of at least 40 attempts fail. Every attempt is logged in `data/raw/cctv/stills.parquet`, including when a round is stopped.
- **D18 Review and grading.** `cctv_review.py` builds numbered contact sheets for a view triage (`clear`, `far`, `unusable`) and, for clear views, a full-size crop of the near part of the frame. The grading list holds only an index, the camera id and the file name: no rating, prediction or label. Grades go to `data/raw/cctv/grades.csv` (`camera_id`, `file`, `view`, `damage` in `none | cracks_or_patches | pothole | cant_tell`, `pass`, `grader`, `graded_at`) and must pass the validator. Forty clear stills are graded a second time in shuffled order under new numbers; a key file the graders never see maps them back, so both passes are compared on the same still. Raw agreement and Cohen's kappa are reported.
- **D19 Camera check.** Cameras with a matched segment and a clear, decided grade. Share with visible damage in the worst third against the best third of each score (rating, held-out `pred_rate`, held-out `pred_crack`, `pred_pothole` when present). The 30-camera minimum is applied to each score separately, after keeping only cameras that have that score held out; under it, that score gets a "too few" flag and no ratio.
- **D20 Untouched.** No edits to `src/model/common.py`, `train_tabular.py`, `final_ablation.py`, `train_vit.py`, existing `src/pipeline/*`, top-level `tests/*.py`, `pyproject.toml`, `uv.lock`, the readme (`readme` on this branch, renamed `README.md` on `main` at `baa0d4e`) or `PLAN.md`.
- **D21 Tests.** New folders `tests/potholes/` and `tests/cctv/`, each with its own `conftest.py`. Fast tests use fakes for every network call. Markers `realdata` and `network` gate the rest.

## What will change

New code: `src/pipeline/arcgis_fetch.py`, `src/pipeline/pull_potholes.py`, `src/pipeline/pothole_labels.py`, `src/pipeline/cctv.py`, `src/pipeline/cctv_review.py`, `src/model/pothole_check.py`, `src/model/pothole_head.py`, `src/model/cctv_check.py`.
New tests: `tests/potholes/` and `tests/cctv/`.
New data (git-ignored): `data/raw/pothole_reports.parquet` and `.meta.json`, `data/raw/city_limits.parquet`, `data/raw/cctv/`, `data/processed/pothole_labels.parquet`, `data/processed/pothole_predictions.parquet`, `data/processed/results/pothole_*.{json,md}`, `data/processed/results/cctv_check.{json,md}`.
Not in this change: any edit to the main model; a ready-made pothole detector; city streets that are not in the segment table; merging into `main`; pushing.

## Acceptance criteria

- **AC1** `.venv/bin/python -m pytest -q -m "not realdata and not network"` passes with no failures, including the 83 tests already on the branch.
- **AC2** The real report pull finishes with rows received equal to the server's count for each source, and `pothole_reports.meta.json` records the dropped counts.
- **AC3** `pothole_labels.parquet` has one row per segment (112,443), `y_pothole_any` is blank outside the two cities, and the match rate is printed.
- **AC4** `pothole_check.json` exists with an adjusted lift and its range for each city and score, whatever the values are.
- **AC5** `pothole_head.json` reports head, traffic-only, main-model ranking and base rate on identical rows, for held-out Charlotte and for Raleigh, with the "beats traffic" flag. A losing head is reported, not hidden.
- **AC6** `cameras.parquet` exists with at least 900 cameras marked recent; one daylight round of stills is saved and logged; the graded stills pass the validator; double-grading agreement is reported; `cctv_check.json` exists.
- **AC7** Running the check and the head twice gives identical result files apart from the timestamp.
- **AC8** No regression: every pre-existing test passes; the NCDOT join recomputed in memory from the cached files gives 112,443 / 68,531 / 68,349 (`pull_ncdot --join-only` itself is not run because it rewrites a shared file); the sha256 of `segments_targets.parquet`, `split.parquet`, `predictions.parquet` and the three raw NCDOT files is the same before and after this change's real-data runs; `git diff --stat 64609f1..HEAD` lists only this change's files.

## Failure modes and tests

IDs are the suffixes of the test function names.

**Pulling the reports** (`tests/potholes/test_pothole_pull.py`)
P1 short paging raises. P2 an "OK" reply carrying a notice or error raises and writes nothing. P3 a missing field raises and names it. P4 null or zero coordinates are dropped and counted. P5 out-of-state or swapped coordinates are dropped and counted. P6 only the three pothole types survive. P7 a known epoch value lands on the right day; null and future dates are dropped and counted. P8 one row per report id. P9 a failed write leaves the old file intact. P10 exact columns and EPSG:4326. P11 a pause between pages and the User-Agent on every request (fails if the pause is removed). P12 a failure between writing the reports and the manifest leaves a bundle the label step refuses.

**Matching** (`tests/potholes/test_pothole_labels.py`)
L1 29 m matches, 31 m does not. (As executed: Raleigh 29/31 m, Charlotte 59/61 m; see Deviations 1.) L2 a report near two segments is counted once, on the nearest. L3 far reports stay unmatched and are counted. L4 blank outside the city, 0 or 1 inside (fails if the mask is removed). L5 a segment straddling the edge follows its midpoint. L6 an unknown `seg_id` raises; one row per segment in table order. L7 a report before the exposure start is not counted. L8 exposure years per city and rehab year. L9 zero or missing length gives a blank rate. L10 the two Charlotte types are separate counts. L11 a missing city-limits file raises. L12 a failed write leaves the old file intact. L13 `main()` on the real raw schema computes length from the geometry. L14 a file that does not match the manifest is refused.

**The check** (`tests/potholes/test_pothole_check.py`)
C1 rows without the held-out flag are excluded (fails if the filter is removed). C2 reports that depend only on traffic give an adjusted lift near 1 while the unadjusted lift is well above 1. C3 a band under 50 segments is left out with a reason. C4 hand-worked lift. C5 the range resamples whole blocks and is identical for the same seed. C6 a predictions file with missing columns, duplicate ids or different segments is refused. C7 direction: a low rating and a high predicted rate both count as "worst". C8 the result carries input fingerprints and the code version and is written atomically. C9 segments without a traffic count form their own band. C10 the sensitivity row counts only the NCDOT-type reports. C11 a population with no reports gives blank lifts and a blank range without an error.

**The head** (`tests/potholes/test_pothole_head.py`)
H1 a label column or any `pothole` column in the inputs raises. H2 blank labels never train. H3 the folds equal the shared split and train and test blocks never overlap. H4 no Raleigh segment trains the transfer model (fails if the mask is removed). H5 segments resurfaced inside the window are excluded. H6 a one-class fold is skipped and reported; under 20 positives sets the flag. H7 every baseline is scored on the same rows. H8 two runs are identical. H9 an AUC-PR above 0.9 raises. H10 an unseen category in Raleigh does not crash. H11 `pothole_heldout` and `pothole_tested_area` are true only where real. H12 the shared files' fingerprints are unchanged after a run. H13 built cases: potholes driven by age (head beats traffic-only) and by traffic only (it does not). H14 an empty and H15 a one-class Charlotte population give `unavailable`, with no prediction and no held-out flag.

**Collector** (`tests/cctv/test_cctv_collect.py`)
K1 a short camera list raises. K2 a web page, a notice, an empty body and a cut-off JPEG are not saved. K3 the same bytes from three cameras are flagged as a placeholder and removed. K4 a stale image is flagged and not saved. K5 only cameras marked recent are fetched. K6 no two requests to one server within a second (fails if the pacing is removed). K7 more than half of 40 attempts failing stops the round. K8 a failed download leaves no partial file. K9 an unchanged image is not saved twice. K10 the file name uses the image's own time in UTC. K11 a dark frame is flagged. K12 low disk space refuses to start. K13 git ignores a still's path. K14 `--help` exits 0. K15 timer mode stops after N rounds and one bad camera does not stop a round. K16 changed bytes with an unchanged image time never overwrite the earlier still.

**Camera to segment** (`tests/cctv/test_cctv_match.py`)
M1 distances are in metres. M2 a camera over 100 m from any segment is left blank and counted. M3 a camera named I-40 nearer to a cross street is matched to I-40. M4 odd highway names fall back to the nearest segment. M5 the camera file has the contract columns, one row per camera, and known segment ids.

**Review and grading** (`tests/cctv/test_cctv_review.py`)
G1 sheet labels follow file order (17 stills make two sheets, labels 000 to 016). G2 the crop is the near part of the frame at full size. G3 the grading list has only index, camera id and file. G4 a bad value, an unknown camera, a missing file or a duplicate is refused. G5 agreement and kappa match a hand-worked case. G6 only clear views with a decided grade enter the check. G7 the whole shuffled-repeat path pairs each second grade with the same still.

**Camera check** (`tests/cctv/test_cctv_check.py`)
X1 held-out predictions only. X2 under 30 cameras sets "too few" and gives no ratio. X3 unmatched cameras are excluded and counted. X4 hand-worked shares. X5 over 30 graded cameras but under 30 with a held-out score sets "too few" for that score only.

**Guards** (`tests/potholes/test_pothole_guards.py`)
R1 every new module answers `--help`. R2 no iCloud duplicate files under `src` or `tests`. R3 this branch has not changed any file listed in D20.

**Real data and live servers** (`tests/potholes/test_pothole_real.py`, `tests/cctv/test_cctv_real.py`)
N1 Charlotte rows equal the server's count and are at least 24,824. N2 at least 17,441 located. N3 at least 351 Raleigh potholes. N4 the label table has 112,443 rows. N5 the camera list has at least 1,100 cameras and 900 marked recent.

Historical bug classes pinned: id format mismatch (L6), wrong-road match (L2, M3), "finished but wrong" (P1, K1, C6), zeros that mean "unrecorded" (L4), label and clue dated to different years (L7), in-sample shown as held-out (C1, H11), an "OK" reply with no data (P2, K2), in-place writes on an iCloud folder (P9, L12, K8), shared files overwritten (H12).

## Documentation

- This run spec.
- `docs/reports/2026-10-03_pothole-evidence-plan.md` and its review file.
- `README.md` (still named `readme` on this branch): conditional, confirm at execution. Another chat owns it; the default is to hand the user one results paragraph in this spec's Results section instead of editing it.
- `PLAN.md`: not edited by this change.
- No feature-spec layer; the project had none when P2 was frozen.

## Results (2026-10-03)

Commits on `cctv-potholes`: `a04a18b` (camera list, match, collector), `04f7326` (reports, labels, check, head), `a55033e` (review and camera check), `48568da` (docs), `7f9289b` and `e9094a5` (fixes after the two critique rounds), `de323cf` (fixes after the Codex audit). Every result file below was produced by `de323cf` and carries that stamp; the numbers are identical to the `7f9289b` run.

### Tests and acceptance

| Criterion | Result |
|---|---|
| AC1 fast suite | 197 passed, 0 failed: the 83 that were on the branch and 114 new cases |
| Real-data pins (`-m realdata`) | 11 passed (5 new, 6 existing) |
| Live-server pins (`-m network`) | 3 passed |
| AC2 report pull | Charlotte 24,824 rows and Raleigh 351 rows received. `fetch_all` refuses a pull whose rows differ from the server's count (test P1), so the recorded count is the server's by construction. Drops are in the manifest |
| AC3 labels | 112,443 rows; blank outside the two cities; match counts printed and written to `pothole_labels.meta.json` (3,610 matched, 14,180 unmatched) |
| AC4 check file | written; 9 rows |
| AC5 head file | written; status `ok`; table below |
| AC6 cameras | 1,158 listed, 998 marked recent; one daylight round saved and logged; grades valid; agreement reported; check written |
| AC7 repeatability | check and head each run twice on the first pass: results identical apart from the timestamp, head predictions identical |
| AC8 no regression | pre-existing tests pass; the join recomputed in memory gives 112,443 / 68,531 / 68,349; the six shared files are unchanged (sha256 below, same before the first run and after the last); `git diff --stat 64609f1..HEAD` lists only this change's files |

sha256 of the shared files, before and after:

```
c9711a9f8ee211cdd0c429b8990c33a1f376c7caeb7c34821ba316656534cffe  data/processed/segments_targets.parquet
109573563afa09b68b2a7f5844d424d8cbf344d3746ded0025d8bf9bc95b840e  data/processed/split.parquet
7b996f1c7a26f95e9953e06ddf12bdda0ff48832d1dfe05a1abc132364f2a808  data/processed/predictions.parquet
ea67bdcbc2fd4ab4c686a98d3ee9dc4380218872de58f74cf64d644cbbcd2680  data/raw/ncdot_joined.parquet
2b905277fdbdcfebcf70feebc2c323a448d74e372a85a0967ca846b31c3b5fa0  data/raw/ncdot_master.parquet
d34316ebef771c6742af6dcb84173b2e505df3299258af80a081657106c01e93  data/raw/ncdot_asphalt.parquet
```

Tests added after the critique: K17 (a later placeholder round never deletes an earlier still), K18 (an interrupted round logs what it saved), K19 (a still saved by a round whose log write failed is adopted), X6 (road class is not mistaken for ranking skill), H16 (the gap to the traffic-only model has a range, drawn over whole blocks), H17 (a test city with no usable rows still gets a report). Tightened: K5, K8, K16, M2, L3, L8, L9, L13, C8, C10, H3, H7, H14, G1, R1, R3, N1.

### Reports and labels

- Charlotte: 24,824 pothole records on the server, 17,441 located (7,383 have no coordinates). By type: 16,539 city-street repairs (`CDOT POTHOLE REPAIR`) and 902 state-road requests (`NCDOT POTHOLE REQUEST`).
- Raleigh: 351 pothole records, 349 located. The first is dated 2025-06-18.
- Matched to a state road: 3,610 of 17,790 (20.3%). By type, matched / unmatched: Charlotte city-street repairs 2,935 / 13,604; Charlotte state-road requests 580 / 322; Raleigh 95 / 254. Unmatched reports are on city streets that are not in the segment table, or further from a state road than the match distance.
- Charlotte: 1,324 state segments inside the city, 372 with at least one counted report (28.1%), 1,651 reports counted. Of those 1,651, 1,461 (88%) are city-street repairs that sit within 60 m of a state road and 190 are state-road requests.
- Raleigh: 953 segments, 59 with a report (6.2%); 95 reports matched, 84 counted. Of the other 11, 7 are on segments whose midpoint is outside the city and 4 predate the segment's last resurfacing.

### The check

Lift = reports per mile per year on the worst-ranked fifth of segments divided by the best fifth, with the fifths cut inside groups of roads with similar traffic. Range = 95% from resampling whole 5 km blocks.

| City | Ranking | Reports used | Segments | Reports | Unadjusted | Adjusted lift | Range |
|---|---|---|---|---|---|---|---|
| Charlotte | NCDOT rating | state-road requests only | 1,324 | 190 | 16.12 | 8.93 | 4.25 to 41.06 |
| Charlotte | held-out wear prediction | state-road requests only | 937 | 172 | 8.33 | 3.44 | 1.37 to 13.57 |
| Charlotte | held-out cracking prediction | state-road requests only | 971 | 177 | 6.19 | 8.16 | 3.99 to 24.95 |
| Charlotte | NCDOT rating | all | 1,324 | 1,651 | 20.15 | 7.69 | 4.79 to 12.64 |
| Charlotte | held-out wear prediction | all | 937 | 1,406 | 6.86 | 3.27 | 1.59 to 6.70 |
| Charlotte | held-out cracking prediction | all | 971 | 1,450 | 4.36 | 3.76 | 2.25 to 6.68 |
| Raleigh | NCDOT rating | all | 953 | 84 | 8.34 | 2.56 | 1.10 to 7.95 |
| Raleigh | held-out wear prediction | all | 774 | 65 | 8.34 | 0.42 | 0.17 to 1.42 |
| Raleigh | held-out cracking prediction | all | 877 | 84 | 5.02 | 3.82 | 1.38 to 10.53 |

Reading it:

- The state-road-only rows are the cleaner test, because those requests were filed against state roads; they rest on 190 reports, so their ranges are wide. The "all" rows have tighter ranges but 88% of their reports are city-street repairs that merely sit beside a state road. The two sets agree in direction and rough size.
- In Charlotte the lower end of every range is above 1: roads NCDOT rates worst, and roads the model's held-out predictions rank worst, draw more reports per mile than the best-ranked roads with similar traffic. The rating is never an input to the model, and each prediction is for a block the model did not train on; its wear and cracking targets do come from the same NCDOT survey.
- Raleigh has 84 counted reports. Rating and cracking show lift with wide ranges. The wear prediction does not: its estimate is below 1 (0.42) and its range (0.17 to 1.42) includes 1.
- In Charlotte the busiest third of roads has the fewest reports (137 of 1,651).
- The move from 30 m to 60 m for Charlotte (Deviations 1) does not create the result. Recomputed in memory at 30 m, the "all" rows are: rating 10.22 (5.94 to 20.55), wear 2.98 (1.15 to 6.94), cracking 3.20 (1.48 to 7.22), on 641 or fewer reports.

### The pothole head

Trained on 1,092 Charlotte segments (324 with a report); 26 inputs (the main model's pavement, traffic and terrain clues). The traffic-only model uses the traffic counts and the segment's length.

| Test | Method | Segments | AUC-PR | AUC-PR on shared rows | Hits in top 50 on shared rows |
|---|---|---|---|---|---|
| Charlotte, held-out blocks | pothole head | 1,092 | 0.619 | 0.665 | 88% |
| Charlotte, held-out blocks | traffic-only model | 1,092 | 0.590 | 0.633 | 76% |
| Charlotte, held-out blocks | main model's wear ranking | 804 | 0.588 | 0.588 | 76% |
| Charlotte, held-out blocks | base rate | 1,092 | 0.297 | 0.341 | |
| Raleigh, never seen | pothole head | 922 | 0.136 | 0.141 | 8% |
| Raleigh, never seen | traffic-only model | 922 | 0.151 | 0.149 | 16% |
| Raleigh, never seen | main model's wear ranking | 774 | 0.087 | 0.087 | 4% |
| Raleigh, never seen | base rate | 922 | 0.060 | 0.058 | |

Head minus traffic-only on held-out Charlotte: +0.030, 95% range -0.020 to +0.069 (1,000 block resamples).

Reading it: the head is about twice the base rate on Charlotte blocks it did not train on, and so is the traffic-only model. The gap between them is inside the noise, so the head is **not distinguishable from the traffic-only model** (`distinguishable_from_traffic: false`, which is true only when the range excludes zero on either side; the point-estimate flag `beats_traffic` is true and should not be quoted on its own). Carried to Raleigh, the head is above the base rate and below the traffic-only model, on 55 positives. With these inputs a pothole head adds nothing measurable beyond traffic and segment length. `pothole_predictions.parquet` covers all 112,443 segments, with `pothole_tested_area` true for the 2,277 inside the two cities; everywhere else the prediction is untested.

### Cameras

- List: 1,158 cameras; 1,115 tied to a segment within 100 m (923 by route name, 192 by nearest), 43 unmatched.
- Round `20261003T201812Z_00` (16:18 to 16:23 EDT): 998 attempts, 992 stills saved (78.6 MB), 6 logged as HTTP errors, 1 dark frame, no placeholder or stale images. Four of the six errors were cameras NCDOT lists as recent with an empty link; the collector now skips those.
- View sorting of a random 400: 141 clear (35%), 151 too far or blocked, 108 unusable (mostly rain).
- Damage grades on the 141 clear views: 113 none, 24 cracks or patches, 4 could not tell, 0 potholes.
- Double grading of 40: 35 agree (87.5%), Cohen's kappa 0.60.

| Roads | Ranking | Cameras | Showing damage | Worst third | Best third | Ratio |
|---|---|---|---|---|---|---|
| all | NCDOT rating | 134 | 18% | 33% | 7% | 4.89 |
| all | held-out wear prediction | 110 | 18% | 24% | 8% | 2.92 |
| all | held-out cracking prediction | 98 | 23% | 45% | 9% | 4.85 |
| all | pothole head | 134 | 18% | 31% | 11% | 2.74 |
| interstate | NCDOT rating | 71 | 4% | 4% | 4% | 0.96 |
| interstate | held-out wear prediction | 60 | 5% | 0% | 10% | 0.00 |
| interstate | held-out cracking prediction | 39 | 5% | 0% | 8% | 0.00 |
| interstate | pothole head | 71 | 4% | 0% | 9% | 0.00 |
| other | NCDOT rating | 63 | 33% | 52% | 24% | 2.20 |
| other | held-out wear prediction | 50 | 34% | 35% | 38% | 0.94 |
| other | held-out cracking prediction | 59 | 36% | 55% | 16% | 3.48 |
| other | pothole head | 63 | 33% | 29% | 24% | 1.20 |

Reading it: the ratios over all cameras mostly restate road class. Interstates are rated best and almost never show damage (3 of 71 cameras); other roads show it in 21 of 63. Inside the other roads, with about 20 cameras per third and no range computed, the rating (11 against 5 damaged cameras) and the cracking prediction (11 against 3) lean the right way, the cracking prediction more clearly; the wear prediction (6 against 6) and the pothole head (6 against 5) show nothing. Inside interstates there is too little damage to say anything. The cameras are weak support for the rating and the cracking prediction and no support for the wear prediction or the head. No still showed an open pothole.

### Deviations from the plan

1. **Charlotte match distance 60 m, not 30 m** (D6, L1). The first live pull showed Charlotte's points are address locations: its state-road requests sit a median 44 m from the centreline and 30 m kept 173 of 902 (60 m keeps 580). Raleigh stays at 30 m. The Charlotte results at 30 m are given under "The check".
2. **Raleigh's window starts 2025-06-18, not 2025-05-01** (D8). Changed after the first critique, not at execution: the first Raleigh pothole report in the layer has that date, and starting earlier counted about seven weeks in which nothing was being collected.
3. **A failed still write is logged as `save_error` and the round continues**; it counts toward the stop rule (tested in K8).
4. **A cut-off download is caught by its missing end marker.** A truncated file that happened to end with the JPEG end marker would decode and be kept; K2 uses a real cut-off.
5. **H13's second case allows the head up to 0.05 above the traffic-only model**, where the plan said 0.02. The real gap of 0.030 is inside that tolerance, which is the same point the gap range makes.
6. **R3 compares against the merge base with `main`**, not the fixed commit `64609f1`, so it stays meaningful after `main` moves. It is empty by construction once the branch is merged, cannot see untracked files, and skips when there is no `main`.
7. **N1, N3 and N5 each have a `realdata` and a `network` form.** N1's bookkeeping check (kept plus dropped equals rows received) is a consistency check on the manifest; equality with the server's count is enforced in `fetch_all` and tested by P1.
8. **Grading used helper agents as planned.** Their part files (`triage_part*.csv`, `damage_part*.csv`, `damage_list_part*.txt`) stay in the review folder beside the merged answers. All 141 clear views were graded, below the cap of 160.
9. **Added after the critique, not in the plan:** a label run now stops on a segment with no geometry (frozen L9 said "blank rate"; zero length still gives a blank rate, and the real table has no such segment); the review step's manifest, repeat key and grades file are swapped in whole; a still left on disk by a round whose log write failed is adopted by the next round; the camera check validates grades without needing the stills; the head's gap range (which needs at least half its draws to be valid) and `distinguishable_from_traffic` flag; top-50 hits on the shared rows; a refusal when the targets table's folds differ from `split.parquet`; interstate and other-road rows in the camera check; grade validation and full input fingerprints in the camera check; `pothole_labels.meta.json`; a `-dirty` suffix on the code stamp when `src/` has uncommitted changes; skipping cameras with an empty link; logging an interrupted round; leaving identical bytes alone and never deleting a still saved by an earlier round.
10. **Charlotte's timestamps look like local time stored as UTC** (reports peak between 08 and 16). D4 calls them UTC. The shift is at most five hours and moves no report across a window boundary in this data.
11. **An unavailable head result carries `charlotte_heldout: null` and `raleigh_transfer: null`** (after the critique; the first version omitted the keys).
12. **The first result files were stamped `64609f1`**, the commit before the code existed in git, because they were generated before the code was committed. They were regenerated at `7f9289b`.

### Critique and audit record

- Claude critique, round 1 (after `48568da`): Needs-work. No blocking findings; 6 should-fix and 12 minor. The should-fix items: the camera ratio was mostly road class; "beats traffic" was inside the noise; the result files carried the wrong code stamp; placeholder clean-up could delete an earlier round's still; the `save_error` path was untested; the headline Charlotte lift rested on the mixed report set. All 18 were addressed in `7f9289b` and in this section.
- Claude critique, round 2 (after `a05ee30`): 17 of the 18 resolved and one (the UTC label) left as a recorded limitation; every Results number matched the files except one clause. Overall Needs-work for one new should-fix: the head's report crashed when the gap was undefined. That and the seven minor notes (a wrong reason for the 11 uncounted Raleigh reports, an unlogged still never adopted, an incomplete deviations list, a test that did not pin whole-block resampling, no minimum draw count and a one-sided flag, the camera check needing the stills on disk, two wording points) were addressed in `e9094a5` and in this section. The critic did not run the three live-server pins; they were run by the implementer.
- Claude critique, round 3 (after `b9518c8`, narrow): Pass on all seven dimensions; two wording leftovers, fixed here.
- Codex audit, round 1 (at `b9518c8`): Overall Fail on plan adherence, for two failure paths. (1) A camera request cut short by an interrupt was missing from the round's log. (2) The head's report crashed when the test city had no usable rows. Other dimensions: scope discipline, review compliance and documentation Excellent; test coverage, freeze integrity and regression check Acceptable (its sandbox could not create temporary folders, so 82 of the fast tests errored at setup there; no assertion failed; it reproduced the result files, the six shared hashes and the join counts independently). Both findings were fixed in `de323cf`: an interrupted attempt is logged with status `interrupted` (K18), and a blank base rate renders (H17).
- Not verifiable from files: the 30 m figures under "The check" were recomputed in memory by the implementer and by the critic and agree, but are not stored.

### Limits to state with any of these numbers

- Reports are complaints. They cover two cities and follow where people live and drive; the traffic bands remove only part of that.
- 88% of the Charlotte reports counted are city-street repairs within 60 m of a state road; some belong to the side street.
- The Raleigh test has 84 counted reports and 55 positive segments.
- The pothole head is not distinguishable from a traffic-and-length model.
- Camera grades come from one round on a rainy afternoon, graded by Claude; two passes agreed on 35 of 40. The camera comparison has about 20 cameras per group once road class is held level.

### Paragraph for the README (for the user to paste; this change does not edit the README)

> **Checked against real potholes.** Charlotte and Raleigh publish located pothole reports, and we matched 3,610 of them to state road segments. In Charlotte, roads our model's held-out predictions rank worst draw about three times the pothole reports per mile of the roads it ranks best, comparing roads with similar traffic (wear: 3.3, 95% range 1.6 to 6.7; cracking: 3.8, range 2.3 to 6.7). NCDOT's own rating, which is never an input to the model, gives 7.7 (range 4.8 to 12.6). Most of those reports are city-street repairs beside a state road; using only the 190 requests filed against state roads gives the same picture with wider ranges. Raleigh has 84 usable reports: its ranges are wide and the wear prediction shows no lift there. A separate pothole model trained on Charlotte did no better than a model that knows only traffic and segment length. We also graded 141 clear NCDOT traffic-camera stills; none showed an open pothole, and once interstates are set apart the camera evidence is too thin (about 20 cameras per group) to count as more than weak support.
