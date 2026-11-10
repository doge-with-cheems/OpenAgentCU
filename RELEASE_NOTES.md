# OpenAgentCU 2.1.0

2.1.0：虚拟游标 **面积缩小 50%**（36×36），并支持 **最多 4 个独立虚拟指针**；
默认仍只使用 1 个。虚拟指针与定向 UIA/窗口消息的边界保持不变：不移动系统光标、
不注入全局键鼠。

## 2.1.0 变更

- `▣` 游标窗口与字号减半：从 72×72 缩至 36×36
- 最多 4 个独立虚拟指针，默认 1 号；其余按需创建
- 每个指针独立保存坐标、目标窗口和显示期限，互不影响
- MCP 鼠标/键盘/输入工具新增可选 `pointer` 参数（1–4，默认 1）
- CLI `input move/click/drag/scroll/key/type/pos` 新增 `--pointer` 参数
- 2–4 号指针首次使用时从虚拟屏幕中心开始，避免与用户物理光标重叠
- 状态文件升级为多指针格式，兼容读取 2.0.x 的单指针 `pointer.json`
- overlay 进程按需创建窗口，支持 `{"id": n, "hide": true}` 隐藏单个游标

## 2.0.1

- 新增 `▣` 虚拟游标，由独立 `oacu overlay` 进程渲染
- 游标窗口 `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`，点击穿透
- 环境变量 `OACU_NO_OVERLAY=1` 可关闭游标

## 下载

- `OpenAgentCU-2.1.0-Setup.exe`：Windows 安装版（Program Files，需管理员确认 UAC）
- `OpenAgentCU-2.1.0-portable.zip`：便携版，解压即用
- `OpenAgentCU-2.1.0-source.zip`：完整源代码

安装包未做代码签名，SmartScreen 可能提示“未知发布者”。

## 亮点
- 基于 Windows UI Automation 的桌面感知与元素 token 化
- MCP stdio 服务（18 个工具），可被 Chatbox/Claude 等客户端调用
- **虚拟指针**：不移动系统光标、不注入全局键鼠；UIA pattern + 定向窗口消息
- 虚拟鼠标：移动/点击/双击/右键/拖拽/滚轮，附带 `▣` 虚拟游标
- 最多 4 个独立虚拟游标（默认 1 个），每个可独立定位和计时
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

- 145 个单元测试
- CLI 冒烟 9/9
- 端到端 12/12
- MCP 协议 4/4
- GUI 自检 5/5
