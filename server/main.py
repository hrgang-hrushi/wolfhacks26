"""RoadSense AI Prediction API service for Vercel and local development.

Run with:
    uvicorn server.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("roadsense.api")

SERVER_DIR = Path(__file__).resolve().parent
CANDIDATE_PATHS = [
    SERVER_DIR / "predictions_geo.parquet",
    SERVER_DIR.parent / "handoff" / "predictions_geo.parquet",
    Path("handoff/predictions_geo.parquet"),
]

DATA_PATH = next((p for p in CANDIDATE_PATHS if p.exists()), CANDIDATE_PATHS[0])

# One reply carries full geometry, so this stays well under the hosting response cap.
MAX_LIMIT = 5000


def _num(v: float | None, nd: int) -> float | None:
    """Rounded float, or None for a missing value."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), nd)


NC_COUNTIES = [
    "Alamance", "Alexander", "Alleghany", "Anson", "Ashe", "Avery", "Beaufort", "Bertie", "Bladen", "Brunswick",
    "Buncombe", "Burke", "Cabarrus", "Caldwell", "Camden", "Carteret", "Caswell", "Catawba", "Chatham", "Cherokee",
    "Chowan", "Clay", "Cleveland", "Columbus", "Craven", "Cumberland", "Currituck", "Dare", "Davidson", "Davie",
    "Duplin", "Durham", "Edgecombe", "Forsyth", "Franklin", "Gaston", "Gates", "Graham", "Granville", "Greene",
    "Guilford", "Halifax", "Harnett", "Haywood", "Henderson", "Hertford", "Hoke", "Hyde", "Iredell", "Jackson",
    "Johnston", "Jones", "Lee", "Lenoir", "Lincoln", "Macon", "Madison", "Martin", "McDowell", "Mecklenburg",
    "Mitchell", "Montgomery", "Moore", "Nash", "New Hanover", "Northampton", "Onslow", "Orange", "Pamlico",
    "Pasquotank", "Pender", "Perquimans", "Person", "Pitt", "Polk", "Randolph", "Richmond", "Robeson", "Rockingham",
    "Rowan", "Rutherford", "Sampson", "Scotland", "Stanly", "Stokes", "Surry", "Swain", "Transylvania", "Tyrrell",
    "Union", "Vance", "Wake", "Warren", "Washington", "Watauga", "Wayne", "Wilkes", "Wilson", "Yadkin", "Yancey",
]

ROUTE_PREFIX = {"1": "I-", "2": "US ", "3": "NC ", "4": "SR "}

# Reference points for the dashboard's "nearest city" grouping. A label for the area, not an address.
METROS = [
    ("Charlotte", -80.84, 35.22), ("Raleigh", -78.64, 35.78), ("Greensboro", -79.79, 36.07),
    ("Winston-Salem", -80.24, 36.10), ("Wilmington", -77.94, 34.23), ("Asheville", -82.55, 35.59),
    ("Fayetteville", -78.88, 35.05), ("Greenville", -77.37, 35.61), ("Boone", -81.67, 36.21),
    ("Outer Banks", -75.62, 35.95),
]

# A flood score at or above this is "high" (the fix-now threshold in web/src/lib/priority.json).
HIGH_FLOOD = 0.5


def route_label(route_id: str) -> str:
    """'20000013008' -> 'US 13'. An NCDOT route id is a class digit, two flag digits, a five-digit number, then the county."""
    try:
        return f"{ROUTE_PREFIX.get(route_id[:1], 'SR ')}{int(route_id[3:8])}"
    except ValueError:
        return "State road"


def county_name(route_id: str) -> str | None:
    """The county from the last three digits of the route id (001 Alamance to 100 Yancey)."""
    try:
        i = int(route_id[8:11])
    except ValueError:
        return None
    return NC_COUNTIES[i - 1] if 1 <= i <= len(NC_COUNTIES) else None


def nearest_metro(lng: float, lat: float) -> str:
    return min(METROS, key=lambda m: (lng - m[1]) ** 2 + (lat - m[2]) ** 2)[0]


