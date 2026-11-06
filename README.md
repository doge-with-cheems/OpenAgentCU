# OpenAgentCU

Windows 桌面感知 + UIA 操作桥。把当前桌面控件树整理成
`{[组件名][组件类型][坐标][关联]}` token 快照，再把自然语言指令编译成带时序的
IR，交给本地解释器按序操作 UI Automation 元素；同时提供鼠标、键盘、组合键和
Win+R 的直接控制。

零第三方 Python 依赖：UIA 通过 PowerShell 5.1 的
`System.Windows.Automation` 访问，存储用标准库 `sqlite3`，通信用 `socket`。
**首个公开发布即 1.0.0 最终版。**

## 下载

- [Windows 安装包（Setup.exe）](https://github.com/doge-with-cheems/OpenAgentCU/releases/latest)
- [便携版 ZIP](https://github.com/doge-with-cheems/OpenAgentCU/releases/latest)
- [源代码 ZIP](https://github.com/doge-with-cheems/OpenAgentCU/releases/latest)

> 安装包未签名，Windows SmartScreen 可能提示“未知发布者”；介意时使用便携版。
> 支持 Windows 10/11 x64，不需要单独安装 Python。

## 能力概览

- 桌面 UIA 采集 → 去噪 → 阅读顺序 → 紧凑 token 表
- MCP stdio 服务：`desktop_scan/tokens/find/summary`、`computer_act`
- 鼠标：移动、点击、双击、右键、拖拽、滚轮
- 键盘：文本输入、单键、组合键（`win+r`、`ctrl+shift+esc`、`alt+tab`…）、长按
- Win+R：`win_run` / `oacu input winrun <command>`
- 零扫描动作：`launch_app`、`open_url`、`search_web`、`win_run`
- GUI 五个页签：快照 / 指令 / 记录 / MCP / 输入控制
- 针对 MCP token 优化：元素表放 `content.text`、过滤无名容器、默认 80 行、find/diff/分页

## 环境

- Windows 10/11 x64
- Python 3.10+
- PowerShell 5.1（自带）

自检：

```powershell
python -m oacu doctor
```

## 图形界面

```powershell
python -m oacu gui
```

五个页签：**桌面快照**（采集 + token 列表 + 组件详情）、**指令执行**（计划 / IR /
预演 / 执行 / 日志）、**运行记录**（actions 审计）、**MCP / 设置**（环境状态、
MCP 配置一键复制）、**输入控制**（鼠标移动/点击/拖拽/滚轮、按键、文本输入）。
执行与键鼠按钮默认禁用，勾选对应授权后才可用。

`--tab 0..4` 可直接打开指定页；`--self-test` 用于无交互自检（打印 `gui 5/5`）。

## 快速开始

```powershell
cd E:\document\ai\working_file\opencu

# 0. 图形界面
python -m oacu gui

# 1. 抓桌面并落库
python -m oacu scan

# 2. 看当前组件 token
python -m oacu dump --limit 20

# 3. 只生成计划与 IR，不动鼠标键盘
python -m oacu plan "点击记事本"
python -m oacu plan "在文本编辑器输入你好然后按键回车"

# 4. 真正执行（进程内）
python -m oacu act "点击七" --inproc

# 5. 直接键鼠控制
python -m oacu input screen
python -m oacu input pos
python -m oacu input move --x 800 --y 500 --duration-ms 200
python -m oacu input click --x 800 --y 500 --button left
python -m oacu input drag --from-x 100 --from-y 100 --to-x 600 --to-y 400
python -m oacu input scroll --dy -3
python -m oacu input key --press "ctrl+s"
python -m oacu input key --hold shift --ms 800
python -m oacu input key --press "win+r"
python -m oacu input key --press "ctrl+shift+esc"
python -m oacu input type "hello"
python -m oacu input winrun notepad

# 6. 或者先起解释器守护进程，再远程执行
python -m oacu serve
python -m oacu exec %APPDATA%\OpenAgentCU\ir\<trace-id>.json
```

全局参数：`--json`、`--db`、`--backend {auto,ps,uia,fake}`、`--timeout`、`-v`。
退出码：`0` 成功、`1` 运行失败、`2` 用法错误、`3` 环境/数据不可用。

## MCP

```powershell
python -m oacu mcp serve
```

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "opencu": {
      "command": "python",
      "args": ["-m", "oacu", "mcp", "serve"],
      "cwd": "E:\\document\\ai\\working_file\\opencu"
    }
  }
}
```

工具：

| 工具 | 作用 |
| --- | --- |
| `desktop_scan` | 采集并返回**紧凑 token 表**；`diff=true` 只返回变化 |
| `desktop_tokens` | 分页读取 token 表（默认 20 条，无重复全文） |
| `desktop_find` | 按名称只查匹配元素（比全量扫描省 token） |
| `desktop_summary` | 只返回窗口/数量摘要 |
| `launch_app` | 按名称启动应用（零扫描） |
| `open_url` | 打开 URL（零扫描） |
| `search_web` | 打开 Google/Bing/YouTube 搜索结果（零扫描） |
| `win_run` | Win+R → 输入命令 → 回车（零扫描） |
| `computer_act` | 单轮：计划 → IR → 执行（默认只回状态，`verbose=true` 才回计划/IR） |
| `mouse_move` | 鼠标移动到绝对坐标 |
| `mouse_click` | 左/右/中键单击、多次点击 |
| `mouse_drag` | 按住拖拽到目标坐标 |
| `mouse_scroll` | 垂直/水平滚轮 |
| `key_press` | 按键/组合键（win、ctrl+s、enter…） |
| `key_hold` | 按住指定时长 |
| `type_text` | 向当前焦点输入 Unicode 文本 |
| `screen_info` | 虚拟屏幕范围与主屏分辨率 |
| `mouse_position` | 当前鼠标坐标 |

## 支持的动作

| 指令示例 | 动作 |
| --- | --- |
| `打开 chrome` / `启动 记事本` | 启动应用（ShellExecute，内置常见应用别名） |
| `打开 youtube` / `打开 https://...` | 打开网址 |
| `搜索 爱泼斯坦 资料` | 打开 Google 搜索结果 |
| `点击「开始」` / `双击 七` / `右键 桌面` | UIA token 点击 |
| `在文本编辑器输入你好` | ValuePattern 写入；不支持时点击后 SendInput 输入 |
| `输入 chrome` | 向当前焦点输入文本（SendInput Unicode） |
| `按键 win` / `按 win+r` / `按 ctrl+shift+esc` | 特殊键与组合键（WinR 等同 win+r） |
| `oacu input winrun notepad` / `win_run` | Win+R → 输入命令 → 回车 |
| `向下滚动 3 次` | 滚动 |
| `等待 2 秒` | 等待 |
| `激活 计算器` | 前置窗口 |

## 组合键

统一解析以下写法（CLI / MCP / `computer_act` 通用）：

```text
win+r     Win+R
winr      等同 win+r
ctrl+shift+esc
alt+tab
alt+f4
ctrl+l
^s        pywinauto 风格 = ctrl+s
%{F4}     alt+f4
+{TAB}    shift+tab
{ENTER}   回车
win       单独 Win 键
```

`oacu input winrun "notepad"` / MCP `win_run` 会完整执行 Win+R → 输入命令 → 回车。

## Token 用量设计

- `desktop_scan` 直接返回 **`content.text` 里的紧凑表**（Chatbox 只读这个字段），格式 `id|name|type|x|y|w|h|win`。
- 默认过滤无名 `Pane/Group/Custom` 容器，只回前 **80 行**；头部显示 `shown: 80/N`。
- 不再返回 `structuredContent`，避免与 `content.text` 双份。
- `desktop_tokens` 默认只回 20 条，支持 `offset`；不再返回全文 `text`。
- `desktop_find` 只返回匹配元素，适合“找搜索框/视频/按钮”这类操作。
- `desktop_scan` 支持 `diff=true`，只返回新增/删除。
- `launch_app` / `open_url` / `search_web` / `win_run` **完全不扫描桌面**。
- `computer_act` 默认只回 `{ok,status,steps,results}`；计划/IR 需要 `verbose=true`。

实测一个 363 token 的桌面（字符数按 ~3.5 字符/token 估算）：

| 调用 | 旧格式 | 新格式 | 降幅 |
| --- | --- | --- | --- |
| `desktop_scan` | ~26,059 tok | ~4,558 tok | **-82.5%** |
| `desktop_tokens` | ~48,718 tok | ~4,569 tok | **-90.6%** |
| `computer_act` | ~402 tok | ~91 tok | **-77.3%** |

日常操作优先用 `desktop_find`（只回匹配行）或 `desktop_scan(diff=true)`，不要反复拉全量快照。

### 为什么 75 次调用会烧掉 ~1M token

按你提供的日志统计：75 次工具调用，工具结果合计约 13 万字符，但**每一轮都会把之前所有结果重新发给模型**，累计约 630 万字符（≈180 万 token；按不同 tokenizer/缓存口径，账单显示 100 万很正常）。其中：

- `desktop_scan` 6 次，单次约 1.9 万字符（≈5.6k token）；
- `desktop_find` 34 次、按键 17 次、文本 8 次，都是因为 0.2.1 只把摘要放进 `content.text`，元素表在 `structuredContent`，Chatbox 没把它给模型，模型只能“盲操作”并反复试探；
- 每次调用都会把历史结果再算一遍，**调用次数比单次大小更致命**。

1.0.0 起：元素表直接放进模型可见的 `content.text`，不再返回 `structuredContent`；`desktop_scan` 默认只回前 80 行并过滤无名容器；新增 `launch_app/open_url/search_web/win_run` 零扫描工具；`win+r`、`ctrl+shift+esc`、`alt+tab` 等组合键统一解析。**换新会话执行任务**（不要把几十轮工具历史一直带着）同样关键。

### 平均任务消耗

按 1.0.0 的实测载荷与典型 13 次工具调用估算：

- **平均约 45k token/任务**（38k–50k）
- 简单任务约 20k–30k；复杂任务约 60k–80k
- 旧版同任务约 1M token
- 单次 `desktop_scan` ≈720 token，`desktop_find` ≈31 token

详见 [`docs/token-benchmark.md`](docs/token-benchmark.md)。实际账单还取决于客户端是否重发历史、是否计入思考 token 与缓存策略。

## 目录

```text
oacu/
  cli.py            命令行入口（scan/dump/plan/act/exec/serve/mcp/doctor/gui/input）
  gui.py            tkinter 图形外壳（快照 / 指令 / 记录 / MCP / 输入控制）
  input.py          鼠标移动/点击/拖拽/滚轮、按键、文本输入
  config.py         路径与默认值（%APPDATA%/OpenAgentCU）
  models.py         RawElement / Element / Token / Snapshot
  pipeline.py       capture → normalize → order → tokenize
  tokens.py         {[名称][类型][坐标][关联]} 渲染
  store.py          SQLite：snapshots / tokens / actions
  context.py        取最新快照，过期自动重扫
  planner.py        规则规划器（中英文动词 + 模糊匹配）
  ir.py             IR v1 编译、校验、落盘
  transport.py      JSON-lines over TCP 127.0.0.1:8765
  interpreter.py    按时序执行，鼠标/键盘/PS UIA pattern
  agent.py          单轮编排与 actions 审计
  uia/              PowerShell UIA 桥与采集
  mcp/              MCP JSON-RPC 2.0 stdio 服务
tools/
  uia_dump.ps1      桌面树采集（UTF-8 JSON）
  uia_act.ps1       Invoke/Value/Scroll/SetFocus
  smoke_cli.py      G2：cli 9/9
  flow_check.py     G3：e2e 12/12
  mcp_probe.py      G4：mcp 4/4
  gui_probe.py      图形外壳自检：gui 5/5
tests/              138 个单元测试（含 GUI 线程交互与输入校验）
```

## 验收

```powershell
python -m unittest discover -s tests -v     # G1
python tools\smoke_cli.py                   # G2 -> cli 9/9
python tools\flow_check.py                  # G3 -> e2e 12/12
python tools\mcp_probe.py                   # G4 -> mcp 4/4
python tools\gui_probe.py                   # GUI -> gui 5/5
```

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

产物：

| 文件 | 说明 |
| --- | --- |
| `dist\installer\OpenAgentCU-1.0.0-Setup.exe` | 安装版（Program Files，需管理员；带卸载） |
| `dist\OpenAgentCU-1.0.0-portable.zip` | 便携版（解压即用） |
| `dist\OpenAgentCU\` | 便携目录（`OpenAgentCU.exe` + `oacu.exe` + `_internal`） |

打包依赖：PyInstaller（MSYS2 `mingw-w64-ucrt-x86_64-pyinstaller`）与 Inno Setup 6。
安装包入口脚本在 `packaging\cli_entry.py` / `gui_entry.py`，spec 在
`packaging\OpenAgentCU.spec`，安装器脚本在 `packaging\installer.iss`。

安装版会把数据写到 `%APPDATA%\OpenAgentCU`；不可写时依次回退到
`%LOCALAPPDATA%`、`C:\Users\Public\OpenAgentCU`、`~\.opencu`、当前目录 `.opencu`。

## 已知边界

- 计划器是确定性的规则匹配，不调用 LLM；支持启动/打开/搜索、点击/双击/右键、输入/逐字输入、滚动、按键（含 Win/组合键）、等待、激活。
- 快照默认 30 秒过期；执行前元素失效会返回 `stale_token`，重新 `scan` 即可。
- token 不保存 COM 句柄，执行时按名称/automation_id/坐标重新定位元素。
- 只支持单轮指令，不做多步自主循环。
