"""The augmentation toolbox (src/model/augment.py). Test ids A1 to A32 follow the run spec."""

import glob
import itertools
import warnings

import numpy as np
import pytest
import torch

from src.model import augment as A
from vision_helpers import REAL_CHIPS, lopsided_chip


def distinct_views(chip):
    return len({A.view(chip, k).tobytes() for k in range(8)})


def marker_chip():
    """Zeros with three different corner values, so every symmetry gives a different corner layout."""
    c = np.zeros((4, 128, 128), dtype=np.uint8)
    c[:, 0, 0], c[:, 0, -1], c[:, -1, 0] = 10, 20, 30
    return c


def corners(c):
    return (int(c[0, 0, 0]), int(c[0, 0, -1]), int(c[0, -1, 0]), int(c[0, -1, -1]))


# ---------------------------------------------------------------- the 8 views

def test_a1_the_eight_views_are_pairwise_different(chip):
    assert distinct_views(chip) == 8


def test_a2_the_same_check_finds_one_view_on_a_constant_chip():
    assert distinct_views(np.full((4, 128, 128), 77, dtype=np.uint8)) == 1


@pytest.mark.parametrize("k", range(8))
def test_a3_a4_views_keep_shape_type_and_each_bands_pixels(chip, k):
    v = A.view(chip, k)
    assert v.shape == (4, 128, 128) and v.dtype == np.uint8
    for band in range(4):
        assert np.array_equal(np.sort(v[band], axis=None), np.sort(chip[band], axis=None))


def test_a5_corner_markers_land_in_the_eight_expected_arrangements():
    got = {corners(A.view(marker_chip(), k)) for k in range(8)}
    tl, tr, bl, br = 10, 20, 30, 0
    expected = {(tl, tr, bl, br), (tr, br, tl, bl), (br, bl, tr, tl), (bl, tl, br, tr),   # the 4 turns
                (tr, tl, br, bl), (bl, br, tl, tr), (tl, bl, tr, br), (br, tr, bl, tl)}   # the 4 mirror images
    assert got == expected and len(expected) == 8
    assert corners(A.view(marker_chip(), 0)) == (tl, tr, bl, br)
    assert corners(A.view(marker_chip(), 4)) == (tr, tl, br, bl)  # left-right flip
    assert corners(A.view(marker_chip(), 6)) == (bl, br, tl, tr)  # up-down flip
    assert corners(A.view(marker_chip(), 2)) == (br, bl, tr, tl)  # half turn


@pytest.mark.parametrize("k", range(8))
def test_a6_inverse_view_restores_the_original(chip, k):
    assert np.array_equal(A.inverse_view(A.view(chip, k), k), chip)


def test_a7_no_operation_modifies_its_input(chip):
    before = chip.copy()
    for k in range(8):
        A.view(chip, k)
        A.inverse_view(chip, k)
    A.gain(chip, 1.1), A.contrast(chip, 0.85), A.shift(chip, 3, -2), A.ndvi(chip), A.ndvi_stats(chip)
    for preset in A.PRESETS.values():
        A.random_augment(chip, A.sample_rng(0, 0, 0), preset)
    assert np.array_equal(chip, before)


@pytest.mark.parametrize("op", [lambda c: A.view(c, 0), lambda c: A.view(c, 3), lambda c: A.view(c, 5),
                                lambda c: A.inverse_view(c, 0), lambda c: A.gain(c, 1.0),
                                lambda c: A.contrast(c, 1.0), lambda c: A.shift(c, 0, 0), lambda c: A.shift(c, 2, 1)])
def test_a8_transforms_return_a_new_owned_contiguous_array(chip, op):
    out = op(chip)
    assert out is not chip and not np.shares_memory(out, chip)
    assert out.flags["C_CONTIGUOUS"] and out.flags["OWNDATA"]
    assert torch.from_numpy(out).shape == (4, 128, 128)


@pytest.mark.parametrize("k", [-1, 8, 2.0, "1", None, True])
def test_a9_a_view_id_outside_0_to_7_raises(chip, k):
    with pytest.raises(ValueError):
        A.view(chip, k)
    with pytest.raises(ValueError):
        A.inverse_view(chip, k)


