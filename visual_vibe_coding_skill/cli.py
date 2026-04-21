from __future__ import annotations

import argparse
import json
from pathlib import Path

from .inspector import inspect_project
from .memory import DEFAULT_MEMORY_ROOT
from .traces import iter_default_trace_roots


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visual-vibe-coding",
        description="Read traces, Git, and source files to explain a vibe-coded project without forcing the user to read the whole repo.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect a project and build a visual logic report.")
    inspect.add_argument("--project", default=".", help="Project root to inspect.")
    inspect.add_argument("--trace-source", choices=["auto", "codex", "claude", "none"], default="auto")
    inspect.add_argument("--trace-alias", action="append", default=[], help="Extra historical project path to match old traces after moving or renaming a repo.")
    inspect.add_argument("--trace-limit", type=int, default=6)
    inspect.add_argument("--max-files", type=int, default=600)
    inspect.add_argument("--memory", dest="memory_enabled", action="store_true")
    inspect.add_argument("--no-memory", dest="memory_enabled", action="store_false")
    inspect.set_defaults(memory_enabled=True)
    inspect.add_argument("--output", help="Write markdown output to this file.")
    inspect.add_argument("--json-output", help="Write structured JSON output to this file.")

    scan = subparsers.add_parser("scan-traces", help="Show which traces match the current project.")
    scan.add_argument("--project", default=".", help="Project root to match against.")
    scan.add_argument("--trace-source", choices=["auto", "codex", "claude"], default="auto")
    scan.add_argument("--trace-alias", action="append", default=[], help="Extra historical project path to match old traces after moving or renaming a repo.")
    scan.add_argument("--trace-limit", type=int, default=6)
    scan.add_argument("--json-output", help="Write structured JSON output to this file.")

    doctor = subparsers.add_parser("doctor", help="Show default trace roots and memory location.")
    doctor.add_argument("--json-output", help="Write doctor data to this file.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "inspect":
        payload, markdown = inspect_project(
            args.project,
            trace_source=args.trace_source,
            trace_aliases=args.trace_alias,
            trace_limit=args.trace_limit,
            max_files=args.max_files,
            memory_enabled=args.memory_enabled,
        )
        _write_optional(args.output, markdown)
        _write_optional(args.json_output, json.dumps(payload, ensure_ascii=False, indent=2))
        if not args.output:
            print(markdown)
        return

    if args.command == "scan-traces":
        payload, _markdown = inspect_project(
            args.project,
            trace_source=args.trace_source,
            trace_aliases=args.trace_alias,
            trace_limit=args.trace_limit,
            max_files=1,
            memory_enabled=False,
        )
        summary = {
            "project_root": payload["project_root"],
            "trace": payload["trace"],
        }
        serialized = json.dumps(summary, ensure_ascii=False, indent=2)
        _write_optional(args.json_output, serialized)
        print(serialized)
        return

    doctor_payload = {
        "trace_roots": [str(path) for path in iter_default_trace_roots()],
        "memory_root": str(DEFAULT_MEMORY_ROOT),
    }
    serialized = json.dumps(doctor_payload, ensure_ascii=False, indent=2)
    _write_optional(getattr(args, "json_output", None), serialized)
    print(serialized)


def _write_optional(path: str | None, content: str) -> None:
    if not path:
        return
    output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
