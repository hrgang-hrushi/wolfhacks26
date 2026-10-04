"""Fixtures for the Helene depth tests. The builders live in hd_helpers.py."""
import shutil
from types import SimpleNamespace

import pytest

import hd_helpers as H
from src.pipeline import helene_depth as hd


@pytest.fixture(scope="session")
def _root_template(tmp_path_factory):
    root = tmp_path_factory.mktemp("hd_template")
    H.build_root(root)
    return root


@pytest.fixture
def mini_root(tmp_path, _root_template):
    """A fresh copy of the synthetic project: every test may write to it."""
    root = tmp_path / "mini" / "root"
    shutil.copytree(_root_template, root)
    return SimpleNamespace(root=root, p=hd.paths(root))


@pytest.fixture(scope="session")
def built_template(tmp_path_factory, _root_template):
    """The synthetic project after one full run, for tests that only read the outputs."""
    root = tmp_path_factory.mktemp("hd_built") / "root"
    shutil.copytree(_root_template, root)
    validation = hd.run(root, say=lambda *_: None)
    return SimpleNamespace(root=root, p=hd.paths(root), validation=validation)


@pytest.fixture
def built_root(tmp_path, built_template):
    """A fresh copy of the synthetic project with its outputs already built."""
    root = tmp_path / "built" / "root"
    shutil.copytree(built_template.root, root)
    return SimpleNamespace(root=root, p=hd.paths(root), validation=built_template.validation)
