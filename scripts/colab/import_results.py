"""Bring a results zip downloaded from Colab into data/processed/vision.

    python scripts/colab/import_results.py ~/Downloads/vision_results.zip

The zip is unpacked into a temporary folder first and only then copied over, so a bad download never
leaves half a result set. Only the result folders and by-product files this change writes are accepted.
"""

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "data" / "processed" / "vision"
ALLOWED_TOP = {"frozen", "finetune", "ndvi_stats.parquet", "vit_frozen_statewide.parquet",
               "vit_frozen_statewide_8view.parquet", "chip_index.parquet", "colab_tests.txt", "colab_run.json"}


def import_results(zip_path, out_root=OUT_ROOT) -> list:
    """Unpack zip_path into out_root. Returns the relative paths written."""
    out_root = Path(out_root)
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        for n in names:
            p = Path(n)
            if p.is_absolute() or ".." in p.parts or p.parts[0] not in ALLOWED_TOP:
                raise ValueError(f"unexpected file in the results zip: {n}")
        bad = z.testzip()
        if bad:
            raise ValueError(f"the zip is damaged at {bad}; download it again")
        with tempfile.TemporaryDirectory(dir=out_root.parent) as tmp:
            z.extractall(tmp)
            for n in names:
                dest = out_root / n
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(Path(tmp) / n), dest)
    return names


if __name__ == "__main__":
    written = import_results(sys.argv[1])
    print(f"{len(written)} files written under {OUT_ROOT}")
    for report in ("frozen/report.md", "finetune/report.md"):
        if report in written:
            print(f"--- {report}")
            print((OUT_ROOT / report).read_text())
