# Prompt: build the two Unwatched Roads dashboards

Paste everything below the line into Claude Code, run from the root of `wolfhacks26`.

---

You are building two front ends for **Unwatched Roads**, our WolfHacks 2026 project (NC State, Oct 3-4, Center for Geospatial Analytics track). The project predicts pavement wear, cracking and Hurricane Helene flood-failure risk for all 112,443 NCDOT road segments. Read `README.md`, `DESIGN.md`, `src/api.py`, `web/src/types/roadSegment.ts`, `web/src/components/CleanMapCard.tsx` and `handoff/predictions_geo.parquet` first. Then build:

1. **Dashboard A, Agency dashboard** (desktop). For road officials: see road condition across the state, rank what to fix, and dispatch repair crews.
2. **Dashboard B, Judge dashboard** (mobile-first). Judges scan a QR code, land on a phone-friendly map of the predictions, and can switch on a "model in action" mode.

Both ship from the same Vite app in `web/` (routes `/gov` and `/m`, `/` redirects by screen width) and share one data layer.

## 0. Ground truth you must respect

What the data actually contains (`handoff/predictions_geo.parquet`, 112,443 rows, geometry simplified to 3 m, EPSG:4326):

| Column | Meaning |
|---|---|
| `seg_id` | `ncdot:<routeid>:<milepost>` (city segments would be `city:<OBJECTID>`, none scored yet) |
| `pred_rate` | predicted rating points lost per year (can be slightly negative; clamp for display) |
| `pred_years_to_poor` | years until rating drops below 60; capped at 50; **blank for ~1,643 segments** (rating out of date or rating 0) |
| `pred_crack` | probability of cracking above 10% |
| `pred_flood` | Helene-style flood-failure score, **meaningful only where `in_helene_zone == 1`** (about 29% of segments) |
| `rate_heldout`, `crack_heldout`, `flood_heldout` | true when that prediction came from a model that never saw the segment |

Headline numbers we can claim (from the README, do not inflate them): wear-rate typical miss 0.749 pts/yr vs 0.965 with no model; cracking AUC-PR 0.422 vs 0.158 chance; of the 50 riskiest roads in the Helene zone, 18 were actually damaged vs about 2 by chance (13 without terrain features). State roads only. One snapshot, so wear per year is rating lost divided by age, not a measured trend.

**The current `src/api.py` and bundled `realRoads.json` fabricate several fields. Do not carry these into either dashboard:**

- `pv_rating` is computed as `60 + years*1.5`, not the real NCDOT rating. `pv_age` is also invented.
- Road names (`Patton Ave (Seg #0.200)`) are rotated from a hardcoded list by nearest city, so they are not the road's real name.
- `flood_rank` "FEMA Tier 1/2" and `drivers` ("Helene Storm Surge", "3DEP Slope Index") are hardcoded text. We never used FEMA data. `chip_url` points to files that don't exist.
- `/api/simulate` multiplies by hand-picked constants (0.45, 0.3, 2.4). It is not the model.
- `/api/weather` silently returns fixed fake weather when there is no API key.
- `DESIGN.md` and several components still carry real-estate leftovers ("Insurance Type", "Tenants", "ARR run rate", "$4.9M Est", house counts). Remove all of it.

Replace with real values or leave the field out. Where a real value needs a join that isn't in the handoff file (route name, county, NCDOT recommended treatment and cost), do it in the build script from `data/raw/ncdot_joined.parquet` **only if those columns exist there**. Check the real column names, and if a field isn't available, omit the UI for it. Label the road by what we truly know: route class and number parsed from the 8-character `ROUTE` (class digit 1 Interstate, 2 US, 3 NC, 4 secondary; route number in characters 4 to 8) plus milepost, e.g. "NC 12, mp 0.20".

Honesty rules for every screen:

- Always distinguish **held-out prediction** from **in-sample** using the `*_heldout` flags (small badge or tooltip).
- Show flood risk only inside the Helene zone. Outside it say "not assessed", never "low risk".
- State roads only. Say so in the UI.
- Anything that is a scenario or a mock must be visibly labeled as one.

## 1. Shared data layer (do this first)

Create `scripts/build_web_data.py` (run with `uv run`). It reads the handoff parquet (plus optional joins above) and writes static files to `web/public/data/`:

