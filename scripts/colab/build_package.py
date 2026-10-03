"""Build the Google Colab package for the vision comparisons: one notebook and one zip.

    python scripts/colab/build_package.py [output_dir]

Colab is the route for a network that blocks the ports a rented box needs: everything goes through the
browser. The zip holds the same files `scripts/cloud/box.py push` would send (code, the segment table,
the labels and folds), the code fingerprint, and the pixel hashes of the photos this machine already
has, so the notebook can check that Colab fetches the same photos.

The notebook is built to fail early and lose little:
- a complete small run on 50 photos comes first, so an environment problem shows in minutes, not hours;
- every command that matters stops the notebook if it fails;
- results are offered as a download after every stage, and again in a `finally`, so a disconnect or
  an error part-way costs one stage, not the run;
- the fine-tune schedule is chosen to fit a stated time, down to one seed if need be.
It fetches a random sample of photos (Colab's free machine cannot hold the whole state).
"""

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "processed" / "vision" / "colab"
N_PHOTOS = 40_000            # 2.6 GB in memory; Colab's free machine has about 12 GB
MINUTES_FOR_TRAINING = 80    # the fine-tune stage alone; fetch, checks and the frozen stage add about an hour


def load_box():
    spec = importlib.util.spec_from_file_location("cloud_box", ROOT / "scripts" / "cloud" / "box.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


UPLOAD = '''
import glob, json, os, pathlib, subprocess, sys, zipfile
if not os.path.exists("/content/hack/CODE_HASH"):
    from google.colab import files
    print("Choose vision_colab.zip")
    uploaded = files.upload()
    zipfile.ZipFile(next(iter(uploaded))).extractall("/content/hack")
os.chdir("/content/hack")
sys.path.insert(0, "/content/hack")
print("code fingerprint:", open("CODE_HASH").read().strip())
'''

HELPERS = '''
import pathlib, subprocess, sys, zipfile


def run(*args):
    """Run a command, showing its output as it comes. A failure stops the notebook."""
    args = [str(a) for a in args]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        print(line, end="")
    if p.wait() != 0:
        raise RuntimeError("failed (exit %d): %s" % (p.returncode, " ".join(args[:7])))


def py(*args):
    run(sys.executable, "-u", *args)


def save(name, root="data/processed/vision"):
    """Zip the results so far and offer them as a download, so a disconnect loses one stage, not the run."""
    from google.colab import files
    root, path = pathlib.Path(root), "/content/%s.zip" % name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(root.rglob("*")):
            if f.is_file() and f.suffix != ".npy":
                z.write(f, f.relative_to(root).as_posix())
    files.download(path)
'''

INSTALL = '''
run(sys.executable, "-m", "pip", "-q", "install", "timm", "geopandas", "rasterio", "pystac-client",
    "planetary-computer", "lightgbm", "pytest")
# everything the later stages import, and both data files read, checked now
py("-c", "import torch, timm, lightgbm, geopandas, rasterio, pandas, numpy; "
         "from src.model import train_vit, vision_frozen, vision_finetune, vision_data as V; "
         "d = V.load_table(); "
         "g = geopandas.read_parquet('data/raw/ncdot_joined.parquet', columns=['seg_id', 'geometry']); "
         "print('imports ok;', len(d), 'rows with labels and folds,', len(g), 'segments; pandas', pandas.__version__, "
         "'numpy', numpy.__version__, 'torch', torch.__version__)")
'''

SMOKE = '''
py("-m", "src.pipeline.chips", "--limit", 50, "--seed", 0, "--workers", 16)
py("scripts/colab/check_identity.py", "mac_chip_digests.json", "data/chips")

# A complete small run on those 50 photos: every later stage, in a few minutes, so a problem shows up now.
smoke = "/content/smoke"
py("-m", "src.model.vision_frozen", "--out", smoke, "--boot", 30)
from src.model import vision_finetune as Ft
json.dump([list(j) for j in Ft.reduced_schedule()], open("/content/smoke_jobs.json", "w"))
py("-m", "src.model.vision_finetune", "--out", smoke, "--epochs", 1, "--batch", 8, "--workers", 2, "--boot", 30,
   "--jobs", "/content/smoke_jobs.json", "--shuffled-control", "--report")
rec = json.load(open(smoke + "/finetune/full/seed0/fold0.done.json"))
print("small run complete; backbone change on this GPU:", rec["backbone_change"])
assert rec["backbone_change"] > 0, "the backbone did not train on this GPU: stop here and tell the chat"
'''

FETCH = '''
py("-m", "src.pipeline.chips", "--limit", N_PHOTOS, "--seed", 0, "--workers", FETCH_WORKERS)
py("-m", "src.pipeline.chips", "--limit", N_PHOTOS, "--seed", 0, "--workers", FETCH_WORKERS)  # retry any failures
n_photos = len(glob.glob("data/chips/*.npy"))
print(n_photos, "photos on this machine")
assert n_photos >= 0.95 * N_PHOTOS, "only %d of %d photos arrived: stop here and tell the chat" % (n_photos, N_PHOTOS)
'''

TESTS = '''
import numpy, pandas
pathlib.Path("data/processed/vision").mkdir(parents=True, exist_ok=True)
t = subprocess.run([sys.executable, "-m", "pytest", "tests/vision", "-q", "-rs", "-p", "no:cacheprovider"],
                   capture_output=True, text=True)
pathlib.Path("data/processed/vision/colab_tests.txt").write_text(t.stdout[-8000:] + t.stderr[-2000:])
json.dump({"n_photos_requested": N_PHOTOS, "n_photos": n_photos, "gpu": torch.cuda.get_device_name(0),
           "torch": torch.__version__, "pandas": pandas.__version__, "numpy": numpy.__version__,
           "code_hash": open("CODE_HASH").read().strip(), "minutes_for_training": MINUTES_FOR_TRAINING,
           "tests_exit_code": t.returncode}, open("data/processed/vision/colab_run.json", "w"), indent=1)
print(t.stdout[-1500:])
print("TESTS PASSED" if t.returncode == 0 else "TESTS FAILED (continuing; the output is saved with the results)")
'''

FROZEN = '''
try:
    py("-m", "src.model.vision_frozen")
    print(open("data/processed/vision/frozen/report.md").read())
finally:
    save("frozen_results")
'''

PLAN = '''
py("-m", "src.model.vision_finetune", "--time-only", "--workers", 2)
timing = json.load(open("data/processed/vision/finetune/timing.json"))
print("backbone change in the timed job:", timing["backbone_change"])
try:
    plan = Ft.plan_grid(timing, dph=0.0, cap_left=1.0, minutes_left=MINUTES_FOR_TRAINING, reserve_min=0)
except ValueError as e:  # not even the smaller schedule fits: one seed only, and the report will say so
    print("does not fit the time set at the top:", e)
    jobs = [[arm, 0, fold] for arm in Ft.ARMS for fold in range(5)]
    plan = {"schedule": "one seed only", "jobs": jobs,
            "minutes": (len(jobs) + 1) * Ft.job_seconds(timing) / 60 + Ft.REPORT_MIN}
print(plan["schedule"], "schedule:", len(plan["jobs"]), "jobs, about", round(plan["minutes"]), "minutes")
'''

FINETUNE = '''
stages = [(arm, [j for j in plan["jobs"] if j[0] == arm and j[1] == 0]) for arm in Ft.ARMS]
stages.append(("second_seed", [j for j in plan["jobs"] if j[1] != 0]))
try:
    for name, jobs in stages:
        if jobs:
            json.dump(jobs, open("/content/stage.json", "w"))
            py("-m", "src.model.vision_finetune", "--jobs", "/content/stage.json", "--workers", 2)
            save("results_after_" + name)
    py("-m", "src.model.vision_finetune", "--shuffled-control", "--report", "--workers", 2)
    print(open("data/processed/vision/finetune/report.md").read())
finally:
    save("vision_results")
'''


def notebook(n_photos: int = N_PHOTOS, minutes: int = MINUTES_FOR_TRAINING) -> dict:
    cells = [
        md("""
# Unwatched Roads: does image augmentation help?

**Before you run:** Runtime > Change runtime type > **T4 GPU**. Then Runtime > **Run all**.

The second cell asks you to upload `vision_colab.zip`. After that it runs by itself, about 2.5 hours in all.
Keep this tab open, and if the browser asks whether this page may download several files, allow it.

A small zip downloads after each stage (`frozen_results.zip`, `results_after_...zip`, and at the end
`vision_results.zip`, which holds everything). Give them to the image-augmentation chat. If the notebook
stops with an error, send the chat the last lines it printed and whatever zips it downloaded.
"""),
        code(f"""
N_PHOTOS = {n_photos}        # random sample of road photos (the whole state does not fit on this machine)
FETCH_WORKERS = 64
MINUTES_FOR_TRAINING = {minutes}    # the fine-tune stage is cut down to fit in this

import torch
assert torch.cuda.is_available(), "No GPU: Runtime > Change runtime type > T4 GPU, then Run all again"
print("GPU:", torch.cuda.get_device_name(0))
"""),
        code(UPLOAD + HELPERS),
        code(INSTALL),
        md("## 1. A small complete run on 50 photos (a few minutes)\n"
           "Fetches the 50 photos the Mac already has, checks they are identical pixel for pixel, then runs every later "
           "stage on just those 50. If anything about this machine is going to break the run, it breaks here."),
        code(SMOKE),
        md("## 2. Photos"),
        code(FETCH),
        md("## 3. Tests\nThe full test suite, including the two tests that need a GPU. The output is saved with the results."),
        code(TESTS),
        md("## 4. Frozen model: one view against the average of 8"),
        code(FROZEN),
        md("## 5. Fine-tune: no augmentation, flips only, full\n"
           "One job is timed first; the schedule is then chosen to fit the time set at the top. "
           "Results download after each arm."),
        code(PLAN),
        code(FINETUNE),
        md("## Done\nGive every zip that downloaded to the image-augmentation chat. `vision_results.zip` holds everything."),
    ]
    return {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "provenance": []},
                                         "kernelspec": {"display_name": "Python 3", "name": "python3"},
                                         "language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 0}


def build(out_dir=DEFAULT_OUT, root=ROOT, n_photos: int = N_PHOTOS) -> dict:
    """Write the notebook and the zip into out_dir. Returns their paths and what the zip holds."""
    box = load_box()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # the Colab scripts travel too: the notebook runs check_identity.py, and the tests under tests/vision cover them
    colab = sorted(f.relative_to(root).as_posix() for f in (Path(root) / "scripts" / "colab").glob("*.py"))
    files = box.bundle_files(root) + colab
    if "data/processed/segments_targets.parquet" not in files:
        raise SystemExit("data/processed/segments_targets.parquet is missing: the labels and folds must be in the package")
    box.scan_for_keys(files, root)
    digests = box.local_digests(Path(root) / "data" / "chips")
    if not digests:
        raise SystemExit("no photos on this machine: the package needs their pixel hashes for the identity check")
    nb_path, zip_path = out_dir / "vision_colab.ipynb", out_dir / "vision_colab.zip"
    nb_path.write_text(json.dumps(notebook(n_photos), indent=1))
    tmp = zip_path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            z.write(Path(root) / rel, rel)
        z.writestr("CODE_HASH", box.code_hash(root) + "\n")
        z.writestr("mac_chip_digests.json", json.dumps(digests, indent=1))
    tmp.replace(zip_path)
    return {"notebook": nb_path, "zip": zip_path, "files": files, "n_digests": len(digests),
            "zip_mb": zip_path.stat().st_size / 1e6, "code_hash": box.code_hash(root)}


if __name__ == "__main__":
    info = build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
    print(f"notebook: {info['notebook']}")
    print(f"zip:      {info['zip']} ({info['zip_mb']:.0f} MB, {len(info['files'])} files, {info['n_digests']} photo hashes)")
    print(f"code fingerprint: {info['code_hash'][:12]}")
