from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .models import FileNote, GitSnapshot, ProjectScan, TraceDigest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "tmp",
    "output",
    ".turbo",
    ".demo",
    ".vercel",
    ".temp",
    "docs",
    "assets",
    "state",
    "vendor",
    "reference",
    ".cache",
    ".vitepress",
}

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".pptx",
    ".docx",
    ".zip",
    ".gz",
    ".tar",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".mp4",
    ".mov",
    ".mp3",
    ".sqlite",
    ".db",
    ".lock",
}

READABLE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".jsonl",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".css",
    ".scss",
    ".html",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".mts",
    ".cts",
}

SPECIAL_FILES = {
    "README",
    "README.md",
    "README.zh-CN.md",
    "README.en.md",
    "AGENTS.md",
    "SKILL.md",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
    "package.json",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "tsconfig.json",
    "tsconfig.build.json",
    ".env.example",
}

SKIP_FILES = {
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "bun.lock",
    "Cargo.lock",
}

JS_IMPORT_RE = re.compile(r"""(?:import|export)\s+.*?\sfrom\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)""")
PY_IMPORT_RE = re.compile(r"^(?:from\s+([.\w]+)\s+import|import\s+([\w.]+))", re.MULTILINE)
PY_SYMBOL_RE = re.compile(r"^(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
JS_SYMBOL_RE = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)|^(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)|^(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=",
    re.MULTILINE,
)


def scan_project(
    project_root: Path,
    trace_digest: TraceDigest,
    git_snapshot: GitSnapshot,
    max_files: int = 600,
) -> ProjectScan:
    project_root = project_root.resolve()
    project_name, purpose, entrypoints = _load_project_metadata(project_root)
    candidate_paths, skipped_files = _collect_candidate_files(project_root, max_files=max_files)

    trace_counter = Counter(path for path, count in trace_digest.hot_files for _ in range(count))
    git_counter = Counter(git_snapshot.recent_files)
    known_relpaths = {str(path.relative_to(project_root)) for path in candidate_paths}
    test_lookup = _build_test_lookup(known_relpaths)
    root_dirs = {Path(relpath).parts[0] for relpath in known_relpaths if Path(relpath).parts}

    notes: list[FileNote] = []
    for path in candidate_paths:
        relpath = str(path.relative_to(project_root))
        text = path.read_text(encoding="utf-8", errors="ignore")
        category = _classify_category(path, relpath)
        language = _detect_language(path)
        is_entrypoint = relpath in entrypoints or _looks_like_entrypoint(relpath, category, language)
        symbols = _extract_symbols(text, language)
        raw_imports = _extract_import_specs(text, language)
        role_hint = _guess_role_hint(relpath, category, is_entrypoint)
        risks = _detect_risks(
            text=text,
            relpath=relpath,
            category=category,
            language=language,
            line_count=text.count("\n") + 1,
            test_lookup=test_lookup,
        )
        note = FileNote(
            relpath=relpath,
            category=category,
            language=language,
            line_count=text.count("\n") + 1,
            priority=0,
            role_hint=role_hint,
            behavior="",
            is_entrypoint=is_entrypoint,
            raw_imports=raw_imports,
            symbols=symbols[:5],
            risks=risks,
            mentioned_by_trace=trace_counter[relpath],
            touched_by_git=git_counter[relpath],
        )
        note.imports = _resolve_imports(
            relpath=relpath,
            language=language,
            raw_imports=raw_imports,
            known_relpaths=known_relpaths,
            root_dirs=root_dirs,
        )
        note.priority, note.reasons = _score_note(note)
        note.behavior = _build_behavior(note)
        notes.append(note)

    indegree = Counter(imported for note in notes for imported in note.imports)
    for note in notes:
        if indegree[note.relpath]:
            note.priority += min(indegree[note.relpath], 5) * 4
            note.reasons.append(f"被 {indegree[note.relpath]} 个文件依赖")
        if note.imports:
            note.priority += min(len(note.imports), 5) * 2

    notes.sort(key=lambda item: (-item.priority, item.relpath))
    top_relpaths = {note.relpath for note in notes[:12]}
    mermaid_edges = _build_mermaid_edges(notes, top_relpaths)
    directory_summary = _summarize_directories(notes)

    return ProjectScan(
        project_root=project_root,
        project_name=project_name,
        purpose=purpose,
        entrypoints=entrypoints,
        files=notes,
        skipped_files=skipped_files,
        directory_summary=directory_summary,
        mermaid_edges=mermaid_edges,
    )