# ---------------------------------------------------------------- brightness and contrast

def all_band_gain_ok(original, changed, tol=0.02):
    """The A10 check: NDVI on unsaturated pixels moves by less than tol."""
    keep = (changed[A.NIR] < 255) & (changed[A.RED] < 255) & (original[A.NIR] > 30) & (original[A.RED] > 30)
    return float(np.abs(A.ndvi(changed) - A.ndvi(original))[keep].max()) < tol


@pytest.mark.parametrize("g", [0.8, 0.9, 1.1, 1.15])
def test_a10_gain_scales_all_bands_alike_and_keeps_ndvi(chip, g):
    out = A.gain(chip, g)
    unsat = out < 255
    for band in range(4):
        m = unsat[band]
        assert np.abs(out[band][m].astype(float) - chip[band][m] * g).max() <= 0.5 + 1e-4  # rounding only
    assert all_band_gain_ok(chip, out)


def test_a11_a_per_band_gain_fails_the_same_check(chip):
    wrong = chip.copy()
    wrong[A.NIR] = np.clip(np.rint(chip[A.NIR] * 1.2), 0, 255).astype(np.uint8)  # brightens one band only
    assert not all_band_gain_ok(chip, wrong)


def test_a12_brightening_never_wraps_around():
    bright = np.full((4, 128, 128), 250, dtype=np.uint8)
    assert (A.gain(bright, 1.15) == 255).all()  # 287.5 saturates; uint8 arithmetic would give 31
    chip = lopsided_chip(3)
    assert (A.gain(chip, 1.15) >= chip).all() and (A.gain(chip, 0.8) <= chip).all()
    assert (A.contrast(chip, 1.25).astype(int) >= 0).all()
    dark_bright = np.zeros((4, 128, 128), dtype=np.uint8)
    dark_bright[:, :, 64:] = 255
    out = A.contrast(dark_bright, 1.25)
    assert (out[:, :, :64] == 0).all() and (out[:, :, 64:] == 255).all()  # clipped, not wrapped


@pytest.mark.parametrize("g", [0.79, 1.16, 1.25, 0.0, -1.0, 2.0])
def test_a13_gain_outside_its_range_raises(chip, g):
    with pytest.raises(ValueError, match="gain"):
        A.gain(chip, g)


def test_a14_strongest_gain_saturates_under_two_percent_of_real_pixels():
    files = sorted(glob.glob(str(REAL_CHIPS / "*.npy")))[:50]
    if not files:
        pytest.skip("no real chips in data/chips")
    chips = np.stack([np.load(f) for f in files])
    assert chips.shape[1:] == (4, 128, 128) and chips.dtype == np.uint8
    newly = np.mean([((A.gain(c, A.GAIN_RANGE[1]) == 255) & (c < 255)).mean() for c in chips])
    assert newly < 0.02, f"{newly:.3%} of pixels newly saturated"
    per_band = np.mean([((A.gain(c, A.GAIN_RANGE[1]) == 255) & (c < 255)).mean(axis=(1, 2)) for c in chips], axis=0)
    assert per_band.max() < 0.02, f"a band saturates: {per_band}"  # at 1.25 the NIR band lost 20%
    both = np.mean([((A.contrast(A.gain(c, 1 + A.FULL.gain), 1 + A.FULL.contrast) == 255) & (c < 255)).mean()
                    for c in chips])
    assert both < 0.02, f"{both:.3%} newly saturated at FULL's strongest gain and contrast together"
    both_band = np.mean([((A.contrast(A.gain(c, 1 + A.FULL.gain), 1 + A.FULL.contrast) == 255) & (c < 255)).mean(axis=(1, 2))
                         for c in chips], axis=0)
    assert both_band.max() < 0.02, f"a band saturates at FULL's strongest draw: {both_band}"


def test_a15_identity_settings_return_an_equal_array(chip):
    assert np.array_equal(A.gain(chip, 1.0), chip)
    assert np.array_equal(A.contrast(chip, 1.0), chip)
    assert np.array_equal(A.shift(chip, 0, 0), chip)
    assert np.array_equal(A.view(chip, 0), chip)


