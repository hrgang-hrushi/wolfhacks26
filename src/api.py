"""Unwatched Roads: a fast read-only API over handoff/predictions_geo.parquet.

Run with:
    uv run --with fastapi,uvicorn uvicorn src.api:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import math
from pathlib import Path

import shapely
from shapely import STRtree

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "handoff" / "predictions_geo.parquet"
if not DATA_PATH.exists():
    DATA_PATH = Path("handoff/predictions_geo.parquet")

MAX_LIMIT = 5000


def _num(v: float, nd: int) -> float | None:
    """Rounded float, or None for a missing value."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), nd)


class Store:
    """The handoff file in memory, with a spatial index over the road lines."""

    def __init__(self, path: Path = DATA_PATH) -> None:
        import geopandas as gpd

        if not path.exists():
            raise RuntimeError(f"handoff file not found at {path.resolve()}")
        g = gpd.read_parquet(path)
        self.df = g.drop(columns="geometry")
        self.geoms = g.geometry.to_numpy()
        self.tree = STRtree(self.geoms)

    def __len__(self) -> int:
        return len(self.df)

    def stats(self) -> dict:
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
        r = self.df.iloc[i]
        in_zone = bool(r.in_helene_zone)
        rec = {
            "seg_id": str(r.seg_id),
            "pred_rate": _num(r.pred_rate, 3),
            "pred_years_to_poor": _num(r.pred_years_to_poor, 2),
            "pred_crack": _num(r.pred_crack, 4),
            "pred_flood": _num(r.pred_flood, 4) if in_zone else None,
            "in_helene_zone": in_zone,
            "rate_heldout": bool(r.rate_heldout),
            "crack_heldout": bool(r.crack_heldout),
            "flood_heldout": bool(r.flood_heldout),
        }
        if with_path:
            geom = self.geoms[i]
            parts = [geom] if geom.geom_type == "LineString" else list(geom.geoms)
            rec["paths"] = [[[round(x, 5), round(y, 5)] for x, y in shapely.get_coordinates(p)] for p in parts]
        return rec

    def bbox(self, minx: float, miny: float, maxx: float, maxy: float, limit: int = 250) -> dict:
        """Roads whose line touches the box, in file order."""
        hits = sorted(int(i) for i in self.tree.query(shapely.box(minx, miny, maxx, maxy), predicate="intersects"))
        return {
            "bbox": [minx, miny, maxx, maxy],
            "matched": len(hits),
            "count": min(len(hits), limit),
            "truncated": len(hits) > limit,
            "segments": [self.record(i) for i in hits[:limit]],
        }

    def find(self, seg_id: str) -> dict | None:
        m = self.df.index[self.df.seg_id == seg_id]
        return self.record(int(m[0])) if len(m) else None


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def build_app():
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="RoadSense AI / Unwatched Roads API",
        description="Read-only predictions for 112,443 North Carolina state road segments.",
        version="2.0.0",
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

    @app.get("/api/health")
    def health():
        return {"status": "ok", "total_records": len(get_store())}

    @app.get("/api/stats")
    def stats():
        return get_store().stats()

    @app.get("/api/segments")
    def list_segments(limit: int = Query(250, ge=1, le=MAX_LIMIT)):
        store = get_store()
        n = min(len(store), limit)
        return {"total": len(store), "count": n, "segments": [store.record(i) for i in range(n)]}

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

    @app.get("/api/segments/{seg_id}")
    def segment(seg_id: str):
        rec = get_store().find(seg_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"segment {seg_id} not found")
        return rec

    return app


try:
    app = build_app()
except ImportError:
    app = None

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="127.0.0.1", port=8000)
