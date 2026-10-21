"""月历选择器。"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from tkinter import ttk
from typing import Optional

from .common import FONT, FONT_BOLD


class CalendarDialog:
    """极简月历选择器（纯 tkinter，不引第三方依赖）。点日期即选定并关闭。"""

    WEEK = ("一", "二", "三", "四", "五", "六", "日")

    @staticmethod
    def ask(parent, initial=None):
        import calendar

        win = tk.Toplevel(parent)
        win.title("选择日期")
        win.transient(parent)
        win.grab_set()
        win.resizable(False, False)
        result = {"v": None}
        ref = initial or date.today()
        state = {"y": ref.year, "m": ref.month}

        head = ttk.Frame(win)
        head.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(head, text="◀", width=3, command=lambda: shift(-1)).pack(side="left")
        lbl = ttk.Label(head, text="", font=FONT_BOLD, anchor="center", width=16)
        lbl.pack(side="left", expand=True)
        ttk.Button(head, text="▶", width=3, command=lambda: shift(1)).pack(side="left")

        grid = ttk.Frame(win)
        grid.pack(padx=10, pady=2)
        foot = ttk.Frame(win)
        foot.pack(fill="x", padx=10, pady=(6, 10))

        def pick(d):
            result["v"] = date(state["y"], state["m"], d)
            win.destroy()

        def shift(delta):
            m, y = state["m"] + delta, state["y"]
            if m < 1:
                m, y = 12, y - 1
            elif m > 12:
                m, y = 1, y + 1
            state["m"], state["y"] = m, y
            render()

        def render():
            for w in grid.winfo_children():
                w.destroy()
            lbl.configure(text=f"{state['y']} 年 {state['m']} 月")
            for c, wd in enumerate(CalendarDialog.WEEK):
                ttk.Label(grid, text=wd, width=4, anchor="center", style="Hint.TLabel").grid(row=0, column=c)
            today = date.today()
            weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(state["y"], state["m"])
            for r, week in enumerate(weeks, 1):
                for c, d in enumerate(week):
                    if d == 0:
                        continue
                    is_today = today.year == state["y"] and today.month == state["m"] and today.day == d
                    ttk.Button(
                        grid, text=(f"{d}·" if is_today else str(d)), width=4,
                        command=lambda dd=d: pick(dd),
                    ).grid(row=r, column=c, padx=1, pady=1)

        ttk.Button(foot, text="今天", width=6, command=lambda: (result.update(v=date.today()), win.destroy())).pack(side="left")
        ttk.Button(foot, text="取消", width=6, command=win.destroy).pack(side="right")
        render()
        win.bind("<Escape>", lambda e: win.destroy())
        parent.wait_window(win)
        return result["v"]