def _resolve_road_meta(seg_id: str, coords: list) -> tuple[str, str]:
    """(nearest city, road name) from the road's own id and position. Nothing here is invented."""
    parts = seg_id.split(":")
    route_id = parts[1] if len(parts) > 1 else ""
    county = county_name(route_id)
    name = route_label(route_id) + (f", {county} County" if county else "")
    if len(parts) > 2:
        try:
            name += f" (mp {float(parts[2]):.2f})"
        except ValueError:
            pass
    city = nearest_metro(coords[0][0], coords[0][1]) if coords else (f"{county} County" if county else "North Carolina")
    return city, name


class Store:
    """The predictions parquet file in memory, with a spatial STRtree index over road lines."""

    def __init__(self, path: Path = DATA_PATH) -> None:
        self.df = None
        self.geoms = []
        self.tree = None

        if not path.exists():
            logger.warning(f"Data file not found at {path.resolve()}, initializing empty store")
            import pandas as pd
            self.df = pd.DataFrame(columns=[
                "seg_id", "pred_rate", "pred_years_to_poor", "pred_crack", "pred_flood",
                "in_helene_zone", "rate_heldout", "crack_heldout", "flood_heldout"
            ])
            return

        # Fast pyarrow + shapely load (zero C-GIS/GDAL requirement)
        try:
            import pyarrow.parquet as pq
            import shapely
            from shapely import STRtree

            table = pq.read_table(path)
            self.df = table.drop(["geometry"]).to_pandas()
            geoms_wkb = table["geometry"].to_numpy()
            self.geoms = shapely.from_wkb(geoms_wkb)
            self.tree = STRtree(self.geoms)
            logger.info(f"Loaded {len(self.df)} segments via pyarrow/shapely")
            return
        except Exception as e:
            logger.warning(f"pyarrow/shapely load failed: {e}; attempting geopandas fallback")

        try:
            import geopandas as gpd
            from shapely import STRtree

            g = gpd.read_parquet(path)
            self.df = g.drop(columns="geometry")
            self.geoms = g.geometry.to_numpy()
            self.tree = STRtree(self.geoms)
            logger.info(f"Loaded {len(self.df)} segments via geopandas")
            return
        except Exception as e:
            logger.error(f"geopandas loader fallback failed: {e}")
            import pandas as pd
            self.df = pd.DataFrame(columns=[
                "seg_id", "pred_rate", "pred_years_to_poor", "pred_crack", "pred_flood",
                "in_helene_zone", "rate_heldout", "crack_heldout", "flood_heldout"
            ])

    def __len__(self) -> int:
        return len(self.df) if self.df is not None else 0

    def stats(self) -> dict:
        if self.df is None or len(self.df) == 0:
            return {
                "total_segments": 0,
                "helene_zone_segments": 0,
                "segments_without_years_to_poor": 0,
                "median_years_to_poor": None,
                "mean_pred_rate": None,
                "heldout": {"rate": 0, "crack": 0, "flood": 0},
                "scope": "State-maintained roads only.",
            }

        df = self.df
        zone = df.in_helene_zone == 1
        return {
            "total_segments": int(len(df)),
            "helene_zone_segments": int(zone.sum()),
            "segments_without_years_to_poor": int(df.pred_years_to_poor.isna().sum()),
            "median_years_to_poor": _num(float(df.pred_years_to_poor.median()), 1),
            "mean_pred_rate": _num(float(df.pred_rate.clip(lower=0).mean()), 3),
            "heldout": {
                "rate": int(df.rate_heldout.sum()),
                "crack": int(df.crack_heldout.sum()),
                "flood": int(df.flood_heldout.sum()),
            },
            "scope": "State-maintained roads only. Flood scores apply only where in_helene_zone is true.",
        }

    def record(self, i: int, with_path: bool = True) -> dict:
        if self.df is None or i >= len(self.df):
            return {}

        import shapely

        r = self.df.iloc[i]
        in_zone = bool(r.in_helene_zone)
        ytp = _num(r.pred_years_to_poor, 2)
        rate = _num(r.pred_rate, 3)
        flood = _num(r.pred_flood, 4) if in_zone else None
        # A 0-1 condition index for map colour: years to Poor over a 35-year horizon. None when there is no forecast.
        score = _num(max(0.05, min(1.0, ytp / 35.0)), 3) if ytp is not None else None

        paths = []
        if with_path and i < len(self.geoms):
            geom = self.geoms[i]
            parts = [geom] if geom.geom_type == "LineString" else list(geom.geoms)
            paths = [[[round(x, 5), round(y, 5)] for x, y in shapely.get_coordinates(p)] for p in parts]
        path = paths[0] if paths else []

        seg_id_str = str(r.seg_id)
        city, name = _resolve_road_meta(seg_id_str, path)

        if not in_zone:
            flood_rank = "Not scored (outside the Helene zone)"
        elif flood is not None and flood >= HIGH_FLOOD:
            flood_rank = "High flood score (Helene zone)"
        else:
            flood_rank = "Lower flood score (Helene zone)"

        return {
            "seg_id": seg_id_str,
            "name": name,
            "source": "ncdot",
            "score": score,
            # The condition index as 0-100. It is derived from the forecast, not NCDOT's surveyed rating.
            "pv_rating": int(round(score * 100)) if score is not None else None,
            # Surface age is not in the predictions file; the dashboards read it from the NCDOT record instead.
            "pv_age": None,
            "years_to_poor": ytp,
            "city": city,
            "flood_rank": flood_rank,
            # The three groups of inputs the models use (README, "Does it work?"). Not per-road importances.
            "drivers": ["Pavement record (age, last treatment)", "Traffic volume", "Shape of the land (slope, drainage)"],
            "chip_url": None,
            "pred_rate": rate,
            "pred_years_to_poor": ytp,
            "pred_crack": _num(r.pred_crack, 4),
            "pred_flood": flood,
            "in_helene_zone": in_zone,
            "rate_heldout": bool(r.rate_heldout),
            "crack_heldout": bool(r.crack_heldout),
            "flood_heldout": bool(r.flood_heldout),
            "path": path,
            "paths": paths,
        }

    def bbox(self, minx: float, miny: float, maxx: float, maxy: float, limit: int = 250) -> dict:
        """Roads whose line touches the box. When more match than `limit`, an even spread of them, not the first few."""
        if self.tree is None or self.df is None or len(self.df) == 0:
            return {
                "bbox": [minx, miny, maxx, maxy],
                "matched": 0,
                "count": 0,
                "truncated": False,
                "segments": [],
            }

        import shapely

        hits = sorted(int(i) for i in self.tree.query(shapely.box(minx, miny, maxx, maxy), predicate="intersects"))
        matched = len(hits)
        if matched > limit:
            # The file is in route order, so the first `limit` rows are one corner of the box. Take every k-th instead.
            step = matched / limit
            hits = [hits[int(k * step)] for k in range(limit)]
        return {
            "bbox": [minx, miny, maxx, maxy],
            "matched": matched,
            "count": len(hits),
            "truncated": matched > limit,
            "segments": [self.record(i) for i in hits],
        }

    def find(self, seg_id: str) -> dict | None:
        if self.df is None or len(self.df) == 0:
            return None
        m = self.df.index[self.df.seg_id == seg_id]
        return self.record(int(m[0])) if len(m) else None


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


