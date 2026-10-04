"""Secrets and repo safety: no credential in a file, an error or a log; tests can only reach a local database;
nobody else's files are touched."""
import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

import pytest

from web.tiger import config

ADDRESS_WITH_PASSWORD = re.compile(r"postgres(ql)?://[^\s:@/]+:[^\s@/]+@")
VENV_PATH = "web/.venv/lib/python3.11/site-packages"
# owned by other work: the pipeline and model code, the project files, the shared tests, the tracked map files,
# and the teammate's frontend, which shares the web/ folder with this package
NOT_OURS = ["src", "pyproject.toml", "uv.lock", ".gitignore", ".python-version", "README.md", "readme", "PLAN.md", "DESIGN.md",
            "handoff", "notebooks", "scripts", "tests/conftest.py", "tests/test_features.py", "tests/test_folds.py",
            "tests/test_oof.py", "tests/test_predictions.py", "tests/test_realdata.py", "tests/test_repo_guards.py",
            "tests/test_scripts.py", "tests/test_targets.py", "tests/potholes", "tests/cctv", "tests/crashes", "tests/vision",
            "web/src", "web/public", "web/README.md", "web/DESIGN.md", "web/index.html", "web/package.json",
            "web/package-lock.json", "web/vite.config.ts", "web/.gitignore", "web/.env.example", "web/generate_roads.cjs",
            "web/capture.mjs", "web/tsconfig.json", "web/tsconfig.app.json", "web/tsconfig.node.json", "web/.oxlintrc.json"]


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True)


def run_py(code_or_args, env=None, python=sys.executable, timeout=180):
    """A fresh interpreter from the repo root, with the dashboard's packages on its path."""
    full = {k: v for k, v in os.environ.items() if not k.startswith("PG") and k != config.ENV_KEY}
    full["PYTHONPATH"] = VENV_PATH
    full.update(env or {})
    args = code_or_args if isinstance(code_or_args, list) else ["-c", code_or_args]
    return subprocess.run([python, *args], capture_output=True, text=True, timeout=timeout, env=full)


# ------------------------------------------------------------------------------------------------ S1

def test_S1_no_file_git_would_see_holds_a_database_address_with_a_password():
    names = git("ls-files", "--cached", "--others", "--exclude-standard").stdout.split("\n")
    hits = []
    for name in filter(None, names):
        p = Path(name)
        if not p.is_file() or p.suffix in {".parquet", ".jpg", ".png", ".webp", ".svg", ".lock", ".csv", ".ipynb"}:
            continue
        if ADDRESS_WITH_PASSWORD.search(p.read_text(errors="ignore")):
            hits.append(name)
    assert hits == []


def test_S1_the_pattern_does_catch_an_address_with_a_password(dash):
    assert ADDRESS_WITH_PASSWORD.search(dash.fake_url())            # the check above is able to fail
    assert not ADDRESS_WITH_PASSWORD.search(dash.LOCAL_URL)         # the local test address has no password


def test_S1_the_ignore_rule_that_covers_tiger_env_is_still_there():
    # git cannot check a path behind the worktree's data/raw symlink, so the rule is read from the file
    rules = [line.strip() for line in Path(".gitignore").read_text().splitlines()]
    assert "data/raw/*" in rules
    assert str(config.ENV_FILE) == "data/raw/tiger.env"
    assert not Path(".env").exists() and not Path("web/.env").exists()


# ------------------------------------------------------------------------------------------------ S2 (connection half)

def _all_text(exc):
    return "".join(traceback.format_exception(exc)) + repr(exc) + str(exc)


def test_S2_a_refused_connection_says_nothing_of_the_address(dash):
    with pytest.raises(config.DatabaseUnavailable) as e:
        config.connect(dash.fake_url(), connect_timeout=2)          # nothing listens on port 1
    assert e.value.kind == "network" and str(e.value) == config.MESSAGES["network"]
    text = _all_text(e.value)
    assert "pw-marker" not in text and "user-marker" not in text and "127.0.0.1" not in text


@pytest.mark.db
def test_S2_a_refused_login_says_nothing_of_the_address(db_url, dash):
    url = dash.fake_url(port=55432)                                 # the test database; the user does not exist
    with pytest.raises(config.DatabaseUnavailable) as e:
        config.connect(url, connect_timeout=3)
    assert e.value.kind == "login" and str(e.value) == config.MESSAGES["login"]
    text = _all_text(e.value)
    assert "pw-marker" not in text and "user-marker" not in text and "55432" not in text


