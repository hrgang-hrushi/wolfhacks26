# Run spec: Helene depth map (2026-10-03)

Status: executed 2026-10-03 on branch `helene-depth` (not merged, not pushed); results, deviations and audit verdicts are at the end. The Decisions and the test list below are the frozen design plus the additions from the Codex plan review; what changed at execution is listed under Deviations, not edited in above (parenthetical pointers excepted). P1 frozen 2026-10-03, P2 frozen 2026-10-03 (standard mode). Plan reviewed by Codex 2026-10-03: eight findings, all accepted (tests B11, B12, D16, E12, E13, E14, E15 and F11 added; D4, D14, D17, D19, D22 and D23 tightened). Branch `helene-depth`, created from `main` at `65162c5`, in the worktree `.claude/worktrees/helene-depth`. Plan: `docs/reports/2026-10-03_helene-depth-map-plan.md`. Feature doc: `docs/features/HELENE_DEPTH_MAP.md`.

## Problem

For a road beside a river in western North Carolina we know whether it failed in Hurricane Helene, but not how deep the water was. No photo, satellite pass or camera caught the peak (27 September 2024, afternoon). The only evidence is 2,193 high-water marks surveyed by the Army Corps (USACE) in 12 mountain counties, each with a water-surface elevation. Depth is the water surface minus the ground.

On the project's 30 m terrain that subtraction is not believable. Measured on 2026-10-03 against the 280 marks where surveyors also taped the depth (typical taped depth 1.04 m):

| | 30 m ground | 10 m ground |
|---|---|---|
| Typical miss against the tape | 0.61 m | 0.20 m |
| Worst tenth miss by more than | 2.63 m | 1.24 m |
| Marks where water comes out below ground | 34% | 22% |
| Agreement with the tape (correlation) | 0.36 | 0.65 |

The water level between marks was checked by hiding each mark and guessing it from its neighbours on the same stream:

| Nearest other mark along the stream | Typical miss |
|---|---|
| Within 100 m | 0.22 m |
| 100 to 250 m | 0.42 m |
| 250 to 500 m | 0.59 m |
| 500 m to 1 km | 0.77 m |
| Over 1 km | 0.9 m and up |

Both together, at 267 taped marks: typical miss 0.50 m, one in ten off by more than 1.6 m. So depth near the marks is believable to about half a metre: good enough for depth bands, not for centimetres.

## Solution

1. Save 10 m ground only for the strips along the marked streams.
2. On each stream, line the marks up in survey order and draw the water level between them.
3. For each nearby road, take a point every 30 m, read the water level at the nearest spot on the stream line, and subtract the ground.
4. Set aside points on or under bridges, where the ground data shows the river bed instead of the road.
5. Per segment, report the deepest water, the share under water, how many marks informed it, the distance to the nearest mark and a confidence grade.
6. Measure the error by hiding stretches of marks and guessing them back, and against the tape heights.
7. Write one file keyed by `seg_id`. Roads too far from any mark stay blank, not zero.

## Decisions

