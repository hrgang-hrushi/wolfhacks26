"""Prepare camera stills for grading by eye, and check the grades that come back.

Usage:  uv run python -m src.pipeline.cctv_review build --round R [--sample 400]
        uv run python -m src.pipeline.cctv_review crops --round R [--cap 160] [--repeat 40]
        uv run python -m src.pipeline.cctv_review assemble --round R --grader NAME
        uv run python -m src.pipeline.cctv_review validate
        uv run python -m src.pipeline.cctv_review agreement
Reads:  data/raw/cctv/stills.parquet, cameras.parquet and the stills
Writes: data/raw/cctv/review/{round}/sheets/sheet_NN.jpg   numbered contact sheets for sorting views
        data/raw/cctv/review/{round}/manifest.csv          index, camera_id, file (nothing else)
        data/raw/cctv/review/{round}/crops/{index}.jpg     near part of each clear view, full size
        data/raw/cctv/review/{round}/repeat/{n}.jpg        some crops again, renumbered and shuffled
        data/raw/cctv/review/{round}/repeat_key.csv        which still each repeat is (graders never see it)
        data/raw/cctv/grades.csv                           camera_id, file, view, damage, pass, grader, graded_at

The grader fills triage.csv (index, view), damage.csv (index, damage) and repeat_damage.csv
(repeat_index, damage) in the round folder. Nothing a grader sees carries a rating or a prediction.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from src.model.common import write_atomic

OUT = Path("data/raw/cctv")
VIEWS = ("clear", "far", "unusable")
DAMAGE = ("none", "cracks_or_patches", "pothole", "cant_tell")
DECIDED = ("none", "cracks_or_patches", "pothole")
GRADE_COLS = ["camera_id", "file", "view", "damage", "pass", "grader", "graded_at"]
CELL = (392, 220)
GRID = (4, 4)
NEAR_FRAC = 0.6       # cracks only show in the near part of the frame
MAX_SIDE = 1568


def make_sheets(paths, out_dir, start=0):
    """Contact sheets of GRID cells, each labelled with its running index. Returns the sheet files."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    per, (w, h), sheets = GRID[0] * GRID[1], CELL, []
    for n in range(0, len(paths), per):
        sheet = Image.new("RGB", (w * GRID[0], h * GRID[1]), "black")
        draw = ImageDraw.Draw(sheet)
        for j, f in enumerate(paths[n:n + per]):
            x, y = (j % GRID[0]) * w, (j // GRID[0]) * h
            sheet.paste(Image.open(f).convert("RGB").resize((w, h)), (x, y))
            draw.rectangle([x, y + h - 16, x + 34, y + h], fill="black")
            draw.text((x + 3, y + h - 14), f"{start + n + j:03d}", fill="yellow")
        sheets.append(out_dir / f"sheet_{n // per:02d}.jpg")
        sheet.save(sheets[-1], quality=80)
    return sheets


def near_crop(im):
    """The bottom NEAR_FRAC of the frame, at full size unless its longest side exceeds MAX_SIDE."""
    w, h = im.size
    c = im.crop((0, round(h * (1 - NEAR_FRAC)), w, h))
    k = MAX_SIDE / max(c.size)
    return c.resize((round(c.width * k), round(c.height * k))) if k < 1 else c


def build(base, round_id, sample=400, seed=0):
    """Pick the stills to review and write the sheets and the manifest."""
    base = Path(base)
    s = pd.read_parquet(base / "stills.parquet")
    s = s[(s["round"] == round_id) & (s.status == "ok") & ~s.dark]
    if s.empty:
        raise ValueError(f"no saved daylight stills for round {round_id!r}")
    s = s.sample(min(sample, len(s)), random_state=seed).reset_index(drop=True)
    m = pd.DataFrame({"index": s.index, "camera_id": s.camera_id, "file": s.file})   # and nothing else
    out = base / "review" / round_id
    make_sheets([base / f for f in m.file], out / "sheets")
    write_atomic(out / "manifest.csv", lambda f: m.to_csv(f, index=False))
    return m


def crops(base, round_id, cap=160, repeat=40, seed=0):
    """Near-field crops of the views sorted as clear, and a shuffled, renumbered repeat set."""
    out = Path(base) / "review" / round_id
    m = pd.read_csv(out / "manifest.csv")
    t = pd.read_csv(out / "triage.csv")
    clear = m[m["index"].isin(t.loc[t["view"] == "clear", "index"])]
    if len(clear) > cap:
        clear = clear.sample(cap, random_state=seed).sort_values("index")
    for sub in ("crops", "repeat"):
        (out / sub).mkdir(exist_ok=True)
    for i, f in zip(clear["index"], clear.file):
        near_crop(Image.open(Path(base) / f).convert("RGB")).save(out / "crops" / f"{i:03d}.jpg", quality=92)
    again = clear.sample(min(repeat, len(clear)), random_state=seed + 1).reset_index(drop=True)
    for j, f in enumerate(again.file):
        near_crop(Image.open(Path(base) / f).convert("RGB")).save(out / "repeat" / f"{j:03d}.jpg", quality=92)
    key = pd.DataFrame({"repeat_index": again.index, "camera_id": again.camera_id, "file": again.file})
    write_atomic(out / "repeat_key.csv", lambda f: key.to_csv(f, index=False))
    return clear, again


def assemble(manifest, triage, damage, repeat_key=None, repeat_damage=None, grader="", graded_at=""):
    """Grades keyed by (camera_id, file). Pass 1 answers come through the manifest, pass 2 answers
    through the repeat key, so both passes name the same still the same way."""
    for name, answers, key, col in (("triage", triage, manifest, "index"), ("damage", damage, manifest, "index"),
                                    ("repeat damage", repeat_damage, repeat_key, "repeat_index")):
        if answers is not None:
            lost = sorted(set(answers[col]) - set(key[col]))
            if lost or answers[col].duplicated().any():
                raise ValueError(f"{name}: indices missing from the key or given twice: {lost[:5]}")
    g = manifest.merge(triage, on="index").merge(damage, on="index", how="left")
    g = g[(g["view"] != "clear") | g.damage.notna()].copy()     # a clear view nobody graded is not a grade
    g["damage"] = g.damage.where(g["view"] == "clear", "").fillna("")
    g["pass"] = 1
    parts = [g]
    if repeat_damage is not None:
        r = repeat_key.merge(repeat_damage, on="repeat_index")
        parts.append(r.assign(view="clear", **{"pass": 2}))
    out = pd.concat(parts, ignore_index=True).assign(grader=grader, graded_at=graded_at)
    return out[GRADE_COLS]


def validate_grades(grades, cameras, base, files=True):
    """Raise on anything a check could silently miscount. files=False skips the look for each still on
    disk, for a machine that has the grades but not the images."""
    if list(grades.columns) != GRADE_COLS:
        raise ValueError(f"grades columns must be {GRADE_COLS}, got {list(grades.columns)}")
    g = grades.assign(damage=grades.damage.fillna(""))
    bad = g[~g["view"].isin(VIEWS)
            | ((g["view"] == "clear") & ~g.damage.isin(DAMAGE))
            | ((g["view"] != "clear") & (g.damage != ""))
            | ~g["pass"].isin([1, 2])
            | ~g.camera_id.isin(cameras.camera_id)
            | g.duplicated(["camera_id", "file", "pass"], keep=False)]
    if len(bad):
        raise ValueError(f"{len(bad)} bad grade rows, first: {bad.iloc[0].to_dict()}")
    gone = [f for f in g.file.unique() if not (Path(base) / f).exists()] if files else []
    if gone:
        raise ValueError(f"{len(gone)} graded stills are not on disk, first: {gone[0]}")
    return True


def agreement(grades):
    """Pass 1 against pass 2 on the same stills: pairs, raw agreement and Cohen's kappa on damage."""
    g = grades[grades["view"] == "clear"]
    pair = g[g["pass"] == 1].merge(g[g["pass"] == 2], on=["camera_id", "file"], suffixes=("_1", "_2"))
    if pair.empty:
        raise ValueError("no still was graded in both passes")
    po = float((pair.damage_1 == pair.damage_2).mean())
    pe = float(sum((pair.damage_1 == k).mean() * (pair.damage_2 == k).mean() for k in DAMAGE))
    return {"pairs": int(len(pair)), "agreement": po, "kappa": None if pe == 1 else (po - pe) / (1 - pe)}


def decided(grades):
    """One row per camera: its first-pass clear view with a decided grade. Only these enter a check."""
    g = grades[(grades["pass"] == 1) & (grades["view"] == "clear") & grades.damage.isin(DECIDED)]
    return g.sort_values("file").drop_duplicates("camera_id")[["camera_id", "file", "damage"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "crops", "assemble"):
        s = sub.add_parser(name)
        s.add_argument("--round", required=True)
        if name == "build":
            s.add_argument("--sample", type=int, default=400)
        if name == "crops":
            s.add_argument("--cap", type=int, default=160)
            s.add_argument("--repeat", type=int, default=40)
        if name == "assemble":
            s.add_argument("--grader", required=True)
    sub.add_parser("validate")
    sub.add_parser("agreement")
    a = ap.parse_args()

    if a.cmd == "build":
        m = build(OUT, a.round, a.sample)
        print(f"{len(m)} stills on {-(-len(m) // (GRID[0] * GRID[1]))} sheets in {OUT / 'review' / a.round}")
    elif a.cmd == "crops":
        clear, again = crops(OUT, a.round, a.cap, a.repeat)
        print(f"{len(clear)} clear views cropped, {len(again)} repeated")
    elif a.cmd == "assemble":
        d = OUT / "review" / a.round
        rep = pd.read_csv(d / "repeat_damage.csv") if (d / "repeat_damage.csv").exists() else None
        g = assemble(pd.read_csv(d / "manifest.csv"), pd.read_csv(d / "triage.csv"), pd.read_csv(d / "damage.csv"),
                     pd.read_csv(d / "repeat_key.csv") if rep is not None else None, rep, a.grader,
                     pd.Timestamp.now("UTC").isoformat())
        validate_grades(g, pd.read_parquet(OUT / "cameras.parquet"), OUT)
        write_atomic(OUT / "grades.csv", lambda f: g.to_csv(f, index=False))
        print(f"saved {OUT / 'grades.csv'}: {len(g)} rows; views {g[g['pass'] == 1]['view'].value_counts().to_dict()}")
    else:
        g = pd.read_csv(OUT / "grades.csv", keep_default_na=False)
        validate_grades(g, pd.read_parquet(OUT / "cameras.parquet"), OUT)
        print("grades are valid" if a.cmd == "validate" else agreement(g))


if __name__ == "__main__":
    main()
