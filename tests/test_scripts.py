"""End-to-end runs of the two tabular scripts on a fixture directory (never the real data or handoff/)."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from src.model import common, final_ablation, train_tabular

pytestmark = pytest.mark.usefixtures("small_models")

ABLATION_COLS = ["model", "rate_mae", "rate_spearman", "crack_aucpr", "flood_p50", "flood_aucpr", "n_rate",
                 "rate_mae_naive", "crack_prevalence", "n_scored"]


def test_S1_train_tabular_writes_targets_split_and_ablation(scripts_run):
    p = scripts_run["p"]
    t = pd.read_parquet(p / "segments_targets.parquet")
    assert {"split_block", "fold", "pv_age_at_survey", "y_rate", "y_years_to_poor", "y_crack", "tn_elev"} <= set(t.columns)
    assert pd.read_parquet(p / "split.parquet").columns.tolist() == ["seg_id", "split_block", "fold"]
    a = pd.read_csv(p / "ablation.csv")
    assert a.columns.tolist() == ABLATION_COLS
    assert a.model.tolist() == ["baseline: pavement + traffic", "+ terrain"]
    assert (a.rate_mae < a.rate_mae_naive).all()                  # the fixture has real signal
    assert (a.n_rate == t.y_rate.notna().sum()).all() and (a.n_scored == a.n_rate).all()


def test_S2_running_twice_gives_the_same_ablation(scripts_run):
    train_tabular.main(scripts_run["p"])
    assert (scripts_run["p"] / "ablation.csv").read_bytes() == scripts_run["first_csv"]


def test_S3_final_ablation_runs_without_embeddings(scripts_run):
    a = pd.read_csv(scripts_run["p"] / "ablation_final.csv")
    assert a.model.tolist() == ["ALL: baseline", "ALL: + terrain"]
    assert (a.n_scored == a.n_rate).all() and (a.rate_mae < a.rate_mae_naive).all()
    assert (scripts_run["p"] / "predictions.parquet").exists()


def test_S5_map_file_goes_only_to_the_given_handoff_dir(scripts_run):
    assert scripts_run["tracked_untouched"]
    g = gpd.read_parquet(scripts_run["handoff"] / "predictions_geo.parquet")
    geom = gpd.read_parquet(scripts_run["p"] / "segments_geom.parquet")
    assert g.crs == geom.crs
    assert g.seg_id.tolist() == geom.seg_id.tolist() and g.seg_id.is_unique
    assert g.columns.tolist() == ["seg_id", "geometry", "pred_rate", "pred_years_to_poor", "pred_crack", "pred_flood",
                                  "in_helene_zone", "rate_heldout", "crack_heldout", "flood_heldout"]
    assert g.geometry.notna().all() and not g.geometry.is_empty.any()
    pred = pd.read_parquet(scripts_run["p"] / "predictions.parquet")
    assert np.allclose(g.pred_rate, pred.pred_rate) and g.rate_heldout.tolist() == pred.rate_heldout.tolist()


def _with_embeddings(write_dir, tmp_path, seg_ids, terrain=True):
    p = write_dir(tmp_path / "processed", terrain=terrain)
    train_tabular.main(p)
    rng = np.random.default_rng(0)
    emb = pd.DataFrame(rng.normal(size=(len(seg_ids), 16)), columns=[f"im_emb{i}" for i in range(16)])
    emb.insert(0, "seg_id", seg_ids)
    emb.to_parquet(p / "vit_frozen.parquet")
    final_ablation.main(p, handoff_dir=tmp_path / "handoff")
    return pd.read_csv(p / "ablation_final.csv")


def test_S4_with_embeddings_the_imagery_rows_run(write_dir, tmp_path, table):
    a = _with_embeddings(write_dir, tmp_path, table.seg_id[::2].tolist())
    assert a.model.tolist() == ["ALL: baseline", "ALL: + terrain", "CHIPPED: baseline", "CHIPPED: + terrain",
                                "CHIPPED: + frozen DINOv2"]
    assert (a.n_rate[2:] < a.n_rate[0]).all() and a.rate_mae[2:].notna().all()
    assert a.rate_mae_naive.notna().all() and (a.n_scored == a.n_rate).all()
    assert a.rate_mae_naive[2] != a.rate_mae_naive[0]       # the reference is computed on the row's own subset


def test_S6_embeddings_matching_no_segment_give_empty_rows_not_a_crash(write_dir, tmp_path):
    a = _with_embeddings(write_dir, tmp_path, ["ncdot:nowhere:0.000", "ncdot:nowhere:1.000"])
    chipped = a[a.model.str.startswith("CHIPPED")]
    assert len(chipped) == 3 and (chipped.n_rate == 0).all() and (chipped.n_scored == 0).all()
    assert chipped[["rate_mae", "rate_spearman", "crack_aucpr", "flood_aucpr", "rate_mae_naive"]].isna().all().all()


def test_S7_without_terrain_there_is_no_terrain_row(write_dir, tmp_path, table):
    a = _with_embeddings(write_dir, tmp_path, table.seg_id[::2].tolist(), terrain=False)
    assert a.model.tolist() == ["ALL: baseline", "CHIPPED: baseline", "CHIPPED: + frozen DINOv2"]
    p = tmp_path / "processed"
    assert pd.read_csv(p / "ablation.csv").model.tolist() == ["baseline: pavement + traffic"]
    pred = pd.read_parquet(p / "predictions.parquet")           # the map model falls back to the baseline
    assert pred.pred_rate.notna().all() and pred.rate_heldout.sum() == pd.read_csv(p / "ablation.csv").n_rate[0]


def test_S8_both_scripts_call_the_leak_tripwire(write_dir, tmp_path, monkeypatch):
    p = write_dir(tmp_path / "processed")
    train_tabular.main(p)
    monkeypatch.setattr(common, "LEAK_SPEARMAN", -1.0)        # any score now counts as too good
    with pytest.raises(RuntimeError, match="leaking"):
        train_tabular.main(p)
    with pytest.raises(RuntimeError, match="leaking"):
        final_ablation.main(p, handoff_dir=tmp_path / "handoff")


def test_S9_map_export_refuses_geometry_that_covers_different_segments(scripts_run, tmp_path):
    p = scripts_run["p"]
    pred = pd.read_parquet(p / "predictions.parquet")
    geom = gpd.read_parquet(p / "segments_geom.parquet")
    for bad in (geom.iloc[:-5], pd.concat([geom, geom.tail(1).assign(seg_id="ncdot:extra:0.000")])):
        q = tmp_path / f"geom{len(bad)}"
        q.mkdir()
        bad.to_parquet(q / "segments_geom.parquet")
        with pytest.raises(ValueError, match="different segments"):
            final_ablation.export_geo(pred, q, tmp_path / "handoff")
    assert not (tmp_path / "handoff" / "predictions_geo.parquet").exists()


def test_final_ablation_refuses_targets_without_folds(write_dir, tmp_path):
    p = write_dir(tmp_path / "processed")
    pd.read_parquet(p / "segments.parquet").to_parquet(p / "segments_targets.parquet")
    with pytest.raises(SystemExit, match="train_tabular"):
        final_ablation.main(p, handoff_dir=tmp_path / "handoff")
