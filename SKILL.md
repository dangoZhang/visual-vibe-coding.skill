---
name: visual-vibe-coding
description: Read Codex and Claude Code traces, inspect Git and source files, then explain the code logic, structure, behavior, and risks of a vibe-coded project with visual maps and memory.
---

# VisualVibeCoding.skill

## 这是什么

这是一个专门给「不想自己通读 AI 写的仓库」的人用的 skill。

它不是只列目录，也不是只读 README。

它会把四类证据拼起来：

1. `.codex` / `.claude` 轨迹：看用户到底让 Agent 做过什么，哪些文件被反复点名。
2. Git：看最近改了什么，当前工作树脏在哪里。
3. 代码文件：按优先级逐个读取，给出行为、结构、依赖和风险。
4. 本地记忆：记住上次的重点文件和风险，下一轮直接对照变化。

## 适用场景

当用户在说这些话时，就该用这个 skill：

- “帮我快速看懂这个 AI 写的项目。”
- “我不想一行行看代码，你先把结构和逻辑梳理出来。”
- “把这个仓库的功能、风险、主链路画出来。”
- “结合 Codex / Claude Code 轨迹，告诉我这个项目到底在干嘛。”
- “看下最近改动后，项目重点和风险变了没有。”

## 工作流

1. 先跑 CLI 生成项目报告。
2. 再根据报告的阅读顺序，打开前 5 到 15 个重点文件做人工校验。
3. 输出时必须覆盖：
   - 项目是干什么的
   - 主结构和主链路
   - 关键文件为什么重要
   - 主要行为和潜在风险
   - 轨迹和 Git 对这个判断的影响
   - 相比上次分析发生了什么变化

## 先跑什么

默认命令：

```bash
~/.agents/skills/visual-vibe-coding/bin/visual-vibe-coding inspect \
  --project . \
  --memory \
  --output .visual-vibe-coding-output/latest-report.md \
  --json-output .visual-vibe-coding-output/latest-report.json
```

如果只想看轨迹匹配情况：

```bash
~/.agents/skills/visual-vibe-coding/bin/visual-vibe-coding scan-traces --project .
```

如果你正在这个仓库本身里开发，也可以直接用本地命令：

```bash
python3 -m visual_vibe_coding_skill.cli inspect --project .
```

## 回答规则

- 先讲人话版总览，再讲结构图和重点文件。
- 不要只抄 CLI 结果。高优先级文件要补直接读文件后的确认。
- 不要声称“全部无风险”。要指出真正会影响维护、上线、排障的地方。
- 如果轨迹和代码矛盾，优先相信代码和 Git，再说明轨迹为什么可能过时。
- 如果仓库很大，优先把 `entrypoint -> orchestration -> storage/provider -> tests` 这条链路讲清楚。

## 安装

### Codex

```bash
npx skills add https://github.com/dangoZhang/visual-vibe-coding.skill -a codex
```

### Claude Code

```bash
npx skills add https://github.com/dangoZhang/visual-vibe-coding.skill -a claude-code
```
