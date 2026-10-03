# Run spec: fix and test the tabular model code (2026-10-03)

Status: executed on branch `model-hardening`. Plan reviewed by Codex 2026-10-03: seven findings, all accepted (D8a, D9a and tests X6, O8, O9, P4, S5, S6 added).

## History

- P1 and P2 were frozen on 2026-10-03 for a plan to build a model frame and baseline from scratch. That plan was reviewed by Codex (nine findings, all accepted) and approved.
- Before execution, commits `f1744d6`..`48520d9` (Vihan Singh, 13:59 to 14:12) landed with a working feature table, Helene labels, a LightGBM baseline, a terrain row, a frozen-DINOv2 test and a predictions file. They include `src/model/train_tabular.py`, the file the old plan was about to create.
- The user chose to keep that code and fix and test it. This spec replaces the old one, which was never committed.

## Problem

The landed model code gets the main things right: survey measurements are kept out of the inputs, evaluation is by 5 km spatial blocks, and there is no monotone age constraint. Six things are wrong or fragile:

1. **Age basis.** `y_rate` divides by `pv_PVMNT_AGE`, which is counted to 2025. 28,426 of the 81,191 labelled segments were surveyed in 2023 or 2024, so their rate is understated. The age feature has the same problem.
2. **Cracking definition.** `y_crack` is 1 for any moderate or high alligator cracking (41% positive). `PLAN.md` defines it as moderate plus high above 10% (15.8% positive).
3. **In-sample map predictions.** `final_ablation.py` fits on all labelled segments and predicts those same segments. The file the map uses overstates accuracy.
4. **Folds recomputed in three places.** `train_tabular.py`, `final_ablation.py` and `train_vit.py` each rebuild the folds with `GroupKFold`, whose assignment depends on which rows are in the table. Adding city streets would reshuffle every fold.
5. **Duplicated logic.** The feature lists, `prep` and `oof` exist twice and can drift apart. Nothing stops a banned column being added to a list.
6. **No tests.** Also, `final_ablation.py` cannot run on a machine that has the terrain rasters (its merge collides on `tn_elev` and `tn_slope`) or that lacks `vit_frozen.parquet`.

## Decisions

