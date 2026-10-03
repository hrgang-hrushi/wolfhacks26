"""Guards for things that broke on 2026-10-03."""
import subprocess
import sys
from pathlib import Path

import pytest


def test_G1_no_icloud_duplicate_files_under_src():
    assert [str(f) for f in Path("src").rglob("* 2*")] == []


def test_G2_numpy_pin_is_still_in_place():
    assert '"numpy<2.4"' in Path("pyproject.toml").read_text()   # pysheds 0.5 calls np.in1d


@pytest.mark.parametrize("module", ["src.pipeline.pull_ncdot", "src.pipeline.dem", "src.pipeline.chips"])
def test_G3_pipeline_scripts_still_start(module):
    r = subprocess.run([sys.executable, "-m", module, "--help"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
