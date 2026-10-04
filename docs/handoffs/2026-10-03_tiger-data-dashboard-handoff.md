# Handoff - Tiger Data dashboard and GoDaddy domain (2026-10-03)

**Purpose of this chat:** Build the officials' repair dashboard for Unwatched Roads on a Tiger Data (Postgres + TimescaleDB) database, so the project can enter the "Best Use of Tiger Data" prize, and get the demo onto a GoDaddy Registry domain for the "Best Domain Name" prize.

## Context
Project "Unwatched Roads" (NC State hackathon, Oct 3-4 2026): predict pavement wear, cracking and Hurricane Helene flood failure for every state road segment in North Carolina. Nathan Stough owns CV/ML and is running several Claude chats in parallel. Read `README.md` first; it has the plain-English overview, the measured results and an "End goals" table.

What exists as of 17:55 on Oct 3:
- Predictions for all 112,443 state segments (wear rate, years until Poor, cracking risk, flood risk), held-out where a label exists.
- Pothole evidence: Charlotte and Raleigh report pulls, labels per segment, and checks against the predictions.
- NCDOT traffic cameras: a keyless list of 1,158 cameras matched to segments, and one round of stills.
- Flood depth from cameras: 1,902 labelled frames from coastal roadside cameras and a first depth reader, run on the NCDOT stills too. This is on branch `flood-depth`, not yet merged.
- Crash counts and estimated traffic per segment.

What does not exist: any dashboard, map or export. `web/` holds only `.gitkeep`. End goals 1 (repair dashboard for officials) and 2 (risk file for map companies) are unbuilt. That is this chat's job.

Sponsor prize text Nathan pasted:
- **Tiger Data:** "extends PostgreSQL into an ultra-fast foundation for real-time data, time-series metrics, and complex analytics: standard SQL, relational and metric data in one database, real-time dashboards via Continuous Aggregates, and 90%+ compression on free-tier instances. The most innovative, impactful, and performance-driven use of Tiger Data wins - think real-time IoT monitoring, AI-driven analytics dashboards, or financial prediction engines."
- **GoDaddy Registry:** "Register your domain name with GoDaddy Registry for a chance to win."

Nathan said he is creating the Tiger Data account and service himself right now.

## Working branch / worktree
- Branch `tiger-dashboard`, worktree `/Users/nathanstough/Desktop/Hack-NCSU/.claude/worktrees/tiger-dashboard`, created from local `main` at `a4cf879`, clean. Enter it with EnterWorktree using `path` (not `name`). Write all code there. Commit only on this branch, with explicit paths.
- Nathan's rule: every chat that writes code works on its own branch in its own worktree. Nothing is merged into main or pushed without his say.
- Local `main` (`a4cf879`) is 16+ commits ahead of `origin/main` (`742cf54`): the "Demo completion checklist" chat merged `model-hardening`, `cctv-potholes`, `image-augmentation` and `traffic-crashes` and has not pushed yet. `flood-depth` (3 commits) is still unmerged, waiting on a Colab run.
- `origin` is `hrgang-hrushi/wolfhacks26`: public and owned by a teammate.
- Untracked in the main checkout, not yours: `PLAN.md`, `docs/handoffs/`, `reports/`.

## Environment / setup
```
# from the worktree root
/Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python -m pytest tests/test_repo_guards.py -q
```
- **Python:** run from the worktree root with the main environment's interpreter, as above. It imports the worktree's own `src`. Do not run `uv sync` or a bare `uv run` inside the worktree; that builds a second 1.4 GB environment and the disk has 20 GB free.
- **Data is shared, not copied.** `data/raw`, `data/chips` and `data/processed` in the worktree are symlinks to the main checkout. Never delete or replace them; `rm -rf data/raw/` with a trailing slash would delete the shared data.
- **Dependencies:** `pyproject.toml` and `uv.lock` are shared and other chats depend on them. A database driver or web framework is a new dependency. Prefer `uv run --with <package>` or a `web/requirements.txt` with its own small environment under `web/`, and tell Nathan which you chose. Do not edit `pyproject.toml` without his say.
- **Not installed:** `tippecanoe`, `psql`. Installed: `node`, `npm`.
- **Secrets:** the Tiger connection string and any API key go in `data/raw/tiger.env`, which git ignores. `.env` at the repo root is NOT ignored and the repo is public. Never print, commit or paste a credential. Nathan puts the values in the file himself.
- **Git:** the stash stack is shared by every worktree; never use bare `git stash` or `git stash pop`.
- **Machine:** 18 GB RAM. `~/Desktop` syncs to iCloud; write large files to a temporary name, then rename.
- **Known crash:** training a LightGBM model and running PyTorch in the same process hangs or crashes on this Mac. Run `tests/vision` in a separate process from the other test folders.

