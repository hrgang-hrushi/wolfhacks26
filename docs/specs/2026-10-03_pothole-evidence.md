# Run spec: real pothole evidence (reports, cameras, pothole head) (2026-10-03)

Status: executed 2026-10-03 on branch `cctv-potholes` (not merged, not pushed); results at the end. P1 frozen 2026-10-03, P2 frozen 2026-10-03 (standard mode). Plan reviewed by Codex 2026-10-03: ten findings, all accepted (tests C11, H14, H15, K16, L13, L14, P12, G7 and X5 added; AC8 reworded so the regression check never rewrites shared data). Branch `cctv-potholes`, which contains `model-hardening` at `64609f1` (fast-forward merge, approved by the user).

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
- **D6 Matching.** In EPSG:32119. A report goes to the single nearest segment within its source's match distance; ties are broken by `seg_id` order. Unmatched reports are counted. Raleigh: 30 m (the `PLAN.md` distance; its points sit on the street). Charlotte: 60 m. This was 30 m when P2 was frozen and was changed at execution on the evidence of the first live pull: Charlotte's points are address locations, its state-road requests sit a median 44 m from the centreline, and 30 m kept only 173 of 902 of them (60 m keeps 580).
- **D7 Coverage.** `pothole_city` is the city whose polygon contains the segment's midpoint (the midpoint rule of `chips.py` and `features.py`), else null. Outside a city a zero means "not recorded", so the label is blank there.
- **D8 Window and exposure.** City windows start 2023-01-01 (Charlotte) and 2025-05-01 (Raleigh) and end at the pull date. A segment's exposure starts at the later of the window start and 1 January of the year after `YEAR_LAST_REHAB` (window start when the rehab year is unknown). Only reports received from that date up to the pull time count. `pothole_exposure_years` is recorded per segment.
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
L1 Raleigh: 29 m matches, 31 m does not; Charlotte: 59 m matches, 61 m does not. L2 a report near two segments is counted once, on the nearest. L3 far reports stay unmatched and are counted. L4 blank outside the city, 0 or 1 inside (fails if the mask is removed). L5 a segment straddling the edge follows its midpoint. L6 an unknown `seg_id` raises; one row per segment in table order. L7 a report before the exposure start is not counted. L8 exposure years per city and rehab year. L9 zero or missing length gives a blank rate. L10 the two Charlotte types are separate counts. L11 a missing city-limits file raises. L12 a failed write leaves the old file intact. L13 `main()` on the real raw schema computes length from the geometry. L14 a file that does not match the manifest is refused.

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

Code commits on `cctv-potholes`: `a04a18b` (camera list, match, collector), `04f7326` (reports, labels, check, head), `a55033e` (review and camera check).

### Tests and acceptance

| Criterion | Result |
|---|---|
| AC1 fast suite | 191 passed (the 83 that were on the branch and 108 new cases from 88 new test functions), 0 failed |
| Real-data pins (`-m realdata`) | 11 passed (5 new, 6 existing) |
| Live-server pins (`-m network`) | 3 passed |
| AC2 report pull | Charlotte 24,824 received = server count; Raleigh 351 received = server count; drops recorded in the manifest |
| AC3 labels | 112,443 rows; blank outside the two cities; match rate printed (20.3%) |
| AC4 check file | written; 9 rows |
| AC5 head file | written; status `ok`; table below |
| AC6 cameras | 1,158 listed, 998 marked recent; one daylight round saved and logged; grades valid; agreement reported; check written |
| AC7 repeatability | check and head each run twice: results identical apart from the timestamp; head predictions identical |
| AC8 no regression | pre-existing tests pass; join recomputed in memory gives 112,443 / 68,531 / 68,349; all six shared-file sha256 values unchanged; `git diff --stat 64609f1..HEAD` lists only this change's files |

### Reports and labels

