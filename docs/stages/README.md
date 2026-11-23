# OpenAgentCU 阶段文档

本目录按时间顺序记录 OpenAgentCU 的主要工程阶段。每份文档说明该阶段的目标、工程任务、文件改动、验证结果、提交和遗留问题，便于回溯设计决策与排查回归。

## 阶段索引

| 阶段 | 版本/主题 | 提交 | 文档 |
| --- | --- | --- | --- |
| 1 | 1.0.0 首个公开版本 | `59fb476` | [01-initial-1.0.0.md](01-initial-1.0.0.md) |
| 2 | 2.0.0 虚拟输入边界 | `e18f50a` | [02-virtual-input-2.0.0.md](02-virtual-input-2.0.0.md) |
| 3 | 2.0.1 可见虚拟游标 | `6162666` | [03-overlay-2.0.1.md](03-overlay-2.0.1.md) |
| 4 | 2.1.0 半尺寸与多指针 | `79bb139` | [04-multi-pointer-2.1.0.md](04-multi-pointer-2.1.0.md) |
| 5 | 2.2.0 操作链 | `ef90088` | [05-operation-chain-2.2.0.md](05-operation-chain-2.2.0.md) |
| 6 | 2.2.0 Esc 取消 | `01d816d` / `4ce483c` | [06-esc-cancellation.md](06-esc-cancellation.md) |
| 7 | 2.2.0 十字准星 | `90d0ad4` | [07-crosshair.md](07-crosshair.md) |

## 阅读顺序

1. 先读 1.0.0，了解 UIA 采集、token 化、规划器/IR、解释器、MCP 和 GUI 的基础结构。
2. 再读 2.0.0，理解为什么放弃物理键鼠注入，改为虚拟指针和定向窗口消息。
3. 2.0.1、2.1.0 依次补充游标可见性、多指针和尺寸调整。
4. 2.2.0 是当前主线：操作链、Esc 取消、十字准星视觉。
5. 需要修改行为时，优先阅读对应阶段的“文件改动”和“遗留问题”。

## 当前状态

当前代码版本为 **2.2.0**。最新阶段包含：

- 操作链 `chain_run`：整链预检、按指针执行、6–12 步建议、幂等与超时。
- Esc 取消：覆盖操作链、`computer_act`/`act`、IR 执行，并返回 `stop_conversation`。
- 十字准星：36×36 透明窗口，白色准星加深色描边，点击穿透。
- 全局技能：`~/.agents/skills/opencu/SKILL.md` 与本仓库同步维护。

阶段文档只描述历史与当前实现，不替代 `README.md`（使用说明）、`RELEASE_NOTES.md`（发布说明）和 `docs/chain-design.md`（操作链设计）。
