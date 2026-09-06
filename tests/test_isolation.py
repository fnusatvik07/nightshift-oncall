"""Concurrency, tested, because this is where it silently went wrong.

The first version of the code change tool did `git checkout -b` in the
project's own working tree. With one investigation it worked. With two it
produced this, reproduced in a throwaway repository:

    thread 1: reported "committed"     its branch contained the ORIGINAL file
    thread 2: reported "commit failed" its branch contained its change

A success report with no change in it, and a failure report with one. Nobody
would ever find that from the logs.

The fix is a git worktree per investigation. These tests hold it in place.
"""
from __future__ import annotations

import subprocess
import uuid
import threading

import pytest

from agent_service.tools import repo

pytestmark = pytest.mark.skipif(not repo.have_repo(),
                                reason="needs a git repository")


def _git(*args):
    return subprocess.run(["git", *args], cwd=repo.ROOT,
                          capture_output=True, text=True)


def _cleanup(*branches):
    for b in branches:
        _git("branch", "-D", b)


def _three_editable_files() -> list[tuple[str, str, str]]:
    """Find three real files in the configured repo, and a unique line in each.

    The target repository is configurable, so a test cannot name files and hope.
    It finds them, which also means this test keeps working when the agent is
    pointed at somebody else's pipelines repo.
    """
    found = []
    for folder in repo.WRITABLE:
        for path in sorted((repo.ROOT / folder).rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            body = path.read_text()
            for line in body.splitlines():
                stripped = line.strip()
                # a unique, safe line to append a comment to
                if (stripped.startswith(("TABLE = ", "SCHEMA = ", "GROUP = "))
                        and body.count(line) == 1):
                    rel = str(path.relative_to(repo.ROOT))
                    found.append((rel, line, line + "  # touched by a test"))
                    break
            if len(found) == 3:
                return found
    return found


def test_the_live_working_tree_is_never_touched(tmp_path):
    """A proposal must not change the branch or the files a human is using."""
    before_branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    before_status = _git("status", "--porcelain").stdout

    result = repo.propose(
        breach_id=f"ISO{uuid.uuid4().hex[:6]}", summary="test", rationale="test",
        path="signals/board.py",
        old_string="Z_THRESHOLD = 4.0", new_string="Z_THRESHOLD = 4.1",
        artifacts=tmp_path)

    assert result.ok, result.reason
    assert _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == before_branch
    assert _git("status", "--porcelain").stdout == before_status
    # and the change is on the branch rather than on disk
    assert "Z_THRESHOLD = 4.0" in (repo.ROOT / "signals" / "board.py").read_text()
    _cleanup(result.branch)


def test_three_at_once_all_succeed(tmp_path):
    """Three investigations, three files, no interference.

    Before the worktree fix, one of these would report success with an empty
    commit and the others would fail on a git lock.
    """
    files = _three_editable_files()
    if len(files) < 3:
        pytest.skip(f"only found {len(files)} editable files in {repo.ROOT}")

    run = uuid.uuid4().hex[:6]
    targets = [(f"C{i}{run}", path, old, new)
               for i, (path, old, new) in enumerate(files, 1)]
    results = {}

    def go(bid, path, old, new):
        results[bid] = repo.propose(
            breach_id=bid, summary=f"{bid}", rationale="concurrency",
            path=path, old_string=old, new_string=new, artifacts=tmp_path)

    threads = [threading.Thread(target=go, args=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert len(results) == 3
        for bid, r in results.items():
            assert r.ok, f"{bid}: {r.reason}"
            assert r.commit, f"{bid} committed nothing"
            # the commit must actually contain the change, which is the bit
            # the old implementation got wrong while reporting success
            shown = _git("show", "--stat", "--format=", r.commit).stdout
            assert shown.strip(), f"{bid} produced an empty commit"
        assert len({r.branch for r in results.values()}) == 3
    finally:
        _cleanup(*[r.branch for r in results.values() if r.branch])
        assert _git("status", "--porcelain").stdout == ""


def test_no_worktrees_are_left_behind(tmp_path):
    """A failed or finished proposal tidies up after itself."""
    before = len(_git("worktree", "list").stdout.splitlines())

    ok = repo.propose(breach_id=f"TIDYA{uuid.uuid4().hex[:6]}", summary="x", rationale="x",
                      path="signals/board.py",
                      old_string="Z_THRESHOLD = 4.0", new_string="Z_THRESHOLD = 4.3",
                      artifacts=tmp_path)
    bad = repo.propose(breach_id=f"TIDYB{uuid.uuid4().hex[:6]}", summary="x", rationale="x",
                       path="signals/board.py",
                       old_string="Z_THRESHOLD = 4.0", new_string="Z_THRESHOLD = = 4",
                       artifacts=tmp_path)

    assert ok.ok and not bad.ok
    assert len(_git("worktree", "list").stdout.splitlines()) == before
    _cleanup(ok.branch)


def test_an_existing_branch_is_reported_honestly(tmp_path):
    """The failure mode that made this suite flaky, pinned.

    Working the same breach twice used to silently reuse the branch. The file on
    it already had the change, so the old_string check failed and the caller was
    told "that text is not in the file", which was untrue and sent an agent
    hunting for a different cause.
    """
    bid = f"TWICE{uuid.uuid4().hex[:6]}"
    args = dict(breach_id=bid, summary="x", rationale="x",
                path="signals/board.py",
                old_string="Z_THRESHOLD = 4.0", new_string="Z_THRESHOLD = 4.4",
                artifacts=tmp_path)

    first = repo.propose(**args)
    assert first.ok, first.reason
    try:
        second = repo.propose(**args)
        assert not second.ok
        assert "already exists" in second.reason
        assert "not in the file" not in second.reason
    finally:
        _cleanup(first.branch)