- **D1 Marks.** Input `data/raw/flood_usace_hwm_helene.geojson` (read-only). Required columns: `HWM_ID`, `Stream`, `Watershed`, `Point_Number_on_Stream`, `HWM_Elevation__ft_`, `Measured_Height__ft_`, `HWM_Quality`, `HWM_Type`, geometry in EPSG:4326. A missing column or a file with no usable marks stops the run. Water surface in metres = feet x 0.3048 (NAVD88). A taped height of 0 means "not measured" and becomes blank. Dropped and counted: marks outside the box lon -84.4 to -81.0, lat 34.9 to 36.7; a blank or zero water height; a repeated `HWM_ID` (first kept). (One more drop rule and three reading rules were added at execution: see Deviations 15.)
- **D2 Stream groups.** A stream is `Stream` + `Watershed` (101 groups; Cane Creek and Crabtree Creek are each two different creeks). Marks are ordered by `Point_Number_on_Stream` as a number.
- **D3 Which marks draw the line.** Marks graded Poor or Very Poor (306) do not draw the water line; they miss about twice as much as Excellent or Good marks (0.65 m against 0.31 to 0.37 m). They are still scored, separately.
- **D4 10 m ground.** USGS 3DEP 1/3 arc-second seamless ground (`py3dep.static_3dep_dem(bbox, 4326, 10)`), saved as tiles of 0.1 degree with 3 extra cells on every side, in the source grid (EPSG:4269, no resampling), under `data/processed/dem10_helene/`. Only tiles that hold a mark or a sampled road point are fetched (somewhat more than the 84 that lie within 400 m of a stream line, because candidate roads run past that band). A reply is refused unless it is in EPSG:4269, unrotated, at 1/3 arc-second, and covers the tile it was asked for. A manifest records each tile's sha256, shape and grid. A tile is written to a temporary name and renamed.
- **D5 Reading the ground.** Bilinear from the four surrounding cells of the tile that holds the point; a blank cell among the four gives blank ground. A missing tile, a tile at another resolution, or a tile whose sha256 differs from the manifest stops the run and names the tile. There is no fall-back to the 30 m ground.
- **D6 Unit tripwire.** If water surface minus 10 m ground at the line-drawing marks has a median outside -1 to 3 m, the run stops ("units or datum wrong").
- **D7 Stream line.** For each group, the polyline through its line-drawing marks in order, in EPSG:32119 (metres). Marks less than 1 m apart along the line become one point with their mean level. The water level along the line is a straight-line interpolation between neighbouring marks.
- **D8 Where a road point gets a level.** Only "live" parts of a line count: within 1,000 m along the line of a mark (`REACH_M`). A road point takes the nearest live part within 300 m to the side (`SIDE_CAP_M`); if two streams qualify the nearer wins. A point is matched to a live part only where its foot on the line falls inside that part, or at a real bend of the line; it is never slid along the line to the edge of a live part. (Tightened at execution: see Deviations 1 and 2.) Past the first or last mark of a line, and for a stream with one mark, a level is given only within 100 m of that mark (`END_CAP_M`), at that mark's level. Everything else is "not assessed" (blank), never "dry".
- **D9 Confidence.** High when the nearest mark is within 250 m along the line (`HIGH_CONF_M`); low otherwise, and always low under the 100 m end rule. (How the distance is measured at a bend was settled after the review: see Deviations 13.)
- **D10 Road points.** Each segment's geometry (from `data/processed/segments_geom.parquet`, EPSG:4326) is projected to EPSG:32119 and sampled at even spacing of at most 30 m, both ends included (a 300 m road gets 11 points; a shorter road gets its two ends). A multi-part line is sampled part by part. An empty geometry is skipped and counted. Only segments within 300 m of a live line part are sampled.
- **D11 Depth.** Depth = water level minus ground; below zero is recorded as 0 and "dry".
- **D12 Bridges.** The ground data has every bridge removed, so a road on a bridge reads as if it sat on the river bed. A road point is set aside when any of these holds:
  1. it is within 60 m of a bridge in `data/raw/helene_structures.parquet` (read-only; a structure counts as a bridge unless its type names a culvert or pipe: `culvert|pipe|rcbc|cmp|corrugated|aluminum|multi-plate`, any letter case; a blank type counts as a bridge);
  2. it sits in a notch: its ground is at least 3 m below both neighbours 30 m away, or both neighbours 60 m away;
  3. it lies on a steep bank next to a set-aside point: walking away from a set-aside point, each further point is set aside while the ground climbs more than 2 m per 30 m; the point at the top of the climb is kept.
  Set-aside points count toward nothing. A missing bridge list stops the run.