1. `stats.json`: statewide counts and averages, tier counts, Helene-zone counts, and the README metrics block (as a typed constant, with source noted).
2. Geometry shards: segments bucketed into a ~0.25 degree grid, coordinates quantized to 5 decimals, gzip-friendly JSON, each segment as `{id, path, rate, ytp, crack, flood, hz, ho}` with short keys. Also an `overview.json` with only the worst ~5,000 segments for zoomed-out views. The client fetches only the shards intersecting the viewport. This must be static-hostable with no backend, and total transfer for a typical phone view must stay under ~1.5 MB.
3. `ranked.json`: segments sorted by priority score (definition below), top ~3,000, with display fields.
4. `backtest.json` (for Dashboard B): the **top 50 riskiest held-out segments in the Helene zone** by `pred_flood`, with the real outcome `y_helene_failed` joined from `data/raw/helene_labels.parquet` (only if the file is present locally; it isn't committed). Include the overall count damaged. Only use segments where `flood_heldout` is true so the demo is honest. If the labels file is missing, skip this file and tell me.

Priority tiers (make thresholds constants at the top of one file, shown in the UI):

- **Fix now**: `pred_years_to_poor <= 1` or (`pred_crack >= 0.6`) or (in Helene zone and `pred_flood >= 0.5`)
- **Fix within a year**: years-to-poor <= 3 or crack >= 0.4
- **Plan within five years**: years-to-poor <= 5
- **Monitor**: everything else; **No estimate**: missing years-to-poor

Priority score for ranking inside a tier: weighted blend of normalized crack, flood (zone only) and inverse years-to-poor; AADT-based weighting is a stretch goal if `tr_aadt` is joinable.

Shared TS module `web/src/lib/data.ts` for loading shards, tier logic, color scale and formatting. Reuse `web/src/utils/colors.ts` (crimson to emerald) but drive it from tier or years-to-poor, not the fake `score`.

## 2. Dashboard A: Agency dashboard (`/gov`)

Audience: a district engineer or county maintenance supervisor. Desktop, dense, calm. Keep the visual language from `DESIGN.md` (light surfaces, 20px cards, amber alerts) but make it read as a government operations tool.

**Layout:** left rail, large map, right panel (selected segment), bottom or side work-queue panel. Zero page scroll; panels scroll internally.

**Map** (MapLibre GL + deck.gl `PathLayer`, existing deps; use free OSM/Carto basemap if no Mapbox token):
- Layer switcher: *Years to Poor* (default), *Cracking risk*, *Flood risk (Helene zone)*, *Priority tier*.
- Filters: tier, minimum cracking probability, Helene zone only, held-out only, route class (Interstate/US/NC/secondary), county if joinable, text search by route ("NC 12", "I-40").
- Box-select (shift-drag) to select many segments at once.
- Statewide view loads `overview.json`; zooming in loads shards.

**Segment panel (real values only):** route label and milepost, predicted wear rate, years to Poor (or "no estimate" with the reason), cracking probability, flood score if in zone, held-out badges, and recommended treatment and cost **only if joined**. Add a "Why" line that states honestly what drives the model (age, traffic, terrain, from the README's feature groups), not hardcoded driver strings. Optionally include the 77 m NAIP chip if you can generate one, otherwise omit.

**Crew dispatch workflow** (the core of this dashboard):
- "Add to work order" from a segment or a box selection.
- Work order fields: id, segments, priority tier, crew (pick from an editable list, seed with 4 demo crews labeled "demo crews"), due date, notes, status (Queued, Dispatched, In progress, Done).
- Kanban or table view of work orders. Status changes persist (localStorage is fine, FastAPI + SQLite if time allows). Put dispatched orders on the map with a distinct outline.
- Export work order as CSV and GeoJSON, and a printable one-page order (route, mileposts, tier, map thumbnail).
- Crew/work-order data is a demo of the workflow; label it "demo data" so nobody mistakes it for real dispatching.

**Storm readiness mode:** button "Storm readiness". Shows the top N (default 50) highest `pred_flood` roads in the Helene zone as a staging list with map pins, count by county if available, and an exportable detour/staging checklist. Use the README's validation claim (18 of top 50) in a small footnote. Do not invent a live storm feed.

**KPI strip:** total segments, Fix-now count, Fix-within-year count, Helene-zone high-flood count, share held-out. All from `stats.json`.

**Alerts:** we have a single snapshot, so there is no history. Implement "Alerts" as "segments currently over a threshold" with adjustable thresholds. Do not draw trend charts or "crossed threshold this week" claims. Remove the invented PCI forecast chart in `GovAnalyticsCard.tsx`, or replace it with a straight-line projection from the segment's own `pred_rate` that is labeled "linear projection at predicted wear rate".

**Model transparency drawer:** the README metrics table, what we cannot claim (the five bullets), and data sources. Judges and officials both look for this.

## 3. Dashboard B: Judge dashboard (`/m`)

Audience: a judge with a phone, 20 seconds of attention, scanned from a QR code on our poster. Portrait, one hand, bad conference wifi.

**Map:** Google Maps JavaScript API with the deck.gl `GoogleMapsOverlay` (`@deck.gl/google-maps`) drawing the same `PathLayer` shards. Needs a Maps JS API key and a vector **Map ID** in `VITE_GOOGLE_MAPS_API_KEY` and `VITE_GOOGLE_MAP_ID` (never commit the key; add to `.env.example`; I will restrict it by HTTP referrer to the deployed domain). If the key is missing or the load fails, **automatically fall back to MapLibre** with the same overlay so the demo never shows a blank map.

**Screen structure** (bottom-sheet pattern, thumb reachable):
- Top: one-line title "Which NC roads fail next, even the ones nobody inspects", small "State roads · held-out predictions" badge.
- Full-screen map, starting framed on Raleigh/Wake County with a locate-me button. Roads colored by years to Poor.
- Bottom sheet with a segmented control: **Condition | Flood | Model in action**. Swipe up for details.
- Tap a road: sheet shows route, years to Poor, cracking probability, flood score if in zone, held-out badge, in plain English. Use State Road 2748 in Wake County as a "featured example" chip that jumps to the road and shows the README's real worked example (rating 73.4, wear 1.77 vs predicted 1.62 pts/yr, cracking risk top 13%, inspection found cracking over 10%).

**"Model in action" mode** (the demo moment). Three real, honest options, in this priority order:

1. **Helene backtest (build this).** Show the 50 riskiest held-out roads in the Helene zone as pins from `backtest.json`, pitched as "we asked the model to rank roads without ever seeing them". A big **Reveal what happened** button flips each pin to damaged (red) or not damaged (gray) with an animated counter: "18 of 50 damaged vs about 2 expected by chance". This is the strongest, truest proof we have.
2. **Near me.** Uses geolocation to rank the nearest 5 scored segments by years to Poor. If the user is outside NC, offer "Jump to Raleigh / Asheville / Wilmington" buttons.
3. **Scenario slider (only if time).** Traffic and storm sliders. This **cannot** use the `/api/simulate` constants as if they were the model. Either (a) skip it, or (b) first persist the trained LightGBM models in `src/model/final_ablation.py` (joblib) and serve a real what-if, or (c) ship it clearly labeled "Illustrative scenario, not a model retrain". Ask me which before building.

Also include a collapsed "About" sheet with the three headline metrics and the "What we cannot claim" list.

**Mobile requirements:** works at 360x640, 44px touch targets, no hover-only interactions, respects `prefers-color-scheme`, loads first useful map in under 3 s on throttled "Fast 3G" (Chrome devtools), and stays usable offline once loaded (cache shards with a simple service worker or cache-first fetch).

## 4. Deployment and QR code

A phone cannot reach `localhost`, so the demo needs a public HTTPS URL:

1. Everything is static (`npm run build` in `web/`), so deploy `web/dist` to Vercel, Netlify or Cloudflare Pages. Give me the exact commands and the env vars to set. Keep `public/data` out of git if it is large and generate it in the build step instead (document which you chose).
2. Generate a QR code PNG and SVG for `https://<deployed-domain>/m` (script in `scripts/make_qr.py` or an npm one-liner), with a short fallback URL printed under it for posters. Put output in `web/public/qr/`.
3. Add a `?demo=1` URL param on `/m` that auto-opens "Model in action" so the QR on the poster can go straight to the proof.

## 5. Quality bar and order of work

Build in this order and tell me when each is done, so I can interrupt if time runs short (hackathon clock):

1. `scripts/build_web_data.py` and data layer, with a quick sanity print of tier counts and shard sizes.
2. Dashboard B, Condition and Flood tabs on Google Maps with MapLibre fallback.
3. Dashboard B, Helene backtest ("Model in action").
4. Dashboard A map, filters and segment panel.
5. Dashboard A work orders, export and storm readiness.
6. Deploy, QR, `?demo=1`, then cleanup of real-estate leftovers and fabricated fields.

Constraints: TypeScript strict, `npm run build` and `npm run lint` pass, no new heavy dependencies beyond `@deck.gl/google-maps` and `@googlemaps/js-api-loader` (and `pmtiles`/`maplibre` only if you can justify them), no secrets in git, and keep the existing Python tests passing (`uv run pytest -q`). If `src/api.py` stays, fix `/api/segments/bbox` so it uses a spatial index (it currently parses geometry for all 112k rows on every request) or stop depending on it, and remove the fabricated fields listed in section 0.

When anything in the data doesn't match what this prompt says, **stop and tell me rather than papering over it.**
