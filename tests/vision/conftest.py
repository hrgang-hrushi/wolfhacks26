"""Fixtures for the vision tests. Registers no command-line options."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

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