- **D13 Headline depth.** `y_helene_depth_max_m` is the deepest water held by two neighbouring kept points (the larger of min(depth_i, depth_i+1) over neighbouring pairs). One lone deep point cannot set it. The raw single-point maximum is kept beside it.
- **D14 Per-segment columns.** `seg_id`, `y_helene_depth_assessed` (true when at least two neighbouring points were kept, which is what a headline needs), `y_helene_depth_max_m`, `y_helene_depth_point_max_m`, `y_helene_depth_wet_share` (kept points with depth above 0 divided by kept points), `y_helene_depth_band` (`dry`, `under 0.3 m`, `0.3 to 1 m`, `1 to 2 m`, `over 2 m`, from the headline), `y_helene_depth_conf` (`high` or `low`), `y_helene_depth_mark_dist_m` (distance along the line to the nearest mark: the larger of the two for the pair that set the headline; the median over kept points when dry), `y_helene_depth_typical_miss_m` (the typical miss for that distance, from the hidden-mark table; blank when that band has under 30 marks), `y_helene_depth_stream`, `n_helene_depth_marks` (distinct marks behind the kept points), `n_helene_depth_points` (kept points), `n_helene_depth_set_aside`. Ties are settled the same way every time: the headline pair is the first pair in road order that reaches the maximum; the distance, confidence and stream come from that pair (the stream of its deeper point, the first point when equal); when dry, the stream is the most common among kept points, alphabetical on a tie. `y_helene_depth_conf` is `high` when both points of the pair that set the headline have a mark within 250 m along the line and neither falls under the 100 m end rule (when dry: at least half of the kept points). Not assessed: every `y_` value blank except `y_helene_depth_assessed = False`; `n_helene_depth_marks` 0.
- **D15 Names ban themselves.** Every column but `seg_id` starts with `y_` or `n_`, so `src.model.common.check_features` rejects them as model inputs. This is an outcome of the storm, not a clue.
- **D16 Output.** `data/processed/flood_helene_depth.parquet`: one row per segment in the order of `data/processed/segments.parquet` (112,443). `data/processed/flood_helene_depth_points.parquet`: one row per sampled road point (segment, position, ground, water level, depth, flags). The two tables, the validation file and the notes file are all staged under temporary names and renamed only when all four are ready, notes last; a failure while staging leaves the previous files untouched. A depth above 15 m among kept points stops the run and names the segment. (Changed at execution: see Deviations 3.)
- **D17 Hidden-mark test.** For each line-drawing mark, hide every line-drawing mark of its stream within a stretch of 0, 250 or 500 m along the line (0 hides only the mark itself), redraw that stream's line, and guess the mark's level with the same code that serves road points. The headline is the stretch-0 run. The table by distance uses, per mark and distance band (0-100, 100-250, 250-500, 500-1,000 m), the result from the smallest stretch that lands in that band. A band with under 30 marks is reported as "too few" (an empty band as 0 marks). If the stretch-0 run yields fewer than 30 guesses in total the build refuses, because no error number can be stated. Poor and Very Poor marks are guessed from the full lines and scored apart. The typical miss is also listed per stream group, so a stream whose survey numbering folds back on itself shows up by name.
- **D18 Tape tests.** On marks with a taped height: (a) ground only: the mark's own level minus 10 m ground against the tape; (b) end to end: the hidden-mark guess minus 10 m ground against the tape.
- **D19 Gate against 30 m.** On the taped marks that have ground in both, the 10 m typical miss must be below the 30 m typical miss (`data/processed/dem/dem.tif`) and at most 0.25 m, or the build refuses. With no taped mark that has ground, the build refuses. If the 30 m file is absent the build refuses unless run with `--skip-30m-check`, which is recorded.
- **D20 Range.** A 95% range for the headline numbers by resampling whole stream groups, 1,000 draws, seed 0.
- **D21 Check against the failure labels.** Among assessed segments in `segments.parquet`, the share with `y_helene_failed = 1` for segments with at least 0.3 m of water against dry ones. Reported, not a gate.
- **D22 Notes file.** `data/processed/flood_helene_depth.meta.json`, written last: every setting, counts, the validation headline, sha256 of the marks file, the tile manifest, the bridge list, the ordered `seg_id` list, both output files, the sha256 of each shared input before and after the run, and the git commit. A file that is absent is recorded as such. `load_depth()` refuses when the sha256 of the depth, points or validation file, the marks file, the tile manifest or the `seg_id` list no longer match the notes.
- **D23 Validation file.** `data/processed/flood_helene_depth_validation.json`: the numbers of D17 to D21. The gates (D6, D17, D19) run before the build; the label comparison (D21) and the build counts are added after the per-segment table exists, so they always describe the table that is written. `--validate-only` stops after the gates and writes nothing. Identical between runs apart from the timestamp, which lives only in the notes file.
- **D24 Writes only its own files.** The code writes only `data/processed/flood_helene_depth*` and `data/processed/dem10_helene/`; a write to any other path raises. (As built this is a check on the file name: see Deviations 14.)
- **D25 Not touched.** `segments.parquet` and its columns, the model code, `pyproject.toml`, `uv.lock`, `src/pipeline/pull_helene.py`, `helene_points.py`, `helene_labels.py`, `README.md`, `PLAN.md`. No new dependency. No push or merge.

Settings in one place (recorded in the notes file and pinned by test F6): `SPACING_M 30`, `SIDE_CAP_M 300`, `REACH_M 1000`, `HIGH_CONF_M 250`, `END_CAP_M 100`, `MERGE_M 1`, `BRIDGE_M 60`, `NOTCH_M 3`, `BANK_RISE_M 2` per 30 m, `MAX_DEPTH_M 15`, `TRIPWIRE_M (-1, 3)`, `MAX_TAPE_MISS_M 0.25`, `BANDS_M (0.3, 1, 2)`, `HOLD_STRETCHES_M (0, 250, 500)`, `DIST_BANDS_M (100, 250, 500, 1000)`, `MIN_BAND_N 30`, `BOOT_N 1000`, `SEED 0`, `NO_LINE_GRADES (Poor, Very Poor)`, `TILE_DEG 0.1`, `HALO_PX 3`. (Two settings were added at execution, `MAX_LIFT_M 2` and `MAX_TOO_DEEP_SHARE 0.005`: see Deviations 1 and 3.)

## What will change

New files only:

