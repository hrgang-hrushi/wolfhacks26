> Note added 2026-10-03 15:00: written before a teammate's model code and the Helene labels landed. Rate labels are now 77,422 (age counted to the survey year) and cracking is 10,766 positive of 68,349 (above 10%). A model, a training loop and tests now exist on branch `model-hardening`. See `readme`.

# Handoff - CCTV pothole detection (2026-10-03)

**Purpose of this chat:** Pull traffic-camera (CCTV) imagery for North Carolina roads and detect potholes in it, as a side track to the main model.

## Context
Project "Unwatched Roads" (NC State hackathon, Oct 3-4 2026): predict pavement wear and Hurricane Helene flood failure for every road segment in North Carolina. Nathan Stough owns CV/ML. Two teammates own data (Helene labels, traffic, weather, city streets) and the map. Read `PLAN.md` first.

Built and pushed (4 commits on `main`):
- `src/pipeline/pull_ncdot.py`: both NCDOT layers statewide, joined into `data/raw/ncdot_joined.parquet`. `seg_id` is `ncdot:{ROUTEID}:{BEG_MP:.3f}`.
- `src/pipeline/dem.py`: 3DEP 30 m terrain into `data/processed/dem/{dem,slope,flowacc}.tif` (EPSG:32119).
- `src/pipeline/chips.py`: one 128x128 4-band NAIP 2022 chip per segment midpoint, saved as `data/chips/{seg_id with ':' as '_'}.npy`, uint8, shape (4,128,128), bands R,G,B,NIR. Only a 50-chip smoke test has been run.

There is no model, no training loop and no test suite yet. A plan-review for the modelling frame (5 km block folds, targets, allowed inputs, LightGBM baseline) is open at P1 and NOT frozen; Nathan still owes five yes/no answers on it.

This is a scope change. `PLAN.md` says "Cameras: OUT. No detection code." Nathan decided on Oct 3 to add it anyway. It must not break or delay the main plan.

What this track is up against (none of the leads are verified):
- No camera source has been checked. `PLAN.md` notes the NCDOT TIMS incident feed is current-only, and that is incidents, not cameras.
- Cameras cover roughly 1% of road miles; that gap is the project's own pitch.
- Footage collected from now covers under 24 hours. It can show potholes visible today. It cannot show wear over years.
- Traffic cameras are aimed at traffic at low resolution. Whether pavement defects are visible is unknown.
- The project has no pothole labels. `PLAN.md` lists Raleigh's public pothole reports (Jul 2025 onward) as a possible check.

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
1. Feasibility first. Report to Nathan before building anything bigger:
   - find NCDOT's public traffic-camera feed and read its terms of use;
   - count the cameras and note image size and refresh rate;
   - save about 50 stills from different cameras and judge whether the road surface is clear enough to see defects.
2. If it is feasible, write `src/pipeline/cctv.py` to list cameras (id, lat, lon, URL) and save stills on a timer to `data/raw/cctv/{camera_id}/{timestamp}.jpg`. `data/raw` is gitignored.
3. Snap each camera to its nearest `seg_id` using `data/raw/ncdot_joined.parquet`.
4. Find a pretrained pothole detector. Check that the weights are downloadable and the licence allows this use. Run it on the stills.
5. Agree with Nathan how the output is used: an extra clue for those segments, or a spot check on the main model's predictions.
6. Respect the feed's terms and rate limits. Do not work around bot detection. Keep raw stills local; they can show vehicles.

## IMPORTANT - tests & at-risk artifacts (make sure these survive)
- There is no test command and there are no tests. Do not assume coverage.
- Check: `uv run python -m src.pipeline.pull_ncdot --join-only` -> master 112,443 rows, asphalt 68,531, matched pairs 68,349 (99.73% of asphalt, 60.79% of master).
- Check: `uv run python -m src.pipeline.chips --limit 50 --overwrite` -> 50/50 chips, 0 failed, about 16 s.
- Check: `uv run python -m src.pipeline.dem` -> terrain step about 240 s, prints `4,161,030 interior sink cells` (reuses the cached `dem.tif`).
- At-risk, gitignored, NOT archived: `data/raw/*.parquet` (192 MB, about 1 min to regenerate), `data/processed/dem/*.tif` (1.5 GB, about 15 min), `data/chips/` (50 chips, 16 s).
- At-risk, untracked, NOT archived: `PLAN.md` (original at `~/Downloads/PLAN.md`), `reports/Road model augmentation and architectures.md` (only copy), `docs/handoffs/`.
- In flight: nothing is running.

## Analytical notes
- Segment table: 112,443 state road segments with geometry in `data/raw/ncdot_joined.parquet` (EPSG:4326).
- The main model predicts wear rate and a heavy-cracking flag from clues; it does no detection. A camera track would be the only place real potholes appear.
- If camera coverage turns out to be a few hundred segments, say so plainly. That is a validation set, not a training set.

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
