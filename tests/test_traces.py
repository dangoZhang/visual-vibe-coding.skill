from __future__ import annotations

import json
from pathlib import Path

from visual_vibe_coding_skill.traces import _parse_claude_session, _parse_codex_session


def test_parse_codex_session_matches_project(tmp_path: Path) -> None:
    project_root = tmp_path / "demo"
    project_root.mkdir()
    trace_path = tmp_path / "codex.jsonl"
    events = [
        {
            "type": "session_meta",
            "timestamp": "2026-04-21T10:00:00Z",
            "payload": {
                "timestamp": "2026-04-21T10:00:00Z",
                "cwd": str(project_root),
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "Please inspect src/app.ts and package.json",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "content": [{"type": "text", "text": "I will read src/app.ts first."}],
            },
        },
    ]
    trace_path.write_text("\n".join(json.dumps(item) for item in events), encoding="utf-8")

    session = _parse_codex_session(trace_path, project_root)
    assert session is not None
    assert session.cwd == str(project_root)
    assert "src/app.ts" in session.mentioned_files


def test_parse_claude_session_matches_project(tmp_path: Path) -> None:
    project_root = tmp_path / "demo"
    project_root.mkdir()
    trace_path = tmp_path / "claude.jsonl"
    events = [
        {
            "type": "user",
            "timestamp": "2026-04-21T11:00:00Z",
            "cwd": str(project_root),
            "message": {"content": "Review src/runtime.ts for risks."},
        },
        {
            "type": "assistant",
            "timestamp": "2026-04-21T11:01:00Z",
            "cwd": str(project_root),
            "message": {"content": [{"type": "text", "text": "I see src/runtime.ts calling SMTP."}]},
        },
    ]
    trace_path.write_text("\n".join(json.dumps(item) for item in events), encoding="utf-8")

    session = _parse_claude_session(trace_path, project_root)
    assert session is not None
    assert session.source == "claude"
    assert "src/runtime.ts" in session.mentioned_files