- `src/pipeline/helene_dem10.py`: fetch, save and read the 10 m ground tiles.
- `src/pipeline/helene_depth.py`: marks, stream lines, road points, bridges, depth, error tests, output.
- `tests/helene_depth/`: `conftest.py`, `test_hd_marks.py`, `test_hd_ground.py`, `test_hd_profile.py`, `test_hd_points.py`, `test_hd_validate.py`, `test_hd_output.py`, `test_hd_guards.py`, `test_hd_real.py`.
- `docs/specs/2026-10-03_helene-depth-map.md`, `docs/features/HELENE_DEPTH_MAP.md`, `docs/reports/2026-10-03_helene-depth-map-plan.md` and its review file.
- Data (git-ignored): `data/processed/dem10_helene/`, `data/processed/flood_helene_depth.parquet`, `flood_helene_depth_points.parquet`, `flood_helene_depth_validation.json`, `flood_helene_depth.meta.json`.

## Acceptance criteria

`PY=/Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python`, run from the worktree root.

- **AC1** `$PY -m pytest -q tests/helene_depth -m "not realdata and not network"` prints 80 passed (81 as executed: see Deviations 1). `$PY -m pytest -q tests/helene_depth -m "realdata and not network"` prints 12 passed. `$PY -m pytest -q tests/helene_depth -m network` prints 1 passed. `$PY -m pytest -q -m "not network"` prints 662 passed, 2 skipped, 0 failed (663 as executed) (baseline on `main` at `65162c5`: 570 passed, 2 skipped).
- **AC2** On the 280 taped marks the 10 m typical miss is below the 30 m typical miss and at most 0.25 m. If not, execution stops and the user is told.
- **AC3** The hidden-mark miss is reported per distance band with counts and a range.
- **AC4** The end-to-end tape miss is reported in plain words, whatever it is.
- **AC5** `flood_helene_depth.parquet` has 112,443 rows in segment-table order, the D14 columns, blanks where not assessed, and a notes file that `load_depth()` accepts.
- **AC6** Biltmore Village (`ncdot:21000025011:7.235`) is at least 2 m deep. The downtown Asheville hilltop (`ncdot:20000025011:11.328`) is dry or not assessed. The segment that starts on the Smith Mill Creek bridge (`ncdot:40001338011:0.000`, bridge 100726) has its river-end points set aside and reports under 1 m. (As executed it reports nothing at all: see Deviations 9.)
- **AC7** Two runs give identical output and validation files; only the notes file's timestamp differs.
- **AC8** Nothing else changed: no existing test fails; the sha256 of every shared input is the same before and after the real run; `git diff --name-only main...HEAD` lists only the files under "What will change".

A regression is: any of the 570 existing tests failing, a shared data file's sha256 changing, or any change to a file listed in D25.

## Failure modes and tests

IDs are the suffixes of the test function names. Frozen at P2 unless marked "added at planning".

**Reading the marks** (`tests/helene_depth/test_hd_marks.py`)
A1 feet become metres (2,100.75 ft gives 640.31 m). A2 a taped height of 0 becomes blank, never a zero depth. A3 a mark outside the box is dropped and counted. A4 two creeks sharing a name stay separate (fails if grouped by name alone). A5 a missing column stops the run and names it. A6 an empty file stops the run. A7 a blank or zero water height is dropped and counted. A8 a repeated mark id is used once. A9 Poor and Very Poor marks do not draw the line (fails if the filter is removed). A10 point numbers sort as numbers.

**The 10 m ground** (`test_hd_ground.py`)
B1 a planted height is read back at the planted spot. B2 a point on the seam between two tiles reads the same from either tile. B3 a "no data" cell gives blank ground. B4 a missing tile stops the run and names it; no fall-back to 30 m. B5 a failed download leaves no partial tile and no manifest entry. B6 a tile at the wrong resolution is refused. B7 a tile that does not match its recorded sha256 is refused. B8 an empty or all-blank reply stops the pull and writes nothing. B9 the unit tripwire fires when the marks are fed in feet. B10 only tiles that hold a needed point are requested. B11 (added after the Codex review) a road running into a second tile gets that tile, and without it the build names the missing tile. B12 (added after the Codex review) a reply for the wrong place, in the wrong CRS or rotated is refused.

**The water line** (`test_hd_profile.py`)
C1 distances along the line are in metres. C2 hand-worked: marks at 0 m (100.0) and 400 m (104.0) give 101.0 at 100 m. C3 a road point takes its level from the nearest spot on the line. C4 between two streams the nearer live one wins. C5 two marks at one spot are averaged with no divide-by-zero. C6 a stream with one mark gives a level only within 100 m. C7 past the last mark a level is given only within 100 m, low confidence, blank after (fails if the cap is removed). C8 999 m from the nearest mark gives a value, 1,001 m gives blank. C9 249 m is high confidence, 251 m is low. C10 a point too far to the side is "not assessed", not "dry". C11 the count of marks behind a point is right (2 between marks, 1 at an end). C12 shuffled input rows give the same lines.

