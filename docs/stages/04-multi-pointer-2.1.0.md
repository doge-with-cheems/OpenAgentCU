# 阶段 4：2.1.0 半尺寸与多指针

> 提交 `79bb139` ｜ 2026-11-10 ｜ 版本 2.1.0

## 阶段目标

2.0.1 的游标是 72×72 的 `▣`，单进程单窗口，所有操作共用同一个位置，且遮挡目标。
单游标只能显示最后一次位置，无法表达“两个指针分别操作两个窗口”的场景。本阶段目标：

- 把游标窗口与字号减半，面积降到 2.0.1 的 50%（72×72 → 36×36，字号 44 → 22）；
- 支持最多 4 个独立虚拟指针，默认只使用 1 号，2–4 号按需创建；
- 每个指针独立维护坐标、上次目标窗口和显示到期时间；坐标与窗口落盘互不覆盖；
- MCP 输入类工具与 CLI `input` 子命令统一增加 `pointer` / `--pointer` 参数（1–4）；
- 仍由一个 overlay 进程承载全部指针窗口，不引入额外常驻进程。

外观说明：本阶段缩小的仍是 `▣` 游标；十字准星是后续提交 `90d0ad4` 才引入的，
当前版本已改为准星，本文件只记录 2.1.0 当时的外观。

## 工程任务

1. 尺寸与常量：`overlay.py` 引入 `SIZE = 36`、`FONT_SIZE = 22`、
   `MAX_POINTERS = 4`、`COLORKEY`/`COLORKEY_REF`；中心偏移由 `SIZE // 2` 计算，
   去掉硬编码的 36。
2. 多窗口宿主：根窗口只作为隐藏的 Tk 宿主，每个指针对应一个懒创建的 `Toplevel`；
   `windows: dict[int, dict]` 保存窗口、`until` 到期时间和需要设置样式的句柄列表
   （窗口句柄 + 父句柄）。`create()` 负责绘制八向白色描边加中心 `#0d9488` 的 `▣`，
   并立即应用穿透/置顶样式。
3. 协议扩展：每行 JSON 增加 `id`，显示命令为 `{"id": 1, "x": 500, "y": 320, "ms": 900}`，
   隐藏命令为 `{"id": 2, "hide": true}`；`id` 不在 1–4 范围或无法转成整数时忽略该行。
4. 计时与退出：`show()` 只刷新对应指针的 `until`，`poll()` 每 30ms 遍历所有指针，
   到期各自 `withdraw`；stdin EOF 后若仍有指针未到期，则等待全部到期再销毁根窗口。
5. 主进程侧：`_Overlay` 抽出 `_send(payload)`（失败最多尝试两次），`show(..., pointer_id=1)`、
   新增 `hide(pointer_id=1)`；模块级 `_overlay()` 返回单例，供所有
   `VirtualPointer` 共享同一个 overlay 子进程。
6. 指针对象：`VirtualPointer(pointer_id=1)` 校验 1–4；1 号从物理光标位置起步，
   2–4 号首次使用从虚拟屏幕中心起步，避免与用户光标重叠；模块级缓存由单例
   `_POINTER` 改为 `_POINTERS: dict[int, VirtualPointer]`。
7. 状态持久化：`pointer.json` 升级为 `{"pointers": {"1": {"x", "y", "hwnd"}, ...}}`；
   读取时若没有 `pointers` 字段，则把 2.0.x 的顶层 `x/y/hwnd` 映射为 1 号指针。
   `_save()` 采用“读出现有文件 → 更新本指针 → 整体写回”。
8. 对外接口：`move/click/drag/scroll/key_press/key_down/key_up/key_hold/type_text/
   mouse_position` 增加末尾 `pointer_id=1` 参数；所有动作返回值补充 `pointer` 字段，
   便于调用方确认实际生效的指针。
9. MCP：8 个输入类工具（`mouse_move/click/drag/scroll`、`key_press`、`key_hold`、
   `type_text`、`mouse_position`）的 schema 增加 `pointer`（1–4，默认 1），
   处理函数统一经 `_pointer(arguments)` 取号。
10. CLI：`input move/click/drag/scroll/key/type/pos` 增加 `--pointer`（默认 1）；
    非 1 号时输出前缀 `[pointer n] `，JSON 载荷带 `pointer` 字段。

## 文件改动

