"""Guards for this change: the scripts start, nobody else's files were touched, nothing heavy is loaded."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = ["src.pipeline.helene_dem10", "src.pipeline.helene_depth"]
OURS = ("src/pipeline/helene_dem10.py", "src/pipeline/helene_depth.py", "tests/helene_depth/",
        "docs/specs/2026-10-03_helene-depth-map", "docs/features/HELENE_DEPTH_MAP.md",
        "docs/reports/2026-10-03_helene-depth-map-plan")  # fmt: skip


def test_G1_both_scripts_answer_help():
    for module in SCRIPTS:
        r = subprocess.run([sys.executable, "-m", module, "--help"], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0 and "usage:" in r.stdout, r.stderr[-500:]  # a real command line, not a silent import


def test_G2_no_icloud_duplicate_files():
    assert [str(f) for d in ("src", "tests") for f in Path(d).rglob("* 2*")] == []


def test_G3_this_branch_changed_only_its_own_files():
    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True)

    if git("branch", "--show-current").stdout.strip() != "helene-depth":
        pytest.skip("only speaks while the work is on its own branch")
    base = next((git("merge-base", "HEAD", ref).stdout.strip() for ref in ("main", "origin/main")
                 if git("rev-parse", "--verify", "-q", ref).returncode == 0), "")  # fmt: skip
    if not base:
        pytest.skip("no main branch to compare against")
    changed = set(git("diff", "--name-only", base, "HEAD").stdout.split("\n")) | set(git("diff", "--name-only").stdout.split("\n"))
    changed |= set(git("ls-files", "--others", "--exclude-standard").stdout.split("\n"))  # new files not yet committed
    foreign = sorted(f for f in changed if f and not f.startswith(OURS))
    assert foreign == [], f"files outside this change were touched: {foreign}"


def test_G4_the_scripts_import_with_no_data_no_network_and_nothing_heavy(tmp_path):
    code = ("import socket, sys\n"
            "def no_network(*a, **k): raise RuntimeError('import reached for the network')\n"
            "socket.socket.connect = no_network\n"
            "socket.create_connection = no_network\n"
            "import src.pipeline.helene_dem10, src.pipeline.helene_depth\n"
            "heavy = [m for m in ('torch', 'lightgbm', 'py3dep', 'timm') if m in sys.modules]\n"
            "sys.exit(f'loaded at import: {heavy}' if heavy else 0)\n")  # fmt: skip
    env = {**os.environ, "PYTHONPATH": str(Path.cwd())}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=tmp_path, env=env)
    assert r.returncode == 0, r.stderr[-800:]  # run from an empty folder: no data/ to lean on
