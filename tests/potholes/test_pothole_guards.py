"""Guards for this change: every new script starts, and nobody else's files were touched."""
import subprocess
import sys
from pathlib import Path

import pytest

NEW_SCRIPTS = ["src.pipeline.cctv", "src.pipeline.cctv_review", "src.pipeline.pull_potholes",
               "src.pipeline.pothole_labels", "src.model.pothole_check", "src.model.pothole_head", "src.model.cctv_check"]
# owned by other work: the model code and its tests, the earlier pipeline scripts, the project files
NOT_OURS = ["src/model/common.py", "src/model/train_tabular.py", "src/model/final_ablation.py", "src/model/train_vit.py",
            "src/pipeline/pull_ncdot.py", "src/pipeline/dem.py", "src/pipeline/chips.py", "src/pipeline/features.py",
            "src/pipeline/helene_labels.py", "src/pipeline/helene_points.py", "src/pipeline/pull_aadt.py",
            "src/pipeline/pull_helene.py", "src/pipeline/terrain_simple.py", "tests/conftest.py", "tests/test_features.py",
            "tests/test_folds.py", "tests/test_oof.py", "tests/test_predictions.py", "tests/test_realdata.py",
            "tests/test_repo_guards.py", "tests/test_scripts.py", "tests/test_targets.py", "pyproject.toml", "uv.lock",
            "src/pipeline/__init__.py", "src/model/__init__.py", ".gitignore", ".python-version",
            "readme", "README.md", "PLAN.md"]


@pytest.mark.parametrize("module", NEW_SCRIPTS)
def test_R1_new_scripts_start(module):
    r = subprocess.run([sys.executable, "-m", module, "--help"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "usage:" in r.stdout, r.stderr[-500:]     # a real command line, not a silent import


def test_R1_fetch_helper_imports():
    from src.pipeline import arcgis_fetch                # a library, with no command line of its own
    assert callable(arcgis_fetch.fetch_all) and callable(arcgis_fetch.count)


def test_R2_no_icloud_duplicate_files():
    assert [str(f) for d in ("src", "tests") for f in Path(d).rglob("* 2*")] == []


def test_R3_files_owned_by_other_work_are_unchanged_on_this_branch():
    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True)
    base = next((git("merge-base", "HEAD", ref).stdout.strip() for ref in ("main", "origin/main")
                 if git("rev-parse", "--verify", "-q", ref).returncode == 0), "")
    if not base:
        pytest.skip("no main branch to compare against")
    # once this branch is merged the comparison is empty by construction, which is the point:
    # it only speaks while the work is still on its own branch
    assert git("diff", "--name-only", base, "HEAD", "--", *NOT_OURS).stdout.split() == []
    assert git("diff", "--name-only", "--", *NOT_OURS).stdout.split() == []     # nor uncommitted edits