| 文件 | 类型 | 改动 |
| --- | --- | --- |
| `oacu/overlay.py` | 修改 | 36×36 / 字号 22；`MAX_POINTERS=4`；多 `Toplevel` 懒创建；带 `id` 的显示与 `hide` 协议；按指针独立到期；EOF 等待全部到期 |
| `oacu/virtual.py` | 修改 | `MAX_POINTERS=4`；`_send()`、`show(..., pointer_id)`、`hide()`；`_overlay()` 单例；多指针状态文件与旧格式兼容；`VirtualPointer(pointer_id)` 校验与中心起步；`_POINTERS` 缓存；返回值带 `pointer` |
| `oacu/input.py` | 修改 | 转发 `MAX_POINTERS`、`pointer` 及各输入函数的 `pointer_id` |
| `oacu/cli.py` | 修改 | `add_pointer()` 助手；7 个 `input` 子命令增加 `--pointer`；摘要前缀与 JSON 载荷带指针号 |
| `oacu/mcp/protocol.py` | 修改 | 8 个工具 schema 增加 `pointer`；`_pointer()` 统一取值；返回值带 `pointer` |
| `tests/test_input.py` | 修改 | 新增编号范围校验、2 号指针独立且可复用两个用例 |
| `tests/test_mcp.py` | 修改 | 新增 schema 范围、`pointer=5` 拒绝、`mouse_position` 指定指针三个用例 |
| `tests/test_overlay.py` | 新增 | 校验 `SIZE=36`/`FONT_SIZE=22`，以及 overlay 与 virtual 的 `MAX_POINTERS` 一致 |
| `oacu/__init__.py` | 修改 | `__version__` 2.0.1 → 2.1.0 |
| `pyproject.toml` | 修改 | 版本号 2.1.0 |
| `packaging/installer.iss` | 修改 | `MyAppVersion` 2.1.0 |
| `packaging/version_info.txt` | 修改 | 文件/产品版本 2.1.0.0 |
| `packaging/build.ps1` | 修改 | 抽出 `$version`，包名统一引用 |
| `packaging/README-install.txt` | 修改 | 安装说明中的版本与包名 |
| `README.md` | 修改 | 版本标识、工具表 `pointer` 列、游标尺寸与多指针说明、测试数 145 |
| `RELEASE_NOTES.md` | 修改 | 2.1.0 变更清单、包名、验证数 145 |

## 验证

该提交的 `RELEASE_NOTES.md` 记录：

- 145 个单元测试（2.0.1 为 138，本阶段新增 7 个）
- CLI 冒烟 9/9
- 端到端 12/12
- MCP 协议 4/4
- GUI 自检 5/5

新增用例覆盖三类边界：指针编号只接受 1–4（`pointer(0)`、`pointer(5)` 抛
`InputError`）；2 号指针与 1 号不是同一实例且重复取用返回同一实例；MCP schema 的
`minimum/maximum/default` 为 1/4/1，`pointer=5` 返回 `isError` 且错误信息含 `1..4`，
`mouse_position(pointer=2)` 回传 `pointer: 2`。尺寸与常量一致性由
`tests/test_overlay.py` 锁定，防止后续只改一处。

## 提交

`79bb1390fd8db7ad961848b133b2f520d52f2df5`

```
OpenAgentCU 2.1.0: half-size overlay with up to four virtual pointers
```

共 16 个文件，核心为 `oacu/overlay.py`、`oacu/virtual.py`、`oacu/mcp/protocol.py`
与 `oacu/cli.py`；测试新增 7 个用例（含新建 `tests/test_overlay.py`）。

## 遗留问题

- 指针参数只贯通 MCP 原子工具与 CLI；`computer_act` / `act` / IR 解释器路径仍固定
  使用 1 号指针，计划式操作无法指定指针。
- `hide` 已在 `_Overlay` 与 `VirtualPointer` 实现，但没有 MCP 工具或 CLI 入口，
  外部无法主动隐藏游标。
- `pointer.json` 的读改写没有跨进程锁；MCP 服务与 CLI 同时操作不同指针时可能互相
  覆盖坐标。
- 升级后的状态文件对旧版本不向前兼容：2.0.1 只读顶层 `x/y/hwnd`，读到
  `{"pointers": ...}` 会视为无状态并回到物理光标位置。
- 每个父进程各自启动一个 overlay，多个 MCP 客户端或 CLI 并发时会叠加多个游标窗口，
  没有单实例仲裁。
- overlay 进程退出后 `_failed` 永久为真，指针输入继续可用但不再显示游标，需重启
  主进程恢复。
- 4 个指针同色同形，只能靠位置区分；上限常量在 `overlay.py` 与 `virtual.py` 各写
  一份，目前仅靠单测保持一致。
- `key` / `type` 的指针隔离只覆盖坐标与状态，实际按键仍发往 `last_hwnd` 或前台
  窗口，多指针并行操作同一应用时可能互相影响。
