"""Connection settings for the Tiger Data service.

Usage:  python -m web.tiger.config --check     prints ok | network | login | unavailable
        python -m web.tiger.config --probe     version, available features, and a trial of each feature we use

The connection string comes from the environment variable TIGER_DATABASE_URL, else from data/raw/tiger.env
(git-ignored). Nothing in this module prints, logs or returns it, and a driver error is never passed on as
text: it names the host, the port and the user.
"""
import argparse
import ipaddress
import os
import re
import secrets
from pathlib import Path

import psycopg
from psycopg import conninfo, sql

ENV_KEY = "TIGER_DATABASE_URL"
ENV_FILE = Path("data/raw/tiger.env")
SCHEMA_KEY = "TIGER_SCHEMA"
DEFAULT_SCHEMA = "unwatched"
MIN_TIMESCALE = (2, 20)  # CREATE TABLE ... WITH (tsdb.hypertable) needs 2.20

MESSAGES = {
    "network": "database unreachable: the network blocked the connection or nothing is listening",
    "login": "database refused the login",
    "unavailable": "database unavailable",
}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_LOGIN_SQLSTATES = {"28P01", "28000"}
_LOGIN_HINTS = ("authentication failed", "does not exist", "no pg_hba.conf entry", "password")
_NETWORK_HINTS = ("refused", "timeout", "timed out", "could not translate host name", "unreachable", "no route",
                  "could not receive data", "server closed the connection")


class ConfigError(RuntimeError):
    """The connection settings are missing or unusable."""


class DatabaseUnavailable(RuntimeError):
    """A connection or query failed. Carries a kind and a fixed message, never the driver's text."""

    def __init__(self, kind="unavailable"):
        self.kind = kind if kind in MESSAGES else "unavailable"
        super().__init__(MESSAGES[self.kind])


def read_env_file(path):
    """KEY=VALUE lines; '#' comments; surrounding quotes are stripped."""
    out = {}
    path = Path(path)
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def database_url(env=None, env_file=None):
    """The connection string: the environment wins, then the file. There is no default."""
    env = os.environ if env is None else env
    env_file = ENV_FILE if env_file is None else env_file
    value = (env.get(ENV_KEY) or "").strip() or read_env_file(env_file).get(ENV_KEY, "").strip()
    if not value:
        raise ConfigError(f"{ENV_KEY} is not set (environment or {env_file})")
    return value


def schema_name(env=None):
    env = os.environ if env is None else env
    name = (env.get(SCHEMA_KEY) or DEFAULT_SCHEMA).strip()
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
        raise ConfigError(f"{SCHEMA_KEY} must be a plain lower-case name")
    return name


def classify(exc):
    """network | login | unavailable. The driver's text is read here and goes no further."""
    if isinstance(exc, psycopg.errors.ConnectionTimeout):
        return "network"
    state = getattr(exc, "sqlstate", None)
    if state in _LOGIN_SQLSTATES:
        return "login"
    text = str(exc).lower()
    if state is None and isinstance(exc, psycopg.OperationalError):
        if any(h in text for h in _NETWORK_HINTS):
            return "network"
        if any(h in text for h in _LOGIN_HINTS):
            return "login"
    return "unavailable"


def describe(exc):
    """Any database error as one fixed sentence. The driver's own text is never printed: it can name the host,
    the port and the user."""
    if isinstance(exc, DatabaseUnavailable):
        return f"{exc} ({exc.kind})"
    kind = classify(exc)
    state = getattr(exc, "sqlstate", None)
    text = MESSAGES[kind] if kind != "unavailable" else "the database reported an error"
    return f"{text} (code {state})" if state else text


def extension_schema(conn):
    """Schema that holds TimescaleDB's functions ('public' on a stock install)."""
    row = conn.execute("SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace "
                       "WHERE e.extname = 'timescaledb'").fetchone()
    return row[0] if row else "public"