## What to do next
1. **Test the network before anything else.** The venue network blocks most outgoing ports. Measured at 17:52: 22, 80, 443 and 2222 open; 5432, 8080, 30776 and 34567 blocked. Tiger Cloud services listen on a high port, so the database is probably unreachable from here. As soon as Nathan has the service, test it: `nc -z -G 5 <host> <port>`. If it is blocked, tell him at once. The fixes are a phone hotspot or VPN for the Mac, or hosting the small API somewhere that can reach the database and serving the dashboard over 443.
2. **Ask Nathan three things up front:** the submission deadline; whether a teammate is already building the map (the plan gave the map to a teammate, and `web/` is empty on GitHub); and whether he wants Gemini features in the dashboard as well (he was offered an "explain this road" button and a camera photo check).
3. **Design the database to show what the prize asks for,** then confirm the design with Nathan before loading. A suggested shape, not a decision:
   - Relational: `segments` (112,443 rows) with rating, survey year, predictions, held-out flags, crash rate, pothole counts, and NCDOT's `PMS_TREATMENT_NAME` and `TREATMENT_COST`. Geometry in PostGIS if the service has it, otherwise serve shapes from `handoff/predictions_geo.parquet`.
   - Time series (hypertables): camera flood readings (`data/processed/flood_camera_depth.parquet`, 3,093 rows, Sept 24 to Oct 3), water-level sensor readings every 6 minutes (`data/raw/sunnyday/levels/*.json`, 11 stations), and pothole reports (`data/raw/pothole_reports.parquet`, 17,790 rows, July 2016 to Oct 2026).
   - Continuous aggregates: hourly worst depth per camera and segment, for a "flooded in the last hour" alert; monthly pothole reports per segment.
   - Compression on old chunks, with the measured ratio reported for the pitch.
   Verify the current Tiger Data syntax in its docs; do not write it from memory.
4. **Build the smallest dashboard that shows end goal 1:** a ranked work list (fix now, within a year, within five), a map, a road detail panel, and the alert list. `PLAN.md` section 5 has the original map design (MapLibre GL, deck.gl, PMTiles). Put it under `web/`.
5. **Add the export for end goal 2:** a downloadable per-road risk file.
6. **Live data:** if you want fresh camera readings, call the existing collector in `src/pipeline/cctv.py`. Do not write a second NCDOT image puller; one polite caller was agreed with the other chats.
7. **GoDaddy domain:** only Nathan can register it, because it is an account and a purchase or promo code. Ask him for the hackathon's exact instructions for this prize, propose three names, and tell him what DNS records the hosting needs. Hosting the demo publicly is outward-facing; get his explicit yes on where it is hosted before deploying anything.
8. **Report in plain English.** Nathan wants short answers, everyday words, and an explicit list of anything done without asking.

## IMPORTANT - tests & at-risk artifacts (make sure these survive)
- Test (base suite, verified by the coordination chat at `64609f1`): `/Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python -m pytest tests -q -m "not network" --ignore=tests/vision --ignore=tests/potholes --ignore=tests/cctv --ignore=tests/crashes` -> expected 89 passed (83 fast, 6 real-data).
- Tests reported by other chats, NOT rerun by the coordination chat: `tests/potholes` + `tests/cctv` 114 new tests (197 fast with the base 83); `tests/vision` 307; `tests/crashes` count not recorded. Run `tests/vision` in its own process.
- There are no dashboard or database tests. Do not assume coverage. Add at least a load check: row counts in the database equal the parquet row counts below.
- Numbers to reproduce when loading:
  - `handoff/predictions_geo.parquet`: 112,443 rows; columns `seg_id, geometry, pred_rate, pred_years_to_poor, pred_crack, pred_flood, in_helene_zone, rate_heldout, crack_heldout, flood_heldout`.
  - `handoff/traffic_crash.parquet` and `data/processed/traffic_crash.parquet`: 112,443 rows.
  - `data/processed/pothole_labels.parquet`: 112,443 rows. `data/raw/pothole_reports.parquet`: 17,790 rows.
  - `data/raw/cctv/cameras.parquet`: 1,158 cameras. `data/raw/cctv/stills.parquet`: 998 rows, one round.
  - `data/processed/flood_camera_depth.parquet`: 3,093 rows.
  - Helene zone: 32,558 segments, 1,266 damaged. Top 50 by `pred_flood` in the zone: 18 damaged.