- **D1 One shared module.** New `src/model/common.py` holds targets, block and fold rules, feature lists, the banned list, `prep`, `oof`, the terrain merge and the held-out prediction rule. The three scripts import from it and their duplicated copies are removed.
- **D2 Age at survey.** `age = pv_PCS_SRVY_YR - pv_YEAR_LAST_REHAB`. The existing label filter is kept on this age: `2 <= age <= 40` and `pv_RTG_NBR > 0`. A new column `pv_age_at_survey` (NaN when negative) replaces `pv_PVMNT_AGE` in the feature list.
- **D3 Rate and years to Poor.** Unchanged from the landed code apart from the age: `y_rate = clip((100 - rating) / age, lower=0)`; `y_years_to_poor = 0` if rating is below 60, else `min((rating - 60) / max(y_rate, 0.1), 50)`; NaN without a rate label.
- **D4 Cracking.** `y_crack = 1.0 if moderate + high > 10 else 0.0`, NaN when `pv_asph_ALGTR_HGH_PCT` is null. Strict comparison, as in `PLAN.md`.
- **D5 Folds.** `split_block = f"{floor(mid_x/5000)}_{floor(mid_y/5000)}"` (unchanged rule). `fold = crc32(split_block) % 5`, so a block's fold never depends on other rows. Both columns are written into `segments_targets.parquet` and to `data/processed/split.parquet` (`seg_id`, `split_block`, `fold`). No script calls `GroupKFold`.
- **D6 Banned inputs.** `check_features(cols)` raises on: rating, IRI, rut depth, the Good/Fair/Poor code, treatment name and cost, budget group, survey year, every asphalt distress code and alligator percentage, the asphalt rating, and any column starting with `y_`, `pred_`, `n_` (Helene point counts) or `im_vit_`, plus `in_helene_zone`. `prep` calls it, so no model can be fitted on a banned column.
- **D7 Terrain columns.** `attach_terrain(d, dir)` merges `terrain.parquet` when it exists. On a name clash the `terrain.parquet` column wins and the one already in the table is renamed with the suffix `_d8`. Only `tn_` columns are renamed; any other shared column, or a `_d8` name that already exists, raises. The terrain row uses every `tn_` column present. With no `tn_` columns there is no terrain row in either script and the map model is the baseline. `train_tabular.py` attaches the terrain and writes it into `segments_targets.parquet`; `final_ablation.py` reads it from there, so both score the same terrain set.
- **D8 Held-out predictions.** For each target, a segment that has an out-of-fold prediction gets it; every other segment gets the prediction of the model fitted on all labelled segments. Three boolean columns record which: `rate_heldout`, `crack_heldout`, `flood_heldout`, true only where the value really is out-of-fold. Existing columns keep their names.
- **D8b Out-of-date ratings.** `pred_years_to_poor` is blank where the rating is 0 or the survey predates the last resurfacing (the rating then describes the old surface). One function, `years_to_poor`, computes the forecast for both the target and the map.
- **D8a Sparse subsets.** A fold with no test rows, no training rows, or one training class for a binary target is skipped and reported; its rows stay without an out-of-fold value. A subset with nothing to score yields NaN metrics, not an error.
- **D9 Optional embeddings.** If `vit_frozen.parquet` is absent, `final_ablation.py` prints that the three imagery-subset rows were skipped and carries on. If it is present but matches no segment, the rows are written with zero counts and NaN metrics.
- **D9a One-to-one merges.** Terrain, embeddings and geometry are merged through one helper that rejects null or duplicate `seg_id`, rejects any other column present on both sides, and preserves row count and order.
- **D10 Reproducibility.** `oof` and the final fits pass `random_state=0`. Other LightGBM settings are unchanged.
- **D11 Do-nothing reference and tripwire.** Every row in both `ablation.csv` and `ablation_final.csv` reports `rate_mae_naive` (training-fold median, on that row's own subset), `n_scored` and the cracking prevalence. A rate Spearman above 0.95 raises as a probable leak.
- **D12 Script shape.** `train_tabular.py` and `final_ablation.py` move their module-level code into `main(p=Path("data/processed"))` under an `if __name__ == "__main__"` guard, so they can be imported and run on a fixture directory. Outputs and file names are unchanged.
- **D13 Map file.** `final_ablation.py` writes `predictions_geo.parquet` into a handoff directory (default `handoff/`, injectable so tests never write the tracked file) from `predictions.parquet` and `segments_geom.parquet` when the latter exists.
- **D14 Untouched.** `src/pipeline/*` is not edited. `train_vit.py` changes only its fold lines (to call the shared function).
- **D15 Tests.** `pytest` as a dev dependency; marker `realdata` for tests that need `data/processed/segments.parquet`.

## Acceptance criteria

- **AC1** `uv run pytest -q -m "not realdata"` passes.
- **AC2** `uv run pytest -q -m realdata` passes, pinning 112,443 rows, 77,422 rate labels, 68,349 cracking labels with 10,766 positive, 5,040 blocks, and five folds each holding 15% to 25% of rate labels.
- **AC3** `uv run python -m src.model.train_tabular` writes `ablation.csv` with a baseline row and a terrain row; each has rate MAE below `rate_mae_naive` and cracking AUC-PR above prevalence; the tripwire does not fire.
- **AC4** Running it twice gives identical `ablation.csv`.
- **AC5** `uv run python -m src.model.final_ablation` runs on this machine and writes `predictions.parquet` in which every labelled segment's prediction equals its out-of-fold value.
- **AC6** `grep -rn "GroupKFold\|pv_PVMNT_AGE\|alg > 0" src/model` prints nothing.
- **AC7** `git diff --stat d7b4370..HEAD -- src/pipeline/pull_ncdot.py src/pipeline/chips.py` is empty for this change's commits, and `uv run python -m src.pipeline.pull_ncdot --join-only` still prints 112,443 / 68,531 / 68,349.

## Failure modes and tests

**Targets** (`tests/test_targets.py`)
- T1 age counted to 2025: surveyed 2023, rehab 2015 uses age 8. T2 filter bounds: age 1 and 41 give no label, 2 and 40 do. T3 resurfaced after survey gives no label and NaN `pv_age_at_survey`.
- T4 rating 0 gives no label. T5 rate arithmetic (85 at age 8 is 1.875). T6 years to Poor: 0 below 60, cap 50. T6b the 0.1 rate floor and the cap in `years_to_poor`, with values that fail if either constant changes.
- T7 cracking boundary: 10 is 0, 11 is 1. T8 cracking is NaN without asphalt data. T9 row count and order preserved.

**Folds** (`tests/test_folds.py`)
- F1 floor rule, including negative coordinates. F2 `fold` equals `crc32 % 5`. F3 segments in one block share a fold.
- F4 adding or removing rows never changes an existing segment's fold. F5 the split file round-trips. F6 no `GroupKFold`, `pv_PVMNT_AGE` or `alg > 0` in `src/model` (AC6).

**Features** (`tests/test_features.py`)
- X1 the feature list has `pv_age_at_survey` and not `pv_PVMNT_AGE`. X2 no banned column in the baseline lists. X3 each banned name and each banned prefix raises (parametrised).
- X4 `prep` raises on a banned column and casts strings to category. X5 terrain merge with clashing names keeps both, with `_d8` on the table's copy; an existing `_d8` name or a non-terrain clash raises.
- X6 a duplicate or null `seg_id` on either side of a merge raises, as does a shared non-key column; row count and order are otherwise preserved.

**Out-of-fold** (`tests/test_oof.py`)
- O1 only masked rows are trained on or predicted. O2 each masked row is predicted once and never by a model that trained on its fold. O3 same seed gives identical predictions.
- O4 an empty fold is skipped without error. O5 cheat demonstration: a direct estimator given rating plus age drives MAE to near 0 on a synthetic table (below 0.1 and below a fifth of the do-nothing error), and `prep` rejects those columns. O6 the naive MAE uses training-fold medians only. O7 the tripwire raises above 0.95.
- O8 labels confined to one fold give NaN out-of-fold values and NaN metrics, not an error. O9 a fold whose training labels have one class is skipped for a binary target.

**Predictions** (`tests/test_predictions.py`)
- P1 a labelled segment's prediction equals its out-of-fold value. P2 an unlabelled segment gets the full-model value. P3 the three `*_heldout` flags are true exactly where an out-of-fold value exists.
- P4 a labelled segment in a skipped fold gets the full-model value with its flag false, whatever the index of the full-model values.
- P5 `pred_years_to_poor` is blank where the survey predates the resurfacing and otherwise equals `years_to_poor` of the predicted rate. P2 compares unlabelled rows with the full-model fit, and labelled rows are checked not to equal the in-sample fit.

**End to end** (`tests/test_scripts.py`)
- S1 `train_tabular.main` on a fixture directory writes `segments_targets.parquet` (with `split_block`, `fold`), `split.parquet` and `ablation.csv` with the expected columns. S2 running it twice gives identical CSVs.
- S3 `final_ablation.main` without `vit_frozen.parquet` skips the imagery rows and writes predictions; every row has `rate_mae_naive` and `n_scored`. S4 with a fixture `vit_frozen.parquet` it runs them.
- S5 the exported map file is written only inside the supplied handoff directory, is GeoParquet in the geometry's CRS, covers every segment once and carries the three flags. S6 an embeddings file matching no segment gives zero-count rows with NaN metrics.
- S9 the map export raises when the geometry file and the predictions cover different segments.
- S7 without terrain columns neither script writes a terrain row and the map model is the baseline. S8 both scripts raise when the leak threshold is lowered, which proves the tripwire is wired in. The script fixture carries a `terrain.parquet`, so S1 and S3 exercise the terrain rows.

**Repo guards** (`tests/test_repo_guards.py`)
- G1 no `* 2.py` under `src/`. G2 the `numpy<2.4` pin is present. G3 `pull_ncdot`, `dem` and `chips` answer `--help`.

**Real data** (`tests/test_realdata.py`)
- R1 the label counts in AC2. R2 block count and fold shares in AC2. R3 every fold has Helene positives inside the zone. R4 every baseline feature exists after `add_targets`, and every raw column `add_targets` reads exists in `segments.parquet`.
- R5 (AC5) in the generated `predictions.parquet` each `*_heldout` flag equals its label mask. R6 (AC3) every row of the generated `ablation.csv` beats the do-nothing reference and stays under the leak threshold. Both skip where the outputs have not been generated. AC7 is checked by hand (`git diff --stat` and the join command).

Bug classes pinned: label and feature dated to different years (T1), a target that differs from the plan (T7), flattering in-sample output (P1), fold drift when rows change (F4), an output that finishes but is wrong (O7, R1), duplicated logic drifting (F6, X1), iCloud duplicates (G1), dependency drift (G2).

## Documentation

- This run spec; `docs/reports/2026-10-03_model-hardening-plan.md` and its review file.
- `readme`: the measured-results section and the limitations list, updated with the rerun numbers.
- `docs/ablation_final.csv`: regenerated.
- `PLAN.md`: conditional, confirm with the user (untracked).

## Known gap

The imagery-subset rows need `vit_frozen.parquet`, which exists only on Vihan's machine. Until that file is here those rows cannot be rerun with the corrected labels; the README will mark them as measured before the fix.

## Results (2026-10-03)

Tests after the critique fixes: `pytest -q -m "not realdata"` 82 passed; `pytest -q -m realdata` 6 passed. (First commit: 78 and 4.)

| Criterion | Result |
|---|---|
| AC1 fast tests | Pass (82) |
| AC2 real-data pins | Pass: 112,443 rows; 77,422 rate labels; 68,349 cracking labels, 10,766 positive; 5,040 blocks; fold shares within 15% to 25% |
| AC3 baseline and terrain rows beat the do-nothing reference | Pass (table below); tripwire did not fire |
| AC4 two runs identical | Pass: `diff` of the two `ablation.csv` files is empty |
| AC5 `final_ablation` runs here; labelled segments carry out-of-fold values | Pass: `rate_heldout` 77,422, `crack_heldout` 68,349, `flood_heldout` 32,558, equal to the label masks |
| AC6 no `GroupKFold`, `pv_PVMNT_AGE` or `alg > 0` in `src/model` | Pass |
| AC7 pipeline untouched; join still 112,443 / 68,531 / 68,349 | Pass |

Measured, all labelled segments, 5-fold spatial block CV:

| Row | n rate | Rate MAE | Do-nothing MAE | Rate Spearman | Cracking AUC-PR (prevalence) | Flood P@50 / AUC-PR |
|---|---|---|---|---|---|---|
| Before this change, baseline | 81,191 | 0.781 | not reported | 0.503 | 0.706 (0.41) | 0.26 / 0.111 |
| Before this change, + terrain | 81,191 | 0.765 | not reported | 0.533 | 0.731 (0.41) | 0.36 / 0.206 |
| After, baseline | 77,422 | 0.753 | 0.965 | 0.573 | 0.377 (0.158) | 0.26 / 0.106 |
| After, + terrain | 77,422 | 0.749 | 0.965 | 0.586 | 0.422 (0.158) | 0.36 / 0.207 |

The cracking numbers are not comparable across the change: the target went from 41% positive to 15.8% positive. Relative to chance, AUC-PR went from 1.7 times prevalence to 2.4 times (baseline) and 2.7 times (terrain).

The imagery-subset rows were not rerun: `vit_frozen.parquet` is not on this machine. The README keeps the earlier values and says they predate the fix.

## Deviations from the plan

1. **Branch.** Committed on branch `model-hardening`, not `main`. The user's instruction, relayed by the coordination chat during execution, was that each chat writing code works on its own branch and worktree.
2. **Map file geometry.** `export_geo` simplifies geometry to 3 m (in EPSG:32119) and writes with zstd. Without it the regenerated file was 74.7 MB against the committed 17.8 MB, because the committed file had been simplified by hand (1,074,136 vertices; 3 m gives 1,076,473). The new file is 19.5 MB. The README states the simplification.
3. **`score` signature.** `score(y, pred, mask, kind)`; the plan listed an unused `d` argument.
4. **Small additions.** `precision_at_k` (the flood P@50 expression, previously inline twice) and `write_atomic`. Two tests beyond the listed IDs: hand-worked metric values, and `final_ablation` refusing a targets file without folds.
5. **README.** Besides the planned updates it gained a short Reproducing section and three limitation bullets (unseeded `train_vit.py`, extrapolated rate predictions for the 22,948 segments without a resurfacing year, simplified geometry).
6. **`PLAN.md`** was not edited. It is untracked and the user has not confirmed changes to it.
7. **Terrain in `final_ablation.py`.** It does not call `attach_terrain`; it uses the terrain columns `train_tabular.py` wrote into `segments_targets.parquet` (plan Step 4.2). If `terrain.parquet` changes, rerun `train_tabular` first.
8. **Out-of-date ratings (D8b).** Not in the plan; added after the critique. 1,640 segments resurfaced after their survey are newly blank in `pred_years_to_poor`; 112 of them had been shown as 0 years to Poor. (The 3 segments with a rating of 0 were already blank, so 1,643 are blank in total.) The 4,856 segments surveyed in the year they were resurfaced keep a forecast, since the order of survey and work within that year is unknown; the README says so.
9. **Worktree.** After the first commit the work moved to a git worktree at `.claude/worktrees/model-hardening`, with `data/raw`, `data/chips` and `data/processed` symlinked to the main checkout, per the same instruction as deviation 1.

## Found during execution, not fixed here

- Rate predictions for segments without a rate label are unstable: between the old and new map files their Spearman correlation is -0.19 (0.86 for labelled segments). Most of these segments have no resurfacing year, so the model has no age to work with. Recorded as a README limitation.
- `train_vit.py`: unseeded flips in DataLoader workers; PCA fitted on all chips. Recorded as README limitations (D14 limits this change to its fold lines).

## Reviews

### Claude critique, round 1 (commit 43a68e5): Overall Fail

Graded by a separate agent against the audit rubric. Plan adherence Acceptable, Scope discipline Acceptable, Test coverage **Fail**, Review compliance Acceptable, Freeze integrity n/a, Regression check Excellent, Documentation Acceptable. It confirmed from the code that no labelled segment's map prediction comes from a model trained on it, that a `*_heldout` flag cannot be true on a full-model value, and that no label-derived column can pass `prep`.

Sixteen findings, all fixed in the next commit:

1. O6 could not tell a training-fold median from the global median (blocking). Rewritten with values where the two differ (50/7 against 30/7).
2. T6 could not fail if the rate floor changed. `years_to_poor` is now one function, with test T6b.
3. `ablation.csv` lacked `n_scored` (D11). Added, and pinned in S1.
4. No test failed if a script stopped calling the tripwire. Test S8; S4 now checks `rate_mae_naive`.
5. `final_ablation` wrote "+ terrain" rows identical to baseline when there were no terrain columns. Those rows are now skipped (S7).
6. `merge_one_to_one` let pandas rename shared columns to `_x`/`_y`, silently dropping features. It now raises (X6).
7. `attach_terrain` could create duplicate `_d8` names and renamed non-terrain clashes. It now renames only `tn_` columns and raises otherwise (X5).
8. `pred_years_to_poor` used the pre-resurfacing rating for 1,640 segments. Now blank (D8b, P5), and stated in the README.
9. P2 only checked non-null. It now compares with the full-model fit.
10. AC3, AC5 and AC7 had no automated test. R5 and R6 added; AC7 stays a manual check and the spec says so.
11. A code comment said 18 MB for a 19.5 MB file. Fixed.
12. The README overstated the banned list. Reworded.
13. The README gave 41% prevalence for the imagery subset (it was 34%) and the old rows had left the CSV. Reworded, with the commit that holds the old rows.
14. This spec's status still said planned. Fixed.
15. `final_ablation` not calling `attach_terrain` was an unlisted deviation. Listed (deviation 7).
16. `heldout_then_model` would have misaligned a Series with a different index. It now takes positional values (P4).

### Claude critique, round 2 (commit 1255b87): Overall Acceptable

All 16 round-1 findings confirmed fixed. The reviewer mutated a scratch copy (removed the stale-rating mask, disabled the shared-column check, built the map model on the wrong features, set the rate floor to 0) and each mutation made a test fail. Plan adherence, Scope discipline, Test coverage, Review compliance and Documentation Acceptable; Regression check Excellent; Freeze integrity n/a.

Four new non-blocking findings, addressed in the following commit:

- N1 same-year resurfacings (4,856 segments) keep a forecast that may rest on a pre-work rating. Left as is, because the order within the year is unknown, and stated in the README and in deviation 8.
- N2 wording: only the 1,640 stale segments are newly blank. Corrected in the README and this spec.
- N3 `years_to_poor` only accepted pandas Series. It now takes arrays as well (T6b).
- N4 R5 could judge stale shared outputs. It now skips when `predictions.parquet` is older than `segments_targets.parquet`.

### Codex audit (commit 565d582): Overall Acceptable

Report: `docs/specs/2026-10-03_model-hardening-audit.md`. Plan adherence Acceptable, Scope discipline Excellent, Test coverage Acceptable, Review compliance Acceptable, Freeze integrity skipped, Regression check Acceptable, Documentation Excellent.

Three findings, none blocking:

1. `export_geo` did not check that the geometry file and the predictions cover the same segments, so a mismatch would drop or blank segments silently. Fixed in the following commit: it now raises, with test S9. The tracked map was unaffected (all 112,443 segments match).
2. O5 only compared the cheating error with the honest error. An absolute bound was added.
3. A verification limit, not a defect: the audit's sandbox is read-only, so it reran 69 of the 82 fast tests and all 6 real-data tests, and could not rerun the model or the join command. Those were run in this session (88 passed; results above).

The audit was not rerun after these two fixes: both are small and covered by new tests, and the user asked for each review stage to run once unless it found something serious.
