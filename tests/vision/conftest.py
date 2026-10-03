"""Fixtures for the vision tests. Registers no command-line options."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# This checkout's root must come first on the path, ahead of any other checkout pytest may have put
# there (a worktree sits inside the main checkout, whose pytest config adds its own root).
for p in (str(ROOT), str(HERE)):
    while p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)
for name in [n for n in sys.modules if n == "src" or n.startswith("src.")]:
    if not str(getattr(sys.modules[name], "__file__", "") or "").startswith(str(ROOT)):
        del sys.modules[name]  # a copy of the package imported from another checkout

import torch  # noqa: E402

# On macOS, LightGBM and PyTorch each bring their own OpenMP runtime; with both loaded (tests/conftest.py
# imports LightGBM through src.model.common) a multi-threaded PyTorch call segfaults. One thread is safe.
torch.set_num_threads(1)

import vision_helpers as vh  # noqa: E402


@pytest.fixture
def box(tmp_path, monkeypatch):
    """scripts/cloud/box.py with its state files in a temporary directory and the vastai binary stubbed."""
    mod = vh.load_box()
    logs = tmp_path / "logs"
    monkeypatch.setattr(mod, "LOGS", logs)
    monkeypatch.setattr(mod, "STATE", logs / "cloud_box_state.json")
    monkeypatch.setattr(mod, "HISTORY", logs / "cloud_box_history.json")
    monkeypatch.setattr(mod, "KNOWN_HOSTS", logs / "cloud_known_hosts")
    monkeypatch.setattr(mod, "vastai_bin", lambda: "vastai")
    return mod


@pytest.fixture
def offers():
    return json.loads((vh.FIXTURES / "offers_sample.json").read_text())


@pytest.fixture
def chip():
    return vh.lopsided_chip()


@pytest.fixture
def table():
    return vh.make_table()


@pytest.fixture
def chips_dir(tmp_path, table):
    """A directory of chip files for the fixture table, named the way chips.py names them."""
    from src.pipeline.chips import chip_path
    cdir = tmp_path / "chips"
    cdir.mkdir()
    for seg_id, c in zip(table.seg_id, vh.chips_for(table)):
        np.save(cdir / chip_path(seg_id).name, c)
    return cdir


@pytest.fixture
def processed_dir(tmp_path, table):
    p = tmp_path / "processed"
    p.mkdir()
    table.to_parquet(p / "segments_targets.parquet")
    return p


@pytest.fixture
def tiny_net():
    import torch
    torch.manual_seed(0)
    return vh.tiny_net_factory()