- Charlotte: 24,824 pothole records on the server, 17,441 located (7,383 have no coordinates). By type: 16,539 city-street repairs (`CDOT POTHOLE REPAIR`) and 902 state-road requests (`NCDOT POTHOLE REQUEST`).
- Raleigh: 351 pothole records, 349 located.
- Matched to a state road: 3,610 of 17,790 (20.3%): 2,935 Charlotte city-street repairs, 580 Charlotte state-road requests, 95 Raleigh reports. The rest are on city streets that are not in the segment table.
- Charlotte: 1,324 state segments inside the city, 372 with at least one counted report (28.1%), 1,651 reports counted. Raleigh: 953 segments, 59 with a report (6.2%), 84 reports counted.

### The check

Lift = reports per mile per year on the worst-ranked fifth of segments divided by the best fifth, with the fifths cut inside groups of roads with similar traffic. Range = 95% from resampling whole 5 km blocks.

| City | Ranking | Reports used | Segments | Reports | Unadjusted | Adjusted lift | Range |
|---|---|---|---|---|---|---|---|
| Charlotte | NCDOT rating | all | 1,324 | 1,651 | 20.2 | 7.7 | 4.8 to 12.6 |
| Charlotte | held-out wear prediction | all | 937 | 1,406 | 6.9 | 3.3 | 1.6 to 6.7 |
| Charlotte | held-out cracking prediction | all | 971 | 1,450 | 4.4 | 3.8 | 2.3 to 6.7 |
| Raleigh | NCDOT rating | all | 953 | 84 | 8.3 | 2.5 | 1.1 to 7.9 |
| Raleigh | held-out wear prediction | all | 774 | 65 | 8.3 | 0.4 | 0.2 to 1.4 |
| Raleigh | held-out cracking prediction | all | 877 | 84 | 5.1 | 3.8 | 1.4 to 10.6 |
| Charlotte | NCDOT rating | state-road requests only | 1,324 | 190 | 16.1 | 8.9 | 4.3 to 41.1 |
| Charlotte | held-out wear prediction | state-road requests only | 937 | 172 | 8.3 | 3.4 | 1.4 to 13.6 |
| Charlotte | held-out cracking prediction | state-road requests only | 971 | 177 | 6.2 | 8.2 | 4.0 to 25.0 |

Reading it: in Charlotte the roads NCDOT rates worst draw about eight times the pothole reports of the best-rated roads with similar traffic, and the model's held-out predictions, which never see the rating, still separate them by a factor of three to four. Raleigh has 84 reports, so its ranges are wide; the wear prediction there shows no lift (range 0.2 to 1.4). Reports are fewest on the busiest third of roads (137 of 1,651 in Charlotte): people do not file address-based reports on freeways.

### The pothole head

