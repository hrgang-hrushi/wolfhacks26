"""The 10 m ground tiles: fetching, saving and reading (run spec D4-D6)."""
import numpy as np
import pytest
from rasterio.transform import Affine

import hd_helpers as H
from src.pipeline import helene_dem10 as dem
from src.pipeline import helene_depth as hd


def plane(lon, lat):
    return 100 + 1000 * (lon + 82.55) + 500 * (lat - 35.55)


def wavy(lon, lat):
    return 500 + 40 * np.sin(lon * 800) + 30 * np.cos(lat * 700)


def test_B1_a_planted_height_is_read_back_at_the_planted_spot(tmp_path):
    ground = H.mk_ground(tmp_path, plane, metric=False)
    lon, lat = -82.5512345, 35.5523456
    assert ground.sample(lon, lat)[0] == pytest.approx(plane(lon, lat), abs=1e-3)  # a swapped axis or half-cell shift fails
    # nearest: the value at the centre of the cell that holds the point
    w, _, _, n = dem.fetch_bounds(H.TILE)
    cx = w + (np.floor((lon - w) / dem.PX_DEG) + 0.5) * dem.PX_DEG
    cy = n - (np.floor((n - lat) / dem.PX_DEG) + 0.5) * dem.PX_DEG
    near = ground.sample(lon, lat, method="nearest")[0]
    assert near == pytest.approx(plane(cx, cy), abs=1e-3) and abs(near - plane(lon, lat)) > 1e-3
    assert np.isnan(ground.sample(np.nan, lat)[0])


def test_B2_a_point_on_the_seam_reads_the_same_from_either_tile(tmp_path):
    ground = H.mk_ground(tmp_path, wavy, tiles=(H.TILE, H.TILE_E), metric=False)
    lon, lat = np.array([-82.5, -82.5]), np.array([35.5437, 35.5912])
    west, east = ground.sample(lon, lat, tile=H.TILE), ground.sample(lon, lat, tile=H.TILE_E)
    assert np.all(np.isfinite(west)) and west == pytest.approx(east, abs=1e-3)
    assert ground.sample(lon, lat) == pytest.approx(west, abs=1e-3)


def test_B3_a_no_data_cell_gives_blank_ground(tmp_path):
    def blank_one(arr):
        arr[500, 500] = np.nan

    ground = H.mk_ground(tmp_path, plane, metric=False, edit=blank_one)
    w, _, _, n = dem.fetch_bounds(H.TILE)
    lon, lat = w + 500.9 * dem.PX_DEG, n - 500.9 * dem.PX_DEG  # its four cells include the blank one
    assert np.isnan(ground.sample(lon, lat)[0])
    far = ground.sample(lon + 2 * dem.PX_DEG, lat)[0]
    assert np.isfinite(far) and abs(far) < 1000  # never a huge number standing in for "no data"


def test_B4_a_missing_tile_stops_the_run_and_there_is_no_fallback_to_30m(tmp_path):
    p = hd.paths(tmp_path)
    ground = H.mk_ground(p.tiles, plane, metric=False)
    H.mk_dem30(p.dem30, lambda x, y: 600.0)  # the 30 m ground is right there, and must not be used
    lon, lat = H.ll(6000, 0)  # in the next tile east, which was never fetched
    with pytest.raises(dem.MissingTile, match=r"t_\+0355_-0825\.tif"):
        ground.sample(lon, lat)
    with pytest.raises(dem.GroundError, match="helene_dem10"):
        dem.Ground(tmp_path / "nothing_here")


def test_B5_a_failed_download_leaves_no_partial_tile(tmp_path):
    with pytest.raises(RuntimeError, match="network dropped"):
        dem.pull([H.TILE, H.TILE_E], out=tmp_path, fetch=H.fake_fetch(plane, fail=[H.TILE_E], metric=False), workers=1)
    assert sorted(f.name for f in tmp_path.iterdir()) == ["manifest.json", dem.tile_name(H.TILE)]  # no .tmp either
    assert list(dem.load_manifest(tmp_path)["tiles"]) == [dem.tile_name(H.TILE)]
    # a second run fetches only what is missing
    assert dem.pull([H.TILE, H.TILE_E], out=tmp_path, fetch=H.fake_fetch(plane, metric=False), workers=1) == 1
    assert np.isfinite(dem.Ground(tmp_path).sample(*H.ll(6000, 0))[0])


def _coarse(tile):
    w, s, e, n = dem.fetch_bounds(tile)
    px = 1 / 3600  # a 30 m grid
    nx, ny = int(np.ceil((e - w) / px)) + 2, int(np.ceil((n - s) / px)) + 2
    return np.full((ny, nx), 600, dtype="float32"), Affine(px, 0, w - px, 0, -px, n + px)


