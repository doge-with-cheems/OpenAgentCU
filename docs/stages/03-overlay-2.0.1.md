# 阶段 3：2.0.1 可见虚拟游标

> 提交 `6162666` ｜ 2026-11-08 ｜ 版本 2.0.1

## 阶段目标

2.0.0 已将输入改为虚拟指针加定向 UIA/窗口消息，但可视化只有一个在 `virtual.py`
后台线程里创建的 64×64 点击环。Tk 的窗口循环要求由主线程驱动，后台线程方案不符合
Tk 的线程模型，长期驻留进程中的刷新与退出都缺乏保障；CLI 单次命令也缺少稳定的
可见反馈。
本阶段的目标是把“输入”和“显示”拆开：

- 新增独立进程 `oacu overlay`，由它独占 Tk 主线程渲染游标；
- 游标置顶、点击穿透、不抢焦点，不改变被测应用的焦点与输入；
- 每次虚拟操作都在该指针当前位置显示 `▣`，默认保持约 900ms；
- 主进程通过 stdin 单向下发 JSON 命令，overlay 崩溃或不可用不影响输入本身。

外观说明：`▣` 加八向白色描边、中心 `#0d9488` 是 2.0.1 当时的游标形态；后续提交
`90d0ad4` 才改为十字准星，本文件只记录该阶段的历史外观。

## 工程任务

1. 实现 `oacu/overlay.py`：无边框置顶窗口，72×72 Canvas，`Segoe UI Symbol` 44 号字，
   透明色 `#ff00ff`；通过 `SetWindowLongPtrW` 给窗口及其父窗口加
   `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`，再用
   `SetLayeredWindowAttributes` 重新声明色键，保证点击穿透且不激活。
2. 定义 stdin 协议：每行一个 JSON 对象 `{"x": 500, "y": 320, "ms": 900}`；读取线程
   只做解析入队，Tk 主线程每 30ms 轮询队列、移动窗口并设置到期时间。
3. 定义生命周期：stdin 收到 EOF 时，若当前游标尚未到期则继续显示到到期再退出，
   保证 CLI 一次性命令也能看到游标；到期后 `withdraw`，关闭时 `destroy`。
4. 改造 `oacu/virtual.py`：删除线程内 Tk 点击环，`_Overlay` 改为
   `subprocess.Popen` 管理 overlay 子进程；源码模式用 `python -m oacu overlay`，
   打包模式用 `可执行文件 overlay`，均带 `CREATE_NO_WINDOW`，stdout/stderr 丢弃。
5. 发送失败最多尝试两次（一次重试），仍失败则置 `_failed` 并静默降级；`OACU_NO_OVERLAY=1` 或
   `oacu.gui` 已载入时禁用 overlay。
6. 在 CLI 增加隐藏的 `overlay` 子命令，并在 `argparse` 的子命令列表中移除其条目，
   保持 `oacu --help` 不暴露内部进程入口。

## 文件改动

| 文件 | 类型 | 改动 |
| --- | --- | --- |
| `oacu/overlay.py` | 新增 | 独立 Tk 进程；`▣` 绘制、透明色、点击穿透样式、stdin JSON、30ms 轮询、到期隐藏与 EOF 处理 |
| `oacu/virtual.py` | 修改 | 移除线程内 64×64 点击环；`_Overlay` 改为子进程 + stdin 写入；`show()` 增加 `hold_ms=900`；`key_hold` 用 `max(900, ms)`；新增 `_start()` 与失败降级 |
| `oacu/cli.py` | 修改 | 新增隐藏 `overlay` 子命令与 `cmd_overlay()`（延迟导入 `overlay.main`）；清理 `sub._choices_actions` |
| `oacu/__init__.py` | 修改 | `__version__` 2.0.0 → 2.0.1 |
| `pyproject.toml` | 修改 | 版本号 2.0.1 |
| `packaging/installer.iss` | 修改 | `MyAppVersion` 2.0.1 |
| `packaging/version_info.txt` | 修改 | 文件/产品版本 2.0.1.0 |
| `packaging/build.ps1` | 修改 | 安装包与便携包文件名改为 2.0.1 |
| `packaging/README-install.txt` | 修改 | 安装说明中的版本与包名 |
| `packaging/OpenAgentCU.ico` | 修改 | 图标资源更新（二进制） |
| `README.md` | 修改 | 版本标识、`▣` 游标说明、模块职责表 |
| `RELEASE_NOTES.md` | 修改 | 新增 2.0.1 变更条目与包名 |
| `docs/token-benchmark.md` | 修改 | 版本行标注“2.0.0（2.0.1 沿用）” |

## 验证

该提交的 `RELEASE_NOTES.md` 记录：

- 138 个单元测试
- CLI 冒烟 9/9
- 端到端 12/12
- MCP 协议 4/4
- GUI 自检 5/5

本阶段没有新增 overlay 专项单测（`tests/` 仍为 138 个）。按实现，overlay 的可见行为
只能在实际运行中观察：MCP 长驻进程下每次操作把游标移到目标坐标；CLI 单次命令
退出时 stdin 收到 EOF，游标保留到 900ms 到期后再退出。该路径未纳入自动化测试。
输入路径本身未改动语义，回归由既有 138 个测试覆盖。

## 提交

`61626665b5ed0dc9944f750660d783f3877a0406`

```
OpenAgentCU 2.0.1: visible ▣ virtual cursor overlay
```

共 13 个文件，核心是新增 `oacu/overlay.py`（146 行）与重写 `virtual._Overlay`。

## 遗留问题

- 单游标：所有操作复用同一个窗口，只有最后一次坐标可见，无法同时显示多个位置。
- 保持时间固定为默认 900ms，只有 `key_hold` 延长到按键时长；慢速拖拽或长等待后
  游标可能提前消失。
- overlay 失败后 `_failed` 永久为真且无日志，用户只能看到“没有游标”，难以排查。
- `disabled` 在 `oacu.gui` 已载入时返回真，GUI 进程实际不显示独立游标，与 README
  “长驻的 MCP/GUI 里持续可见”的表述不一致，需要后续统一。
- 隐藏子命令依赖 `argparse` 私有属性 `_choices_actions`，升级 Python 时可能失效。
- 打包模式假定可执行文件接受 `overlay` 位置参数；若入口参数解析变化，子进程会启动失败。
- overlay 进程未声明 DPI 感知，系统缩放不是 100% 时 72×72 的物理尺寸可能被拉伸。
