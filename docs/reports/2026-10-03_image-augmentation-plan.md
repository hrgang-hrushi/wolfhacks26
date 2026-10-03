# Implementation plan: image augmentation for the vision path (2026-10-03)

Run spec: `docs/specs/2026-10-03_image-augmentation.md` (decisions D1 to D17, acceptance AC1 to AC9, tests A, D, M, E, F, C). Reviewed by Codex on 2026-10-03; the thirteen findings and how each was handled are at the end.

Context for a reviewer: there is no `CLAUDE.md` or `AGENTS.md`. `readme` holds measured results; `PLAN.md` (untracked) is the project plan. Python 3.11, `uv`; modules run from the repo root as `uv run python -m src.<pkg>.<module>`. Several chats share this working tree and git index. This change creates new files only. A separate change ("model hardening", `docs/specs/2026-10-03_model-hardening.md`, approved, not yet executed) will rewrite `data/processed/segments_targets.parquet` with stable folds and corrected labels, and will add `tests/conftest.py`, `tests/test_folds.py` and pytest config to `pyproject.toml`. This plan depends on that file and avoids those paths.

Where the work happens (instruction of 2026-10-03, relayed by the coordination chat): code and tests are written in the worktree `/Users/nathanstough/Desktop/Hack-NCSU/.claude/worktrees/image-augmentation` on branch `image-augmentation` (created at `48520d9`), and committed there. Nothing goes onto `main` and nothing is merged or pushed without Nathan's say. In the worktree, `data/raw`, `data/chips` and `data/processed` are symlinks to the main checkout's folders, so inputs and `data/processed/vision/` are shared. Python is the main checkout's environment, written `$PY` below: `/Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python` (pytest 9.1.1, torch 2.14.1), run from the worktree root. No `uv sync` or bare `uv run` in the worktree (it would build a second 1.4 GB environment), no `git stash`, and the three data links are never deleted or replaced. The docs for this change stay untracked in the main checkout.

## Current state (verified 2026-10-03, HEAD `48520d9`)

- `src/pipeline/chips.py` (189 lines): `chip_path(seg_id)` on lines 50 to 52; `--seed` only matters together with `--limit` (lines 82 to 85); CLI flags `--limit`, `--seed`, `--workers` on lines 127 to 129; the banner with the "midpoints outside NAIP coverage" count on lines 146 to 150; the progress line `[chips] done/total ... N failed ... done in Xs` on line 166, where `done` counts successes plus failures; `_failed.csv` written only when a run has failures (lines 182 to 185). It skips chips that already exist.
- `src/model/train_vit.py` (122 lines): `DS.__getitem__` reads `np.load(chip_path(id))[:3, 1:127, 1:127] / 255` (line 35) and applies two random flips with global `np.random` (lines 36 to 38); `Net` (lines 45 to 54) is `timm` `vit_small_patch14_dinov2.lvd142m` at `img_size=126` with `nn.Linear(384, 2)`, attributes `b` (backbone) and `h` (head), `forward(x, emb=False)`; `loader` uses 4 workers and `drop_last=shuffle` (line 58); `predict` (lines 61 to 67); folds from `GroupKFold` (lines 78 to 81); the frozen export is `PCA(16, random_state=0).fit_transform(E)` into `im_emb0..15` (lines 91 to 94); optimiser `AdamW` with backbone 2e-5, head 1e-3, weight decay 0.05 (lines 101 to 102); masked loss, L1 for rate plus binary cross-entropy for cracking (lines 110 to 112). Module level sets `dev`, `MEAN`, `STD`.
- `data/chips/`: 50 chips, equal to `--limit 50 --seed 0` (checked: 50 of 50 names match the seed-0 sample). All are (4,128,128) uint8 with no blank fill.
- `data/processed/segments_targets.parquet`: the pre-hardening file. 112,443 rows, 103 columns, with `mid_x`, `mid_y` (EPSG:32119), `y_rate` (81,191), `y_crack` (68,349, prevalence 0.414), `y_helene_failed`, `in_helene_zone` (32,558 zone rows, 1,266 positive), `pv_COUNTY`. No `fold` or `split_block`. After hardening: 77,422 rate labels, 10,766 cracking positives, `split_block`, `fold = crc32(split_block) % 5`.
- `data/raw/ncdot_joined.parquet` (78 MB, `seg_id` unique: 112,443 of 112,443) and `data/raw/naip_2022_index.parquet` (0.3 MB) exist.
- `pyproject.toml` already lists `torch>=2.14.1`, `timm>=1.0.30`, `scipy`, `scikit-learn`. Locally torch 2.14.1 and timm 1.0.30 import. `uv.lock` pins the CUDA 13 build of torch for Linux (`nvidia-cudnn-cu13`), which needs an NVIDIA driver of 580 or newer. `tests/` does not exist. `pytest` is not a dependency.
- vast.ai: the CLI is `~/Powerlifting-Analyzer/.venv/bin/vastai` (not on `PATH`), authenticated, $32.93 credit, 0 instances, one SSH key registered that matches `~/.ssh/id_ed25519.pub`. RTX 5090 offers seen at planning time, all with CUDA 13.0 or newer: Slovakia $0.59 an hour (32 cores, 62 GB, 899 Mbps), Bulgaria $0.62, Czechia $0.87, Denmark $1.00 (32 cores, 123 GB, 7,620 Mbps). Instances are listed with `vastai show instances-v1 --raw` (`instances[].id`, `actual_status`, `ssh_host`, `ssh_port`); the older `show instances` is gone (HTTP 410). Offer fields used: `id`, `machine_id`, `rentable`, `verification`, `num_gpus`, `gpu_name`, `gpu_ram` (MiB), `dph_total`, `cpu_cores_effective`, `cpu_ram` (MiB), `disk_space`, `inet_down`, `inet_down_cost`, `inet_up_cost`, `reliability2`, `cuda_max_good`, `geolocation`, `storage_cost` ($ per GB per month).
- Reused from `~/Powerlifting-Analyzer/scripts/fleet/`: the offer-filter logic (`offer_filter.py`), rent and destroy calls (`campaign.py` lines 65 to 78: `vastai create instance <offer> --image pytorch/pytorch --disk N --ssh --raw` returning `new_contract`; `echo y | vastai destroy instance <id>`), and the SSH retry pattern (`provision_box.sh`: 5 tries, 15 s apart). Rewritten here as one small Python file; nothing is imported from that repo.