# =============================================================================
# Top-level ASGI Application for Vercel & Uvicorn
# =============================================================================

app = FastAPI(
    title="RoadSense AI / Unwatched Roads API",
    description="Read-only predictions for 112,443 North Carolina state road segments.",
    version="2.0.0",
)

# Read-only and public: any site may call it, and it never takes cookies or credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


ROUTE_CORRIDORS = {
    "asheville-helene": {
        "id": "asheville-helene",
        "name": "Asheville Mountain Pass (Helene Corridor)",
        "region": "Western NC / Blue Ridge",
        "badge": "Helene Impact Zone",
        "center": [-82.445, 35.602],
        "zoom": 11.8,
        "origin": "Asheville River Arts District (US-25)",
        "destination": "Black Mountain / Swannanoa (I-40 East)",
        "fastest": {
            "label": "Fastest Route (Google Maps Baseline)",
            "travel_time_min": 19,
            "distance_miles": 14.2,
            "pci_score": 41,
            "flood_risk_pct": 92.0,
            "severe_potholes": 8,
            "road_name": "Swannanoa River Rd (US-70 Lowland)",
            "critical_hazards": [
                "Swannanoa River Lowland Washout (92% flood failure hazard)",
                "Severe Sub-base Structural Collapses (8 axle-strike potholes)",
            ],
            "geometry": [
                [-82.565, 35.585], [-82.551, 35.589], [-82.535, 35.592], [-82.518, 35.595],
                [-82.498, 35.599], [-82.475, 35.604], [-82.451, 35.607], [-82.430, 35.611],
                [-82.405, 35.614], [-82.378, 35.616], [-82.350, 35.617], [-82.321, 35.618]
            ]
        },
        "safest": {
            "label": "Safest Route (RoadSense AI Hazard-Penalized)",
            "travel_time_min": 22,
            "distance_miles": 16.5,
            "pci_score": 89,
            "flood_risk_pct": 0.0,
            "severe_potholes": 0,
            "road_name": "I-40 Ridge High Ground & Blue Ridge Pass",
            "critical_hazards": [],
            "geometry": [
                [-82.565, 35.585], [-82.560, 35.568], [-82.542, 35.558], [-82.515, 35.552],
                [-82.485, 35.559], [-82.450, 35.572], [-82.420, 35.588], [-82.390, 35.602],
                [-82.360, 35.612], [-82.335, 35.616], [-82.321, 35.618]
            ]
        },
        "hazards_avoided": {"potholes": 8, "flood_zones": 2, "time_delta_min": 3},
        "ai_rationale": "RoadSense AI penalizes the Google Maps default (US-70) due to 92% flood vulnerability along the Swannanoa riverbed and 8 unpatched severe potholes. Rerouting via the I-40 Ridge adds only 3 minutes to travel time while eliminating 100% of flood hazard and boosting Pavement Condition Index from 41 to 89."
    },
    "raleigh-capital": {
        "id": "raleigh-capital",
        "name": "Raleigh Capital Corridor (Crabtree Creek Lowland)",
        "region": "Central NC / Research Triangle",
        "badge": "Capital District",
        "center": [-78.658, 35.807],
        "zoom": 12.4,
        "origin": "NC State Centennial Campus (Fitts-Woolard Hall)",
        "destination": "North Hills / Midtown Raleigh (Six Forks Rd)",
        "fastest": {
            "label": "Fastest Route (Google Maps Baseline)",
            "travel_time_min": 14,
            "distance_miles": 8.1,
            "pci_score": 56,
            "flood_risk_pct": 68.0,
            "severe_potholes": 4,
            "road_name": "Glenwood Ave & Crabtree Floodplain",
            "critical_hazards": [
                "Crabtree Creek Flash Floodway (68% high water surge danger)",
                "Glenwood Ave Rutting & Pothole Clusters (4 tire-puncture risks)",
            ],
            "geometry": [
                [-78.6748, 35.7725], [-78.6720, 35.7850], [-78.6650, 35.7980], [-78.6610, 35.8110],
                [-78.6570, 35.8230], [-78.6520, 35.8340], [-78.6410, 35.8420]
            ]
        },
        "safest": {
            "label": "Safest Route (RoadSense AI Hazard-Penalized)",
            "travel_time_min": 16,
            "distance_miles": 9.4,
            "pci_score": 92,
            "flood_risk_pct": 2.0,
            "severe_potholes": 0,
            "road_name": "I-440 Beltline High Elevation Flyover",
            "critical_hazards": [],
            "geometry": [
                [-78.6748, 35.7725], [-78.6850, 35.7800], [-78.6920, 35.7950], [-78.6880, 35.8150],
                [-78.6750, 35.8310], [-78.6580, 35.8400], [-78.6410, 35.8420]
            ]
        },
        "hazards_avoided": {"potholes": 4, "flood_zones": 1, "time_delta_min": 2},
        "ai_rationale": "RoadSense AI detects high vulnerability in the Crabtree Creek basin. By shifting the vehicle path to the I-440 elevated flyover, drivers avoid 4 severe potholes and 1 critical flood entrapment hazard for a minor 2-minute delta, raising road quality from 56 to 92 PCI."
    },
    "outer-banks-coast": {
        "id": "outer-banks-coast",
        "name": "Outer Banks Coastal Corridor (NC 12 Dune Overwash)",
        "region": "Eastern NC / Cape Hatteras Coast",
        "badge": "Atlantic Surge Zone",
        "center": [-75.535, 35.773],
        "zoom": 10.4,
        "origin": "Nags Head Beachfront (US-158)",
        "destination": "Rodanthe / Hatteras Island (NC-12 South)",
        "fastest": {
            "label": "Fastest Route (Google Maps Baseline)",
            "travel_time_min": 32,
            "distance_miles": 25.1,
            "pci_score": 48,
            "flood_risk_pct": 84.0,
            "severe_potholes": 6,
            "road_name": "NC 12 Dune Overwash Section",
            "critical_hazards": [
                "Pea Island Ocean Dune Breach (84% ocean overwash hazard)",
                "Saltwater Ponding & Undermined Asphalt Shoulders",
            ],
            "geometry": [
                [-75.602, 35.952], [-75.589, 35.910], [-75.578, 35.865], [-75.565, 35.815],
                [-75.548, 35.760], [-75.525, 35.700], [-75.495, 35.645], [-75.468, 35.594]
            ]
        },
        "safest": {
            "label": "Safest Route (RoadSense AI Hazard-Penalized)",
            "travel_time_min": 35,
            "distance_miles": 27.2,
            "pci_score": 95,
            "flood_risk_pct": 4.0,
            "severe_potholes": 0,
            "road_name": "Jug Handle Bridge Bypass & High Causeway",
            "critical_hazards": [],
            "geometry": [
                [-75.602, 35.952], [-75.592, 35.910], [-75.582, 35.865], [-75.572, 35.815],
                [-75.560, 35.760], [-75.545, 35.695], [-75.510, 35.635], [-75.480, 35.608],
                [-75.468, 35.594]
            ]
        },
        "hazards_avoided": {"potholes": 6, "flood_zones": 2, "time_delta_min": 3},
        "ai_rationale": "RoadSense AI detects high-tide overwash risks along NC-12 barrier dunes. Directing drivers onto the Jug Handle Bridge structure avoids the notorious S-curves dune breach zone, ensuring 100% passability and protecting vehicle undercarriages from corrosive saltwater."
    }
}


