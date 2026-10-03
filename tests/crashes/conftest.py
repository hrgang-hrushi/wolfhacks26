"""Fixtures for the crash and estimated-traffic joins: three segments on one route, one on another."""
import pandas as pd
import pytest

R1, R2 = 40001001008, 20000013008


@pytest.fixture
def segs():
    """Route R1: 0-1, 1-2, then a gap, 3-4. Route R2: 0-0.5."""
    d = pd.DataFrame({"seg_id": ["a", "b", "c", "z"], "rid": [R1, R1, R1, R2],
                      "BEG_MP": [0.0, 1.0, 3.0, 0.0], "END_MP": [1.0, 2.0, 4.0, 0.5]})
    d["rid"] = d.rid.astype("Int64")
    d["seg_mi"] = d.END_MP - d.BEG_MP
    return d


class FakeSession:
    """Answers ArcGIS count, statistics and window queries from a list of attribute dicts."""

    def __init__(self, rows, oid="FID", count=None, limit=None, fail_first=0):
        self.rows, self.oid, self.limit, self.fail_first = rows, oid, limit, fail_first
        self.count = len(rows) if count is None else count
        self.calls = []

    def get(self, url, params, **kw):
        self.calls.append(params)
        if self.fail_first > 0:
            self.fail_first -= 1
            return Reply({"error": {"code": 500, "message": "busy"}})
        if params.get("returnCountOnly"):
            return Reply({"count": self.count})
        ids = [r[self.oid] for r in self.rows]
        if "outStatistics" in params:
            return Reply({"features": [{"attributes": {"lo": min(ids), "hi": max(ids)}}]})
        lo, hi = (int(x) for x in __import__("re").findall(r"[<>]=?(\d+)", params["where"]))
        hit = [r for r in self.rows if lo < r[self.oid] <= hi]
        if self.limit and len(hit) > self.limit:
            return Reply({"features": [{"attributes": r} for r in hit[:self.limit]], "exceededTransferLimit": True})
        return Reply({"features": [{"attributes": r} for r in hit]})


class Reply:
    def __init__(self, j):
        self.j = j

    def raise_for_status(self):
        pass

    def json(self):
        return self.j


@pytest.fixture
def fake_session():
    return FakeSession