def test_S2_reachability_tells_a_network_block_from_a_refused_login(dash):
    assert config.reachability(dash.fake_url(), timeout=2) == "network"


@pytest.mark.db
def test_L1_reachability_against_the_local_database(db_url, dash):
    assert config.reachability(db_url) == "ok"
    assert config.reachability(dash.fake_url(port=55432), timeout=3) == "login"


def test_S2_an_error_kind_outside_the_list_becomes_unavailable():
    assert config.DatabaseUnavailable("made up").kind == "unavailable"


# ------------------------------------------------------------------------------------------------ S3 (settings half)

def test_S3_a_missing_setting_is_refused_and_named(tmp_path):
    with pytest.raises(config.ConfigError, match=config.ENV_KEY):
        config.database_url(env={}, env_file=tmp_path / "tiger.env")


def test_S3_a_half_filled_file_is_refused_and_named(tmp_path):
    f = tmp_path / "tiger.env"
    f.write_text("# filled in by the user\nOTHER_KEY=1\nTIGER_DATABASE_URL=\n")
    with pytest.raises(config.ConfigError, match=config.ENV_KEY):
        config.database_url(env={}, env_file=f)
    with pytest.raises(config.ConfigError, match=config.ENV_KEY):
        config.database_url(env={config.ENV_KEY: "   "}, env_file=f)


def test_S3_the_file_is_read_and_the_environment_wins(tmp_path):
    f = tmp_path / "tiger.env"
    f.write_text("TIGER_DATABASE_URL='from-file'\n")
    assert config.database_url(env={}, env_file=f) == "from-file"
    assert config.database_url(env={config.ENV_KEY: "from-env"}, env_file=f) == "from-env"


def test_S3_there_is_no_default_address():
    src = Path("web/tiger/config.py").read_text()
    assert "localhost:" not in src and "127.0.0.1:" not in src      # no fallback address in the module


def test_S3_the_schema_name_must_be_plain():
    assert config.schema_name(env={}) == "unwatched"
    with pytest.raises(config.ConfigError):
        config.schema_name(env={config.SCHEMA_KEY: 'x"; DROP SCHEMA public; --'})


# ------------------------------------------------------------------------------------------------ S5, S9

def _base():
    """Where this branch left the main line: the nearer of the merge-bases with main and origin/main
    (the local main can lag behind the pushed one, and then its merge-base would blame us for others' commits)."""
    bases = [git("merge-base", "HEAD", ref).stdout.strip() for ref in ("main", "origin/main")
             if git("rev-parse", "--verify", "-q", ref).returncode == 0]
    bases = [b for b in bases if b]
    return min(bases, key=lambda b: int(git("rev-list", "--count", f"{b}..HEAD").stdout or 0)) if bases else ""


def test_S5_the_shared_dependency_files_are_unchanged():
    base = _base()
    if not base:
        pytest.skip("no main branch to compare against")
    assert git("diff", "--name-only", base, "HEAD", "--", "pyproject.toml", "uv.lock").stdout.split() == []
    assert git("diff", "--name-only", "--", "pyproject.toml", "uv.lock").stdout.split() == []


def test_S9_files_owned_by_other_work_are_unchanged_on_this_branch():
    base = _base()
    if not base:
        pytest.skip("no main branch to compare against")
    assert git("diff", "--name-only", base, "HEAD", "--", *NOT_OURS).stdout.split() == []
    assert git("diff", "--name-only", "--", *NOT_OURS).stdout.split() == []     # nor uncommitted edits


def test_S9_no_icloud_duplicate_files():
    assert [str(f) for d in ("web/tiger", "web/service", "tests/dashboard") for f in Path(d).rglob("* 2*")] == []


# ------------------------------------------------------------------------------------------------ S8, S11

@pytest.mark.parametrize("url", [
    "postgresql://postgres@db.example.com:5432/postgres",
    "postgresql://postgres@127.0.0.1:55432/postgres?host=db.example.com",        # the query string overrides the host
    "postgresql://postgres@localhost:55432/postgres?hostaddr=203.0.113.5",        # a local name, a remote address
    "host=localhost hostaddr=203.0.113.5 port=5432 dbname=postgres",
    "postgresql://postgres@127.0.0.1,db.example.com:5432/postgres",               # one of two hosts is remote
    "postgresql://postgres@127.0.0.1:55432/postgres?service=prod",
    "postgresql://postgres@127.0.0.1:55432/postgres?passfile=/tmp/pgpass",
    "dbname=postgres",                                                            # no host named
])
def test_S8_an_address_that_could_reach_another_machine_is_refused_before_connecting(url):
    with pytest.raises(config.ConfigError, match="refusing the test database"):
        config.require_local(url, env={})


