"""The risk file: every road once, sorted, blanks kept, the same bytes every time."""
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from web.tiger import build, export

# the file's contract, typed out here on purpose: a change to the columns has to change this list too
EXPECTED_HEADER = ["seg_id", "route_id", "route", "county", "beg_mp", "end_mp", "from_desc", "to_desc", "length_mi", "mid_lon",
                   "mid_lat", "rating", "survey_year", "wear_rate_pred", "wear_rate_heldout", "years_to_poor", "repair_bucket",
                   "crack_risk", "crack_heldout", "flood_risk", "flood_scored", "flood_heldout"]


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], pd.DataFrame(rows[1:], columns=rows[0])


@pytest.fixture(scope="module")
def written(fixture_root, tmp_path_factory):
    out = tmp_path_factory.mktemp("export")
    n, size, sha = export.export(fixture_root, out)
    header, frame = read(out / export.FILE_NAME)
    return dict(out=out, n=n, size=size, sha=sha, header=header, frame=frame, roads=build.build_roads(fixture_root))


@pytest.fixture(scope="module")
def real_written(real_root, tmp_path_factory):
    out = tmp_path_factory.mktemp("export_real")
    n, size, sha = export.export(real_root, out)
    header, frame = read(out / export.FILE_NAME)
    return dict(out=out, n=n, size=size, sha=sha, frame=frame)


# ------------------------------------------------------------------------------------------------ E1, E2

def test_E1_every_road_once_sorted_by_id(written, dash):
    f = written["frame"]
    assert len(f) == written["n"] == dash.N_ROADS and f.seg_id.is_unique
    assert f.seg_id.tolist() == sorted(written["roads"].seg_id.tolist())


@pytest.mark.realdata
def test_E1_real_row_count(real_written):
    f = real_written["frame"]
    assert len(f) == 112_443 and f.seg_id.is_unique and f.seg_id.tolist() == sorted(f.seg_id.tolist())


def test_E2_the_same_input_gives_the_same_bytes(written, fixture_root, tmp_path):
    again = export.export(fixture_root, tmp_path / "again")
    assert again == (written["n"], written["size"], written["sha"])
    assert (tmp_path / "again" / export.FILE_NAME).read_bytes() == (written["out"] / export.FILE_NAME).read_bytes()
    assert (tmp_path / "again" / "risk_dictionary.json").read_bytes() == (written["out"] / "risk_dictionary.json").read_bytes()


def test_E2_the_order_of_the_input_rows_does_not_matter(written):
    roads = written["roads"]
    shuffled = roads.sample(frac=1, random_state=3)
    a, b = io.BytesIO(), io.BytesIO()
    export.write_risk_csv(export.rows_from_frame(roads), a)
    export.write_risk_csv(export.rows_from_frame(shuffled), b)
    assert a.getvalue() == b.getvalue() and hashlib.sha256(a.getvalue()).hexdigest() == written["sha"]


@pytest.mark.realdata
def test_E2_real_file_is_identical_on_a_second_run(real_written, real_root, tmp_path):
    assert export.export(real_root, tmp_path / "again")[2] == real_written["sha"]


# ------------------------------------------------------------------------------------------------ E3, E6

def test_E3_blank_stays_blank(written):
    f, roads = written["frame"], written["roads"].sort_values("seg_id").reset_index(drop=True)
    assert (f.years_to_poor == "").tolist() == roads.pred_years_to_poor.isna().tolist() and (f.years_to_poor == "").sum() == 6
    assert (f.repair_bucket[f.years_to_poor == ""] == "unknown").all()
    assert (f.rating == "").sum() == 1                                     # the road whose rating is missing
    everything = "\n".join(f.astype(str).agg(",".join, axis=1)).lower()
    assert "nan" not in everything and "none" not in everything and "<na>" not in everything


@pytest.mark.parametrize("value, text", [(None, ""), (float("nan"), ""), (float("inf"), ""), (True, "true"), (False, "false"),
                                         (0.0, "0.0"), (73.4, "73.4"), (1.6233952729806722, "1.623395"), (2025, "2025"),
                                         ("SR-2755", "SR-2755"), (0, "0")])
def test_E3_one_cell_as_text(value, text):
    assert export.format_value(value) == text


def test_E3_a_numpy_boolean_is_written_the_same_way():
    import numpy as np
    assert export.format_value(np.bool_(True)) == "true" and export.format_value(np.bool_(False)) == "false"
    assert export.format_value(np.float64(73.4)) == "73.4" and export.format_value(np.int64(2025)) == "2025"


