# RoadSense AI — Pavement Condition Predictor (WolfHacks '26)

Interactive geospatial infrastructure dashboard built with **Vite**, **MapLibre GL**, and **deck.gl `PathLayer`** to visualize and inspect AI-predicted road surface deterioration across North Carolina.

---

## Quick Start

```bash
cd web
npm install
npm run dev
```

Visit `http://localhost:5173` to interact with the map.

To create a production build:
```bash
npm run build
npm run preview
```

---

## Features Implemented

1. **MapLibre GL & deck.gl `PathLayer`**:
   - High-contrast, dark-mode vector cartography powered by MapLibre GL.
   - High-performance WebGL line rendering via deck.gl `PathLayer` with smooth line caps and joints.
   - Interactive hover tooltips and dynamic selection highlighting with radiant cyan halo glow.

2. **100 Realistic Road Segments**:
   - 50 segments in **Raleigh** (Piedmont Capital region).
   - 50 segments in **Asheville** (Western Mountain region).
   - Coloured dynamically by a continuous condition score from `0.0` (Critical / Crimson) to `1.0` (Optimal / Emerald).

3. **City Quick-Zoom Controls**:
   - **Asheville Button**: Flies smoothly to the Asheville French Broad River & downtown corridor (`zoom: 13.4`, `pitch: 35°`, `bearing: -15°`).
   - **Raleigh Button**: Flies smoothly to the Raleigh Capital Blvd & downtown beltline (`zoom: 13.2`, `pitch: 25°`, `bearing: 0°`).

4. **Deep Inspection Slide-Over Panel**:
   - Clicking any road segment opens an inspection panel detailing:
     - **Pavement Rating (`pv_rating`)**: 0–100 condition rating with condition badge & progress gauge.
     - **Pavement Age (`pv_age`)**: Years since last resurfacing.
     - **Predicted Years Until Poor (`years_to_poor`)**: AI forecast horizon to failure threshold.
     - **Flood Rank (`flood_rank`)**: FEMA tier and hydrological saturation index.
     - **Top 3 Reasons (`drivers`)**: AI-attributed deterioration drivers (e.g., AADT heavy truck volume, freeze-thaw cycles, subgrade moisture).
     - **Aerial Photo Square Placeholder (`chip_url`)**: Strictly 1:1 aspect-ratio container displaying high-res satellite ortho simulation with target crosshairs, scale bar, and coordinate readout, ready for live raster drop-in.
     - **Fly to Segment Action**: Re-centers and zooms directly onto the chosen segment geometry.

5. **Coverage Filter Toggle**:
   - **"What the state surveys"**: Filters view to state-maintained roads only (`source === "ncdot"`).
   - **"What we predict"**: Expands view to every street across both state and municipal networks (`all`).

---

## Data Schema Contract (1:1 Drop-in Ready)

Every segment follows this exact TypeScript schema:

| Property | Type | Description | Production Compatibility |
| :--- | :--- | :--- | :--- |
| `seg_id` | `string` | Unique segment identifier (e.g., `"NC-RAL-001"`) | Matches real prediction output |
| `source` | `"ncdot" \| "city"` | Jurisdiction origin (`"ncdot"` state or `"city"` municipal) | Direct match |
| `pv_rating` | `number` | Pavement rating (0–100) | Direct match |
| `pv_age` | `number` | Age in years since last repave | Direct match |
| `years_to_poor` | `number` | Predicted years until condition reaches "Poor" | Direct match |
| `flood_rank` | `string \| number` | Flood risk classification | Direct match |
| `drivers` | `[string, string, string]` | Top 3 explanatory degradation factors | Direct match |
| `chip_url` | `string` | URL to aerial ortho photo chip | Direct match |
| `path` | `[number, number][]` | Array of `[longitude, latitude]` coordinates | deck.gl PathLayer |
| `score` | `number` | Normalized score `0.0 – 1.0` for color mapping | deck.gl Color Scale |

---

## Scaling to Real Data (112k+ Segments via PMTiles)

Loading 112,000+ line geometries as plain GeoJSON would result in an unwieldy **180 MB – 240 MB** payload, freezing browser tabs and failing on mobile devices.

### PMTiles Integration Roadmap:
1. **Pipeline**:
   - Export ML predictions with geometry into GeoJSON / GeoParquet.
   - Slice into multi-zoom vector tiles using Tippecanoe:
     ```bash
     tippecanoe -zg --drop-densest-as-needed --extend-zooms-if-still-dropping -l nc_roads -o nc_roads.pmtiles roads.geojson
     ```
2. **Client Streaming**:
   - Host `nc_roads.pmtiles` on S3 or Cloudflare R2 with HTTP Range Request support.
   - Register the `pmtiles` protocol in MapLibre:
     ```ts
     import * as pmtiles from 'pmtiles';
     const protocol = new pmtiles.Protocol();
     maplibregl.addProtocol('pmtiles', protocol.tile);
     ```
   - Connect the tile source directly to the map with sub-35ms tile streaming latency.
   - The UI components (`DetailPanel`, `Header`, `Legend`) consume feature properties identically without rewriting any application logic.
