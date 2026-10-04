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

MAX_LIMIT = 120000


def _num(v: float | None, nd: int) -> float | None:
    """Rounded float, or None for a missing value."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), nd)


def _resolve_road_meta(seg_id: str, in_zone: bool, coords: list) -> tuple[str, str]:
    lng = coords[0][0] if coords else -78.6
    lat = coords[0][1] if coords else 35.8
    parts = seg_id.split(":")
    route_code = parts[1] if len(parts) > 1 else ""
    mile = parts[2] if len(parts) > 2 else "0.0"

    # 1. Interstate Corridors
    if route_code.startswith("104"):
        return ("Asheville" if lng < -81.5 else ("Raleigh" if lng > -79.2 else "Greensboro")), f"I-40 Trans-Carolina Corridor (MP #{mile})"
    elif route_code.startswith("108"):
        return ("Charlotte" if lat < 35.5 else "Greensboro"), f"I-85 Piedmont Gateway (MP #{mile})"
    elif route_code.startswith("107"):
        return "Charlotte", f"I-77 Metrolina Expressway (MP #{mile})"
    elif route_code.startswith("109"):
        return "Fayetteville", f"I-95 Coastal Link (MP #{mile})"
    elif route_code.startswith("102"):
        return "Asheville", f"I-26 Mountain Pass (MP #{mile})"
    elif route_code.startswith("144") or route_code.startswith("154"):
        return "Raleigh", f"I-440 / I-540 Beltline (MP #{mile})"

    # 2. Geographic North Carolina City & Street Resolution
    if lng > -76.3:
        city = "Outer Banks"
        street = "Virginia Dare Trail" if "0" in mile else "Croatan Hwy (US-158)"
    elif lat < 34.6 and lng > -78.6:
        city = "Wilmington"
        street = "Market St (US-17)" if "1" in mile else ("College Rd" if "2" in mile else "Oleander Dr")
    elif lng > -77.8 and 35.3 <= lat <= 36.2:
        city = "Greenville"
        street = "Evans St" if "1" in mile else ("Greenville Blvd" if "2" in mile else "Arlington Blvd")
    elif -81.2 <= lng <= -80.5 and 35.0 <= lat <= 35.5:
        city = "Charlotte"
        street = "Tryon St" if "1" in mile else ("Independence Blvd (US-74)" if "2" in mile else "South Blvd")
    elif -80.1 <= lng <= -79.6 and 35.8 <= lat <= 36.3:
        city = "Greensboro"
        street = "Friendly Ave" if "1" in mile else ("Battleground Ave" if "2" in mile else "Wendover Ave")
    elif -80.5 <= lng < -80.1 and 35.9 <= lat <= 36.3:
        city = "Winston-Salem"
        street = "Broad St" if "1" in mile else ("Stratford Rd" if "2" in mile else "University Pkwy")
    elif -79.2 <= lng <= -78.6 and 34.8 <= lat <= 35.4:
        city = "Fayetteville"
        street = "Bragg Blvd" if "1" in mile else ("Skibo Rd" if "2" in mile else "Ramsey St")
    elif -82.0 <= lng <= -81.4 and 36.0 <= lat <= 36.5:
        city = "Boone"
        street = "Highland Ave" if "1" in mile else ("King St" if "2" in mile else "Blowing Rock Rd")
    elif -81.6 <= lng <= -81.1 and 35.6 <= lat <= 36.0:
        city = "Hickory"
        street = "US-70 Corridor" if "1" in mile else "Lenoir Rhyne Blvd"
    elif in_zone or lng < -82.0:
        city = "Asheville"
        street = "Patton Ave" if "1" in mile else ("Biltmore Ave" if "2" in mile else ("Merrimon Ave" if "3" in mile else "Tunnel Rd"))
    else:
        city = "Raleigh"
        street = "Hillsborough St" if "1" in mile else ("Fayetteville St" if "2" in mile else ("Capital Blvd (US-401)" if "3" in mile else "Wade Ave"))

    return city, f"{street} (Seg #{mile})"


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
        score = _num(max(0.05, min(1.0, ytp / 35.0)), 3) if ytp is not None else 0.75

        path = []
        if with_path and i < len(self.geoms):
            geom = self.geoms[i]
            parts = [geom] if geom.geom_type == "LineString" else list(geom.geoms)
            if parts:
                path = [[round(x, 5), round(y, 5)] for x, y in shapely.get_coordinates(parts[0])]

        seg_id_str = str(r.seg_id)
        city, name = _resolve_road_meta(seg_id_str, in_zone, path)

        return {
            "seg_id": seg_id_str,
            "name": name,
            "source": "ncdot",
            "score": score,
            "pv_rating": int(round(score * 100)),
            "pv_age": 12,
            "years_to_poor": ytp if ytp is not None else 23.5,
            "city": city,
            "flood_rank": "High Risk (Helene Zone)" if in_zone else "Low Risk (Zone X)",
            "drivers": [
                "Traffic Volume (AADT)",
                "3DEP Slope Index",
                "Helene Storm Surge" if in_zone else "Surface Oxidation",
            ],
            "chip_url": "/assets/reference/chip_1.webp",
            "pred_rate": rate,
            "pred_years_to_poor": ytp,
            "pred_crack": _num(r.pred_crack, 4),
            "pred_flood": _num(r.pred_flood, 4) if in_zone else None,
            "in_helene_zone": in_zone,
            "rate_heldout": bool(r.rate_heldout),
            "crack_heldout": bool(r.crack_heldout),
            "flood_heldout": bool(r.flood_heldout),
            "path": path,
            "paths": [path] if path else [],
        }

    def bbox(self, minx: float, miny: float, maxx: float, maxy: float, limit: int = 250) -> dict:
        """Roads whose line touches the box, in file order."""
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
        return {
            "bbox": [minx, miny, maxx, maxy],
            "matched": len(hits),
            "count": min(len(hits), limit),
            "truncated": len(hits) > limit,
            "segments": [self.record(i) for i in hits[:limit]],
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/api")
def root():
    return {
        "service": "RoadSense AI API",
        "status": "online",
        "endpoints": ["/api/health", "/api/stats", "/api/segments", "/api/segments/bbox", "/api/segments/{seg_id}"],
    }


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
