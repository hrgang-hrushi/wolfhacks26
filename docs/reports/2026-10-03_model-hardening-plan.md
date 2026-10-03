# Implementation plan: fix and test the tabular model code (2026-10-03)

Run spec: `docs/specs/2026-10-03_model-hardening.md` (decisions D1 to D15, acceptance AC1 to AC7).

Context for a reviewer: there is no `CLAUDE.md` or `AGENTS.md`. `readme` (repo root) holds measured results; `PLAN.md` (untracked) is the project plan. Python 3.11, `uv`, run from the repo root as `uv run python -m src.<pkg>.<module>`. The model code under `src/model/` was written by a teammate (commits `aa8d8cd`, `5c07f7c`); this change keeps it and fixes it.

## Current state (verified 2026-10-03, HEAD `48520d9`)

- `src/model/train_tabular.py` (88 lines): module-level script, no `main`. Lines 19 to 30 compute targets from `pv_PVMNT_AGE` (line 20) and `alg > 0` (line 27) and write `segments_targets.parquet`. Lines 33 to 36 build folds with `GroupKFold`. Lines 39 to 47 define `PV`, `TR`, `TN` and the ladder. Lines 49 to 66 define `prep` and `oof`. Lines 68 to 89 score the ladder and write `ablation.csv`.
- `src/model/final_ablation.py` (106 lines): module-level script. Line 15 reads `segments_targets.parquet`; line 16 merges `terrain.parquet`; lines 17 to 19 require `vit_frozen.parquet`; lines 21 to 24 rebuild folds with `GroupKFold`; lines 26 to 57 repeat `PV`, `TR`, `prep`, `oof`; lines 60 to 88 score five rows; lines 91 to 106 fit on all labelled rows and predict every row (in-sample for labelled rows), writing `predictions.parquet`.
- `src/model/train_vit.py`: lines 78 to 81 rebuild folds with `GroupKFold`.
- `src/pipeline/features.py` writes `data/processed/segments.parquet` (112,443 rows, 100 columns: every raw NCDOT column prefixed `pv_`, six `tr_` columns, `y_helene_*`, `in_helene_zone`, `mid_x`, `mid_y` in EPSG:32119, and `tn_elev`, `tn_slope`, `tn_flowacc` when the DEM rasters exist, as they do here).
- `src/pipeline/terrain_simple.py`: module-level script writing `data/processed/terrain.parquet` (`seg_id`, `tn_elev`, `tn_slope`, `tn_relief1k`, `tn_hand_proxy`). Not yet run on this machine.
- On this machine `data/processed/` has `segments.parquet`, `segments_geom.parquet`, `segments_targets.parquet`, `ablation.csv`; it lacks `terrain.parquet`, `vit_frozen.parquet`, `predictions.parquet`. `.gitignore` ignores all of `data/processed/`.
- Tracked outputs: `docs/ablation_final.csv`, `handoff/predictions_geo.parquet` (112,443 rows: `seg_id`, `geometry`, `pred_rate`, `pred_years_to_poor`, `pred_crack`, `pred_flood`, `in_helene_zone`).
- `pyproject.toml`: dependencies on lines 6 to 24; no test config. `tests/` does not exist.
- Measured on the real table: the D2 filter gives 77,422 rate labels (81,191 before); `moderate + high > 10` gives 10,766 positives of 68,349; 5,040 blocks; `crc32 % 5` puts 18.3% to 20.7% of rate labels in each fold, with 209 to 300 Helene positives per fold inside the zone.

## Step 0. Pre-flight

1. `git branch --show-current` prints `main`; `pwd` is the repo root.
2. `git pull --rebase origin main`, so the edits start from the teammate's latest code. If files this plan edits changed upstream, re-read them before continuing.
3. `git status --short` shows only untracked `PLAN.md`, `docs/handoffs/`, `docs/reports/`, `docs/specs/`, `reports/`.
4. `find src -name "* 2*"` prints nothing.

