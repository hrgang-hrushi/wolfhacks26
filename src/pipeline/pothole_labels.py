"""Label each state road segment with the pothole reports that fall on it.

Usage:  uv run python -m src.pipeline.pothole_labels
Reads:  data/raw/ncdot_joined.parquet          (seg_id, YEAR_LAST_REHAB, LineString, EPSG:4326)
        data/raw/pothole_reports.parquet, city_limits.parquet, pothole_reports.meta.json
Writes: data/processed/pothole_labels.parquet  (no geometry; one row per seg_id, same order)

Columns:
  pothole_city            "charlotte" / "raleigh" when the segment's midpoint is inside the city, else null.
                          Outside a city nobody was collecting reports: a zero there means "not recorded".
  pothole_exposure_years  how long the segment's current pavement has been watched
  n_pothole_reports       reports matched to the segment, received while the current pavement was watched
  n_pothole_cdot/_ncdot/_raleigh   the same count per report type
  n_pothole_all_time      every matched report, whatever its date
  y_pothole_rate          reports per mile per year (blank without length or exposure)
  y_pothole_any           1.0 / 0.0 inside a city with exposure, blank otherwise
"""
import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from src.model.common import write_atomic
from src.pipeline.pull_potholes import read_bundle

RAW = Path("data/raw")
PROCESSED = Path("data/processed")
CRS_M = "EPSG:32119"  # NAD83 / North Carolina (meters)
# Raleigh's points sit on the street, so PLAN.md's 30 m holds. Charlotte's are address locations: its
# state-road requests sit a median 44 m from the centreline and 30 m kept only 173 of 902 (2026-10-03).
MATCH_M = {"charlotte": 60, "raleigh": 30}
M_PER_MILE = 1609.344
# Charlotte's reports go back to 2016; the pavement surveys are 2023-2025. Raleigh's data starts in May 2025.
WINDOW_START = {"charlotte": pd.Timestamp("2023-01-01"), "raleigh": pd.Timestamp("2025-05-01")}
TYPE_COL = {"CDOT POTHOLE REPAIR": "n_pothole_cdot", "NCDOT POTHOLE REQUEST": "n_pothole_ncdot",
            "Pothole": "n_pothole_raleigh"}
LABEL_COLS = ["seg_id", "pothole_city", "pothole_exposure_years", "n_pothole_reports", "n_pothole_cdot",
              "n_pothole_ncdot", "n_pothole_raleigh", "n_pothole_all_time", "y_pothole_rate", "y_pothole_any"]


def assign_city(segs_m, limits_m):
    """City containing each segment's midpoint (the midpoint rule of chips.py and features.py), else None."""
    if limits_m is None or len(limits_m) == 0:
        raise ValueError("no city limits: refusing to treat every segment as covered")
    mid = shapely.line_interpolate_point(segs_m.geometry.values, 0.5, normalized=True)
    pts = gpd.GeoDataFrame({"pos": np.arange(len(segs_m))}, geometry=mid, crs=segs_m.crs)
    hit = gpd.sjoin(pts, limits_m[["city", "geometry"]], predicate="within", how="left").drop_duplicates("pos").sort_values("pos")
    return np.array([c if isinstance(c, str) else None for c in hit.city], dtype=object)


def match_reports(reports_m, segs_m):
    """Each report's single nearest segment within its source's match distance. Further reports are left out."""
    parts = [gpd.sjoin_nearest(g[["report_id", "geometry"]], segs_m[["seg_id", "geometry"]],
                               max_distance=MATCH_M[source], distance_col="dist_m")
             for source, g in reports_m.groupby("source")]
    j = pd.concat(parts) if parts else pd.DataFrame(columns=["report_id", "seg_id", "dist_m"])
    return j.sort_values(["report_id", "dist_m", "seg_id"]).drop_duplicates("report_id")[["report_id", "seg_id", "dist_m"]]


