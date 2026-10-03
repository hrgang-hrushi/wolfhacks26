"""Guards for things that broke on 2026-10-03."""
import subprocess
import sys
from pathlib import Path

import pytest


def test_G1_no_icloud_duplicate_files_under_src():
    assert [str(f) for f in Path("src").rglob("* 2*")] == []


def test_G2_numpy_pin_is_still_in_place():
    assert '"numpy<2.4"' in Path("pyproject.toml").read_text()   # pysheds 0.5 calls np.in1d


@pytest.mark.parametrize("module", ["src.model.common", "src.model.train_vit"])
def test_G4_importing_the_shared_module_does_not_load_lightgbm(module):
    """LightGBM loaded before PyTorch runs segfaults on macOS (two OpenMP runtimes)."""
    code = f"import sys, {module}; sys.exit(1 if 'lightgbm' in sys.modules else 0)"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-500:] or "lightgbm was imported"


@pytest.mark.parametrize("module", ["src.pipeline.pull_ncdot", "src.pipeline.dem", "src.pipeline.chips"])
def test_G3_pipeline_scripts_still_start(module):
    r = subprocess.run([sys.executable, "-m", module, "--help"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