def test_E6_flood_is_blank_outside_the_zone_and_the_flags_are_there(written):
    f, roads = written["frame"], written["roads"].sort_values("seg_id").reset_index(drop=True)
    outside = f.flood_scored == "false"
    assert outside.sum() == 200 and (f.flood_risk[outside] == "").all() and (f.flood_risk[~outside] != "").all()
    for column, source in (("wear_rate_heldout", "rate_heldout"), ("crack_heldout", "crack_heldout"), ("flood_heldout", "flood_heldout")):
        assert set(f[column]) == {"true", "false"}
        assert (f[column] == "true").tolist() == roads[source].tolist()


@pytest.mark.realdata
def test_E3_E6_real_blanks(real_written):
    f = real_written["frame"]
    assert int((f.years_to_poor == "").sum()) == 1_643
    assert int((f.flood_risk == "").sum()) == 79_885 and int((f.flood_scored == "true").sum()) == 32_558
    assert [int((f[c] == "true").sum()) for c in ("wear_rate_heldout", "crack_heldout", "flood_heldout")] == [77_422, 68_349, 32_558]
    assert f.repair_bucket.value_counts().to_dict() == {"later": 100_875, "within_5y": 4_699, "fix_now": 4_432,
                                                        "unknown": 1_643, "within_1y": 794}


# ------------------------------------------------------------------------------------------------ E4, E5

def test_E4_the_header_is_the_contract(written):
    assert written["header"] == EXPECTED_HEADER == export.HEADER


def test_E4_every_column_is_described(written):
    d = json.loads((written["out"] / "risk_dictionary.json").read_text())
    assert [c["name"] for c in d["columns"]] == EXPECTED_HEADER
    assert all(len(c["description"]) > 10 for c in d["columns"])
    assert d["blank"].startswith("an empty field") and len(d["what_this_cannot_claim"]) >= 5
    assert not any("crash" in name for name in EXPECTED_HEADER)            # an open question for the user, so left out


def test_E4_a_row_of_the_wrong_width_is_refused():
    with pytest.raises(ValueError, match="values, not 22"):
        list(export.iter_risk_csv([("ncdot:1:0.000", 1.0)]))


def test_E5_longitude_then_latitude_inside_north_carolina(written):
    f = written["frame"]
    assert written["header"].index("mid_lon") + 1 == written["header"].index("mid_lat")
    lon, lat = f.mid_lon.astype(float), f.mid_lat.astype(float)
    assert lon.between(-84.5, -75.3).all() and lat.between(33.7, 36.7).all()


@pytest.mark.realdata
def test_E5_real_coordinates(real_written):
    f = real_written["frame"]
    assert f.mid_lon.astype(float).between(-84.5, -75.3).all() and f.mid_lat.astype(float).between(33.7, 36.7).all()


def test_awkward_text_survives_the_file(written):
    f, roads = written["frame"], written["roads"]
    want = roads.from_desc.iloc[11]
    assert f.set_index("seg_id").loc[roads.seg_id.iloc[11], "from_desc"] == want and '"' in want and "," in want


# ------------------------------------------------------------------------------------------------ E7

def test_E7_a_failed_write_leaves_nothing(tmp_path):
    target = tmp_path / "risk_roads.csv"

    def half_then_fail(tmp):
        Path(tmp).write_text("half a file")
        raise RuntimeError("disk full")
    with pytest.raises(RuntimeError, match="disk full"):
        export.atomic(target, half_then_fail)
    assert list(tmp_path.iterdir()) == []


def test_E7_a_failed_rewrite_leaves_the_old_file_untouched(tmp_path):
    target = tmp_path / "risk_roads.csv"
    export.atomic(target, lambda tmp: Path(tmp).write_text("complete"))
    assert [p.name for p in tmp_path.iterdir()] == ["risk_roads.csv"]       # no temporary file left after success

    def fail(tmp):
        Path(tmp).write_text("half")
        raise RuntimeError("stopped")
    with pytest.raises(RuntimeError):
        export.atomic(target, fail)
    assert target.read_text() == "complete" and [p.name for p in tmp_path.iterdir()] == ["risk_roads.csv"]


def test_the_writer_needs_nothing_but_the_standard_library():
    code = "import sys, web.tiger.export as e; sys.exit(1 if 'pandas' in sys.modules or 'numpy' in sys.modules else 0)"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-300:]


def test_the_command_line_starts():
    r = subprocess.run([sys.executable, "-m", "web.tiger.export", "--help"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "usage:" in r.stdout