## Step 0. Pre-flight

1. Enter the worktree. `git branch --show-current` prints `image-augmentation`; `pwd` is the worktree root. Record `git merge-base main HEAD` as `<base>`.
2. `git status --short` shows nothing staged. `find src tests scripts -name "* 2*"` prints nothing. `ls -la data` shows the three links.
3. `$PY -c "import src, os; print(os.path.dirname(src.__file__))"` prints the worktree's `src`.
4. Tell the pipeline chat that this change is starting and that local runs are light (tests only).

## Step 1. Cloud driver and its tests (Mac, no spending)

Create `scripts/cloud/box.py` (standard library only). Every vast.ai and SSH call goes through one module-level `_sh` function so tests can replace it.

Choosing and paying:
- `vastai_bin()`: `$VASTAI_BIN`, else `shutil.which("vastai")`, else `~/Powerlifting-Analyzer/.venv/bin/vastai`; raise if none exists.
- `filter_offers(offers, gpu_names=("RTX 5090",), min_gpu_ram_mib=24000, max_dph=1.30, min_cores=16, min_ram_gb=48, min_disk=100, min_inet=800, min_reliability=0.98, min_cuda=13.0, n=5)`: keep rentable, verified offers with `num_gpus == 1`, an allowed `gpu_name`, enough GPU memory, and `inet_down_cost` and `inet_up_cost` at most 0.001; one per `machine_id`; sorted European hosts first, then by `dph_total`; raise `ValueError("no offers matched")` when empty. The CLI retries once with `gpu_names=("RTX 4090",)` before giving up.
- Constants `CAP_USD = 15.0`, `MAX_HOURS = 8`, `MAX_REPLACEMENTS = 2`, `RESERVE_MIN = 20`.
- `State` at `logs/cloud_box_state.json` and `History` at `logs/cloud_box_history.json` (`logs/` is gitignored), both written through a temporary file and `os.replace`. A rental records `instance_id`, `dph`, `storage_rate` (`storage_cost * disk_gb / 730` dollars an hour), `rented_at`, `deadline_epoch`, SSH host and port, `jobs` (name to execution id), `last_run_at`, `last_verified_pull_at`, `watchdog_armed`, and a list of billing intervals (`start`, `end`, `rate`): the full price while running, the storage rate while stopped.
- `spent_total(now)`: every interval in the history plus the current rental. `cap_left(now) = CAP_USD - spent_total(now)`.
- `allowed_hours(dph, cap_left) = min(MAX_HOURS, cap_left / dph)`. `rent` refuses when this is under 1 hour. `deadline_epoch = rented_at + allowed_hours * 3600`, fixed at rental and never extended by a restart.

