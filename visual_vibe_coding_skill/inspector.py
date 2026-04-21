from __future__ import annotations

from dataclasses import asdict
from collections import Counter
from pathlib import Path

from .git_tools import capture_git_snapshot
from .memory import build_snapshot, compare_snapshots, load_snapshot, save_snapshot
from .project_scan import scan_project
from .render import build_key_risks, render_markdown, render_mermaid
from .traces import discover_trace_digest


def inspect_project(
    project_root: str | Path,
    *,
    trace_source: str = "auto",
    trace_aliases: list[str] | None = None,
    trace_limit: int = 6,
    max_files: int = 600,
    memory_enabled: bool = True,
) -> tuple[dict, str]:
    requested_root = Path(project_root).expanduser().resolve()
    if not requested_root.exists():
        raise SystemExit(f"Project path does not exist: {requested_root}")
    git_snapshot = capture_git_snapshot(requested_root)
    scan_root = git_snapshot.root or requested_root
    trace_digest = (
        discover_trace_digest(scan_root, source=trace_source, limit=trace_limit, trace_aliases=trace_aliases)
        if trace_source != "none"
        else discover_trace_digest(scan_root, source="none", limit=0, trace_aliases=trace_aliases)
    )
    project_scan = scan_project(scan_root, trace_digest, git_snapshot, max_files=max_files)
    scanned_paths = {note.relpath for note in project_scan.files}
    filtered_hot_files = [
        (path, count)
        for path, count in trace_digest.hot_files
        if path in scanned_paths or path in {"package.json", "README.md", "README.zh-CN.md", "SKILL.md", "AGENTS.md", "pyproject.toml", "Dockerfile"}
    ]

    snapshot_path = None
    previous_snapshot = None
    memory_delta = {
        "summary": "已禁用记忆。",
        "focus_added": [],
        "focus_removed": [],
        "same_head": False,
    }
    current_snapshot = build_snapshot(project_scan, git_snapshot, trace_digest)
    if memory_enabled:
        snapshot_path, previous_snapshot = load_snapshot(scan_root)
        memory_delta = compare_snapshots(previous_snapshot, current_snapshot)
        snapshot_path = save_snapshot(scan_root, current_snapshot)

    reading_order = [
        {
            "path": note.relpath,
            "role_hint": note.role_hint,
            "reasons": note.reasons,
        }
        for note in _select_reading_order(project_scan.files, limit=12)
    ]
    file_notes = [asdict(note) for note in project_scan.files]
    mermaid = render_mermaid(project_scan.mermaid_edges)
    logic_chain = _build_logic_chain(project_scan.files)

    payload = {
        "project_root": str(project_scan.project_root),
        "project_name": project_scan.project_name,
        "purpose": project_scan.purpose,
        "entrypoints": project_scan.entrypoints,
        "files_scanned": len(project_scan.files),
        "files_skipped": project_scan.skipped_files,
        "reading_order": reading_order,
        "logic_chain": logic_chain,
        "directory_summary": [{"directory": name, "count": count} for name, count in project_scan.directory_summary],
        "mermaid": mermaid,
        "trace": {
            "summary": _build_trace_summary(trace_digest.sessions, filtered_hot_files),
            "sessions": [
                {
                    "source": session.source,
                    "path": str(session.path),
                    "timestamp": session.timestamp,
                    "top_prompt": _session_top_prompt(session.user_messages),
                }
                for session in trace_digest.sessions
            ],
            "hot_files": [{"path": path, "count": count} for path, count in filtered_hot_files],
            "recent_tasks": trace_digest.recent_tasks,
        },
        "git": {
            "root": str(git_snapshot.root) if git_snapshot.root else None,
            "branch": git_snapshot.branch,
            "head": git_snapshot.head,
            "remote": git_snapshot.remote,
            "dirty_files": git_snapshot.dirty_files,
            "recent_commits": [asdict(commit) for commit in git_snapshot.recent_commits],
        },
        "memory": {
            "path": str(snapshot_path) if snapshot_path else None,
            **memory_delta,
            "previous_snapshot": previous_snapshot,
        },
        "key_risks": build_key_risks(file_notes),
        "file_notes": file_notes,
    }
    payload["directory_summary"] = [
        {"directory": item["directory"], "count": item["count"]} for item in payload["directory_summary"]
    ]
    markdown = render_markdown(
        {
            **payload,
            "directory_summary": [f"{item['directory']}/ ({item['count']} files)" for item in payload["directory_summary"]],
        }
    )
    return payload, markdown


def _session_top_prompt(messages: list[str]) -> str:
    for message in messages:
        compact = " ".join(message.split())
        if not compact or compact.startswith("/codex:") or "<command-message>" in compact.lower():
            continue
        return compact[:140]
    return ""


def _build_trace_summary(sessions: list, hot_files: list[tuple[str, int]]) -> str:
    if not sessions:
        return "没有匹配到与当前仓库关联的轨迹。"
    sources = sorted({session.source for session in sessions})
    parts = [f"匹配到 {len(sessions)} 条轨迹", f"来源 {', '.join(sources)}"]
    if hot_files:
        parts.append("高频文件 " + ", ".join(f"{path} x{count}" for path, count in hot_files[:4]))
    return "；".join(parts)


def _select_reading_order(notes: list, limit: int) -> list:
    selected = []
    bucket_counts: Counter[str] = Counter()
    category_limits = {
        "source": 8,
        "test": 2,
        "config": 2,
        "script": 2,
        "doc": 1,
    }
    category_counts: Counter[str] = Counter()

    for note in notes:
        if not note.reasons:
            continue
        if category_counts[note.category] >= category_limits.get(note.category, 2):
            continue
        bucket = _note_bucket(note.relpath)
        bucket_limit = 2 if bucket == "src/cli" else 1
        if bucket_counts[bucket] >= bucket_limit:
            continue
        selected.append(note)
        bucket_counts[bucket] += 1
        category_counts[note.category] += 1
        if len(selected) >= limit:
            return selected

    for note in notes:
        if note in selected:
            continue
        if not note.reasons:
            continue
        if category_counts[note.category] >= category_limits.get(note.category, 2):
            continue
        selected.append(note)
        category_counts[note.category] += 1
        if len(selected) >= limit:
            return selected

    for note in notes:
        if note in selected:
            continue
        if category_counts[note.category] >= category_limits.get(note.category, 2):
            continue
        selected.append(note)
        category_counts[note.category] += 1
        if len(selected) >= limit:
            return selected
    return selected


def _note_bucket(relpath: str) -> str:
    parts = Path(relpath).parts
    if not parts:
        return relpath
    if parts[0] == "src" and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def _build_logic_chain(notes: list) -> list[dict[str, str]]:
    stages = [
        ("入口", lambda note: note.is_entrypoint and note.category == "source"),
        ("核心", lambda note: note.role_hint in {"运行时编排", "执行引擎", "业务逻辑", "接口层", "记忆层", "线程路由"}),
        ("依赖", lambda note: note.role_hint in {"外部服务适配层", "邮件服务适配层", "存储层", "数据访问层"}),
        ("验证", lambda note: note.category == "test"),
    ]
    chain: list[dict[str, str]] = []
    used_paths: set[str] = set()
    for label, predicate in stages:
        for note in notes:
            if note.relpath in used_paths:
                continue
            if not predicate(note):
                continue
            chain.append(
                {
                    "stage": label,
                    "path": note.relpath,
                    "role_hint": note.role_hint,
                    "why": "，".join(note.reasons[:3]) if note.reasons else note.behavior.rstrip("。"),
                }
            )
            used_paths.add(note.relpath)
            break
    return chain
