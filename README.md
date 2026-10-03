# RoadSense AI — Intelligent Pavement Prediction & Disaster Resilience

RoadSense AI is a state-wide infrastructure intelligence platform that predicts road degradation and flood vulnerability across North Carolina. Built with LightGBM models trained on NCDOT pavement condition survey data, 3DEP terrain elevation/slope proxies, AADT traffic counts, and satellite imagery embeddings from frozen DINOv2 vision transformers.

---

## 1. Pipeline & Model Architecture (From `main`)

The machine learning pipeline evaluates **112,443 North Carolina road segments**:
- **Dataset**: `handoff/predictions_geo.parquet` (17.8 MB Parquet format with EPSG:4326 WKB geometry).
- **Target Variables**:
  1. `pred_rate`: Annual pavement rating deterioration rate (points per year, average ~1.34 pts/yr).
  2. `pred_years_to_poor`: Remaining operational horizon before the segment drops below rating 60 (average ~23.5 years).
  3. `pred_crack`: Probability of moderate-to-high alligator cracking (41% baseline prevalence).
  4. `pred_flood`: Flood damage probability, scored with high sensitivity inside the Hurricane Helene disaster zone (`in_helene_zone == 1`).

### Cross-Validation Results (5-Fold Spatial Block CV on 5km Grid)
| Model Architecture | Rate MAE | Rate Spearman | Cracking AUC-PR | Flood P@50 / AUC-PR |
| :--- | :--- | :--- | :--- | :--- |
| **LightGBM (Pavement + Traffic AADT Baseline)** | 0.781 | 0.503 | 0.706 | 0.26 / 0.111 |
| **+ 3DEP Terrain (Elevation, Slope, Relief, HAND proxy)** | **0.765** | **0.533** | **0.731** | **0.36 / 0.206** |
| **+ Frozen DINOv2 Satellite Embedding (PCA 16)** | 0.746 | 0.587 | 0.663 | *(Tested on 8.5k subset)* |

---

## 2. Real-Time Architecture: Do You Need an API?

### The Architectural Decision Matrix
When dealing with **112,443 road segments** (~18 MB Parquet, ~90 MB GeoJSON):

| Use Case | Architecture Approach | Is an API Required? | Why? |
| :--- | :--- | :--- | :--- |
| **Large-Scale Map Rendering (60fps Pan/Zoom)** | **PMTiles / Vector Tiles** | **No API required** *(Serverless)* | Serving a single static `predictions.pmtiles` file over HTTP Range Requests allows the browser to fetch only 20KB–100KB vector slices on demand. Scales infinitely at zero server cost. |
| **Dynamic Viewport Bounding Box Queries** | **FastAPI Spatial Backend** | **Yes** | Allows map to request `GET /api/segments/bbox?minx=...` dynamically without downloading the entire 90MB dataset upfront. |
| **Live "What-If" Degradation Simulation** | **FastAPI ML Service** | **Yes** | Allows users to simulate traffic surges (`+35% AADT`) or storm events (Hurricane Helene 500-yr flood) via `POST /api/simulate` and receive recalculated deterioration curves in real time. |
| **Real-Time Sensor Telemetry & Weather Feeds** | **FastAPI + WebSockets / SSE** | **Yes** | Ingests real-time precipitation radars and USGS river gauge streams to trigger flood alerts on intersecting road segments. |

### Implemented Dual-Mode Architecture
RoadSense AI implements a **dual-mode architecture**:
1. **Standalone Offline Mode**: The web client bundles 300 rich, real North Carolina segments (Asheville & Raleigh) with statewide metadata, functioning instantly with zero server setup.
2. **Live FastAPI Backend (`src/api.py`)**: A high-performance Python microservice that loads all 112,443 segments into memory with spatial indexing for live bounding-box queries, statewide statistics, and ML degradation simulations.

---

## 3. Quickstart Guide

### Running the FastAPI Backend
```bash
# Start FastAPI prediction microservice on port 8000
uv run --with fastapi,uvicorn,pyarrow,pandas,shapely uvicorn src.api:app --host 127.0.0.1 --port 8000 --reload
```
Interactive Swagger API documentation is available at `http://127.0.0.1:8000/docs`.

#### Key API Endpoints
- `GET /api/health` — Status and dataset record count (112,443 segments).
- `GET /api/stats` — Statewide aggregations (total segments, Helene counts, average deterioration rate).
- `GET /api/segments?city=Asheville&limit=100` — Filter segments by city or Helene impact zone.
- `GET /api/segments/bbox?minx=-82.7&miny=35.4&maxx=-82.4&maxy=35.7` — Spatial bounding box viewport query.
- `POST /api/simulate` — Real-time simulation of traffic surges and storm flood scenarios on any segment.

### Running the Web Frontend
```bash
cd web
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 4. Frontend Component Overview

1. **Map Card (`CleanMapCard.tsx`)**:
   - **Executive Canvas**: High-resolution executive map with interactive amber glowing pins, black metric badges, and instant city navigation.
   - **Live Vector GIS**: MapLibre GL + deck.gl `PathLayer` rendering real road lines colored by predicted condition score, with real-time hover inspection and click selection.
   - **Top Pill Controls**: Search input, Jurisdiction filter (State Surveys vs Prediction), State dropdown, City dropdown (Asheville vs Raleigh), and Live Mode switcher.
2. **Location Card (`CleanLocationCard.tsx`)**:
   - Live telemetry pod displaying real segment ID, road corridor, pavement age, predicted years to poor, and flood inundation risk.
   - Interactive favorite heart toggle and click-to-open inspection drawer.
3. **Tenants Card (`CleanTenantsCard.tsx`)**:
   - Large golden amber circular progress gauge and agency avatar stack.
   - Click-to-open network architecture and statewide statistics overview.
4. **Detail Inspection Modal (`SegmentDetailModal.tsx`)**:
   - Deep drilldown into LightGBM + 3DEP predictions: cracking probability, deterioration rate, Helene disaster zone indicator, and top 3 attribution drivers.