def _load_project_metadata(project_root: Path) -> tuple[str, str, list[str]]:
    project_name = project_root.name
    purpose = ""
    entrypoints: list[str] = []

    package_json = project_root / "package.json"
    if package_json.exists():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
            project_name = payload.get("name") or project_name
            main_file = payload.get("main")
            if isinstance(main_file, str):
                entrypoints.append(main_file)
            bin_field = payload.get("bin")
            if isinstance(bin_field, str):
                entrypoints.append(bin_field)
            elif isinstance(bin_field, dict):
                for value in bin_field.values():
                    if isinstance(value, str):
                        entrypoints.append(value)
        except json.JSONDecodeError:
            pass

    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project_name = payload.get("project", {}).get("name") or project_name
        except Exception:
            pass

    purpose = _readme_purpose(project_root) or purpose or "项目说明未直接写死，需要结合代码和轨迹反推。"

    for candidate in [
        "src/index.ts",
        "src/index.js",
        "src/app.ts",
        "src/app.js",
        "src/main.ts",
        "src/main.py",
        "src/cli.ts",
        "src/cli.py",
        "app.py",
        "main.py",
        "cli.py",
        "bin/main",
    ]:
        if (project_root / candidate).exists():
            entrypoints.append(candidate)

    deduped = []
    seen = set()
    for item in entrypoints:
        normalized = str(Path(item))
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return project_name, purpose, deduped


def _readme_purpose(project_root: Path) -> str:
    for name in ["README.md", "README.zh-CN.md", "README.en.md", "README"]:
        path = project_root / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("<") or line.startswith("!"):
                continue
            line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
            line = re.sub(r"`([^`]+)`", r"\1", line)
            return line[:220]
    return ""


def _collect_candidate_files(project_root: Path, max_files: int) -> tuple[list[Path], int]:
    candidates: list[Path] = []
    skipped = 0
    for root, dirs, files in _walk_project(project_root):
        for filename in sorted(files):
            path = Path(root) / filename
            if _should_skip_file(path):
                skipped += 1
                continue
            if not _should_read_file(path):
                skipped += 1
                continue
            candidates.append(path)
            if len(candidates) >= max_files:
                skipped += 1
                continue
    candidates = sorted(set(candidates))
    if len(candidates) > max_files:
        skipped += len(candidates) - max_files
        candidates = candidates[:max_files]
    return candidates, skipped


def _walk_project(project_root: Path):
    for root, dirs, files in __import__("os").walk(project_root):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        yield root, dirs, files


