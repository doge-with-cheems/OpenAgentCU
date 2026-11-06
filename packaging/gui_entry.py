"""PyInstaller entry point for the GUI executable (OpenAgentCU.exe)."""

import sys

from oacu.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["gui", *sys.argv[1:]]))
