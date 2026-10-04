# Unwatched Roads: design notes for the two dashboards

Both dashboards are one Vite app in `web/`. They share one data layer (`web/src/lib/`) and read only static files written by `scripts/build_web_data.py`.

| Route | Who it is for | Form |
|---|---|---|
| `/gov` | A district engineer or county maintenance supervisor | Desktop, dense, calm, zero page scroll |
| `/m` | A hackathon judge who scanned the poster QR code | Phone, portrait, one hand, bad wifi |
| `/` | | Redirects to `/m` under 820 px wide, otherwise `/gov` |

## Rules every screen follows

1. **Real values only.** A number on screen is a column of `handoff/predictions_geo.parquet` or of the NCDOT record joined at build time. If a field cannot be joined, its UI is left out. Nothing is rotated from a list or computed from a made-up formula.
2. **Held-out vs in-sample is always visible.** Each prediction carries a `Held-out` or `In-sample` badge driven by `rate_heldout`, `crack_heldout`, `flood_heldout`. The badge explains itself on tap, not only on hover.
3. **Flood only in the Helene zone.** Outside it the screen says "not assessed", never "low risk". The flood value is not even shipped for those roads.
4. **State roads only**, and the UI says so.
5. **Scenarios and mock data are labelled.** Crews and work orders carry a `demo data` tag. There is no simulated storm feed and no what-if slider.
6. **One snapshot.** No trend charts and no "crossed a threshold this week". The only chart is a straight line from a road's own rating at its own predicted wear rate, labelled "linear projection at predicted wear rate".

## Shared pieces

- **Road label:** route class and number from the 8-character route code, plus milepost: `NC 12, mp 0.20`. County comes from the code in `seg_id`.
- **Repair tiers:** thresholds and score weights live in `web/src/lib/priority.json`, read by both the build script and the app, and shown in the UI.
- **Colour:** crimson to emerald (`web/src/utils/colors.ts`), driven by years to Poor, cracking probability, flood score or tier. Worse roads are also thicker and more opaque, so colour is not the only cue. Grey means no value.
- **Maps:** MapLibre GL with a free Carto basemap and a deck.gl `PathLayer` overlay. `/m` uses Google Maps with deck.gl's `GoogleMapsOverlay` when a key and Map ID are set, and falls back to MapLibre on any failure.

## Dashboard A: agency (`/gov`)

Visual language: light surfaces (`#ffffff` on `#f8fafc`), 20 px card radius, `1px solid rgba(0,0,0,0.07)` borders, soft shadow, Plus Jakarta Sans, amber (`#f59e0b`) for primary actions and alerts, jet black (`#111`) for active chips.

```
+------+--------------------------------------------------------------+
| Rail | Title · KPI strip (5 tiles, all from stats.json)             |
| 64px +----------------------------------------+---------------------+
|      | Map card                               | Side panel          |
|      |  search · county · filters · layer     |  Road / Work order  |
|      |  legend            status · hints      |  Storm / Model      |
|      +----------------------------------------+---------------------+
|      | Bottom panel: Work queue | Work orders | Alerts              |
+------+--------------------------------------------------------------+
```

- **Map:** layers Years to Poor (default), Cracking risk, Flood risk (Helene zone), Priority tier. Filters for tier, minimum cracking, Helene zone only, held-out only, route class and county; route search. Shift-drag selects many roads. Zoomed out it draws `overview.json`; zoomed in it loads the shards in view.
- **Road panel:** label, tier, the four predictions with badges, the NCDOT record (rating, resurfacing year, traffic, NCDOT's own treatment and cost), an honest "Why" line, and the linear projection.
- **Work orders:** add from a road, a box selection, the queue or the storm list. Status, crew, due date and notes persist in `localStorage`. Dispatched orders get a blue outline on the map. Export CSV, GeoJSON and a one-page printable order with a route sketch.
- **Storm readiness:** the top N flood scores in the Helene zone as numbered pins, a count by county, and a staging checklist (CSV and print). Footnote: 18 of the top 50 were damaged in the held-out test.
- **Alerts:** roads currently over an adjustable threshold. Counts are exact, from histograms in `stats.json`.
- **Model transparency:** the README results table, what cannot be claimed, tier rules and data sources.

## Dashboard B: judge (`/m`)

- Works at 360 x 640, 44 px touch targets, no hover-only interaction, follows `prefers-color-scheme`.
- Title bar, full-screen map framed on Raleigh, locate-me button, and a bottom sheet with three resting heights.
- Segmented control: **Condition | Flood | Model in action**.
- Tap a road for a plain-English card. A chip jumps to the README's worked example, State Road 2748 in Wake County.
- **Model in action:** the Helene backtest. Fifty pins, a **Reveal what happened** button, an animated counter ending on "18 of 50 damaged vs about 2 expected by chance". Also **Near me**, which ranks the five nearest scored roads.
- `?demo=1` opens straight into Model in action, for the poster QR code.
- A service worker caches the app and the road data, so a loaded map keeps working offline.

## Do not

- Do not bake controls into images or lay invisible buttons over pictures.
- Do not add page scrollbars on `/gov`; panels scroll inside themselves.
- Do not present a crew, a work order, a scenario or a camera flag as real without a label.
