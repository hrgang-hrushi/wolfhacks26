# Road model augmentation and architectures

Research run on Oct 3, 2026 for the Unwatched Roads project.

**How this was produced.** A background research run searched five angles, read 22 sources and pulled out 95 specific claims. The 25 most important claims were each attacked by three independent checkers. 17 survived, 8 were thrown out. Opus planned the search and wrote the synthesis; Sonnet did the searching, reading and checking.

**How to read it.** Every statement is marked one of three ways:

- **Checked**: survived the three-checker test.
- **Found, not checked**: read from a source, but it was outside the 25 claims that got checked.
- **My reasoning**: not from the research at all.

The research was strong on how to test the model and on which image and table models exist. It was weak on augmentation and on prior pavement-from-imagery results: nothing on those two topics made it through checking.

---

## Bottom line

1. **Keep the shape of the current plan.** A tree model on the table, with the image model's numbers added as extra columns, is the cheapest robust design. Networks that train on images and the table together have no evidence behind them for aerial data. *(Checked, low confidence)*
2. **Try image models in this order.**
   1. DINOv3 ViT-S/16 in place of DINOv2 ViT-S/14. Same size class, light, a drop-in swap. *(Checked)*
   2. DOFA, the one model here that takes all four bands, near-infrared included, with no surgery. *(Checked, medium)*
   3. DINOv3's satellite model as a frozen feature reader. It was trained on 0.6 m imagery, the same ground resolution as our photos, but it is large and takes colour only. *(Checked)*
   4. A plain ImageNet CNN as a sanity baseline. Specialised remote-sensing models do not consistently beat simple supervised baselines. *(Checked, medium)*
3. **Stay with LightGBM for the table.** TabPFN-2.5 is a credible extra model to average in, with caveats on size and licence. *(Checked, medium)*
4. **Augmentation: flips and quarter turns, mild brightness changes applied to all bands together, no hue shifts.** The research did not check any of this; it is standard practice plus my reasoning.
5. **Testing by map squares is strongly supported.** Random splits inflate scores. Every copy of a road's photo must stay in that road's group. *(Checked, high)*
6. **Expect the photos to help a little, not a lot.** Published image-only pavement results look excellent on random splits and fall sharply when whole roads are held out. *(Found, not checked)*

---

## Image models

| Option | For | Against | Effort (my estimate) | Evidence |
|---|---|---|---|---|
| **DINOv2 ViT-S/14, frozen** (current plan) | Already planned; small; no training | Colour only; patch size 14 means resizing chips | 0 | Not examined |
| **DINOv3 ViT-S/16** | 21M parameters; patch 16, so a 128 px chip is a clean 8 × 8 grid; runs on a T4 or a Mac | Colour only; custom licence to read | About 1 hour | Checked, high |
| **DINOv3 satellite model (SAT-493M, ViT-L/16)** | Trained on 493M Maxar images at 0.6 m, the same ground resolution as NAIP | 300M parameters, about 14× ViT-S; colour only; frozen use only, fine-tuning is unrealistic in the time left; its strong benchmark results are self-reported | 1 to 2 hours | Checked, high for the facts; medium for the performance claim |
| **DOFA** | Takes any set of bands by being told each band's wavelength, so red, green, blue and near-infrared go straight in; weights are public | The checker relied on memory for some details; fine-tuning is advisable because it was trained at other scales | 2 to 3 hours | Checked, medium |
| **ImageNet ResNet or ConvNeXt with a 4-band first layer** | Simple and fast; the PANGAEA benchmark found remote-sensing models do not consistently beat supervised baselines | Needs the first layer adapted for the fourth band | 1 to 2 hours | Checked, medium, for the benchmark; the adaptation recipe is my reasoning |
| **SatMAE, Scale-MAE, Prithvi, Clay, SatlasPretrain** | None established | The research found no checked evidence on any of them for this kind of image | Unknown | Nothing survived checking |
| **Fine-tuned ViT-S with three outputs** (current plan) | Learns from our own labels | Needs a GPU and the full photo set | Several hours | Not examined |

Two details worth knowing:

- **The near-infrared band.** Every DINO model takes colour only. The cheap way to use the fourth band is to compute a vegetation index (NDVI) and hand it to the tree model. TorchGeo has a ready-made transform for this. *(Checked, high.)* For our band order the call would be `AppendNDVI(index_nir=3, index_red=0)`; that specific call is inferred, not tested.
- **Chip size.** At 128 px a patch-16 model sees an 8 × 8 grid. Enlarging the chip to 224 px gives 14 × 14, which may help with a road only 12 px wide, at about three times the compute. *(My reasoning.)*

