# 阶段 5：2.2.0 操作链

> 提交 `ef90088` ｜ 2026-11-10 ｜ 版本 2.2.0

## 阶段目标

原子工具要求模型逐步“点一下、等一下、再点一下”，每一步都要往返一次工具调用，长任务
的 token 成本和失败重试成本都很高。本阶段增加中间层**操作链**：

- 模型先观察/定位，再一次性写 6–12 步链；
- OpenCU 对整条链做一次预检，确认后才开始输入，避免“前几步已点击、后面才发现参数错”；
- 每条链绑定一个虚拟指针（1–4），各指针的坐标、目标窗口、锁和链状态独立；
- 链级支持停止、继续、超时、幂等和逐级结果，便于失败后恢复而不是整链重发。

## 工程任务

1. 新增 `oacu/chain.py`：定义 7 种操作 `move/click/drag/scroll/key/type/wait`，
   校验字段、坐标、按键、文本长度、点击次数、等待时长和预计总耗时。
2. 执行语义：默认 `stop_on_error=true`；失败返回已执行步与 `resume_from`；
   `stop_on_error=false` 时继续执行并标记 `partial`。
3. 安全约束：`key`/`type` 之前必须有链内 `click`/`drag`，确保目标窗口来自本链；
   `scroll` 使用 `direction`，消除 `dy` 正负方向歧义。
4. 指针隔离：使用 `pointer_lock(pointer_id)` 防止同指针并发；链内所有动作调用同一个
   `VirtualPointer`，保留该指针的 `last_point`/`last_hwnd`。
5. 投递校验：`virtual.py` 的点击/拖拽/滚轮/按键/文本增加 `delivered`，
   定向消息全部失败时链步骤记为 `post_failed`，不再“调用成功即业务成功”。
6. 输入控制：`type_text(replace=False)` 跳过 UIA SetValue，退回 WM_CHAR 追加；
   `virtual.validate_keys()` 在预检阶段就拒绝系统组合键。
7. 省 token：MCP 工具 `chain_run` 返回紧凑文本（头部 + 每步 `index op ok/错误码 耗时`），
   不在结果里重复整链 JSON；`dry_run` 只返回计划和预计耗时。
8. 幂等：可选的 `chain_id` 在 120 秒内缓存结果，客户端超时重发时直接返回上次结果，
   `duplicate=true`，不重复输入。
9. 入口：MCP `chain_run`；CLI `oacu chain run <file>| -`，支持
   `--pointer/--dry-run/--stop-on-error/--keep-going/--timeout-ms/--chain-id`。
10. 文档与验收：新增 `docs/chain-design.md`、`tools/chain_demo.json`、`tests/test_chain.py`；
    MCP 探针和 CLI 冒烟同步加入链检查。

## 文件改动

| 文件 | 类型 | 改动 |
| --- | --- | --- |
| `oacu/chain.py` | 新增 | 468 行：校验、规范化、执行、结果压缩、幂等缓存、取消接口 |
| `docs/chain-design.md` | 新增 | 设计目标、同步执行理由、schema、失败语义、限额与并发 |
| `tests/test_chain.py` | 新增 | 12 个用例：预检、失败停机、继续、指针隔离、幂等、长度提示等 |
| `tools/chain_demo.json` | 新增 | 6 步示例链（click/type/wait/key/scroll/move） |
| `oacu/cli.py` | 修改 | 新增 `chain run` 子命令与文件/BOM 处理、摘要与退出码 |
| `oacu/mcp/protocol.py` | 修改 | 新增 `chain_run` 定义/handler、审计、紧凑渲染、未知参数检查 |
| `oacu/virtual.py` | 修改 | `validate_pointer/validate_keys/pointer_lock`；`delivered`；`type_text(replace)` |
| `oacu/input.py` | 修改 | 转发新校验与锁接口 |
| `tests/test_mcp.py` | 修改 | 工具数 18→19，新增 dry-run 与非法链用例 |
| `tools/smoke_cli.py` | 修改 | 增加 chain dry-run，检查数 9→10 |
| `tools/mcp_probe.py` | 修改 | 工具集合加入 `chain_run` |
| `README.md` | 修改 | 工具表、操作链章节、CLI 示例、测试数 |
| `RELEASE_NOTES.md` | 修改 | 2.2.0 变更、包名、验证数 |
| `docs/token-benchmark.md` | 修改 | 工具 schema 数 18→19 |
| `docs/open_agent_computer_use_in_windows.logic.md` | 修改 | 工具列表与 CLI 检查项 |
| `oacu/__init__.py`、`pyproject.toml` | 修改 | 2.2.0 |
| `packaging/*` | 修改 | 安装包版本、包名、说明 |
| `tests/test_chain.py`、`README`、`RELEASE_NOTES` | 后续 | `bf6749f` 补充恢复语义；`ef71ba3` GUI MCP 提示加入 `chain_run` |

## 验证

- 159 个单元测试
- CLI 冒烟 10/10
- 端到端 12/12
- MCP 协议 4/4
- GUI 自检 5/5

实测 6 步链在 3 号指针完成，坐标状态独立；`dry_run` 不创建指针；非法字段/未知操作
在执行前返回 `executed=0`。

## 提交

`ef90088`

```text
OpenAgentCU 2.2.0: batch operation chains per virtual pointer
```

后续提交：`bf6749f`（失败恢复需补 click/drag 的说明）、`ef71ba3`（GUI 工具提示）。

## 遗留问题

- 链是固定序列，执行中不会观察或自适应；复杂任务应拆成多条 6–12 步短链。
- MCP 传输层同步处理，一条链执行期间不能接收新的 tool 请求；不同指针的链状态独立，
  但不会真正并行。
- 失败后若剩余步骤以 `key`/`type` 开头，不能直接只发剩余部分，必须补一个
  `click`/`drag` 重新绑定目标窗口。
- `chain_id` 幂等缓存只在进程内有效，CLI 每次运行是独立进程。
- 还没有 GUI 操作链编辑器；GUI 仍以单步输入为主。
