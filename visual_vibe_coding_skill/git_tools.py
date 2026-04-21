from __future__ import annotations

import subprocess
from pathlib import Path

from .models import GitCommit, GitSnapshot


def capture_git_snapshot(project_root: Path, commit_limit: int = 8) -> GitSnapshot:
    root = _git_root(project_root)
    if root is None:
        return GitSnapshot(root=None, branch=None, head=None, remote=None)

    branch = _run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    head = _run_git(root, ["rev-parse", "HEAD"])
    remote = _run_git(root, ["remote", "get-url", "origin"])

    dirty_files: list[str] = []
    for line in _run_git(root, ["status", "--short"]).splitlines():
        if not line.strip():
            continue
        dirty_files.append(line[3:] if len(line) > 3 else line)

    recent_commits: list[GitCommit] = []
    commit_lines = _run_git(
        root,
        ["log", f"-n{commit_limit}", "--date=short", "--pretty=format:%h\t%ad\t%s"],
    ).splitlines()
    for line in commit_lines:
        parts = line.split("\t", 2)
        if len(parts) == 3:
            recent_commits.append(GitCommit(short_sha=parts[0], authored_at=parts[1], subject=parts[2]))

    recent_files = []
    seen_files: set[str] = set()
    for line in _run_git(root, ["log", f"-n{commit_limit}", "--name-only", "--pretty=format:"]).splitlines():
        item = line.strip()
        if not item or item in seen_files:
            continue
        seen_files.add(item)
        recent_files.append(item)

    return GitSnapshot(
        root=root,
        branch=branch or None,
        head=head or None,
        remote=remote or None,
        dirty_files=dirty_files,
        recent_commits=recent_commits,
        recent_files=recent_files,
    )


def _git_root(project_root: Path) -> Path | None:
    output = _run_git(project_root, ["rev-parse", "--show-toplevel"])
    return Path(output).resolve() if output else None


def _run_git(project_root: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()
