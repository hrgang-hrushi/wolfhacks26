"""Inputs for the vision comparisons: the label and fold table, the chips, and the model input.

Labels and folds are read, never computed here. load_table refuses segments_targets.parquet unless
it carries the stable 5 km folds (fold = crc32(split_block) % 5), so a result can never be scored on
a different split from the tabular models. Everything this module writes goes under
data/processed/vision through atomic_write.
"""

from __future__ import annotations

import hashlib
import os
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from src.model import augment
from src.pipeline.chips import chip_path

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
CHIPS = ROOT / "data" / "chips"
OUT_ROOT = PROCESSED / "vision"

BLOCK_M = 5000
N_FOLDS = 5
MAX_BLANK = 0.05
CHIP_SHAPE = (4, 128, 128)
REQUIRED = ["seg_id", "mid_x", "mid_y", "split_block", "fold", "y_rate", "y_crack"]
HASHED_COLUMNS = ["seg_id", "fold", "split_block", "mid_x", "mid_y", "y_rate", "y_crack", "y_helene_failed",
                  "in_helene_zone"]
CODE_DIRS = ("src", "tests/vision", "scripts/cloud")
RERUN = "rerun src.model.train_tabular after the model-hardening change"


# ---------------------------------------------------------------- writing

def atomic_write(path, write_fn, out_root=None) -> Path:
    """Write through a temporary file and rename. Refuses any path outside the output root."""
    path = Path(path).resolve()
    root = Path(OUT_ROOT if out_root is None else out_root).resolve()
    if root != path and root not in path.parents:
        raise ValueError(f"refusing to write outside {root}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        write_fn(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def save_npy(path, arr, out_root=None) -> Path:
    def write(tmp):
        with open(tmp, "wb") as f:
            np.save(f, arr)
    return atomic_write(path, write, out_root)


# ---------------------------------------------------------------- the table gate

def fold_of(block: str) -> int:
    return zlib.crc32(str(block).encode()) % N_FOLDS


def block_of(mid_x, mid_y) -> pd.Series:
    bx = np.floor(np.asarray(mid_x, dtype="float64") / BLOCK_M).astype("int64")
    by = np.floor(np.asarray(mid_y, dtype="float64") / BLOCK_M).astype("int64")
    return pd.Series(bx).astype(str) + "_" + pd.Series(by).astype(str)


def check_table(d: pd.DataFrame) -> pd.DataFrame:
    """Raise unless d has the hardened labels-and-folds contract. Returns d unchanged."""
    missing = [c for c in REQUIRED if c not in d.columns]
    if missing:
        raise ValueError(f"segments_targets.parquet lacks {missing}; {RERUN}")
    if d.seg_id.isna().any() or d.seg_id.duplicated().any():
        raise ValueError("seg_id must be unique and non-null")
    if d[["mid_x", "mid_y"]].isna().any().any():
        raise ValueError("mid_x and mid_y must be present for every segment")
    expected_block = block_of(d.mid_x.values, d.mid_y.values).values
    wrong = d.split_block.astype(str).values != expected_block
    if wrong.any():
        raise ValueError(f"{int(wrong.sum())} rows have a split_block that is not the 5 km block of their midpoint; {RERUN}")
    expected_fold = np.array([fold_of(b) for b in d.split_block.values])
    if not np.array_equal(pd.to_numeric(d.fold, errors="coerce").fillna(-1).astype(int).values, expected_fold):
        raise ValueError(f"fold is not crc32(split_block) % {N_FOLDS}; {RERUN}")
    return d


def load_table(processed_dir=None) -> pd.DataFrame:
    path = Path(PROCESSED if processed_dir is None else processed_dir) / "segments_targets.parquet"
    if not path.exists():
        raise ValueError(f"{path} not found; {RERUN}")
    return check_table(pd.read_parquet(path)).reset_index(drop=True)


def _sha(parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
        h.update(b"\x1f")
    return h.hexdigest()


def table_hash(d: pd.DataFrame) -> str:
    """Fingerprint of every column this change reads. A column that is absent hashes as absent."""
    parts = []
    for c in HASHED_COLUMNS:
        parts.append(c)
        if c in d.columns:
            col = d[c]
            if pd.api.types.is_numeric_dtype(col):
                parts.append(np.ascontiguousarray(col.values, dtype="float64").tobytes())
            else:
                parts.append("\x1e".join(col.astype(str).values))
        else:
            parts.append("<absent>")
    return _sha(parts)


def manifest_hash(seg_ids) -> str:
    """Fingerprint of a road list, independent of order."""
    return _sha(sorted(str(s) for s in seg_ids))


# ---------------------------------------------------------------- chips

def chip_file(seg_id: str, chips_dir=None) -> Path:
    """The chip file for a segment: the name chips.py gives it, in chips_dir."""
    return Path(CHIPS if chips_dir is None else chips_dir) / chip_path(seg_id).name


def chipped(d: pd.DataFrame, chips_dir=None) -> pd.DataFrame:
    d = d.copy()
    cdir = Path(CHIPS if chips_dir is None else chips_dir)
    present = {p.name for p in cdir.iterdir() if p.suffix == ".npy"} if cdir.exists() else set()
    d["has_chip"] = [chip_path(s).name in present for s in d.seg_id]
    return d


def chip_census(d: pd.DataFrame, chips_dir=None) -> dict:
    has = chipped(d, chips_dir).has_chip
    return {"total": int(len(d)), "with_chip": int(has.sum()), "without_chip": int((~has).sum())}


def _load_one(args):
    seg_id, path = args
    try:
        chip = np.load(path)
    except Exception as e:
        raise ValueError(f"chip for {seg_id} is unreadable ({path.name}): {e}") from e
    if chip.shape != CHIP_SHAPE or chip.dtype != np.uint8:
        raise ValueError(f"chip for {seg_id} is {chip.dtype} {chip.shape}, expected uint8 {CHIP_SHAPE} ({path.name})")
    return chip


def blank_fraction(chips: np.ndarray) -> np.ndarray:
    """Share of pixels where all four bands are 0 (the fill value chips.py uses outside a NAIP tile)."""
    return (chips == 0).all(axis=1).reshape(len(chips), -1).mean(axis=1).astype("float32")


def load_chips(seg_ids, chips_dir=None, workers=16):
    """All chips for seg_ids as one uint8 array (N,4,128,128), plus each chip's blank fraction."""
    jobs = [(s, chip_file(s, chips_dir)) for s in seg_ids]
    out = np.empty((len(jobs), *CHIP_SHAPE), dtype=np.uint8)
    with ThreadPoolExecutor(workers) as pool:
        for i, chip in enumerate(pool.map(_load_one, jobs)):
            out[i] = chip
    return out, blank_fraction(out)


def usable_mask(blank_frac, max_blank=MAX_BLANK) -> np.ndarray:
    return np.asarray(blank_frac) <= max_blank


def to_model_input(chips_u8: np.ndarray) -> np.ndarray:
    """The landed model's input (train_vit.DS): bands R, G, B, cropped to 126 x 126, scaled to 0..1."""
    x = np.asarray(chips_u8)
    single = x.ndim == 3
    x = x[None] if single else x
    out = np.ascontiguousarray(x[:, :3, 1:127, 1:127]).astype("float32") / 255
    return out[0] if single else out


# ---------------------------------------------------------------- dataset and folds

class ViewDataset:
    """Chips in memory with labels. Training reads apply one random draw of the preset; scoring reads apply nothing.

    __getitem__ returns (input, y_rate, y_crack, mask, index, n_ops) as tensors, with NaN labels
    replaced by 0 and flagged in mask, the layout train_vit.DS uses plus the index and the number of
    changes applied. Call set_epoch before each epoch; loaders must be built per epoch.
    """

    def __init__(self, chips, y_rate, y_crack, preset=augment.NONE, seed=0, train=False, rows=None):
        assert len(chips) == len(y_rate) == len(y_crack)
        self.chips, self.y_rate, self.y_crack = chips, np.asarray(y_rate, "float32"), np.asarray(y_crack, "float32")
        self.preset, self.seed, self.train, self.epoch = preset, int(seed), bool(train), 0
        # rows: which rows of chips this dataset serves (a fold's training rows), without copying the array
        self.rows = np.arange(len(chips)) if rows is None else np.asarray(rows, dtype="int64")

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def __len__(self):
        return len(self.rows)

    def draw(self, i: int):
        """The chip that item i is trained on this epoch, and the record of what was applied.

        The random draw is keyed by the road's row in the full array, so it does not depend on which
        other roads are in the fold.
        """
        row = int(self.rows[i])
        if not self.train:
            return self.chips[row], {"view": 0, "dx": 0, "dy": 0, "gain": 1.0, "contrast": 1.0, "n_ops": 0}
        return augment.random_augment(self.chips[row], augment.sample_rng(self.seed, self.epoch, row), self.preset)

    def __getitem__(self, i):
        import torch
        row = int(self.rows[int(i)])
        chip, record = self.draw(int(i))
        yr, yc = self.y_rate[row], self.y_crack[row]
        return (torch.from_numpy(to_model_input(chip)),
                torch.tensor(0.0 if np.isnan(yr) else float(yr)), torch.tensor(0.0 if np.isnan(yc) else float(yc)),
                torch.tensor([float(not np.isnan(yr)), float(not np.isnan(yc))]),
                torch.tensor(row), torch.tensor(int(record["n_ops"])))


def fold_split(d: pd.DataFrame, k: int):
    """(training row positions, held-out row positions) for fold k."""
    fold = d.fold.values
    return np.where(fold != k)[0], np.where(fold == k)[0]


def cross_fold_neighbours(d: pd.DataFrame, radius_m: float = 77.0) -> int:
    """Pairs of roads closer than radius_m whose folds differ: chips that overlap across a held-out boundary."""
    from scipy.spatial import cKDTree
    xy = d[["mid_x", "mid_y"]].values
    pairs = cKDTree(xy).query_pairs(radius_m, output_type="ndarray")
    if len(pairs) == 0:
        return 0
    fold = d.fold.values
    return int((fold[pairs[:, 0]] != fold[pairs[:, 1]]).sum())


# ---------------------------------------------------------------- fingerprints

def _skip(path: Path) -> bool:
    import re
    return "__pycache__" in path.parts or path.suffix == ".pyc" or bool(re.search(r" \d+(\.[^/]*)?$", path.name))


def code_hash(root=None) -> str:
    """Same rule as scripts/cloud/box.py: every .py under CODE_DIRS plus uv.lock."""
    root = Path(ROOT if root is None else root)
    files = sorted(f for d in CODE_DIRS for f in (root / d).rglob("*.py") if not _skip(f))
    lock = root / "uv.lock"
    h = hashlib.sha256()
    for f in files + ([lock] if lock.exists() else []):
        h.update(f.relative_to(root).as_posix().encode())
        h.update(hashlib.sha256(f.read_bytes()).hexdigest().encode())
    return h.hexdigest()


def check_shipped_code(root=None) -> str:
    """On the box, the code that runs must be the code that was pushed. Returns the hash."""
    root = Path(ROOT if root is None else root)
    digest = code_hash(root)
    marker = root / "CODE_HASH"
    if marker.exists() and marker.read_text().strip() != digest:
        raise RuntimeError(f"code on this machine ({digest[:12]}) is not the code that was pushed "
                           f"({marker.read_text().strip()[:12]}); push again")
    return digest


def weights_hash(net) -> str:
    """Fingerprint of a model's parameters, taken before training starts."""
    h = hashlib.sha256()
    for name, p in sorted(net.state_dict().items()):
        h.update(name.encode())
        h.update(p.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