**Road points and depth** (`test_hd_points.py`)
D1 a 300 m road in lat/lon gets 11 points 30 m apart. D2 a road under 30 m gets both ends. D3 a multi-part road is walked part by part; an empty one is skipped and counted. D4 depth is water level minus ground, hand-worked. D5 water below ground is depth 0 and dry. D6 a road with one low end reports the low end, not the midpoint. D7 points within 60 m of a bridge are set aside; near a culvert or pipe they are not. D8 a 4 m deep, 30 m wide dip is set aside; a gentle sag and an all-low road are not. D9 beside a set-aside point a steep bank is set aside; a flat floodplain is kept. D10 with the three bridge rules off, the bridge value becomes the deepest. D11 one lone deep point cannot set the headline. D12 share under water, hand-worked, set-aside points left out of both sides. D13 a missing bridge list stops the run and names the file. D14 a segment with no kept points is blank, not 0. D15 (added at planning) messy structure types are sorted correctly: "RC Arch Culvert" and "CM Pipe Arch" are culverts, "Arch Spandrel" and a blank type are bridges. D16 (added after the Codex review) tied pairs and a segment touching two streams report by the fixed rules of D14.

**The error number** (`test_hd_validate.py`)
E1 a hidden mark's own level never enters its guess. E2 a hidden stretch hides every mark inside it. E3 hand-worked median and 90th percentile. E4 the tape tests use only taped marks. E5 the end-to-end number uses the hidden-mark guess. E6 per-band counts, and "too few" under 30. E7 if 10 m is not better than 30 m on identical marks, the build refuses. E8 the range resamples whole streams and repeats for the same seed. E9 Poor and Very Poor marks are scored apart. E10 two runs are identical apart from the timestamp. E11 (added at planning) a missing 30 m file refuses unless `--skip-30m-check` is given, and the skip is recorded; driven through the whole command. E12 (added after the Codex review) the saved validation holds the label comparison of the written table. E13 (added after the Codex review) `--validate-only` creates and changes no file. E14 (added after the Codex review) no taped marks, or no ground at the marks, refuses. E15 (added after the Codex review) an empty distance band reports 0 marks and gives a blank typical miss.

**The output file** (`test_hd_output.py`)
F1 exact columns, one row per segment in table order. F2 an unknown or missing `seg_id` stops the write. F3 not assessed is blank, assessed and dry is 0.0. F4 a failed write leaves the old file intact. F5 the notes file records the fingerprints and the loader refuses a changed output. F6 the settings are recorded and pinned. F7 `check_features` rejects every output column. F8 a write to a path that is not ours raises, and every output name starts with `flood_helene_depth` or `dem10_helene`. F9 a depth above 15 m stops the run. F10 (added at planning) the loader refuses when the marks file, the tile manifest or the `seg_id` list has changed since the build. F11 (added after the Codex review) a write that fails part-way leaves the previous four files untouched, and a hand-mixed bundle is refused.

**Repo guards** (`test_hd_guards.py`)
G1 both scripts answer `--help`. G2 no iCloud duplicate files under `src` or `tests`. G3 the branch changed only this change's files. G4 the scripts import from an empty folder with no data and no network, and do not load torch or lightgbm.

**Real data** (`test_hd_real.py`, marked `realdata`; N13 marked `network`)
N1 2,193 marks, 280 taped, 99 stream names, 101 groups. N2 the 30 m typical miss reproduces at 0.61 m, give or take 0.03. N3 the 10 m typical miss is at most 0.25 m and below the 30 m number. N4 the hidden-mark miss is at most 0.30 m within 100 m and at most 0.50 m overall. N5 the end-to-end tape miss is at most 0.60 m. N6 ground from the saved tiles agrees with the USGS point lookup within 0.5 m for 95% of marks. N7 112,443 rows, between 500 and 5,000 segments assessed, nothing above 15 m. N8 Biltmore Village is at least 2 m deep. N9 the downtown hilltop is dry or not assessed. N10 the Smith Mill Creek bridge segment has its river-end points set aside and reports under 1 m. N11 the failed-against-not-failed comparison is present. N12 shared inputs have the same sha256 before and after. N13 a live one-tile fetch returns 10 m ground.

**Changes to the frozen P2 list, found while planning**
- N10 was "the I-240 bridge over the French Broad shows no deep water". No pavement segment lies on that bridge: the nearest segments stay at 624 m or higher, well above the 604 m water, so the test would pass without testing anything. It is replaced by a segment that does start on a bridge and read 5.2 m at its river end in the pre-plan check.
- D7 covers every listed bridge, not only bridges over water, because the ground data removes all bridges.
- Three tests added at planning (D15, E11, F10) and eight after the Codex plan review (B11, B12, D16, E12, E13, E14, E15, F11), so the unit count is 80 and the full-suite count 662.
- B10 was "only tiles touching a marked stream are requested". Roads are sampled along their whole length, so the tile list is now built from the sampled points (Codex finding 1).