- At-risk, gitignored, NOT archived (only copy is this Mac plus iCloud Desktop sync):
  - `data/raw/sunnyday/` (214 MB). The source deletes these camera frames about two weeks after capture, so from Oct 7 they cannot be downloaded again. No licence was found for them; keep them out of the repo.
  - `data/raw/cctv/` (118 MB), `data/raw/pothole_reports.parquet`, everything in `data/processed/` (1.7 GB) including `results/`.
- At-risk, untracked, NOT archived: `PLAN.md`, `docs/handoffs/`, `reports/` in the main checkout.
- At-risk, local only: local `main` is ahead of GitHub, and branch `flood-depth` exists only on this Mac.
- At-risk, session temp: the explainer page's source is in the coordination chat's scratchpad. The published copy is at https://claude.ai/artifact/RNUtgPcpEVJV7C9ePigBNF (private to Nathan).
- In flight:
  - Flood fine-tune on Google Colab. Check: `ls ~/Downloads/flood_camera_results.zip`. The "CV flood depth estimation" chat folds it in, then `flood-depth` can merge.
  - "Demo completion checklist" chat is merging branches and plans to push main. Check: `git -C ~/Desktop/Hack-NCSU log --oneline origin/main..main`.
  - "Image augmentation for vision model" chat has a Colab package at `data/processed/vision/colab/` that has not been run.
  - Rented vast.ai boxes are unreachable from this network.

## Analytical notes
- Measured results (held-out, 5 km spatial blocks): wear-rate miss 0.749 rating points a year against 0.965 with no model; cracking ranking score 0.422 against 0.158; Helene damage 18 of the top 50 against about 2 by chance.
- Pothole check, Charlotte: roads ranked worst by the held-out predictions draw about 3 times the reports per mile of the best-ranked roads with similar traffic (wear 3.3, cracking 3.8). NCDOT's own rating gives 7.7. Raleigh shows no lift for wear.
- Flood reader on dry NCDOT stills: 10 false alarms in 1,191. Cameras pan and zoom, so a view is not fixed between pulls. Say this on the dashboard; do not present a camera flag as a confirmed flood.
- Crash counts and estimated traffic do not improve the predictions. An open question for Nathan is whether crash rate should feed the repair ranking and the risk file.
- City streets are not scored. Do not show them as if they were.
- `pred_years_to_poor` is blank for 1,643 segments whose rating is out of date; treat blank as unknown, not zero.
- `seg_id` format is `ncdot:{ROUTEID}:{BEG_MP:.3f}`. Projected coordinates are EPSG:32119.
- Other chats agreed: one branch per chat, explicit-path commits, no README edits without Nathan's say, and no teammate names in documents.

## Pointers
- `README.md`: overview, end goals, measured results, limitations.
- `PLAN.md` (untracked, main checkout): original plan; section 5 is the demo design, and the "End goals" block was added today.
- `docs/specs/` and `docs/reports/`: run specs and plans from the other tracks. The pothole spec has a paste-ready results paragraph.
- `data/processed/results/*.md`: pothole, camera and crash result tables.
- Memory files in `~/.claude/projects/-Users-nathanstough-Desktop-Hack-NCSU/memory/`: `unwatched-roads-plan`, `team-repo-wolfhacks26`, `hack-ncsu-env-quirks`, `nathan-working-preferences`, `ncdot-camera-feed-access`, `nc-pothole-report-sources`, `flood-camera-sources`.
- Coordination: message the "Multi-chat messaging coordination" chat with your planned file list before you start, and when you finish.
