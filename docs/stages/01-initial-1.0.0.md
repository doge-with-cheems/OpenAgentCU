# 阶段 1：1.0.0 首个公开版本

> 提交 `59fb476` ｜ 2026-11-06 ｜ 版本 1.0.0

## 阶段目标

建立 OpenAgentCU 的完整基础链路：采集 Windows 桌面 UIA 元素树，压缩成模型可读的
紧凑 token 表；把自然语言指令规划成带时序的 IR；由本地解释器按序操作控件；再通过
MCP、CLI 和 GUI 对外提供。该阶段重点是把“感知—规划—执行—审计”串成可运行闭环，
而不是虚拟输入或游标显示。

## 工程任务

1. 感知层：PowerShell 5.1 调用 `System.Windows.Automation` 采集原始元素，经过
   去噪、阅读顺序排序、字段归一化后生成 `RawElement / Element / Token / Snapshot`。
2. 存储层：SQLite 保存 `snapshots / tokens / actions`，快照默认 30 秒过期，
   运行记录用于 GUI 审计页。
3. 执行层：规则规划器把中英文动词和目标名称匹配到 token；IR v1 编译为带
   `at` 时序的步骤；解释器按序执行点击、输入、按键、滚动、等待等动作。
4. MCP：stdio JSON-RPC 2.0 服务，提供 18 个工具；元素表放在 `content.text`，
   默认 80 行，支持 find/tokens/summary/diff 等省 token 查询。
5. CLI/GUI：`scan/dump/plan/act/exec/serve/mcp/doctor/gui/input` 命令；
   tkinter 五页签外壳，输入类按钮默认需要显式授权。
6. 打包与验收：PyInstaller + Inno Setup，提供安装版、便携版；配套
   `smoke_cli.py`、`flow_check.py`、`mcp_probe.py`、`gui_probe.py` 和 138 个单元测试。

## 文件改动

首个提交共新增 66 个文件，按模块分组如下：

| 模块组 | 文件数 | 新增行 | 主要内容 |
| --- | ---: | ---: | --- |
| 感知（`oacu/uia/`、`models`、`pipeline`、`tokens`） | 8 | 714 | UIA 采集、去噪、排序、token 渲染 |
| 存储（`store`、`context`） | 2 | 343 | SQLite 三表、快照上下文与过期重扫 |
| 执行链（`planner/ir/transport/interpreter/agent/keys/input/config/errors`） | 9 | 2001 | 规则规划、IR、本地 TCP 解释器、审计 |
| MCP（`protocol/server/compact/__init__`） | 4 | 744 | 18 个工具、紧凑 token 表、stdio 服务 |
| CLI/GUI/入口 | 4 | 1725 | 命令行、五页签图形外壳、模块入口 |
| 打包 | 11 | 758 | PyInstaller spec、Inno Setup、图标、构建脚本 |
| 工具与夹具 | 8 | 682 | UIA dump/act、四个验收探针、桌面 fixture |
| 测试 | 13 | 1554 | 感知、规划、IR、解释器、MCP、GUI 等 |
| 文档 | 4 | 798 | README、发布说明、token 基准、逻辑图 |
| 工程配置 | 2 | 29 | `.gitignore`、`pyproject.toml` |

该版本的输入实现仍使用物理键鼠注入路径（`SetCursorPos`、`mouse_event`、
`SendInput` 等），这是 2.0.0 要替换的核心问题。

## 验证

该提交的 `RELEASE_NOTES.md` 记录：

- 138 个单元测试
- CLI 冒烟 9/9
- 端到端 12/12
- MCP 协议 4/4
- GUI 自检 5/5

## 提交

`59fb476`

```text
OpenAgentCU 1.0.0: first public release
```

## 遗留问题

- 输入依赖物理键鼠注入，会移动用户光标、抢占键盘焦点，无法在用户同时使用电脑时安全运行。
- 自然语言规划器是规则匹配，不调用 LLM；复杂指令容易匹配失败，需要拆成原子操作。
- UIA 对 Electron、游戏、视频播放器等自绘界面的控件覆盖有限，快照可能缺少目标。
- 快照默认 30 秒过期，窗口变化后旧 token 与坐标会失效，需要重新扫描。
- 元素表与工具描述仍包含较多上下文，长任务下 token 成本随历史累积快速上升。
