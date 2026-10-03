"""Count-checked paging for ArcGIS feature layers.

A pull stops with an error unless the rows received equal the server's own count. A reply that is
"200 OK" but carries an error or a notice instead of features is an error too (the retired NCDOT
camera endpoint answers that way).
"""
import time

import requests

UA = {"User-Agent": "unwatched-roads-hackathon/0.1 (NC State student project)"}
PAUSE_S = 0.5


class ArcGISError(RuntimeError):
    pass


def get_json(session, url, params):
    r = session.get(url, params=params, headers=UA, timeout=60)
    r.raise_for_status()
    try:
        j = r.json()
    except ValueError as e:
        raise ArcGISError(f"{url}: reply is not JSON") from e
    if not isinstance(j, dict):
        raise ArcGISError(f"{url}: reply is not a JSON object")
    if "error" in j:
        raise ArcGISError(f"{url}: {j['error']}")
    return j


def count(session, layer_url, where):
    j = get_json(session, f"{layer_url}/query", {"where": where, "returnCountOnly": "true", "f": "json"})
    if "count" not in j:
        raise ArcGISError(f"{layer_url}: no count in the reply: {str(j)[:200]}")
    return int(j["count"])


def fetch_all(layer_url, where, out_fields, *, geometry=True, page=1000, session=None, sleep=time.sleep):
    """Every row matching `where`, as attribute dicts (plus lon/lat when geometry=True)."""
    session = session or requests.Session()
    n = count(session, layer_url, where)
    rows, first = [], True
    while len(rows) < n:
        if not first:
            sleep(PAUSE_S)
        j = get_json(session, f"{layer_url}/query", {
            "where": where, "outFields": ",".join(out_fields), "returnGeometry": str(geometry).lower(),
            "outSR": 4326, "orderByFields": "OBJECTID", "resultOffset": len(rows),
            "resultRecordCount": page, "f": "json"})
        feats = j.get("features")
        if not isinstance(feats, list):
            raise ArcGISError(f"{layer_url}: no features in the reply: {str(j)[:200]}")
        if not feats:
            break
        if first:
            missing = [f for f in out_fields if f not in feats[0].get("attributes", {})]
            if missing:
                raise ArcGISError(f"{layer_url}: fields missing from the reply: {missing}")
            first = False
        for f in feats:
            a = dict(f["attributes"])
            if geometry:
                g = f.get("geometry") or {}
                a["lon"], a["lat"] = g.get("x"), g.get("y")
            rows.append(a)
    if len(rows) != n:
        raise ArcGISError(f"{layer_url}: received {len(rows):,} rows but the server counts {n:,}")
    return rows
