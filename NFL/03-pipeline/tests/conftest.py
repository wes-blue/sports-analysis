"""Shared fixtures: a fabricated upstream (no network) and temp project folders."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))      # tests/miniverse.py

import miniverse  # noqa: E402


@pytest.fixture
def upstream(monkeypatch):
    """The miniature nflverse release, installed in place of the downloader."""
    return miniverse.Upstream().install(monkeypatch)


@pytest.fixture
def project(tmp_path, upstream):
    """Empty temp project (config and fixtures written, nothing published yet)."""
    return miniverse.Project(tmp_path / "proj")


@pytest.fixture(scope="session")
def published_root(tmp_path_factory):
    """One complete mini publish, built once per session; tests copy it and never change it."""
    root = tmp_path_factory.mktemp("published") / "proj"
    with pytest.MonkeyPatch.context() as mp:
        miniverse.Upstream().install(mp)
        assert miniverse.Project(root).run() == 0, "the miniature pipeline should publish"
    return root


@pytest.fixture
def mini(tmp_path, published_root, upstream):
    """A private copy of the mini project after one PUBLISH (upstream installed)."""
    target = tmp_path / "proj"
    shutil.copytree(published_root, target)
    return miniverse.Project(target, write=False)
