# 操作链设计（OpenAgentCU 2.2.0）

## 目标

在“大模型直接调用原子键鼠工具”和“OpenCU 执行”之间增加一层**操作链**：

```text
LLM 观察/定位 → 写一条 chain JSON → OpenCU 整链校验 → 按指针顺序执行 → 紧凑结果
```

链是固定序列，执行中不调用 LLM、不自适应。复杂任务拆成多条 6–12 步短链，每条链前后
用 `desktop_scan(diff=true)` 或截图验证。

## 为什么是同步执行

- MCP 传输层是逐行请求/响应（`oacu/mcp/server.py`），没有异步任务表或多路复用。
- `computer_act` 已证明同步多步可接受；6–12 步通常远低于客户端超时。
- 同步天然避免“两个指针同时抢真实焦点”的问题。**每指针独立**指坐标、目标窗口、
  锁和链状态独立，不承诺时间重叠。
- 将来若需要并行，保留 `run_chain()` 纯函数形状，把调用方改为 job 表 +
  `chain_status/chain_cancel` 即可，不需要改链语义。

## 分层

```text
oacu/chain.py        校验、规范化、执行、结果压缩、幂等缓存
oacu/virtual.py      每指针 VirtualPointer + pointer_lock()
oacu/input.py        CLI/GUI/MCP 共用的输入门面
oacu/mcp/protocol.py chain_run 工具与紧凑渲染
oacu/cli.py          oacu chain run
```

链层不组装 IR，也不经过 `interpreter.execute`：解释器的后端没有 pointer 参数，
直接调用 `VirtualPointer` 才能保证每条链使用自己的指针状态。

## 步骤 schema

```json
{"op":"click","x":420,"y":260}
```

| op | 字段 | 说明 |
| --- | --- | --- |
| `move` | `x,y,duration_ms?` | 移动该指针，不点击 |
| `click` | `x?,y?,button?,clicks?,interval_ms?` | 省略 x/y 表示当前位置点击；button 默认 left |
| `drag` | `to_x,to_y,from_x?,from_y?,button?,duration_ms?` | 省略 from 表示从当前位置拖 |
| `scroll` | `direction,times?` | `up/down/left/right`，避免 dy 符号歧义 |
| `key` | `keys,ms?` | `ms>0` 走 key_hold，否则 key_press |
| `type` | `text,replace?` | `replace=true` 走 UIA SetValue；false 走 WM_CHAR 追加 |
| `wait` | `ms?` | 仅等待，不计入输入 |

`key`/`type` 之前必须有 `click` 或 `drag`，确保目标窗口在本链内建立，而不是使用
`pointer.json` 里上一次会话残留的 `last_hwnd`。

## 校验优先

执行前对整条链做一次预检，任何错误都返回 `executed=0`，不会出现“前 3 步已点击、
第 4 步才发现参数拼错”：

- 未知 op / 未知字段 / 类型错误；
- 坐标是否在虚拟屏幕内；
- 按键表达式与系统组合键拒绝（Win、Alt+Tab、Alt+F4、Ctrl+Shift+Esc）；
- click 次数、wait 时长、文本长度、预计总耗时；
- key/type 的目标窗口前置条件。

建议 6–12 步；1–5 或 13–32 步只给 `length_hint`，不阻断。硬上限 32 步。

## 结果与失败

```json
{"ok":true,"status":"done","pointer":1,"steps":6,"executed":6,
 "results":[[0,"click",true,12,null],[1,"wait",true,300,null]],
 "state":{"x":100,"y":200,"hwnd":123456},"retry_safe":false}
```

- 每步五元组：`[index, op, ok, ms, code|null]`。
- `stop_on_error=true`（默认）：首错即停，`status=stopped`，返回 `resume_from`。
- `stop_on_error=false`：继续执行，`status=partial`，`ok=false`。
- 定向消息投递失败（`delivered=false`）计为 `post_failed`，不把调用成功当业务成功。
- 链级超时（默认 30s）在每步前检查，超时返回 `timeout` 和 `resume_from`。
- 执行期间按 **Esc**：全局观察、不拦截按键，在下一步边界取消；`status=cancelled`，
  返回已执行结果和 `resume_from`，`cancelled=true`。正在进行的单步 UIA 调用不会被打断。
- 取消结果同时带 `stop_conversation=true`；遵循该信号的 agent 应立即结束当前对话。
  OpenCode 原生 `session.interrupt` 默认也是 Esc，可同时中断客户端回合。
  同一机制也用于 `computer_act`/`act` 的 IR 执行；取消后 `status=cancelled`、退出码 130。
- 失败后不要重发整链；用 `resume_from` 和 `results` 决定补救动作。若剩余步骤以
  `key`/`type` 开头，必须补一个 `click`/`drag` 重新绑定目标窗口，否则会因
  `no_target` 被预检拒绝。
- `retry_safe=false` 表示链可能已经产生副作用；只有预检失败（`executed=0`）才是安全的。

## 幂等

`chain_id` 在进程内缓存 120 秒（最多 16 条）。同一 `chain_id` 重放直接返回上次结果，
`duplicate=true`，不再次发送输入。客户端可能超时重试时应始终提供唯一 `chain_id`。
缓存不跨进程，CLI 每次运行是独立进程。

## 限额

| 项 | 限制 |
| --- | --- |
| 步数 | 1–32（建议 6–12） |
| 文本 | 2000 字符 |
| 单步等待 | 10000ms |
| move/drag 时长 | 5000ms |
| click 次数 | 3（右键/中键 2） |
| 链超时 | 1000–120000ms，默认 30000ms |

## 并发

- 每个指针一把进程内 `threading.Lock`；同指针同时只允许一条链。
- 不同指针的链状态独立，但当前 MCP 服务器单线程串行处理请求，因此不会真正并行执行。
- 若将来支持多客户端/并行，需要增加全局输入调度器：等待类步骤可交错，真正输入步骤
  仍应串行，避免焦点与目标窗口互相污染。

## 不在 v1 范围

- 链内条件分支、循环、观察/重规划；
- 链内调用 `desktop_scan` 或截图（应由外部步骤拆分）；
- 跨进程取消与进度通知；
- GUI 操作链编辑器（可复用同一 `run_chain`）。
