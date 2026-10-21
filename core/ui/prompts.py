"""三个轻量输入框：单行输入、多行文本、按键。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional

from .common import FONT


class SimplePrompt:
    @staticmethod
    def ask(parent, title: str, label: str, initial: str = "", allow_empty: bool = False) -> Optional[str]:
        win = tk.Toplevel(parent)
        win.title(title)
        win.transient(parent)
        win.grab_set()
        win.resizable(False, False)
        result: Dict[str, Optional[str]] = {"v": None}
        ttk.Label(win, text=label).pack(anchor="w", padx=12, pady=(12, 4))
        var = tk.StringVar(value=initial)
        e = ttk.Entry(win, textvariable=var, width=46)
        e.pack(padx=12)
        e.focus_set()
        e.select_range(0, "end")

        def ok(_=None):
            v = var.get()
            if not v.strip() and not allow_empty:
                return
            result["v"] = v
            win.destroy()

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=10)
        ttk.Button(bar, text="确定", width=8, command=ok).pack(side="right")
        ttk.Button(bar, text="取消", width=8, command=win.destroy).pack(side="right", padx=6)
        win.bind("<Return>", ok)
        win.bind("<Escape>", lambda e: win.destroy())
        parent.wait_window(win)
        return result["v"]


class TextDialog:
    @staticmethod
    def ask(parent, title: str, label: str, initial: str = "") -> Optional[tuple]:
        win = tk.Toplevel(parent)
        win.title(title)
        win.transient(parent)
        win.grab_set()
        win.geometry("560x360")
        result: Dict[str, Optional[tuple]] = {"v": None}
        ttk.Label(win, text=label + "（支持中英文、换行）").pack(anchor="w", padx=12, pady=(12, 4))
        txt = tk.Text(win, wrap="word", font=FONT, height=10)
        txt.pack(fill="both", expand=True, padx=12)
        txt.insert("1.0", initial)
        txt.focus_set()
        var_clear = tk.BooleanVar(value=True)
        ttk.Checkbutton(win, text="输入前先 Ctrl+A 清空原有内容", variable=var_clear).pack(anchor="w", padx=12, pady=6)

        def ok():
            v = txt.get("1.0", "end-1c")
            result["v"] = (v, bool(var_clear.get()))
            win.destroy()

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(bar, text="确定", width=8, command=ok).pack(side="right")
        ttk.Button(bar, text="取消", width=8, command=win.destroy).pack(side="right", padx=6)
        win.bind("<Escape>", lambda e: win.destroy())
        parent.wait_window(win)
        return result["v"]


class KeyDialog:
    PRESETS = ["enter", "ctrl+enter", "shift+enter", "tab", "esc", "ctrl+a", "ctrl+v", "space"]

    @staticmethod
    def ask(parent, title: str, initial: str = "enter") -> Optional[str]:
        win = tk.Toplevel(parent)
        win.title(title)
        win.transient(parent)
        win.grab_set()
        win.resizable(False, False)
        result: Dict[str, Optional[str]] = {"v": None}
        ttk.Label(win, text="要发送的按键（可用 + 组合，如 ctrl+enter）").pack(anchor="w", padx=12, pady=(12, 4))
        var = tk.StringVar(value=initial)
        cmb = ttk.Combobox(win, textvariable=var, values=KeyDialog.PRESETS, width=30)
        cmb.pack(padx=12)
        cmb.focus_set()

        def ok(_=None):
            if not var.get().strip():
                return
            result["v"] = var.get().strip()
            win.destroy()

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=12, pady=10)
        ttk.Button(bar, text="确定", width=8, command=ok).pack(side="right")
        ttk.Button(bar, text="取消", width=8, command=win.destroy).pack(side="right", padx=6)
        win.bind("<Return>", ok)
        win.bind("<Escape>", lambda e: win.destroy())
        parent.wait_window(win)
        return result["v"]

