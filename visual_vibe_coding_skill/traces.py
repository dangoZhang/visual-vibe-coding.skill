from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from .models import TraceDigest, TraceSession


CODEX_LOCATIONS = [
    Path("~/.codex/sessions").expanduser(),
    Path("~/.codex/archived_sessions").expanduser(),
]

CLAUDE_LOCATIONS = [
    Path("~/.claude/projects").expanduser(),
]

FILE_MENTION_PATTERN = re.compile(
    r"(?:~?/[\w./-]+|[\w./-]+\.(?:py|ts|tsx|js|jsx|mjs|cjs|json|md|toml|ya?ml|sql|sh|go|rs|java|rb|php|swift|kt))"
)


def discover_trace_digest(project_root: Path, source: str = "auto", limit: int = 6) -> TraceDigest:
    project_root = project_root.expanduser().resolve()
    sessions: list[TraceSession] = []

    if source in {"auto", "codex"}:
        sessions.extend(_load_recent_codex_sessions(project_root, limit))
    if source in {"auto", "claude"}:
        sessions.extend(_load_recent_claude_sessions(project_root, limit))

    sessions.sort(key=lambda item: item.timestamp or "", reverse=True)
    sessions = sessions[:limit]

    hot_file_counter: Counter[str] = Counter()
    recent_tasks: list[str] = []
    seen_tasks: set[str] = set()
    for session in sessions:
        hot_file_counter.update(session.mentioned_files)
        for message in session.user_messages:
            task = _compact_text(message)
            if not task or _looks_like_meta_prompt(task):
                continue
            if task not in seen_tasks:
                recent_tasks.append(task[:140])
                seen_tasks.add(task)
            break

    hot_files = hot_file_counter.most_common(8)
    sources = sorted({session.source for session in sessions})
    summary_parts = [f"匹配到 {len(sessions)} 条轨迹"]
    if sources:
        summary_parts.append(f"来源 {', '.join(sources)}")
    if hot_files:
        hot_labels = ", ".join(f"{path} x{count}" for path, count in hot_files[:4])
        summary_parts.append(f"高频文件 {hot_labels}")
    summary = "；".join(summary_parts) if sessions else "没有匹配到与当前仓库关联的轨迹。"

    return TraceDigest(
        sessions=sessions,
        hot_files=hot_files,
        recent_tasks=recent_tasks[:8],
        summary=summary,
    )


def iter_default_trace_roots(source: str = "auto") -> list[Path]:
    roots: list[Path] = []
    if source in {"auto", "codex"}:
        roots.extend(CODEX_LOCATIONS)
    if source in {"auto", "claude"}:
        roots.extend(CLAUDE_LOCATIONS)
    return roots


def _load_recent_codex_sessions(project_root: Path, limit: int) -> list[TraceSession]:
    sessions: list[TraceSession] = []
    for path in _recent_jsonl_files(CODEX_LOCATIONS, limit * 24):
        session = _parse_codex_session(path, project_root)
        if session is None:
            continue
        sessions.append(session)
        if len(sessions) >= limit * 2:
            break
    return sessions


def _load_recent_claude_sessions(project_root: Path, limit: int) -> list[TraceSession]:
    sessions: list[TraceSession] = []
    for path in _recent_jsonl_files(CLAUDE_LOCATIONS, limit * 24):
        session = _parse_claude_session(path, project_root)
        if session is None:
            continue
        sessions.append(session)
        if len(sessions) >= limit * 2:
            break
    return sessions


def _parse_codex_session(path: Path, project_root: Path) -> TraceSession | None:
    cwd: str | None = None
    timestamp: str | None = None
    user_messages: list[str] = []
    assistant_messages: list[str] = []
    mentioned_files: list[str] = []

    for item in _iter_jsonl(path):
        item_type = item.get("type")
        payload = item.get("payload") or {}
        if item_type == "session_meta":
            cwd = (payload.get("cwd") or "").strip() or None
            timestamp = payload.get("timestamp") or item.get("timestamp")
            if not _cwd_matches_project(cwd, project_root):
                return None
            continue
        if cwd is None:
            continue
        if item_type == "event_msg" and payload.get("type") == "user_message":
            text = payload.get("message") or _flatten_text(payload.get("text_elements"))
            if text:
                user_messages.append(text)
                mentioned_files.extend(_extract_file_mentions(text, project_root))
        elif item_type == "response_item" and payload.get("type") == "message":
            text = _flatten_text(payload.get("content"))
            if text:
                assistant_messages.append(text)
                mentioned_files.extend(_extract_file_mentions(text, project_root))

    if cwd is None:
        return None
    return TraceSession(
        source="codex",
        path=path,
        cwd=cwd,
        timestamp=timestamp,
        user_messages=user_messages,
        assistant_messages=assistant_messages,
        mentioned_files=mentioned_files,
    )


