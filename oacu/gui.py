"""Native Windows GUI shell for OpenAgentCU (tkinter, stdlib only)."""

from __future__ import annotations

import json
import os
import queue
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from . import __version__
from .config import DEFAULTS, Settings, home_dir
from .errors import EnvUnavailable
from .pipeline import capture_snapshot
from .store import Store

C = {
    "bg": "#f1f5f9",
    "card": "#ffffff",
    "border": "#e2e8f0",
    "text": "#0f172a",
    "muted": "#64748b",
    "accent": "#0d9488",
    "accent_dark": "#0f766e",
    "header": "#0f172a",
    "side": "#0f172a",
    "side_hover": "#1e293b",
    "side_active": "#134e4a",
    "ok": "#059669",
    "err": "#dc2626",
    "warn": "#d97706",
}

FONT = "Microsoft YaHei UI"
MONO = "Consolas"


def _dpi() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - cosmetic only
        pass


def _set_text(widget: tk.Text, value: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", value)
    widget.configure(state="disabled")


def _text_box(parent: tk.Misc, mono: bool = True, wrap: str = "word") -> tuple[tk.Frame, tk.Text]:
    frame = tk.Frame(parent, bg=C["card"])
    widget = tk.Text(
        frame, relief="flat", bd=0, bg=C["card"], fg=C["text"],
        insertbackground=C["text"], wrap=wrap,
        font=(MONO, 9) if mono else (FONT, 10), padx=10, pady=8,
    )
    scroll = ttk.Scrollbar(frame, orient="vertical", command=widget.yview)
    widget.configure(yscrollcommand=scroll.set, state="disabled")
    widget.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    return frame, widget


class GuiApp:
    def __init__(self, root: tk.Tk, settings: Settings, fixture: str | None = None,
                 start_tab: int = 0) -> None:
        self.root = root
        self.settings = settings
        self.fixture = fixture
        self.start_tab = start_tab
        self.tokens: list[Any] = []
        self.current_snapshot_id: int | None = None
        self.records: list[dict[str, Any]] = []
        self.busy = False
        self.queue: queue.Queue[tuple] = queue.Queue()
        self.buttons: list[ttk.Button] = []
        self.nav_buttons: list[tk.Button] = []
        self.views: list[ttk.Frame] = []
        self._build_style()
        self._build()
        self.root.after(80, self._poll)
        self.root.after(150, self._startup_load)

    # ------------------------------------------------------------------ style
    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=(FONT, 10), background=C["bg"], foreground=C["text"])
        style.configure("TFrame", background=C["bg"])
        style.configure("Card.TFrame", background=C["card"])
        style.configure("TLabel", background=C["bg"], foreground=C["text"])
        style.configure("Card.TLabel", background=C["card"], foreground=C["text"])
        style.configure("Muted.TLabel", background=C["bg"], foreground=C["muted"])
        style.configure("CardMuted.TLabel", background=C["card"], foreground=C["muted"])
        style.configure("Stat.TLabel", background=C["card"], foreground=C["text"],
                        font=(FONT, 10, "bold"))
        style.configure("TButton", padding=(12, 6))
        style.configure("Accent.TButton", background=C["accent"], foreground="white",
                        borderwidth=0, padding=(16, 7), font=(FONT, 10, "bold"))
        style.map("Accent.TButton",
                  background=[("active", C["accent_dark"]), ("disabled", "#94a3b8")],
                  foreground=[("disabled", "#e2e8f0")])
        style.configure("Danger.TButton", background=C["err"], foreground="white",
                        borderwidth=0, padding=(16, 7), font=(FONT, 10, "bold"))
        style.map("Danger.TButton",
                  background=[("active", "#b91c1c"), ("disabled", "#cbd5e1")],
                  foreground=[("disabled", "#f8fafc")])
        style.configure("Treeview", rowheight=25, background=C["card"],
                        fieldbackground=C["card"], borderwidth=0)
        style.configure("Treeview.Heading", font=(FONT, 9, "bold"),
                        background="#e2e8f0", foreground=C["text"], padding=(6, 5))
        style.map("Treeview", background=[("selected", "#ccfbf1")],
                  foreground=[("selected", C["text"])])
        style.configure("TNotebook", background=C["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 6), background="#e2e8f0",
                        foreground=C["muted"])
        style.map("TNotebook.Tab",
                  background=[("selected", C["card"])],
                  foreground=[("selected", C["text"])])

    # ------------------------------------------------------------------- build
    def _build(self) -> None:
        self.root.configure(bg=C["bg"])
        self.root.title(f"OpenAgentCU {__version__} · Windows 桌面智能体")
        self.root.geometry("1220x780")
        self.root.minsize(1020, 640)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self.root, bg=C["header"], height=66)
        header.grid(row=0, column=0, sticky="ew")
        header.pack_propagate(False)
        tk.Label(header, text="◈ OpenAgentCU", bg=C["header"], fg="white",
                 font=(FONT, 15, "bold")).pack(side="left", padx=(22, 10))
        tk.Label(header, text="桌面感知 · 元素 token 化 · UIA 执行", bg=C["header"],
                 fg="#94a3b8", font=(FONT, 9)).pack(side="left", pady=(6, 0))
        self.chip = tk.Label(header, text="就绪", bg=C["accent"], fg="white",
                             font=(FONT, 9, "bold"), padx=12, pady=4)
        self.chip.pack(side="right", padx=(8, 22))
        tk.Label(header, text=f"v{__version__}", bg=C["header"], fg="#94a3b8",
                 font=(FONT, 9)).pack(side="right")

        body = tk.Frame(self.root, bg=C["bg"])
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        sidebar = tk.Frame(body, bg=C["side"], width=190)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        self.content = tk.Frame(body, bg=C["bg"])
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        labels = ["桌面快照", "指令执行", "运行记录", "MCP / 设置", "输入控制"]
        builders = [self._view_snapshot, self._view_instruction, self._view_records,
                    self._view_mcp, self._view_input]
        for index, (label, builder) in enumerate(zip(labels, builders)):
            view = ttk.Frame(self.content, padding=(18, 14))
            view.grid(row=0, column=0, sticky="nsew")
            self.views.append(view)
            builder(view)
            button = tk.Button(
                sidebar, text=label, anchor="w", relief="flat", bd=0,
                bg=C["side"], fg="#cbd5e1", activebackground=C["side_hover"],
                activeforeground="white", font=(FONT, 10), padx=22, pady=12,
                cursor="hand2", command=lambda i=index: self._show(i),
            )
            button.pack(fill="x", pady=1)
            self.nav_buttons.append(button)

        tk.Frame(sidebar, bg="#1e293b", height=1).pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(sidebar, text="Ctrl+Enter 预演指令", bg=C["side"], fg="#64748b",
                 font=(FONT, 8)).pack(anchor="w", padx=22)

        footer = tk.Frame(self.root, bg="#e2e8f0", height=28)
        footer.grid(row=2, column=0, sticky="ew")
        footer.pack_propagate(False)
        self.footer = tk.Label(footer, text="", bg="#e2e8f0", fg="#475569",
                               font=(FONT, 9), anchor="w", padx=14)
        self.footer.pack(fill="both", expand=True)

        self._show(max(0, min(4, self.start_tab)))
        self._log("就绪。先采集桌面，或在「指令执行」里输入一条指令。", "muted")
        self.root.after(200, self._init_sashes)

    def _init_sashes(self) -> None:
        for panes, ratio in ((getattr(self, "snapshot_panes", None), 0.62),
                             (getattr(self, "instruction_panes", None), 0.5)):
            if panes is None:
                continue
            try:
                panes.sashpos(0, int(panes.winfo_width() * ratio))
            except tk.TclError:
                pass

    def _show(self, index: int) -> None:
        for i, button in enumerate(self.nav_buttons):
            if i == index:
                button.configure(bg=C["side_active"], fg="white", font=(FONT, 10, "bold"))
            else:
                button.configure(bg=C["side"], fg="#cbd5e1", font=(FONT, 10))
        self.views[index].tkraise()

    # ------------------------------------------------------------------ helpers
    def _log(self, text: str, kind: str = "info") -> None:
        colors = {"ok": C["ok"], "err": C["err"], "warn": C["warn"], "muted": C["muted"],
                  "info": C["text"]}
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n", kind)
        self.log_text.tag_configure(kind, foreground=colors.get(kind, C["text"]))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_footer(self, text: str) -> None:
        self.footer.configure(text=text)

    def _set_chip(self, text: str, kind: str = "ok") -> None:
        color = {"ok": C["accent"], "busy": C["warn"], "err": C["err"], "idle": C["muted"]}.get(kind, C["accent"])
        self.chip.configure(text=text, bg=color)

    def _action_buttons(self) -> list[ttk.Button]:
        return self.buttons

    def _refresh_button_state(self) -> None:
        allow = bool(self.allow_execute.get()) and not self.busy
        self.execute_button.configure(state="normal" if allow else "disabled")
        for button in self.buttons:
            if button is not self.execute_button:
                button.configure(state="disabled" if self.busy else "normal")

    def run_task(self, label: str, work: Callable[[], Any], apply: Callable[[Any], None]) -> None:
        if self.busy:
            self._set_footer("正在执行上一个任务，请稍候")
            return
        self.busy = True
        self._set_chip(label, "busy")
        self._set_footer(label)
        self._refresh_button_state()

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001 - surfaced in the UI
                self.queue.put(("err", exc))
            else:
                self.queue.put(("ok", result, apply))

        threading.Thread(target=runner, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                item = self.queue.get_nowait()
                if item[0] == "ok":
                    _, result, apply = item
                    try:
                        apply(result)
                    except Exception as exc:  # noqa: BLE001
                        self._task_failed(exc)
                    else:
                        self.busy = False
                        self._set_chip("就绪", "ok")
                        self._set_footer("完成")
                        self._refresh_button_state()
                else:
                    self._task_failed(item[1])
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _task_failed(self, exc: Exception) -> None:
        self.busy = False
        self._set_chip("错误", "err")
        self._set_footer(str(exc))
        self._refresh_button_state()
        self._log(f"错误: {exc}", "err")

    def _store(self) -> Store:
        return Store(self.settings.db)

    # ---------------------------------------------------------------- snapshot
    def _card(self, parent: tk.Misc) -> tk.Frame:
        frame = tk.Frame(parent, bg=C["card"], highlightbackground=C["border"],
                         highlightthickness=1)
        return frame

    def _view_snapshot(self, view: ttk.Frame) -> None:
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(2, weight=1)

        toolbar = self._card(view)
        toolbar.grid(row=0, column=0, sticky="ew")
        inner = tk.Frame(toolbar, bg=C["card"])
        inner.pack(fill="x", padx=12, pady=10)

        tk.Label(inner, text="窗口过滤", bg=C["card"], fg=C["muted"],
                 font=(FONT, 9)).pack(side="left")
        self.window_var = tk.StringVar()
        ttk.Entry(inner, textvariable=self.window_var, width=22).pack(side="left", padx=(8, 16))

        tk.Label(inner, text="最大元素", bg=C["card"], fg=C["muted"],
                 font=(FONT, 9)).pack(side="left")
        self.max_elements_var = tk.StringVar(value=str(self.settings.config.get("max_elements", 3000)))
        ttk.Spinbox(inner, from_=50, to=5000, increment=50, width=7,
                    textvariable=self.max_elements_var).pack(side="left", padx=(8, 16))

        scan_button = ttk.Button(inner, text="采集桌面", style="Accent.TButton", command=self.scan)
        scan_button.pack(side="left")
        self.buttons.append(scan_button)
        reload_button = ttk.Button(inner, text="读取最近快照", command=self.refresh_snapshot)
        reload_button.pack(side="left", padx=(8, 0))
        self.buttons.append(reload_button)

        stats = self._card(view)
        stats.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        self.stat_snapshot = tk.StringVar(value="尚未采集")
        self.stat_tokens = tk.StringVar(value="0 tokens")
        self.stat_windows = tk.StringVar(value="0 windows")
        self.stat_dropped = tk.StringVar(value="dropped 0")
        for var in (self.stat_snapshot, self.stat_tokens, self.stat_windows, self.stat_dropped):
            tk.Label(stats, textvariable=var, bg=C["card"], fg=C["text"],
                     font=(FONT, 10, "bold")).pack(side="left", padx=16, pady=9)
        tk.Label(stats, text="UI Automation · PowerShell 桥", bg=C["card"], fg=C["muted"],
                 font=(FONT, 8)).pack(side="right", padx=14)

        panes = ttk.Panedwindow(view, orient="horizontal")
        panes.grid(row=2, column=0, sticky="nsew")
        self.snapshot_panes = panes

        left = self._card(panes)
        panes.add(left, weight=5)
        columns = ("order", "id", "name", "type", "rect")
        self.token_tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        for column, title, width in (
            ("order", "#", 40), ("id", "ID", 56), ("name", "组件名", 190),
            ("type", "类型", 86), ("rect", "坐标", 120),
        ):
            self.token_tree.heading(column, text=title)
            self.token_tree.column(column, width=width, stretch=column == "name",
                                   anchor="w" if column in ("name", "type") else "center")
        yscroll = ttk.Scrollbar(left, orient="vertical", command=self.token_tree.yview)
        xscroll = ttk.Scrollbar(left, orient="horizontal", command=self.token_tree.xview)
        self.token_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        xscroll.pack(side="bottom", fill="x")
        yscroll.pack(side="right", fill="y")
        self.token_tree.pack(side="left", fill="both", expand=True, padx=(2, 0), pady=(2, 0))
        self.token_tree.bind("<<TreeviewSelect>>", self._on_token_select)

        right = self._card(panes)
        panes.add(right, weight=4)
        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True, padx=2, pady=2)
        detail_tab = tk.Frame(notebook, bg=C["card"])
        detail_frame, self.detail_text = _text_box(detail_tab)
        detail_frame.pack(fill="both", expand=True)
        notebook.add(detail_tab, text="选中组件")
        token_tab = tk.Frame(notebook, bg=C["card"])
        token_frame, self.token_text = _text_box(token_tab, wrap="none")
        token_frame.pack(fill="both", expand=True)
        notebook.add(token_tab, text="Token 文本")

    def scan(self) -> None:
        try:
            max_elements = int(self.max_elements_var.get())
        except ValueError:
            max_elements = 3000
        window = self.window_var.get().strip() or None
        settings = self.settings
        fixture = self.fixture

        def work():
            snapshot = capture_snapshot(
                backend=settings.backend, window=window, max_elements=max_elements,
                fixture=fixture,
            )
            store = self._store()
            try:
                snapshot_id = store.save_snapshot(
                    snapshot, keep=int(settings.config.get("snapshot_keep", 20)))
            finally:
                store.close()
            return snapshot_id, snapshot

        self.run_task("正在采集桌面…", work, self._apply_snapshot)

    def _apply_snapshot(self, data: tuple[int, Any]) -> None:
        snapshot_id, snapshot = data
        self.current_snapshot_id = snapshot_id
        self._fill_tokens(snapshot.tokens, snapshot.text)
        self.stat_snapshot.set(f"snapshot #{snapshot_id}")
        self.stat_tokens.set(f"{len(snapshot.tokens)} tokens")
        self.stat_windows.set(f"{len(snapshot.window)} windows")
        self.stat_dropped.set(f"dropped {snapshot.stats.get('dropped', 0)}")
        self._log(f"采集完成：snapshot #{snapshot_id}，{len(snapshot.tokens)} tokens，"
                  f"{len(snapshot.window)} windows", "ok")
        self._set_footer(f"快照 #{snapshot_id} · {snapshot.created_at}")

    def refresh_snapshot(self) -> None:
        def work():
            store = self._store()
            try:
                record = store.latest_snapshot()
                if record is None:
                    return None
                return record, store.get_tokens(record.id)
            finally:
                store.close()

        def apply(data) -> None:
            if data is None:
                self._log("还没有快照，请先采集桌面。", "warn")
                return
            record, tokens = data
            self.current_snapshot_id = record.id
            self._fill_tokens(tokens, record.text)
            self.stat_snapshot.set(f"snapshot #{record.id}")
            self.stat_tokens.set(f"{len(tokens)} tokens")
            self.stat_windows.set(f"{len(record.window)} windows")
            self.stat_dropped.set(f"dropped {record.stats.get('dropped', 0)}")
            self._set_footer(f"快照 #{record.id} · {record.created_at}")

        self.run_task("读取最近快照…", work, apply)

    def _fill_tokens(self, tokens: list[Any], text: str) -> None:
        self.tokens = tokens
        self.token_tree.delete(*self.token_tree.get_children())
        for index, token in enumerate(tokens[:1200]):
            self.token_tree.insert("", "end", iid=str(index), values=(
                token.order, token.id, token.name, token.ctype,
                ",".join(str(v) for v in token.rect),
            ))
        _set_text(self.token_text, text)
        _set_text(self.detail_text, "选择左侧组件查看详情。")

    def _on_token_select(self, _event=None) -> None:
        selection = self.token_tree.selection()
        if not selection:
            return
        try:
            token = self.tokens[int(selection[0])]
        except (ValueError, IndexError):
            return
        relations = ";".join(f"{k}={v}" for k, v in token.relations.items())
        detail = (
            f"ID        {token.id}\n"
            f"组件名    {token.name}\n"
            f"类型      {token.ctype}\n"
            f"坐标      x={token.rect[0]}  y={token.rect[1]}  "
            f"w={token.rect[2]}  h={token.rect[3]}\n"
            f"中心点    {token.center[0]}, {token.center[1]}\n"
            f"关联      {relations}\n"
        )
        _set_text(self.detail_text, detail)

    # -------------------------------------------------------------- instruction
    def _view_instruction(self, view: ttk.Frame) -> None:
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(1, weight=3)
        view.grid_rowconfigure(3, weight=2)

        card = self._card(view)
        card.grid(row=0, column=0, sticky="ew")
        inner = tk.Frame(card, bg=C["card"])
        inner.pack(fill="x", padx=12, pady=10)

        row = tk.Frame(inner, bg=C["card"])
        row.pack(fill="x")
        tk.Label(row, text="指令", bg=C["card"], fg=C["muted"],
                 font=(FONT, 9)).pack(side="left")
        self.instruction_var = tk.StringVar()
        self.instruction_box = ttk.Combobox(row, textvariable=self.instruction_var, width=64)
        self.instruction_box.pack(side="left", padx=8, fill="x", expand=True)
        self.instruction_box.bind("<Return>", lambda _e: self.do_plan())
        self.instruction_box.bind("<Control-Return>", lambda _e: self.do_plan())

        buttons = tk.Frame(inner, bg=C["card"])
        buttons.pack(fill="x", pady=(10, 0))
        plan_button = ttk.Button(buttons, text="生成计划", command=self.do_plan)
        plan_button.pack(side="left")
        self.buttons.append(plan_button)
        dry_button = ttk.Button(buttons, text="预演（不操作）", command=lambda: self.do_act(dry_run=True))
        dry_button.pack(side="left", padx=8)
        self.buttons.append(dry_button)
        self.execute_button = ttk.Button(buttons, text="执行", style="Danger.TButton",
                                         command=lambda: self.do_act(dry_run=False),
                                         state="disabled")
        self.execute_button.pack(side="left")
        self.allow_execute = tk.BooleanVar(value=False)
        tk.Checkbutton(buttons, text="我确认执行会操作桌面元素", variable=self.allow_execute,
                       bg=C["card"], fg=C["muted"], activebackground=C["card"],
                       font=(FONT, 9), command=self._refresh_button_state).pack(side="left", padx=12)
        tk.Label(buttons, text="示例：点击七 · 在文本编辑器输入你好 · 按键回车",
                 bg=C["card"], fg=C["muted"], font=(FONT, 8)).pack(side="right")

        panes = ttk.Panedwindow(view, orient="horizontal")
        panes.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        self.instruction_panes = panes
        left = self._card(panes)
        panes.add(left, weight=2)
        self.plan_tree = ttk.Treeview(left, columns=("no", "op", "target", "value", "score"),
                                      show="headings", height=8)
        for column, title, width in (
            ("no", "#", 36), ("op", "动作", 76), ("target", "目标", 150),
            ("value", "值", 110), ("score", "匹配", 56),
        ):
            self.plan_tree.heading(column, text=title)
            self.plan_tree.column(column, width=width, stretch=column == "target",
                                  anchor="w" if column in ("target", "value") else "center")
        plan_y = ttk.Scrollbar(left, orient="vertical", command=self.plan_tree.yview)
        plan_x = ttk.Scrollbar(left, orient="horizontal", command=self.plan_tree.xview)
        self.plan_tree.configure(yscrollcommand=plan_y.set, xscrollcommand=plan_x.set)
        plan_x.pack(side="bottom", fill="x")
        plan_y.pack(side="right", fill="y")
        self.plan_tree.pack(side="left", fill="both", expand=True, padx=2, pady=2)

        right = self._card(panes)
        panes.add(right, weight=3)
        header = tk.Frame(right, bg=C["card"])
        header.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(header, text="IR（时序指令）", bg=C["card"], fg=C["muted"],
                 font=(FONT, 9)).pack(side="left")
        ir_frame, self.ir_text = _text_box(right, wrap="none")
        ir_frame.pack(fill="both", expand=True, padx=2, pady=2)

        tk.Label(view, text="执行日志", bg=C["bg"], fg=C["muted"],
                 font=(FONT, 9)).grid(row=2, column=0, sticky="w")
        log_card = self._card(view)
        log_card.grid(row=3, column=0, sticky="nsew")
        log_frame, self.log_text = _text_box(log_card, mono=True)
        log_frame.pack(fill="both", expand=True, padx=2, pady=2)
        self.log_text.configure(state="normal")

    def _instruction(self) -> str | None:
        text = self.instruction_var.get().strip()
        if not text:
            messagebox.showwarning("缺少指令", "请先输入一条指令，例如：点击七")
            return None
        history = list(self.instruction_box.cget("values"))
        if text in history:
            history.remove(text)
        history.insert(0, text)
        self.instruction_box.configure(values=history[:10])
        return text

    def do_plan(self) -> None:
        text = self._instruction()
        if not text:
            return
        settings = self.settings
        window = self.window_var.get().strip() or None
        fixture = self.fixture

        def work():
            from .agent import build_plan_only

            return build_plan_only(text, settings, window=window, fixture=fixture)

        self.run_task("正在生成计划…", work, self._apply_plan)

    def _apply_plan(self, result: dict[str, Any]) -> None:
        self.plan_tree.delete(*self.plan_tree.get_children())
        steps = result["plan"]["steps"]
        for index, step in enumerate(steps, start=1):
            self.plan_tree.insert("", "end", values=(
                index, step.get("op", ""), step.get("token_name") or step.get("token_id") or "-",
                step.get("value", ""), step.get("score", ""),
            ))
        _set_text(self.ir_text, json.dumps(result["ir"], ensure_ascii=False, indent=2))
        self._log(f"计划 {result['trace_id']}：{len(steps)} 步，snapshot #{result['snapshot_id']}", "ok")
        self._set_footer(f"计划已生成 · {len(steps)} 步 · 未执行")

    def do_act(self, dry_run: bool) -> None:
        text = self._instruction()
        if not text:
            return
        if not dry_run and not self.allow_execute.get():
            messagebox.showwarning("未授权执行", "请先勾选“我确认执行会操作桌面元素”。")
            return
        settings = self.settings
        window = self.window_var.get().strip() or None
        fixture = self.fixture

        def work():
            from .agent import run_act

            return run_act(text, settings, window=window, dry_run=dry_run,
                           fixture=fixture, inproc=True)

        self.run_task("预演中…" if dry_run else "正在执行…", work, self._apply_act)

    def _apply_act(self, result: dict[str, Any]) -> None:
        if result.get("plan"):
            self._apply_plan({
                "trace_id": result["trace_id"],
                "snapshot_id": result["snapshot_id"],
                "plan": result["plan"],
                "ir": result["ir"],
            })
        self._log(f"trace {result['trace_id']} → {result.get('status')}", 
                  "ok" if result.get("ok") else "err")
        for item in result.get("results", []):
            mark = "ok" if item.get("ok") else "FAIL"
            line = f"  [{mark}] {item.get('index')}. {item.get('op')} ({item.get('ms')} ms)"
            if item.get("error"):
                line += f"  {item['error']}"
            self._log(line, "ok" if item.get("ok") else "err")
        if result.get("dry_run"):
            self._log(f"预演完成：{result['tokens']} tokens，未操作桌面。", "muted")
            self._set_footer("预演完成 · 未操作桌面")
        elif result.get("ok"):
            self._set_footer(f"执行完成 · {len(result.get('results', []))} 步")
        else:
            self._set_footer(f"执行失败 · {result.get('error', '')}")

    # ----------------------------------------------------------------- records
    def _view_records(self, view: ttk.Frame) -> None:
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(1, weight=3)
        view.grid_rowconfigure(3, weight=2)

        toolbar = self._card(view)
        toolbar.grid(row=0, column=0, sticky="ew")
        inner = tk.Frame(toolbar, bg=C["card"])
        inner.pack(fill="x", padx=12, pady=8)
        refresh = ttk.Button(inner, text="刷新记录", command=self.refresh_records)
        refresh.pack(side="left")
        self.buttons.append(refresh)
        self.records_label = tk.StringVar(value="0 条记录")
        tk.Label(inner, textvariable=self.records_label, bg=C["card"], fg=C["muted"],
                 font=(FONT, 9)).pack(side="left", padx=12)

        tree_card = self._card(view)
        tree_card.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        self.record_tree = ttk.Treeview(tree_card, columns=("time", "status", "trace", "snapshot", "instruction"),
                                        show="headings", selectmode="browse")
        for column, title, width in (
            ("time", "时间", 150), ("status", "状态", 80), ("trace", "trace", 170),
            ("snapshot", "快照", 70), ("instruction", "指令", 420),
        ):
            self.record_tree.heading(column, text=title)
            self.record_tree.column(column, width=width, anchor="w")
        scroll = ttk.Scrollbar(tree_card, orient="vertical", command=self.record_tree.yview)
        self.record_tree.configure(yscrollcommand=scroll.set)
        self.record_tree.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        scroll.pack(side="right", fill="y")
        self.record_tree.bind("<<TreeviewSelect>>", self._on_record_select)

        tk.Label(view, text="详情", bg=C["bg"], fg=C["muted"],
                 font=(FONT, 9)).grid(row=2, column=0, sticky="w")
        detail_card = self._card(view)
        detail_card.grid(row=3, column=0, sticky="nsew")
        detail_frame, self.record_detail = _text_box(detail_card, wrap="none")
        detail_frame.pack(fill="both", expand=True, padx=2, pady=2)

    def refresh_records(self) -> None:
        def work():
            store = self._store()
            try:
                return store.list_actions(80)
            finally:
                store.close()

        self.run_task("读取运行记录…", work, self._apply_records)

    def _apply_records(self, rows: list[dict[str, Any]]) -> None:
        self.records = rows
        self.record_tree.delete(*self.record_tree.get_children())
        for index, row in enumerate(rows):
            self.record_tree.insert("", "end", iid=str(index), values=(
                row.get("created_at", ""), row.get("status", ""), row.get("trace_id", ""),
                row.get("snapshot_id") or "-", (row.get("instruction") or "")[:90],
            ))
        self.records_label.set(f"{len(rows)} 条记录")

    def _on_record_select(self, _event=None) -> None:
        selection = self.record_tree.selection()
        if not selection:
            return
        try:
            row = self.records[int(selection[0])]
        except (ValueError, IndexError):
            return
        detail = {
            "trace_id": row.get("trace_id"),
            "status": row.get("status"),
            "snapshot_id": row.get("snapshot_id"),
            "instruction": row.get("instruction"),
            "error": row.get("error"),
            "created_at": row.get("created_at"),
        }
        for key in ("plan", "ir"):
            if row.get(key):
                try:
                    detail[key] = json.loads(row[key])
                except (TypeError, ValueError):
                    detail[key] = row[key]
        _set_text(self.record_detail, json.dumps(detail, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------- input
    def _view_input(self, view: ttk.Frame) -> None:
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(4, weight=1)

        status = self._card(view)
        status.grid(row=0, column=0, sticky="ew")
        inner = tk.Frame(status, bg=C["card"])
        inner.pack(fill="x", padx=12, pady=9)
        self.input_screen_var = tk.StringVar(value="屏幕 —")
        self.input_pos_var = tk.StringVar(value="鼠标 —")
        tk.Label(inner, textvariable=self.input_screen_var, bg=C["card"], fg=C["text"],
                 font=(FONT, 9, "bold")).pack(side="left")
        tk.Label(inner, textvariable=self.input_pos_var, bg=C["card"], fg=C["muted"],
                 font=(FONT, 9)).pack(side="left", padx=16)
        ttk.Button(inner, text="刷新", command=self.refresh_input_status).pack(side="left")
        ttk.Button(inner, text="拾取鼠标位置", command=self.pick_mouse).pack(side="left", padx=8)
        self.allow_input = tk.BooleanVar(value=False)
        tk.Checkbutton(inner, text="启用虚拟指针操作", variable=self.allow_input,
                       bg=C["card"], fg=C["err"], activebackground=C["card"],
                       font=(FONT, 9), command=self._refresh_input_state).pack(side="right")

        mouse_card = self._card(view)
        mouse_card.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        mouse = tk.Frame(mouse_card, bg=C["card"])
        mouse.pack(fill="x", padx=12, pady=10)
        self.input_x = tk.StringVar(value="")
        self.input_y = tk.StringVar(value="")
        self.input_to_x = tk.StringVar(value="")
        self.input_to_y = tk.StringVar(value="")
        for label, var, width in (("X", self.input_x, 7), ("Y", self.input_y, 7),
                                  ("拖到 X", self.input_to_x, 7), ("Y", self.input_to_y, 7)):
            tk.Label(mouse, text=label, bg=C["card"], fg=C["muted"],
                     font=(FONT, 9)).pack(side="left", padx=(0, 4))
            ttk.Entry(mouse, textvariable=var, width=width).pack(side="left", padx=(0, 10))

        row = tk.Frame(mouse_card, bg=C["card"])
        row.pack(fill="x", padx=12, pady=(0, 10))
        self.input_buttons = []
        for text, command in (
            ("移动", lambda: self.do_input_move()),
            ("左键", lambda: self.do_input_click("left", 1)),
            ("双击", lambda: self.do_input_click("left", 2)),
            ("右键", lambda: self.do_input_click("right", 1)),
            ("拖拽", self.do_input_drag),
            ("上滚", lambda: self.do_input_scroll(2)),
            ("下滚", lambda: self.do_input_scroll(-2)),
        ):
            button = ttk.Button(row, text=text, command=command, state="disabled")
            button.pack(side="left", padx=(0, 8))
            self.input_buttons.append(button)

        key_card = self._card(view)
        key_card.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        keys = tk.Frame(key_card, bg=C["card"])
        keys.pack(fill="x", padx=12, pady=10)
        tk.Label(keys, text="按键", bg=C["card"], fg=C["muted"],
                 font=(FONT, 9)).pack(side="left")
        self.input_keys = tk.StringVar(value="")
        ttk.Entry(keys, textvariable=self.input_keys, width=24).pack(side="left", padx=8)
        for text, command in (("按下", lambda: self.do_input_key("press")),
                              ("长按 0.5s", lambda: self.do_input_key("hold"))):
            button = ttk.Button(keys, text=text, command=command, state="disabled")
            button.pack(side="left", padx=(0, 8))
            self.input_buttons.append(button)
        tk.Label(keys, text="文本", bg=C["card"], fg=C["muted"],
                 font=(FONT, 9)).pack(side="left", padx=(12, 0))
        self.input_text = tk.StringVar(value="")
        ttk.Entry(keys, textvariable=self.input_text, width=36).pack(side="left", padx=8)
        type_button = ttk.Button(keys, text="发送文本", command=self.do_input_type,
                                 state="disabled")
        type_button.pack(side="left")
        self.input_buttons.append(type_button)

        tk.Label(view, text="输入日志", bg=C["bg"], fg=C["muted"],
                 font=(FONT, 9)).grid(row=3, column=0, sticky="nw")
        log_card = self._card(view)
        log_card.grid(row=4, column=0, sticky="nsew", pady=(4, 0))
        log_frame, self.input_log = _text_box(log_card, mono=True)
        log_frame.pack(fill="both", expand=True, padx=2, pady=2)
        self.input_log.configure(state="normal")

        self.refresh_input_status()

    def _refresh_input_state(self) -> None:
        state = "normal" if self.allow_input.get() else "disabled"
        for button in getattr(self, "input_buttons", []):
            button.configure(state=state)

    def _input_log_line(self, text: str, kind: str = "info") -> None:
        colors = {"ok": C["ok"], "err": C["err"], "info": C["text"]}
        self.input_log.configure(state="normal")
        self.input_log.insert("end", text + "\n", kind)
        self.input_log.tag_configure(kind, foreground=colors.get(kind, C["text"]))
        self.input_log.see("end")
        self.input_log.configure(state="disabled")

    def refresh_input_status(self) -> None:
        try:
            from . import input as input_mod

            info = input_mod.screen_info()
            x, y = input_mod.mouse_position()
            self.input_screen_var.set(f"屏幕 {info['width']}x{info['height']} @ {info['x']},{info['y']}")
            self.input_pos_var.set(f"鼠标 {x},{y}")
        except Exception as exc:  # noqa: BLE001
            self.input_screen_var.set("屏幕不可用")
            self._input_log_line(f"读取屏幕信息失败: {exc}", "err")

    def pick_mouse(self) -> None:
        try:
            from . import input as input_mod

            x, y = input_mod.mouse_position()
            self.input_x.set(str(x))
            self.input_y.set(str(y))
            self.input_pos_var.set(f"鼠标 {x},{y}")
        except Exception as exc:  # noqa: BLE001
            self._input_log_line(f"拾取失败: {exc}", "err")

    def _input_point(self, *, allow_empty: bool = False) -> tuple[int | None, int | None]:
        raw_x = self.input_x.get().strip()
        raw_y = self.input_y.get().strip()
        if not raw_x and not raw_y and allow_empty:
            return None, None
        if not raw_x or not raw_y:
            raise ValueError("请填写 X 和 Y")
        return int(raw_x), int(raw_y)

    def _run_input(self, label: str, action) -> None:
        if not self.allow_input.get():
            self._input_log_line("请先勾选“启用虚拟指针操作”", "err")
            return
        try:
            result = action()
        except Exception as exc:  # noqa: BLE001
            self._input_log_line(f"{label}失败: {exc}", "err")
        else:
            self._input_log_line(f"{label}: {result}", "ok")
            self.refresh_input_status()

    def do_input_move(self) -> None:
        def action():
            from . import input as input_mod

            x, y = self._input_point()
            return input_mod.move(x, y, 200)

        self._run_input("移动", action)

    def do_input_click(self, button: str, clicks: int) -> None:
        def action():
            from . import input as input_mod

            x, y = self._input_point(allow_empty=True)
            return input_mod.click(x, y, button, clicks)

        self._run_input("点击", action)

    def do_input_drag(self) -> None:
        def action():
            from . import input as input_mod

            x, y = self._input_point()
            to_x = int(self.input_to_x.get().strip())
            to_y = int(self.input_to_y.get().strip())
            return input_mod.drag(x, y, to_x, to_y, "left", 500)

        self._run_input("拖拽", action)

    def do_input_scroll(self, dy: int) -> None:
        def action():
            from . import input as input_mod

            x, y = self._input_point(allow_empty=True)
            return input_mod.scroll(x, y, dy, 0)

        self._run_input("滚动", action)

    def do_input_key(self, mode: str) -> None:
        def action():
            from . import input as input_mod

            keys = self.input_keys.get().strip()
            if mode == "hold":
                return input_mod.key_hold(keys, 500)
            return input_mod.key_press(keys)

        self._run_input("按键", action)

    def do_input_type(self) -> None:
        def action():
            from . import input as input_mod

            return input_mod.type_text(self.input_text.get())

        self._run_input("输入文本", action)

    # --------------------------------------------------------------------- mcp
    def _view_mcp(self, view: ttk.Frame) -> None:
        view.grid_columnconfigure(0, weight=1)
        view.grid_columnconfigure(1, weight=1)
        view.grid_rowconfigure(0, weight=1)

        left = self._card(view)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(left, text="环境与后端", bg=C["card"], fg=C["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
        self.doctor_labels: dict[str, tk.StringVar] = {}
        for key, title in (
            ("python", "Python"), ("backend", "UIA 后端"), ("ps_uia", "PowerShell UIA"),
            ("pywinauto", "pywinauto"), ("db", "数据库"), ("home", "数据目录"),
        ):
            row = tk.Frame(left, bg=C["card"])
            row.pack(fill="x", padx=14, pady=2)
            tk.Label(row, text=title, bg=C["card"], fg=C["muted"], width=14,
                     anchor="w", font=(FONT, 9)).pack(side="left")
            var = tk.StringVar(value="—")
            tk.Label(row, textvariable=var, bg=C["card"], fg=C["text"], anchor="w",
                     justify="left", wraplength=380, font=(FONT, 9)).pack(
                side="left", fill="x", expand=True)
            self.doctor_labels[key] = var
        actions = tk.Frame(left, bg=C["card"])
        actions.pack(fill="x", padx=14, pady=(10, 12))
        doctor_button = ttk.Button(actions, text="重新检测环境", command=self.doctor)
        doctor_button.pack(side="left")
        self.buttons.append(doctor_button)
        open_button = ttk.Button(actions, text="打开数据目录", command=self.open_data_dir)
        open_button.pack(side="left", padx=8)

        right = self._card(view)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        header = tk.Frame(right, bg=C["card"])
        header.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(header, text="MCP 配置（复制到客户端）", bg=C["card"], fg=C["text"],
                 font=(FONT, 11, "bold")).pack(side="left")
        copy_button = ttk.Button(header, text="复制配置", command=self.copy_mcp)
        copy_button.pack(side="right")

        config = self.mcp_config()
        self.mcp_text = None
        frame, text = _text_box(right, wrap="word")
        frame.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        _set_text(text, config)
        self.mcp_text = text

        tk.Label(right, text="工具：desktop_scan · desktop_tokens · computer_act",
                 bg=C["card"], fg=C["muted"], font=(FONT, 8)).pack(anchor="w", padx=14, pady=(0, 10))

    def mcp_config(self) -> str:
        import sys

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            cli = exe_dir / "oacu.exe"
            command = cli if cli.is_file() else Path(sys.executable)
            return (
                "{\n"
                '  "mcpServers": {\n'
                '    "opencu": {\n'
                f'      "command": {json.dumps(str(command), ensure_ascii=False)},\n'
                '      "args": ["mcp", "serve"]\n'
                "    }\n"
                "  }\n"
                "}"
            )

        root = Path(__file__).resolve().parents[1]
        cwd = json.dumps(str(root), ensure_ascii=False)
        return (
            "{\n"
            '  "mcpServers": {\n'
            '    "opencu": {\n'
            '      "command": "python",\n'
            '      "args": ["-m", "oacu", "mcp", "serve"],\n'
            f'      "cwd": {cwd}\n'
            "    }\n"
            "  }\n"
            "}"
        )

    def copy_mcp(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.mcp_config())
        self._set_footer("MCP 配置已复制到剪贴板")
        self._log("MCP 配置已复制。", "ok")

    def open_data_dir(self) -> None:
        try:
            os.startfile(str(home_dir()))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    # ------------------------------------------------------------------ doctor
    def doctor(self) -> None:
        from .uia import backend as backend_mod

        def work():
            return backend_mod.probe()

        def apply(info: dict[str, Any]) -> None:
            self._apply_doctor(info)

        self.run_task("检测环境…", work, apply)

    def _apply_doctor(self, info: dict[str, Any]) -> None:
        import platform
        import sys

        self.doctor_labels["python"].set(f"{platform.python_version()} · {platform.platform()}")
        self.doctor_labels["backend"].set(info.get("backend") or "none")
        self.doctor_labels["ps_uia"].set("可用" if info.get("ps_uia") else "不可用")
        self.doctor_labels["pywinauto"].set("已安装" if info.get("pywinauto") else "未安装（使用 PowerShell 桥）")
        self.doctor_labels["db"].set(str(self.settings.db))
        self.doctor_labels["home"].set(str(home_dir()))
        ok = bool(info.get("ps_uia") or info.get("pywinauto"))
        self._set_chip("环境正常" if ok else "后端不可用", "ok" if ok else "err")
        if not ok:
            self._log("UIA 后端不可用：请检查 PowerShell 5.1。", "err")

    def _startup_load(self) -> None:
        from .uia import backend as backend_mod

        settings = self.settings

        def work():
            info = backend_mod.probe()
            store = Store(settings.db)
            try:
                rows = store.list_actions(80)
                record = store.latest_snapshot()
                tokens = store.get_tokens(record.id) if record else []
                text = record.text if record else ""
            finally:
                store.close()
            return info, rows, record, tokens, text

        def apply(data) -> None:
            info, rows, record, tokens, text = data
            self._apply_doctor(info)
            self._apply_records(rows)
            if record is not None:
                self.current_snapshot_id = record.id
                self._fill_tokens(tokens, text)
                self.stat_snapshot.set(f"snapshot #{record.id}")
                self.stat_tokens.set(f"{len(tokens)} tokens")
                self.stat_windows.set(f"{len(record.window)} windows")
                self.stat_dropped.set(f"dropped {record.stats.get('dropped', 0)}")
                self._set_footer(f"快照 #{record.id} · {record.created_at}")
            else:
                self._set_footer("尚无快照 · 点击「采集桌面」开始")

        self.run_task("加载环境…", work, apply)


def _self_test(root: tk.Tk, settings: Settings, fixture: str | None) -> int:
    checks: list[bool] = []
    app = GuiApp(root, settings, fixture)
    checks.append(bool(root.winfo_exists()))

    fixture = fixture or str(Path(__file__).resolve().parents[1] / "tools" / "fixture_desktop.json")
    snapshot = capture_snapshot(backend="fake", fixture=fixture)
    store = Store(settings.db)
    try:
        snapshot_id = store.save_snapshot(snapshot)
    finally:
        store.close()
    app._apply_snapshot((snapshot_id, snapshot))
    root.update_idletasks()
    checks.append(len(app.tokens) == 7)

    from .agent import build_plan_only

    result = build_plan_only("点击七", settings, fixture=fixture)
    app._apply_plan(result)
    checks.append(result["plan"]["steps"][0]["token_id"] == "t0006"
                  and len(app.plan_tree.get_children()) == 1)

    store = Store(settings.db)
    try:
        rows = store.list_actions(10)
    finally:
        store.close()
    app._apply_records(rows)
    checks.append(len(rows) >= 1 and len(app.record_tree.get_children()) >= 1)

    checks.append("mcpServers" in app.mcp_text.get("1.0", "end"))

    root.destroy()
    passed = sum(1 for check in checks if check)
    print(f"gui {passed}/{len(checks)}")
    return 0 if passed == len(checks) else 1


def run_gui(settings: Settings, fixture: str | None = None, self_test: bool = False,
            start_tab: int = 0) -> int:
    _dpi()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise EnvUnavailable("无法创建图形界面（Tk 不可用或没有桌面会话）", detail=str(exc)) from exc

    if self_test:
        root.withdraw()
        tmpdir = tempfile.TemporaryDirectory(prefix="oacu-gui-")
        os.environ["OACU_HOME"] = tmpdir.name
        settings = Settings(
            json=True,
            db=Path(tmpdir.name) / "gui.db",
            backend="fake",
            timeout=settings.timeout,
            verbose=False,
            config=dict(DEFAULTS),
        )
        try:
            return _self_test(root, settings, fixture)
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass
            tmpdir.cleanup()

    root.update_idletasks()
    width, height = 1220, 780
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2 - 20)
    root.geometry(f"{width}x{height}+{x}+{y}")
    GuiApp(root, settings, fixture, start_tab=start_tab)
    root.mainloop()
    return 0