Past problems pinned: in-place writes on the iCloud folder (B5, F4), "finished but wrong" replies (A6, B8), zeros that mean "not recorded" (A2, F3), id mismatch (F2), shared files overwritten (F8, N12), one name for different things (A4, D15), unit mix-ups (A1, B9), midpoint depth (D6), tile seams (B2), in-sample shown as held-out (E1, E2, E5), stale files (B6, B7, F5, F10), iCloud duplicates (G2).

## Documentation

- This run spec (frozen after commit).
- `docs/features/HELENE_DEPTH_MAP.md`: created.
- `docs/reports/2026-10-03_helene-depth-map-plan.md` and `-plan-review.md`.
- `README.md`: conditional, confirm at execution. Another chat owns it; the default is to hand the user one status row and one limitation line in this spec's Results section instead of editing it.
- `PLAN.md`: not edited.

## Limits stated up front

- Coverage is 12 counties and about 100 streams. Chimney Rock and Old Fort have no marks.
- The ground was surveyed before the storm; washed-out spots have changed.
- Accuracy is about half a metre near marks and worse with distance.
- A road point within 300 m of a stream line is compared with that stream's water level even if a low ridge lies between; the cap limits this but does not remove it.
- Bridge handling is by rule. A bridge that is not in the list and leaves no sharp notch can still read as deep water; the 15 m stop and the two-point headline limit the damage.
- Depth on a steep bank next to a bridge is set aside even where the road there was truly under water.

## Codex plan review (2026-10-03)

Review file: `docs/reports/2026-10-03_helene-depth-map-plan-review.md`. Eight findings, all accepted before execution.

| # | Finding | How it was addressed | Test |
|---|---|---|---|
| 1 (critical) | Ground tiles covered a 400 m band near streams, but ground is sampled along whole roads | The tile list is the set of tiles holding a mark or a sampled road point; `candidates` feeds both the tile list and the build | B11 |
| 2 (critical) | The failure-label comparison was promised by a step that ran before the table existed | Gates run before the build (`pre_checks`); the comparison is added after (`finish_validation`) | E12 |
| 3 (critical) | Writing the notes file last did not keep the four files consistent | All four are staged, then renamed; `load_depth` checks the sha256 of the depth, points and validation files | F11 |
| 4 (critical) | `--validate-only` had no early exit | `run` returns right after the gates, before the bridge list is read | E13 |
| 5 (critical) | Fingerprinting the 30 m file broke the "30 m file missing" path | `fingerprints` records an absent file as `null` | E11 |
| 6 | A reply for the wrong place or grid could pass | `check_reply` checks CRS, rotation, cell size and coverage of the tile | B12 |
| 7 | Behaviour with no data was undefined | Gates refuse without evidence; reports say 0 marks | E14, E15 |
| 8 | Ties for the headline pair and the `stream` value were undefined | First pair in road order; fixed rule for the stream | D16 |

## Deviations from the plan

