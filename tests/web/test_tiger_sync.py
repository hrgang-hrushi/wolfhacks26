"""server/tigersvc is a generated copy of the Tiger Data service. It must match web/ exactly."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_hosted_copy_of_the_service_is_up_to_date(capsys):
    spec = importlib.util.spec_from_file_location("sync_tiger_service", ROOT / "scripts" / "sync_tiger_service.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0, capsys.readouterr().out
