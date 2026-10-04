# Unwatched Roads — Hackathon Plan (statewide NC)

**One line:** Predict pavement failure and Helene-class flood failure for every road segment in North Carolina, including the city streets nobody surveys, from terrain, traffic, pavement history, weather, and 4-band aerial imagery.

**Pitch hook:** NCDOT surveys state roads. Cities survey nothing publicly. Cameras cover ~1% of miles. Potholes and road flooding share a root cause (water that doesn't drain). One shared drainage backbone, two heads, trained on 112k labelled state segments, applied to every street.

**Scope decisions (locked):**
- Geography: all of NC for pavement (112,443 NCDOT segments). Helene counties (western NC) for flood labels. Demo zoom: Asheville and Raleigh.
- Pavement target: deterioration rate from the NCDOT snapshot (cross-sectional, see §2). Say so in the pitch.
- Flood target: segment failed during Helene (damage sites, landslides, high-water marks within 30 m). If no label source is downloadable by hour 3, the flood head is an unvalidated susceptibility rank, labelled as such.
- Cameras: OUT. No detection code.
- Imagery: NAIP 2022 via Planetary Computer, ONE 128 px chip per segment, windowed reads, background job from hour 1. Never download mosaics.
- DEM: 3DEP 30 m statewide, 10 m for Helene counties only.
- Model ladder (in order, each a row in the ablation): LightGBM tabular → frozen DINOv2 embedding → fine-tuned ViT-S score (stacked) → route transformer (stretch).
- Routing: stretch only.

**End goals (added 2026-10-03):** what the predictions are meant to power. Goals 1 and 2 are the team's original aims; 3 to 6 were added on 2026-10-03.
1. **Repair dashboard for officials.** A ranked work list for road agencies (fix now, fix within a year, plan within five) with alerts when a road crosses a threshold. Status (evening of 2026-10-03): predictions exist for all 112,443 state segments; agency (`/gov`) and phone (`/m`) dashboards are merged into main under `web/`, not deployed; a database-backed service is being built on branch `tiger-dashboard`.
2. **Safer-route data for map companies.** A per-road risk file navigation apps can read, so drivers are routed around rough pavement and flood-prone roads. Status: `handoff/predictions_geo.parquet` exists; a downloadable risk file is being built on branch `tiger-dashboard`; no routing yet.
3. **Budget planner.** Rank repairs by benefit per dollar and show what waiting costs, using NCDOT's `PMS_TREATMENT_NAME` and `TREATMENT_COST`. Status: not built.
4. **Storm readiness.** Before a forecast storm, list the roads most likely to wash out so crews can stage equipment and plan detours. Status: flood model tested on Helene (18 of the top 50 damaged, about 2 by chance).
5. **Live confirmation from cameras.** Use public traffic cameras to confirm water on the road or visible damage. Status: merged into main. One round of NCDOT stills is matched to segments, and the flood reader is tested (camera never seen: precision 0.85, recall 0.91, depth error 9.7 cm on flooded frames; 9 false alarms in 1,191 dry stills). Not running live. This reverses "Cameras: OUT" above for these two side tracks.
6. **Scores for streets nobody inspects.** A first estimate for city streets. Status: not built; only state roads are scored.

Done since: resident pothole reports (Charlotte, Raleigh) as a check on the predictions (Charlotte lift about 3; Raleigh too few reports), and crash counts plus estimated traffic per segment (`handoff/traffic_crash.parquet`; no gain for the model). Done and merged: a Helene depth map (1,602 segments assessed, 648 with water; typical miss 0.37 m against taped depths). Dropped: the image-augmentation comparison was built but not run (Nathan, 2026-10-03). Still planned: ranking by who relies on the road (trucks, school routes, ambulance routes).
Suggested for the demo, not yet decided: a ranked list with a map for goal 1 and a downloadable risk file for goal 2.

---

## 1. Team split

| Who | Owns | Hours 0–4 | Hours 4–16 | Hours 16–24 |
|---|---|---|---|---|
| Nathan (CV/ML) | Modelling, imagery, eval | Repo, NCDOT pull, DEM pipeline, start NAIP reads | Tabular baseline (h6), frozen embeddings (h10), ViT fine-tune on GPU (h10–16), stack, ablation, SHAP | Freeze, export predictions + metrics JSON |
| CS dev A | Data pipeline | **Helene labels (critical path, report by h2)**, centerlines, AADT, weather | Feature table, validation, spatial lags, no-pv variant inputs | PMTiles/GeoJSON export, README |
| CS dev B | Map + demo | MapLibre + deck.gl skeleton on mock data (h2) | Layers, click panel, state-vs-predicted toggle, chip preview | Pitch, 2-min script, optional Valhalla routing |

Contract: `data/processed/segments.parquet`, one row per segment, columns prefixed by group. `data/raw` is gitignored.

---

## 2. Data sources

### Pavement labels — NCDOT PCS (VERIFIED 2026-10-03)
- Network Master: `https://gis11.services.ncdot.gov/arcgis/rest/services/NCDOT_PMS_Network_Master_PCS/MapServer/0/query`
- Asphalt detail: `https://gis11.services.ncdot.gov/arcgis/rest/services/NCDOT_Asphalt_PCS/MapServer/0/query`
- Statewide count: 112,443. Wake: 6,233 (6,209 surveyed 2025). **Snapshot, no per-segment history.**
- County field format: `COUNTY='092-Wake'` (Network Master). Buncombe is probably `011-Buncombe`; verify with one query. Asphalt layer uses `SAP_COUNTY`; check its format.
- Pull: `where=OBJECTID>0`, `f=geojson`, `outSR=4326`, `resultRecordCount=2000`, paginate with `resultOffset`. ~57 calls for the whole state.
- Network Master fields: `ROUTEID, BEG_MP, END_MP, COUNTY, DIVISION, RTG_NBR (0-100), PCS_SRVY_YR, YEAR_LAST_REHAB, LAST_REHAB_TYPE, PVMNT_AGE, SURFACE, NUMBER_OF_LANES, SEC_WIDTH, CURB, SHOULDER_TYPE_ID, SHOULDER_WIDTH, AVERAGE_IRI, AVERAGE_RUT_DEPTH, NC_SYSTEM_CODE, SUBDIVISION_RURAL_CODE, PMS_TREATMENT_NAME, TREATMENT_COST, LENGTH, LANE_MILES`
- Asphalt fields: `AADT, RSRFC_YR_NBR, SRVY_YR, PAVEMENT_TYPE, ALGTR_NONE_PCT, ALGTR_LOW_PCT, ALGTR_MDRT_PCT, ALGTR_HGH_PCT, TRNSVRS_CD, RUT_CD, RVL_CD, OXDTN_CD, BLD_CD, PTCH_CD, RIDE_CD, RSRF_THCKNS_NBR, SAP_COUNTY, NC_TIER`
- Join: `ROUTEID + BEG_MP + END_MP` with milepost tolerance (±0.01 mi). Report join rate; expect < 100%.

**Pavement targets:**
```
y_deter_rate  = (100 - RTG_NBR) / max(PVMNT_AGE, 1)        # rating points lost per year; drop PVMNT_AGE < 1
years_to_poor = max(RTG_NBR - 60, 0) / max(y_deter_rate, 0.5)
y_cracking_hi = (ALGTR_MDRT_PCT + ALGTR_HGH_PCT) > 10
```

### Flood labels — Helene (CRITICAL PATH, Dev A, hour 0)
Try in order, report yes/no + row count by hour 2:
1. NCDOT Helene recovery / damage-site feature services: search `ncdot.maps.arcgis.com` and `connect.ncdot.gov` for "Helene". NCDOT reported thousands of damage sites; find the layer.
2. NC Geological Survey Helene landslide inventory (2,000+ points, public).
3. USACE Helene high-water marks (2,587 points): https://www.usace.army.mil/Media/Fact-Sheets/Fact-Sheets-View/Article/4272569/hurricane-helene-flood-data-collection/
4. Post-Helene NC OneMap ortho for pre/post differencing (fallback label generator, CV-heavy, only if 1–3 fail).
- The live TIMS incident feed (`NCDOT_TIMSIncidents`) is current-only. Dead end for a 2024 event.
- `y_flood_failed = any positive within 30 m of segment`. Negatives: everything else in the Helene counties, plus a sample of Piedmont/coast segments.

### Road network
- Statewide display network: `osmnx.graph_from_place` per county, or NCDOT state road layer plus city centerlines for Asheville and Raleigh (Raleigh: https://data.raleighnc.gov/datasets/city-of-raleigh-maintained-streets-2).
- `seg_id`: `ncdot:{ROUTEID}:{BEG_MP}` for state roads, `city:{OBJECTID}` for city streets.

### Terrain — USGS 3DEP (shared backbone)
- `py3dep.get_dem(bbox, resolution=30)` statewide; `resolution=10` for the Helene counties.
- `pysheds` or `richdem`: slope, flow accumulation, HAND (cheap version: elevation minus nearest flowacc>threshold cell), stream power = slope × flowacc, distance to channel.
- Per segment (20 m buffer, 10 points): `tn_elev_min, tn_elev_mean, tn_slope_mean, tn_slope_max, tn_flowacc_max, tn_hand_min, tn_stream_power_max, tn_relief_50m, tn_dist_stream_m, tn_is_low_point`.

### Weather — NOAA GHCN-d
- Stations: AVL (Asheville), RDU, GSO, CLT, ILM. Nearest station per segment.
- Over the window `YEAR_LAST_REHAB → 2025`: `wx_freeze_thaw_per_yr` (Tmin < 0 and Tmax > 0), `wx_heavy_rain_days_per_yr` (≥ 25 mm), `wx_precip_mm_per_yr`.

### Imagery — NAIP via Planetary Computer
- STAC `https://planetarycomputer.microsoft.com/api/stac/v1`, collection `naip`, NC 2022. `pystac_client` + `planetary_computer.sign` + `rasterio` windowed reads.
- One chip per segment at the midpoint, 128×128 px (≈77 m), 4 bands uint8, saved as `data/chips/{seg_id}.npy`. Parallelise with 16–32 workers. Budget ~3 h for 112k. Start at hour 1.
- Cheap features: `im_ndvi_mean, im_ndvi_std, im_impervious_frac (NDVI<0.1), im_bright_var`.
- Learned features: see §4.

### Traffic
- `AADT` from the Asphalt layer for state roads. City streets: nearest NCDOT traffic segment, else functional class as proxy. Record `tr_aadt_source`.

### Validation extras
- Ask Raleigh potholes (Jul 2025+): hit rate in top vs bottom decile of predicted deter_rate on Raleigh state roads.

---

## 3. Feature table contract — `data/processed/segments.parquet`

```
seg_id, geometry(wkb), source(ncdot|city), county, route, length_m, func_class, lanes, split_block (5 km grid id)
pv_rating, pv_srvy_yr, pv_year_last_rehab, pv_age, pv_surface, pv_curb, pv_shoulder_w, pv_iri, pv_rut, pv_algtr_mod_hi_pct, pv_patch_cd, pv_rvl_cd
tr_aadt, tr_aadt_source
tn_*  (above)
wx_*  (above)
im_ndvi_mean, im_ndvi_std, im_impervious_frac, im_bright_var, im_emb_00..15, im_vit_rate, im_vit_crack, im_vit_flood
sl_rating_nbr_mean, sl_algtr_nbr_mean, sl_flowacc_nbr_max
y_deter_rate, y_cracking_hi, y_flood_failed
```

---

## 4. Model ladder

All models use the same `split_block` 5-fold spatial CV. No random splits, ever.

1. **Hour 6 — LightGBM baseline:** `pv_ + tr_` only. L1 objective for rate, binary for cracking and flood. Monotone constraint on `pv_age` (+). This is "what a PMS already knows."
2. **Hour 8 — +terrain, +weather, +spatial lags:** one ablation row each.
3. **Hour 10 — Frozen DINOv2 ViT-S/14 embeddings** on RGB chips → PCA 16 → `im_emb_*`. Linear probe on its own first (20 min) for the "frozen SSL" row.
4. **Hour 10–16 — Fine-tune ViT-S/14 (DINOv2 init), multi-task:** 3 heads (rate, cracking, flood), weighted BCE on flood. LR 1e-5 backbone / 1e-4 head, layer-wise decay 0.8, 5–10 epochs, batch 64, flips + 90° rotations only. LoRA if memory-bound. Train on the same block folds; output out-of-fold scores as `im_vit_*` and stack into LightGBM. Needs a GPU (Colab T4 is enough, ~10 min/epoch). If no GPU by hour 10, skip; frozen row stands.
   - Alternative backbone if someone verifies weights load in hour 1: DOFA (accepts 4-band natively). Otherwise DINOv2 RGB + NDVI as tabular.
5. **Hour 14 — Full stack:** all groups. Second variant trained with `pv_*` dropped, for city streets.
6. **Optional, 30 min — TabPFN** on the tabular columns as a second model, report alongside LightGBM.
7. **Stretch — Route transformer:** tokens = segment feature vectors in ROUTEID + milepost order, attention over the route, predict per-token targets. Only if ablation shows spatial lags matter and everything above is done.

**Eval (hour 14–18):** MAE + Spearman (rate), AUC-PR (cracking), precision@50 and recall@top-5% (flood) vs flowacc-only ranking. Ablation ladder table. SHAP summary + top-3 drivers per segment exported for the map.

---

## 5. Demo (Dev B)
- MapLibre GL + deck.gl PathLayer, PMTiles via tippecanoe (statewide is too big for raw GeoJSON). Zoom presets: Asheville, Raleigh.
- Layers: pothole risk (years_to_poor quantile), flood risk, "unsurveyed" mask (city streets), actual Helene damage points.
- Click: rating, age, predicted years to Poor, flood rank, top-3 SHAP, NAIP chip.
- Toggle: NCDOT snapshot (state roads only) vs our prediction (every street). Metrics card: the ablation table.
- Stretch: Valhalla with a custom costing that penalises top-5% flood segments.

---

## 6. Hour-0 checklist
1. [Nathan] Repo scaffold, `pyproject.toml`, `.gitignore data/raw data/chips`. Pull both NCDOT layers statewide with pagination to `data/raw/ncdot_{layer}.parquet`. Report row counts and join rate.
2. [Nathan] Verify county string format and Buncombe code with one query. Fetch 3DEP 30 m for NC bbox; confirm < 15 min. Start the NAIP chip job (background, logged).
3. [Dev A] Helene labels (above). Report by hour 2.
4. [Dev A] Centerlines for Asheville + Raleigh, GHCN-d pull, AADT shapefile.
5. [Dev B] Vite + MapLibre + deck.gl, 100 fake segments, click popup. Hour 2.

## 7. Known weaknesses (put in README)
- Pavement target is snapshot ÷ age, not a temporal forecast. NCDOT publishes no survey history.
- Flood labels come from one extreme event; the model learns Helene.
- NAIP 2022 is three years older than the 2025 survey.
- City streets have no labels; predictions there are transfer from state roads.
- Published pothole prediction is modest (TfL: 55% of pothole sections). Lift over baseline is the claim.
