"""Checks against the real Tiger Data service and, once it is hosted, the public address.

All carry the `network` marker, so they never run in the base suite. They read TIGER_DATABASE_URL from the
environment or data/raw/tiger.env and skip when it is not there. Nothing here prints the address.

    PYTHONPATH=web/.venv/lib/python3.11/site-packages python -m pytest tests/dashboard/test_dash_live.py -m network -q
"""
import json
import os
import socket
import urllib.request

import pytest

from web.tiger import config, verify

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def tiger_url():
    try:
        return config.database_url()
    except config.ConfigError:
        pytest.skip("the Tiger connection setting is not on this machine")


def test_L1_the_reachability_check_gives_one_plain_word(tiger_url):
    state = config.reachability(tiger_url)
    assert state in ("ok", "network", "login", "unavailable")
    if state != "ok":
        pytest.fail(f"the Tiger service is not reachable from here: {state} ({config.MESSAGES[state]})")


def test_L4_the_service_is_new_enough_and_its_features_are_recorded(tiger_url, record_property):
    conn = config.connect(tiger_url, autocommit=True)
    try:
        info = config.probe(conn)
        features = config.try_features(conn)
    finally:
        conn.close()
    for key, value in {**info, **{f"feature_{k}": v for k, v in features.items()}}.items():
        record_property(key, value)
    assert config.parse_version(info["timescaledb_version"])[:2] >= config.MIN_TIMESCALE
    assert all(v == "ok" for v in features.values()), features


def test_L2_the_check_command_passes_against_tiger(tiger_url):
    results = verify.run(tiger_url, config.schema_name())
    assert all(c.ok for c in results), [c for c in results if not c.ok]


def test_L3_every_route_on_the_hosted_address_answers():
    base = os.environ.get("DASHBOARD_URL")
    if not base:
        pytest.skip("needs the user's yes on hosting: set DASHBOARD_URL to the public address")
    for path in ("/api/health", "/api/summary", "/api/worklist?limit=1", "/api/alerts", "/api/alerts/peaks", "/api/stats",
                 "/api/export/dictionary"):
        with urllib.request.urlopen(base.rstrip("/") + path, timeout=90) as r:      # a sleeping free host can take a minute
            assert r.status == 200 and isinstance(json.loads(r.read()), dict), path


def test_L5_the_domain_resolves():
    domain = os.environ.get("DASHBOARD_DOMAIN")
    if not domain:
        pytest.skip("needs the registered domain: set DASHBOARD_DOMAIN")
    assert socket.getaddrinfo(domain, 443)
