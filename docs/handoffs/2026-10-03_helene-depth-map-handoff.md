# Handoff - Helene depth map (2026-10-03)

**Purpose of this chat:** Put a Hurricane Helene flood depth, in metres, on the road segments near the surveyed high-water marks in western North Carolina, with an honest error number, and deliver one file keyed by `seg_id`.

## Context
Project "Unwatched Roads" (NC State hackathon, Oct 3-4 2026): predict pavement wear and Helene flood failure for every road segment in North Carolina. Nathan Stough owns CV/ML. Read `PLAN.md` first (untracked, repo root).

This is the second half of the flood-depth track. The first half (a camera depth reader) is built and merged; see "Analytical notes". The Helene depth map has NOT been started. No code, no plan, no go-ahead.

Where Nathan stands on it:
- He said the Helene depth map "feels really easy to implement".
- I told him it is easy to make and hard to make believable, because the 30 m terrain is too coarse (numbers below). He has not replied to that and has not said "go".
- So the first step is to confirm with him that he still wants it, and agree the method, before writing code.

What was established on Oct 3 (all checked by downloading, see the memory file `helene-flood-data-sources.md`):
- No imagery shows Helene water at its peak (Sept 27 2024 afternoon). Aerial and satellite sources are all a day to months late. Cameras cannot give Helene depths either: the USGS Asheville river camera died about 9 hours before the peak, and NCDOT camera frames were not archived.
- So depth has to come from surveyed high-water marks minus the ground.
- 2,193 Army Corps (USACE) high-water marks in 12 mountain counties, each with a water-surface elevation. They are saved locally (path below). No marks in Rutherford, McDowell, Polk, Burke, Caldwell or Ashe, so Chimney Rock and Old Fort cannot be checked.
- The data teammate has Helene labels in `data/raw/helene_*.parquet` (1,314 failed segments). His `src/pipeline/pull_helene.py` still waits for a manual zip for the USACE marks; do not edit his script unless Nathan asks.

## Working branch / worktree
- Nathan's rule since Oct 3 afternoon: every chat that writes code works on its own branch in its own worktree under `.claude/worktrees/`. Nothing is merged or pushed without his say; the "Demo completion checklist" chat has been doing the merges and pushes from the main checkout.
- `main` = `origin/main` at `65162c5` (it already contains the camera reader up to `babe1fa`).
- The previous chat's branch is `flood-depth` in `.claude/worktrees/flood-depth`, at `04e28d0`, clean, one commit ahead of what is merged. It has a training run in flight (below). Do NOT work in that worktree.
- For this work make a new branch `helene-depth` from `main` in `.claude/worktrees/helene-depth`. Easiest: ask the coordination chat ("Multi-chat messaging coordination") to create it the way it made the others. If you do it yourself, copy the existing mechanism exactly:
  ```
  cd ~/Desktop/Hack-NCSU
  git worktree add .claude/worktrees/helene-depth -b helene-depth main
  cd .claude/worktrees/helene-depth
  # each of data/raw, data/chips, data/processed holds only .gitkeep in a fresh worktree
  for d in raw chips processed; do rm data/$d/.gitkeep && rmdir data/$d && ln -s ~/Desktop/Hack-NCSU/data/$d data/$d; done
  git update-index --skip-worktree data/raw/.gitkeep data/chips/.gitkeep data/processed/.gitkeep
  ```
  `rmdir` refuses a non-empty folder, which is the safety. Once the links exist, never `rm -rf data/raw/` (trailing slash): that deletes the shared data.
- Main checkout untracked: `PLAN.md`, `docs/handoffs/`, `reports/`. Committing those was not approved.

## Environment / setup
```
cd ~/Desktop/Hack-NCSU/.claude/worktrees/helene-depth
/Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python -m src.pipeline.<module>
```
- Use the main checkout's interpreter from the worktree root. Do not run `uv sync` or bare `uv run` inside a worktree (it builds a second 1.4 GB environment).
- The pipeline chat is the only editor of `pyproject.toml` and `uv.lock`. Ask before adding a dependency. `py3dep`, `pysheds`, `rasterio`, `geopandas`, `scipy` are already installed.
- 18 GB RAM, about 15 GB free disk. `pysheds` cannot run a big grid in one piece; `src/pipeline/dem.py` tiles it.
- `~/Desktop` syncs to iCloud: write large files to a temporary name, then rename.
- The venue network blocks outgoing high ports. Ports 22, 80 and 443 work, so normal downloads are fine; a rented GPU box is not reachable without a VPN (ProtonVPN is installed; Nathan has to switch it on himself).
- Commit with explicit paths (`git commit -- <paths>`) and check `git diff --cached --name-only` first; the git index and stash are shared across worktrees.

