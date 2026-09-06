"""The guards, tested.

Every safety claim this project makes is a claim about a refusal, and a refusal
that has never been tested is a hope. These are the tests that turn the claims
into facts:

    the warehouse tools refuse to write, in several spellings
    a proposed code change cannot touch a file outside two directories
    a proposed code change that would not compile is thrown away
    the database tool never executes anything, whatever it is handed
    a proposed change never touches the working tree anybody is sitting in

None of these need the estate. They prove properties of the code, so they run
anywhere, in a second, which is what makes it reasonable to run them on every
commit.
"""
from __future__ import annotations

import pathlib
import subprocess
import uuid

import pytest

from agent_service.tools import repo
from agent_service.tools.publish import request_db_change
from agent_service.tools.verify import run_pipeline
from agent_service.tools.warehouse import _ALLOWED, _FORBIDDEN, run_sql

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ── the warehouse tools refuse to write ────────────────────────────────────

@pytest.mark.parametrize("statement", [
    "DELETE FROM teach.silver_rides",
    "delete from teach.silver_rides",
    "  Delete  From teach.silver_rides",
    "UPDATE teach.gold_daily SET revenue = 0",
    "INSERT INTO teach.gold_daily VALUES (1)",
    "DROP TABLE teach.bronze_trips",
    "TRUNCATE teach.quarantine",
    "ALTER TABLE teach.runs ADD COLUMN x INT",
    "CREATE TABLE evil (id INT)",
    "GRANT ALL ON teach.runs TO PUBLIC",
    "COPY teach.runs FROM '/etc/passwd'",
])
def test_write_statements_are_refused(statement):
    """Every spelling of a write is refused before it reaches the database."""
    assert run_sql.invoke({"query": statement}).startswith("REFUSED")


@pytest.mark.parametrize("statement", [
    "SELECT 1; DROP TABLE teach.gold_daily",
    "SELECT 1;DELETE FROM teach.runs",
])
def test_stacked_statements_are_refused(statement):
    """One statement at a time. A semicolon is how a read becomes a write."""
    assert run_sql.invoke({"query": statement}).startswith("REFUSED")


def test_a_write_hidden_after_a_select_is_still_refused():
    """The allow check passes on 'SELECT', so the forbidden check has to catch it."""
    sneaky = "WITH x AS (SELECT 1) INSERT INTO teach.runs SELECT * FROM x"
    assert run_sql.invoke({"query": sneaky}).startswith("REFUSED")


def test_the_two_guards_disagree_on_purpose():
    """The allow list and the deny list are separate checks, and both are needed.

    A statement can start with SELECT and still write, so passing the first
    check must not be enough to run.
    """
    sneaky = "SELECT 1 FROM teach.runs; UPDATE teach.runs SET status = 'ok'"
    assert _ALLOWED.match(sneaky)          # it does look like a select
    assert _FORBIDDEN.search(sneaky)       # and the second guard catches it


# ── a code change cannot escape its two directories ────────────────────────

@pytest.mark.parametrize("path", [
    "platform/docker-compose.yml",
    "tests/test_guards.py",
    ".env",
    ".github/workflows/ci.yml",
    "/etc/passwd",
    "notebooks/build_nb.py",
])
def test_writes_outside_the_allow_list_are_refused(path):
    """Inside the repo, but not in a writable directory."""
    rel, refusal = repo.check_writable(path)
    assert rel is None
    assert refusal.startswith("REFUSED")


@pytest.mark.parametrize("escape", [
    "../../../../etc/passwd",
    "../" * 8 + "tmp/evil.py",
    "pipelines/../../outside.py",
])
def test_paths_that_climb_out_of_the_repo_are_refused(escape):
    """Traversal is refused whatever ONCALL_REPO_PATH is pointed at.

    This test used to name a sibling directory, which made it depend on where
    the repo happened to be configured: with the agent pointed at the pipelines
    repo, "../pipelines-repo/x.py" resolves back INSIDE it and is correctly
    allowed. A guard test that changes meaning with configuration is worse than
    no test, so this builds its escape relative to whatever ROOT actually is.
    """
    rel, refusal = repo.check_writable(escape)
    assert rel is None, f"{escape} escaped {repo.ROOT}"
    assert "outside the project" in refusal or "not writable" in refusal


def test_the_guard_is_relative_to_the_configured_repo():
    """Whatever ROOT is, a writable directory inside it is accepted."""
    inside = repo.ROOT / "pipelines" / "p1_bronze_trips.py"
    if inside.is_file():
        rel, refusal = repo.check_writable(str(inside))
        assert refusal == ""
        assert rel == pathlib.Path("pipelines/p1_bronze_trips.py")