Trained on 1,092 Charlotte segments (324 with a report); 26 inputs (the main model's pavement, traffic and terrain clues).

| Test | Method | Segments | AUC-PR | AUC-PR on shared rows | Hits in top 50 |
|---|---|---|---|---|---|
| Charlotte, held-out blocks | pothole head | 1,092 | 0.619 | 0.665 | 88% |
| Charlotte, held-out blocks | traffic-only model | 1,092 | 0.590 | 0.633 | 76% |
| Charlotte, held-out blocks | main model's wear ranking | 804 | 0.588 | 0.588 | 76% |
| Charlotte, held-out blocks | base rate | 1,092 | 0.297 | 0.341 | |
| Raleigh, never seen | pothole head | 922 | 0.136 | 0.141 | 10% |
| Raleigh, never seen | traffic-only model | 922 | 0.151 | 0.149 | 18% |
| Raleigh, never seen | main model's wear ranking | 774 | 0.087 | 0.087 | 4% |
| Raleigh, never seen | base rate | 922 | 0.060 | 0.058 | |

Reading it: on Charlotte blocks it did not train on, the head is twice the base rate and beats the traffic-only model by a small margin (0.619 against 0.590; no range was computed for that gap). Carried to Raleigh, which it never saw, it is above the base rate but does not beat the traffic-only model (0.136 against 0.151, 55 positives). Most of what predicts a report is the kind of road and its traffic; the pavement clues add a little in Charlotte and nothing measurable in Raleigh. `pothole_predictions.parquet` covers all 112,443 segments, with `pothole_tested_area` true for the 2,277 inside the two cities; everywhere else the prediction is untested.

### Cameras

- List: 1,158 cameras; 1,115 tied to a segment within 100 m (923 by route name, 192 by nearest), 43 unmatched.
- Round `20261003T201812Z_00` (16:18 to 16:23 EDT): 998 attempts, 992 stills saved (78.6 MB), 6 HTTP errors, 1 dark frame, no placeholder or stale images.
- View sorting of a random 400: 141 clear (35%), 151 too far or blocked, 108 unusable (mostly rain).
- Damage grades on the 141 clear views: 113 none, 24 cracks or patches, 4 could not tell, 0 potholes.
- Double grading of 40: 35 agree (87.5%), Cohen's kappa 0.60.

| Ranking | Cameras | Showing damage | Worst third | Best third | Ratio |
|---|---|---|---|---|---|
| NCDOT rating | 134 | 18% | 33% | 7% | 4.9 |
| held-out wear prediction | 110 | 18% | 24% | 8% | 2.9 |
| held-out cracking prediction | 98 | 23% | 45% | 9% | 4.8 |
| pothole head (untested outside the two cities) | 134 | 18% | 31% | 11% | 2.7 |

Reading it: cameras on the roads ranked worst show cracking or patching three to five times as often as cameras on the roads ranked best. The groups are small (about 45 cameras per third, 24 damaged views in all) and no range was computed, so this supports the report check rather than standing on its own. No still showed an open pothole.

### Deviations from the plan

1. **Charlotte match distance 60 m, not 30 m** (D6). The first live pull showed Charlotte's points are address locations: its state-road requests sit a median 44 m from the centreline and 30 m kept 173 of 902. Raleigh stays at 30 m. Test L1 pins both.
2. **A failed still write is logged as `save_error` and the round continues**; it counts toward the stop rule. The plan did not cover a write failure inside a round.
3. **A cut-off download is caught by its missing end marker.** A truncated file that happened to end with the JPEG end marker would decode and be kept; test K2 uses a real cut-off (no end marker).
4. **H13's second case allows the head up to 0.05 above the traffic-only model**, where the plan said 0.02, to keep the test stable on 1,000 fixture rows.
5. **R3 compares against the merge base with `main`**, not the fixed commit `64609f1`, so the test stays meaningful after `main` moves and is empty by construction once merged.
6. **N1, N3 and N5 each have a `realdata` and a `network` form**: the on-disk pin and a live count that must not have shrunk.
7. **Grading used helper agents as planned**; their part files (`triage_part*.csv`, `damage_part*.csv`, `damage_list_part*.txt`) stay in the review folder beside the merged answers.
8. **The `clear` views graded were all 141**, below the cap of 160, so no sampling was needed.

### Limits to state with any of these numbers

- Reports are complaints. They cover two cities and follow where people live and drive; the traffic bands remove only part of that.
- Charlotte's city-street repairs are matched to a state road when they sit within 60 m of one, so some belong to the side street. The state-road-only rows are the cleaner test and agree with the full rows.
- The Raleigh test has 84 reports and 55 positive segments.
- Camera grades come from one round on a rainy afternoon, graded by Claude; agreement between two passes was 87.5%.

### Paragraph for the README (for the user to paste; this change does not edit the README)

> **Checked against real potholes.** Charlotte and Raleigh publish located pothole reports. We matched 3,610 of them to state road segments. In Charlotte, the roads NCDOT rates worst draw about eight times the reports per mile of the best-rated roads with similar traffic (95% range 4.8 to 12.6), and our model's held-out predictions, which never see the rating, separate them by a factor of three to four. Raleigh has only 84 matched reports and its ranges are wide. A separate pothole model trained on Charlotte beats a traffic-only model by a small margin on held-out Charlotte blocks (AUC-PR 0.62 against 0.59, base rate 0.30) and does not beat it when carried to Raleigh. We also graded 141 clear NCDOT traffic-camera stills: cameras on the worst-ranked roads show cracking or patching three to five times as often as cameras on the best-ranked roads, with about 45 cameras per group.