Renting, with bounded failure paths:
- `rent(offer)`: refuse per the budget; `vastai create instance <id> --image pytorch/pytorch --disk 100 --ssh --raw`; save `instance_id`, `rented_at` and `deadline_epoch` at once; poll `show instances-v1` every 15 s up to 15 min for `running`; save SSH details.
- `abandon(reason)`: `destroy`, confirm gone, close the billing interval into the history with the reason. Used by every failure path where the box holds nothing of value. `rent` calls it if the box never reaches `running` or SSH fails after the retries. A third replacement in one campaign raises instead of renting.
- `ssh(cmd, retries=5, backoff=15)` with `-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=logs/cloud_known_hosts -o ConnectTimeout=25`.
- `selfstop_test()`: on the box, check that `CONTAINER_ID` and `CONTAINER_API_KEY` are set, `pip install -q vastai`, and run `vastai stop instance $CONTAINER_ID --api-key $CONTAINER_API_KEY`. From the Mac, poll up to 3 min for the instance to leave `running`; then `vastai start instance <id>` and poll up to 10 min for `running`. If the variables are missing or the stop is not observed: `abandon("no self-stop")` and raise `SelfStopUnavailable` (the plan then stops and asks Nathan). If the restart fails: `abandon("restart failed")` and rent a replacement.
- `arm_watchdog()`: on the box, `setsid nohup sh -c 'while [ $(date +%s) -lt <deadline_epoch> ]; do sleep 30; done; pkill -f "src\.(model|pipeline)"; touch /root/DEADLINE_HIT; vastai stop instance $CONTAINER_ID --api-key $CONTAINER_API_KEY' > /root/watchdog.log 2>&1 & echo $! > /root/watchdog.pid`. `watchdog_alive()` is `kill -0 $(cat /root/watchdog.pid)`. Armed after the self-stop test and again after any restart, always with the original `deadline_epoch`.
- `stop()` and `start()`: `vastai stop instance` and `vastai start instance` from the Mac, switching the billing interval between the full price and the storage rate; `start` re-arms the watchdog; if the box cannot restart within 10 min, `abandon` and report.