def test_a16_contrast_uses_one_grey_level_for_all_bands():
    const = np.full((4, 128, 128), 90, dtype=np.uint8)
    assert np.array_equal(A.contrast(const, 1.25), const)
    chip = np.zeros((4, 128, 128), dtype=np.uint8)
    chip[0], chip[1], chip[2], chip[3] = 40, 80, 120, 160  # grey level is 100 for every band
    out = A.contrast(chip, 1.2)
    assert [int(out[b, 0, 0]) for b in range(4)] == [28, 76, 124, 172]  # each band stretched around 100


@pytest.mark.parametrize("c", [0.79, 1.26, 0.0, 3.0])
def test_a17_contrast_outside_its_range_raises(chip, c):
    with pytest.raises(ValueError, match="contrast"):
        A.contrast(chip, c)


# ---------------------------------------------------------------- shifts

@pytest.mark.parametrize("dx,dy", [(3, 0), (0, 2), (-4, 1), (4, -4), (-1, -3)])
def test_a18_a_marker_moves_by_exactly_dx_dy_in_all_bands(dx, dy):
    chip = np.zeros((4, 128, 128), dtype=np.uint8)
    chip[:, 60, 70] = [50, 100, 150, 200]  # row 60, column 70
    out = A.shift(chip, dx, dy)
    assert [int(v) for v in out[:, 60 + dy, 70 + dx]] == [50, 100, 150, 200]
    assert int((out > 0).sum()) == 4  # nothing else appeared


def test_a19_the_exposed_strip_repeats_the_edge_not_the_far_side():
    chip = np.zeros((4, 128, 128), dtype=np.uint8)
    chip[:, :, 0] = 200    # left edge bright
    chip[:, :, -1] = 90    # right edge different
    out = A.shift(chip, 3, 0)  # move right: columns 0..2 are exposed
    assert (out[:, :, :3] == 200).all()      # the left edge repeated
    assert (out[:, :, 3] == 200).all()       # the original edge column, moved
    assert not (out[:, :, :3] == 90).any()   # the right edge did not wrap in
    chip2 = np.zeros((4, 128, 128), dtype=np.uint8)
    chip2[:, -1, :] = 60
    assert not (A.shift(chip2, 0, 2)[:, :2, :] == 60).any()  # bottom row did not wrap to the top


@pytest.mark.parametrize("dx,dy", [(5, 0), (0, -5), (9, 9), (-5, 4), (4, 5)])
def test_a20_a_shift_above_four_pixels_raises(chip, dx, dy):
    with pytest.raises(ValueError, match="exceeds"):
        A.shift(chip, dx, dy)


@pytest.mark.parametrize("dx,dy", [(2.9, 0), (0, 1.0), (True, 0), ("1", 0), (None, 0)])
def test_a20b_a_shift_that_is_not_whole_pixels_raises(chip, dx, dy):
    with pytest.raises(ValueError, match="whole pixels"):  # 2.9 must not silently become 2
        A.shift(chip, dx, dy)
    assert np.array_equal(A.shift(chip, np.int64(3), np.int32(-4)), A.shift(chip, 3, -4))  # numpy integers are fine
    assert np.array_equal(A.shift(chip, 4, -4)[:, :-4, 4:], chip[:, 4:, :-4])              # the limits, both signs


# ---------------------------------------------------------------- NDVI

def band_chip(r, g, b, nir):
    c = np.zeros((4, 128, 128), dtype=np.uint8)
    c[0], c[1], c[2], c[3] = r, g, b, nir
    return c


def test_a21_ndvi_of_red_50_nir_150_is_one_half():
    v = A.ndvi(band_chip(50, 1, 2, 150))
    assert v.dtype == np.float32 and v.shape == (128, 128)
    assert np.allclose(v, 0.5)


def test_a22_ndvi_uses_band_3_and_band_0(chip):
    nir, red = chip[3].astype(np.float64), chip[0].astype(np.float64)
    assert np.allclose(A.ndvi(chip), (nir - red) / (nir + red), atol=1e-6)
    for i, j in itertools.permutations(range(4), 2):
        if (i, j) == (3, 0):
            continue
        a, b = chip[i].astype(np.float64), chip[j].astype(np.float64)
        other = np.divide(a - b, a + b, out=np.zeros_like(a), where=(a + b) > 0)
        assert not np.allclose(A.ndvi(chip), other, atol=1e-3), f"NDVI matches bands ({i},{j})"
    assert (A.NIR, A.RED) == (3, 0)


