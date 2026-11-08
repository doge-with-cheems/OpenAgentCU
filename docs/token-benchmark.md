# OpenAgentCU Token 基准

测量日期：2026-11-06 ｜ 版本：2.0.0（2.0.1 沿用） ｜ 估算口径：约 3.5 字符/token（JSON 与服务端 tokenizer 有差异）

## 1. 单次 MCP 调用

| 调用 | 实测字符 | 约 token |
| --- | --- | --- |
| `desktop_scan`（65 个可见元素，默认 80 行上限） | 2,523 | ~720 |
| `desktop_find("开始")` | 108 | ~31 |
| `launch_app` / `win_run` / `key_press` | 40–150 | 15–45 |
| 18 个工具的 schema（每轮都会随请求发送） | 6,190 | ~1,769 |

2.0.0 的 `desktop_scan` 只回 `content.text` 里的紧凑表，过滤无名 Pane/Group，默认 80 行；不再返回 `structuredContent`。

## 2. 旧版 Epstein 任务为什么约 1M

日志：75 次工具调用，工具结果合计 129,738 字符。

| 项目 | 数值 |
| --- | --- |
| `desktop_scan` | 6 次，94,514 字符（单次约 19.6k） |
| `desktop_find` | 34 次，17,282 字符 |
| 按键/输入/鼠标 | 约 9k 字符 |
| 累计上下文（每轮重发历史） | 约 6,316,282 字符 |
| 估算 token | 约 1.8M（按 3.5 字符/token；账单 1M 受缓存/口径影响） |

根因：

1. 0.2.1 把元素表放在 `structuredContent`，Chatbox 只把 `content.text` 给模型，模型看不到元素表；
2. 模型只能反复 `desktop_find`、按键、扫描来试探；
3. 75 轮的工具结果不断累积并重发，形成近似平方级上下文。

## 3. 2.0.0 典型任务估算

定义“典型任务”为 13 次工具调用：

- 1 次 `desktop_scan`
- 4 次 `desktop_find`
- 2 次 `launch_app` / `win_run`
- 6 次 `key_press` / `type_text` / `mouse_click`

计算：

| 组成 | 约 token |
| --- | --- |
| 工具 schema（1,769 × 13 轮） | 23,000 |
| 工具结果累计（约 3.4k 字符，13 轮三角累积） | 6,900 |
| 对话、系统提示与模型思考（按 13 轮粗估） | 8,000–20,000 |
| **合计** | **约 38k–50k** |

因此 2.0.0 的典型任务平均约 **45k token/任务**，简单任务可低至 20k–30k，复杂任务（大量点击/滚动/重试）约 60k–80k。

与旧版同任务约 1M 相比，下降约 **95%**。

## 4. 使用建议

1. **每个任务开新会话**；不要把几十轮工具历史一直带着。
2. 启动/打开/搜索/Win+R 用零扫描工具：`launch_app`、`open_url`、`search_web`、`win_run`。
3. 找元素用 `desktop_find`，不要全量扫描。
4. 桌面大改后才 `desktop_scan`；之后用 `diff=true`。
5. `computer_act` 默认精简；只有调试才 `verbose=true`。

> 以上为基于实测载荷的估算，不是模型供应商账单。实际 token 取决于客户端是否重发历史、是否计入思考 token、tokenizer 与缓存策略。