## What to do next
1. Ask Nathan: does he still want the Helene depth map, and is "surveyed water marks minus finer terrain" the method? Plain English, short. Stop until he answers.
2. Get finer ground. `PLAN.md` asks for 10 m terrain in the Helene counties; it is not built. `py3dep.get_dem(bbox, resolution=10)` is the route already used at 30 m. Only the valleys near marked streams are needed, not whole counties.
3. Repeat the acceptance check at 10 m before anything else (it takes minutes): water-surface elevation minus ground at the 280 tape-measured marks, compared with the tape. The 30 m numbers to beat are in "tests" below. If 10 m is not clearly better, tell Nathan and stop; finer terrain (NC lidar) would be the next thing to look for.
4. Build a water surface along each stream. The marks carry `Stream` (99 names) and `Point_Number_on_Stream`, so they are already ordered along each stream. A simple, defensible version: interpolate water-surface elevation between neighbouring marks along the stream, then for points every 30 m along each nearby road segment subtract the 10 m ground. This design is my suggestion only; it is not tested and Nathan has not seen it.
5. Per segment report: deepest water anywhere along it, share of its length under water, how many marks informed it, distance to the nearest mark. A depth at the midpoint is meaningless: segments are 830 m long at the median and change 23 m in elevation along their length.
6. Hold out whole streams (not random marks) and report the miss in metres against the held-out marks, and separately against the 280 tape heights.
7. Write `data/processed/flood_helene_depth.parquet` keyed by `seg_id`. Do not change the `segments.parquet` column contract without Nathan. Avoid these names in `data/processed/`, which other chats use: `segments*.parquet`, `split.parquet`, `terrain.parquet`, `ablation*.csv`, `predictions.parquet`, `vit_frozen.parquet`, `vision/`, and everything starting `flood_camera_`.
8. Web research must not use Fable; use Sonnet or Opus agents in the background.

## IMPORTANT - tests & at-risk artifacts (make sure these survive)
- Test: `/Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python -m pytest -q -m "not network"` -> 89 passed in the `flood-depth` worktree at `04e28d0`. On `main` after all merges the demo chat reported 573 passed; I did not verify that number.
- Repo guards that will bite: `tests/test_folds.py` F6 fails if any file in `src/model/` contains the name of sklearn's group fold helper; `tests/test_repo_guards.py` G1 fails on iCloud duplicate files (names with " 2") under `src/`.
- Check (data in hand):
  ```
  /Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python -c "import geopandas as gpd; h=gpd.read_file('data/raw/flood_usace_hwm_helene.geojson'); print(len(h), int((h['Measured_Height__ft_']>0).sum()), h['Stream'].nunique())"
  ```
  -> `2193 280 99`
- Check (the numbers to beat, 30 m terrain, measured Oct 3): sample `data/processed/dem/dem.tif` (EPSG:32119, metres) at each mark; water surface = `HWM_Elevation__ft_` x 0.3048.
  - all 2,193 marks: water surface minus ground has median 0.6 m, and 34% come out negative (water "below" the ground);
  - the 280 marks with `Measured_Height__ft_` > 0: error against the tape has median absolute value 0.61 m, 90th percentile 2.63 m, correlation 0.36. The typical tape depth is 1.04 m.
- At-risk, git-ignored, NOT archived:
  - `data/raw/flood_usace_hwm_helene.geojson` (2.3 MB; re-downloadable, URL in "Pointers")
  - `data/raw/flood_ncgs_hwm_all_storms.geojson` (1.6 MB), `data/raw/flood_nwis_peaks_helene_nc.rdb` (80 gauge peaks)
  - `data/processed/dem/*.tif` (1.5 GB, about 15 min to regenerate with `python -m src.pipeline.dem`)
  - `data/raw/sunnyday/` (103 MB, 1,902 camera frames): the public feed drops these about Oct 7-10 2026, after which they CANNOT be pulled again. This is the one thing in the project that is truly unrecoverable. It belongs to the camera half, but do not delete it.
  - `data/processed/flood_camera_*` (camera results; the fine-tuned day-split half exists only there and in `~/Downloads/flood_camera_results.zip`)
- At-risk, untracked, NOT archived: `PLAN.md` (original at `~/Downloads/PLAN.md`), `reports/`, `docs/handoffs/` (including this file).
- In flight (owned by the previous chat, leave it alone): a fine-tune of the camera reader on the Mac's GPU chip, started 18:22 EDT Oct 3, expected to take about 90 minutes.
  - check: `tail -5 ~/Desktop/Hack-NCSU/.claude/worktrees/flood-depth/logs/flood_camera_finetune_camera.log`
  - writes `data/processed/flood_camera_oof_finetune_camera.parquet`, `flood_camera_metrics_finetune_camera.json`, `flood_camera_vits14.pt`, and hidden `.flood_camera_finetune_camera_*fold*.npz` files while running. Do not delete those.
  - it holds the GPU chip and a few GB of memory; a heavy local job will slow both.

