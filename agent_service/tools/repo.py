"""Proposing a code change, in isolation, and raising a pull request for it.

## The bug this file exists to prevent

The first version of this did `git checkout -b` in the project's own working
tree. It worked perfectly with one investigation and failed silently with two.

Two investigations ran at once. The first checked out its branch. The second was
half way through reading a file, found the contents had changed underneath it,
and was told:

    REFUSED: that exact text is not in the file.

The text WAS in the file. The message was a lie produced by a race, and an agent
reading it concludes its diagnosis was wrong and goes looking for a different
cause. No error, no crash, a plausible wrong answer, and nobody finds out.

That is the exact failure this whole project is about, committed by the project.

## The fix, which the architecture already called for

`git worktree add` gives each investigation **its own checkout** of the same
repository, in its own directory, on its own branch. Two investigations cannot
see each other's files, and the working tree a human is sitting in is never
touched at all.

    main working tree     never modified, never checked out, never stashed
    worktree per incident created at HEAD, edited, committed, then removed

That is the "worktree per incident" line in the scaling page of the
architecture, and it is not an optimisation. It is what makes a second
investigation safe.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
import uuid

PROJECT = pathlib.Path(__file__).resolve().parents[2]

# Which repository a proposed change is raised against.
#
# By default the agent proposes changes to the project it lives in, which is
# what you want on a laptop. In a real estate the pipelines live in their own
# repository with its own reviewers and its own CI, and the agent should raise
# a pull request THERE rather than in the repository it happens to run from.
#
# Point ONCALL_REPO_PATH at a local clone of that repository and nothing else
# changes: same tools, same guards, same isolation. The agent does not know or
# care which repository it is proposing against.
ROOT = pathlib.Path(os.environ.get("ONCALL_REPO_PATH", str(PROJECT))).expanduser().resolve()

# The only directories a proposed change may touch. An agent that can edit the
# tests which judge it is not being judged.
WRITABLE = ("pipelines", "signal_service", "signals", "agent_service")

TIMEOUT = 90


def _git(*args: str, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True,
                          text=True, timeout=TIMEOUT)


def have_repo() -> bool:
    return _git("rev-parse", "--git-dir").returncode == 0


def remote_url() -> str:
    r = _git("remote", "get-url", "origin")
    return r.stdout.strip() if r.returncode == 0 else ""


def check_writable(path: str) -> tuple[pathlib.Path | None, str]:
    """Is this path one an agent may propose changing?"""
    target = (ROOT / path).resolve()
    try:
        rel = target.relative_to(ROOT)
    except ValueError:
        return None, f"REFUSED: {path!r} is outside the project."
    if not rel.parts or rel.parts[0] not in WRITABLE:
        return None, (f"REFUSED: {path!r} is not writable. "
                      f"Writable directories: {', '.join(WRITABLE)}")
    if not target.is_file():
        return None, f"REFUSED: {path!r} does not exist."
    return rel, ""


def unified_diff(rel: pathlib.Path, old: str, new: str, before: str) -> str:
    """A real unified diff, so a person can read the change without a checkout."""
    import difflib
    after = before.replace(old, new)
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{rel}", tofile=f"b/{rel}", n=4))


class Proposal:
    """The result of trying to propose a change. Never raises."""

    def __init__(self) -> None:
        self.ok = False
        self.reason = ""
        self.diff = ""
        self.branch = ""
        self.commit = ""
        self.pushed = False
        self.pr_url = ""
        self.patch_path = ""

    def summary(self) -> str:
        if not self.ok:
            return self.reason
        lines = [f"branch {self.branch}, commit {self.commit[:8]}, "
                 f"main untouched in {ROOT.name}"]
        if self.pr_url:
            lines.append(f"pull request: {self.pr_url}")
        elif self.pushed:
            lines.append("branch pushed, but no pull request was opened")
        else:
            lines.append(f"no remote, so no pull request. Patch saved at {self.patch_path}")
        return "\n".join(lines)


def propose(breach_id: str, summary: str, rationale: str, path: str,
            old_string: str, new_string: str,
            artifacts: pathlib.Path | None = None) -> Proposal:
    """Apply one edit on an isolated branch and raise a pull request for it.

    Nothing on the main branch changes, nothing in the working tree changes, and
    the change is never merged.
    """
    out = Proposal()
    artifacts = artifacts or (ROOT / "artifacts" / "patches")
    artifacts.mkdir(parents=True, exist_ok=True)

    rel, refusal = check_writable(path)
    if rel is None:
        out.reason = refusal
        return out

    before = (ROOT / rel).read_text()
    if old_string not in before:
        out.reason = ("REFUSED: that exact text is not in the file. Read it again "
                      "with read_source and copy the text precisely, whitespace "
                      "included.")
        return out
    if before.count(old_string) > 1:
        out.reason = ("REFUSED: that text appears more than once. Include enough "
                      "surrounding lines to make it unique.")
        return out

    after = before.replace(old_string, new_string)

    # Whether a change is right is a judgement. Whether it compiles is a fact,
    # and facts get checked before a person is asked for an opinion.
    if rel.suffix == ".py":
        try:
            compile(after, str(rel), "exec")
        except SyntaxError as e:
            out.reason = f"REFUSED: the edited file would not parse. {e}"
            return out

    out.diff = unified_diff(rel, old_string, new_string, before)

    if not have_repo():
        patch = artifacts / f"{breach_id}-{rel.name}.patch"
        patch.write_text(out.diff)
        out.ok, out.patch_path = True, str(patch)
        out.reason = "no git repository, so the change is a patch file"
        return out

    # ── the isolated checkout ──────────────────────────────────────────────
    branch = f"oncall/{breach_id.lower()}-{rel.stem}"[:60]
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"oncall-{uuid.uuid4().hex[:6]}-"))
    work = tmp / "work"

    try:
        made = _git("worktree", "add", "--detach", str(work), "HEAD")
        if made.returncode != 0:
            out.reason = f"could not create an isolated checkout: {made.stderr[:200]}"
            return out

        if _git("checkout", "-b", branch, cwd=work).returncode != 0:
            # a branch of that name already exists, so reuse it rather than fail
            _git("checkout", branch, cwd=work)

        # apply the edit inside the isolated checkout, never in the live tree
        target = work / rel
        current = target.read_text()
        if old_string not in current:
            out.reason = ("REFUSED: the text is in your working copy but not in the "
                          "committed version. Commit or stash first.")
            return out
        target.write_text(current.replace(old_string, new_string))

        _git("add", str(rel), cwd=work)
        message = (f"{summary}\n\n{rationale}\n\n"
                   f"Raised automatically from breach {breach_id}. "
                   f"Nothing was merged and no data was changed.")
        committed = _git("commit", "-m", message, cwd=work)
        if committed.returncode != 0:
            out.reason = f"could not commit: {committed.stderr[:250]}"
            return out

        out.ok = True
        out.branch = branch
        out.commit = _git("rev-parse", "HEAD", cwd=work).stdout.strip()

        patch = artifacts / f"{breach_id}-{rel.name}.patch"
        patch.write_text(out.diff)
        out.patch_path = str(patch)

        # ── push and raise a pull request, if there is anywhere to push to ──
        if remote_url():
            pushed = _git("push", "-u", "origin", branch, cwd=work)
            out.pushed = pushed.returncode == 0
            if out.pushed:
                out.pr_url = _open_pull_request(branch, summary, rationale,
                                                breach_id, out.diff, work)
            else:
                out.reason = f"push failed: {pushed.stderr[:200]}"
        return out
    finally:
        # always tidy up, so a failed proposal does not leave checkouts behind
        _git("worktree", "remove", "--force", str(work))
        shutil.rmtree(tmp, ignore_errors=True)


def _open_pull_request(branch: str, title: str, rationale: str, breach_id: str,
                       diff: str, cwd: pathlib.Path) -> str:
    """Open the pull request with the GitHub CLI. Returns the URL, or "".

    gh is used rather than the REST API because it already holds the token a
    developer authenticated with, so there is no second credential to manage and
    nothing secret in this repository.
    """
    if not shutil.which("gh"):
        return ""

    body = (
        f"{rationale}\n\n"
        f"---\n\n"
        f"Raised automatically from signal breach `{breach_id}` by the NIGHTSHIFT "
        f"on call agent.\n\n"
        f"**Nothing was merged and no data was changed.** The agent proposed this "
        f"change; reviewing and merging it is a human decision.\n\n"
        f"<details><summary>The diff, inline</summary>\n\n"
        f"```diff\n{diff[:6000]}\n```\n\n</details>\n"
    )
    r = subprocess.run(
        ["gh", "pr", "create", "--title", title, "--body", body, "--head", branch],
        cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
    if r.returncode != 0:
        return ""
    for line in reversed(r.stdout.strip().splitlines()):
        if line.startswith("http"):
            return line.strip()
    return ""