def _should_skip_file(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _should_read_file(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return False
    if path.name in SPECIAL_FILES:
        return True
    if path.suffix.lower() in BINARY_SUFFIXES:
        return False
    if path.suffix.lower() in READABLE_SUFFIXES:
        return path.stat().st_size <= 350_000
    if path.name.startswith("Dockerfile"):
        return True
    if path.name.startswith(".env") and "example" in path.name:
        return True
    return False


def _classify_category(path: Path, relpath: str) -> str:
    lower = relpath.lower()
    if path.name.lower().startswith("readme") or lower.endswith(".md"):
        return "doc"
    if "test" in path.parts or path.stem.endswith((".test", ".spec")):
        return "test"
    if path.parts and path.parts[0] in {"scripts", "bin"}:
        return "script"
    if path.suffix.lower() in {".json", ".toml", ".yaml", ".yml"} or path.name in SPECIAL_FILES:
        return "config"
    return "source"


def _detect_language(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "jsx",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".json": "json",
        ".jsonl": "jsonl",
        ".md": "markdown",
        ".toml": "toml",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".sql": "sql",
        ".sh": "shell",
        ".bash": "shell",
        ".zsh": "shell",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".css": "css",
        ".scss": "scss",
        ".html": "html",
        ".mts": "typescript",
        ".cts": "typescript",
    }.get(suffix, "text")


def _looks_like_entrypoint(relpath: str, category: str, language: str) -> bool:
    if category != "source":
        return False
    if language not in {"python", "typescript", "tsx", "javascript", "jsx", "go", "rust", "java", "ruby", "php", "swift", "kotlin"}:
        return False
    lower = relpath.lower()
    patterns = [
        "src/index.",
        "src/main.",
        "src/cli.",
        "src/app.",
        "/cli/",
        "/route.",
        "/page.",
        "/layout.",
        "app.py",
        "main.py",
        "cli.py",
    ]
    return any(token in lower for token in patterns)


def _extract_symbols(text: str, language: str) -> list[str]:
    if language == "python":
        return list(dict.fromkeys(PY_SYMBOL_RE.findall(text)))[:6]
    if language in {"typescript", "tsx", "javascript", "jsx"}:
        found = []
        for groups in JS_SYMBOL_RE.findall(text):
            found.extend([item for item in groups if item])
        return list(dict.fromkeys(found))[:6]
    return []


def _extract_import_specs(text: str, language: str) -> list[str]:
    specs: list[str] = []
    if language == "python":
        for left, right in PY_IMPORT_RE.findall(text):
            specs.append(left or right)
    if language in {"typescript", "tsx", "javascript", "jsx"}:
        for left, right in JS_IMPORT_RE.findall(text):
            specs.append(left or right)
    return list(dict.fromkeys(specs))


def _resolve_imports(
    relpath: str,
    language: str,
    raw_imports: list[str],
    known_relpaths: set[str],
    root_dirs: set[str],
) -> list[str]:
    resolved: list[str] = []
    current_dir = Path(relpath).parent
    for spec in raw_imports:
        candidate: str | None = None
        if spec.startswith("."):
            candidate = _resolve_path_spec(current_dir, spec, known_relpaths)
        elif language == "python":
            candidate = _resolve_module_spec(spec, known_relpaths)
        elif "/" in spec and spec.split("/", 1)[0] in root_dirs:
            candidate = _resolve_path_spec(Path("."), spec, known_relpaths)
        if candidate and candidate != relpath:
            resolved.append(candidate)
    return list(dict.fromkeys(resolved))


def _resolve_module_spec(spec: str, known_relpaths: set[str]) -> str | None:
    base = spec.replace(".", "/")
    for candidate in _candidate_relpaths(Path(base)):
        if candidate in known_relpaths:
            return candidate
    return None


def _resolve_path_spec(base_dir: Path, spec: str, known_relpaths: set[str]) -> str | None:
    base = (base_dir / spec).resolve().relative_to(Path.cwd().resolve()) if False else None
    joined = (base_dir / spec).as_posix()
    for candidate in _candidate_relpaths(Path(joined)):
        if candidate in known_relpaths:
            return candidate
    return None


def _candidate_relpaths(path: Path) -> list[str]:
    stem = path.as_posix().lstrip("./")
    candidates = [
        stem,
        f"{stem}.py",
        f"{stem}.ts",
        f"{stem}.tsx",
        f"{stem}.js",
        f"{stem}.jsx",
        f"{stem}.mjs",
        f"{stem}.cjs",
        f"{stem}.mts",
        f"{stem}/__init__.py",
        f"{stem}/index.ts",
        f"{stem}/index.tsx",
        f"{stem}/index.js",
        f"{stem}/index.jsx",
    ]
    return [candidate.lstrip("./") for candidate in candidates]


def _guess_role_hint(relpath: str, category: str, is_entrypoint: bool) -> str:
    lower = relpath.lower()
    if relpath.lower().startswith("readme"):
        return "项目总览入口"
    if is_entrypoint:
        return "运行入口"
    if category == "test":
        return "回归验证"
    if category == "config":
        return "配置基线"
    if category == "script":
        return "自动化脚本"
    for token, label in [
        ("cli", "命令行入口"),
        ("runtime", "运行时编排"),
        ("executor", "执行引擎"),
        ("memory", "记忆层"),
        ("thread", "线程路由"),
        ("storage", "存储层"),
        ("db", "数据访问层"),
        ("provider", "外部服务适配层"),
        ("smtp", "邮件服务适配层"),
        ("api", "接口层"),
        ("component", "界面组件"),
        ("view", "界面视图"),
        ("schema", "数据模式"),
        ("types", "类型边界"),
        ("bench", "实验场景"),
    ]:
        if token in lower:
            return label
    return "业务逻辑"


def _detect_risks(
    *,
    text: str,
    relpath: str,
    category: str,
    language: str,
    line_count: int,
    test_lookup: set[str],
) -> list[str]:
    risks: list[str] = []
    if line_count >= 380:
        risks.append("文件偏大，职责可能已经混在一起")
    if re.search(r"\b(eval|exec)\s*\(|new Function\(", text):
        risks.append("包含动态执行")
    if any(token in text for token in ["subprocess", "child_process", "shell=True", "os.system(", "spawn("]):
        risks.append("会拉起 shell 或子进程")
    if any(token in text for token in ["process.env", "os.environ", "getenv(", "import.meta.env"]):
        risks.append("强依赖环境变量")
    if re.search(r"\bTODO\b|\bFIXME\b|\bHACK\b", text):
        risks.append("留有 TODO/FIXME/HACK")
    if re.search(r"except\s*:\s*$", text, re.MULTILINE) or re.search(r"catch\s*\([^)]*\)\s*{\s*}", text):
        risks.append("异常处理偏宽，错误路径不够显式")
    if language in {"typescript", "tsx", "javascript", "jsx"} and any(
        token in text for token in ["@ts-ignore", "@ts-expect-error", ": any", "<any>"]
    ):
        risks.append("存在类型兜底或忽略")
    if any(token in text for token in ["fetch(", "axios.", "requests.", "smtplib", "nodemailer", "smtp"]):
        risks.append("直接访问外部网络或邮件服务")
    if category == "source" and line_count >= 220 and not _has_direct_test(relpath, test_lookup):
        risks.append("没有看到明显的直接测试邻居")
    return list(dict.fromkeys(risks))[:4]


def _has_direct_test(relpath: str, test_lookup: set[str]) -> bool:
    stem = Path(relpath).stem.lower()
    parent = Path(relpath).parent.name.lower()
    candidates = {stem, parent}
    return any(any(token and token in item for token in candidates) for item in test_lookup)


def _build_test_lookup(known_relpaths: set[str]) -> set[str]:
    return {Path(relpath).stem.lower() for relpath in known_relpaths if "test" in Path(relpath).parts or ".test." in relpath or ".spec." in relpath}


def _score_note(note: FileNote) -> tuple[int, list[str]]:
    score = 5
    reasons: list[str] = []
    if note.is_entrypoint:
        score += 40
        reasons.append("运行入口")
    if note.mentioned_by_trace:
        score += min(note.mentioned_by_trace, 4) * 15
        reasons.append(f"轨迹提到 {note.mentioned_by_trace} 次")
    if note.touched_by_git:
        score += min(note.touched_by_git, 4) * 10
        reasons.append("最近提交改过")
    if note.category == "config":
        score += 18
        reasons.append("决定项目边界或运行方式")
    if note.category == "test":
        score += 8
    if note.line_count >= 220:
        score += 8
        reasons.append("文件体量较大")
    if note.risks:
        score += len(note.risks) * 4
        reasons.append("内含风险点")
    return score, reasons[:4]


def _build_behavior(note: FileNote) -> str:
    if note.category == "doc":
        return "解释项目目标、用法和协作边界。"
    if note.category == "config":
        return f"定义 `{Path(note.relpath).name}` 的构建或运行参数。"
    if note.category == "test":
        target = Path(note.relpath).stem.replace(".test", "").replace(".spec", "")
        return f"校验 `{target}` 相关行为，防止回归。"
    if note.category == "script":
        return f"执行 `{Path(note.relpath).stem}` 自动化流程。"

    sentence = note.role_hint
    if note.symbols:
        sentence += f"，主要符号有 {', '.join(note.symbols[:3])}"
    elif note.imports:
        neighbors = ", ".join(Path(item).name for item in note.imports[:3])
        sentence += f"，会串起 {neighbors}"
    sentence += "。"
    return sentence


def _build_mermaid_edges(notes: list[FileNote], top_relpaths: set[str]) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for note in notes:
        if note.relpath not in top_relpaths:
            continue
        for imported in note.imports:
            if imported in top_relpaths:
                edges.append((note.relpath, imported))
    if edges:
        return list(dict.fromkeys(edges))
    top_files = [note.relpath for note in notes[:6]]
    return [("project", relpath) for relpath in top_files]


def _summarize_directories(notes: list[FileNote]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for note in notes:
        parts = Path(note.relpath).parts
        key = parts[0] if parts else "."
        counter[key] += 1
    return counter.most_common(12)
