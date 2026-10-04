# Image augmentation and view averaging

Status: code and tests written (2026-10-03, branch `image-augmentation`); the comparisons have not been run yet. Living document; the run spec for the first change is `docs/specs/2026-10-03_image-augmentation.md`.

## What it is

Each road has one aerial photo ("chip"): 128 x 128 pixels, four bands (red, green, blue, near-infrared), saved by `src/pipeline/chips.py`. This feature gives the image model varied copies of that photo during training, and can average the model's answer over the 8 flipped and turned versions when scoring.

## What is allowed

| Change | Rule |
|---|---|
| Flips and quarter turns | The 8 symmetries of a square. An overhead photo has no "up". |
| Brightness | One multiplier for all four bands, 0.8 to 1.15. Above that the near-infrared band washes out (20% of its pixels at 1.25, measured on real chips). The "full" setting draws from 0.9 to 1.1. |
| Contrast | One stretch for all four bands around a shared grey level, 0.8 to 1.25. |
| Shift | Whole pixels, at most 4, all bands together, edge repeated. |

Not allowed: hue or saturation changes, MixUp, CutMix, random erasing, RandAugment. The road is about 12 pixels wide, one target is a continuous number, and colour tricks have no meaning for the near-infrared band.

## Rules that keep the test honest

- Copies are made on the fly from the road's own chip. Nothing augmented is saved to disk, so a copy can never sit in a different fold from its road.
- Folds and labels come from `data/processed/segments_targets.parquet`. This feature does not compute either.
- Every arm of a comparison is scored on the same roads, with the same code, and says so in its result file.
- The vegetation index (NDVI) is computed from the original chip, never from a brightened one.
- Random changes are keyed by (seed, epoch, road index), so a run repeats exactly whatever the number of loader workers.

## Where things are

| Piece | File |
|---|---|
| The changes themselves, NDVI | `src/model/augment.py` |
| Loading chips, the label and fold gate, model input | `src/model/vision_data.py` |
| Scores and the comparison between arms | `src/model/vision_metrics.py` |
| Frozen-model comparison (1 view vs 8) | `src/model/vision_frozen.py` |
| Fine-tune comparison (none, flips, full) | `src/model/vision_finetune.py` |
| Tests | `tests/vision/` |
| Outputs | `data/processed/vision/` |

Run the tests from the repo (or worktree) root with the project environment: `python -m pytest tests/vision -q -rs`. Until pytest is a project dependency on your branch, `uv run --with pytest python -m pytest tests/vision -q -rs` does the same.

## Cloud box

The venue link fetches about 3 chips a second, so the statewide fetch and the model runs happen on one rented vast.ai GPU box, driven from the Mac by `scripts/cloud/box.py`.

- The box is picked by a filter (one RTX 5090 or 4090, free bandwidth, enough cores, disk and network, a GPU driver new enough for the locked PyTorch build).
- There is a spending cap and an hour limit; renting is refused if they would be exceeded. The spend record lives in `~/.config/hack-ncsu-cloud`, outside the repository, so the cap holds from any checkout.
- A watcher on the box, installed by the box's own start-up script, stops the box at the deadline without the Mac.
- What a failed check does depends on what the box holds. Before it holds anything (it never boots, cannot be reached, cannot stop itself, has a GPU that does not work or is too small, fetches different photos, or fetches too slowly), the driver destroys it. A failed install or a check that could not run leaves it up. Once it holds photos or results, a failure stops it (storage billing only) and never destroys it.
- The driver only ever stops, starts or destroys the one box it created, which it labels `image-augmentation`.
- The Mac reaches the box over SSH on a random high-numbered port. Some networks (the hackathon venue's, for one) block those ports; the driver checks first and refuses to rent on such a network. Use a hotspot or VPN.
- Code and inputs are sent as an explicit file list, and the list is scanned for anything that looks like a credential before it is sent.
- Teardown refuses until every result file on the box is on the Mac with the same size and checksum, and no job is still running. Chips are not kept after teardown; they can be fetched again.
- The fine-tune report reads a job's results only if its completion record matches the current code, labels, roads, weights and settings, and its file is intact.

## Google Colab instead of a box

When the network blocks the box (or for a free run), the same comparisons run in Colab on a sample of roads.

1. `python scripts/colab/build_package.py` writes `vision_colab.ipynb` and `vision_colab.zip` into `data/processed/vision/colab/`.
2. In Colab: upload the notebook, set the runtime to T4 GPU, Run all, and give it the zip when it asks. It first does a complete small run on the Mac's 50 photos (checked pixel for pixel), so a problem with the machine shows in minutes. Then it fetches the sample, runs the tests, and runs both comparisons. The fine-tune schedule is cut to fit 80 minutes, down to one seed if need be.
3. It offers a download after every stage (`frozen_results.zip`, `results_after_<arm>.zip`) and, at the end or on an error, `vision_results.zip`, which holds everything finished so far.
4. `python scripts/colab/import_results.py ~/Downloads/vision_results.zip` puts the results under `data/processed/vision/` and prints the two reports.

The fine-tune loop uses a gradient scaler on a CUDA GPU, and each job records how far the backbone weights moved; the report refuses if they did not move.

Colab's free machine holds about 40,000 photos, so this is a random sample of the state, not all of it.

## Results

None. The comparison was built and tested but never run: it was dropped for the hackathon on 2026-10-03, so there is no evidence either way on whether augmentation helps. The fine-tune loop has not been exercised on a GPU. To run it, use the Colab steps above or the cloud box; the run spec (`docs/specs/2026-10-03_image-augmentation.md`, "Closed") lists what is still open.
