"""Build the Google Colab package for the vision comparisons: one notebook and one zip.

    python scripts/colab/build_package.py [output_dir]

Colab is the route for a network that blocks the ports a rented box needs: everything goes through the
browser. The zip holds the same files `scripts/cloud/box.py push` would send (code, the segment table,
the labels and folds), the code fingerprint, and the pixel hashes of the photos this machine already
has, so the notebook can check that Colab fetches the same photos. The notebook fetches a random
sample of photos (Colab's free machine cannot hold the whole state), runs the tests, the frozen
comparison and the fine-tune comparison, and offers the results as a zip to download.
"""

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "processed" / "vision" / "colab"
N_PHOTOS = 40_000  # 2.6 GB in memory; Colab's free machine has about 12 GB


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


def notebook(n_photos: int = N_PHOTOS) -> dict:
    cells = [
        md("""
# Unwatched Roads: does image augmentation help?

**Before you run:** Runtime > Change runtime type > **T4 GPU**. Then Runtime > **Run all**.

The second cell asks you to upload `vision_colab.zip`. After that it runs by itself for about two hours.
Keep this tab open. Two downloads appear on the way: `frozen_results.zip` after roughly 30 minutes and
`vision_results.zip` at the end. Give both to the image-augmentation chat.
"""),
        code(f"""
N_PHOTOS = {n_photos}        # random sample of road photos (the whole state does not fit on this machine)
FETCH_WORKERS = 64
MINUTES_FOR_TRAINING = 150   # the fine-tune schedule is chosen to fit in this

import torch
assert torch.cuda.is_available(), "No GPU: Runtime > Change runtime type > T4 GPU, then Run all again"
print("GPU:", torch.cuda.get_device_name(0))
"""),
        code("""
import os, zipfile
if not os.path.exists("/content/hack/CODE_HASH"):
    from google.colab import files
    print("Choose vision_colab.zip")
    uploaded = files.upload()
    zipfile.ZipFile(next(iter(uploaded))).extractall("/content/hack")
os.chdir("/content/hack")
print("code fingerprint:", open("CODE_HASH").read().strip())
"""),
        code("""
!pip -q install timm geopandas rasterio pystac-client planetary-computer lightgbm pytest 2>&1 | tail -2
!python -c "import torch, timm, lightgbm, geopandas, rasterio; from src.model import train_vit; print('imports ok')"
"""),
        md("## 1. Photos\nFetch the 50 photos the Mac already has and check they are identical, then the full sample."),
        code("""
!python -m src.pipeline.chips --limit 50 --seed 0 --workers 16 2>&1 | tail -2
!python scripts/colab/check_identity.py mac_chip_digests.json data/chips
import subprocess, sys
assert subprocess.run([sys.executable, "scripts/colab/check_identity.py"]).returncode == 0, "photos differ: stop here"
"""),
        code("""
!python -u -m src.pipeline.chips --limit $N_PHOTOS --seed 0 --workers $FETCH_WORKERS 2>&1 | tail -3
!python -u -m src.pipeline.chips --limit $N_PHOTOS --seed 0 --workers $FETCH_WORKERS 2>&1 | tail -2   # retry any failures
import glob
print(len(glob.glob("data/chips/*.npy")), "photos on this machine")
"""),
        md("## 2. Tests\nThe full test suite, including the two tests that need a GPU. The output is saved with the results."),
        code("""
import subprocess, sys, pathlib
pathlib.Path("data/processed/vision").mkdir(parents=True, exist_ok=True)
t = subprocess.run([sys.executable, "-m", "pytest", "tests/vision", "-q", "-rs", "-p", "no:cacheprovider"],
                   capture_output=True, text=True)
pathlib.Path("data/processed/vision/colab_tests.txt").write_text(t.stdout[-6000:] + t.stderr[-2000:])
print(t.stdout[-1500:])
print("TESTS PASSED" if t.returncode == 0 else "TESTS FAILED (continuing; the output is saved with the results)")
"""),
        md("## 3. Frozen model: one view against the average of 8"),
        code("""
!python -u -m src.model.vision_frozen
print(open("data/processed/vision/frozen/report.md").read())
"""),
        code("""
import zipfile, pathlib
def pack(name, skip=(".npy",)):
    root = pathlib.Path("data/processed/vision")
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(root.rglob("*")):
            if f.is_file() and f.suffix not in skip and "colab" not in f.parts:
                z.write(f, f.relative_to(root).as_posix())
    return name
from google.colab import files
files.download(pack("/content/frozen_results.zip"))
"""),
        md("## 4. Fine-tune: no augmentation, flips only, full\nOne job is timed first; the schedule is then chosen to fit the time set at the top."),
        code("""
!python -u -m src.model.vision_finetune --time-only --workers 2 2>&1 | tail -4
import json
from src.model import vision_finetune as Ft
timing = json.load(open("data/processed/vision/finetune/timing.json"))
try:
    plan = Ft.plan_grid(timing, dph=0.0, cap_left=1.0, minutes_left=MINUTES_FOR_TRAINING, reserve_min=5)
except ValueError as e:  # neither schedule fits the time set at the top: run the smaller one anyway and say so
    print("does not fit the time budget:", e)
    plan = {"schedule": "reduced (over the time budget)", "jobs": [list(j) for j in Ft.reduced_schedule()],
            "minutes": (len(Ft.reduced_schedule()) + 1) * Ft.job_seconds(timing) / 60 + Ft.REPORT_MIN}
json.dump(plan, open("/content/jobs.json", "w"))
print(plan["schedule"], "schedule:", len(plan["jobs"]), "jobs, about", round(plan["minutes"]), "minutes")
"""),
        code("""
!python -u -m src.model.vision_finetune --jobs /content/jobs.json --shuffled-control --report --workers 2
print(open("data/processed/vision/finetune/report.md").read())
"""),
        md("## 5. Results\nDownload and hand to the image-augmentation chat."),
        code("""
files.download(pack("/content/vision_results.zip"))
"""),
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
            "zip_mb": zip_path.stat().st_size / 1e6}


if __name__ == "__main__":
    info = build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
    print(f"notebook: {info['notebook']}")
    print(f"zip:      {info['zip']} ({info['zip_mb']:.0f} MB, {len(info['files'])} files, {info['n_digests']} photo hashes)")
