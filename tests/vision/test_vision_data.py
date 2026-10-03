"""Loading chips, the label-and-fold gate, and the model input (src/model/vision_data.py). Ids D1 to D21."""

import os
import zlib

import numpy as np
import pandas as pd
import pytest
import torch

from src.model import augment as A
from src.model import vision_data as V
from src.pipeline.chips import chip_path
from vision_helpers import REAL_JOINED, REAL_TARGETS, ROOT, chips_for, load_box, lopsided_chip, make_table


def hardened_real_table():
    """The real targets file, or None if it is absent or still the pre-hardening version (schema check only)."""
    if not REAL_TARGETS.exists():
        return None
    import pyarrow.parquet as pq
    names = set(pq.ParquetFile(REAL_TARGETS).schema.names)
    return REAL_TARGETS if {"fold", "split_block"} <= names else None


needs_hardened = pytest.mark.skipif(hardened_real_table() is None, reason="waiting for the model-hardening outputs")


# ---------------------------------------------------------------- the table gate (D1 to D6)

@pytest.mark.parametrize("drop", ["fold", "split_block", ["fold", "split_block"]])
def test_d1_a_table_without_folds_is_refused_naming_train_tabular(table, drop):
    with pytest.raises(ValueError, match="train_tabular"):
        V.check_table(table.drop(columns=drop))


def test_d1b_a_missing_file_is_refused(tmp_path):
    with pytest.raises(ValueError, match="train_tabular"):
        V.load_table(tmp_path)


def test_d2_a_fold_that_is_not_crc32_mod_5_is_refused(table):
    bad = table.copy()
    bad.loc[3, "fold"] = (bad.loc[3, "fold"] + 1) % 5
    with pytest.raises(ValueError, match="crc32"):
        V.check_table(bad)
    shuffled = table.copy()
    shuffled["fold"] = np.roll(shuffled.fold.values, 7)  # what a row-dependent splitter could produce
    with pytest.raises(ValueError, match="crc32"):
        V.check_table(shuffled)


def test_d3_blocks_are_5000_metres_not_degrees(table):
    assert V.block_of([504_999.0], [200_000.0])[0] == V.block_of([500_001.0], [200_000.0])[0] == "100_40"
    assert V.block_of([505_001.0], [200_000.0])[0] == "101_40"
    assert V.block_of([-1.0], [-5001.0])[0] == "-1_-2"  # floor, not truncation
    bad = table.copy()
    bad.loc[0, "mid_x"] += 5000.0  # the segment moved a block; its recorded block is now wrong
    with pytest.raises(ValueError, match="5 km block"):
        V.check_table(bad)


