"""NCDOT traffic cameras: list them, tie each to a road segment, save stills.

Usage:  uv run python -m src.pipeline.cctv list
        uv run python -m src.pipeline.cctv collect --rounds 1 [--every 300] [--limit N]
Reads:  data/raw/ncdot_joined.parquet           (seg_id, ROUTE, geometry)
Writes: data/raw/cctv/cameras.parquet           one row per camera, with its seg_id
        data/raw/cctv/{camera_id}/{time}.jpg    stills, named by the image's own time (UTC)
        data/raw/cctv/stills.parquet            one row per attempt

Stills can show vehicles. data/raw is git-ignored: keep them on this machine.
"""
import argparse
import hashlib
import io
import os
import re
import shutil
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely
from PIL import Image

from src.model.common import write_atomic
from src.pipeline.arcgis_fetch import UA, fetch_all

RAW = Path("data/raw")
OUT = RAW / "cctv"
CRS_M = "EPSG:32119"  # NAD83 / North Carolina (meters)
LAYER = "https://services.arcgis.com/NuWFvHYDMVmmxMeM/ArcGIS/rest/services/NCDOT_Cameras/FeatureServer/0"
FIELDS = {"CameraId": "camera_id", "CameraStatus": "status", "ImageStatus": "image_status", "Highway": "highway",
          "County": "county", "LocationName": "location_name", "Latitude": "lat", "Longitude": "lon",
          "ImageUrl": "image_url"}
CAMERA_COLS = list(FIELDS.values()) + ["seg_id", "seg_dist_m", "match_rule"]
LOG_COLS = ["camera_id", "round", "file", "image_time", "fetched", "bytes", "sha1", "width", "height",
            "mean_luma", "status", "dark", "no_image_time"]
MAX_M = 100            # a camera further than this from every state road gets no segment
STALE_S = 900          # an image older than this is not a current view
MIN_BYTES = 2000
DARK_LUMA = 40         # mean brightness (0-255) below this is a night frame
HOST_GAP_S = 1.0       # at most one request per second to each image server
MIN_FREE_GB = 2
BREAKER_MIN, BREAKER_SHARE = 40, 0.5   # stop a round when the servers mostly refuse
PLACEHOLDER_CAMERAS = 3                # the same bytes from this many cameras is a "no image" card
ROUTE_CLASS = {"I": "1", "US": "2", "NC": "3"}


# ---- camera list and segment match ----
def list_cameras(session=None, sleep=time.sleep):
    rows = fetch_all(LAYER, "1=1", list(FIELDS), geometry=False, page=1000, session=session, sleep=sleep)
    cams = pd.DataFrame(rows)[list(FIELDS)].rename(columns=FIELDS)
    if cams.camera_id.isna().any() or cams.camera_id.duplicated().any():
        raise ValueError("camera list: camera_id has nulls or duplicates")
    return cams


def parse_highway(name):
    """("1", 40) for "I-40"; None for names that are not an Interstate, US or NC route."""
    m = re.match(r"^\s*(I|US|NC)[- ]?(\d+)", str(name), flags=re.I)
    return (ROUTE_CLASS[m.group(1).upper()], int(m.group(2))) if m else None