## Analytical notes
High-water marks (USACE set, hosted by NCDOT Hydraulics):
- Fields: `HWM_Elevation__ft_` (water surface, feet, NAVD88; identical to `Surveyed_Height__ft_`), `Measured_Height__ft_` (height above ground; 0 means not measured; filled for 280), `HWM_Type` (Debris Line 1,011, Mud Line 652, Debris Snag 317, Seed Line 155, Eyewitness 37, Other 21), `HWM_Quality` (Excellent 646, Good 721, Fair 416, Poor 121, Very Poor 185, "ALTH" 104, meaning unknown), `Stream`, `Point_Number_on_Stream`, `Watershed`, `County`.
- Counties: Buncombe 617, Haywood 482, Yancey 280, Mitchell 215, Avery 166, Henderson 126, Jackson 82, Watauga 82, Madison 67, Swain 42, Transylvania 27, Macon 7.
- Busiest streams: French Broad 218, Swannanoa 160, North Toe 136, Pigeon 105, Jonathans Creek 101, Cane River 92.
- One point is in Tennessee state-plane coordinates although its State field says NC; drop it by bounds.
- Marks near our segments: 837 within 30 m (466 segments), 1,638 within 100 m (719 segments), 1,990 within 250 m (816 segments).
- The "2,587" in `PLAN.md` section 2 probably counts Tennessee and Virginia too; not confirmed.

Other sources:
- NC Geodetic Survey marks: `data/raw/helene_ncgs_hwm.parquet` (teammate's pull, all storms) or my copy; filter `storm_name` starting "Hurricane Helene" -> about 386, survey grade, elevation only, datum not stated in the layer. Overlap with the USACE set is not checked.
- NC Emergency Management flooded-area outline (2,082 polygons, yes/no only). It was adjusted to the NCGS marks, so it is not an independent check.
- USGS gauge peaks: 80 NC sites, stage above each gauge's own datum, so each needs its datum looked up before it is an elevation.

Terrain and segments:
- `data/processed/dem/{dem,slope,flowacc}.tif`: 30 m, EPSG:32119, metres. `flowacc` is a cell count (x 900 for m2) and undercounts big rivers because the state was processed in tiles (French Broad at Asheville reads 793 km2 against 2,448 km2); small and mid basins are right.
- The 15 hardest-hit mountain counties hold 12,308 segments. 54% pass within about 60 m of a stream draining 1 km2 or more, 26% beside one draining 10 km2 or more.
- `seg_id` is `ncdot:{ROUTEID}:{BEG_MP:.3f}`; geometry is in `data/raw/ncdot_joined.parquet` (EPSG:4326, WKB).

The camera half, for context only (done, merged, do not rework):
- `src/pipeline/sunnyday.py`, `src/model/flood_camera.py`, `notebooks/flood_camera_colab.ipynb`.
- Pretrained model as is, camera never seen: catches 86% of flooded frames, right 65% of the time, depth off by 8.7 cm. Known camera on a new day: 85%, 87%, 4.8 cm. Fine-tuned on a Colab T4, new day: 89%, 95%, 4.8 cm. Fine-tuned on a never-seen camera: not obtained yet (the in-flight run above is producing it at a smaller frame size).
- `data/processed/flood_camera_depth.parquet`: 3,093 frames, 1,003 cameras, 958 matched to a segment; `flood_camera_summary.json` has the runs side by side.

## Working with Nathan
- Plain English, short answers, concrete examples first. A jargon-heavy page was rejected.
- He gates work in stages: do the stage asked, report, stop.
- Say up front what you did without asking.
- Ask before pushing or merging. Research agents on Sonnet or Opus only, in the background.
- Several chats share this folder. "Multi-chat messaging coordination" tracks who owns which files; "Demo completion checklist" has been merging and pushing. Tell them your branch, files and output name.

## Pointers
- `PLAN.md` section 2 (flood labels) and section 7 (known weaknesses).
- Memory: `~/.claude/projects/-Users-nathanstough-Desktop-Hack-NCSU/memory/` -> `helene-flood-data-sources.md` (all checked URLs), `hack-ncsu-env-quirks.md`, `nathan-working-preferences.md`, `flood-camera-sources.md`.
- USACE marks, no login: `https://services.arcgis.com/NuWFvHYDMVmmxMeM/arcgis/rest/services/USACE_HWMs_Helene/FeatureServer/0/query` (page with `resultOffset`, `outSR=4326`, `f=geojson`).
- NCEM flooded-area outline: `https://services1.arcgis.com/YBWrN5qiESVpqi92/arcgis/rest/services/HeleneEstimatedFloodInundation_Jan2025/FeatureServer/0`.
- `src/pipeline/dem.py` (how the 30 m terrain was pulled and tiled), `src/pipeline/terrain_simple.py`.
- Teammate's Helene code, read-only for you: `src/pipeline/pull_helene.py`, `helene_points.py`, `helene_labels.py`.
- Earlier handoff for the whole flood-depth track: `docs/handoffs/2026-10-03_cv-flood-depth-handoff.md`.
