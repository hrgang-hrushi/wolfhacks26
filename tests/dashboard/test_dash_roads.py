"""The road table: one row per road, blanks kept, flood blank outside the zone, buckets and rank."""
import numpy as np
import pandas as pd
import pytest

from web.tiger import build, schema

PER_ROAD_FILES = ["handoff/predictions_geo.parquet", "handoff/traffic_crash.parquet",
                  "data/processed/segments.parquet", "data/processed/pothole_labels.parquet"]


@pytest.fixture(scope="module")
def roads(fixture_root):
    return build.build_roads(fixture_root)


@pytest.fixture(scope="module")
def real_roads(real_root):
    return build.build_roads(real_root)


def source(root, rel):
    return pd.read_parquet(root / rel)


# ------------------------------------------------------------------------------------------------ R1, R2

def test_R1_one_row_per_road(roads, dash):
    assert len(roads) == dash.N_ROADS and roads.seg_id.is_unique and roads.seg_id.notna().all()


@pytest.mark.parametrize("rel", PER_ROAD_FILES)
def test_R1_a_duplicated_road_in_any_input_is_refused(rel, fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    dash.rewrite(root, rel, lambda d: pd.concat([d, d.iloc[[0]]], ignore_index=True))
    with pytest.raises(ValueError, match="duplicates|same roads"):
        build.build_roads(root)


@pytest.mark.parametrize("rel", PER_ROAD_FILES[1:])
def test_R2_an_input_missing_roads_is_refused_not_filled_with_blanks(rel, fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    dash.rewrite(root, rel, lambda d: d.iloc[2:].reset_index(drop=True))
    with pytest.raises(ValueError, match="same roads"):
        build.build_roads(root)


def test_R2_an_input_with_other_roads_is_refused(fixture_root, tmp_path, dash):
    # the old ROUTEID mismatch: the same number of rows, different ids
    root = dash.copy_root(fixture_root, tmp_path / "r")
    dash.rewrite(root, "handoff/traffic_crash.parquet", lambda d: d.assign(seg_id=d.seg_id.str.replace("ncdot:4", "ncdot:9")))
    with pytest.raises(ValueError, match="same roads"):
        build.build_roads(root)


@pytest.mark.realdata
def test_R1_real_road_count(real_roads):
    assert len(real_roads) == 112_443 and real_roads.seg_id.is_unique


# ------------------------------------------------------------------------------------------------ R3, R4

def test_R3_blank_years_stay_blank_and_land_in_unknown(roads, fixture_root):
    src = source(fixture_root, "handoff/predictions_geo.parquet")
    blank = src.pred_years_to_poor.isna().values
    assert blank.sum() == 6                                             # the fixture plants six
    assert roads.pred_years_to_poor.isna().values.tolist() == blank.tolist()
    assert (roads.repair_bucket[blank] == "unknown").all() and (roads.repair_bucket[~blank] != "unknown").all()
    rows = list(build.to_rows(roads[blank], ["pred_years_to_poor"]))
    assert rows == [(None,)] * 6                                        # blank, never 0


@pytest.mark.parametrize("years, bucket", [(0.0, "fix_now"), (0.01, "within_1y"), (1.0, "within_1y"), (1.01, "within_5y"),
                                           (5.0, "within_5y"), (5.01, "later"), (50.0, "later"), (np.nan, "unknown")])
def test_R4_bucket_edges(years, bucket):
    assert build.repair_bucket([years])[0] == bucket


def test_R4_every_bucket_is_one_the_table_accepts(roads):
    assert set(roads.repair_bucket) <= set(schema.BUCKETS)


@pytest.mark.realdata
def test_R3_R4_real_bucket_counts(real_roads):
    counts = real_roads.repair_bucket.value_counts().reindex(schema.BUCKETS).tolist()
    assert counts == [4_432, 794, 4_699, 100_875, 1_643]
    assert int(real_roads.pred_years_to_poor.isna().sum()) == 1_643


# ------------------------------------------------------------------------------------------------ R5, R6

def test_R5_flood_is_blank_outside_the_zone(roads, fixture_root):
    src = source(fixture_root, "handoff/predictions_geo.parquet")
    assert src.pred_flood.notna().all()                                 # the file carries a number everywhere
    zone = src.in_helene_zone.values == 1
    assert roads.pred_flood[~zone].isna().all() and roads.pred_flood[zone].notna().all()
    assert roads.flood_scored.tolist() == zone.tolist()
    assert np.allclose(roads.pred_flood[zone], src.pred_flood[zone])


@pytest.mark.realdata
def test_R5_real_flood_counts(real_roads):
    assert int(real_roads.pred_flood.isna().sum()) == 79_885 and int(real_roads.pred_flood.notna().sum()) == 32_558


def test_R6_held_out_flags_are_carried_through(roads, fixture_root):
    src = source(fixture_root, "handoff/predictions_geo.parquet")
    for c in ("rate_heldout", "crack_heldout", "flood_heldout"):
        assert roads[c].tolist() == src[c].tolist()
        assert 0 < roads[c].sum() < len(roads)                          # a column of all-true would hide a swap


@pytest.mark.realdata
def test_R6_real_held_out_counts(real_roads):
    assert [int(real_roads[c].sum()) for c in ("rate_heldout", "crack_heldout", "flood_heldout")] == [77_422, 68_349, 32_558]


# ------------------------------------------------------------------------------------------------ R7, S7

def test_R7_not_a_number_becomes_blank_and_infinity_is_refused():
    d = pd.DataFrame({"x": [1.5, np.nan]})
    assert list(build.to_rows(d, ["x"])) == [(1.5,), (None,)]
    with pytest.raises(ValueError, match="x: infinity"):
        list(build.to_rows(pd.DataFrame({"x": [1.0, np.inf]}), ["x"]))
    with pytest.raises(ValueError, match="x: infinity"):
        list(build.to_rows(pd.DataFrame({"x": pd.Series([-np.inf], dtype=object)}), ["x"]))


def test_R7_infinity_in_a_source_file_refuses_the_build(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")

    def plant(d):
        d.loc[4, "pred_rate"] = np.inf
        return d
    dash.rewrite(root, "handoff/predictions_geo.parquet", plant)
    with pytest.raises(ValueError, match="infinity"):
        build.build_roads(root)


def test_S7_every_kind_of_blank_loads_as_none():
    d = pd.DataFrame({
        "f": [np.nan, 2.0], "i": pd.array([pd.NA, 3], dtype="Int64"), "s": pd.array([np.nan, "a"], dtype="str"),
        "o": pd.Series([None, "b"], dtype=object), "b": [True, False],
        "t": pd.to_datetime(["NaT", "2026-09-24 11:06"]).tz_localize("UTC"),
    })
    first, second = list(build.to_rows(d, ["f", "i", "s", "o", "b", "t"]))
    assert first == (None, None, None, None, True, None)
    assert second[:5] == (2.0, 3, "a", "b", False)
    assert [type(v) for v in second[:5]] == [float, int, str, str, bool]          # plain values, not numpy ones
    assert second[5].utcoffset().total_seconds() == 0 and second[5].hour == 11


def test_S7_a_blank_text_never_becomes_the_word_nan(roads):
    rows = list(build.to_rows(roads, ["pothole_city", "treatment_cost", "lanes"]))
    flat = [v for row in rows for v in row]
    assert None in flat
    assert not any(isinstance(v, str) and v.lower() == "nan" for v in flat)
    assert not any(isinstance(v, float) and v != v for v in flat)


def test_S7_a_time_without_a_zone_is_refused():
    d = pd.DataFrame({"t": pd.to_datetime(["2026-09-24 11:06"])})
    with pytest.raises(ValueError, match="t: a time without a zone"):
        list(build.to_rows(d, ["t"]))
    with pytest.raises(ValueError, match="a time without a zone"):
        list(build.to_rows(pd.DataFrame({"t": pd.Series([pd.Timestamp("2026-09-24 11:06")], dtype=object)}), ["t"]))


# ------------------------------------------------------------------------------------------------ R8, R9, R10

def test_R8_a_blank_cost_stays_blank_and_a_real_zero_stays_zero(roads, fixture_root):
    src = source(fixture_root, "data/processed/segments.parquet")
    assert roads.treatment_cost.isna().tolist() == src.pv_TREATMENT_COST.isna().tolist()
    assert roads.treatment_cost.isna().sum() == (src.pv_PMS_TREATMENT_NAME == "Do Nothing").sum() > 0
    assert roads.treatment_cost.iloc[3] == 0.0                          # the planted zero is a cost, not a blank


def test_R8_a_zero_rating_or_lane_count_is_missing_not_zero(roads):
    assert pd.isna(roads.rating.iloc[0]) and pd.isna(roads.lanes.iloc[5])
    assert (roads.rating.dropna() > 0).all()


@pytest.mark.realdata
def test_R8_real_blank_costs(real_roads):
    assert int(real_roads.treatment_cost.isna().sum()) == 63_021
    assert int((real_roads.treatment_cost == 0).sum()) == 8
    assert int(real_roads.rating.isna().sum()) == 3


def test_R9_an_id_that_is_not_a_state_road_is_refused(fixture_root, tmp_path, dash):
    root = dash.copy_root(fixture_root, tmp_path / "r")
    old = source(fixture_root, "handoff/traffic_crash.parquet").seg_id.iloc[0]
    for rel in PER_ROAD_FILES:
        dash.rewrite(root, rel, lambda d: d.assign(seg_id=d.seg_id.replace(old, "city:12345")))
    with pytest.raises(ValueError, match="ncdot:"):
        build.build_roads(root)


def test_R9_the_table_itself_refuses_other_ids():
    check = dict((n, c) for n, _, c in schema.ROADS)["seg_id"]
    assert check == "seg_id LIKE 'ncdot:%'"


def test_R10_damage_comes_from_the_label_the_model_was_scored_on(roads, fixture_root):
    src = source(fixture_root, "data/processed/segments.parquet")
    assert roads.helene_damaged.sum() == src.y_helene_failed.sum() == 10
    assert src.y_helene_damage.sum() == 5                                # the other column would give a different count


@pytest.mark.realdata
def test_R10_real_helene_numbers(real_roads):
    zone = real_roads[real_roads.in_helene_zone]
    assert len(zone) == 32_558 and int(zone.helene_damaged.sum()) == 1_266
    assert int(zone.nlargest(50, "pred_flood").helene_damaged.sum()) == 18


@pytest.mark.realdata
def test_R10_the_readme_example_road(real_roads):
    r = real_roads.set_index("seg_id").loc["ncdot:40002748092:0.940"]
    assert (r.county, r.rating, r.survey_year, r.last_rehab_year, r.from_desc, r.to_desc) == ("Wake", 73.4, 2025, 2010, "SR-2755", "SR-1006")
    assert round(r.pred_rate, 2) == 1.62 and round(r.pred_years_to_poor, 1) == 8.3 and r.rate_heldout
    assert pd.isna(r.pred_flood) and not r.flood_scored


# ------------------------------------------------------------------------------------------------ R11, R12

def test_R11_built_columns_are_the_tables_columns_in_order(roads, fixture_root):
    assert list(roads.columns) == schema.columns("roads")
    assert list(build.build_road_shapes(fixture_root).columns) == schema.columns("road_shapes")


def test_R11_rows_are_picked_by_name_so_a_shuffled_frame_loads_the_same(roads):
    cols = schema.columns("roads")
    shuffled = roads[list(reversed(cols))]
    assert list(build.to_rows(shuffled, cols)) == list(build.to_rows(roads, cols))
    first = next(build.to_rows(roads, cols))
    assert first[cols.index("seg_id")] == roads.seg_id.iloc[0] and first[cols.index("repair_bucket")] == roads.repair_bucket.iloc[0]


def test_R11_a_column_list_that_drifts_from_the_table_is_refused():
    with pytest.raises(ValueError, match="columns differ"):
        build._checked(pd.DataFrame({"seg_id": ["ncdot:1:0.000"], "geojson_text": ["{}"]}), "road_shapes")


def test_R12_no_rank_key_is_a_crash_or_traffic_column():
    assert build.RANK_KEYS == ("bucket_order", "pred_years_to_poor", "rating", "-pred_rate", "seg_id")
    assert not any(word in key for key in build.RANK_KEYS for word in ("crash", "fatal", "serious", "aadt", "safety"))


def test_R12_crash_rate_does_not_move_the_rank(roads):
    worst_first = roads.sort_values("priority_rank")
    opposite = roads.assign(crash_per_mvm=roads.priority_rank.astype(float))          # safest roads ranked first
    aligned = roads.assign(crash_per_mvm=-roads.priority_rank.astype(float))
    shuffled = roads.assign(crash_per_mvm=np.random.default_rng(0).permutation(roads.crash_per_mvm.values))
    for variant in (opposite, aligned, shuffled):
        assert build.rank(variant).tolist() == roads.priority_rank.tolist()
    assert worst_first.repair_bucket.iloc[0] == "fix_now" and worst_first.repair_bucket.iloc[-1] == "unknown"


def test_R12_rank_order_is_bucket_then_years_then_rating_then_wear_then_id():
    d = pd.DataFrame({
        "seg_id": ["ncdot:b:0.000", "ncdot:a:0.000", "ncdot:c:0.000", "ncdot:d:0.000", "ncdot:e:0.000", "ncdot:f:0.000"],
        "pred_years_to_poor": [0.0, 0.0, 0.0, 0.5, np.nan, 0.0],
        "rating": [40.0, 40.0, 30.0, 61.0, 20.0, 40.0],
        "pred_rate": [1.0, 1.0, 0.5, 3.0, 9.0, 2.0],
    })
    d["repair_bucket"] = build.repair_bucket(d.pred_years_to_poor)
    order = d.assign(rank=build.rank(d)).sort_values("rank").seg_id.str[6].tolist()
    # c: lowest rating; f: same rating as a and b but wears faster; a before b by id; d: next bucket; e: unknown, last
    assert order == ["c", "f", "a", "b", "d", "e"]
    assert sorted(build.rank(d)) == [1, 2, 3, 4, 5, 6]


# ------------------------------------------------------------------------------------------------ shapes and places

def test_shapes_are_geojson_lines_in_longitude_latitude_order(fixture_root, roads):
    import json
    shapes = build.build_road_shapes(fixture_root)
    assert shapes.seg_id.tolist() == roads.seg_id.tolist()
    g = json.loads(shapes.geojson.iloc[0])
    assert g["type"] == "LineString" and len(g["coordinates"]) >= 2
    lon, lat = g["coordinates"][0]
    assert -84.5 < lon < -75 and 33.5 < lat < 37
    r = roads.iloc[0]
    assert r.min_lon <= r.mid_lon <= r.max_lon and r.min_lat <= r.mid_lat <= r.max_lat


def test_county_is_split_from_its_code(roads):
    assert set(roads.county) == {"Buncombe", "Mecklenburg", "Wake"} and set(roads.county_code) == {"011", "060", "092"}