@pytest.mark.parametrize("key", ["PGHOST", "PGHOSTADDR", "PGSERVICE"])
def test_S8_environment_settings_that_redirect_the_connection_are_refused(key, dash):
    with pytest.raises(config.ConfigError, match=key):
        config.require_local(dash.LOCAL_URL, env={key: "db.example.com"})


def test_S8_local_addresses_pass(dash):
    for url in (dash.LOCAL_URL, "postgresql://postgres@localhost:55432/postgres?hostaddr=127.0.0.1",
                "host=/var/run/postgresql dbname=postgres", "postgresql://postgres@[::1]:55432/postgres"):
        config.require_local(url, env={})


@pytest.mark.parametrize("info, ok", [
    (SimpleNamespace(hostaddr="127.0.0.1", host="localhost"), True),
    (SimpleNamespace(hostaddr="::1", host="localhost"), True),
    (SimpleNamespace(hostaddr="", host="/var/run/postgresql"), True),
    (SimpleNamespace(hostaddr="203.0.113.5", host="localhost"), False),           # the name lied
    (SimpleNamespace(hostaddr="", host="db.example.com"), False),
])
def test_S8_the_open_connection_is_checked_too(info, ok):
    conn = SimpleNamespace(info=info)
    if ok:
        config.assert_local(conn)
    else:
        with pytest.raises(config.ConfigError):
            config.assert_local(conn)


@pytest.mark.db
def test_S8_the_real_test_connection_ends_on_this_machine(db_url):
    conn = config.connect(db_url, autocommit=True)
    try:
        config.assert_local(conn)
    finally:
        conn.close()


@pytest.mark.db
def test_S11_starting_a_test_session_leaves_an_existing_test_schema_alone(db_url, dash):
    from psycopg import sql
    schema = dash.new_schema()
    conn = config.connect(db_url, autocommit=True)
    try:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        dash.open_test_database({})                                  # what every session runs first
        n = conn.execute("SELECT count(*) FROM pg_namespace WHERE nspname = %s", [schema]).fetchone()[0]
        assert n == 1
    finally:
        conn.close()
        dash.drop_schema(db_url, schema)


def test_S11_only_a_test_schema_can_be_dropped_by_the_helpers(dash):
    with pytest.raises(RuntimeError, match="not a test schema"):
        dash.drop_schema(dash.LOCAL_URL, "unwatched")


# ------------------------------------------------------------------------------------------------ S3 (commands), S6

@pytest.mark.parametrize("module, args", [("load", []), ("verify", []), ("replay", []), ("replay", ["--clear"]), ("config", ["--check"])])
def test_S3_every_command_refuses_without_its_setting_and_names_it(module, args, monkeypatch, tmp_path, capsys):
    import importlib
    monkeypatch.delenv(config.ENV_KEY, raising=False)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")       # so a real tiger.env on this machine is never read
    assert importlib.import_module(f"web.tiger.{module}").main(args) == 2
    out = capsys.readouterr().out
    assert config.ENV_KEY in out and "is not set" in out


@pytest.mark.parametrize("module", ["web.tiger.config", "web.tiger.load", "web.tiger.verify", "web.tiger.export", "web.tiger.replay"])
def test_every_command_line_starts(module):
    r = run_py(["-m", module, "--help"])
    assert r.returncode == 0 and "usage:" in r.stdout, r.stderr[-300:]


def test_S6_the_loader_loads_neither_lightgbm_nor_pytorch():
    code = ("import sys, web.tiger.build, web.tiger.load, web.tiger.verify, web.tiger.replay; "
            "sys.exit(1 if 'lightgbm' in sys.modules or 'torch' in sys.modules else 0)")
    r = run_py(code)
    assert r.returncode == 0, r.stderr[-500:] or "lightgbm or torch was imported"


