"""Standalone click-through virtual cursor overlay (Minecraft-style crosshair).

Run as its own process so Tk owns the main thread. The parent (MCP server)
writes one JSON line per command to stdin:

    {"id": 1, "x": 500, "y": 320, "ms": 900}
    {"id": 2, "hide": true}

Up to four independent pointer windows are hosted in the same process. Each
pointer keeps its own position and display deadline; unused pointers are
created lazily and normally only pointer 1 is visible.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes

import ctypes

CURSOR = "crosshair"
MAX_POINTERS = 4
SIZE = 36
CROSS_HALF = 9
CROSS_OUTLINE = 5
CROSS_WIDTH = 2
COLORKEY = "#ff00ff"
COLORKEY_REF = 0x00FF00FF
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000


def main() -> int:
    commands: "queue.Queue[dict | None]" = queue.Queue()

    def reader() -> None:
        for line in sys.stdin:
            try:
                commands.put(json.loads(line))
            except ValueError:
                continue
        commands.put(None)

    threading.Thread(target=reader, daemon=True).start()

    root = tk.Tk()
    root.overrideredirect(True)
    root.withdraw()

    user32 = ctypes.windll.user32
    set_ptr = user32.SetWindowLongPtrW
    set_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
    set_ptr.restype = ctypes.c_longlong
    get_ptr = user32.GetWindowLongPtrW
    get_ptr.argtypes = [wintypes.HWND, ctypes.c_int]
    get_ptr.restype = ctypes.c_longlong
    get_parent = user32.GetParent
    get_parent.argtypes = [wintypes.HWND]
    get_parent.restype = wintypes.HWND
    set_top = user32.SetWindowPos
    set_top.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    set_top.restype = wintypes.BOOL
    HWND_TOPMOST = wintypes.HWND(-1)
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    LWA_COLORKEY = 0x1
    set_layered = user32.SetLayeredWindowAttributes
    set_layered.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte,
                            wintypes.DWORD]
    set_layered.restype = wintypes.BOOL

    def apply_style(entry: dict) -> None:
        for target in entry["handles"]:
            style = get_ptr(target, GWL_EXSTYLE)
            set_ptr(target, GWL_EXSTYLE,
                    style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
            # Re-assert the colour key: changing the ex-style resets the layer attrs.
            set_layered(target, COLORKEY_REF, 255, LWA_COLORKEY)
            set_top(target, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)

    def create(pointer_id: int) -> dict:
        window = tk.Toplevel(root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-transparentcolor", COLORKEY)
        window.configure(bg=COLORKEY)
        canvas = tk.Canvas(window, width=SIZE, height=SIZE, bg=COLORKEY,
                           highlightthickness=0)
        canvas.pack()
        center = SIZE // 2
        # Minecraft-style crosshair: white plus with a dark outline.
        for color, width in (("#111827", CROSS_OUTLINE), ("#ffffff", CROSS_WIDTH)):
            canvas.create_line(center - CROSS_HALF, center,
                               center + CROSS_HALF, center,
                               fill=color, width=width, capstyle="butt")
            canvas.create_line(center, center - CROSS_HALF,
                               center, center + CROSS_HALF,
                               fill=color, width=width, capstyle="butt")
        window.withdraw()
        window.update_idletasks()

        handle = int(window.winfo_id())
        handles = [handle]
        parent = get_parent(wintypes.HWND(handle))
        if parent:
            handles.append(int(parent))
        entry = {"window": window, "until": 0.0, "handles": handles}
        windows[pointer_id] = entry
        apply_style(entry)
        return entry

    windows: dict[int, dict] = {}

    def show(pointer_id: int, x: int, y: int, ms: int) -> None:
        entry = windows.get(pointer_id) or create(pointer_id)
        window = entry["window"]
        offset = SIZE // 2
        window.geometry(f"{SIZE}x{SIZE}+{x - offset}+{y - offset}")
        window.deiconify()
        window.lift()
        window.attributes("-topmost", True)
        window.update_idletasks()
        entry["until"] = time.monotonic() + max(0, ms) / 1000.0
        apply_style(entry)

    def hide(pointer_id: int) -> None:
        entry = windows.get(pointer_id)
        if entry is None:
            return
        entry["window"].withdraw()
        entry["until"] = 0.0

    closing = False

    def poll() -> None:
        nonlocal closing
        try:
            while True:
                item = commands.get_nowait()
                if item is None:
                    # Parent exited. Keep cursors up until their holds expire so
                    # one-shot CLI commands still show them.
                    if any(entry["until"] for entry in windows.values()):
                        closing = True
                    else:
                        root.destroy()
                        return
                    break
                try:
                    pointer_id = int(item.get("id", 1))
                except (TypeError, ValueError):
                    continue
                if not 1 <= pointer_id <= MAX_POINTERS:
                    continue
                if item.get("hide"):
                    hide(pointer_id)
                    continue
                try:
                    x = int(item.get("x", 0))
                    y = int(item.get("y", 0))
                    ms = int(item.get("ms", 900))
                except (TypeError, ValueError):
                    continue
                show(pointer_id, x, y, ms)
        except queue.Empty:
            pass

        now = time.monotonic()
        expired = False
        for entry in windows.values():
            if entry["until"] and now > entry["until"]:
                entry["window"].withdraw()
                entry["until"] = 0.0
                expired = True
        if expired:
            root.update_idletasks()
        if closing and not any(entry["until"] for entry in windows.values()):
            root.destroy()
            return
        root.after(30, poll)

    root.after(30, poll)
    try:
        root.mainloop()
    except tk.TclError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
