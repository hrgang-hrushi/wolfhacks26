# Tiger Data loader and data service

The Python side of `web/`: it loads the project's predictions and time-stamped readings into a Tiger Data
(Postgres + TimescaleDB) database and serves them read-only. The frontend in this folder (`web/src`, `web/package.json`)
is separate and is not touched by anything here. What each table and route means is in
`docs/features/TIGER_DASHBOARD.md`.

Run every command from the repository root.

## One-time setup

```
uv venv web/.venv --python .venv/bin/python
uv pip install --python web/.venv/bin/python -r web/requirements.txt
```

This is a small separate environment (database driver, connection pool, web server). `pyproject.toml` is not changed.
Do not run `uv sync` for it. In a worktree, use the main checkout's interpreter in place of `.venv/bin/python`.

The loader also needs pandas and geopandas from the main environment, so it runs with the main interpreter and the
small environment on its path:

```
py() { PYTHONPATH=web/.venv/lib/python3.11/site-packages .venv/bin/python "$@"; }
```

## The connection setting

One setting, `TIGER_DATABASE_URL`: the service's connection string, copied from the Tiger console. Put it in the
environment, or in `data/raw/tiger.env` as one line:

```
TIGER_DATABASE_URL=...
```

That file is git-ignored. `data/raw` is shared between every worktree on this machine, so every chat here can read it.
Nothing in this package prints the value. Optional: `TIGER_SCHEMA` (default `unwatched`), and for the service
`ALLOWED_ORIGINS` (comma-separated sites allowed to call it; unset means any site, never with credentials).

## Commands

| Command | What it does |
|---|---|
| `py -m web.tiger.config --check` | Prints `ok`, `network` (the port is blocked or nothing listens) or `login` |
| `py -m web.tiger.config --probe` | Version, limits, and a trial of each database feature the load uses, in a throwaway schema |
| `py -m web.tiger.load` | Builds the tables from the project files and loads them (about 10 seconds for the real data) |
| `py -m web.tiger.verify` | Compares the database with the files, check by check; exits 1 if any fails |
| `py -m web.tiger.export` | Writes `data/processed/export/risk_roads.csv` and `risk_dictionary.json` (no database needed) |
| `py -m web.tiger.replay` | Replays the storm's peak hour into the tables, labelled, so the alert goes live; `--clear` removes it |
| `py -m web.tiger.load --dump-dir DIR` | Writes CSV files and two SQL scripts for Tiger's browser console, for when the port is blocked |

The service:

```
web/.venv/bin/uvicorn web.service.app:app --host 0.0.0.0 --port 8000 --workers 1
```

`http://127.0.0.1:8000/docs` lists every route and lets you try it. It uses port 8000, the same as `src/api.py`; run one
or the other.

## When the venue network blocks the database port

Tiger services listen on a high port and this network blocks those. In order: `--check`; a phone hotspot; else
`--dump-dir`, then in the Tiger console run `setup.sql` in the SQL editor, import each CSV into its table, and run
`after_load.sql`. The service has to run somewhere that can reach the database.

## Local test database

The tests marked `db` use a local TimescaleDB that only this machine can reach and that has no password:

```
docker run -d --name tiger-dashboard-testdb -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55432:5432 timescale/timescaledb:latest-pg17
```

They refuse any other host, work in throwaway schemas named `test_...`, and drop what they create. If a killed run
leaves one behind: `docker exec tiger-dashboard-testdb psql -U postgres -c "DROP SCHEMA test_xxxx CASCADE"`.

To use the same container as a stand-in for Tiger: `TIGER_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/postgres`.

## Tests

```
py -m pytest tests/dashboard -q -m "not db and not network"    # no database needed
py -m pytest tests/dashboard -q -m db                          # needs the local test database
py -m pytest tests/dashboard -q -m network                     # needs the real Tiger service
```

With the plain main interpreter (no `py`), the files in `tests/dashboard` leave themselves out, so the project's base
suite is unaffected.
