from __future__ import annotations

import json
import subprocess
from pathlib import Path

from visual_vibe_coding_skill.inspector import inspect_project


def test_inspect_project_builds_mermaid_and_file_notes(tmp_path: Path) -> None:
    project_root = tmp_path / "demo"
    src_dir = project_root / "src"
    tests_dir = project_root / "tests"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir()

    (project_root / "README.md").write_text("# Demo\n\nA small mail agent.\n", encoding="utf-8")
    (project_root / "package.json").write_text(json.dumps({"name": "demo-mail-agent", "main": "src/index.ts"}), encoding="utf-8")
    (src_dir / "index.ts").write_text("import { run } from './runtime';\nexport function main() { return run(); }\n", encoding="utf-8")
    (src_dir / "runtime.ts").write_text("export function run() { return process.env.SMTP_HOST || 'ok'; }\n", encoding="utf-8")
    (tests_dir / "runtime.test.ts").write_text("test('run', () => {});\n", encoding="utf-8")

    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=project_root, check=True, capture_output=True)

    payload, markdown = inspect_project(project_root, trace_source="none", memory_enabled=False)

    assert payload["project_name"] == "demo-mail-agent"
    assert payload["files_scanned"] >= 4
    assert "```mermaid" in markdown
    assert any(item["relpath"] == "src/index.ts" for item in payload["file_notes"])