1. **A level-change rule was added (`MAX_LIFT_M = 2`).** The first real build stopped at the 15 m check: five segments held points up to 36 m "deep". The cause was not a bridge. On steep rivers with marks far apart a straight line between the marks is a guess: the worst case sat on the Tuckasegee between two marks 3.5 km apart whose levels differ by 57 m, 996 m from the nearer one; another, on the West Fork Tuckasegee, between marks 4.9 km and 348 m of level apart. Measured on the hidden marks before the rule: where the drawn level sat more than 5 m from the nearer mark's own level the typical miss was 1.29 m, one in ten missed by more than 4.3 m and the worst by 23.7 m; where it sat within 0.25 m the typical miss was 0.15 to 0.2 m at any distance up to 500 m. The rule: no level where the drawn level is more than 2 m from the nearer mark's own level. Together with deviation 2 it cut the kept road points by 22% (36,932 to 28,871) and the assessed segments by 133 (1,735 to 1,602). It also changed every error number, because the hidden-mark test runs the same code: typical miss 0.37 m to 0.27 m; the 500 m to 1 km band 0.78 m to 0.39 m; end to end against the tape 0.45 m to 0.37 m. Both sets of numbers are given under Results. Test C13 added; C8 and C9 now use a gentle river so that they test distance alone.
2. **A line answers only through its own nearest spot.** Test E5 exposed a hole in the 100 m end rule: a point 150 m past the last mark of a line was handed the level of the mark before it, because that mark was within the 300 m side cap. The lookup now finds each line's nearest spot to the point first and then asks whether that spot may give a level (within 1 km of a mark, within 100 m past an end, within the 2 m level rule). If not, that line is silent and another stream within 300 m may answer. C7 gained the failing case.
3. **The 15 m check leaves the point out instead of stopping the run.** A single stray reading should not block the whole map. A road point reading deeper than 15 m is now left out and counted (`too_deep` in the points file, `points_too_deep` in the validation file); the run stops only when more than 0.5% of points read that deep (`MAX_TOO_DEEP_SHARE`). After deviations 1 and 2 the final build has no such point. F9 tests both halves.
4. **Interpolation and the 0.20 m figure.** The build reads the ground by interpolating between the four surrounding cells, as planned. With that, the miss against the 280 taped depths is 0.24 m. The 0.20 m quoted at P1 came from the USGS point service, which returns the cell that holds the point; read that way the saved tiles reproduce it exactly (all 2,193 marks agree to the centimetre, test N6). The method was not switched after seeing the numbers. Both beat the 30 m ground (0.61 m).
5. **N1.** The marks file holds 99 spellings of stream names; "Brushy Creek " differs from "Brushy Creek" only by a trailing space, so there are 98 names after trimming. 101 stream groups, 95 lines (six streams have only Poor or Very Poor marks).
6. **`_atomic` was not written.** `write_outputs` stages the four files itself; F4 tests a failure on the first staged file, F11 on the second.
7. **N6 fixture.** `tests/helene_depth/fixtures/usgs_point_ground.csv` holds the USGS point lookup made at 18:40 on 2026-10-03 for the pre-plan check, not a second live call.
8. **`--root` option.** Both scripts take `--root` so the tests can drive the real command line on a synthetic project (E11, E13).
9. **AC6, bridge anchor.** `ncdot:40001338011:0.000` is "not assessed" rather than "under 1 m": five of its points are set aside (the three within 60 m of bridge 100726 and two on the bank beside them; the first read 4.1 m), and its remaining points are too far from the stream line.
10. **Points file.** It also carries `lift_m`, `near_bridge` and `too_deep`.
11. **G3** checks an allow-list of this change's paths, including files not yet committed, and only speaks on branch `helene-depth`.
12. **Test counts.** 81 unit tests, not 80 (C13). Full suite: 663 passed, 2 skipped, both before and after `main` (at `277154f`) was merged into the branch.
13. **Distance to a mark at a bend (after the review).** Where the nearest spot on a line is a mark itself, at a bend or at the end of a line, the first build reported the distance to the nearest mark as 0 m, although the road point could be up to 300 m from that mark. 261 assessed segments showed "0 m", 216 of them with high confidence. The distance is now the straight line to that mark; confidence and the typical-miss lookup follow it. Depths did not change; 43 segments moved from high to low confidence (1,395 to 1,352). C3 and C9 pin it.
14. **D24 as built.** The depth script refuses any output whose file name does not start with `flood_helene_depth` (a name check, inside whatever output folder it is given; F8 drives it through the writer). The ground script writes only tile files and `manifest.json` into the tiles folder it is given, by default `data/processed/dem10_helene/`; it has no separate guard.
15. **Reading the marks.** Beyond D1: a mark with no point number is dropped and counted (it cannot be placed on its line); a mark whose geometry is not a point is counted as outside the box; marks with a blank id are kept apart, not merged; grade names are matched without regard to letter case or stray spaces. None of these cases occurs in the real file (all drop counts are 0). Marks graded "ALTH" (104, meaning unknown) draw the line, as D3 implies.
16. **A range for every distance band (after the review).** AC3 asks for the miss per band "with counts and a range"; the first build gave a range only for the overall figure. Each band now carries its own range, and N4 checks it.
17. **Which code built the files.** The notes file records the commit and whether the two scripts differed from it. The first build ran before the first commit, so its notes named the base commit; the files were rebuilt from commit `f868917` and the notes now say so (N12).

## Results (2026-10-03)

**The gate (AC2).** On the 280 taped marks the 10 m ground misses by 0.24 m and the 30 m ground by 0.61 m. Passed.

**Hidden marks (AC3).** 1,199 marks could be guessed from their neighbours; 688 could not (first and last marks of a line, marks more than 1 km from a neighbour, and marks on steep stretches). Typical miss 0.27 m (95% range 0.23 to 0.33 m); one in ten misses by more than 1.07 m; no lean either way (+0.02 m).

| Nearest remaining mark | Typical miss | 95% range | One in ten misses by more than | Marks |
|---|---|---|---|---|
| Within 100 m | 0.23 m | 0.18 to 0.28 m | 0.94 m | 693 |
| 100 to 250 m | 0.31 m | 0.26 to 0.40 m | 1.08 m | 474 |
| 250 to 500 m | 0.36 m | 0.31 to 0.48 m | 1.10 m | 374 |
| 500 m to 1 km | 0.39 m | 0.29 to 0.46 m | 1.11 m | 163 |

Before the level-change rule the same table read 0.24, 0.40, 0.58 and 0.78 m, and 0.37 m overall (1,610 marks). Poor and Very Poor marks, scored apart: 0.44 m (88 marks). No stream with five or more guessed marks has a typical miss above 1 m.