def test_a23_all_zero_pixels_give_zero_without_a_warning():
    chip = band_chip(0, 0, 0, 0)
    chip[:, :10, :10] = 100
    with warnings.catch_warnings(), np.errstate(all="raise"):
        warnings.simplefilter("error")
        v = A.ndvi(chip)
    assert np.isfinite(v).all() and (v[20:, 20:] == 0).all()


def test_a24_red_above_nir_is_negative_and_values_stay_in_range():
    assert np.allclose(A.ndvi(band_chip(20, 0, 0, 10)), -1 / 3)  # uint8 10 - 20 would wrap to 246
    rng = np.random.default_rng(1)
    v = A.ndvi(rng.integers(0, 256, size=(4, 128, 128), dtype=np.uint8))
    assert v.min() >= -1.0 and v.max() <= 1.0


def test_a25_ndvi_stats_keys_and_ranges(chip):
    s = A.ndvi_stats(chip)
    assert set(s) == {"im_ndvi_mean", "im_ndvi_std", "im_impervious_frac", "im_bright_var"}
    assert all(isinstance(v, float) for v in s.values())
    assert -1 <= s["im_ndvi_mean"] <= 1 and s["im_ndvi_std"] >= 0 and s["im_bright_var"] >= 0
    veg = A.ndvi_stats(band_chip(50, 0, 0, 150))
    paved = A.ndvi_stats(band_chip(100, 0, 0, 100))
    assert veg["im_impervious_frac"] == 0.0 and paved["im_impervious_frac"] == 1.0


# ---------------------------------------------------------------- randomness and presets

def draw(chip, seed, epoch, index, preset=A.FULL):
    return A.random_augment(chip, A.sample_rng(seed, epoch, index), preset)


def test_a26_same_seed_epoch_index_gives_the_same_output(chip):
    a, ra = draw(chip, 7, 2, 31)
    b, rb = draw(chip, 7, 2, 31)
    assert np.array_equal(a, b) and ra == rb


def test_a27_another_index_or_epoch_gives_another_output(chip):
    base, _ = draw(chip, 7, 2, 31)
    diff_index = sum(not np.array_equal(base, draw(chip, 7, 2, i)[0]) for i in range(100, 150))
    diff_epoch = sum(not np.array_equal(base, draw(chip, 7, e, 31)[0]) for e in range(10, 60))
    diff_seed = sum(not np.array_equal(base, draw(chip, s, 2, 31)[0]) for s in range(100, 150))
    assert diff_index >= 49 and diff_epoch >= 49 and diff_seed >= 49


def test_a28_global_random_state_has_no_effect(chip):
    np.random.seed(1)
    a, _ = draw(chip, 3, 0, 5)
    np.random.seed(999)
    np.random.rand(1000)
    b, _ = draw(chip, 3, 0, 5)
    assert np.array_equal(a, b)
    state = np.random.get_state()[1].copy()
    draw(chip, 3, 0, 6)
    assert np.array_equal(np.random.get_state()[1], state)  # and it does not consume it either


def test_a29_view_choice_presets_and_the_none_fast_path(chip):
    counts = np.bincount([draw(chip, 0, 0, i)[1]["view"] for i in range(800)], minlength=8)
    assert (counts >= 60).all() and (counts <= 140).all(), counts
    flips = {draw(chip, 0, 0, i, A.FLIPS)[1]["view"] for i in range(400)}
    assert flips == {0, 2, 4, 6}
    for i in range(50):
        out, rec = draw(chip, 0, 0, i, A.FLIPS)
        assert rec["dx"] == rec["dy"] == 0 and rec["gain"] == 1.0 and rec["contrast"] == 1.0
        assert out is not chip  # FLIPS always returns a new array, even for view 0
        assert np.array_equal(out, A.view(chip, rec["view"]))
    out, rec = draw(chip, 0, 0, 0, A.NONE)
    assert out is chip and rec["n_ops"] == 0  # the one documented fast path