def test_B6_a_tile_at_the_wrong_resolution_is_refused(tmp_path):
    arr, tr = _coarse(H.TILE)
    with pytest.raises(dem.GroundError, match="wrong resolution"):
        dem.check_reply(arr, tr, "EPSG:4269", H.TILE)
    manifest = dem.new_manifest()  # someone drops a 30 m file into the 10 m folder
    manifest["tiles"][dem.tile_name(H.TILE)] = dem.write_tile(tmp_path, H.TILE, arr, tr)
    dem.save_manifest(tmp_path, manifest)
    with pytest.raises(dem.GroundError, match="wrong resolution"):
        dem.Ground(tmp_path).sample(H.LON0, H.LAT0)


def test_B7_a_tile_that_does_not_match_its_fingerprint_is_refused(tmp_path):
    H.mk_ground(tmp_path, plane, metric=False)
    path = tmp_path / dem.tile_name(H.TILE)
    raw = bytearray(path.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    path.write_bytes(bytes(raw))
    with pytest.raises(dem.GroundError, match="does not match the manifest"):
        dem.Ground(tmp_path).sample(H.LON0, H.LAT0)


def test_B8_an_empty_or_all_blank_reply_stops_the_pull_and_writes_nothing(tmp_path):
    tr, lon, _ = H.tile_grid(dem.fetch_bounds(H.TILE))
    for reply in (np.zeros((0, 0), dtype="float32"), np.full(lon.shape, np.nan, dtype="float32")):
        with pytest.raises(dem.GroundError, match="empty reply|no ground"):
            dem.pull([H.TILE], out=tmp_path, fetch=lambda b, r=reply: (r, tr, "EPSG:4269"), workers=1)
    assert list(tmp_path.glob("t_*")) == []


def test_B9_the_unit_tripwire_fires_when_the_marks_are_left_in_feet(tmp_path):
    marks, _ = H.marks_from(tmp_path, [H.mark(i, 100 * i, 0, 600.0 + i) for i in range(5)])
    g10 = marks.wse_m.values - 1.0
    assert hd.tripwire(marks, g10) == pytest.approx(1.0)
    with pytest.raises(hd.DepthError, match="units or datum wrong"):
        hd.tripwire(marks.assign(wse_m=marks.wse_m / hd.FT), g10)  # someone forgot the conversion
    with pytest.raises(hd.DepthError, match="units or datum wrong"):
        hd.tripwire(marks, g10 + 10)  # or the ground is in another datum


def test_B10_only_tiles_that_hold_a_needed_point_are_requested():
    lon, lat = H.ll(np.array([-2000.0, 0.0, 1800.0]), np.array([0.0, 500.0, 2500.0]))
    assert dem.tiles_needed(lon, lat) == [H.TILE]  # no neighbour is added to be safe
    lon2, lat2 = H.ll(6000.0, 0.0)
    assert dem.tiles_needed(np.r_[lon, lon2, np.nan], np.r_[lat, lat2, np.nan]) == [H.TILE, H.TILE_E]
    assert dem.tile_name(H.TILE) == "t_+0355_-0826.tif"


def test_B11_a_road_running_into_a_second_tile_gets_that_tile(mini_root):
    # no mark lies in the eastern tile: it is needed only because a road that touches the stream runs on into it
    marks, _ = hd.load_marks(mini_root.p.marks)
    assert dem.tiles_needed(marks.lon.values, marks.lat.values) == [H.TILE]
    assert hd.needed_tiles(mini_root.root) == [H.TILE, H.TILE_E]
    hd.run(mini_root.root, say=lambda *_: None)  # builds with both tiles
    for f in mini_root.p.out.glob("flood_helene_depth*"):
        f.unlink()
    (mini_root.p.tiles / dem.tile_name(H.TILE_E)).unlink()
    with pytest.raises(dem.MissingTile, match=r"t_\+0355_-0825\.tif"):  # named, not silently dropped
        hd.run(mini_root.root, say=lambda *_: None)
    assert list(mini_root.p.out.glob("flood_helene_depth*")) == []


def test_B12_a_reply_for_the_wrong_place_or_grid_is_refused(tmp_path):
    arr, tr = H.tile_array(H.TILE, plane, metric=False)
    dem.check_reply(arr, tr, "EPSG:4269", H.TILE)  # the honest reply passes
    shifted = Affine(tr.a, 0, tr.c + 0.1, 0, tr.e, tr.f)
    with pytest.raises(dem.GroundError, match="does not cover"):
        dem.check_reply(arr, shifted, "EPSG:4269", H.TILE)
    with pytest.raises(dem.GroundError, match="expected EPSG:4269"):
        dem.check_reply(arr, tr, "EPSG:32119", H.TILE)
    with pytest.raises(dem.GroundError, match="rotated"):
        dem.check_reply(arr, Affine(tr.a, 1e-6, tr.c, 0, tr.e, tr.f), "EPSG:4269", H.TILE)
    with pytest.raises(dem.GroundError, match="does not cover"):
        dem.pull([H.TILE], out=tmp_path, fetch=lambda b: (arr, shifted, "EPSG:4269"), workers=1)
    assert list(tmp_path.glob("t_*")) == []
