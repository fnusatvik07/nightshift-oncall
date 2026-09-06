"""Shared fixtures.

The tests split into two kinds, and the split matters.

**Guard tests** need nothing running. They prove that a refusal happens, which
is a property of the code rather than of the estate, so they run in CI on a
machine with no Docker and no database.

**Estate tests** need the warehouse. They are marked `needs_estate` and skip
themselves with a clear message when it is not there, rather than failing and
teaching everybody to ignore a red suite.
"""
from __future__ import annotations

import os

import pytest

# Nothing in a test run may push a branch or open a pull request.
#
# This is set before anything imports the agent tools, because the tests call
# the real propose() and the repository it targets is configurable. It was not
# always here: a test run once opened seven pull requests on a live GitHub
# repository, which is exactly the kind of quiet side effect this project
# spends eighteen notebooks warning about.
os.environ["ONCALL_ALLOW_PUSH"] = "0"


def _warehouse_reachable() -> bool:
    try:
        import psycopg
        from pipelines.lib.config import dsn
        with psycopg.connect(dsn(), connect_timeout=3) as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False


ESTATE_UP = _warehouse_reachable()


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "needs_estate: requires the docker estate to be running")


def pytest_collection_modifyitems(config, items):
    if ESTATE_UP:
        return
    skip = pytest.mark.skip(reason="the estate is not running: "
                                   "docker compose -f platform/docker-compose.yml up -d")
    for item in items:
        if "needs_estate" in item.keywords:
            item.add_marker(skip)
