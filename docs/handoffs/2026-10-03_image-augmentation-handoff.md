> Note added 2026-10-03 15:00: written before a teammate's model code and the Helene labels landed. Rate labels are now 77,422 (age counted to the survey year) and cracking is 10,766 positive of 68,349 (above 10%). A model, a training loop and tests now exist on branch `model-hardening`. See `readme`.

# Handoff - image augmentation (2026-10-03)

**Purpose of this chat:** Add image augmentation to the vision-model path of Unwatched Roads and show, on held-out map squares, whether it helps.

## Context
Project "Unwatched Roads" (NC State hackathon, Oct 3-4 2026): predict pavement wear and Hurricane Helene flood failure for every road segment in North Carolina. Nathan Stough owns CV/ML. Two teammates own data (Helene labels, traffic, weather, city streets) and the map. Read `PLAN.md` first.

Built and pushed (4 commits on `main`):
- `src/pipeline/pull_ncdot.py`: both NCDOT layers statewide, joined into `data/raw/ncdot_joined.parquet`. `seg_id` is `ncdot:{ROUTEID}:{BEG_MP:.3f}`.
- `src/pipeline/dem.py`: 3DEP 30 m terrain into `data/processed/dem/{dem,slope,flowacc}.tif` (EPSG:32119).
- `src/pipeline/chips.py`: one 128x128 4-band NAIP 2022 chip per segment midpoint, saved as `data/chips/{seg_id with ':' as '_'}.npy`, uint8, shape (4,128,128), bands R,G,B,NIR. Only a 50-chip smoke test has been run.

There is no model, no training loop and no test suite yet. A plan-review for the modelling frame (5 km block folds, targets, allowed inputs, LightGBM baseline) is open at P1 and NOT frozen; Nathan still owes five yes/no answers on it.

What this track is up against:
- There is nothing to augment yet: no vision model, no training loop, and 50 chips on disk.
- Results cannot be scored until the 5 km block folds and the labels exist, and that frame is not built (P1 is open).

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
1. Read the Augmentation and Image models sections of the research report, and `PLAN.md` section 4.
2. Ask Nathan two things before building: which chips to use (a county subset now, or wait for the statewide download), and which model comes first (frozen DINOv2/DINOv3 embeddings, or the fine-tuned ViT-S).
3. Build an augmentation module for (4,128,128) uint8 chips:
   - the 8 flip and quarter-turn views;
   - mild brightness and contrast changes applied to all four bands together;
   - small shifts of a few pixels;
   - NDVI from band 3 (NIR) and band 0 (red).
   Leave out hue/saturation shifts, MixUp, CutMix, random erasing and RandAugment.
4. Use it in two places: average frozen embeddings or predictions over the 8 views, and apply it on the fly in the fine-tune loop.
5. Keep every augmented copy in its segment's fold.
6. Compare with and without augmentation on held-out blocks and report the difference in plain numbers.
7. Write tests as you go (none exist): the 8 views are distinct and keep shape and dtype; all-band brightness leaves NDVI close to unchanged; a fixed seed gives the same output; no segment's copies cross folds.

## IMPORTANT - tests & at-risk artifacts (make sure these survive)
- There is no test command and there are no tests. Do not assume coverage.
- Check: `uv run python -m src.pipeline.pull_ncdot --join-only` -> master 112,443 rows, asphalt 68,531, matched pairs 68,349 (99.73% of asphalt, 60.79% of master).
- Check: `uv run python -m src.pipeline.chips --limit 50 --overwrite` -> 50/50 chips, 0 failed, about 16 s.
- Check: `uv run python -m src.pipeline.dem` -> terrain step about 240 s, prints `4,161,030 interior sink cells` (reuses the cached `dem.tif`).
- At-risk, gitignored, NOT archived: `data/raw/*.parquet` (192 MB, about 1 min to regenerate), `data/processed/dem/*.tif` (1.5 GB, about 15 min), `data/chips/` (50 chips, 16 s).
- At-risk, untracked, NOT archived: `PLAN.md` (original at `~/Downloads/PLAN.md`), `reports/Road model augmentation and architectures.md` (only copy), `docs/handoffs/`.
- In flight: nothing is running.

## Analytical notes
- Labels: wear rate exists for 85,521 of 112,443 segments; the cracking flag for 68,349 (15.8% positive). Helene flood labels are not in hand.
- The road is about 12 px wide in a chip and cracks are not visible, so the model reads surroundings. Random crops can cut the road out.
- The research run produced no fact-checked evidence on any single augmentation. The recommendations above are standard practice plus judgment.
- Expect a small gain. One published study fell from 88% to 79% when whole roads were held out (read from the paper, not fact-checked).
- DINO models take colour only. The near-infrared band reaches the model through NDVI.

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
