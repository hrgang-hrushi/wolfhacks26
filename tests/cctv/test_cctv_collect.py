"""The camera list and the still collector, against a fake server."""
import shutil
import subprocess
import sys
from datetime import timedelta

import pandas as pd
import pytest
import requests

from src.pipeline import cctv
from src.pipeline.arcgis_fetch import UA, ArcGISError

LAYER_ROW = {"CameraId": 1, "CameraStatus": "Active Streaming", "ImageStatus": "Recent", "Highway": "I-40",
             "County": "Wake", "LocationName": "x", "Latitude": 35.8, "Longitude": -78.6,
             "ImageUrl": "https://a.test/1.jpg"}


def run(fake, cams, tmp_path, handler, clock, round_id="r1", **kw):
    s = fake.Session(handler)
    kw.setdefault("pacer", cctv.Pacer(clock=clock.now, sleep=clock.sleep))
    kw.setdefault("disk_free", lambda: 50e9)
    new = cctv.collect_round(cams, tmp_path, round_id, session=s, now=lambda: fake.NOW, **kw)
    return new, s


def jpgs(tmp_path):
    return sorted(str(f.relative_to(tmp_path)) for f in tmp_path.rglob("*.jpg"))


def test_K1_short_camera_list_raises(fake):
    rows = [dict(LAYER_ROW, CameraId=i) for i in range(3)]
    with pytest.raises(ArcGISError, match="received 3 rows but the server counts 5"):
        cctv.list_cameras(fake.Session(fake.arcgis(rows, count=5)), sleep=lambda s: None)
    cams = cctv.list_cameras(fake.Session(fake.arcgis(rows)), sleep=lambda s: None)
    assert list(cams.columns) == list(cctv.FIELDS.values()) and len(cams) == 3


