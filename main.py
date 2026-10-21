"""autocodex 入口：Codex 定时对话执行器。"""
from __future__ import annotations

import ctypes
import sys

from core import winsys

# DPI 感知必须在任何窗口创建之前设置
winsys.set_dpi_awareness()

import tkinter as tk  # noqa: E402

from core.store import Store  # noqa: E402
from core.ui import App  # noqa: E402

MUTEX_NAME = "Global\\autocodex_singleton"


def already_running() -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def main() -> int:
    if already_running():
        root = tk.Tk()
        root.withdraw()
        from tkinter import messagebox

        messagebox.showinfo("autocodex", "已经有一个 autocodex 在运行了（看右下角托盘图标）。")
        root.destroy()
        return 0

    store = Store()
    root = tk.Tk()
    App(root, store)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
