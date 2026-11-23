# 阶段 7：2.2.0 十字准星

> 提交 `90d0ad4` ｜ 2026-11-11 ｜ 版本 2.2.0

## 阶段目标

2.1.0 的游标是 36×36 的 `▣` 字形。字符渲染受字体、DPI 和缩放影响，视觉上更像一个
“方块”，在浅色或复杂背景上不够直观。本阶段把它替换为 Minecraft 风格的十字准星：

- 白色十字 + 深色描边，中心对准虚拟坐标；
- 保持 36×36 透明窗口、点击穿透、置顶、不抢焦点；
- 不改变虚拟指针的坐标、状态或多指针行为；
- 不引入图片资源，继续用 Tk Canvas 直接绘制。

## 工程任务

1. `oacu/overlay.py` 移除 `CURSOR="▣"` 与 `FONT_SIZE`，改为
   `CURSOR="crosshair"`、`CROSS_HALF=9`、`CROSS_OUTLINE=5`、`CROSS_WIDTH=2`。
2. 在 36×36 Canvas 中心绘制两条线：先画 5px 深色 `#111827` 描边，再画 2px 白色
   `#ffffff` 内线；横竖各一条，`capstyle="butt"` 保持 Minecraft 的方块末端。
3. 保持原有透明色 `#ff00ff`、`WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`、
   置顶和 30ms 轮询逻辑不变。
4. 更新 `oacu/virtual.py` 的模块常量/注释，避免文档继续描述 `▣`。
5. 更新 `tests/test_overlay.py`：断言尺寸 36、`CROSS_HALF=9`、`CROSS_WIDTH=2`，
   并保持与 `virtual.MAX_POINTERS` 的一致性检查。
6. 同步 README、RELEASE_NOTES 的游标说明；历史阶段文档保留 `▣` 作为当时外观。

## 文件改动

| 文件 | 类型 | 改动 |
| --- | --- | --- |
| `oacu/overlay.py` | 修改 | 删除字形常量与 `create_text`；新增准星常量与两组 `create_line`；保留透明/穿透/计时逻辑 |
| `oacu/virtual.py` | 修改 | `VIRTUAL_CURSOR` 改为 `"crosshair"`；`_Overlay` docstring 同步 |
| `tests/test_overlay.py` | 修改 | 从断言字号改为断言准星半长/线宽；保留指针上限一致性 |
| `README.md` | 修改 | 当前版本、虚拟模式边界、目录说明改为十字准星 |
| `RELEASE_NOTES.md` | 修改 | 2.2.0 变更与亮点加入准星；历史 2.1.0 条目注明后续替换 |

## 验证

- 166 个单元测试（与 Esc 阶段相同，准星改动不增加用例数量）
- CLI 冒烟 10/10、端到端 12/12、MCP 4/4、GUI 5/5

实机验证：源码模式在 120/260/400/540 等坐标同时显示 4 个准星，窗口尺寸均为 36×36；
`WindowFromPoint` 返回底层应用窗口而不是 overlay，确认点击穿透；准星在浅色桌面和
深色窗口上都能看清。打包后的 `oacu.exe overlay` 另外验证了 4 个 36×36 窗口的创建、
独立位置与正常退出。

## 设计取舍

- 用 Canvas 线条而不是字体字符：不受 `Segoe UI Symbol` 字体缺失、字号缩放和字符
  基线影响，中心点更稳定。
- 用“深色粗线 + 白色细线”而不是单色：在浅色和深色背景上都有对比度，且不需要额外
  阴影窗口。
- 保持 36×36 窗口：与 2.1.0 的多指针、透明色键和点击穿透逻辑完全兼容，只替换绘制。
- 不画中心点：Minecraft 准星是纯十字，中心点会让小尺寸下看起来更像方块。


## 提交

`90d0ad4`

```text
Use a Minecraft-style crosshair for the virtual pointer
```

## 遗留问题

- 准星颜色固定为白/深灰，尚未提供主题或对比度配置；极端背景仍可能不够醒目。
- 4 个指针同色同形，只能靠位置区分；没有编号或颜色区分。
- 未做高 DPI 专项适配；窗口仍按 36×36 逻辑像素创建，系统缩放可能影响物理尺寸。
- 没有截图或像素级自动化回归，当前依赖实机观察和常量单测。
- 游标仍可能改变窗口 z-order/焦点（历史诊断存在 `GetForegroundWindow()` 等于 overlay
  的记录），不能宣称绝对不抢焦点。
