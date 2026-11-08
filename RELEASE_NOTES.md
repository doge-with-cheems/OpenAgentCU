# OpenAgentCU 2.0.0

2.0.0：默认改为虚拟指针与定向 UIA/窗口消息，不移动系统光标、不注入全局键鼠。

## 下载

- `OpenAgentCU-2.0.0-Setup.exe`：Windows 安装版（Program Files，需管理员确认 UAC）
- `OpenAgentCU-2.0.0-portable.zip`：便携版，解压即用
- `OpenAgentCU-2.0.0-source.zip`：完整源代码

安装包未做代码签名，SmartScreen 可能提示“未知发布者”。

## 亮点
- 基于 Windows UI Automation 的桌面感知与元素 token 化
- MCP stdio 服务（18 个工具），可被 Chatbox/Claude 等客户端调用
- **虚拟指针**：不移动系统光标、不注入全局键鼠；UIA pattern + 定向窗口消息
- 虚拟鼠标：移动/点击/双击/右键/拖拽/滚轮，附带可见的点击环
- 键盘：UIA ValuePattern / 定向 WM_CHAR / WM_KEYDOWN；应用级组合键
- 系统键（Win/Alt+Tab/Alt+F4/Ctrl+Shift+Esc）明确拒绝，避免接管用户输入
- 虚拟 Win+R 替代：`win_run` / `oacu input winrun`（ShellExecute 启动应用/路径/URL）
- 零扫描动作：`launch_app`、`open_url`、`search_web`、`win_run`
- tkinter GUI：快照 / 指令 / 记录 / MCP / 输入控制
- MCP token 优化：紧凑表、过滤无名容器、默认 80 行、find/diff/分页

## Token 基准

- 典型 13 次工具调用任务：**平均约 45k token/任务**（38k–50k）
- 简单任务约 20k–30k；复杂任务约 60k–80k
- 旧版 Epstein 75 次调用任务约 1M token
- 单次 `desktop_scan` ≈720 token；`desktop_find` ≈31 token


## 环境

- Windows 10/11 x64
- PowerShell 5.1（系统自带）
- 安装版不需要单独安装 Python；源码运行需要 Python 3.10+

## 已知限制
- `Ctrl+Alt+Delete` 属于 Windows 安全注意序列，普通程序无法模拟。
- UIA 对部分应用（如某些 Electron/游戏/视频播放器）暴露的控件有限；播放/暂停状态可能无法读取。
- 自然语言规划器是规则匹配，不调用 LLM；复杂指令建议使用原子键鼠工具组合。

## 验证

- 138 个单元测试
- CLI 冒烟 9/9
- 端到端 12/12
- MCP 协议 4/4
- GUI 自检 5/5
