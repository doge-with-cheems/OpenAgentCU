# OpenAgentCU 2.2.0

2.2.0：新增**中间层操作链**。模型先写 6–12 步操作链，OpenCU 整链校验后批量执行；
每条链绑定一个虚拟指针（1–4），各指针的坐标、目标窗口和链状态互相独立。
虚拟指针边界不变：不移动系统光标、不注入全局键鼠。

## 2.2.0 变更

- 新增 `oacu/chain.py`：操作链解析、整链预检、顺序执行、紧凑结果
- 新增 MCP 工具 `chain_run`；新增 CLI `oacu chain run`
- 支持 7 种步骤：`move/click/drag/scroll/key/type/wait`
- 建议 6–12 步，最多 32 步；超出建议范围只提示，不阻断
- 整链预检：未知字段/操作、坐标、按键系统组合键、目标窗口前置条件一次校验，
  失败时 `executed=0`，不会产生部分副作用
- `key`/`type` 要求链内先有 `click`/`drag`，避免把按键发到上次会话缓存的窗口
- `scroll` 使用 `direction`，消除 dy 正负方向歧义；`type.replace=false` 可追加
- 默认 `stop_on_error=true`；`dry_run` 只返回计划/预计耗时，不创建虚拟指针
- 执行期间按 **Esc** 在下一步边界取消本次 OpenCU 任务（操作链、`computer_act`/`act`）；可用 `cancel_on_esc=false` / `--no-esc-cancel` 关闭
- 取消结果带 `stop_conversation:true`；OpenCode `session.interrupt` 默认 Esc，可同时结束当前对话
- Esc 取消覆盖操作链、`computer_act`/`act` 与 IR 执行，CLI 取消时退出码 130
- 每指针独立锁；链级超时（默认 30s）；返回 `results/state/resume_from/partial`
- `chain_id` 120 秒幂等，避免客户端超时重发导致重复点击
- 定向消息投递失败（`delivered=false`）计为步骤失败，不再“假成功”
- 更新全局 `opencu` 技能，加入操作链写法与限制

## 2.1.0

- 虚拟指针改为 Minecraft 风格白色十字准星，保留 36×36 与点击穿透
- 游标窗口与字号减半：从 72×72 缩至 36×36（2.2.0 起改为十字准星）
- 最多 4 个独立虚拟指针，默认 1 号；其余按需创建
- MCP 鼠标/键盘/输入工具新增可选 `pointer` 参数（1–4，默认 1）
- CLI `input move/click/drag/scroll/key/type/pos` 新增 `--pointer` 参数

## 下载

- `OpenAgentCU-2.2.0-Setup.exe`：Windows 安装版（Program Files，需管理员确认 UAC）
- `OpenAgentCU-2.2.0-portable.zip`：便携版，解压即用
- `OpenAgentCU-2.2.0-source.zip`：完整源代码

安装包未做代码签名，SmartScreen 可能提示“未知发布者”。

## 亮点
- 基于 Windows UI Automation 的桌面感知与元素 token 化
- MCP stdio 服务（19 个工具），可被 Chatbox/Claude 等客户端调用
- **操作链**：模型先写 6–12 步，OpenCU 整链校验后批量执行，结果按步返回
- **虚拟指针**：不移动系统光标、不注入全局键鼠；UIA pattern + 定向窗口消息
- 虚拟鼠标：移动/点击/双击/右键/拖拽/滚轮，附带十字准星虚拟游标
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
- 自然语言规划器是规则匹配，不调用 LLM；复杂指令建议使用操作链或原子键鼠工具组合。
- 操作链在 MCP 中同步执行；不同指针的链状态独立，但当前传输层一次只处理一条链。
- 操作链执行期间的 Esc 取消是全局观察；在任意应用按 Esc 都会取消当前 OpenCU 任务，可用
  `cancel_on_esc=false` / `--no-esc-cancel` 关闭。

## 验证

- 166 个单元测试
- CLI 冒烟 10/10
- 端到端 12/12
- MCP 协议 4/4
- GUI 自检 5/5