def test_S6_the_service_runs_without_pandas():
    python = Path("web/.venv/bin/python")
    if not python.exists():
        pytest.skip("web/.venv is not on this machine")
    code = ("import sys, web.service.app, web.tiger.export, web.tiger.config, web.tiger.schema; "
            "sys.exit(1 if 'pandas' in sys.modules or 'numpy' in sys.modules else 0)")
    r = run_py(code, env={"PYTHONPATH": ""}, python=str(python))            # that environment has no pandas at all
    assert r.returncode == 0, r.stderr[-500:] or "pandas was imported"
    missing = run_py("import pandas", env={"PYTHONPATH": ""}, python=str(python))
    assert missing.returncode != 0                                          # so the check above could have failed


# ------------------------------------------------------------------------------------------------ S10

def no_secret(text, *extra):
    for secret in ("pw-marker", "user-marker", *extra):
        assert secret not in text, secret


@pytest.mark.realdata
def test_S10_a_failed_load_prints_nothing_of_the_address(real_root, dash):
    r = run_py(["-m", "web.tiger.load"], env={config.ENV_KEY: dash.fake_url()}, timeout=300)   # nothing listens on port 1
    out = r.stdout + r.stderr
    assert r.returncode == 2 and config.MESSAGES["network"] in out
    no_secret(out, "127.0.0.1", "postgresql://")


@pytest.mark.db
@pytest.mark.realdata
def test_S10_a_successful_load_and_check_print_nothing_of_the_address(db_url, real_root, dash):
    name = dash.new_schema()
    env = {config.ENV_KEY: dash.fake_url(user="postgres", port=55432), config.SCHEMA_KEY: name}   # trust login: the password is unused
    try:
        loaded = run_py(["-m", "web.tiger.load"], env=env, timeout=600)
        checked = run_py(["-m", "web.tiger.verify"], env=env, timeout=600)
        out = loaded.stdout + loaded.stderr + checked.stdout + checked.stderr
        assert loaded.returncode == 0 and f"schema {name}: complete" in loaded.stdout and "roads: 112,443 rows" in loaded.stdout
        assert checked.returncode == 0 and "checks passed" in checked.stdout and "FAIL" not in checked.stdout
        no_secret(out, "55432", "127.0.0.1", "postgresql://")
    finally:
        dash.drop_schema(db_url, name)


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve_and_ask(url, tmp_path, paths=("/api/health", "/api/worklist")):
    """Start the real service in its own process against `url`, ask it, stop it. Returns (replies, everything it printed)."""
    import urllib.error
    import urllib.request
    python = Path("web/.venv/bin/python")
    if not python.exists():
        pytest.skip("web/.venv is not on this machine")
    port = _free_port()
    log = open(tmp_path / "service.log", "w")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env.update({config.ENV_KEY: url, "PYTHONPATH": ""})
    proc = subprocess.Popen([str(python), "-m", "uvicorn", "web.service.app:app", "--host", "localhost", "--port", str(port),
                             "--no-access-log"], stdout=log, stderr=subprocess.STDOUT, env=env)

    def ask(path, timeout):
        try:
            with urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=timeout) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
    try:
        deadline = __import__("time").time() + 30
        while True:
            try:
                if ask("/api/export/dictionary", 2)[0] == 200:
                    break
            except OSError:
                pass
            assert __import__("time").time() < deadline and proc.poll() is None, "the service did not start"
            __import__("time").sleep(0.3)
        replies = [ask(p, 20) for p in paths]
    finally:
        proc.terminate()
        proc.wait(timeout=20)
        log.close()
    return replies, (tmp_path / "service.log").read_text()


def test_S10_the_running_service_leaks_nothing_when_the_network_refuses(tmp_path, dash):
    replies, printed = _serve_and_ask(dash.fake_url(), tmp_path)
    assert [status for status, _ in replies] == [503, 503]
    assert all(json.loads(body)["error"] == "database unavailable" for _, body in replies)
    everything = printed + "".join(body for _, body in replies)
    no_secret(everything, "127.0.0.1", "port 1 ", "postgresql://")
    assert "database connection problem" in printed                        # the pool's own log line, rewritten


@pytest.mark.db
def test_S10_the_running_service_leaks_nothing_when_the_login_is_refused(db_url, tmp_path, dash):
    replies, printed = _serve_and_ask(dash.fake_url(port=55432), tmp_path)   # the test database; that user does not exist
    assert [status for status, _ in replies] == [503, 503]
    everything = printed + "".join(body for _, body in replies)
    no_secret(everything, "55432", "127.0.0.1", "postgresql://")
    assert "database connection problem" in printed