def match_cameras(cams, segs, max_m=MAX_M):
    """Add seg_id, seg_dist_m and match_rule. A camera named for a route prefers a segment of that
    route within max_m over a nearer cross street."""
    cams = cams.drop(columns=["seg_id", "seg_dist_m", "match_rule"], errors="ignore")
    ok = cams.lat.notna() & cams.lon.notna()
    pts = gpd.GeoDataFrame(cams.loc[ok, ["camera_id", "highway"]],
                           geometry=gpd.points_from_xy(cams.lon[ok], cams.lat[ok]), crs="EPSG:4326").to_crs(CRS_M)
    s = segs[["seg_id", "ROUTE", "geometry"]].to_crs(CRS_M).reset_index(drop=True)
    hit = gpd.sjoin(pts, s, predicate="dwithin", distance=max_m, how="inner")
    hit["seg_dist_m"] = shapely.distance(hit.geometry.values, s.geometry.values[hit.index_right.values])
    want = hit.highway.map(parse_highway)
    hit["on_route"] = [w is not None and r[:1] == w[0] and r[3:8].isdigit() and int(r[3:8]) == w[1]
                       for w, r in zip(want, hit.ROUTE.astype(str))]
    best = (hit.sort_values(["camera_id", "on_route", "seg_dist_m", "seg_id"], ascending=[True, False, True, True])
            .drop_duplicates("camera_id"))
    best["match_rule"] = np.where(best.on_route, "route", "nearest")
    out = cams.merge(best[["camera_id", "seg_id", "seg_dist_m", "match_rule"]], on="camera_id", how="left")
    print(f"{len(out):,} cameras: {out.seg_id.notna().sum():,} matched within {max_m} m "
          f"({(out.match_rule == 'route').sum():,} by route name, {(out.match_rule == 'nearest').sum():,} by nearest), "
          f"{out.seg_id.isna().sum():,} unmatched")
    return out[CAMERA_COLS]


def write_cameras(cams, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, cams[CAMERA_COLS].to_parquet)


# ---- stills ----
class Pacer:
    """At most one request per `gap` seconds to each host."""

    def __init__(self, gap=HOST_GAP_S, clock=time.monotonic, sleep=time.sleep):
        self.gap, self.clock, self.sleep, self.last = gap, clock, sleep, {}

    def wait(self, host):
        due = self.last.get(host, float("-inf")) + self.gap
        if self.clock() < due:
            self.sleep(due - self.clock())
        self.last[host] = self.clock()


def check_image(body):
    """(ok, width, height, mean_luma). A web page, a notice, an empty body or a cut-off JPEG is not ok."""
    if len(body) < MIN_BYTES or body[:2] != b"\xff\xd8" or body[-2:] != b"\xff\xd9":
        return False, None, None, None
    try:
        im = Image.open(io.BytesIO(body))
        luma = float(np.asarray(im.convert("L").resize((64, 36))).mean())  # decoding fails on a cut-off file
    except Exception:
        return False, None, None, None
    return True, im.width, im.height, luma


def image_time(headers, now):
    """The image's own time from Last-Modified (UTC), or (now, True) when the server gives none."""
    try:
        t = parsedate_to_datetime(headers.get("Last-Modified"))
        return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc), False
    except (TypeError, ValueError):
        return now, True


def read_log(out_dir):
    f = Path(out_dir) / "stills.parquet"
    return pd.read_parquet(f) if f.exists() else pd.DataFrame(columns=LOG_COLS)


def _save(out_dir, camera_id, when, body, sha1):
    """Write the still under its image time. An existing file is never replaced."""
    d = Path(out_dir) / str(camera_id)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{when:%Y%m%dT%H%M%SZ}.jpg"
    if f.exists():
        f = d / f"{when:%Y%m%dT%H%M%SZ}_{sha1[:8]}.jpg"
        if f.exists():  # these exact bytes are already on disk
            return f"{camera_id}/{f.name}"
    tmp = f.with_name(f.name + ".tmp")
    try:
        tmp.write_bytes(body)
        os.replace(tmp, f)
    finally:
        tmp.unlink(missing_ok=True)
    return f"{camera_id}/{f.name}"


