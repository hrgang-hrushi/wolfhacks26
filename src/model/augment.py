"""Augmentation for the 4-band NAIP chips cut by src.pipeline.chips.

A chip is uint8, shape (4, 128, 128), bands R, G, B, NIR. Everything here treats the four bands
together, so the red to near-infrared relationship that NDVI depends on survives:

    view(chip, k)          the 8 symmetries of a square (flips and quarter turns)
    gain(chip, g)          one brightness multiplier for all bands
    contrast(chip, c)      one stretch for all bands around a shared grey level
    shift(chip, dx, dy)    whole-pixel move, edge repeated
    ndvi(chip)             (NIR - red) / (NIR + red), always taken from the ORIGINAL chip

random_augment draws one combination from a preset (NONE, FLIPS, FULL) using only the generator it
is given; sample_rng keys that generator by (seed, epoch, index) so a run repeats exactly whatever
the number of loader workers. Colour-space tricks and sample mixing are deliberately absent: the
road is about 12 px wide, one target is a continuous number, and NIR has no hue.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

N_VIEWS = 8
MAX_SHIFT = 4
GAIN_RANGE = (0.8, 1.15)  # 1.25 washed out 6% of pixels (20% of NIR) in real chips; 1.15 is 0.3%
CONTRAST_RANGE = (0.8, 1.25)
ALLOWED_OPS = ("view", "shift", "gain", "contrast")
RED, NIR = 0, 3


def check_chip(chip) -> None:
    if not isinstance(chip, np.ndarray) or chip.dtype != np.uint8:
        raise ValueError(f"chip must be a uint8 array, got {type(chip).__name__} {getattr(chip, 'dtype', '')}")
    if chip.ndim != 3 or chip.shape[0] != 4 or chip.shape[1] != chip.shape[2]:
        raise ValueError(f"chip must be (4, H, H) with bands first, got {chip.shape}")


def _check_k(k) -> int:
    if not isinstance(k, (int, np.integer)) or isinstance(k, bool) or not 0 <= k < N_VIEWS:
        raise ValueError(f"view id must be an integer 0..{N_VIEWS - 1}, got {k!r}")
    return int(k)


def view(chip: np.ndarray, k: int) -> np.ndarray:
    """Symmetry k of the chip: k < 4 is k quarter turns; k >= 4 is a left-right flip, then k - 4 quarter turns."""
    check_chip(chip)
    k = _check_k(k)
    x = chip[:, :, ::-1] if k >= 4 else chip
    return np.array(np.rot90(x, k % 4, axes=(1, 2)), order="C", copy=True)


def inverse_view(chip: np.ndarray, k: int) -> np.ndarray:
    """Undo view(chip, k)."""
    check_chip(chip)
    k = _check_k(k)
    x = np.rot90(chip, -(k % 4), axes=(1, 2))
    if k >= 4:
        x = x[:, :, ::-1]
    return np.array(x, order="C", copy=True)


def all_views(chip: np.ndarray) -> np.ndarray:
    """The 8 views stacked: (8, 4, H, H)."""
    return np.stack([view(chip, k) for k in range(N_VIEWS)])


def _to_u8(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(x), 0, 255).astype(np.uint8)


def _check_range(value: float, allowed, name: str) -> float:
    if not allowed[0] - 1e-9 <= value <= allowed[1] + 1e-9:
        raise ValueError(f"{name} {value} is outside the allowed range {allowed}")
    return float(value)


def gain(chip: np.ndarray, g: float) -> np.ndarray:
    """Multiply all four bands by the same g. Saturates at 255; never wraps."""
    check_chip(chip)
    g = _check_range(g, GAIN_RANGE, "gain")
    return _to_u8(chip.astype(np.float32) * np.float32(g))


def contrast(chip: np.ndarray, c: float) -> np.ndarray:
    """Stretch all four bands by c around one grey level, the mean over all bands."""
    check_chip(chip)
    c = _check_range(c, CONTRAST_RANGE, "contrast")
    grey = np.float32(chip.mean())
    return _to_u8((chip.astype(np.float32) - grey) * np.float32(c) + grey)


def shift(chip: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Move the picture dx pixels right and dy pixels down, all bands together. The exposed strip repeats the edge."""
    check_chip(chip)
    for v in (dx, dy):
        if not isinstance(v, (int, np.integer)) or isinstance(v, bool):
            raise ValueError(f"shift must be whole pixels, got {v!r}")
    if abs(dx) > MAX_SHIFT or abs(dy) > MAX_SHIFT:
        raise ValueError(f"shift ({dx}, {dy}) exceeds {MAX_SHIFT} px")
    dx, dy, m = int(dx), int(dy), MAX_SHIFT
    h, w = chip.shape[1:]
    padded = np.pad(chip, ((0, 0), (m, m), (m, m)), mode="edge")
    return np.array(padded[:, m - dy:m - dy + h, m - dx:m - dx + w], order="C", copy=True)


