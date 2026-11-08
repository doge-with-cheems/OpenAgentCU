"""Standalone click-through virtual cursor overlay (▣).

Run as its own process so Tk owns the main thread. The parent (MCP server)
writes one JSON line per show command to stdin:

    {"x": 500, "y": 320, "ms": 900}
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

CURSOR = "▣"
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
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", "#ff00ff")
    root.configure(bg="#ff00ff")
    canvas = tk.Canvas(root, width=72, height=72, bg="#ff00ff", highlightthickness=0)
    canvas.pack()
    font = ("Segoe UI Symbol", 44)
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1),
                   (-1, 0), (1, 0), (0, -1), (0, 1)):
        canvas.create_text(36 + dx, 36 + dy, text=CURSOR, font=font, fill="#ffffff")
    canvas.create_text(36, 36, text=CURSOR, font=font, fill="#0d9488")
    root.withdraw()
    root.update_idletasks()

    user32 = ctypes.windll.user32
    handle = int(root.winfo_id())
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

    def apply_style() -> None:
        targets = [handle]
        parent = get_parent(wintypes.HWND(handle))
        if parent:
            targets.append(int(parent))
        for target in targets:
            style = get_ptr(target, GWL_EXSTYLE)
            set_ptr(target, GWL_EXSTYLE,
                    style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
            # Re-assert the colour key: changing the ex-style resets the layer attrs.
            set_layered(target, 0x00FF00FF, 255, LWA_COLORKEY)
            set_top(target, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)

    apply_style()

    visible_until = 0.0
    closing = False

    def poll() -> None:
        nonlocal visible_until, closing
        changed = False
        try:
            while True:
                item = commands.get_nowait()
                if item is None:
                    # Parent exited. Keep the cursor up until its hold expires so
                    # one-shot CLI commands still show it.
                    if visible_until and time.monotonic() < visible_until:
                        closing = True
                        break
                    root.destroy()
                    return
                x = int(item.get("x", 0))
                y = int(item.get("y", 0))
                ms = int(item.get("ms", 900))
                root.geometry(f"72x72+{x - 36}+{y - 36}")
                root.deiconify()
                root.lift()
                root.attributes("-topmost", True)
                visible_until = time.monotonic() + ms / 1000.0
                changed = True
        except queue.Empty:
            pass
        if visible_until and time.monotonic() > visible_until:
            root.withdraw()
            visible_until = 0.0
            changed = True
            if closing:
                root.destroy()
                return
        if changed:
            root.update_idletasks()
            apply_style()
        root.after(30, poll)

    root.after(30, poll)
    try:
        root.mainloop()
    except tk.TclError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