Shipping code:
- `PUSH_LIST`: `src/`, `tests/vision/`, `scripts/cloud/`, `pyproject.toml`, `uv.lock`, `.python-version`, `data/raw/ncdot_joined.parquet`, `data/raw/naip_2022_index.parquet`, and `data/processed/segments_targets.parquet` when present. `bundle_files()` expands it, dropping `__pycache__`, `*.pyc` and iCloud duplicates (`* 2.*`).
- `scan_for_keys(files)`: refuse a bundle that contains a file named like `vast_api_key`, `*.pem`, `id_*`, `.env`, or any text file with `secret_access_key=`, `BEGIN ... PRIVATE KEY`, or `api_key = <long token>`.
- `code_hash(files)`: SHA-256 over the sorted (path, file SHA-256) pairs of the shipped `.py` files and `uv.lock`.
- `push()`: `scan_for_keys`, then `tar czhf - <files> | ssh 'mkdir -p /root/hack/logs && tar xzf - -C /root/hack'` (`h` follows the worktree's data links, so the box receives real files), then write `/root/hack/CODE_HASH`. All path guards in `box.py` and `vision_data.py` compare resolved paths, because `data/processed` is a link in the worktree.
- `setup()`: on the box, `pip install -q uv && cd /root/hack && uv sync --frozen`, then assert `torch.cuda.is_available()` and print the GPU name. If the assert fails: `abandon("gpu check")` and rent a replacement. Fallback if `uv sync --frozen` fails on a package the box does not need: `uv export --frozen --no-hashes > req.txt` and `uv pip install -r req.txt` minus that package, recorded as a deviation.
- `memcheck()`: on the box, a short Python command using the landed `src.model.train_vit.Net`: one forward and backward pass with `AdamW` on a batch of 128 at 126 px under autocast, then an inference pass on a batch of 512; print peak GPU memory. Failure: `abandon("memory check")` and report.

Running jobs:
- `run(name, cmd)`: refuse unless `watchdog_alive()`. Execution id `<name>-<UTC yyyymmddHHMMSS>`. In `/root/hack`: `mkdir -p logs; setsid nohup sh -c '<cmd>; echo $? > logs/<id>.rc.tmp; mv logs/<id>.rc.tmp logs/<id>.rc' > logs/<id>.log 2>&1 & echo $! > logs/<id>.pid`. After 3 s the process must be alive or the `.rc` file must exist, else raise. Save `jobs[name] = id` and `last_run_at`.
- `wait(name, poll_s=30, timeout_s)`: poll only `logs/<current id>.rc`; print the log tail; return the exit code.
- `pull(remote_dir, local_dir)`: the box writes a list (path, size, SHA-256) for `remote_dir`; stream it with tar into `<local_dir>/.incoming-<timestamp>/`; check every file against the list; move files into place with `os.replace`; never overwrite an existing chip in `data/chips/`; set `last_verified_pull_at`. A mismatch raises and leaves the incoming directory for inspection.
- `DIGEST_CMD`: a one-line Python command printing `<file name> <sha256 of the array bytes>` for chips in a directory, used on both machines. `compare_digests(a, b)` returns the differing names.
- `parse_chips_log(text) -> {to_cut, uncovered, done, failed, seconds}` from the banner and the last `[chips]` line (zeros when nothing was left to cut). `ok_rate(parsed) = (done - failed) / seconds`. `census(n_on_disk, parsed, total=112443, max_failed_share=0.005)` raises unless `n_on_disk + failed + uncovered == total` and `failed / total <= max_failed_share`.
- `status()`: hours used, `spent_total`, `cap_left`, minutes to the deadline, watchdog state.
- `teardown(force_discard=False)`: refuse unless `last_verified_pull_at > last_run_at` or forced; `echo y | vastai destroy instance <id>`; poll `show instances-v1` up to 3 times, 10 s apart, and raise if the id is still listed; close the billing interval into the history; print the campaign spend.
- CLI: `offers`, `rent`, `selfstop-test`, `push`, `setup`, `memcheck`, `run`, `wait`, `pull`, `stop`, `start`, `status`, `teardown`.

Create `tests/vision/conftest.py` (fixtures shared by all vision tests; registers no command-line options, so it does not interact with a future `tests/conftest.py`), `tests/vision/fixtures/offers_sample.json` (ten real offers from `vastai search offers --raw`, cut down to the fields listed above), and `tests/vision/test_cloud_box.py` with C1 to C22.

Run `$PY -m pytest tests/vision/test_cloud_box.py -q`. (On the box, where there is no shared environment, tests run as `uv run --with pytest python -m pytest ...`.)

## Step 2. Rent the box and start the photo fetch

Renting needs Nathan's go-ahead given directly in this chat; a relayed message does not count.

1. `box.py offers`; pick the first offer. If nothing matches for either GPU name, stop and report (nothing is rented).
2. `rent`. Give Nathan the instance id and the deadline.
3. `selfstop-test`. On `SelfStopUnavailable` the box is already destroyed: stop and ask Nathan whether to go on with only the Mac-side stop.
4. `arm_watchdog` (part of the test's success path), `push`, `setup`, `memcheck`. Record the GPU name, the price and the peak memory.
5. Box gate, cloud tests only: `uv run --with pytest python -m pytest tests/vision/test_cloud_box.py -q` on the box.
6. Identity check (AC3): on the box `uv run python -m src.pipeline.chips --limit 50 --seed 0`; run `DIGEST_CMD` on both machines; `compare_digests` must return nothing. If it does not: `abandon("photo identity")` and report.
7. Speed trials, each limited to 500 photos: `--limit 500 --seed 1 --workers 32`, `--limit 500 --seed 2 --workers 64`, `--limit 500 --seed 3 --workers 128`. Compute `ok_rate` for each. If the best is under 20 a second: `abandon("too slow")` and ask Nathan. Record the three rates.
8. Full fetch in the background with the best worker count: `box.py run fetch "uv run python -m src.pipeline.chips --workers <W>"`. Steps 3 to 6 proceed on the Mac while it runs.

## Step 3. Toolbox and its tests (Mac)

Create `src/model/augment.py` per D3 and D4:

- Constants `N_VIEWS = 8`, `MAX_SHIFT = 4`, `GAIN_RANGE = CONTRAST_RANGE = (0.8, 1.25)`, `ALLOWED_OPS = ("view", "shift", "gain", "contrast")`, `NIR, RED = 3, 0`.
- `check_chip(chip)`: `ValueError` unless `ndarray`, uint8, 3 dimensions, 4 bands first, square.
- `view(chip, k)`: `x = chip[:, :, ::-1] if k >= 4 else chip`; `np.rot90(x, k % 4, axes=(1, 2))`; return `np.array(result, order="C", copy=True)`, so the result owns its data for every k, including 0. `inverse_view(chip, k)`. `all_views(chip) -> (8, 4, H, W)`.
- `gain`, `contrast`: computed in float32, `np.rint`, `np.clip(0, 255)`, back to uint8 (always a new array). `contrast` uses `chip.mean()` over all bands as the grey level.
- `shift(chip, dx, dy)`: `np.pad(..., mode="edge")` by `MAX_SHIFT` on the two spatial axes, crop, copy.
- `ndvi(chip)`, `ndvi_stats(chip)`.
- `Preset(name, view_ids, gain, contrast, shift)` as a frozen dataclass; `NONE`, `FLIPS = (0, 2, 4, 6)`, `FULL`; `PRESETS` dict.
- `sample_rng(seed, epoch, index) = np.random.default_rng([seed, epoch, index])`.
- `random_augment(chip, rng, preset) -> (chip, record)`: order view, shift, gain, contrast; `record` holds the drawn values and `n_ops`, the number of non-identity changes. `NONE` is the one fast path: it returns the input object itself with `n_ops = 0`.

Create `tests/vision/test_augment.py` with A1 to A32. A14 uses the 50 real chips and skips, with a named reason, if `data/chips` is empty.

## Step 4. Data and metrics modules and their tests (Mac)

Create `src/model/vision_data.py`:

- `OUT_ROOT = data/processed/vision`. `atomic_write(path, write_fn)`: refuse a path outside `OUT_ROOT`, write to `path + ".tmp"`, `os.replace`; remove the temporary file on failure.
- `load_table(processed_dir)`: the D2 gate. Messages say "rerun `src.model.train_tabular` after the model-hardening change" when `fold` or `split_block` is missing.
- `HASHED_COLUMNS = ["seg_id", "fold", "split_block", "mid_x", "mid_y", "y_rate", "y_crack", "y_helene_failed", "in_helene_zone"]`; `table_hash(d)` hashes exactly these.
- `chipped(d, chips_dir)`: adds `has_chip` using `chips.chip_path(seg_id).name` joined to `chips_dir`.
- `load_chips(seg_ids, chips_dir, workers=16) -> (uint8 array (N,4,128,128), blank_frac)`: validates shape and dtype per file and raises naming the road; ignores `.npy.tmp`; `blank_frac` is the share of pixels where all four bands are 0.
- `usable_mask(blank_frac, max_blank=0.05)`; `manifest_hash(seg_ids)` of the usable roads.
- `to_model_input(chips_u8) -> float32 (N,3,126,126)`: `[:, :3, 1:127, 1:127] / 255`.
- `ViewDataset(chips, y_rate, y_crack, preset, seed, train)`: `set_epoch(e)`; `__getitem__(i)` returns input, the two labels with NaN replaced by 0, the two-element mask, `i`, and `n_ops`; training applies `random_augment(chip, sample_rng(seed, epoch, i), preset)` to the 4-band chip before `to_model_input`; scoring applies nothing. Loaders are created per epoch (no persistent workers), so `set_epoch` reaches the workers.
- `fold_split(d, k)`: training and held-out row indices from `d.fold`.
- `cross_fold_neighbours(d, radius_m=77)`: count of road pairs closer than the radius whose folds differ (`scipy.spatial.cKDTree`).
- `code_hash()`: same rule as `box.py`. On the box, runners compare it with `/root/hack/CODE_HASH` and refuse on a mismatch. `weights_hash(net)`: SHA-256 over the model's parameter bytes at start.
- `chip_census(d, chips_dir)`: counts with and without a chip.

Create `src/model/vision_metrics.py`: `rate_metrics`, `crack_metrics`, `flood_metrics` (precision at 50, AUC-PR), `naive_rate_mae(y, fold)`, `by_fold(...)`, `paired_diff(a_by_fold, b_by_fold)`, `block_bootstrap_diff(d, pred_a, pred_b, metric, n=1000, seed=0)` resampling `split_block` values with replacement, `seed_spread(results, matched_folds)`, `compare(result_a, result_b)` refusing unequal hashes, `render_report(results) -> str` built only from the results dict, including the counts of skipped folds and missing predictions. Empty or single-class subsets give NaN, not an error.

Create `tests/vision/test_vision_data.py` (D1 to D21) and `tests/vision/test_vision_metrics.py` (M1 to M11). D7 runs on `ncdot_joined.parquet`; D20 skips with the reason "waiting for the model-hardening outputs" until the hardened file exists. The `conftest.py` table fixture builds a hardened-format table (blocks on a 5 km grid, `fold = crc32 % 5`).

## Step 5. Frozen and fine-tune runners and their tests (Mac)

Create `src/model/vision_frozen.py`, writing only under `OUT_ROOT/frozen/` and the by-product files at `OUT_ROOT/`:

- `embed(net, chips, view_ids, batch=512) -> float32 (N, len(view_ids), 384)`: `net.eval()`, `torch.no_grad()`, autocast on CUDA, `net(x, emb=True)` on `to_model_input(view(chip, k))` for each view.
- `probe(emb, d, seed=0) -> (oof DataFrame, skips)`: per fold, on usable roads only: `StandardScaler` then `Ridge(alpha=1.0)` on rows with `y_rate`, `LogisticRegression(C=1.0, max_iter=1000)` on rows with `y_crack`, and the same for `y_helene_failed` on rows with `in_helene_zone == 1`. A fold and target is skipped, its predictions left NaN and the skip recorded, when it has no test rows, no labelled training rows, or one training class. `shuffle_labels=True` permutes each label column among its labelled rows with a fixed seed.
- `vit_frozen_format(emb_2d, seg_ids)`: `PCA(16, random_state=0).fit_transform(emb_2d)` into `seg_id`, `im_emb0..15`.
- `main(processed, chips_dir, out_root=OUT_ROOT, net_factory=train_vit.Net)`: gate; load every valid chip; compute `blank_frac` and `usable`; NDVI statistics for every valid chip into `ndvi_stats.parquet` (with `blank_frac`, `usable`); embed 8 views for every valid chip; write `vit_frozen_statewide.parquet` (view 0) and `vit_frozen_statewide_8view.parquet` (8-view mean), one row per valid chip; save `frozen/emb_view0.npy`, `frozen/emb_mean8.npy`, `frozen/index.parquet`; run the probe for `1view` and `8view` and the shuffled control on `8view`; write `frozen/oof_1view.parquet`, `frozen/oof_8view.parquet`, `frozen/metrics.json` (with every hash, the counts excluded and skipped, and the cross-fold neighbour count) and `frozen/report.md`. All through `atomic_write`.

Create `src/model/vision_finetune.py`, writing only under `OUT_ROOT/finetune/`:

- `masked_loss(out, r, c, m)`: the expression on `train_vit.py` lines 110 to 112.
- `arm_config(arm, seed, epochs=6, batch_size=128)`: a dict that differs between arms only in `preset`.
- `train_fold(d, chips, k, cfg, net_factory=train_vit.Net, shuffle_labels=False)`: raise if the training set has fewer rows than `cfg.batch_size`; seed `torch` and `numpy`; build the net and record `weights_hash`; `AdamW` groups as on lines 101 to 102; `drop_last=True`, 16 workers, shuffle order from `torch.Generator().manual_seed(seed * 1000 + epoch)`; autocast on CUDA; raise `RuntimeError` on a non-finite loss, or on an epoch with zero optimiser steps, before anything is written; after each epoch log held-out metrics; after the last epoch return held-out predictions for view 0 and the 8-view average (`predict_views`: rate outputs averaged, cracking logits averaged), `ops_applied` per epoch, and the time spent in each part (start-up, training, per-epoch scoring, 8-view scoring, writing).
- Job files: each job writes `finetune/<arm>/seed<s>/fold<k>.parquet`, then last `fold<k>.done.json` holding the full settings (arm, preset values, seed, fold, epochs, batch size, learning rates, `shuffle_labels`), the code, table, road-list and weights hashes, and the size and SHA-256 of the parquet file. `job_is_complete(job)` is true only if that record exists, every setting and hash equals the current one, and the file matches its checksum.
- `plan_grid(timing, dph, cap_left, minutes_left, epochs=6, reserve_min=20) -> list of (arm, seed, fold)`: job time is start-up + epochs x (training + per-epoch scoring) + 8-view scoring + writing, from the measured parts, times 1.2; the report is budgeted at 5 minutes. Returns the full schedule (30 jobs plus the control) if it fits in `minutes_left - reserve_min` and in `cap_left`; else the reduced schedule (seed 0 for all 15, seed 1 on fold 0 for the 3 arms, plus the control); raises if the reduced one does not fit either.
- CLI: `--time-only` (one complete job at 1 epoch, fold 0, arm `full`; writes `finetune/timing.json` and no result files); `--jobs <file>` (runs exactly the listed jobs in order, skipping those for which `job_is_complete`); `--shuffled-control` (arm `full`, fold 0, seed 0, labels permuted among training rows; written under `finetune/control/`); `--report` (assembles, for seed 0, per-arm out-of-fold tables with `seg_id`, `fold`, `im_vit_rate`, `im_vit_crack`, `im_vit_rate_8v`, `im_vit_crack_8v`, then `finetune/metrics.json` and `finetune/report.md` with per-fold values, differences against `none`, intervals, and the seed spread on matched runs). `--targets` accepts only `rate,crack`.

Create `tests/vision/test_vision_frozen.py` (E1 to E15) and `tests/vision/test_vision_finetune.py` (F1 to F19). The stand-in `TinyNet` (in `conftest.py`) has attributes `b` and `h` and `forward(x, emb=False)`; `b` is a small convolution followed by pooling to a 4 x 4 grid and a flatten, so it is sensitive to flips and turns. Small-data tests set `batch_size=8` and assert that optimiser steps happened. E11 and F15 skip unless CUDA is available.

## Step 6. Local suite and first commit

1. `$PY -m pytest tests/vision -q -rs` from the worktree root (AC1). Fix until green. List the skips.
2. `git add` by explicit path: the six source files, `scripts/cloud/box.py`, and the files under `tests/vision/`. Check `git diff --cached --name-only` equals that list.
3. `git commit -m "feat: image augmentation toolbox, view averaging, comparison runners, cloud box driver, tests" -- <paths>` on branch `image-augmentation`. No merge, no push.

## Step 7. Fetch contract and first report

1. `box.py wait fetch`. Rerun the fetch once to retry failures: `box.py run fetch "uv run python -m src.pipeline.chips --workers <W>"` (a new execution id), then `wait`.
2. `parse_chips_log` on the rerun's log; count chips on the box; `census(...)` (AC4). If it raises: `stop` the box (the photos stay on its disk), report the numbers and ask.
3. Report to Nathan: photos fetched, failed, not covered, photos per second, time taken, spend so far.

## Step 8. Gate before the model stages

1. `load_table("data/processed")` on the Mac. If it refuses (hardening has not landed): `stop` the box, report, and wait. When the table lands: `start`; if the box cannot restart, it is abandoned and Step 2 is repeated on a replacement. No stand-in is built.
2. `push` (code and the hardened table). On the box: `uv run --with pytest python -m pytest tests/vision -q -rs` must pass with 0 skipped (AC2).

## Step 9. Frozen comparison and second report

1. `box.py run frozen "uv run python -m src.model.vision_frozen"`; `wait`.
2. `pull data/processed/vision data/processed/vision`.
3. Check AC5 and the by-product part of AC9 from the pulled files. Tell the pipeline chat that the `vit_frozen`-format files exist and that their reduction was fitted on all chipped roads.
4. Report to Nathan: the `1view` and `8view` table, the differences with intervals, the shuffled control, and one plain sentence on what it means.

## Step 10. Fine-tune comparison and third report

1. `box.py run timing "uv run python -m src.model.vision_finetune --time-only"`; `wait`; read `timing.json`.
2. On the Mac: `plan_grid(timing, dph, cap_left, minutes_left)` from `box.py status`; write the job list to a file and `push` it. If it raises: `stop` the box and report.
3. `box.py run grid "uv run python -m src.model.vision_finetune --jobs jobs.json && uv run python -m src.model.vision_finetune --shuffled-control && uv run python -m src.model.vision_finetune --report"`; `wait`, polling every few minutes. If the box dies, a replacement repeats Step 2 and reruns the same job list.
4. `pull data/processed/vision data/processed/vision`. Check AC6 and that `frozen/` still holds its own results (AC9).
5. Report to Nathan: the three arms, scored with 1 view and with 8 views, differences against `none` with intervals and the seed spread, the control, and one plain sentence on what it means.

## Step 11. Map chips, teardown, cost

1. On the box, tar the chips of roads whose `pv_COUNTY` is `092-Wake` or `011-Buncombe`; `pull` into `data/chips/` (existing files are not overwritten).
2. `box.py teardown`. Confirm `vastai show instances-v1` lists no instance from this run (AC7). Record hours and campaign spend from the history file; also try `vastai show invoices --raw` for the billed figure.

## Step 12. Docs, checks, second commit

1. Fill the Results section of the run spec: fetch numbers, both tables, controls, spend, deviations. Update the Results section of `docs/features/IMAGE_AUGMENTATION.md`.
2. Staleness grep: `grep -rn "85,521\|stand-in\|50-chip\|no vision model" docs reports` and fix what this change made false in living docs; frozen files (the handoff) get a dated one-line note.
3. AC8: `git diff --stat <base>..HEAD -- src/pipeline src/model/train_vit.py src/model/train_tabular.py src/model/final_ablation.py pyproject.toml uv.lock readme` on branch `image-augmentation` prints nothing. After a heads-up to the pipeline, CCTV pothole and CV flood depth chats (the command rewrites the shared `data/raw/ncdot_joined.parquet`, which those chats read), `$PY -m src.pipeline.pull_ncdot --join-only` prints 112,443 / 68,531 / 68,349.
4. Commit any code or test fixes by explicit path on the branch. Docs stay untracked in the main checkout. No merge, no push.

## Step 13. After the commit

An adversarial critique by a separate agent against the audit rubric, the run spec, this plan and the diff; fix and commit until acceptable. Then `bash ~/.claude/review-audit.sh docs/specs/2026-10-03_image-augmentation.md`; record both verdicts in the run spec; fix findings; report.

## Risks

- **The hardened table has not landed when the photos are ready.** Step 8 stops the box (storage-only billing, about a cent an hour) and waits. If the box cannot restart, the photos are re-fetched on a replacement.
- **`train_vit.py` changes under this work.** Only `Net`, `dev`, `MEAN`, `STD` and `DS` are used. Parity tests D10 and F2 fail loudly if the preprocessing or the loss expression changes.
- **The image host throttles a fast box.** The trials measure three worker counts; below 20 a second the box is destroyed and Nathan is asked.
- **The self-stop test costs a restart.** A few minutes, and a small chance the GPU is taken while stopped; then the box is abandoned and a replacement rented, at most twice.
- **The box dies mid-run.** The fetch and the job list are resumable; a replacement repeats Step 2.
- **The session ends while the box is running.** The on-box watcher stops the box at the deadline without the Mac. Nathan has the instance id.
- **Six epochs may be too few or too many to show an effect.** Held-out scores per epoch are logged for every arm, so the report can say whether the curves were still moving. The headline number stays the last epoch.
- **Result differences smaller than noise.** Reported as "no measurable difference", with the interval and the seed spread.
- **Shared repository.** Own worktree and branch; new files only; commits by explicit path; `git diff --cached --name-only` checked before each commit. The data folders are shared through links: this change writes only under `data/processed/vision/` and, at the end, adds chips to `data/chips/` without overwriting.
- **The branch does not contain the pipeline chat's code.** This change depends on its output file, not its code. Parity tests D10 and F2 run against `train_vit.py` as it is on `main` at `48520d9`; when the branches are merged, they run again against the merged file.

## Response to the Codex plan review (2026-10-03)

Review file: `docs/reports/2026-10-03_image-augmentation-plan-review.md`. Thirteen findings, all accepted.

1. **Critical, two speed trials would fetch everything.** Every trial now passes `--limit 500` (Step 2.7), and the rate counts successful photos only (`ok_rate`, test C14).
2. **Critical, job wrapper.** `run` creates `logs/`, gives each execution a unique id, publishes the exit status by rename, and checks the launch; `wait` reads only the current id (tests C16, C17).
3. **Critical, spending limit across failures.** Spend is cumulative across boxes and stopped time; the deadline is fixed at rental; a working self-stop is required and tested for real; every failure exit either destroys or stops the box (D12; tests C18 to C21).
4. **Critical, no GPU requirement.** The filter requires one RTX 5090 (or 4090) with at least 24 GB, and `memcheck` runs a forward and backward pass at the training batch size before the statewide fetch (test C22).
5. **Critical, 32-sample checks got zero batches.** Batch size is a setting; small tests use 8 and assert steps; small folds and zero-step epochs raise (tests F9, F15, F16).
6. **Critical, reduced schedule ambiguous.** `plan_grid` returns explicit (arm, seed, fold) jobs; the reduced schedule keeps seed 0 everywhere; the runner executes the listed jobs; the seed spread uses matched runs (tests F17, F18).
7. **Critical, timing gate incomplete.** `--time-only` runs one complete job and times each part; `plan_grid` takes the minutes left and reserves 20 for copying results and teardown (test F13).
8. **Critical, reports could overwrite each other.** Frozen results live in `frozen/`, fine-tune results in `finetune/` (test E15, AC9).
9. **Critical, resume validation.** A completion record written last holds settings, hashes (including the weights) and file checksums; resume requires it to validate (test F19).
10. **Critical, table fingerprint.** `HASHED_COLUMNS` now includes the Helene columns, the block and the coordinates (test D21).
11. **Critical, NDVI coverage and the `vit_frozen` copy.** NDVI and embeddings cover every valid chip before exclusions; the `vit_frozen`-format files are written by this change's own atomic writer with the landed recipe; `train_vit --frozen` is no longer run (test E14).
12. **Suggestion, array ownership.** Transform functions always return a new owned array; `NONE` is the one documented fast path that returns its input (tests A8, A29).
13. **Suggestion, sparse subsets.** The probe skips, leaves missing and counts folds with no test rows, no labelled training rows or one class (D15a; tests E12, E13).
