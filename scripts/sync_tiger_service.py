"""Copy the Tiger Data service into server/tigersvc/, where the hosted API can import it.

The hosting service builds the API from the server/ folder alone, so code under web/ is out of
its reach. This script writes a copy of the four modules the service needs, with their imports
pointed at the copy. web/ stays the source of truth: edit there, then run this.

    python scripts/sync_tiger_service.py           # write the copies
    python scripts/sync_tiger_service.py --check   # exit 1 if a copy is out of date (the test suite runs this)
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "server" / "tigersvc"
SOURCES = {
    "app.py": "web/service/app.py",
    "queries.py": "web/service/queries.py",
    "config.py": "web/tiger/config.py",
    "export.py": "web/tiger/export.py",
    "schema.py": "web/tiger/schema.py",
}
IMPORTS = [
    ("from web.service import ", "from tigersvc import "),
    ("from web.tiger import ", "from tigersvc import "),
]


def render(name: str) -> str:
    source = SOURCES[name]
    text = (ROOT / source).read_text()
    for old, new in IMPORTS:
        text = text.replace(old, new)
    if "web.service" in text.replace("web.service.app:app", "") or "import web" in text:
        raise SystemExit(f"{source} has an import this script does not rewrite")
    return f"# GENERATED from {source} by scripts/sync_tiger_service.py. Edit that file, then rerun the script.\n{text}"


def main(argv=None) -> int:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--check", action="store_true", help="report copies that are out of date; write nothing")
    check = args.parse_args(argv).check
    stale = []
    wanted = {name: render(name) for name in SOURCES}
    wanted["__init__.py"] = '"""The Tiger Data service, copied from web/ by scripts/sync_tiger_service.py. Do not edit here."""\n'
    for name, text in wanted.items():
        path = DEST / name
        if not path.exists() or path.read_text() != text:
            stale.append(name)
            if not check:
                DEST.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
    if check and stale:
        print("out of date in server/tigersvc: " + ", ".join(stale) + ". Run: python scripts/sync_tiger_service.py")
        return 1
    print("server/tigersvc is up to date" if not stale else "wrote " + ", ".join(stale))
    return 0


if __name__ == "__main__":
    sys.exit(main())