A suggestion that follows from this: compare two or three frozen models on a subset of photos (for example Buncombe and Wake) before downloading the whole state. *(My reasoning.)*

---

## Table models

| Option | For | Against | Evidence |
|---|---|---|---|
| **LightGBM** (current plan) | On the TabArena benchmark, tree models are the strongest and cheapest single models at modest time budgets | None found | Checked, medium |
| **CatBoost** | Handles categories such as surface type natively | No checked evidence that it beats LightGBM here | My reasoning |
| **TabPFN-2.5** | Designed for up to 50,000 rows and evaluated up to 100,000; its authors report an 87% win rate over default XGBoost on classification and 85% on regression | Those figures are vendor-reported and against untuned XGBoost; memory and speed on a T4 with about 68,000 training rows were not verified, so it may need subsampling; non-commercial licence *(found, not checked)* | Checked, medium |
| **TabM, RealMLP** | Competitive with tree models once tuned and ensembled | Need a larger time budget | Checked, medium |
| **AutoGluon, FT-Transformer, XGBoost** | | No checked evidence either way | Nothing survived checking |

---

## Combining images with the table, and using the road network

| Option | For | Against | Evidence |
|---|---|---|---|
| **Stacking** (current plan): the image model's held-out scores become columns for the tree model | Cheap, easy to debug | None found | Checked, low |
| **Joint networks** (TIME, DAFT, GAAL) | One paper reports gains of roughly 2 to 4 points over other fusion methods | Tested only on everyday photos, paintings and medical images; no comparison against stacking; nothing on aerial data | Checked, low, for TIME; found, not checked, for GAAL |
| **Models over the road network** (graph or sequence models) | A Texas study on over 110,000 road sections reported gains of 0 to 20% in R² from a graph model | Its baselines were weak (no boosted trees) and it used a random split; other studies are tiny (750 segments) or report weak fits (R² about 0.38) | Found, not checked |

The cheap version of the road-network idea is neighbour features, such as the average of nearby roads, computed from training groups only. *(My reasoning.)*

---

## Augmentation

The research produced no checked evidence on how well any single augmentation works for four-band aerial chips. This table is standard practice and my reasoning, except where marked.

| Technique | Verdict | Why |
|---|---|---|
| Flips and quarter turns | Use | An overhead photo has no "up"; the road stays centred. A practitioner guide recommends exactly these for aerial data *(found, not checked)* |
| Mild brightness and contrast changes | Use, applied to all bands together | Changing bands separately would corrupt the red to near-infrared relationship that NDVI depends on |
| Hue and saturation shifts | Avoid | They are a colour-image idea with no meaning for a near-infrared band |
| NDVI as an extra input | Use | TorchGeo provides it *(checked, high)* |
| Averaging predictions over the 8 flipped and turned versions | Use | Free at training time; no evidence found on the size of the gain |
| MixUp, CutMix, RandomErasing, RandAugment | Skip for now | No evidence found; blending or erasing is risky when the object is 12 px wide and one target is a continuous number |
| Several photos along each road | Only with a faster download | Real extra views, so they add information, but they multiply the download |

One tooling warning: the claim that TorchGeo lets you chain its index transforms and Kornia augmentations in a single call was thrown out (0 of 3 checkers) for the version examined. Expect to write some glue code.

---

## Testing

- **Random splits inflate results.** One study found random holdouts overstated a CNN's performance by up to 28% compared with spatial blocks, and the gap grew with less training data. Another found random 10-fold testing understated error by 5 to 54%. *(Checked, high.)*
- **Block size matters more than anything else in the setup.** It should be set from how far the leftover errors stay correlated. That finding comes from marine data with ranges of 200 to 300 km, so applying it to 5 km road blocks is a stretch. *(Checked, medium.)*
- **Keep copies together.** All chips, augmented versions and flipped views of a road must sit in that road's group. Overlapping chips of neighbouring roads across a block edge are a leak. *(My reasoning, extending the checked findings.)*
- **Helene.** Flood damage probably clusters by river basin, so holding out whole basins may be the fairer test. The label is rare, so some groups may have few or no positives. *(My reasoning, from the synthesis.)*

---

## What earlier pavement-from-imagery studies reported

None of this was checked. It is what the sources say, as read by the research run.

