import zlib
from pathlib import Path

import pandas as pd

from src.model.common import N_FOLDS, add_folds, block_id, fold_of, write_split


def test_F1_block_is_the_floor_of_metres_over_5000_including_negatives():
    x = pd.Series([0.0, 4999.9, 5000.0, -0.1, -5000.1])
    y = pd.Series([0.0, 0.0, 12345.0, -0.1, 9999.0])
    assert block_id(x, y).tolist() == ["0_0", "0_0", "1_2", "-1_-1", "-2_1"]


def test_F2_fold_is_crc32_of_the_block_id_mod_5():
    assert N_FOLDS == 5
    # pinned values: a change of hash or modulus must fail here
    assert [fold_of(b) for b in ("0_0", "123_45", "-1_-2", "240_150")] == [3, 3, 2, 3]
    assert fold_of("17_3") == zlib.crc32(b"17_3") % 5


def test_F3_segments_in_one_block_share_a_fold(table):
    d = add_folds(table)
    assert (d.groupby("split_block").fold.nunique() == 1).all()
    assert set(d.fold) == {0, 1, 2, 3, 4}
    assert d.fold.tolist() == [fold_of(b) for b in d.split_block]


def test_F4_a_segments_fold_does_not_depend_on_the_other_rows(table):
    full = add_folds(table).set_index("seg_id").fold
    half = add_folds(table.sample(frac=0.5, random_state=1)).set_index("seg_id").fold
    assert (full[half.index] == half).all()
    extra = table.assign(seg_id="city:" + table.seg_id, mid_x=table.mid_x + 123456)
    both = add_folds(pd.concat([table, extra], ignore_index=True)).set_index("seg_id").fold
    assert (both[full.index] == full).all()


def test_F5_split_file_round_trips(table, tmp_path):
    d = add_folds(table)
    write_split(d, tmp_path / "split.parquet")
    back = pd.read_parquet(tmp_path / "split.parquet")
    assert back.columns.tolist() == ["seg_id", "split_block", "fold"]
    assert back.equals(d[["seg_id", "split_block", "fold"]])
    assert not (tmp_path / "split.parquet.tmp").exists()


def test_F6_no_script_rebuilds_folds_with_groupkfold():
    for f in Path("src/model").glob("*.py"):
        assert "GroupKFold" not in f.read_text(), f
