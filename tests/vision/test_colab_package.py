"""The Google Colab route (scripts/colab): the package builder, the notebook's own logic, the identity check, the import."""

import ast
import hashlib
import importlib.util
import json
import sys
import types
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


# ---------------------------------------------------------------- the package

def test_the_package_holds_the_code_the_inputs_the_fingerprint_and_the_photo_hashes(tmp_path):
    builder = load("build_package")
    make_project(tmp_path / "proj")
    info = builder.build(tmp_path / "out", root=tmp_path / "proj", n_photos=123)
    box = builder.load_box()
    with zipfile.ZipFile(info["zip"]) as z:
        names = set(z.namelist())
        assert names == set(box.bundle_files(tmp_path / "proj")) | {
            "scripts/colab/check_identity.py", "scripts/colab/build_package.py", "CODE_HASH", "mac_chip_digests.json"}
        assert z.read("CODE_HASH").decode().strip() == box.code_hash(tmp_path / "proj") == info["code_hash"]
        digests = json.loads(z.read("mac_chip_digests.json"))
        assert digests == box.local_digests(tmp_path / "proj" / "data" / "chips") and len(digests) == 3
        assert "data/processed/segments_targets.parquet" in names and not [n for n in names if "chips/" in n]
    assert not list((tmp_path / "out").glob("*.tmp"))
    assert "N_PHOTOS = 123 " in (tmp_path / "out" / "vision_colab.ipynb").read_text()


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


# ---------------------------------------------------------------- the notebook

def test_the_notebook_is_valid_python_and_runs_the_stages_in_order():
    builder = load("build_package")
    nb = builder.notebook(n_photos=40_000, minutes=80)
    json.loads(json.dumps(nb))
    assert nb["nbformat"] == 4 and nb["metadata"]["accelerator"] == "GPU"
    code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    for cell in code:
        ast.parse(cell)  # plain Python throughout: no shell lines whose failure would go unnoticed
        assert not [ln for ln in cell.splitlines() if ln.startswith(("!", "%"))]
    text = "\n".join(code)
    order = ["torch.cuda.is_available()", "files.upload()", 'sys.path.insert(0, "/content/hack")',
             '"pip", "-q", "install"', "V.load_table()", '"--limit", 50, "--seed", 0', "check_identity.py",
             '"--out", smoke', "reduced_schedule()", 'assert rec["backbone_change"] > 0', '"--limit", N_PHOTOS',
             "0.95 * N_PHOTOS", '"-m", "pytest", "tests/vision"', "colab_run.json",
             'py("-m", "src.model.vision_frozen")', 'save("frozen_results")', '"--time-only"', "plan_grid",
             '"one seed only"', 'save("results_after_" + name)', '"--shuffled-control", "--report", "--workers"',
             'save("vision_results")']
    positions = [text.index(s) for s in order]
    assert positions == sorted(positions), [s for s, a, b in zip(order, positions, sorted(positions)) if a != b]
    assert "N_PHOTOS = 40000 " in text and "MINUTES_FOR_TRAINING = 80 " in text
    assert "train_tabular" not in text and "final_ablation" not in text  # it never regenerates the shared tables
    first = "".join(nb["cells"][0]["source"])
    assert "2.5 hours" in first and "T4 GPU" in first