def collect_round(cams, out_dir, round_id, *, session=None, pacer=None, now=None, disk_free=None):
    """Fetch one still per camera whose image is marked recent. Every attempt is logged, also when
    the round is stopped because the servers mostly refuse."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()
    pacer = pacer or Pacer()
    now = now or (lambda: datetime.now(timezone.utc))
    free = (disk_free or (lambda: shutil.disk_usage(out_dir).free))()
    if free < MIN_FREE_GB * 1e9:
        raise RuntimeError(f"only {free / 1e9:.1f} GB free; need {MIN_FREE_GB} GB to collect stills")

    log = read_log(out_dir)
    last = log[log.status == "ok"].drop_duplicates("camera_id", keep="last").set_index("camera_id").sha1.to_dict()
    todo = cams[(cams.image_status == "Recent") & cams.image_url.notna()].copy()
    todo["host"] = todo.image_url.map(lambda u: urlparse(u).netloc)
    todo = todo.iloc[np.argsort(todo.groupby("host").cumcount().values, kind="stable")]  # take turns between servers

    rows, failed, stopped = [], 0, False
    for c in todo.itertuples():
        row = dict.fromkeys(LOG_COLS)
        row.update(camera_id=c.camera_id, round=round_id, dark=False, no_image_time=False)
        pacer.wait(c.host)
        row["fetched"] = now()
        try:
            r = session.get(c.image_url, headers=UA, timeout=20)
            body = r.content if r.status_code == 200 else None
        except requests.RequestException:
            body = None
        if body is None:
            row["status"] = "http_error"
        else:
            ok, w, h, luma = check_image(body)
            when, no_time = image_time(r.headers, row["fetched"])
            sha1 = hashlib.sha1(body).hexdigest()
            row.update(bytes=len(body), sha1=sha1, width=w, height=h, mean_luma=luma, image_time=when,
                       no_image_time=no_time)
            if not ok:
                row["status"] = "not_image"
            elif (row["fetched"] - when).total_seconds() > STALE_S:
                row["status"] = "stale"
            elif last.get(c.camera_id) == sha1:
                row["status"] = "duplicate"
            else:
                try:
                    row.update(status="ok", dark=bool(luma < DARK_LUMA),
                               file=_save(out_dir, c.camera_id, when, body, sha1))
                except OSError:
                    row["status"] = "save_error"
        rows.append(row)
        failed += row["status"] in ("http_error", "not_image", "save_error")
        if len(rows) >= BREAKER_MIN and failed / len(rows) > BREAKER_SHARE:
            stopped = True
            break

    new = pd.DataFrame(rows, columns=LOG_COLS)
    for c in ("image_time", "fetched"):
        new[c] = pd.to_datetime(new[c], utc=True)
    for c in ("dark", "no_image_time"):
        new[c] = new[c].astype(bool)
    saved = new[new.status == "ok"]
    shared = saved.groupby("sha1").camera_id.nunique()
    card = new.status.eq("ok") & new.sha1.isin(shared[shared >= PLACEHOLDER_CAMERAS].index)
    for f in new.loc[card, "file"]:  # only files this round wrote
        (out_dir / f).unlink(missing_ok=True)
    new.loc[card, ["status", "file"]] = ["placeholder", None]
    full = new if log.empty else pd.concat([log, new], ignore_index=True)
    write_atomic(out_dir / "stills.parquet", full.to_parquet)
    print(f"round {round_id}: {new.status.value_counts().to_dict()}, {int(new.dark.sum())} dark", flush=True)
    if stopped:
        raise RuntimeError(f"round {round_id} stopped: {failed} of {len(rows)} requests failed; "
                           "the image servers may be refusing, so try again later")
    return new


def run_collect(cams, out_dir, rounds, every, sleep=time.sleep, **kw):
    for i in range(rounds):
        collect_round(cams, out_dir, f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{i:02d}", **kw)
        if i < rounds - 1:
            sleep(every)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="pull the camera list and match cameras to segments")
    c = sub.add_parser("collect", help="save one still per recent camera, per round")
    c.add_argument("--rounds", type=int, default=1)
    c.add_argument("--every", type=float, default=300, help="seconds between rounds")
    c.add_argument("--limit", type=int, help="only the first N cameras (for a trial)")
    a = ap.parse_args()

    if a.cmd == "list":
        cams = list_cameras()
        print(f"{len(cams):,} cameras, {(cams.image_status == 'Recent').sum():,} with a recent image")
        segs = gpd.read_parquet(RAW / "ncdot_joined.parquet", columns=["seg_id", "ROUTE", "geometry"])
        write_cameras(match_cameras(cams, segs), OUT / "cameras.parquet")
        print("saved", OUT / "cameras.parquet")
    else:
        cams = pd.read_parquet(OUT / "cameras.parquet")
        run_collect(cams.head(a.limit) if a.limit else cams, OUT, a.rounds, a.every)


if __name__ == "__main__":
    main()
