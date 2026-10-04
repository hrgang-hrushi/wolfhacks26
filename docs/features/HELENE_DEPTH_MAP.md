# Helene depth map

Status: built and tested (2026-10-03, branch `helene-depth`, not merged). Living document; the run spec for the first change is `docs/specs/2026-10-03_helene-depth-map.md`.

## What it is

A Hurricane Helene flood depth, in metres, for road segments near the surveyed high-water marks in western North Carolina. Depth = the water level drawn between surveyed marks along a stream, minus the 10 m ground under the road.

It is the second half of the flood-depth track. The first half reads water depth from camera photos (`src/pipeline/sunnyday.py`, `src/model/flood_camera.py`) and cannot give Helene depths, because no camera caught the peak.

## How it works, following one road

1. Surveyors left 2,193 marks where the water reached, each with a water height above sea level. Marks on one stream are numbered going upstream.
2. The marks on a stream are joined in order into a line. Between two marks the water level is a straight line from one to the other.
3. A road gets a point every 30 m. Each point looks up the water level at the nearest spot on a stream line and subtracts the ground height from the USGS 10 m terrain.
4. Points on or under a bridge are set aside: the terrain has bridges removed, so they would read as river-bed depth.
5. The segment's headline depth is the deepest water held by two neighbouring points.

## Rules that keep it honest

- A road with no mark within 1 km along its stream, or more than 300 m to the side of a stream line, is "not assessed" and blank. Blank never means dry.
- No level is given where the drawn water level strays more than 2 m from the nearer mark's own level. Between marks that differ by many metres (a dam, a fall, a steep reach) a straight line is a guess; before this rule such spots read up to 36 m deep.
- A stream line answers only through its own nearest spot to the road point. If that spot may not give a level, the line is silent; the point is never slid along the line to a mark.
- A reading deeper than 15 m is left out and counted; more than 0.5% of them stops the build.
- Marks graded Poor or Very Poor by the surveyors do not draw the water line.
- The error number comes from hiding marks and guessing them back with the same code, and from the 280 marks where the depth was also taped.
- The build refuses if the 10 m ground does not beat the 30 m ground on the taped marks.
- Every output column starts with `y_` or `n_`, so the model's input check rejects it. The depth is an outcome of the storm, not a clue.
- The depth script refuses to write any file whose name does not start with `flood_helene_depth`; the ground script writes only tiles and their manifest into `data/processed/dem10_helene/`.

## Where things are

| Piece | File |
|---|---|
| 10 m ground tiles: fetch, save, read | `src/pipeline/helene_dem10.py` |
| Marks, stream lines, road points, bridges, depth, error tests, output | `src/pipeline/helene_depth.py` |
| Tests | `tests/helene_depth/` |
| Marks (input, git-ignored) | `data/raw/flood_usace_hwm_helene.geojson` |
| Bridge list (input, teammate's pull) | `data/raw/helene_structures.parquet` |
| Ground tiles (git-ignored) | `data/processed/dem10_helene/` |
| Depth per segment | `data/processed/flood_helene_depth.parquet` |
| Depth per road point (ground, water level, depth, and why a point was left out) | `data/processed/flood_helene_depth_points.parquet` |
| Error numbers | `data/processed/flood_helene_depth_validation.json` |
| Notes: settings, counts, fingerprints | `data/processed/flood_helene_depth.meta.json` |

## Running it

From the repo (or worktree) root:

```
PY=/Users/nathanstough/Desktop/Hack-NCSU/.venv/bin/python
$PY -m src.pipeline.helene_dem10     # about 90 tiles, about 10 minutes, under 0.5 GB
$PY -m src.pipeline.helene_depth     # error tests, then the depth files
```

The marks file can be pulled again without a login from `https://services.arcgis.com/NuWFvHYDMVmmxMeM/arcgis/rest/services/USACE_HWMs_Helene/FeatureServer/0/query` (page with `resultOffset`, `outSR=4326`, `f=geojson`).

## Columns of the per-segment file

| Column | Meaning |
|---|---|
| `seg_id` | Same id as `segments.parquet`, same row order |
| `y_helene_depth_assessed` | True when at least two neighbouring road points were usable (they had a water level and ground, and were not set aside) |
| `y_helene_depth_max_m` | Deepest water held by two neighbouring points; 0.0 when dry; blank when not assessed |
| `y_helene_depth_point_max_m` | Deepest single point |
| `y_helene_depth_wet_share` | Share of the assessed points under water |
| `y_helene_depth_band` | `dry`, `under 0.3 m`, `0.3 to 1 m`, `1 to 2 m`, `over 2 m` |
| `y_helene_depth_conf` | `high` when both points that set the depth are within 250 m of a mark (by the distance below) and neither lies past the end of a stream line; otherwise `low` |
| `y_helene_depth_mark_dist_m` | Distance from the road to the nearest mark: along the stream line to the spot beside the road, then across to the road. A road 290 m to the side of a mark is 290 m from it, not 0 |
| `y_helene_depth_typical_miss_m` | Typical miss at that distance, from the hidden-mark test |
| `y_helene_depth_stream` | The stream whose marks were used |
| `n_helene_depth_marks` | Marks whose levels the estimate was drawn from (a road level with one mark rests on that mark alone) |
| `n_helene_depth_points` | Road points used |
| `n_helene_depth_set_aside` | Road points set aside as bridges |

## What was measured before building (2026-10-03)

| | 30 m ground | 10 m ground |
|---|---|---|
| Typical miss against 280 taped depths | 0.61 m | 0.20 m |
| Worst tenth miss by more than | 2.63 m | 1.24 m |

Guessing a hidden mark from its neighbours: 0.22 m with a mark within 100 m, 0.59 m at 250 to 500 m, over 0.9 m beyond 1 km. Both together: about 0.5 m.

## Results (first build, 2026-10-03)

| Check | Result |
|---|---|
| 10 m against 30 m ground, 280 taped depths | 0.24 m against 0.61 m |
| Hidden marks, typical miss | 0.27 m (1,199 marks; range 0.23 to 0.33 m) |
| ... with a mark within 100 m | 0.20 m (range 0.17 to 0.25) |
| ... 100 to 250 m | 0.31 m (0.26 to 0.42) |
| ... 250 to 500 m | 0.38 m (0.32 to 0.50) |
| ... 500 m to 1 km | 0.38 m (0.29 to 0.47) |
| End to end against the tape | 0.37 m (190 marks; one in ten off by more than 1.4 m) |

1,602 segments assessed out of 112,443; 648 had water (75 under 0.3 m, 136 from 0.3 to 1 m, 175 from 1 to 2 m, 262 over 2 m). Confidence is high for 1,118 of them and low for 484. Biltmore Village reads 4.2 m. Of the segments with at least 0.3 m of water, 37.5% are marked failed in Helene, against 11.5% of the dry ones.

The 0.24 m figure is with the interpolation the build uses. Read the way the USGS point service reads (the cell that holds the point), the same tiles give 0.20 m.

## Limits

- 12 counties, about 100 streams. Chimney Rock and Old Fort have no marks.
- The ground was surveyed before the storm.
- Typical miss 0.3 to 0.4 m; one reading in ten is off by more than 1.4 m; the estimate leans about 0.2 m deep.
- 688 of the 1,887 line-drawing marks could not be guessed from their neighbours, so the error number speaks for the places where marks are close and the river is not steep, which is also where depths are given.
- Bridges are handled by rule (bridge list, notch, steep bank), not by a measured deck height.
- A low ridge between a road and a stream line less than 300 m away is not detected.