def test_K2_replies_that_are_not_images_are_not_saved(fake, tmp_path, clock):
    good = fake.jpeg(1)
    bodies = {1: b"<html>Service unavailable</html>" * 200, 2: b'{"message":"As of May 27, 2026 ..."}' * 100,
              3: b"", 4: good[:len(good) // 2], 5: good}   # 4 is a download cut off half way
    new, _ = run(fake, fake.cameras(5), tmp_path, lambda u, p: fake.image_resp(bodies[int(u.split("-")[1][0])]), clock)
    assert new.status.tolist() == ["not_image"] * 4 + ["ok"]
    assert jpgs(tmp_path) == [new.file.iloc[4]]


def test_K3_same_bytes_from_three_cameras_is_a_placeholder(fake, tmp_path, clock):
    card = fake.jpeg(7)
    new, _ = run(fake, fake.cameras(4), tmp_path,
                 lambda u, p: fake.image_resp(fake.jpeg(99) if "chan-4_" in u else card), clock)
    assert new.status.tolist() == ["placeholder"] * 3 + ["ok"]
    assert new.file.isna().tolist() == [True, True, True, False]
    assert jpgs(tmp_path) == [new.file.iloc[3]]


def test_K4_stale_image_is_flagged_and_not_saved(fake, tmp_path, clock):
    new, _ = run(fake, fake.cameras(1), tmp_path, lambda u, p: fake.image_resp(fake.jpeg(1), age_s=cctv.STALE_S + 1), clock)
    assert new.status.tolist() == ["stale"] and jpgs(tmp_path) == []
    new, _ = run(fake, fake.cameras(1), tmp_path, lambda u, p: fake.image_resp(fake.jpeg(1), age_s=cctv.STALE_S - 1), clock)
    assert new.status.tolist() == ["ok"]


def test_K5_only_cameras_marked_recent_are_fetched(fake, tmp_path, clock):
    cams = fake.cameras(4, image_status=["Recent", "Unavailable", "Stale", "Recent"])
    cams.loc[3, "image_url"] = None
    new, s = run(fake, cams, tmp_path, lambda u, p: fake.image_resp(fake.jpeg(1)), clock)
    assert [u for u, _, _ in s.calls] == ["https://a.test/snapshots/chan-1_l.jpg"] and len(new) == 1
    assert all(h == UA for _, _, h in s.calls)


def test_K6_one_request_a_second_per_server(fake, tmp_path, clock):
    def gaps(pacer):
        times = {}
        def handler(u, p):
            times.setdefault(u.split("/")[2], []).append(clock.now())
            return fake.image_resp(fake.jpeg(len(times["a.test"]) if "a.test" in u else 50))
        run(fake, fake.cameras(6, hosts=("a.test",)), tmp_path / str(pacer.gap), handler, clock, pacer=pacer)
        t = times["a.test"]
        return min(b - a for a, b in zip(t, t[1:]))
    assert gaps(cctv.Pacer(clock=clock.now, sleep=clock.sleep)) >= cctv.HOST_GAP_S
    assert gaps(cctv.Pacer(gap=0, clock=clock.now, sleep=clock.sleep)) == 0   # without the pacing the rule is broken


def test_K7_mostly_failing_round_stops_and_keeps_its_log(fake, tmp_path, clock):
    def handler(u, p):
        n = int(u.split("chan-")[1].split("_")[0])
        return fake.image_resp(fake.jpeg(n)) if n <= 10 else fake.Resp(status=503)
    with pytest.raises(RuntimeError, match="stopped: 30 of 40 requests failed"):
        run(fake, fake.cameras(60, hosts=("a.test",)), tmp_path, handler, clock)
    log = pd.read_parquet(tmp_path / "stills.parquet")
    assert len(log) == cctv.BREAKER_MIN                      # every attempt, and nothing after the stop
    assert log.status.value_counts().to_dict() == {"http_error": 30, "ok": 10}
    assert jpgs(tmp_path) == sorted(log.file.dropna())       # every saved file has a log row


def test_K8_failed_download_or_write_leaves_no_partial_file(fake, tmp_path, clock, monkeypatch):
    new, _ = run(fake, fake.cameras(1), tmp_path, lambda u, p: requests.ConnectionError("reset"), clock)
    assert new.status.tolist() == ["http_error"] and list(tmp_path.rglob("*.jpg*")) == []

    def boom(a, b):
        raise OSError("Operation timed out")
    monkeypatch.setattr(cctv.os, "replace", boom)
    with pytest.raises(OSError):   # the log write also fails here; the still itself must leave nothing behind
        run(fake, fake.cameras(1), tmp_path, lambda u, p: fake.image_resp(fake.jpeg(1)), clock, round_id="r2")
    assert list(tmp_path.rglob("*.jpg*")) == []


def test_K9_unchanged_image_is_not_saved_twice(fake, tmp_path, clock):
    handler = lambda u, p: fake.image_resp(fake.jpeg(3))
    run(fake, fake.cameras(1), tmp_path, handler, clock)
    new, _ = run(fake, fake.cameras(1), tmp_path, handler, clock, round_id="r2")
    assert new.status.tolist() == ["duplicate"] and len(jpgs(tmp_path)) == 1
    assert pd.read_parquet(tmp_path / "stills.parquet")["round"].tolist() == ["r1", "r2"]


def test_K10_file_name_is_the_images_own_time_in_utc(fake, tmp_path, clock):
    new, _ = run(fake, fake.cameras(1), tmp_path, lambda u, p: fake.image_resp(fake.jpeg(1), age_s=125), clock)
    when = fake.NOW - timedelta(seconds=125)
    assert new.file.tolist() == [f"1/{when:%Y%m%dT%H%M%SZ}.jpg"] == ["1/20261003T185755Z.jpg"]
    assert new.image_time.iloc[0] == when and not new.no_image_time.iloc[0]
    new, _ = run(fake, fake.cameras(1), tmp_path, lambda u, p: fake.Resp(body=fake.jpeg(2)), clock, round_id="r2")
    assert new.no_image_time.tolist() == [True] and new.file.iloc[0] == f"1/{fake.NOW:%Y%m%dT%H%M%SZ}.jpg"


def test_K11_dark_frame_is_flagged(fake, tmp_path, clock):
    bodies = {1: fake.jpeg(lo=0, hi=12), 2: fake.jpeg(lo=100, hi=140)}
    new, _ = run(fake, fake.cameras(2), tmp_path, lambda u, p: fake.image_resp(bodies[int(u.split("-")[1][0])]), clock)
    assert new.dark.tolist() == [True, False] and new.status.tolist() == ["ok", "ok"]


def test_K12_low_disk_space_refuses_to_start(fake, tmp_path, clock):
    with pytest.raises(RuntimeError, match="GB free"):
        s = fake.Session(lambda u, p: fake.image_resp(fake.jpeg(1)))
        cctv.collect_round(fake.cameras(2), tmp_path, "r1", session=s, disk_free=lambda: 1e9)
    assert s.calls == [] and not (tmp_path / "stills.parquet").exists()


def test_K13_git_ignores_stills(tmp_path):
    # checked in a scratch repo holding this repo's .gitignore: in a worktree data/raw is a link,
    # and git refuses to answer for paths beyond a link
    shutil.copy(".gitignore", tmp_path / ".gitignore")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for f in ("data/raw/cctv/1/20261003T185755Z.jpg", "data/raw/cctv/stills.parquet", "data/raw/cctv/grades.csv"):
        assert subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", f]).returncode == 0, f


def test_K14_help_runs():
    r = subprocess.run([sys.executable, "-m", "src.pipeline.cctv", "--help"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]


def test_K15_timer_mode_stops_and_survives_one_bad_camera(fake, tmp_path, clock):
    n = {"calls": 0}
    def handler(u, p):
        n["calls"] += 1
        return fake.Resp(status=500) if "chan-2_" in u else fake.image_resp(fake.jpeg(n["calls"]))
    cctv.run_collect(fake.cameras(3), tmp_path, rounds=3, every=300, sleep=clock.sleep, session=fake.Session(handler),
                     pacer=cctv.Pacer(clock=clock.now, sleep=clock.sleep), now=lambda: fake.NOW, disk_free=lambda: 50e9)
    log = pd.read_parquet(tmp_path / "stills.parquet")
    assert clock.sleeps.count(300) == 2 and log["round"].nunique() == 3 and len(log) == 9
    assert log.groupby("camera_id").status.agg(set).to_dict() == {1: {"ok"}, 2: {"http_error"}, 3: {"ok"}}


def test_K16_changed_bytes_with_the_same_image_time_never_overwrite(fake, tmp_path, clock):
    first, second = fake.jpeg(1), fake.jpeg(2)
    new1, _ = run(fake, fake.cameras(1), tmp_path, lambda u, p: fake.image_resp(first), clock)
    new2, _ = run(fake, fake.cameras(1), tmp_path, lambda u, p: fake.image_resp(second), clock, round_id="r2")
    assert new2.status.tolist() == ["ok"] and new1.file.iloc[0] != new2.file.iloc[0]
    assert (tmp_path / new1.file.iloc[0]).read_bytes() == first
    assert (tmp_path / new2.file.iloc[0]).read_bytes() == second
