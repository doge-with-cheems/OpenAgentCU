# 阶段 6：2.2.0 Esc 取消

> 提交 `01d816d` / `4ce483c` ｜ 2026-11-11 ｜ 版本 2.2.0

## 阶段目标

操作链可能执行数秒到数十秒。用户需要一种不依赖鼠标、不切换窗口的“立即停止”方式。
本阶段分两步完成：

1. 先让 Esc 取消正在执行的操作链；
2. 再把取消抽象为通用任务令牌，覆盖 `chain_run`、`computer_act`/`act` 和 IR `exec`，
   并向 agent 返回“结束当前对话”的明确信号。

取消是协作式的：Esc 不会强制杀死线程或中断正在进行的单步 UIA/窗口消息调用，而是在
该步骤返回后的下一步边界生效，避免留下未释放的鼠标按键或半完成的应用状态。

## 工程任务

1. 全局观察 Esc：使用 `GetAsyncKeyState(VK_ESCAPE)` 轮询，只观察、不拦截、不安装
   键盘钩子；Esc 仍会正常传给目标应用。
2. 取消令牌：`CancelToken` 包装 `threading.Event`，提供 `cancel/is_set/check/sleep`；
   `sleep` 分片等待，长等待也能在约 30ms 内响应取消。
3. 线程作用域：`TaskScope` 用线程局部变量绑定当前令牌，嵌套作用域复用外层令牌，
   保证 GUI/agent 任务与内部链共享同一个取消源。
4. 链执行：`run_chain` 在步前、等待中和 `TaskScope` 退出时检查令牌；取消返回
   `status=cancelled`、`cancelled=true`、`stop_conversation=true`、`resume_from`。
5. IR 解释器：在每步前、等待前后和步内插入 `cancel_check()`；捕获 `TaskCancelled`
   后追加 `code=cancelled` 的结果并停止后续步骤。
6. 执行入口：`agent.run_act`、`transport.default_handler`、CLI `exec` 都包一层
   `TaskScope`；`cmd_act`/`cmd_exec` 在取消时返回退出码 130。
7. 对话层：`computer_act` 的紧凑结果和 MCP 文本渲染带 `stop_conversation`；
   OpenCode 的 `session.interrupt` 显式绑定 Esc，客户端与 OpenCU 两层同时生效。
8. 文档与技能：README、发布说明、`docs/chain-design.md` 说明取消边界；全局
   `opencu` 技能加入最高优先级规则——看到取消信号立即停止本次对话。

## 文件改动

| 文件 | 类型 | 改动 |
| --- | --- | --- |
| `oacu/cancel.py` | 新增 | 139 行：`TaskCancelled`（code 130）、`CancelToken`、`_EscWatcher`、`TaskScope`、`current_token/check/sleep/request_cancel` |
| `oacu/chain.py` | 修改 | 删除私有 watcher，改用 `TaskScope`；取消返回 `stop_conversation`；取消不写幂等缓存 |
| `oacu/interpreter.py` | 修改 | 步前/等待/步内取消检查；`code=cancelled` 结果；`sleep` 改为可取消 |
| `oacu/agent.py` | 修改 | `run_act` 包 `TaskScope`；`status=cancelled`、`stop_conversation`、`ok=false` |
| `oacu/transport.py` | 修改 | 解释器 daemon 请求包 `TaskScope` |
| `oacu/cli.py` | 修改 | `--no-esc-cancel`；`act`/`exec` 取消退出码 130；取消摘要 |
| `oacu/mcp/protocol.py` | 修改 | `chain_run` 增加 `cancel_on_esc`；`computer_act` 透传取消/停止信号；STOP 文本 |
| `tests/test_cancel.py` | 新增 | 63 行：令牌睡眠、作用域复用、解释器步前/等待取消 |
| `tests/test_chain.py` | 修改 | 链级取消、等待中取消、Esc 观察器测试 |
| `README.md`、`RELEASE_NOTES.md` | 修改 | 取消范围、`stop_conversation`、退出码与限制 |
| `docs/chain-design.md` | 修改 | 取消语义与“正在进行的单步不打断”的边界 |

外部环境配置（不在仓库内）：`C:\Users\Administrator\.config\opencode\cli.json`
新增 `"session.interrupt": "escape"`，确保 OpenCode 当前回合也由 Esc 中断。

## 验证

- 166 个单元测试
- CLI 冒烟 10/10
- 端到端 12/12
- MCP 协议 4/4
- GUI 自检 5/5

测试覆盖：取消令牌可快速打断睡眠；嵌套 `TaskScope` 复用同一令牌；解释器在第一步前和
等待中返回 `code=cancelled`；链在取消前不执行任何步骤；等待中取消保留已执行结果并给出
`resume_from`；Esc 观察器能识别按键状态。

## 提交

`01d816d`：链级 Esc 取消（初版）。

```text
Cancel running operation chains with Esc
```

`4ce483c`：通用取消层，覆盖 `chain_run`、`computer_act`/`act`、IR `exec`，并返回
`stop_conversation`。

```text
Stop OpenCU runs and the current conversation on Esc
```

## 遗留问题

- Esc 是全局观察：执行期间在任意应用按 Esc 都会取消当前 OpenCU 任务；可用
  MCP `cancel_on_esc=false` 或 CLI `--no-esc-cancel` 关闭。
- 正在进行的单步 UIA/窗口消息调用不能强制中断，取消在下一步边界生效；极端情况下
  仍可能等待一次 PowerShell/UIA 调用的数秒返回。
- OpenCU 是工具服务，不能直接终止外部客户端的会话；“结束当前对话”依赖客户端
  （OpenCode 的 `session.interrupt`）或 agent 遵守 `stop_conversation` 信号。
- 取消不撤销已经完成的步骤；需要根据 `results`/`resume_from` 手工恢复。
- 不同客户端对 MCP `isError` 和自定义字段的处理不一致，停止信号不能保证所有客户端都遵守。
