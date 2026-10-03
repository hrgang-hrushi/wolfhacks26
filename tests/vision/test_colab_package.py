"""The Google Colab route (scripts/colab): the package builder, the identity check, the results import."""

import ast
import importlib.util
import json
import zipfile

import numpy as np
import pytest

from vision_helpers import ROOT


def load(name):
    spec = importlib.util.spec_from_file_location(f"colab_{name}", ROOT / "scripts" / "colab" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_project(root, with_targets=True, with_chips=True):
    files = {"src/a.py": "x = 1\n", "src/model/b.py": "y = 2\n", "tests/vision/test_x.py": "z = 3\n",
             "scripts/cloud/box.py": "w = 4\n", "scripts/colab/check_identity.py": "v = 5\n",
             "scripts/colab/build_package.py": "u = 6\n",
             "pyproject.toml": "[project]\n", "uv.lock": "lock\n", ".python-version": "3.11\n",
             "data/raw/ncdot_joined.parquet": "p", "data/raw/naip_2022_index.parquet": "q"}
    if with_targets:
        files["data/processed/segments_targets.parquet"] = "t"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    (root / "data" / "chips").mkdir(parents=True, exist_ok=True)
    if with_chips:
        rng = np.random.default_rng(0)
        for i in range(3):
            np.save(root / "data" / "chips" / f"ncdot_{i}_0.000.npy", rng.integers(0, 255, (4, 8, 8), dtype=np.uint8))


def test_the_package_holds_the_code_the_inputs_the_fingerprint_and_the_photo_hashes(tmp_path):
    builder = load("build_package")
    make_project(tmp_path / "proj")
    info = builder.build(tmp_path / "out", root=tmp_path / "proj", n_photos=123)
    box = builder.load_box()
    with zipfile.ZipFile(info["zip"]) as z:
        names = set(z.namelist())
        assert names == set(box.bundle_files(tmp_path / "proj")) | {
            "scripts/colab/check_identity.py", "scripts/colab/build_package.py", "CODE_HASH", "mac_chip_digests.json"}
        assert z.read("CODE_HASH").decode().strip() == box.code_hash(tmp_path / "proj")
        digests = json.loads(z.read("mac_chip_digests.json"))
        assert digests == box.local_digests(tmp_path / "proj" / "data" / "chips") and len(digests) == 3
        assert "data/processed/segments_targets.parquet" in names and not [n for n in names if "chips/" in n]
    assert not list((tmp_path / "out").glob("*.tmp"))


def test_the_package_is_refused_without_labels_without_photos_or_with_a_key(tmp_path):
    builder = load("build_package")
    make_project(tmp_path / "a", with_targets=False)
    with pytest.raises(SystemExit, match="labels and folds"):
        builder.build(tmp_path / "out", root=tmp_path / "a")
    make_project(tmp_path / "b", with_chips=False)
    with pytest.raises(SystemExit, match="no photos on this machine"):
        builder.build(tmp_path / "out", root=tmp_path / "b")
    make_project(tmp_path / "c")
    (tmp_path / "c" / "src" / "settings.py").write_text("API" + "_KEY = 'A1b2C3d4E5f6G7h8I9j0K1l2'\n")
    with pytest.raises(Exception, match="look like they hold a key"):
        builder.build(tmp_path / "out", root=tmp_path / "c")
    assert not (tmp_path / "out" / "vision_colab.zip").exists()


def test_the_notebook_is_valid_and_runs_the_stages_in_order():
    builder = load("build_package")
    nb = builder.notebook(n_photos=40_000)
    json.loads(json.dumps(nb))
    assert nb["nbformat"] == 4 and nb["metadata"]["accelerator"] == "GPU"
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for cell in code:  # every code cell is valid Python once the notebook's shell lines are set aside
        ast.parse("\n".join(ln for ln in cell.splitlines() if not ln.startswith("!")))
    text = "\n".join(code)
    order = ["torch.cuda.is_available()", "files.upload()", "pip -q install", "--limit 50 --seed 0",
             "check_identity.py", "--limit $N_PHOTOS --seed 0", '"-m", "pytest", "tests/vision"', "src.model.vision_frozen",
             "frozen_results.zip", "--time-only", "plan_grid", "--jobs /content/jobs.json --shuffled-control --report",
             "vision_results.zip"]
    positions = [text.index(s) for s in order]
    assert positions == sorted(positions)
    assert "N_PHOTOS = 40000" in text
    assert "train_tabular" not in text and "final_ablation" not in text  # it never regenerates the shared tables
    assert 'assert subprocess.run([sys.executable, "scripts/colab/check_identity.py"]).returncode == 0' in text


def test_the_identity_check_fails_only_on_differing_pixels_or_too_few_photos(tmp_path):
    ident = load("check_identity")
    mac = {f"p{i}.npy": f"h{i}" for i in range(50)}
    assert ident.check(mac, dict(mac))[0]
    assert ident.check(mac, {**mac, "extra.npy": "x"})[0]                      # more photos here is fine
    few_missing = {k: v for k, v in mac.items() if k not in ("p1.npy", "p2.npy")}
    assert ident.check(mac, few_missing)[0]                                     # 48 of 50 arrived, all identical
    ok, msg = ident.check(mac, {**mac, "p7.npy": "different"})
    assert not ok and "1 of 50 photos differ" in msg
    ok, msg = ident.check(mac, {k: mac[k] for k in list(mac)[:40]})
    assert not ok and "only 40" in msg
    arr = np.arange(4 * 8 * 8, dtype=np.uint8).reshape(4, 8, 8)
    np.save(tmp_path / "a.npy", arr)
    import hashlib
    assert ident.digests(str(tmp_path)) == {"a.npy": hashlib.sha256(arr.tobytes()).hexdigest()}
    box = load("build_package").load_box()
    assert ident.digests(str(tmp_path)) == box.local_digests(tmp_path)  # the same hash on both machines


def test_results_come_back_whole_or_not_at_all(tmp_path):
    imp = load("import_results")
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("frozen/metrics.json", '{"kind": "frozen"}')
        z.writestr("finetune/report.md", "# report")
        z.writestr("ndvi_stats.parquet", "PAR1")
    out = tmp_path / "vision"
    out.mkdir()
    written = imp.import_results(good, out)
    assert sorted(written) == ["finetune/report.md", "frozen/metrics.json", "ndvi_stats.parquet"]
    assert (out / "frozen" / "metrics.json").read_text() == '{"kind": "frozen"}'
    for bad_name in ("../segments.parquet", "segments_targets.parquet", "chips/x.npy", "/etc/passwd"):
        bad = tmp_path / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("frozen/metrics.json", '{"kind": "changed"}')
            z.writestr(bad_name, "nope")
        with pytest.raises(ValueError, match="unexpected file"):
            imp.import_results(bad, out)
        assert (out / "frozen" / "metrics.json").read_text() == '{"kind": "frozen"}'  # nothing was touched
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bad.zip", "good.zip", "vision"]  # no temp folder left