def _parse_claude_session(path: Path, project_root: Path) -> TraceSession | None:
    cwd: str | None = None
    timestamp: str | None = None
    user_messages: list[str] = []
    assistant_messages: list[str] = []
    mentioned_files: list[str] = []

    for item in _iter_jsonl(path):
        timestamp = timestamp or item.get("timestamp")
        if cwd is None:
            candidate_cwd = (item.get("cwd") or "").strip() or None
            if candidate_cwd:
                cwd = candidate_cwd
                if not _cwd_matches_project(cwd, project_root):
                    return None
        if cwd is None:
            continue
        item_type = item.get("type")
        if item_type not in {"user", "assistant"}:
            continue
        message = item.get("message") or {}
        text = _flatten_text(message.get("content") if isinstance(message, dict) else message)
        if not text:
            continue
        if item_type == "user":
            user_messages.append(text)
        else:
            assistant_messages.append(text)
        mentioned_files.extend(_extract_file_mentions(text, project_root))

    if cwd is None:
        return None
    return TraceSession(
        source="claude",
        path=path,
        cwd=cwd,
        timestamp=timestamp,
        user_messages=user_messages,
        assistant_messages=assistant_messages,
        mentioned_files=mentioned_files,
    )


def _recent_jsonl_files(roots: list[Path], limit: int) -> list[Path]:
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            if path.is_file():
                candidates.append(path)
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[:limit]


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _flatten_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item.get("text", "")))
                elif "message" in item:
                    parts.append(str(item.get("message", "")))
                elif "content" in item:
                    parts.append(_flatten_text(item.get("content")))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if "text" in value:
            return _flatten_text(value.get("text"))
        if "content" in value:
            return _flatten_text(value.get("content"))
    return ""


def _extract_file_mentions(text: str, project_root: Path) -> list[str]:
    mentions: list[str] = []
    for raw in FILE_MENTION_PATTERN.findall(text):
        token = raw if isinstance(raw, str) else raw[0]
        normalized = _normalize_file_mention(token, project_root)
        if normalized:
            mentions.append(normalized)
    return mentions


def _normalize_file_mention(token: str, project_root: Path) -> str | None:
    token = token.strip().strip("`'\"()[]{}.,:;")
    if not token or token in {".", ".."} or token.startswith("http://") or token.startswith("https://"):
        return None
    if token.lower() in {"next.js", "node.js", "javascript", "typescript", "python"}:
        return None
    if token.endswith("/"):
        return None
    path = Path(token).expanduser()
    if path.is_absolute():
        resolved = path.resolve(strict=False)
        try:
            return str(resolved.relative_to(project_root))
        except ValueError:
            return None
    candidate = (project_root / token).resolve(strict=False)
    if candidate.exists():
        try:
            return str(candidate.relative_to(project_root))
        except ValueError:
            return token
    if token in {"package.json", "README.md", "README.zh-CN.md", "SKILL.md", "AGENTS.md", "pyproject.toml", "Dockerfile"}:
        return token
    if "/" in token:
        return token
    return None


def _cwd_matches_project(cwd: str | None, project_root: Path) -> bool:
    if not cwd:
        return False
    cwd_path = Path(cwd).expanduser().resolve(strict=False)
    root = project_root.resolve(strict=False)
    return cwd_path == root or str(cwd_path).startswith(f"{root}{os.sep}")


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_meta_prompt(text: str) -> bool:
    lower = text.lower()
    return (
        lower.startswith("/codex:")
        or "<command-message>" in lower
        or "codex-companion.mjs setup" in lower
        or lower.startswith("run:\n")
    )