**Against the tape (AC4).** Ground only: 0.24 m (280 marks; one in ten off by more than 1.30 m). End to end, with the mark's level guessed from its neighbours: 0.37 m (190 marks; 95% range 0.27 to 0.55 m; one in ten off by more than 1.36 m). The end-to-end estimate leans 0.20 m deep. The typical taped depth is 1.04 m, so the miss is roughly a third of a typical depth.

**The map (AC5).** 91 ground tiles (243 MB). 1,905 segments sampled at 86,030 points; 4,376 points set aside as bridges; 28,871 points kept. 1,602 segments assessed, 648 with water.

| Band | Segments |
|---|---|
| Dry | 954 |
| Under 0.3 m | 75 |
| 0.3 to 1 m | 136 |
| 1 to 2 m | 175 |
| Over 2 m | 262 |

Confidence is high for 1,352 and low for 250. Among segments with water the middle depth is 1.7 m, one in ten is above 4.6 m and the deepest is 9.7 m (Little Crabtree Creek, low confidence). The other 110,841 segments are blank.

**Known places (AC6).** Biltmore Village (`ncdot:21000025011:7.235`): 4.2 m, high confidence. Pack Square: not assessed. The bridge-end segment: not assessed, river-end points set aside.

**Against the failure labels (D21, not a gate).** Of 573 assessed segments with at least 0.3 m of water, 37.5% are marked failed in Helene; of 954 dry ones, 11.5%.

**Repeatability (AC7).** Two runs on the real data gave byte-identical depth, points and validation files (compared by sha256, for the first build and again for the rebuild); E10 checks the same on synthetic data.

**Nothing else changed (AC8).** Checked two ways. The run itself fingerprints its five shared inputs before and after (marks, bridge list, `segments.parquet`, `segments_geom.parquet`, `dem/dem.tif`) and refuses to write if any moved; both lists are in the notes file. Separately, a shell `shasum` of seven shared files (those five plus `segments_targets.parquet` and `terrain.parquet`), taken before any code was written and again after the last build, is identical. `git diff --name-only main...HEAD` lists only this change's 17 files.

**Tests (AC1).** `tests/helene_depth`: 81 unit, 12 real-data, 1 live, all passing. Full suite: 663 passed, 2 skipped.

**For `README.md`** (not edited; another chat owns it). A status row:

`| Helene flood depth on roads | Done | A water depth in metres for the 1,602 road segments near surveyed high-water marks in 12 mountain counties; 648 had water. Checked by hiding marks and guessing them back (typical miss 0.27 m) and against 190 tape-measured depths (0.37 m). |`

A limitation line:

`- **Helene depths cover only roads near surveyed marks.** 1,602 of 112,443 segments have one; a blank means "not assessed", not "dry". The typical miss is 0.3 to 0.4 m and one reading in ten is off by more than 1.4 m. Bridges are handled by rule, and the ground was surveyed before the storm.`

## Audits

**Claude critique, round 1 (on `4666360`): Acceptable overall**, every dimension Acceptable. It rebuilt the three output files in memory from the committed code and got the same bytes, and matched every Results number to the files. Fourteen findings, none forcing a downgrade; all were acted on in `f868917` and in this text:

| # | Finding | What was done |
|---|---|---|
| 1 | At a bend, points up to 300 m from a mark were reported as 0 m from it, with high confidence | Fixed: Deviations 13 |
| 2 | D24 promised more than the code enforces | Stated as built: Deviations 14 |
| 3 | AC3 asks for a range per distance band; only the overall figure had one | Added: Deviations 16 |
| 4 | F8 would pass even if the writer stopped refusing foreign names | F8 now drives the writer |
| 5 | The AC8 sentence named two files the run does not fingerprint; N12 checked three of five inputs | Sentence corrected; N12 also checks the 30 m ground (and says why `segments.parquet` is left to the loader) |
| 6 | Deviations 1 compared two different counts | Reworded |
| 7 | The notes file named the base commit, with no sign that the code was uncommitted | Fixed and rebuilt: Deviations 17 |
| 8 | Deviations 9 said four points were set aside; the file has five | Corrected |
| 9 | An extra drop rule was undocumented | Deviations 15 |
| 10 | Two column descriptions in the feature doc were loose | Corrected |
| 11 | A clause in the D14 test could never fail | Removed |
| 12 | Odd mark files: non-point geometry, blank ids, lower-case grades | Handled and tested (A3, A8, A9) |
| 13 | `band` would label a missing depth "over 2 m" (not reachable) | It now raises; D5 checks |
| 14 | Replies are accepted with one extra cell, while three are fetched | Left as is: one cell is what interpolation needs; D4's reply rule says "covers the tile" |

Codex audit: recorded below once run.