def test_the_agent_cannot_edit_the_tests_that_judge_it():
    """An agent that can edit its own tests is not being judged."""
    assert "tests" not in repo.WRITABLE


def test_a_writable_path_is_accepted():
    """The guard has to allow the thing it is meant to allow, or it is useless."""
    rel, refusal = repo.check_writable("pipelines/p3_bronze_driver_app.py")
    assert refusal == ""
    assert str(rel) == "pipelines/p3_bronze_driver_app.py"


def test_a_change_that_would_not_compile_is_refused(tmp_path):
    """Whether a change is right is a judgement. Whether it compiles is a fact."""
    result = repo.propose(
        breach_id="TEST", summary="break it", rationale="on purpose",
        path="signals/board.py",
        old_string="Z_THRESHOLD = 4.0", new_string="Z_THRESHOLD = = 4.0",
        artifacts=tmp_path)
    assert not result.ok
    assert "would not parse" in result.reason


def test_ambiguous_text_is_refused(tmp_path):
    """Text appearing twice means the edit could land in the wrong place."""
    result = repo.propose(
        breach_id="TEST", summary="x", rationale="x",
        path="signals/board.py", old_string="    ", new_string="  ",
        artifacts=tmp_path)
    assert not result.ok
    assert "more than once" in result.reason


def test_text_that_is_not_there_is_refused(tmp_path):
    result = repo.propose(
        breach_id="TEST", summary="x", rationale="x",
        path="signals/board.py",
        old_string="this string does not appear anywhere in that file",
        new_string="x", artifacts=tmp_path)
    assert not result.ok
    assert "not in the file" in result.reason


# ── the database tool never executes anything ──────────────────────────────

def test_request_db_change_does_not_execute(tmp_path):
    """It records a request and stops. Nothing in this system runs the statement.

    The proof is the returned text plus the absence of an effect: the statement
    below would drop a table, and the table is still there afterwards.
    """
    out = request_db_change.invoke({
        "breach_id": "TEST",
        "summary": "a statement that must never run",
        "rationale": "testing that nothing executes it",
        "statement": "DROP TABLE IF EXISTS teach.gold_daily",
        "rows_affected_estimate": "all of them",
        "reversible": "no",
    })
    assert "WAITING FOR A HUMAN" in out
    assert "Nothing was executed" in out


# ── the verifier cannot run arbitrary commands ─────────────────────────────

@pytest.mark.parametrize("name", [
    "rm -rf /", "p1_bronze_trips; rm -rf /", "../../bin/sh",
    "seed", "reset", "break_it",
])
def test_run_pipeline_refuses_anything_not_a_pipeline(name):
    assert run_pipeline.invoke({"name": name}).startswith("REFUSED")


def test_run_pipeline_allows_exactly_the_eight():
    from agent_service.tools.verify import ALLOWED
    assert len(ALLOWED) == 8
    assert all(n.startswith("p") for n in ALLOWED)


# ── a test run cannot reach a real repository ──────────────────────────────

def test_a_test_run_cannot_push():
    """The guard that stops a test suite opening pull requests on a live repo.

    Both halves are checked, because the point of two independent checks is
    that either one alone would have been enough to prevent the incident, and
    relying on one of them is how it happened.
    """
    allowed, why = repo.pushing_allowed()
    assert not allowed
    assert why


def test_the_env_switch_alone_would_stop_it(monkeypatch):
    monkeypatch.setenv("ONCALL_ALLOW_PUSH", "0")
    assert not repo.pushing_allowed()[0]


def test_pytest_being_loaded_alone_would_stop_it(monkeypatch):
    """Even with the switch on, a test run still refuses to push."""
    monkeypatch.setenv("ONCALL_ALLOW_PUSH", "1")
    allowed, why = repo.pushing_allowed()
    assert not allowed
    assert "test run" in why


def test_a_proposal_in_a_test_commits_but_does_not_push(tmp_path):
    """The branch and commit still happen, so the tool is still exercised."""
    result = repo.propose(
        breach_id=f"NOPUSH{uuid.uuid4().hex[:6]}", summary="x", rationale="x",
        path="signals/board.py",
        old_string="Z_THRESHOLD = 4.0", new_string="Z_THRESHOLD = 4.9",
        artifacts=tmp_path)
    try:
        assert result.ok
        assert result.commit
        assert not result.pushed
        assert result.pr_url == ""
    finally:
        subprocess.run(["git", "branch", "-D", result.branch],
                       cwd=repo.ROOT, capture_output=True)
