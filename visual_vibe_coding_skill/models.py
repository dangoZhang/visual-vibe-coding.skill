from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TraceSession:
    source: str
    path: Path
    cwd: str | None
    timestamp: str | None
    user_messages: list[str] = field(default_factory=list)
    assistant_messages: list[str] = field(default_factory=list)
    mentioned_files: list[str] = field(default_factory=list)


@dataclass
class TraceDigest:
    sessions: list[TraceSession] = field(default_factory=list)
    hot_files: list[tuple[str, int]] = field(default_factory=list)
    recent_tasks: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class GitCommit:
    short_sha: str
    authored_at: str
    subject: str


@dataclass
class GitSnapshot:
    root: Path | None
    branch: str | None
    head: str | None
    remote: str | None
    dirty_files: list[str] = field(default_factory=list)
    recent_commits: list[GitCommit] = field(default_factory=list)
    recent_files: list[str] = field(default_factory=list)


@dataclass
class FileNote:
    relpath: str
    category: str
    language: str
    line_count: int
    priority: int
    role_hint: str
    behavior: str
    is_entrypoint: bool = False
    reasons: list[str] = field(default_factory=list)
    raw_imports: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    mentioned_by_trace: int = 0
    touched_by_git: int = 0


@dataclass
class ProjectScan:
    project_root: Path
    project_name: str
    purpose: str
    entrypoints: list[str]
    files: list[FileNote]
    skipped_files: int
    directory_summary: list[tuple[str, int]]
    mermaid_edges: list[tuple[str, str]]