## Step 1. Test tooling

Append to `pyproject.toml`:
```toml
[dependency-groups]
dev = ["pytest"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
markers = ["realdata: needs data/processed/segments.parquet on this machine"]
```
Run `uv sync`; confirm numpy is still below 2.4.

## Step 2. `src/model/common.py` (new)

Constants: `BLOCK_M = 5000`, `N_FOLDS = 5`, `MIN_AGE = 2`, `MAX_AGE = 40`, `RATE_FLOOR = 0.1`, `YEARS_CAP = 50`, `POOR = 60`, `CRACK_PCT = 10`, `SEED = 0`.

- `PV`: the list on `train_tabular.py` lines 39 to 41 with `pv_PVMNT_AGE` replaced by `pv_age_at_survey`. `TR`: line 42 unchanged.
- `BANNED_EXACT` and `BANNED_PREFIXES` per D6. `check_features(cols)` raises `ValueError` naming every offending column. An import-time assertion runs it on `PV + TR`.
- `add_targets(d) -> d`: adds `pv_age_at_survey`, `y_rate`, `y_years_to_poor`, `y_crack` per D2 to D4. Same expressions as the current lines 19 to 27 except the age source and the `> CRACK_PCT` comparison. Does not drop or reorder rows.
- `block_id(mid_x, mid_y) -> Series[str]`: `floor(mid_x / BLOCK_M)` and `floor(mid_y / BLOCK_M)` as ints joined by `_` (identical to the current `//` expression). `fold_of(block: str) -> int`: `zlib.crc32(block.encode()) % N_FOLDS`. `add_folds(d) -> d` adds `split_block` and `fold`.
- `write_split(d, path)`: writes `seg_id`, `split_block`, `fold` through a temporary file and `os.replace`.
- `attach_terrain(d, p) -> d`: if `p / "terrain.parquet"` exists, rename any `tn_` column of `d` that also appears in the terrain file to `<name>_d8`, then left-merge on `seg_id`. `terrain_columns(d)` returns the sorted `tn_` columns.
- `merge_one_to_one(d, other, name) -> d`: the only merge helper. Raises `ValueError` if `seg_id` is null or duplicated on either side, left-merges with `validate="one_to_one"`, and asserts the row count and `seg_id` order of `d` are unchanged. `attach_terrain`, the embeddings merge and the geometry merge all use it.
- `prep(d, cols) -> X`: calls `check_features(cols)`, then the existing cast (non-numeric or bool to `category`).
- `oof(d, X, y, kind, mask, seed=SEED) -> Series`: based on the `final_ablation.py` version, with `random_state=seed` added and `kind` in `{"l1", "bin"}`. Uses `d.fold`. A fold is skipped, leaving its masked rows NaN, when its test set is empty, its training set is empty, or (for `bin`) its training labels have one class; each skip is printed with the reason. The function never fills a skipped row from another model.
- `score(d, y, pred, mask, kind) -> dict`: metrics over rows where `mask` is true and `pred` is non-null, with `n_scored`. With no such rows, or a single class for `bin`, every metric is NaN and nothing raises. Both scripts use it, so an empty or one-fold subset yields a row with NaN metrics instead of a crash.
- `naive_mae(d, y, mask)`: for each fold, the median of `y` over masked rows in the other folds, scored on that fold; returns the overall MAE.
- `check_not_too_good(spearman)`: raises `RuntimeError` above 0.95.
- `fit_all_predict(X, y, kind, mask, seed=SEED) -> ndarray`: fit on masked rows, predict every row.
- `heldout_then_model(oof_pred, full_pred) -> (pred, is_heldout)`: `is_heldout` is true exactly where `oof_pred` is non-null; `pred` is `oof_pred` there and `full_pred` elsewhere. A labelled row whose fold was skipped therefore gets the full-model value with `is_heldout` false, never a mislabelled one.

