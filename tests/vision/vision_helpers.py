"""Plain helpers shared by the vision tests (kept out of conftest.py so they can be imported by name)."""

import importlib.util
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
REAL_CHIPS = ROOT / "data" / "chips"
REAL_TARGETS = ROOT / "data" / "processed" / "segments_targets.parquet"
REAL_JOINED = ROOT / "data" / "raw" / "ncdot_joined.parquet"


def load_box():
    spec = importlib.util.spec_from_file_location("cloud_box", ROOT / "scripts" / "cloud" / "box.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def good_offer(**changes):
    """An offer that passes every filter; tests change one field at a time."""
    o = {"id": 1, "machine_id": 100, "rentable": True, "verification": "verified", "num_gpus": 1,
         "gpu_name": "RTX 5090", "gpu_ram": 32607, "dph_total": 0.9, "cpu_cores_effective": 24.0,
         "cpu_ram": 64000, "disk_space": 500.0, "inet_down": 2000.0, "inet_down_cost": 0.0, "inet_up_cost": 0.0,
         "reliability2": 0.995, "cuda_max_good": 13.2, "geolocation": "Czechia, CZ", "storage_cost": 0.2}
    o.update(changes)
    return o


def lopsided_chip(seed=0):
    """A (4,128,128) uint8 chip with no symmetry: noise plus a bright corner patch and a band offset."""
    rng = np.random.default_rng(seed)
    chip = rng.integers(20, 200, size=(4, 128, 128), dtype=np.uint8)
    chip[:, :20, :35] = 240
    chip[3] = (chip[3] // 2 + 100).astype(np.uint8)
    return chip


def fold_of(block: str) -> int:
    return zlib.crc32(block.encode()) % 5


def make_table(n_blocks=30, per_block=12, seed=0):
    """A table shaped like the hardened segments_targets.parquet: 5 km blocks, fold = crc32(block) % 5."""
    rng = np.random.default_rng(seed)
    rows = []
    for b in range(n_blocks):
        bx, by = 100 + b % 6, 40 + b // 6
        for j in range(per_block):
            x = bx * 5000 + rng.uniform(100, 4900)
            y = by * 5000 + rng.uniform(100, 4900)
            block = f"{int(np.floor(x / 5000))}_{int(np.floor(y / 5000))}"
            rows.append({"seg_id": f"ncdot:{b:03d}{j:03d}:{j / 10:.3f}", "mid_x": x, "mid_y": y,
                         "split_block": block, "fold": fold_of(block)})
    d = pd.DataFrame(rows)
    n = len(d)
    signal = rng.normal(size=n)
    d["signal"] = signal
    d["y_rate"] = np.where(rng.random(n) < 0.85, 1.5 + signal + rng.normal(scale=0.3, size=n), np.nan)
    d["y_crack"] = np.where(rng.random(n) < 0.7, (signal + rng.normal(scale=0.5, size=n) > 0.8).astype(float), np.nan)
    d["in_helene_zone"] = (d.mid_x < 102 * 5000).astype(int)
    d["y_helene_failed"] = np.where(d.in_helene_zone == 1,
                                    (signal + rng.normal(scale=0.7, size=n) > 1.0).astype(float), np.nan)
    d["pv_COUNTY"] = np.where(d.index % 2 == 0, "092-Wake", "011-Buncombe")
    return d


def chips_for(d, signal_strength=40.0, seed=0):
    """One chip per row whose top-half brightness carries the row's 'signal' column, so a model can learn it."""
    rng = np.random.default_rng(seed)
    out = np.empty((len(d), 4, 128, 128), dtype=np.uint8)
    for i, s in enumerate(d.signal.values):
        base = rng.integers(40, 120, size=(4, 128, 128)).astype(np.float32)
        base[:, :64, :] += signal_strength * s  # top half only: not symmetric under flips
        out[i] = np.clip(base, 1, 255).astype(np.uint8)  # never 0: an all-zero pixel reads as blank fill
    return out


def tiny_net_factory():
    import torch.nn as nn

    class TinyNet(nn.Module):
        """Stand-in for train_vit.Net: same attributes (b, h) and forward(x, emb), sensitive to flips and turns."""

        def __init__(s):
            super().__init__()
            s.b = nn.Sequential(nn.Conv2d(3, 4, 5, stride=4), nn.ReLU(), nn.AdaptiveAvgPool2d(4), nn.Flatten(),
                                nn.Linear(64, 384))
            s.h = nn.Linear(384, 2)

        def forward(s, x, emb=False):
            z = s.b(x)
            return z if emb else s.h(z)

    return TinyNet()
