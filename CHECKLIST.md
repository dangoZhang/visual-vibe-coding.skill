# Requirement Checklist

## 原始要求逐条核对

### 1. 先拉取 `https://github.com/dangoZhang/vibecoding.skill`

- 已做。
- 参考仓库用于抽取工作流和边界，最终项目没有保留其多余子系统。

### 2. 在他的基础上，删除多余的代码和功能

- 已做。
- 新项目删除了等级评估、分享卡、二级 skill 导出、术语刷新、营销画像链路。
- 保留并强化的只有：轨迹、Git、代码结构、风险、记忆、可视化。

### 3. 做一个新的 skill 项目

- 已做。
- 新仓库：`visual-vibe-coding.skill`
- GitHub: <https://github.com/dangoZhang/visual-vibe-coding.skill>

### 4. 能在 Codex 或 Claude Code 等 VibeCoding 项目中，通过读取 `.codex` 等轨迹梳理代码逻辑

- 已做。
- 支持读取 `~/.codex/sessions`、`~/.codex/archived_sessions`、`~/.claude/projects`。
- 已补 `--trace-alias`，项目移动路径后仍可命中旧轨迹。

### 5. 可视化给出项目代码的结构、功能

- 已做。
- 输出目录结构摘要和 Mermaid 结构图。
- 输出重点文件阅读顺序和逐文件行为说明。

### 6. 让 Agent 逐个文件代码读取一遍

- 已做。
- CLI 会遍历并读取候选文本/代码文件内容，再生成 `file_notes`。
- 当前实现默认跳过明显生成物、二进制、锁文件和临时目录，避免噪音淹没主逻辑。

### 7. 像人类程序员一样给出“代码在做什么、有什么风险”

- 已做。
- 每个文件会输出：
  - 角色判断
  - 关键符号
  - 依赖关系
  - 风险提示
- 全局还会汇总 `key_risks`。

### 8. 优势在于会读轨迹、会看 Git、会记忆供下次参考、会给出重点、会可视化结构

- 已做。
- 轨迹：`traces.py`
- Git：`git_tools.py`
- 记忆：`memory.py`
- 重点排序：`project_scan.py` + `inspector.py`
- 可视化：`render.py`

### 9. 写好后逐个检查要求是否做到

- 已做。
- 本文件就是逐条验收记录。

### 10. 在本机 Codex 中安装实践

- 已做。
- 安装路径：`~/.agents/skills/visual-vibe-coding`
- 可执行 wrapper：`~/.agents/skills/visual-vibe-coding/bin/visual-vibe-coding`

### 11. 能否迅速了解 `my-project` 中的项目

- 已验证。
- 已对 `mailclaw`、`CyberDate`、`metaAgent` 做实测。
- 这些项目都能快速产出：
  - 项目用途判断
  - 重点文件顺序
  - 结构图
  - 风险列表
  - 轨迹与 Git 线索
  - 主逻辑链

补充：

- `mailclaw`：验证多 agent 邮件系统和旧路径 Claude 轨迹 alias。
- `CyberDate`：验证 Next.js / API / UI / provider 混合项目。
- `metaAgent`：验证多目录 monorepo，成功抽出 `入口 -> 核心 -> 验证` 主逻辑链。

### 12. 压力测试可以使用 `mailclaw`

- 已做。
- `mailclaw` 报告已经生成过多次，安装态和开发态都已验证。

### 13. 最后上传到 GitHub，创建一个 public 仓库，写富有感染力的海报式 Readme

- 已做。
- 公共仓库：<https://github.com/dangoZhang/visual-vibe-coding.skill>
- README 已包含 hero 海报图和面向用户的项目叙事。

## 额外补强

- 路径不存在时，会友好报错，不再抛 Python 栈。
- 仓库移动后可用 `--trace-alias /old/path` 继续匹配旧轨迹。
- 阅读顺序不再把测试文件误判成入口，也不再把 `pnpm-lock.yaml` 这种锁文件排进重点阅读链路。