def exposure_start(city, rehab_year):
    """The later of the city's window start and 1 January of the year after the last rehab.
    The rehab year is only known to the year, so reports in that year may predate the new surface."""
    win = pd.to_datetime(pd.Series(city, dtype=object).map(WINDOW_START))
    yr = pd.to_numeric(pd.Series(np.asarray(rehab_year)), errors="coerce")
    after = pd.to_datetime((yr + 1).astype("Int64").astype(str) + "-01-01", errors="coerce")
    return win.where(after.isna() | (after <= win), after).where(win.notna())


def build_labels(segs_m, matched, reports, city, pulled_at):
    """One row per segment, in the order of segs_m (seg_id, YEAR_LAST_REHAB, geometry in CRS_M)."""
    if segs_m.seg_id.isna().any() or segs_m.seg_id.duplicated().any():
        raise ValueError("segments: seg_id has nulls or duplicates")
    unknown = sorted(set(matched.seg_id) - set(segs_m.seg_id))
    if unknown:
        raise ValueError(f"{len(unknown)} matched seg_id values are not in the segment table, e.g. {unknown[:3]}")
    pulled_at = pd.Timestamp(pulled_at)
    out = pd.DataFrame({"seg_id": segs_m.seg_id.values, "pothole_city": city})
    start = exposure_start(city, segs_m.YEAR_LAST_REHAB.values)
    out["pothole_exposure_years"] = ((pulled_at - start).dt.days / 365.25).clip(lower=0)
    length_m = segs_m.geometry.length.values  # features.py convention: length of the EPSG:32119 geometry

    m = (matched.merge(reports[["report_id", "request_type", "received_date"]], on="report_id", validate="one_to_one")
         .merge(pd.DataFrame({"seg_id": out.seg_id, "start": start.values}), on="seg_id"))
    watched = m[(m.received_date >= m.start) & (m.received_date <= pulled_at)]

    def per_segment(rows):
        return out.seg_id.map(rows.groupby("seg_id").size()).fillna(0).astype("int32")

    out["n_pothole_reports"] = per_segment(watched)
    for kind, col in TYPE_COL.items():
        out[col] = per_segment(watched[watched.request_type == kind])
    out["n_pothole_all_time"] = per_segment(m)
    mile_years = length_m / M_PER_MILE * out.pothole_exposure_years
    covered = out.pothole_city.notna() & (out.pothole_exposure_years > 0)
    out["y_pothole_rate"] = (out.n_pothole_reports / mile_years.where(mile_years > 0)).where(covered)
    out["y_pothole_any"] = (out.n_pothole_reports > 0).astype(float).where(covered)
    return out[LABEL_COLS]


def main(raw=RAW, processed=PROCESSED):
    raw, processed = Path(raw), Path(processed)
    reports, limits, meta = read_bundle(raw)
    segs = gpd.read_parquet(raw / "ncdot_joined.parquet", columns=["seg_id", "YEAR_LAST_REHAB", "geometry"]).to_crs(CRS_M)
    city = assign_city(segs, limits.to_crs(CRS_M))
    matched = match_reports(reports.to_crs(CRS_M), segs)
    print(f"{len(reports):,} located reports, {len(matched):,} matched to a state road within {MATCH_M} m "
          f"({len(matched) / max(len(reports), 1):.1%})")
    by = reports.merge(matched, on="report_id", how="left").assign(hit=lambda d: d.seg_id.notna())
    print(by.groupby(["source", "request_type"]).hit.agg(["size", "sum"]).rename(
        columns={"size": "reports", "sum": "matched"}).to_string())

    lab = build_labels(segs, matched, reports, city, meta["pulled_at"])
    processed.mkdir(parents=True, exist_ok=True)
    write_atomic(processed / "pothole_labels.parquet", lab.to_parquet)
    for c in WINDOW_START:
        z = lab[lab.pothole_city == c]
        print(f"{c}: {len(z):,} segments in the city, {z.y_pothole_any.notna().sum():,} labelled, "
              f"{int(z.y_pothole_any.sum()):,} with a report ({z.y_pothole_any.mean():.1%}), "
              f"{int(z.n_pothole_reports.sum()):,} reports counted")
    print("saved", processed / "pothole_labels.parquet", lab.shape)


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    main()