def apply_session(conn, *, schema=None, read_only=False, statement_timeout_ms=None, lock_timeout_ms=None):
    """UTC, the search path, the limits. A search path without the extension's schema hides time_bucket."""
    conn.execute("SELECT set_config('TimeZone', 'UTC', false)")
    if schema:
        path = ", ".join(sql.Identifier(s).as_string(conn) for s in dict.fromkeys([schema, extension_schema(conn)]))
        conn.execute("SELECT set_config('search_path', %s, false)", [path])
    if statement_timeout_ms:
        conn.execute("SELECT set_config('statement_timeout', %s, false)", [str(int(statement_timeout_ms))])
    if lock_timeout_ms:
        conn.execute("SELECT set_config('lock_timeout', %s, false)", [str(int(lock_timeout_ms))])
    if read_only:
        conn.execute("SELECT set_config('default_transaction_read_only', 'on', false)")
    if not conn.autocommit:
        conn.commit()


def connect(url, *, autocommit=False, read_only=False, connect_timeout=5, statement_timeout_ms=None,
            lock_timeout_ms=None, schema=None):
    """An open connection in UTC. Driver errors come out as DatabaseUnavailable with nothing of their text."""
    try:
        conn = psycopg.connect(url, autocommit=True, connect_timeout=connect_timeout)
    except psycopg.Error as e:
        raise DatabaseUnavailable(classify(e)) from None
    try:
        apply_session(conn, schema=schema, read_only=read_only, statement_timeout_ms=statement_timeout_ms,
                      lock_timeout_ms=lock_timeout_ms)
        conn.autocommit = autocommit
    except psycopg.Error as e:
        conn.close()
        raise DatabaseUnavailable(classify(e)) from None
    return conn


def _is_loopback(addr):
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return False


def require_local(url, env=None):
    """Raise unless the address can only reach a database on this machine. Called before connecting."""
    env = os.environ if env is None else env
    for key in ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE"):
        if env.get(key):
            raise ConfigError(f"refusing the test database: the environment sets {key}")
    try:
        d = conninfo.conninfo_to_dict(url)
    except psycopg.Error:
        raise ConfigError("refusing the test database: the address does not parse") from None
    if d.get("service") or d.get("passfile"):
        raise ConfigError("refusing the test database: the address names a service or a password file")
    hosts = [h for h in str(d.get("host") or "").split(",") if h]
    if not hosts:
        raise ConfigError("refusing the test database: the address names no host")
    if not all(h in LOCAL_HOSTS or h.startswith("/") for h in hosts):
        raise ConfigError("refusing the test database: its host is not this machine")
    addrs = [a for a in str(d.get("hostaddr") or "").split(",") if a]
    if not all(_is_loopback(a) for a in addrs):
        raise ConfigError("refusing the test database: its hostaddr is not this machine")


def assert_local(conn):
    """Raise unless the open connection really ended on this machine. Called before any change."""
    info = conn.info
    try:
        addr = info.hostaddr
    except Exception:  # an older libpq, or a socket connection
        addr = ""
    if addr:
        ok = _is_loopback(addr)
    else:
        ok = str(info.host or "").startswith("/")
    if not ok:
        raise ConfigError("refusing the test database: the connection did not end on this machine")


def reachability(url, timeout=5):
    """ok | network | login | unavailable."""
    try:
        connect(url, autocommit=True, connect_timeout=timeout).close()
    except DatabaseUnavailable as e:
        return e.kind
    return "ok"


def parse_version(text):
    return tuple(int(x) for x in re.findall(r"\d+", text or "")[:3])


def probe(conn):
    """What the service is: versions, optional extensions, limits, size."""
    one = lambda q: conn.execute(q).fetchone()
    ts = one("SELECT e.extversion, n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace "
             "WHERE e.extname = 'timescaledb'")
    avail = {r[0] for r in conn.execute("SELECT name FROM pg_available_extensions WHERE name IN ('postgis', 'vector')")}
    return {
        "postgres_version": one("SHOW server_version")[0],
        "timescaledb_version": ts[0] if ts else None,
        "timescaledb_schema": ts[1] if ts else None,
        "postgis_available": "postgis" in avail,
        "vector_available": "vector" in avail,
        "max_connections": int(one("SHOW max_connections")[0]),
        "database_size_bytes": int(one("SELECT pg_database_size(current_database())")[0]),
        "background_workers": one("SELECT current_setting('timescaledb.max_background_workers', true)")[0],
    }


