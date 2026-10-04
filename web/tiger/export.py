"""The per-road risk file for map companies (end goal 2).

Usage:  python -m web.tiger.export [--out data/processed/export]
Writes: risk_roads.csv        one row per state road, sorted by seg_id; an empty field means unknown or not scored
        risk_dictionary.json  what each column means, and what the file cannot claim

One writer (`iter_risk_csv`) produces both this file and the service's download, so the two are byte-identical.
This module imports only the standard library at the top, so the service can use the writer without pandas.
"""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path

# (column in the file, column in the road table, what it is, unit)
RISK_COLUMNS = [
    ("seg_id", "seg_id", "Road segment id: ncdot:{route id}:{begin milepost}", ""),
    ("route_id", "route_id", "NCDOT route id with the county code", ""),
    ("route", "route", "NCDOT route code", ""),
    ("county", "county", "County the segment is in", ""),
    ("beg_mp", "beg_mp", "Begin milepost along the route", "miles"),
    ("end_mp", "end_mp", "End milepost along the route", "miles"),
    ("from_desc", "from_desc", "Where the segment starts, as NCDOT describes it", ""),
    ("to_desc", "to_desc", "Where the segment ends, as NCDOT describes it", ""),
    ("length_mi", "length_mi", "Segment length", "miles"),
    ("mid_lon", "mid_lon", "Longitude of the segment's midpoint (WGS 84)", "degrees"),
    ("mid_lat", "mid_lat", "Latitude of the segment's midpoint (WGS 84)", "degrees"),
    ("rating", "rating", "NCDOT pavement rating at the last survey; below 60 is Poor", "0 to 100"),
    ("survey_year", "survey_year", "Year of that survey", "year"),
    ("wear_rate_pred", "pred_rate", "Predicted rating points lost per year", "points per year"),
    ("wear_rate_heldout", "rate_heldout", "true when that prediction came from a model that never saw this road", "true/false"),
    ("years_to_poor", "pred_years_to_poor", "Predicted years until the rating reaches Poor; 0 means already there; capped at 50", "years"),
    ("repair_bucket", "repair_bucket", "fix_now, within_1y, within_5y, later, or unknown when there is no forecast", ""),
    ("crack_risk", "pred_crack", "Predicted chance of cracking on more than 10% of the road", "0 to 1"),
    ("crack_heldout", "crack_heldout", "true when that prediction came from a model that never saw this road", "true/false"),
    ("flood_risk", "pred_flood", "Predicted chance of flood damage in a Helene-like storm; empty outside the Helene zone", "0 to 1"),
    ("flood_scored", "flood_scored", "true inside the Helene zone, the only place flood risk is scored", "true/false"),
    ("flood_heldout", "flood_heldout", "true when that prediction came from a model that never saw this road", "true/false"),
]
HEADER = [c[0] for c in RISK_COLUMNS]
SOURCE_COLUMNS = [c[1] for c in RISK_COLUMNS]
FILE_NAME = "risk_roads.csv"
CAMERA_FLAG_CAVEAT = ("A camera flag is a signal to check, not a confirmed flood. Cameras pan and zoom. On cameras the reader "
                      "had never seen, 85% of its flags were right, and it wrongly flagged 9 of 1,191 NCDOT stills taken on dry roads.")
CAVEATS = [
    "Only state roads are scored. City streets are not in this data.",
    "A blank years-to-Poor means unknown, not zero: the rating is missing or older than the last resurfacing.",
    "Flood risk is scored only inside the Hurricane Helene zone and was learned from that one storm.",
    "A prediction marked held-out came from a model that never saw that road; the others are optimistic.",
    CAMERA_FLAG_CAVEAT,
    "Wear per year is rating lost divided by pavement age from one survey, not a measured trend.",
    "Traffic is an estimate where marked. NCDOT's treatment cost has no documented unit.",
    "Charlotte pothole report times can be up to five hours off.",
]


def format_value(v):
    """One cell as text. Blank is an empty field, never 0 or 'nan'. Floats are rounded to 6 decimals."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return ""
        return repr(round(v, 6))
    return str(v)


def iter_risk_csv(rows, batch=2000):
    """Encoded chunks of the file: the header, then `batch` rows at a time. `rows` are tuples in RISK_COLUMNS order."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADER)
    pending = 0
    for row in rows:
        if len(row) != len(HEADER):
            raise ValueError(f"a risk row has {len(row)} values, not {len(HEADER)}")
        writer.writerow([format_value(v) for v in row])
        pending += 1
        if pending >= batch:
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)
            pending = 0
    if buf.tell():
        yield buf.getvalue().encode("utf-8")


def write_risk_csv(rows, fh):
    """Write the file to a binary handle. Returns the number of bytes."""
    n = 0
    for chunk in iter_risk_csv(rows):
        fh.write(chunk)
        n += len(chunk)
    return n


def rows_from_frame(roads):
    """Tuples for the writer from the built road table, sorted by seg_id in plain string order."""
    from web.tiger.build import to_rows
    return to_rows(roads.sort_values("seg_id", key=lambda s: s.astype(object)), SOURCE_COLUMNS)


def dictionary():
    return {"file": FILE_NAME, "one_row_per": "state road segment", "sorted_by": "seg_id",
            "blank": "an empty field means unknown or not scored",
            "columns": [{"name": n, "description": d, "unit": u} for n, _, d, u in RISK_COLUMNS],
            "what_this_cannot_claim": CAVEATS}


def atomic(path, write):
    """Write to a temporary name, then rename. A failed write leaves nothing behind and the old file untouched."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        write(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def export(root, out_dir):
    """Build the road table from `root` and write both files into `out_dir`. Returns (rows, bytes, sha256)."""
    from web.tiger.build import build_roads
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    roads = build_roads(root)

    def write_csv(tmp):
        with open(tmp, "wb") as f:
            write_risk_csv(rows_from_frame(roads), f)
    atomic(out_dir / FILE_NAME, write_csv)
    atomic(out_dir / "risk_dictionary.json", lambda tmp: Path(tmp).write_text(json.dumps(dictionary(), indent=2) + "\n"))
    data = (out_dir / FILE_NAME).read_bytes()
    return len(roads), len(data), hashlib.sha256(data).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the per-road risk file.")
    ap.add_argument("--out", default="data/processed/export", help="folder to write into")
    args = ap.parse_args(argv)
    rows, size, sha = export(Path("."), args.out)
    print(f"{args.out}/{FILE_NAME}: {rows:,} roads, {size:,} bytes, sha256 {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
