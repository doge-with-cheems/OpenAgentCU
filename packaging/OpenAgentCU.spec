# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one folder, two executables sharing the runtime."""

import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))
PACKAGING = os.path.join(ROOT, "packaging")
TOOLS = os.path.join(ROOT, "tools")
ICON = os.path.join(PACKAGING, "OpenAgentCU.ico")
VERSION = os.path.join(PACKAGING, "version_info.txt")

HIDDEN = [
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "sqlite3",
    "oacu.gui",
    "oacu.mcp.server",
    "oacu.mcp.protocol",
]
HIDDEN += collect_submodules("oacu")

DATAS = [(TOOLS, "tools")]

a_cli = Analysis(
    [os.path.join(PACKAGING, "cli_entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest"],
    noarchive=False,
)

a_gui = Analysis(
    [os.path.join(PACKAGING, "gui_entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest"],
    noarchive=False,
)

pyz_cli = PYZ(a_cli.pure)
pyz_gui = PYZ(a_gui.pure)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="oacu",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=ICON,
    version=VERSION,
)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="OpenAgentCU",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=ICON,
    version=VERSION,
)

coll = COLLECT(
    exe_cli,
    a_cli.binaries,
    a_cli.datas,
    exe_gui,
    a_gui.binaries,
    a_gui.datas,
    strip=False,
    upx=False,
    name="OpenAgentCU",
)