def _reason(e):
    """The server's own first line for a refused statement. It carries no connection details."""
    primary = getattr(getattr(e, "diag", None), "message_primary", None)
    return f"{getattr(e, 'sqlstate', None) or 'error'}: {primary or type(e).__name__}"


def try_features(conn):
    """Try, in a throwaway schema, one of everything the load uses. Returns {feature: 'ok' | reason}."""
    if not conn.autocommit:
        raise ConfigError("try_features needs an autocommit connection")
    name = "probe_" + secrets.token_hex(4)
    ident = sql.Identifier(name)
    ext = sql.Identifier(extension_schema(conn))
    steps = [
        ("hypertable", "CREATE TABLE {s}.t (time timestamptz NOT NULL, k text NOT NULL, v double precision, UNIQUE (k, time)) "
                       "WITH (tsdb.hypertable, tsdb.partition_column = 'time', tsdb.chunk_interval = '1 day', "
                       "tsdb.segmentby = 'k', tsdb.orderby = 'time DESC')"),
        ("insert", "INSERT INTO {s}.t SELECT ts, 'a', 1.5 FROM generate_series(now() - INTERVAL '3 days', "
                   "now() - INTERVAL '2 days', INTERVAL '75 minutes') ts"),
        ("continuous_aggregate", "CREATE MATERIALIZED VIEW {s}.t_hourly WITH (timescaledb.continuous, "
                                 "timescaledb.materialized_only = false) AS SELECT {e}.time_bucket(INTERVAL '1 hour', time) "
                                 "AS bucket, k, max(v) AS hi, count(*) AS n FROM {s}.t GROUP BY 1, 2 WITH NO DATA"),
        ("refresh", "CALL {e}.refresh_continuous_aggregate('{n}.t_hourly', NULL, NULL)"),
        ("refresh_policy", "SELECT {e}.add_continuous_aggregate_policy('{n}.t_hourly', start_offset => NULL, "
                           "end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '30 minutes', "
                           "initial_start => now() + INTERVAL '1 day', if_not_exists => true)"),
        ("columnstore", "DO $$ DECLARE c regclass; BEGIN FOR c IN SELECT {e}.show_chunks('{n}.t') LOOP "
                        "CALL {e}.convert_to_columnstore(c, if_not_columnstore => true); END LOOP; END $$"),
        ("columnstore_stats", "SELECT number_compressed_chunks FROM {e}.hypertable_columnstore_stats('{n}.t')"),
    ]
    out = {}
    try:
        conn.execute(sql.SQL("CREATE SCHEMA {s}").format(s=ident))
        for feature, text in steps:
            try:
                conn.execute(sql.SQL(text.replace("{n}", name)).format(s=ident, e=ext))
                out[feature] = "ok"
            except psycopg.Error as e:
                out[feature] = _reason(e)
    except psycopg.Error as e:
        out["schema"] = _reason(e)
    finally:
        try:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {s} CASCADE").format(s=ident))
        except psycopg.Error:
            out["cleanup"] = f"could not drop schema {name}"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check the Tiger Data connection without printing it.")
    ap.add_argument("--check", action="store_true", help="print ok, network, login or unavailable")
    ap.add_argument("--probe", action="store_true", help="print versions, limits and a trial of each feature")
    args = ap.parse_args(argv)
    try:
        url = database_url()
    except ConfigError as e:
        print(e)
        return 2
    state = reachability(url)
    if args.probe and state == "ok":
        try:
            conn = connect(url, autocommit=True)
            try:
                for k, v in probe(conn).items():
                    print(f"{k}: {v}")
                for k, v in try_features(conn).items():
                    print(f"feature {k}: {v}")
            finally:
                conn.close()
        except (psycopg.Error, DatabaseUnavailable) as e:
            print(describe(e))
            return 2
    else:
        print(state)
    return 0 if state == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
