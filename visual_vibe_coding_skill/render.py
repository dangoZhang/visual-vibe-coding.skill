from __future__ import annotations

from pathlib import Path


def render_markdown(payload: dict) -> str:
    lines: list[str] = []
    lines.append(f"# {payload['project_name']} · Visual Vibe Coding Report")
    lines.append("")
    lines.append(f"> 读取了 {payload['files_scanned']} 个文本/代码文件，跳过 {payload['files_skipped']} 个生成物或二进制文件。")
    lines.append("")
    lines.append("## 快速判断")
    lines.append("")
    lines.append(f"- 项目根目录：`{payload['project_root']}`")
    lines.append(f"- 我对项目用途的判断：{payload['purpose']}")
    if payload["entrypoints"]:
        lines.append(f"- 高概率入口：{', '.join(f'`{item}`' for item in payload['entrypoints'][:6])}")
    git_info = payload["git"]
    if git_info["branch"]:
        head_short = (git_info["head"] or "")[:8]
        lines.append(f"- Git 状态：分支 `{git_info['branch']}`，HEAD `{head_short}`，脏文件 {len(git_info['dirty_files'])} 个")
    lines.append(f"- 轨迹概览：{payload['trace']['summary']}")
    lines.append(f"- 记忆回放：{payload['memory']['summary']}")
    lines.append("")
    lines.append("## 建议阅读顺序")
    lines.append("")
    for index, item in enumerate(payload["reading_order"], start=1):
        reason = "，".join(item["reasons"]) if item["reasons"] else "基础骨架文件"
        lines.append(f"{index}. `{item['path']}`: {item['role_hint']}。优先原因：{reason}。")
    lines.append("")
    if payload["logic_chain"]:
        lines.append("## 主逻辑链")
        lines.append("")
        for item in payload["logic_chain"]:
            lines.append(f"- {item['stage']}：`{item['path']}` · {item['role_hint']} · {item['why']}")
        lines.append("")
    lines.append("## 结构图")
    lines.append("")
    lines.append("```text")
    for item in payload["directory_summary"]:
        lines.append(item)
    lines.append("```")
    lines.append("")
    lines.append("```mermaid")
    lines.extend(payload["mermaid"].splitlines())
    lines.append("```")
    lines.append("")
    lines.append("## 轨迹线索")
    lines.append("")
    for session in payload["trace"]["sessions"]:
        top_prompt = session["top_prompt"] or "没有抽到有效的用户任务"
        lines.append(f"- `{session['source']}` · `{session['timestamp']}` · {top_prompt}")
    if payload["trace"]["hot_files"]:
        hot_files = ", ".join(f"`{item['path']}` x{item['count']}" for item in payload["trace"]["hot_files"])
        lines.append(f"- 轨迹高频文件：{hot_files}")
    if payload["trace"]["recent_tasks"]:
        lines.append(f"- 近期任务主题：{' | '.join(payload['trace']['recent_tasks'])}")
    lines.append("")
    lines.append("## Git 线索")
    lines.append("")
    for commit in payload["git"]["recent_commits"]:
        lines.append(f"- `{commit['short_sha']}` {commit['authored_at']} {commit['subject']}")
    if payload["git"]["dirty_files"]:
        dirty_preview = ", ".join(f"`{item}`" for item in payload["git"]["dirty_files"][:10])
        lines.append(f"- 当前未提交修改：{dirty_preview}")
    lines.append("")
    lines.append("## 关键风险")
    lines.append("")
    if payload["key_risks"]:
        for risk in payload["key_risks"]:
            lines.append(f"- `{risk['path']}`: {risk['message']}")
    else:
        lines.append("- 暂时没有扫到特别突出的结构性风险。")
    lines.append("")
    lines.append("## 逐文件速览")
    lines.append("")
    for note in payload["file_notes"]:
        risk_text = f" 风险：{'；'.join(note['risks'])}。" if note["risks"] else ""
        import_text = ""
        if note["imports"]:
            neighbors = ", ".join(f"`{item}`" for item in note["imports"][:3])
            import_text = f" 关联：{neighbors}。"
        lines.append(f"- `{note['relpath']}`: {note['behavior']}{import_text}{risk_text}")
    return "\n".join(lines).strip() + "\n"


def render_mermaid(edges: list[tuple[str, str]]) -> str:
    labels = sorted({label for edge in edges for label in edge})
    node_ids = {label: f"n{index}" for index, label in enumerate(labels)}
    lines = ["flowchart LR"]
    for label in labels:
        safe = _escape_mermaid_label(label)
        lines.append(f'    {node_ids[label]}["{safe}"]')
    for left, right in edges:
        lines.append(f"    {node_ids[left]} --> {node_ids[right]}")
    return "\n".join(lines)


def build_key_risks(file_notes: list[dict]) -> list[dict]:
    risks: list[dict] = []
    for note in file_notes:
        for item in note["risks"]:
            risks.append({"path": note["relpath"], "message": item, "priority": note["priority"]})
    risks.sort(key=lambda item: (-item["priority"], item["path"], item["message"]))
    return risks[:10]


def _escape_mermaid_label(label: str) -> str:
    return label.replace('"', "'")
