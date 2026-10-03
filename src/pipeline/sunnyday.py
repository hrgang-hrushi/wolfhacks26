"""Pull Sunny Day Flooding Project roadside-camera frames and water levels (coastal NC).

    python -m src.pipeline.sunnyday                      # the Sept 24-28 2026 high-tide flood days
    python -m src.pipeline.sunnyday --days 2026-09-27    # one day
    python -m src.pipeline.sunnyday --index-only         # rebuild frames.parquet from what is on disk
    python -m src.pipeline.sunnyday --labels             # depth labels from what is on disk, no network
    python -m src.pipeline.sunnyday --pack               # labels + small frames + model code, zipped for Colab

Outputs
    data/raw/sunnyday/levels/{station}.json    water-level series from the public feed, as served
    data/raw/sunnyday/frames/{station}/{station}_{YYYY-MM-DDTHHMM}Z.jpg
    data/raw/sunnyday/frames.parquet           one row per saved frame with the nearest sensor level
    data/raw/sunnyday/labels.parquet           frames with depth_cm on the road; role cv | extra
    data/raw/sunnyday/flood_camera_colab.zip   --pack

The public feed keeps about two weeks, so older frames cannot be pulled again.
level_m is the station sensor in metres above NAVD88, not depth on the road: the feed carries no
road elevation. Frames exist only at minutes :06 :18 :30 :42 :54 and some slots are missing.
No licence is published for the images; keep them local.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "sunnyday"

FEED = "https://data.sunnydayflooding.com/services/data.php"
FRAME = "https://wl.secoora.org/webcam/SUNNYD_{sid}.{day}T{hh:02d}:{mm:02d}Z.jpg"
SLOT_MINUTES = (6, 18, 30, 42, 54)
DAYLIGHT_UTC = range(11, 23)  # about sunrise to sunset on the NC coast in late September
FLOOD_DAYS = ["2026-09-27", "2026-09-24", "2026-09-26", "2026-09-25", "2026-09-28"]  # peak day first
PAUSE = 1.0  # seconds between requests
MAX_LEVEL_GAP = pd.Timedelta("10min")

# Sensor level (m above NAVD88) at which water first stands on the lowest pavement in view.
# Read by eye off level-sorted frames from Sept 24-28 2026: good to about 0.05 m (DE_04: 0.10 m,
# it has no frames between 0.48 and 0.71). depth_cm is the depth at that lowest point.
ROAD_LEVEL_M = {
    "BF_01": 0.86, "CB_01": 0.73, "CB_01B": 0.73, "CB_02": 0.77, "CB_03": 0.97,
    "DE_03": 0.58, "DE_04": 0.68, "NB_01": 0.54, "NR_01": 0.80,
}
ALWAYS_DRY = {"DE_02", "NB_02"}  # sensor pinned at one value; the road is dry in every frame checked
LEVEL_FROM = {"CB_01B": "CB_01"}  # second camera at the same site, no sensor of its own
CCTV = ROOT / "data" / "raw" / "cctv"  # NCDOT traffic-camera stills, pulled by src.pipeline.cctv (branch cctv-potholes)
NCDOT_STILLS = CCTV / "look_2026-10-03_1435"  # rainy afternoon, no flood alerts
PACK_SIZE = 448

_session = requests.Session()
_session.headers["User-Agent"] = "UnwatchedRoads (NC State hackathon project; one request per second)"
_last = 0.0


def _get(url: str, params: dict | None = None, tries: int = 3) -> requests.Response:
    """One paced request. A 403 or 429 means stop, not retry."""
    global _last
    for attempt in range(tries):
        wait = PAUSE - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = _session.get(url, params=params, timeout=60)
        except requests.RequestException:
            _last = time.monotonic()
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
            continue
        _last = time.monotonic()
        if r.status_code in (403, 429):
            raise SystemExit(f"{r.status_code} from {r.url}; stopping")
        if r.status_code < 500 or attempt == tries - 1:
            return r
        time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def _write(path: Path, data: bytes) -> None:
    # ~/Desktop is iCloud-synced; write to a temp name and rename
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    tmp.write_bytes(data)
    tmp.replace(path)


def camera_stations() -> list[str]:
    """Station ids (BF_01, ...) that currently publish camera frames."""
    r = _get(FEED, {"format": "json", "time": "latest", "standard": "f"})
    r.raise_for_status()
    out = []
    for f in r.json()["features"]:
        p = f["properties"]
        if any(q["id"] == "webcam_img_url" and q["observations"]["times"] for q in p["parameters"]):
            out.append(p["platform_id"].removeprefix("SUNNYD_"))
    return out


def pull_levels(sid: str, days: list[str]) -> None:
    span = f"{min(days)}T00:00:00/{max(days)}T23:59:59"
    r = _get(FEED, {"format": "json", "time": span, "platform": f"sunnyd_{sid.lower()}", "standard": "true"})
    r.raise_for_status()
    _write(OUT / "levels" / f"{sid}.json", r.content)


def pull_frames(sid: str, day: str, overwrite: bool = False) -> tuple[int, int]:
    saved = missing = 0
    for hh in DAYLIGHT_UTC:
        for mm in SLOT_MINUTES:
            path = OUT / "frames" / sid / f"{sid}_{day}T{hh:02d}{mm:02d}Z.jpg"
            if path.exists() and not overwrite:
                saved += 1
                continue
            r = _get(FRAME.format(sid=sid, day=day, hh=hh, mm=mm))
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image"):
                _write(path, r.content)
                saved += 1
            else:
                missing += 1
    return saved, missing


def read_station(sid: str) -> tuple[dict, pd.DataFrame]:
    """Station name and position, plus its own unfiltered sensor series.

    The feed's other water_level series are the filtered sensor and nearby NOAA gauges.
    """
    levels = pd.DataFrame({"level_time": pd.Series(dtype="datetime64[ns]"), "level_m": pd.Series(dtype=float)})
    path = OUT / "levels" / f"{sid}.json"
    feats = json.loads(path.read_text()).get("features") if path.exists() else None
    if not feats:
        return {}, levels
    p = feats[0]["properties"]
    lon, lat = feats[0]["geometry"]["coordinates"]
    meta = {"name": p["platform_short_name"], "lat": lat, "lon": lon}
    for q in p["parameters"]:
        if q["id"] == "water_level_raw" and q["observations"]["times"]:
            o = q["observations"]
            levels = pd.DataFrame(
                {
                    "level_time": pd.to_datetime(o["times"]).astype("datetime64[ns]"),
                    "level_m": pd.to_numeric(pd.Series(o["values"]), errors="coerce"),
                }
            ).dropna().sort_values("level_time")
            break
    return meta, levels


def build_index() -> pd.DataFrame:
    parts = []
    for d in sorted((OUT / "frames").glob("*")):
        files = sorted(d.glob("*.jpg"))
        if not files:
            continue
        times = pd.to_datetime([f.stem.rsplit("_", 1)[-1] for f in files], format="%Y-%m-%dT%H%MZ")
        frames = pd.DataFrame(
            {
                "station": d.name,
                "time_utc": times.astype("datetime64[ns]"),
                "file": [str(f.relative_to(OUT)) for f in files],
            }
        ).sort_values("time_utc")
        meta, levels = read_station(d.name)
        if d.name in LEVEL_FROM:
            levels = read_station(LEVEL_FROM[d.name])[1]
        frames = pd.merge_asof(
            frames, levels, left_on="time_utc", right_on="level_time", direction="nearest", tolerance=MAX_LEVEL_GAP
        )
        parts.append(frames.assign(**meta))
    index = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if len(index):
        tmp = OUT / "frames.partial.parquet"
        index.to_parquet(tmp, index=False)
        tmp.replace(OUT / "frames.parquet")
    return index


def build_labels() -> pd.DataFrame:
    """Depth on the road per frame, plus the NCDOT stills as known-dry rows that are never trained on."""
    cv = build_index()
    road = cv["station"].map(ROAD_LEVEL_M)
    cv["depth_cm"] = ((cv["level_m"] - road) * 100).clip(lower=0)
    cv.loc[cv["station"].isin(ALWAYS_DRY), "depth_cm"] = 0.0
    cv = cv.dropna(subset=["depth_cm"]).assign(road_m=road, role="cv")
    cv["site"] = cv["station"].replace(LEVEL_FROM)  # cameras at one site are held out together

    parts = [cv]
    log = NCDOT_STILLS / "log.json"
    if log.exists():
        rows = [r for r in json.loads(log.read_text()) if r.get("ok") and (NCDOT_STILLS / f"{r['CameraId']}.jpg").exists()]
        parts.append(
            pd.DataFrame(
                {
                    "station": "NCDOT",
                    "site": [f"NCDOT_{r['CameraId']}" for r in rows],
                    "time_utc": pd.to_datetime([r["last_modified"] for r in rows], format="%a, %d %b %Y %H:%M:%S GMT")
                    .astype("datetime64[ns]"),
                    "file": [f"../cctv/{NCDOT_STILLS.name}/{r['CameraId']}.jpg" for r in rows],
                    "name": [r["LocationName"] for r in rows],
                    "lat": [r["Latitude"] for r in rows],
                    "lon": [r["Longitude"] for r in rows],
                    "depth_cm": 0.0,
                    "role": "extra",
                }
            )
        )
    if (CCTV / "stills.parquet").exists():  # collector rounds; a camera's view can change between rounds
        st = pd.read_parquet(CCTV / "stills.parquet")
        st = st[(st["status"] == "ok") & ~st["dark"]].merge(pd.read_parquet(CCTV / "cameras.parquet"), on="camera_id")
        parts.append(
            pd.DataFrame(
                {
                    "station": "NCDOT",
                    "site": "NCDOT_" + st["camera_id"].astype(str),
                    "time_utc": st["image_time"].dt.tz_localize(None).astype("datetime64[ns]"),
                    "file": "../cctv/" + st["file"],
                    "name": st["location_name"],
                    "lat": st["lat"],
                    "lon": st["lon"],
                    "depth_cm": 0.0,
                    "role": "extra",
                }
            )
        )
    labels = pd.concat(parts, ignore_index=True)
    tmp = OUT / "labels.partial.parquet"
    labels.to_parquet(tmp, index=False)
    tmp.replace(OUT / "labels.parquet")
    return labels


def pack_colab() -> Path:
    """One zip a Colab session can train from: labels, frames shrunk to the model's input size, model code."""
    import io
    import zipfile

    from PIL import Image

    labels = build_labels()
    path = OUT / "flood_camera_colab.zip"
    tmp = path.with_name(path.name + ".partial")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
        files = []
        for f in labels["file"]:
            name = "extra/ncdot/" + "_".join(Path(f).parts[-2:]) if f.startswith("../") else f
            buf = io.BytesIO()
            Image.open(OUT / f).convert("RGB").resize((PACK_SIZE, PACK_SIZE), Image.BILINEAR).save(buf, "JPEG", quality=88)
            z.writestr(f"sunnyday/{name}", buf.getvalue())
            files.append(name)
        buf = io.BytesIO()
        labels.assign(file=files).to_parquet(buf, index=False)
        z.writestr("sunnyday/labels.parquet", buf.getvalue())
        for src in ("src/__init__.py", "src/model/__init__.py", "src/model/flood_camera.py"):
            z.write(ROOT / src, src)
    tmp.replace(path)
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", nargs="+", default=FLOOD_DAYS, help="UTC dates, pulled in the order given")
    ap.add_argument("--stations", nargs="+", help="station ids such as BF_01 (default: every station with a camera)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--index-only", action="store_true")
    ap.add_argument("--labels", action="store_true")
    ap.add_argument("--pack", action="store_true")
    args = ap.parse_args()

    if args.labels or args.pack:
        labels = build_labels()
        cv = labels[labels["role"] == "cv"]
        flooded = cv[cv["depth_cm"] >= 2].groupby("station")["depth_cm"].agg(["size", "max"]).round(0)
        print(f"labels.parquet: {len(cv)} camera frames, {int((cv['depth_cm'] >= 2).sum())} flooded, "
              f"{int((labels['role'] == 'extra').sum())} NCDOT stills taken as not flooded", flush=True)
        print(cv.groupby("station").size().rename("frames").to_frame().join(flooded).fillna(0).astype(int)
              .rename(columns={"size": "flooded", "max": "deepest_cm"}).to_string(), flush=True)
        if args.pack:
            path = pack_colab()
            print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1e6:.0f} MB", flush=True)
        return

    if not args.index_only:
        sids = args.stations or camera_stations()
        print(f"{len(sids)} stations: {' '.join(sids)}", flush=True)
        for sid in sids:
            pull_levels(sid, args.days)
        for day in args.days:
            for sid in sids:
                saved, missing = pull_frames(sid, day, args.overwrite)
                print(f"{day} {sid}: {saved} frames, {missing} slots missing", flush=True)
            build_index()  # a stopped run still leaves a usable index

    index = build_index()
    with_level = int(index["level_m"].notna().sum()) if len(index) else 0
    print(f"frames.parquet: {len(index)} frames, {with_level} with a sensor level", flush=True)


if __name__ == "__main__":
    main()