| Study | Imagery | Result | Catch |
|---|---|---|---|
| Kenya road roughness, 2018 (arXiv 1812.01699) | 50 cm satellite, ImageNet CNNs | 88% on good-versus-bad; 73% on five classes | With whole roads held out, 88% fell to 79% and 73% fell to 52%. Mismatched image and label dates cut usable data from about 7,000 km to about 1,150 km |
| Houston, 2025 (arXiv 2508.01206) | 50 cm aerial, about 3,000 images, five classes | 0.93 accuracy from four small CNNs voting | Random 80/20 split of already-augmented images, so likely inflated. Small older CNNs beat larger newer ones. The authors say cracks are not visible at 50 cm and recommend adding table data |
| PCIer, 2023 (Geographies, MDPI) | Google Earth, about 100 images per class, four classes | 0.97 accuracy | Tiny dataset, random split |

Two things in these match our situation: cracks are invisible at this resolution, and our photos (2022) are older than our scores (2023 to 2025).

---

## What the research could not answer

- How accurate published work is at predicting pavement condition from sub-metre aerial imagery, as a realistic ceiling for our image model.
- Whether DINOv3 satellite features or DOFA features beat DINOv2 ViT-S on chips like ours.
- Whether 5 km is the right block size for each of our three answers.
- Whether TabPFN-2.5 fits in T4 or Mac memory with about 68,000 training rows.

## Claims that were thrown out

1. TorchGeo chains index transforms and Kornia augmentations in one call (0 of 3).
2. On 1.5 to 2 m imagery, resolution-matched remote-sensing models beat the UNet baseline (0 of 3).
3. NAIP was absent from DOFA's training data (0 of 3).
4. TabPFN-2.5 has a hard 50,000-row limit that our data exceeds (0 of 3).
5. TabPFN v2 is not a top choice at about 85,000 rows (0 of 3).
6. TabPFN-2.5 is impractical on a T4 or a Mac (1 of 3).
7. Ensembling across model families is what gives the best table results (1 of 3).
8. TabPFN v2 is limited to 10,000 samples (1 of 3).

## Limits of this report

- 70 of the 95 extracted claims were never checked, because the run checks only the top 25.
- The testing evidence comes from vegetation, marine and hyperspectral studies, not roads.
- The DINOv3 and TabPFN-2.5 performance figures are reported by their own authors.
- Several checkers relied on abstracts or memory instead of full papers.
- Effort estimates are mine and untested.

## Sources

Checked findings draw on:

- Kattenborn et al. 2022, spatial validation for CNNs: https://rsc4earth.de/publication/kattenborn-spatially-2022/
- Stock 2025, block size in spatial cross-validation: https://www.frontiersin.org/journals/remote-sensing/articles/10.3389/frsen.2025.1531097/full
- Nalepa et al. 2019, leakage in hyperspectral validation: https://arxiv.org/pdf/1811.03707
- TorchGeo transforms tutorial: https://torchgeo.readthedocs.io/en/v0.4.0/tutorials/transforms.html
- DINOv3 paper: https://arxiv.org/pdf/2508.10104
- DINOv3 satellite model card: https://huggingface.co/facebook/dinov3-vitl16-pretrain-sat493m
- PANGAEA benchmark: https://arxiv.org/html/2412.04204v2
- DOFA: https://arxiv.org/abs/2403.15356
- TabPFN-2.5 paper: https://arxiv.org/pdf/2511.08667
- TabPFN-2.5 model report: https://priorlabs.ai/technical-reports/tabpfn-2-5-model-report
- TabArena: https://alphaxiv.org/abs/2506.16791
- TIME fusion: https://arxiv.org/pdf/2506.00813

Read but not checked:

- Aerial augmentation guide (blog): https://blog.roboflow.com/image-augmentations-for-aerial-datasets/
- Kenya road quality from satellite imagery: https://ar5iv.labs.arxiv.org/html/1812.01699
- Houston pavement condition from aerial imagery: https://arxiv.org/pdf/2508.01206
- PCIer: https://profiles.ncat.edu/en/publications/pcier-pavement-condition-evaluation-using-aerial-imagery-and-deep-7/
- Texas road-network graph model: https://arxiv.org/html/2508.02749v1
- GAAL image and table fusion: https://arxiv.org/html/2604.01579v1
- Graph model for pavement forecasting: https://arxiv.org/pdf/2511.02957
- ST-ResGAT pavement forecasting: https://arxiv.org/pdf/2603.14107
- Multimodal fusion for remote sensing (Hong et al. 2020): https://arxiv.org/pdf/2008.05457