def helpers(tmp_path, monkeypatch):
    """The notebook's run / py / save helpers, with google.colab.files replaced by a recorder."""
    builder = load("build_package")
    downloads = []
    colab = types.ModuleType("google.colab")
    colab.files = types.SimpleNamespace(download=downloads.append)
    monkeypatch.setitem(sys.modules, "google", types.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.colab", colab)
    ns = {}
    exec(builder.HELPERS, ns)
    return builder, ns, downloads


def test_the_notebooks_commands_stop_on_failure_and_show_their_output(tmp_path, monkeypatch, capsys):
    builder, ns, _ = helpers(tmp_path, monkeypatch)
    ns["py"]("-c", "print('line one'); print('line two')")
    assert capsys.readouterr().out == "line one\nline two\n"
    with pytest.raises(RuntimeError, match=r"failed \(exit 3\)"):
        ns["py"]("-c", "import sys; print('about to fail'); sys.exit(3)")
    assert "about to fail" in capsys.readouterr().out  # the output is shown even when the command fails
    with pytest.raises(RuntimeError, match="failed"):
        ns["py"]("-c", "import a_module_that_does_not_exist")  # e.g. a missing library stops the run at once


def test_save_zips_the_results_so_far_without_the_big_arrays(tmp_path, monkeypatch):
    builder, ns, downloads = helpers(tmp_path, monkeypatch)
    root = tmp_path / "vision"
    for rel, data in {"frozen/metrics.json": b"{}", "frozen/emb_view0.npy": b"x" * 1000,
                      "finetune/none/seed0/fold0.parquet": b"PAR1", "colab_tests.txt": b"ok"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    real_zipfile = zipfile.ZipFile
    written = {}

    class Recorder(real_zipfile):
        def __init__(self, path, *a, **k):
            written["path"] = tmp_path / str(path).strip("/").replace("/", "_")
            super().__init__(written["path"], *a, **k)

    monkeypatch.setattr(ns["zipfile"], "ZipFile", Recorder)
    ns["save"]("after_stage", root=str(root))
    monkeypatch.setattr(ns["zipfile"], "ZipFile", real_zipfile)
    assert downloads == ["/content/after_stage.zip"]
    with zipfile.ZipFile(written["path"]) as z:
        assert sorted(z.namelist()) == ["colab_tests.txt", "finetune/none/seed0/fold0.parquet", "frozen/metrics.json"]
    imp = load("import_results")
    out = tmp_path / "imported"
    out.mkdir()
    assert sorted(imp.import_results(written["path"], out)) == sorted(  # the importer accepts the notebook's own zips
        ["colab_tests.txt", "finetune/none/seed0/fold0.parquet", "frozen/metrics.json"])


class FakeFt:
    ARMS = ("none", "flips", "full")
    REPORT_MIN = 10.0

    def __init__(self, fits):
        self.fits = fits

    def plan_grid(self, timing, dph, cap_left, minutes_left, reserve_min):
        if not self.fits:
            raise ValueError("no schedule fits 80 min")
        return {"schedule": "reduced", "jobs": [[a, 0, f] for a in self.ARMS for f in range(5)] + [[a, 1, 0] for a in self.ARMS],
                "minutes": 70.0}

    @staticmethod
    def job_seconds(timing):
        return 240.0


def run_cell(source, ns):
    exec(compile(source, "<notebook cell>", "exec"), ns)


def notebook_ns(tmp_path, fits=True, fail_on=None):
    """A namespace standing in for the notebook kernel when the fine-tune cells run."""
    log = []
    report = tmp_path / "data" / "processed" / "vision" / "finetune"
    report.mkdir(parents=True)
    (report / "report.md").write_text("# report")
    (report / "timing.json").write_text(json.dumps({"backbone_change": 0.01}))

    real_open = open

    def opened(path, *a, **k):  # the cells use /content and repo-relative paths
        path = str(path)
        if path.startswith("/content/"):
            path = str(tmp_path / path[len("/content/"):])
        elif path.startswith("data/"):
            path = str(tmp_path / path)
        return real_open(path, *a, **k)

    def py(*args):
        args = [str(a) for a in args]
        if "--jobs" in args:
            jobs = json.load(opened(args[args.index("--jobs") + 1]))
            log.append(("jobs", sorted({j[0] for j in jobs}), sorted({j[1] for j in jobs}), len(jobs)))
            if fail_on and fail_on in {j[0] for j in jobs}:
                raise RuntimeError("failed (exit 1): the loss is nan")
        else:
            log.append(tuple(a for a in args if a.startswith("--")))

    ns = {"py": py, "save": lambda name: log.append(("save", name)), "json": json, "open": opened,
          "Ft": FakeFt(fits), "MINUTES_FOR_TRAINING": 80, "print": lambda *a: None}
    return ns, log


def test_the_plan_cell_falls_back_to_one_seed_when_nothing_fits(tmp_path):
    builder = load("build_package")
    ns, log = notebook_ns(tmp_path, fits=True)
    run_cell(builder.PLAN, ns)
    assert ns["plan"]["schedule"] == "reduced" and len(ns["plan"]["jobs"]) == 18
    assert log[0] == ("--time-only", "--workers")
    ns, log = notebook_ns(tmp_path / "b", fits=False)
    run_cell(builder.PLAN, ns)
    assert ns["plan"]["schedule"] == "one seed only"
    assert ns["plan"]["jobs"] == [[a, 0, f] for a in ("none", "flips", "full") for f in range(5)]  # still a full table
    assert ns["plan"]["minutes"] == pytest.approx(16 * 4 + 10)


def test_the_fine_tune_cell_saves_after_every_stage_and_again_at_the_end(tmp_path):
    builder = load("build_package")
    ns, log = notebook_ns(tmp_path)
    run_cell(builder.PLAN, ns)
    log.clear()
    run_cell(builder.FINETUNE, ns)
    assert log == [("jobs", ["none"], [0], 5), ("save", "results_after_none"),
                   ("jobs", ["flips"], [0], 5), ("save", "results_after_flips"),
                   ("jobs", ["full"], [0], 5), ("save", "results_after_full"),
                   ("jobs", ["flips", "full", "none"], [1], 3), ("save", "results_after_second_seed"),
                   ("--shuffled-control", "--report", "--workers"), ("save", "vision_results")]


def test_a_failure_part_way_still_offers_what_was_finished(tmp_path):
    builder = load("build_package")
    ns, log = notebook_ns(tmp_path, fail_on="flips")
    run_cell(builder.PLAN, ns)
    log.clear()
    with pytest.raises(RuntimeError, match="the loss is nan"):  # the error is not swallowed: Run all stops
        run_cell(builder.FINETUNE, ns)
    assert log == [("jobs", ["none"], [0], 5), ("save", "results_after_none"), ("jobs", ["flips"], [0], 5),
                   ("save", "vision_results")]  # ... but the finished arm was saved, and the final zip is still offered
    frozen_ns = {"py": lambda *a: (_ for _ in ()).throw(RuntimeError("frozen stage failed")),
                 "save": lambda name: log.append(("save", name)), "open": open, "print": print}
    log.clear()
    with pytest.raises(RuntimeError, match="frozen stage failed"):
        run_cell(builder.FROZEN, frozen_ns)
    assert log == [("save", "frozen_results")]


# ---------------------------------------------------------------- identity and import

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
        z.writestr("colab_tests.txt", "322 passed")
        z.writestr("colab_run.json", "{}")
    out = tmp_path / "vision"
    out.mkdir()
    written = imp.import_results(good, out)
    assert sorted(written) == ["colab_run.json", "colab_tests.txt", "finetune/report.md", "frozen/metrics.json",
                               "ndvi_stats.parquet"]
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
