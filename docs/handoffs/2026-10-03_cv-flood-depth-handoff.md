> Note added 2026-10-03 15:00: written before a teammate's model code and the Helene labels landed. Rate labels are now 77,422 (age counted to the survey year) and cracking is 10,766 positive of 68,349 (above 10%). A model, a training loop and tests now exist on branch `model-hardening`. See `readme`.

# Handoff - CV flood depth (2026-10-03)

**Purpose of this chat:** Use computer vision to estimate flood depth on road segments, extending the flood half of Unwatched Roads beyond a yes/no answer.

## Context
Project "Unwatched Roads" (NC State hackathon, Oct 3-4 2026): predict pavement wear and Hurricane Helene flood failure for every road segment in North Carolina. Nathan Stough owns CV/ML. Two teammates own data (Helene labels, traffic, weather, city streets) and the map. Read `PLAN.md` first.

Built and pushed (4 commits on `main`):
- `src/pipeline/pull_ncdot.py`: both NCDOT layers statewide, joined into `data/raw/ncdot_joined.parquet`. `seg_id` is `ncdot:{ROUTEID}:{BEG_MP:.3f}`.
- `src/pipeline/dem.py`: 3DEP 30 m terrain into `data/processed/dem/{dem,slope,flowacc}.tif` (EPSG:32119).
- `src/pipeline/chips.py`: one 128x128 4-band NAIP 2022 chip per segment midpoint, saved as `data/chips/{seg_id with ':' as '_'}.npy`, uint8, shape (4,128,128), bands R,G,B,NIR. Only a 50-chip smoke test has been run.

There is no model, no training loop and no test suite yet. A plan-review for the modelling frame (5 km block folds, targets, allowed inputs, LightGBM baseline) is open at P1 and NOT frozen; Nathan still owes five yes/no answers on it.

What this track is up against (none of the leads are verified):
- The only imagery in the project is NAIP 2022, two years before Helene (Sept 2024). There is no floodwater in it.
- The current flood design is yes/no per segment: any Helene damage point within 30 m. Those labels are not in hand; the data teammate is looking, status unknown.
- Leads for depth: USACE Helene high-water marks (2,587 points with measured water heights, URL in `PLAN.md` section 2); post-Helene NC OneMap orthoimagery (the plan's fallback); NOAA post-storm aerial imagery; traffic cameras (current conditions only).

## Working branch / worktree
`main` in `~/Desktop/Hack-NCSU` (single worktree), in sync with `origin` = `hrgang-hrushi/wolfhacks26` (public) at `d7b4370`.
Untracked: `PLAN.md`, `reports/`, `docs/handoffs/`, and iCloud duplicate files ending in ` 2` (do not delete them without Nathan's yes).
Two other chats are working in this same folder on `main` at the same time (the other two handoffs of Oct 3). Stay in your own files, commit only your own files, never `git add -A`.

## Environment / setup
```
cd ~/Desktop/Hack-NCSU
uv sync
uv run python -m src.pipeline.pull_ncdot --join-only
```
- Run modules as `uv run python -m src.<package>.<module>` from the repo root. The editable install is unreliable here (hidden `.pth` files).
- `numpy` is pinned below 2.4 for pysheds.
- 18 GB RAM, about 16 GB free disk.
- `~/Desktop` syncs to iCloud. Write large files to a temporary name, then rename.
- Network: about 10 MB/s in general, about 1 MB/s per connection to the NAIP files (Azure West Europe). The statewide chip download is about 10 hours here.

## What to do next
1. Feasibility first. Report to Nathan before building:
   - what imagery actually shows Helene water on or near roads, at what resolution and date;
   - what measured depths exist to check against (the high-water marks).
2. Pick the method the data supports:
   - flood-extent mapping on event imagery, then the terrain model turns the water edge into a water surface and a depth per segment;
   - depth from reference objects (vehicles, signs) in ground or camera photos, if flooded photos exist;
   - a non-CV fallback: water surface from high-water marks minus ground elevation.
3. Define the output: depth in metres per `seg_id` with a confidence, or depth classes.
4. Hold out some high-water marks and report the error against them in plain numbers.
5. Deliver one file keyed by `seg_id`. Do not change the `segments.parquet` column contract without Nathan.
6. Ask Nathan for the data teammate's status on Helene records before duplicating that search.

## IMPORTANT - tests & at-risk artifacts (make sure these survive)
- There is no test command and there are no tests. Do not assume coverage.
- Check: `uv run python -m src.pipeline.pull_ncdot --join-only` -> master 112,443 rows, asphalt 68,531, matched pairs 68,349 (99.73% of asphalt, 60.79% of master).
- Check: `uv run python -m src.pipeline.chips --limit 50 --overwrite` -> 50/50 chips, 0 failed, about 16 s.
- Check: `uv run python -m src.pipeline.dem` -> terrain step about 240 s, prints `4,161,030 interior sink cells` (reuses the cached `dem.tif`).
- At-risk, gitignored, NOT archived: `data/raw/*.parquet` (192 MB, about 1 min to regenerate), `data/processed/dem/*.tif` (1.5 GB, about 15 min), `data/chips/` (50 chips, 16 s).
- At-risk, untracked, NOT archived: `PLAN.md` (original at `~/Downloads/PLAN.md`), `reports/Road model augmentation and architectures.md` (only copy), `docs/handoffs/`.
- In flight: nothing is running.

## Analytical notes
- Terrain rasters exist at 30 m: elevation, slope, flow accumulation. `PLAN.md` wants 10 m for the Helene counties; that is not built.
- Flow accumulation undercounts large rivers because the state was processed in tiles (French Broad at Asheville reads 793 km2 against a 2,448 km2 basin). Small and mid basins match gauges (Swannanoa 330 vs 337 km2).
- Helene damage probably clusters by river basin, so test by holding out whole basins.
- Positives will be rare. Report hits among the top-ranked segments, not overall accuracy.

## Working with Nathan
- Plain English, short answers. A jargon-heavy page was rejected as not understandable.
- He gates work in stages. Do the stage asked, report, and stop.
- Ask before pushing. Pushing pipeline code to `main` was approved; committing `PLAN.md`, the README draft, reports or handoffs was not.
- Web research must not use Fable. Use Sonnet or Opus, and run it in the background so chat messages cannot interrupt it.

## Pointers
- `PLAN.md` (source of truth; section numbers are how Nathan refers to work).
- `reports/Road model augmentation and architectures.md` (research of Oct 3; marks what was fact-checked and what was not).
- Memory: `~/.claude/projects/-Users-nathanstough-Desktop-Hack-NCSU/memory/`.
- Plain-English model flowchart: https://claude.ai/artifact/HdP8sDFAKLgg5pkmxP5YaX
- Draft README: `~/Downloads/README.md` (not in the repo).