## Step 3. `src/model/train_tabular.py` (edit)

1. Wrap the script body in `def main(p: Path = Path("data/processed"))` with an `if __name__ == "__main__": main()` guard; replace the global `P` with `p`.
2. Replace lines 19 to 27 with `d = add_targets(d)`; replace lines 33 to 36 with `d = add_folds(d)`; call `d = attach_terrain(d, p)` before writing `segments_targets.parquet`; call `write_split(d, p / "split.parquet")`.
3. Delete the local `PV`, `TR`, `prep`, `oof`; import them. `TN = terrain_columns(d)`. The ladder logic on lines 44 to 47 stays.
4. In the row dict add `n_rate`, `rate_mae_naive`, `crack_prevalence`; call `check_not_too_good` on the rate Spearman. Existing keys keep their names and order; new keys are appended.
5. `ablation.csv` is written through a temporary file and `os.replace`.

## Step 4. `src/model/final_ablation.py` (edit)

1. Same wrapping, as `main(p: Path = Path("data/processed"), handoff_dir: Path = Path("handoff"))`. Nothing in the function writes outside `p` and `handoff_dir`, so tests pass temporary directories for both and cannot touch the tracked map file.
2. Read `segments_targets.parquet`. If `split_block` or `fold` is missing (an older file), stop with a message to rerun `train_tabular`. Remove lines 16 and 21 to 24 (terrain is already attached and folds already present). Remove the duplicated lists and functions; import from `common`.
3. Embeddings: if `p / "vit_frozen.parquet"` exists, merge it with `merge_one_to_one` and score the three `CHIPPED` rows; otherwise print `vit_frozen.parquet not found: skipping the imagery-subset rows` and score only the two `ALL` rows. If the file exists but matches no segment, the three rows are written with `n_rate = 0` and NaN metrics.
3a. `evaluate` uses `score` for every metric and adds `rate_mae_naive` (from `naive_mae` on that row's own subset mask) and `n_scored`; it calls `check_not_too_good` on every row whose rate Spearman is not NaN (D11).
4. `TN = terrain_columns(d)`.
5. Predictions (replaces lines 91 to 106): for each of rate, cracking and flood, compute `oof` on the same mask used for scoring and `fit_all_predict` on that mask, then `heldout_then_model(oof_pred, full_pred)`. Write the existing columns plus `rate_heldout`, `crack_heldout`, `flood_heldout`. `pred_years_to_poor` keeps its current formula on the new `pred_rate`.
6. If `p / "segments_geom.parquet"` exists, merge with `merge_one_to_one` and write `handoff_dir / "predictions_geo.parquet"` (GeoParquet in the geometry file's CRS, same column order as now with the three flags appended), through a temporary file.
7. `ablation_final.csv` is written to `p` as now. Copying it to `docs/ablation_final.csv` stays a manual step in Step 8.

## Step 5. `src/model/train_vit.py` (edit, fold lines only)

Replace lines 78 to 81 with: use `d.fold` if `segments_targets.parquet` already has it, else `d = add_folds(d)`. Remove the `GroupKFold` import. No other change. `Net` and the chip preprocessing (RGB, crop 1:127, divide by 255) must stay exactly as they are: the image augmentation chat imports `Net` and mirrors that preprocessing.

## Step 6. Tests

Create `tests/conftest.py` with `make_table(n_blocks=40, per_block=50, seed=0)`: a synthetic `segments.parquet`-shaped frame with the `pv_` columns the code reads, `tr_` columns, `mid_x`, `mid_y` on a grid of blocks, `in_helene_zone`, `y_helene_failed`, and a rate that depends on age plus noise. A `fixture_dir` fixture writes it to a temporary `data/processed`-like directory together with a small `segments_geom.parquet`.

Create the eight test files and tests listed in the run spec (T1 to T9, F1 to F6, X1 to X6, O1 to O9, P1 to P4, S1 to S6, G1 to G3, R1 to R4). Three details:
- O5 (the cheat demonstration) fits a LightGBM estimator directly on a synthetic frame that includes rating and age, bypassing `prep`; a separate assertion in the same test shows `prep` rejects those columns.
- R4 checks the baseline features against the table after `add_targets` (which creates `pv_age_at_survey`), and separately checks that the raw columns `add_targets` reads exist in `segments.parquet`.
- Every script test passes `tmp_path` directories for both `p` and `handoff_dir`. LightGBM in tests uses 30 trees by monkeypatching `common.N_ESTIMATORS`; for that, `common.py` exposes the tree count as a module constant read at call time.

## Step 7. Run on the real data

1. `uv run pytest -q -m "not realdata"` (AC1).
2. `uv run python -m src.pipeline.terrain_simple` to create `terrain.parquet` on this machine.
3. `uv run python -m src.model.train_tabular` (AC3), then again, and `diff` the two `ablation.csv` files (AC4).
4. `uv run pytest -q -m realdata` (AC2).
5. `uv run python -m src.model.final_ablation` (AC5). It will skip the imagery rows unless `vit_frozen.parquet` has arrived.
6. `grep -rn "GroupKFold\|pv_PVMNT_AGE\|alg > 0" src/model` prints nothing (AC6).
7. `uv run python -m src.pipeline.pull_ncdot --join-only` prints 112,443 / 68,531 / 68,349 (AC7).

If a row fails AC3 (does not beat the do-nothing reference), do not tune. Record and report the numbers.

## Step 8. Docs

1. Copy `data/processed/ablation_final.csv` to `docs/ablation_final.csv`.
2. `readme`: update the two `ALL` rows, the label count (77,422), the cracking sentence (moderate plus high above 10%, prevalence 15.8%), and replace the "Predictions are in-sample" limitation with a sentence describing the `*_heldout` flags. If the imagery rows were skipped, mark that table "measured before the 2026-10-03 label fix; rerun needs `vit_frozen.parquet`". Update the terrain limitation to list the terrain columns actually used.
3. Fill the Results section of the run spec.
4. Staleness grep: `grep -rn "81,191\|41%\|in-sample" readme docs reports` and fix what this change made false. Handoff files get a dated one-line note, not a rewrite.

## Step 9. Commit

1. `git pull --rebase origin main` again. If the pull changed anything under `src/` or any input this change reads, rerun Step 7 in full and regenerate `ablation.csv`, `ablation_final.csv`, `predictions.parquet`, `handoff/predictions_geo.parquet` and the README numbers before committing, so the committed results match the committed code. If nothing relevant changed, rerun the fast tests only.
2. The working tree and git index are shared with other chats. Stage file by file, and commit with explicit paths (`git commit -- <paths>`): `pyproject.toml`, `uv.lock`, `src/model/common.py`, `src/model/train_tabular.py`, `src/model/final_ablation.py`, `src/model/train_vit.py`, the nine files under `tests/`, `docs/ablation_final.csv`, `handoff/predictions_geo.parquet`, `readme`, the run spec, this plan and its review file.
3. Compare `git diff --cached --name-only` with that list; unstage anything else. Read `git diff --cached --stat`.
4. Commit as `fix: age-at-survey targets, plan cracking rule, held-out map predictions, shared folds, tests`. Do not push.

## Step 10. After the commit

One adversarial critique by a separate agent against the audit rubric, the run spec, this plan and the diff; fix and commit. Then `bash ~/.claude/review-audit.sh docs/specs/2026-10-03_model-hardening.md`; record both verdicts in the run spec; fix findings; report.

## Risks

- **Editing a teammate's files while he is working.** Mitigated by pulling before starting and before committing, by small edits that keep function and output names, and by telling him before the push.
- **Numbers in the README change.** Fewer rate labels (77,422) and a rarer cracking target (15.8%) will move every metric. That is the point of the fix; the old and new values are both recorded in the run spec.
- **Imagery rows cannot be rerun here** without `vit_frozen.parquet`. Flagged in the README until the file arrives.
- **`handoff/predictions_geo.parquet` is a tracked 17.8 MB file.** Regenerating it adds another copy to git history. Accepted because the map reads it; flagged to the user before pushing.
- **Stacking the fine-tuned ViT scores.** `train_vit.py` writes out-of-fold scores, but feeding them to LightGBM is only leak-free with nested, outer-fold-specific generation. No script does that yet; `im_vit_` columns are banned as inputs until it exists.

## Response to the Codex plan review (2026-10-03)

Review file: `docs/reports/2026-10-03_model-hardening-plan-review.md`. Seven findings, all accepted.

1. **Critical, tests could overwrite the tracked map file.** `final_ablation.main` now takes `handoff_dir`; every script test passes temporary directories. S5 checks the exported file's CRS, columns, segment coverage and flags.
2. **Critical, R4 could not pass.** Features are checked after `add_targets`; raw target inputs are checked separately.
3. **Critical, sparse subsets.** `oof` skips and reports folds with no test rows, no training rows or one training class; `score` returns NaN metrics for empty or single-class subsets; `heldout_then_model` marks a row held-out only where an out-of-fold value exists. Tests O8, O9 and S6.
4. **Critical, final-ablation rows lacked the do-nothing reference and tripwire.** `evaluate` now adds `rate_mae_naive` and `n_scored` and calls the tripwire on each row's own subset. Checked in S3 and S4.
5. **Suggestion, merge cardinality.** One helper, `merge_one_to_one`, used for terrain, embeddings and geometry. Test X6 covers duplicate keys.
6. **Suggestion, cheat demonstration vs the guard.** O5 bypasses `prep` with a direct estimator and separately asserts `prep` rejects the columns.
7. **Suggestion, stale results after the final pull.** Step 9 now requires a full rerun and regeneration when the pull changes code or inputs.

## Coordination with the other chats in this folder (2026-10-03)

From the coordination chat's overlap report. None of this changes the design.

- No other chat edits the files this plan edits. This chat is the only one that edits `pyproject.toml` and `uv.lock`.
- Before Step 7 (the real-data run), send a one-line heads-up to the image augmentation chat and the CCTV pothole chat so heavy jobs do not overlap on an 18 GB machine. The CCTV chat has been asked not to rerun the feature and model scripts once this starts.
- The image augmentation chat pins 77,422 rate labels, 68,349 cracking labels, 10,766 positives and `fold = crc32(split_block) % 5`, and refuses the pre-fix `segments_targets.parquet`. Message it when this change lands, and at once if any of those numbers comes out different.
- The CCTV pothole chat reads the `*_heldout` columns in `handoff/predictions_geo.parquet`. Message it when that file is regenerated.
- The image augmentation chat keeps its tests in `tests/vision/` with its own `conftest.py`; it will not create `tests/conftest.py` or `tests/test_folds.py`.
- `data/processed/split.parquet` is not tracked, because `.gitignore` ignores all of `data/processed/`. That is intended: the rule in `common.py` is the contract and the file is a local convenience.
- Known issues in `train_vit.py` reported by the image augmentation chat and NOT fixed here (D14 limits this change to the fold lines): flips use the global `np.random` inside DataLoader workers, no seed is set, and the PCA for the frozen embeddings is fitted on all chips, held-out ones included. The PCA uses no labels, so it is not a label leak, but the README's imagery rows should say the reduction was fitted on all chips.
- No chat has `vit_frozen.parquet`. The image augmentation chat will later write a statewide file in the same layout to `data/processed/vision/`; its PCA is fitted on different chips than Vihan's, so using it is not a like-for-like rerun. Which to use is the user's decision.
