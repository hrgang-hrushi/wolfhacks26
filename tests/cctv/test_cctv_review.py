"""Review sheets, crops, and the grades file."""
import pandas as pd
import pytest
from PIL import Image

from src.pipeline import cctv_review as cr


def grades(rows):
    return pd.DataFrame(rows, columns=cr.GRADE_COLS)


def row(camera=100, view="clear", damage="none", n=1, file=None):
    return (camera, file or f"{camera}/20261003T201800Z.jpg", view, damage, n, "claude", "2026-10-03")


def test_G1_sheet_labels_follow_file_order(fake, tmp_path):
    base, _ = fake.review_base(tmp_path, n=17)
    m = cr.build(base, "r1", sample=400)
    out = base / "review" / "r1"
    assert sorted(f.name for f in (out / "sheets").glob("*.jpg")) == ["sheet_00.jpg", "sheet_01.jpg"]
    assert m["index"].tolist() == list(range(17)) and m.camera_id.is_unique
    for i, f in zip(m["index"], m.file):               # cell i of the sheets shows the still the manifest calls i
        sheet = Image.open(out / "sheets" / f"sheet_{i // 16:02d}.jpg")
        j = i % 16
        cell = sheet.crop(((j % 4) * 392 + 100, (j // 4) * 220 + 50, (j % 4) * 392 + 300, (j // 4) * 220 + 150))
        assert fake.grey_to_index(cell) == fake.grey_to_index(Image.open(base / f))
    with pytest.raises(ValueError, match="no saved daylight stills"):
        cr.build(base, "another-round")


@pytest.mark.parametrize("size,want", [((1280, 720), (1280, 432)), ((896, 504), (896, 302)), ((1920, 1080), (1568, 529))])
def test_G2_crop_is_the_near_part_of_the_frame_at_full_size(size, want):
    im = Image.new("RGB", size, "black")
    im.paste("white", (0, round(size[1] * 0.4), size[0], size[1]))       # the near 60% is white
    c = cr.near_crop(im)
    assert c.size == want and c.convert("L").getextrema() == (255, 255)


def test_G3_grading_list_holds_only_index_camera_and_file(fake, tmp_path):
    base, _ = fake.review_base(tmp_path, n=5)
    cr.build(base, "r1")
    m = pd.read_csv(base / "review" / "r1" / "manifest.csv")
    assert list(m.columns) == ["index", "camera_id", "file"]
    pd.DataFrame({"index": m["index"], "view": "clear"}).to_csv(base / "review" / "r1" / "triage.csv", index=False)
    cr.crops(base, "r1", repeat=2)
    key = pd.read_csv(base / "review" / "r1" / "repeat_key.csv")
    assert list(key.columns) == ["repeat_index", "camera_id", "file"]
    names = {f.name for f in (base / "review" / "r1").rglob("*") if f.is_file()}
    assert not [n for n in names if any(w in n for w in ("pred", "rating", "label", "score"))]


def test_G4_bad_grades_are_refused(fake, tmp_path):
    base, cams = fake.review_base(tmp_path, n=3)
    good = grades([row(100), row(101, "far", ""), row(102, "clear", "pothole"), row(100, n=2)])
    assert cr.validate_grades(good, cams, base)
    for bad, why in [
        (grades([row(100, "blurry", "")]), "bad grade rows"),
        (grades([row(100, "clear", "severe")]), "bad grade rows"),
        (grades([row(100, "clear", "")]), "bad grade rows"),
        (grades([row(100, "far", "none")]), "bad grade rows"),
        (grades([row(100, n=3)]), "bad grade rows"),
        (grades([row(999)]), "bad grade rows"),
        (grades([row(100), row(100)]), "bad grade rows"),
        (grades([row(100, file="100/missing.jpg")]), "not on disk"),
        (good.drop(columns="grader"), "grades columns must be"),
    ]:
        with pytest.raises(ValueError, match=why):
            cr.validate_grades(bad, cams, base)


def test_G5_agreement_and_kappa_match_a_hand_worked_case():
    first = ["none"] * 5 + ["cracks_or_patches"] * 5
    second = ["none"] * 4 + ["cracks_or_patches"] + ["cracks_or_patches"] * 4 + ["none"]
    g = grades([row(100 + i, damage=a) for i, a in enumerate(first)] + [row(100 + i, damage=b, n=2) for i, b in enumerate(second)])
    assert cr.agreement(g) == {"pairs": 10, "agreement": pytest.approx(0.8), "kappa": pytest.approx(0.6)}
    with pytest.raises(ValueError, match="no still was graded in both passes"):
        cr.agreement(g[g["pass"] == 1])


def test_G6_only_clear_views_with_a_decided_grade_enter_the_check():
    g = grades([row(100, "clear", "none"), row(101, "clear", "cant_tell"), row(102, "far", ""), row(103, "unusable", ""),
                row(104, "clear", "pothole"), row(105, "clear", "cracks_or_patches"), row(104, "clear", "none", n=2)])
    d = cr.decided(g)
    assert d.camera_id.tolist() == [100, 104, 105] and d.damage.tolist() == ["none", "pothole", "cracks_or_patches"]


def test_G7_shuffled_repeat_grades_pair_with_the_same_still(fake, tmp_path):
    base, cams = fake.review_base(tmp_path, n=12)
    m = cr.build(base, "r1")
    out = base / "review" / "r1"
    pd.DataFrame({"index": m["index"], "view": ["far" if i % 4 == 3 else "clear" for i in m["index"]]}).to_csv(out / "triage.csv", index=False)
    clear, again = cr.crops(base, "r1", cap=160, repeat=5)
    assert len(clear) == 9 and len(again) == 5

    def grade(image_file):                              # a grader who sees only the picture
        return cr.DAMAGE[fake.grey_to_index(Image.open(image_file)) % 3]
    damage = pd.DataFrame({"index": clear["index"], "damage": [grade(out / "crops" / f"{i:03d}.jpg") for i in clear["index"]]})
    repeat = pd.DataFrame({"repeat_index": range(5), "damage": [grade(out / "repeat" / f"{j:03d}.jpg") for j in range(5)]})
    key = pd.read_csv(out / "repeat_key.csv")
    assert key.camera_id.tolist() != sorted(key.camera_id)          # the repeats really are in another order
    g = cr.assemble(m, pd.read_csv(out / "triage.csv"), damage, key, repeat, "claude", "2026-10-03")
    assert cr.validate_grades(g, cams, base)
    assert (g["pass"] == 1).sum() == 12 and (g["pass"] == 2).sum() == 5 and (g[g["view"] == "far"].damage == "").all()
    assert cr.agreement(g) == {"pairs": 5, "agreement": 1.0, "kappa": 1.0}
    with pytest.raises(ValueError, match="repeat damage: indices missing from the key"):
        cr.assemble(m, pd.read_csv(out / "triage.csv"), damage, key, repeat.assign(repeat_index=repeat.repeat_index + 3))
