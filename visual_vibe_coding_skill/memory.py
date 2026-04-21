from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import GitSnapshot, ProjectScan, TraceDigest


DEFAULT_MEMORY_ROOT = Path("~/.visual-vibe-coding/memory").expanduser()


def load_snapshot(project_root: Path, memory_root: Path = DEFAULT_MEMORY_ROOT) -> tuple[Path, dict | None]:
    path = _snapshot_path(project_root, memory_root)
    if not path.exists():
        return path, None
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return path, None


def save_snapshot(project_root: Path, snapshot: dict, memory_root: Path = DEFAULT_MEMORY_ROOT) -> Path:
    path = _snapshot_path(project_root, memory_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_snapshot(project_scan: ProjectScan, git_snapshot: GitSnapshot, trace_digest: TraceDigest) -> dict:
    return {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_scan.project_root),
        "project_name": project_scan.project_name,
        "git_head": git_snapshot.head,
        "git_branch": git_snapshot.branch,
        "focus_files": [note.relpath for note in project_scan.files[:12]],
        "risk_files": [note.relpath for note in project_scan.files if note.risks][:20],
        "trace_hot_files": [path for path, _count in trace_digest.hot_files[:12]],
        "trace_session_count": len(trace_digest.sessions),
    }


def compare_snapshots(previous: dict | None, current: dict) -> dict:
    if previous is None:
        return {
            "summary": "第一次建立这份项目记忆，后续运行会对照这里的重点文件和风险。",
            "focus_added": current.get("focus_files", [])[:6],
            "focus_removed": [],
            "same_head": False,
        }

    previous_focus = set(previous.get("focus_files", []))
    current_focus = set(current.get("focus_files", []))
    focus_added = [item for item in current.get("focus_files", []) if item not in previous_focus][:8]
    focus_removed = [item for item in previous.get("focus_files", []) if item not in current_focus][:8]
    same_head = previous.get("git_head") == current.get("git_head")

    if same_head and not focus_added and not focus_removed:
        summary = "上次分析之后 Git HEAD 没变，重点文件也基本稳定。"
    elif same_head:
        summary = "Git HEAD 没变，但重点文件排序有变化，说明近期讨论焦点转移了。"
    else:
        old_head = (previous.get("git_head") or "")[:8] or "unknown"
        new_head = (current.get("git_head") or "")[:8] or "unknown"
        summary = f"Git HEAD 从 `{old_head}` 变到 `{new_head}`，需要按新改动重读关键链路。"

    return {
        "summary": summary,
        "focus_added": focus_added,
        "focus_removed": focus_removed,
        "same_head": same_head,
        "previous_saved_at": previous.get("saved_at"),
    }


def _snapshot_path(project_root: Path, memory_root: Path) -> Path:
    key = hashlib.sha1(str(project_root.resolve()).encode("utf-8")).hexdigest()[:12]
    slug = re_slug(project_root.name)
    return memory_root / f"{slug}-{key}.json"


def re_slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return slug or "project"
