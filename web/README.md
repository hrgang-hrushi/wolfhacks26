# Unwatched Roads: web dashboards

One Vite + React app with three routes:

- **`/gov`** agency dashboard (desktop): map, ranked work queue, work orders, storm readiness, alerts, model transparency.
- **`/m`** judge dashboard (phone): map, Condition / Flood / Model in action, with the Helene backtest reveal.
- **`/dashboard`** executive dashboard: a statewide map and three summary cards.
- **`/`** sends narrow screens to `/m` and everything else to `/gov`.

`/gov` and `/m` read static JSON from `public/data/`, which a Python script builds from the prediction file. They need no backend. `/dashboard` calls the API in `server/main.py` (`/api/segments/bbox` and friends) and falls back to a bundled sample of roads when it is not there. When that API has a Tiger Data database behind it, `/gov` also shows a flood watch and a database panel (`docs/features/TIGER_DASHBOARD.md`).

## Display settings

- **Theme.** Light, dark or match the device, from the moon button on `/gov` and `/m` or the settings button on `/gov`. Light is the default. The choice is kept in the browser and applied before first paint (`src/lib/prefs.ts`, and a small script in `index.html`).
- **Panels on `/gov`.** Drag the divider between the map and the side panel, or between the map and the bottom panel, to resize. Double-click a divider to reset it. Each panel can be hidden and shown again, and the bottom panel can be maximised.
- **What shows on `/gov`.** The settings button chooses table density, which summary tiles show, which work queue columns show, and whether the map legend and hints show. "Reset layout" puts everything back.
- **Keys on `/gov`.** `/` focuses the search box, `1` to `4` change what the map is coloured by, `Esc` clears the selection.
- **Links.** Selecting a road on `/gov` puts `?seg=...&at=...` in the address bar; that link reopens the same road.

## Run it locally

```bash
# 1. from the repo root: build the data files (about 20 seconds, writes web/public/data/, ~50 MB)
uv run python scripts/build_web_data.py

# 2. start the app
cd web
npm install
npm run dev
```

Open `http://localhost:5173/gov` or `http://localhost:5173/m`.

A built copy of `web/public/data/` **is committed**, so step 1 is only needed after the predictions change; commit the rebuilt files when you run it. A rebuild has to happen on a machine that has the data. The script always needs `handoff/predictions_geo.parquet` (committed). Route names, county, mileposts, rating, NCDOT treatment and cost come from `data/raw/ncdot_joined.parquet`, and the Helene backtest from `data/raw/helene_labels.parquet`. Neither of those two is committed. Without them the script still runs, says what it left out, and the dashboards hide those parts.

## What the data files are

| File | What it holds |
|---|---|
| `stats.json` | Statewide counts, tier counts, county table, exact-threshold histograms, shard index, README metrics (source noted) |
| `shards/<cell>.json` | Every road on a 0.25 degree grid: `{id, path, rate, ytp, crack, flood, hz, ho}` |
| `overview.json` | The ~5,000 highest-priority roads, simplified, for zoomed-out views |
| `detail/<cell>.json` | NCDOT record fields per road, fetched when a road is opened |
| `ranked.json` | Top 1,000 roads in each of the three action tiers |
| `county/<code>.json` | Every action-tier road in one county, plus where each SR number is |
| `routes.json` | Where each Interstate / US / NC route is; which counties have an SR number |
| `storm.json` | The 300 highest flood scores in the Helene zone |
| `backtest.json` | The 50 highest held-out flood scores and what Helene did to them |

`path` is a flat list of integers: the first pair is `round(degrees * 1e5)` for longitude and latitude, and every later pair is the difference from the point before. `ho` is a bit mask: 1 wear held-out, 2 cracking held-out, 4 flood held-out. `flood` is present only inside the Helene zone.

Tier thresholds and the priority-score weights are in `src/lib/priority.json`. Change them there and rerun the build script; the app and the script both read that file.

## Google Maps on `/m` (optional)

Copy `.env.example` to `.env` (git-ignored) and set both values. Without them, or if Google fails to load for any reason, `/m` uses MapLibre with the same road layers.

```
VITE_GOOGLE_MAPS_API_KEY=...   # restrict by HTTP referrer to the deployed domain
VITE_GOOGLE_MAP_ID=...         # must be a vector map ID
```

The Google path has not been run with a real key. The MapLibre path is the one that was tested.

## Deploy

The site is fully static. The data files cannot be rebuilt on a hosting service (the source files are not in the repo), but a built copy is committed in `web/public/data/`, so a host that builds from the repo ships it. You can also **build on this machine, then upload `web/dist`**:

```bash
uv run python scripts/build_web_data.py     # from the repo root
cd web
npm ci
npm run build                               # set the two VITE_GOOGLE_* variables first if you want Google Maps
```

Then one of:

```bash
# Netlify (public/_redirects handles /m and /gov)
npx netlify-cli deploy --prod --dir=dist

# Cloudflare Pages (unknown paths fall back to index.html by default)
npx wrangler pages deploy dist --project-name unwatched-roads

# Vercel (vercel.json handles /m and /gov; --prebuilt uploads what you built)
npx vercel build --prod && npx vercel deploy --prebuilt --prod
```

For Vercel, `VITE_GOOGLE_MAPS_API_KEY` and `VITE_GOOGLE_MAP_ID` are read at build time from `web/.env` on this machine. Nothing needs to be set on the host for a prebuilt upload.

## QR code for the poster

After deploying, from the repo root:

```bash
uv run --no-project --with segno --with pillow python scripts/make_qr.py "https://<deployed-domain>/m?demo=1"
```

It writes `web/public/qr/unwatched-roads.png` and `.svg` with the short address printed underneath. `?demo=1` opens the page straight into the Helene backtest. Rebuild and redeploy if you want the QR image served from the site too.

## Checks

```bash
npm run build      # TypeScript (strict) + production build
npm run lint       # oxlint
cd .. && uv run pytest tests/web -q    # data build, tier logic, API
```