def ndvi(chip: np.ndarray) -> np.ndarray:
    """(NIR - red) / (NIR + red) per pixel as float32; 0 where both bands are 0."""
    check_chip(chip)
    nir, red = chip[NIR].astype(np.float32), chip[RED].astype(np.float32)
    total = nir + red
    return np.divide(nir - red, total, out=np.zeros_like(total), where=total > 0)


def ndvi_stats(chip: np.ndarray) -> dict:
    """The cheap per-chip image features named in PLAN.md section 2."""
    v = ndvi(chip)
    brightness = chip[:3].astype(np.float32).mean(axis=0)
    return {"im_ndvi_mean": float(v.mean()), "im_ndvi_std": float(v.std()),
            "im_impervious_frac": float((v < 0.1).mean()), "im_bright_var": float(brightness.var())}


@dataclass(frozen=True)
class Preset:
    name: str
    view_ids: tuple  # views to draw from, uniformly
    gain: float      # brightness multiplier drawn from 1 +/- gain
    contrast: float  # contrast multiplier drawn from 1 +/- contrast
    shift: int       # shift drawn from -shift..shift px on each axis

    def __post_init__(self):
        for k in self.view_ids:
            _check_k(k)
        _check_range(1 - self.gain, GAIN_RANGE, "gain")
        _check_range(1 + self.gain, GAIN_RANGE, "gain")
        _check_range(1 - self.contrast, CONTRAST_RANGE, "contrast")
        _check_range(1 + self.contrast, CONTRAST_RANGE, "contrast")
        if not 0 <= self.shift <= MAX_SHIFT:
            raise ValueError(f"preset shift {self.shift} exceeds {MAX_SHIFT} px")

    @property
    def is_identity(self) -> bool:
        return tuple(self.view_ids) == (0,) and self.gain == 0 and self.contrast == 0 and self.shift == 0


NONE = Preset("none", (0,), 0.0, 0.0, 0)
FLIPS = Preset("flips", (0, 2, 4, 6), 0.0, 0.0, 0)  # the 4 results of independent left-right and up-down flips
# +/-10% each: at +/-15% each, the strongest draw washed out 3% of real pixels (11% of NIR); at 10% it is 0.2%
FULL = Preset("full", tuple(range(N_VIEWS)), 0.10, 0.10, MAX_SHIFT)
PRESETS = {p.name: p for p in (NONE, FLIPS, FULL)}


def sample_rng(seed: int, epoch: int, index: int) -> np.random.Generator:
    """The generator for one sample in one epoch. Independent of worker count and of global random state."""
    return np.random.default_rng([int(seed), int(epoch), int(index)])


def random_augment(chip: np.ndarray, rng: np.random.Generator, preset: Preset):
    """One random draw from the preset. Returns (chip, record); record['n_ops'] counts non-identity changes.

    An identity preset (NONE) is the one fast path: it returns the input object itself. Every other
    preset returns a new array, even when the draw happens to change nothing.
    """
    check_chip(chip)
    if preset.is_identity:
        return chip, {"view": 0, "dx": 0, "dy": 0, "gain": 1.0, "contrast": 1.0, "n_ops": 0}
    k = int(preset.view_ids[int(rng.integers(len(preset.view_ids)))])
    dx, dy = (int(v) for v in rng.integers(-preset.shift, preset.shift + 1, size=2)) if preset.shift else (0, 0)
    g = 1.0 + float(rng.uniform(-preset.gain, preset.gain)) if preset.gain else 1.0
    c = 1.0 + float(rng.uniform(-preset.contrast, preset.contrast)) if preset.contrast else 1.0
    out, n_ops = chip, 0
    if k:
        out, n_ops = view(out, k), n_ops + 1
    if dx or dy:
        out, n_ops = shift(out, dx, dy), n_ops + 1
    if g != 1.0:
        out, n_ops = gain(out, g), n_ops + 1
    if c != 1.0:
        out, n_ops = contrast(out, c), n_ops + 1
    if out is chip:
        out = chip.copy()
    return out, {"view": k, "dx": dx, "dy": dy, "gain": g, "contrast": c, "n_ops": n_ops}