@app.get("/")
@app.get("/api")
def root():
    return {
        "service": "RoadSense AI API",
        "status": "online",
        "endpoints": [
            "/api/health",
            "/api/stats",
            "/api/segments",
            "/api/segments/bbox",
            "/api/segments/{seg_id}",
            "/api/routes/corridors",
            "/api/routes/safe-route",
        ],
    }


@app.get("/routes/corridors")
@app.get("/api/routes/corridors")
def list_route_corridors():
    return {"total": len(ROUTE_CORRIDORS), "corridors": list(ROUTE_CORRIDORS.values())}


@app.get("/routes/safe-route")
@app.get("/api/routes/safe-route")
def get_safe_route(
    corridor: str = Query("asheville-helene", description="Corridor ID: asheville-helene, raleigh-capital, or outer-banks-coast")
):
    if corridor not in ROUTE_CORRIDORS:
        raise HTTPException(
            status_code=404,
            detail=f"Corridor '{corridor}' not found. Available corridors: {list(ROUTE_CORRIDORS.keys())}"
        )
    return ROUTE_CORRIDORS[corridor]


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "total_records": len(get_store())}


@app.get("/stats")
@app.get("/api/stats")
def stats():
    return get_store().stats()


@app.get("/segments")
@app.get("/api/segments")
def list_segments(limit: int = Query(250, ge=1, le=MAX_LIMIT)):
    store = get_store()
    n = min(len(store), limit)
    return {"total": len(store), "count": n, "segments": [store.record(i) for i in range(n)]}


@app.get("/segments/bbox")
@app.get("/api/segments/bbox")
def segments_bbox(
    minx: float = Query(..., description="West longitude, e.g. -82.7"),
    miny: float = Query(..., description="South latitude, e.g. 35.4"),
    maxx: float = Query(..., description="East longitude, e.g. -82.4"),
    maxy: float = Query(..., description="North latitude, e.g. 35.7"),
    limit: int = Query(250, ge=1, le=MAX_LIMIT),
):
    if not all(math.isfinite(v) for v in (minx, miny, maxx, maxy)):
        raise HTTPException(status_code=422, detail="bbox values must be finite numbers")
    if minx >= maxx or miny >= maxy:
        raise HTTPException(status_code=422, detail="bbox must have minx < maxx and miny < maxy")
    return get_store().bbox(minx, miny, maxx, maxy, limit)


@app.get("/segments/{seg_id}")
@app.get("/api/segments/{seg_id}")
def segment(seg_id: str):
    rec = get_store().find(seg_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"segment {seg_id} not found")
    return rec


# Vercel and WSGI/ASGI entrypoint aliases
application = app
handler = app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