def test_a29b_flips_matches_independent_left_right_and_up_down_flips(chip):
    made = {A.view(chip, k).tobytes() for k in A.FLIPS.view_ids}
    by_hand = {chip.tobytes(), chip[:, :, ::-1].tobytes(), chip[:, ::-1, :].tobytes(), chip[:, ::-1, ::-1].tobytes()}
    assert made == by_hand  # exactly what train_vit.py's two coin-flip flips can produce


def test_a30_the_allowed_operations_are_pinned():
    assert A.ALLOWED_OPS == ("view", "shift", "gain", "contrast")
    assert set(A.PRESETS) == {"none", "flips", "full"}
    fields = set(A.Preset.__dataclass_fields__)
    assert fields == {"name", "view_ids", "gain", "contrast", "shift"}
    banned = ("hue", "saturat", "mixup", "cutmix", "erase", "erasing", "randaug", "jitter", "solariz", "posteriz")
    names = [n.lower() for n in dir(A)]
    assert not [n for n in names if any(b in n for b in banned)]
    assert (A.FULL.gain, A.FULL.contrast, A.FULL.shift, A.FULL.view_ids) == (0.10, 0.10, 4, tuple(range(8)))
    assert A.MAX_SHIFT == 4 and A.GAIN_RANGE == (0.8, 1.15) and A.CONTRAST_RANGE == (0.8, 1.25)


@pytest.mark.parametrize("bad", [
    {"gain": 0.3}, {"contrast": 0.3}, {"shift": 5}, {"view_ids": (0, 8)},
])
def test_a30b_a_preset_outside_the_limits_cannot_be_built(bad):
    kwargs = dict(name="x", view_ids=(0,), gain=0.0, contrast=0.0, shift=0)
    kwargs.update(bad)
    with pytest.raises(ValueError):
        A.Preset(**kwargs)


@pytest.mark.parametrize("bad", [
    np.zeros((3, 128, 128), dtype=np.uint8),       # three bands
    np.zeros((128, 128, 4), dtype=np.uint8),       # bands last
    np.zeros((4, 128, 128), dtype=np.float32),     # decimals
    np.zeros((4, 128, 100), dtype=np.uint8),       # not square
    np.zeros((4, 128), dtype=np.uint8),            # wrong rank
    [[1, 2], [3, 4]],                              # not an array
])
def test_a31_wrong_inputs_raise(bad):
    for fn in (lambda c: A.view(c, 1), lambda c: A.gain(c, 1.1), lambda c: A.contrast(c, 1.1),
               lambda c: A.shift(c, 1, 1), A.ndvi, A.ndvi_stats, A.all_views,
               lambda c: A.random_augment(c, A.sample_rng(0, 0, 0), A.FULL),
               lambda c: A.random_augment(c, A.sample_rng(0, 0, 0), A.NONE)):
        with pytest.raises(ValueError):
            fn(bad)


def test_a32_full_changes_the_chip_and_records_what_it_did(chip):
    changed = 0
    for i in range(200):
        out, rec = draw(chip, 1, 0, i)
        assert out.shape == chip.shape and out.dtype == np.uint8
        assert set(rec) == {"view", "dx", "dy", "gain", "contrast", "n_ops"}
        assert 0 <= rec["view"] <= 7 and abs(rec["dx"]) <= 4 and abs(rec["dy"]) <= 4
        assert 0.9 <= rec["gain"] <= 1.1 and 0.9 <= rec["contrast"] <= 1.1
        expected = A.contrast(A.gain(A.shift(A.view(chip, rec["view"]), rec["dx"], rec["dy"]), rec["gain"]),
                              rec["contrast"])
        assert np.array_equal(out, expected)  # the record reproduces the output: view, shift, gain, contrast
        applied = (rec["view"] != 0) + (rec["dx"] != 0 or rec["dy"] != 0) + (rec["gain"] != 1.0) + (rec["contrast"] != 1.0)
        assert rec["n_ops"] == applied
        changed += not np.array_equal(out, chip)
    assert changed >= 190


def test_all_views_stacks_the_eight(chip):
    stack = A.all_views(chip)
    assert stack.shape == (8, 4, 128, 128) and stack.dtype == np.uint8
    assert all(np.array_equal(stack[k], A.view(chip, k)) for k in range(8))