def test_d4_duplicate_or_null_seg_id_is_refused(table):
    dup = pd.concat([table, table.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique"):
        V.check_table(dup)
    null = table.copy()
    null.loc[2, "seg_id"] = None
    with pytest.raises(ValueError, match="unique"):
        V.check_table(null)
    nogeo = table.copy()
    nogeo.loc[2, "mid_x"] = np.nan
    with pytest.raises(ValueError, match="mid_x"):
        V.check_table(nogeo)


def test_d5_a_good_table_is_accepted_with_row_order_kept(table, processed_dir):
    d = V.load_table(processed_dir)
    assert list(d.seg_id) == list(table.seg_id) and len(d) == len(table)
    assert V.check_table(table) is table


def test_d6_every_block_maps_to_one_fold(table):
    assert (table.groupby("split_block").fold.nunique() == 1).all()
    assert set(table.fold.unique()) <= set(range(5)) and table.fold.nunique() >= 4
    assert V.fold_of("100_40") == zlib.crc32(b"100_40") % 5


# ---------------------------------------------------------------- chips (D7 to D9)

def test_d7_chip_files_are_named_by_chips_py_and_unique():
    assert V.chip_file("ncdot:10400085041:15.716", "/x").name == chip_path("ncdot:10400085041:15.716").name
    assert V.chip_file("ncdot:10400085041:15.716", "/x").name == "ncdot_10400085041_15.716.npy"
    if not REAL_JOINED.exists():
        pytest.skip("data/raw/ncdot_joined.parquet not on this machine")
    ids = pd.read_parquet(REAL_JOINED, columns=["seg_id"]).seg_id
    names = [chip_path(s).name for s in ids]
    assert len(ids) == 112_443 and len(set(names)) == len(ids)  # no two roads share a chip file


def test_d8_a_bad_chip_raises_naming_the_road_and_tmp_files_are_ignored(table, chips_dir):
    ids = list(table.seg_id[:6])
    chips, blank = V.load_chips(ids, chips_dir, workers=2)
    assert chips.shape == (6, 4, 128, 128) and chips.dtype == np.uint8 and blank.shape == (6,)
    assert np.array_equal(chips[2], np.load(chips_dir / chip_path(ids[2]).name))  # order kept
    (chips_dir / "ncdot_999_0.000.npy.tmp").write_bytes(b"half written")
    assert V.chipped(table, chips_dir).has_chip.all() and V.chip_census(table, chips_dir)["with_chip"] == len(table)
    np.save(chips_dir / chip_path(ids[1]).name, np.zeros((4, 128, 100), dtype=np.uint8))
    with pytest.raises(ValueError, match=ids[1].replace(":", ".")):
        V.load_chips(ids, chips_dir)
    np.save(chips_dir / chip_path(ids[1]).name, np.zeros((4, 128, 128), dtype=np.float32))
    with pytest.raises(ValueError, match="float32"):
        V.load_chips(ids, chips_dir)
    (chips_dir / chip_path(ids[1]).name).write_bytes(b"not an npy file")
    with pytest.raises(ValueError, match="unreadable"):
        V.load_chips(ids, chips_dir)
    os.remove(chips_dir / chip_path(ids[1]).name)
    census = V.chip_census(table, chips_dir)
    assert census == {"total": len(table), "with_chip": len(table) - 1, "without_chip": 1}


def test_d9_a_chip_more_than_5_percent_blank_is_flagged():
    chips = np.stack([lopsided_chip(i) for i in range(3)])
    chips[1, :, :16, :] = 0      # 12.5% of the picture is fill
    chips[2, :, :4, :] = 0       # 3.1%
    chips[0, 0, :64, :] = 0      # one band dark is not blank: the other three have data
    blank = V.blank_fraction(chips)
    assert blank[0] == 0.0 and blank[1] == pytest.approx(0.125) and blank[2] == pytest.approx(4 / 128)
    assert list(V.usable_mask(blank)) == [True, False, True]


# ---------------------------------------------------------------- model input (D10, D11)

def test_d10_model_input_equals_the_landed_dataset(chips_dir, table):
    from src.model import train_vit
    ids = table.seg_id.values[:3]
    chips, _ = V.load_chips(ids, chips_dir)
    orig = train_vit.chip_path
    train_vit.chip_path = lambda s: chips_dir / orig(s).name
    try:
        ds = train_vit.DS(ids, np.zeros(3), np.zeros(3), train=False)
        theirs = torch.stack([ds[i][0] for i in range(3)]).numpy()
    finally:
        train_vit.chip_path = orig
    assert np.array_equal(V.to_model_input(chips), theirs)


def test_d11_model_input_is_rgb_in_order_scaled_and_cropped():
    chip = np.zeros((4, 128, 128), dtype=np.uint8)
    chip[0], chip[1], chip[2], chip[3] = 51, 102, 153, 204
    chip[:, 0, :], chip[:, :, 0], chip[:, 127, :], chip[:, :, 127] = 255, 255, 255, 255  # the outer ring is cropped
    chip[:, 64, 64] = 0
    x = V.to_model_input(chip)
    assert x.shape == (3, 126, 126) and x.dtype == np.float32 and x.flags["C_CONTIGUOUS"]
    assert np.allclose(x[:, 5, 5], [0.2, 0.4, 0.6])  # R, G, B in that order; NIR (0.8) is not an input
    assert x.max() <= 0.6 + 1e-6  # the 255 ring is gone
    assert (x[:, 63, 63] == 0).all()  # chip pixel (64, 64) sits at (63, 63) after the 1 px crop
    batch = V.to_model_input(np.stack([chip, chip]))
    assert batch.shape == (2, 3, 126, 126) and np.array_equal(batch[0], x)


# ---------------------------------------------------------------- dataset (D12 to D15)

def make_ds(table, preset, train, seed=0):
    chips = chips_for(table)
    return V.ViewDataset(chips, table.y_rate.values, table.y_crack.values, preset=preset, seed=seed, train=train)


def test_d12_scoring_reads_repeat_and_training_reads_follow_the_switch(table):
    score = make_ds(table, A.FULL, train=False)
    assert all(torch.equal(score[i][0], score[i][0]) for i in range(5))
    score.set_epoch(3)
    plain = torch.from_numpy(V.to_model_input(score.chips[4]))
    assert torch.equal(score[4][0], plain) and int(score[4][5]) == 0  # never augmented, whatever the epoch
    full = make_ds(table, A.FULL, train=True)
    first = [full[i][0].clone() for i in range(20)]
    full.set_epoch(1)
    assert sum(not torch.equal(first[i], full[i][0]) for i in range(20)) >= 19  # a new draw each epoch
    full.set_epoch(0)
    assert all(torch.equal(first[i], full[i][0]) for i in range(20))  # and the same draw for the same epoch
    none = make_ds(table, A.NONE, train=True)
    none.set_epoch(5)
    assert all(torch.equal(none[i][0], torch.from_numpy(V.to_model_input(none.chips[i]))) for i in range(20))
    assert sum(int(none[i][5]) for i in range(50)) == 0 and sum(int(full[i][5]) for i in range(50)) > 50


def test_d12b_labels_and_masks(table):
    ds = make_ds(table, A.NONE, train=False)
    i_missing = int(np.where(np.isnan(table.y_crack.values) & ~np.isnan(table.y_rate.values))[0][0])
    x, yr, yc, m, idx, n_ops = ds[i_missing]
    assert float(yr) == pytest.approx(table.y_rate.values[i_missing], rel=1e-6) and float(yc) == 0.0
    assert m.tolist() == [1.0, 0.0] and int(idx) == i_missing


def collect_records(ds, workers):
    loader = torch.utils.data.DataLoader(ds, batch_size=16, shuffle=False, num_workers=workers)
    xs, idx, ops = [], [], []
    for x, _, _, _, i, n in loader:
        xs.append(x), idx.append(i), ops.append(n)
    return torch.cat(xs), torch.cat(idx), torch.cat(ops)


def test_d13_worker_count_does_not_change_the_augmentation(table):
    small = table.iloc[:48].reset_index(drop=True)
    a = make_ds(small, A.FULL, train=True, seed=3)
    a.set_epoch(2)
    x0, i0, n0 = collect_records(a, 0)
    x2, i2, n2 = collect_records(a, 2)
    assert torch.equal(i0, i2) and torch.equal(n0, n2) and torch.equal(x0, x2)
    # and two samples in one batch do not share a draw (the classic copied-seed bug)
    records = [a.draw(i)[1] for i in range(48)]
    assert len({(r["view"], r["dx"], r["dy"], round(r["gain"], 6)) for r in records}) >= 45


def test_d14_copies_stay_in_their_roads_fold(table):
    ds = make_ds(table, A.FULL, train=True)
    for k in range(5):
        train, held = V.fold_split(table, k)
        assert len(np.intersect1d(train, held)) == 0 and len(train) + len(held) == len(table)
        assert not set(table.seg_id.values[train]) & set(table.seg_id.values[held])
        assert not set(table.split_block.values[train]) & set(table.split_block.values[held])  # whole blocks
        assert (table.fold.values[held] == k).all() and (table.fold.values[train] != k).all()
    # a copy is made on the fly from row i and carries row i's index, so it can only be in row i's fold
    for epoch in range(4):
        ds.set_epoch(epoch)
        for i in (0, 17, 99):
            assert int(ds[i][4]) == i
    for i in (0, 17, 99):
        assert len({table.fold.values[i] for _ in A.all_views(ds.chips[i])}) == 1


def test_d15_each_road_is_held_out_exactly_once(table):
    held = np.concatenate([V.fold_split(table, k)[1] for k in range(5)])
    assert sorted(held) == list(range(len(table)))


# ---------------------------------------------------------------- fingerprints and guards (D16 to D19, D21)

def test_d16_the_road_list_hash_is_stable_and_order_free(table):
    ids = list(table.seg_id)
    assert V.manifest_hash(ids) == V.manifest_hash(ids[::-1]) == V.manifest_hash(np.array(ids))
    assert V.manifest_hash(ids) != V.manifest_hash(ids[:-1])
    assert V.manifest_hash(ids) != V.manifest_hash(ids[:-1] + ["ncdot:other:0.000"])


def test_d17_cross_fold_neighbours_are_counted():
    def pair(distance, folds):
        return pd.DataFrame({"mid_x": [500_000.0, 500_000.0 + distance], "mid_y": [200_000.0, 200_000.0],
                             "fold": folds})
    assert V.cross_fold_neighbours(pair(50, [0, 1])) == 1   # chips overlap across a held-out boundary
    assert V.cross_fold_neighbours(pair(100, [0, 1])) == 0  # too far apart to overlap
    assert V.cross_fold_neighbours(pair(50, [2, 2])) == 0   # same fold: not a leak


def test_d18_the_code_hash_is_stable_changes_with_a_file_and_matches_the_driver(tmp_path):
    for rel, text in {"src/a.py": "x = 1\n", "tests/vision/t.py": "y = 2\n", "scripts/cloud/box.py": "z = 3\n",
                      "uv.lock": "lock\n", "src/a 2.py": "duplicate\n"}.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    h = V.code_hash(tmp_path)
    assert h == V.code_hash(tmp_path) == load_box().code_hash(tmp_path)
    (tmp_path / "src/a.py").write_text("x = 2\n")
    assert V.code_hash(tmp_path) != h
    assert V.code_hash(ROOT) == load_box().code_hash(ROOT)  # the real tree, both implementations
    (tmp_path / "CODE_HASH").write_text(h + "\n")
    with pytest.raises(RuntimeError, match="not the code that was pushed"):
        V.check_shipped_code(tmp_path)
    (tmp_path / "CODE_HASH").write_text(V.code_hash(tmp_path) + "\n")
    assert V.check_shipped_code(tmp_path) == V.code_hash(tmp_path)


def test_d19_writes_are_whole_or_absent_and_stay_under_the_output_root(tmp_path):
    root = tmp_path / "vision"
    target = root / "frozen" / "metrics.json"
    V.atomic_write(target, lambda tmp: tmp.write_text("ok"), out_root=root)
    assert target.read_text() == "ok" and not list(root.rglob("*.tmp"))

    def boom(tmp):
        tmp.write_text("partial")
        raise RuntimeError("disk full")

    other = root / "frozen" / "report.md"
    with pytest.raises(RuntimeError, match="disk full"):
        V.atomic_write(other, boom, out_root=root)
    assert not other.exists() and not list(root.rglob("*.tmp"))
    with pytest.raises(RuntimeError):
        V.atomic_write(target, boom, out_root=root)
    assert target.read_text() == "ok"  # a failed rewrite leaves the old file intact
    for outside in (tmp_path / "segments.parquet", tmp_path / "chips" / "x.npy", root / ".." / "vit_frozen.parquet"):
        with pytest.raises(ValueError, match="refusing to write outside"):
            V.atomic_write(outside, lambda tmp: tmp.write_text("no"), out_root=root)
        assert not outside.exists()
    V.save_npy(root / "frozen" / "e.npy", np.arange(4), out_root=root)
    assert np.array_equal(np.load(root / "frozen" / "e.npy"), np.arange(4))
    assert V.OUT_ROOT.name == "vision" and V.OUT_ROOT.parent.name == "processed"


def test_d19b_the_default_output_root_refuses_the_shared_tables():
    for name in ("segments.parquet", "segments_targets.parquet", "vit_frozen.parquet"):
        with pytest.raises(ValueError, match="refusing to write outside"):
            V.atomic_write(V.PROCESSED / name, lambda tmp: tmp.write_text("no"))
    with pytest.raises(ValueError, match="refusing to write outside"):
        V.atomic_write(V.CHIPS / "ncdot_1_0.000.npy", lambda tmp: tmp.write_text("no"))


@pytest.mark.parametrize("column", V.HASHED_COLUMNS)
def test_d21_changing_any_hashed_column_changes_the_table_hash(table, column):
    assert set(V.HASHED_COLUMNS) >= {"y_helene_failed", "in_helene_zone", "split_block", "mid_x", "mid_y"}
    base = V.table_hash(table)
    assert base == V.table_hash(table.copy())
    changed = table.copy()
    if column == "seg_id":
        changed.loc[5, column] = "ncdot:changed:0.000"
    elif column == "split_block":
        changed.loc[5, column] = "0_0"
    else:
        old = changed.loc[5, column]
        changed.loc[5, column] = 1.0 if (pd.isna(old) or old != 1.0) else 0.0
    assert V.table_hash(changed) != base
    assert V.table_hash(table.drop(columns=column)) != base
    assert V.table_hash(table.assign(pv_COUNTY="x")) == base  # a column this change does not read


def test_weights_hash_changes_with_the_weights(tiny_net):
    h = V.weights_hash(tiny_net)
    assert h == V.weights_hash(tiny_net)
    with torch.no_grad():
        tiny_net.h.bias.add_(1.0)
    assert V.weights_hash(tiny_net) != h


# ---------------------------------------------------------------- the real table (D20)

@needs_hardened
def test_d20_the_real_table_passes_the_gate_and_matches_the_pinned_counts():
    d = V.load_table(REAL_TARGETS.parent)
    assert len(d) == 112_443
    assert int(d.y_rate.notna().sum()) == 77_422
    assert int(d.y_crack.notna().sum()) == 68_349 and int((d.y_crack == 1).sum()) == 10_766
    assert d.split_block.nunique() == 5_040 and sorted(d.fold.unique()) == [0, 1, 2, 3, 4]
    share = d[d.y_rate.notna()].fold.value_counts(normalize=True)
    assert share.min() >= 0.15 and share.max() <= 0.25
    assert (d.groupby("split_block").fold.nunique() == 1).all()
    for k in range(5):
        train, held = V.fold_split(d, k)
        assert not set(d.split_block.values[train]) & set(d.split_block.values[held])
    assert {"y_helene_failed", "in_helene_zone", "pv_COUNTY"} <= set(d.columns)
