"""On Colab: check that the photos fetched there have the same pixels as the ones on the Mac.

    python scripts/colab/check_identity.py [mac_chip_digests.json] [data/chips]

The package carries the pixel hashes of the photos the Mac already holds. Exit status 0 only if at
least MIN_COMMON of them are present here and none differs.
"""

import glob
import hashlib
import json
import os
import sys

import numpy as np

MIN_COMMON = 45


def digests(chips_dir: str) -> dict:
    return {os.path.basename(f): hashlib.sha256(np.load(f).tobytes()).hexdigest()
            for f in sorted(glob.glob(os.path.join(chips_dir, "*.npy")))}


def check(mac: dict, here: dict, min_common: int = MIN_COMMON) -> tuple:
    """(ok, message). Only differing pixels are a failure of identity; too few common photos is a failed fetch."""
    common = sorted(set(mac) & set(here))
    differ = [n for n in common if mac[n] != here[n]]
    if differ:
        return False, f"FAIL: {len(differ)} of {len(common)} photos differ from the Mac's, e.g. {differ[:3]}"
    if len(common) < min_common:
        return False, f"FAIL: only {len(common)} of the Mac's {len(mac)} photos were fetched here (need {min_common})"
    return True, f"OK: {len(common)} photos are identical, pixel for pixel, to the Mac's"


if __name__ == "__main__":
    mac_file = sys.argv[1] if len(sys.argv) > 1 else "mac_chip_digests.json"
    chips_dir = sys.argv[2] if len(sys.argv) > 2 else "data/chips"
    with open(mac_file) as f:
        ok, message = check(json.load(f), digests(chips_dir))
    print(message)
    sys.exit(0 if ok else 1)
