# 阶段 2：2.0.0 虚拟输入边界

> 提交 `e18f50a` ｜ 2026-11-08 ｜ 版本 2.0.0

## 阶段目标

1.0.0 的解释器通过 `SetCursorPos`、`mouse_event`、`keybd_event`、`SendInput` 注入
物理键鼠，会移动用户光标并抢占真实输入焦点。本阶段的目标是建立“不接管用户键鼠”的
硬边界：

- 新增虚拟指针：坐标和点击由 OpenCU 自己维护，物理光标不动；
- 点击优先使用 UIA pattern（Invoke / SelectionItem / ExpandCollapse / Toggle /
  LegacyIAccessible），失败时回退到定向 `WM_*` 窗口消息；
- 输入文字优先走 UIA ValuePattern，失败时回退到定向 `WM_CHAR`；
- 键盘组合键只发给目标窗口，Win、Alt+Tab、Alt+F4、Ctrl+Shift+Esc 直接拒绝；
- 用 `win_run` / ShellExecute 替代 Win+R，不再弹运行框。

## 工程任务

1. 新增 `oacu/virtual.py`：屏幕范围与坐标校验、`WindowFromPoint`/`ScreenToClient`、
   `PostMessageW` 封装、虚拟指针状态（x/y/hwnd）持久化、UIA pattern 优先、
   `key_press/key_down/key_up/key_hold`、`type_text` 三级回退、`win_run`。
2. 重写 `oacu/input.py`：从 225 行物理输入封装缩减为 44 行，统一转发到
   `virtual.py`，保留 `normalize_keys` 和错误类型别名。
3. 改造 `oacu/interpreter.py`：删除 `SendInput`/`mouse_event`/`keybd_event` 结构，
   `_mouse/_send_keys/_send_text` 转发到虚拟输入；点击先试 UIA pattern，再回退虚拟鼠标。
4. 扩展 `tools/uia_act.ps1`：新增 `focus_point`、`set_value_point`、
   `focused_set_value`，以及完整的 Invoke → SelectionItem → ExpandCollapse →
   Toggle → LegacyIAccessible 点击回退链。
5. 更新 MCP 工具描述与 GUI 授权文案，明确“虚拟指针、不移动系统光标”的语义。
6. 更新 README、发布说明、token 基准与打包版本号；`flow_check.py` 的 pattern 后端
   改为返回失败，以覆盖虚拟鼠标回退路径。

## 文件改动

| 文件 | 增/删 | 改动 |
| --- | --- | --- |
| `oacu/virtual.py` | +636 | 新增虚拟指针、定向消息、UIA pattern 与按键/文本回退 |
| `oacu/input.py` | +44 / −225 | 重写为虚拟输入薄封装 |
| `oacu/interpreter.py` | +32 / −85 | 移除物理注入，改用虚拟后端 |
| `tools/uia_act.ps1` | +109 | 新增焦点、ValuePattern 与点击回退动作 |
| `README.md` | +102 / −38 | 虚拟模式、边界、动作与 MCP 说明 |
| `RELEASE_NOTES.md` | +18 / −5 | 2.0.0 变更与包名 |
| `oacu/mcp/protocol.py` | +8 / −8 | 8 条工具描述改为虚拟语义 |
| `oacu/gui.py` | +4 / −4 | 输入授权文案 |
| `docs/token-benchmark.md` | +4 / −4 | 版本标注 |
| `packaging/version_info.txt` | +4 / −4 | 2.0.0.0 |
| `packaging/build.ps1` | +3 / −3 | 包名 |
| `packaging/README-install.txt` | +3 / −3 | 安装说明 |
| `oacu/cli.py` | +2 / −2 | 版本与帮助 |
| `tests/test_interpreter.py` | +2 / −2 | 适配虚拟后端 |
| `packaging/installer.iss` | +1 / −1 | `MyAppVersion` |
| `pyproject.toml` | +1 / −1 | 2.0.0 |
| `oacu/__init__.py` | +1 / −1 | 2.0.0 |
| `tools/flow_check.py` | +1 / −1 | pattern 回退路径 |
| `packaging/OpenAgentCU.ico` | 0 | 图标资源替换 |

## 验证

该提交的 `RELEASE_NOTES.md` 记录：

- 138 个单元测试
- CLI 冒烟 9/9
- 端到端 12/12
- MCP 协议 4/4
- GUI 自检 5/5

另外确认：虚拟移动前后物理光标坐标不变；Win+R 被拒绝；ShellExecute 启动正常；
UIA 点击 pattern 失败时可回退到定向窗口消息。

## 提交

`e18f50a`

```text
OpenAgentCU 2.0.0: virtual pointer, no physical keyboard/mouse injection
```

## 遗留问题

- 部分 Chromium / UWP / 游戏窗口忽略合成 `WM_*` 消息；工具返回成功不代表目标应用
  真正接受输入，需要重新扫描或截图验证。
- `type_text` 的 UIA SetValue 可能替换控件原内容；WM_CHAR 回退在部分应用中不可用。
- 系统级快捷键（Win、Win+R、Alt+Tab、Alt+F4、Ctrl+Shift+Esc）被硬拒绝，这是
  “不接管键鼠”的边界，不是可配置项。
- 不再提供物理输入回退；确需真实键鼠注入时必须修改源码。
- 每个进程各自维护虚拟指针状态，多进程/多客户端同时操作时没有统一仲裁。
