"""计划对话框：什么时候跑 + 用哪套动作。"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from .. import trigger as trigger_mod
from ..store import parse_dt

from .calendar_dialog import CalendarDialog
from .common import FONT


class PlanDialog:
    """计划编辑器：触发方式（定点 / 间隔 / 一次）+ 动作序列。

    设计原则：用户点进来只需要回答一个问题「什么时候跑」，
    所以不做结束条件，也不摆「最多执行 N 次」这种和每天执行自相矛盾的选项。
    底部那行说明是实时的，改任何一个时刻 / 星期都会立刻重算「到底会怎么跑」。
    """

    @staticmethod
    def ask(parent, seq_map: Dict[str, str], default_seq_id: str = "", plan: Optional[Dict[str, Any]] = None):
        editing = plan is not None
        win = tk.Toplevel(parent)
        win.title("编辑计划" if editing else "新建计划")
        win.transient(parent)
        win.grab_set()
        win.resizable(False, False)
        result: Dict[str, Optional[Dict[str, Any]]] = {"v": None}

        plan = plan or {}
        trig = trigger_mod.normalize(plan.get("trigger")) or {
            "kind": "calendar", "times": ["09:00"], "days": []
        }

        # 星期按钮用方形开关：vista 主题的 Toolbutton 平时不画边框、看不出能点，
        # 所以用经典 Checkbutton 的 indicatoron=False 做凸起按钮。

        body = ttk.Frame(win)
        body.pack(fill="both", padx=16, pady=14)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="名称").grid(row=0, column=0, sticky="w", pady=(0, 10), padx=(0, 10))
        var_name = tk.StringVar(value=plan.get("name") or "")
        ttk.Entry(body, textvariable=var_name, width=32).grid(row=0, column=1, sticky="w", pady=(0, 10))

        ttk.Label(body, text="触发方式").grid(row=1, column=0, sticky="w", pady=(0, 10), padx=(0, 10))
        var_kind = tk.StringVar(value=trig["kind"])
        kbar = ttk.Frame(body)
        kbar.grid(row=1, column=1, sticky="w", pady=(0, 10))
        for txt, val in (("定点", "calendar"), ("间隔", "interval"), ("只跑一次", "once")):
            ttk.Radiobutton(kbar, text=txt, variable=var_kind, value=val,
                            command=lambda: render()).pack(side="left", padx=(0, 18))

        dyn = ttk.LabelFrame(body, text=" 什么时间运行 ")
        dyn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        # ---- 状态变量：切换触发方式时控件会重建，值保留在这里 ----
        once_at = (parse_dt(trig.get("at", "")) if trig["kind"] == "once" else None) or \
            (datetime.now() + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
        var_date = tk.StringVar(value=once_at.strftime("%Y-%m-%d"))
        var_hh = tk.StringVar(value=once_at.strftime("%H"))
        var_mm = tk.StringVar(value=once_at.strftime("%M"))

        init_times: List[str] = list(trig.get("times") or ["09:00"])
        picked_days = set(trig.get("days") or [])
        var_day = {d: tk.BooleanVar(value=d in picked_days) for d in range(1, 8)}
        time_rows: List[Dict[str, Any]] = []

        var_every = tk.StringVar(value=str(trig.get("every") or 3))
        var_unit = tk.StringVar(value=trig.get("unit") or "hour")
        anchor = parse_dt(trig.get("anchor", "")) or datetime.now().replace(second=0, microsecond=0)
        var_anchor = tk.StringVar(value=anchor.strftime(trigger_mod.DT_FMT))

        var_sum = tk.StringVar(value="")

        def refresh_summary() -> None:
            """把当前设置翻译成一句人话：这么设到底会怎么跑。"""
            kind = var_kind.get()

            if kind == "once":
                var_sum.set(f"{var_date.get()} {var_hh.get()}:{var_mm.get()} 跑一次，之后不再运行。")
                return

            if kind == "interval":
                try:
                    every = int(float(var_every.get()))
                except Exception:
                    every = 0
                if every <= 0:
                    var_sum.set("间隔要填大于 0 的整数。")
                    return
                raw = {"kind": "interval", "every": every, "unit": var_unit.get(),
                       "anchor": var_anchor.get().strip()}
                nf = trigger_mod.next_fire(raw, datetime.now())
                if not nf:
                    var_sum.set("起点格式应形如 2026-10-21 15:00。")
                    return
                unit = trigger_mod.UNITS[var_unit.get()]
                var_sum.set(f"从 {nf:%m-%d %H:%M} 起，每 {every} {unit}跑一次，一直跑下去。")
                return

            times: List[str] = []
            bad = False
            for item in time_rows:
                raw_text = item["var"].get().strip()
                hm = trigger_mod.parse_time(raw_text)
                if hm:
                    if hm not in times:
                        times.append(hm)
                elif raw_text:
                    bad = True
            if bad:
                var_sum.set("时刻要写成 09:00 这种格式。")
                return
            if not times:
                var_sum.set("至少填一个时刻，比如 09:00。")
                return
            times.sort()
            days = [d for d in range(1, 8) if var_day[d].get()]
            when = "每天" if not days else "每周" + "、".join(trigger_mod.WEEK[d - 1] for d in days) + "的"
            if len(times) == 1:
                var_sum.set(f"{when} {times[0]} 跑一次。")
            else:
                var_sum.set(f"{when} {'、'.join(times)} 各跑一次，一天 {len(times)} 次。")

        def pick_date() -> None:
            cur = parse_dt(f"{var_date.get()} 00:00")
            picked = CalendarDialog.ask(win, cur.date() if cur else None)
            if picked:
                var_date.set(picked.strftime("%Y-%m-%d"))
                refresh_summary()

        # ---- 定点：时刻行 + 星期开关 ----
        def build_calendar() -> None:
            grid = ttk.Frame(dyn)
            grid.pack(fill="x", padx=12, pady=(10, 10))
            grid.columnconfigure(1, weight=1)

            ttk.Label(grid, text="时刻").grid(row=0, column=0, sticky="nw", pady=(3, 0), padx=(0, 10))
            holder = ttk.Frame(grid)
            holder.grid(row=0, column=1, sticky="ew")

            def next_slot() -> str:
                used = [trigger_mod.parse_time(it["var"].get()) for it in time_rows]
                used = [u for u in used if u]
                if not used:
                    return "09:00"
                return f"{(max(int(u[:2]) for u in used) + 1) % 24:02d}:00"

            def add_row(value: str = "") -> None:
                row = ttk.Frame(holder)
                row.pack(fill="x", pady=1)
                var = tk.StringVar(value=value)
                ttk.Entry(row, textvariable=var, width=8).pack(side="left")
                item: Dict[str, Any] = {"var": var, "frame": row}

                def drop() -> None:
                    if item in time_rows:
                        time_rows.remove(item)
                    row.destroy()
                    refresh_summary()

                ttk.Button(row, text="×", width=2, command=drop).pack(side="left", padx=(4, 0))
                var.trace_add("write", lambda *a: refresh_summary())
                time_rows.append(item)
                refresh_summary()   # 新行带了初始值，trace 不会为初始值触发

            for t in init_times:
                add_row(t)

            ttk.Button(holder, text="+ 再加一个时刻", width=14,
                       command=lambda: add_row(next_slot())).pack(anchor="w", pady=(4, 0))

            ttk.Label(grid, text="星期").grid(row=1, column=0, sticky="w", pady=(14, 0), padx=(0, 10))
            daybar = ttk.Frame(grid)
            daybar.grid(row=1, column=1, sticky="w", pady=(14, 0))
            for d in range(1, 8):
                ttk.Checkbutton(
                    daybar, text=trigger_mod.WEEK[d - 1], variable=var_day[d],
                    style="Toggle.TButton", width=3, command=refresh_summary,
                ).pack(side="left", padx=(0, 3))
            ttk.Label(daybar, text="不选 = 每天", style="Hint.TLabel").pack(side="left", padx=(9, 0))

            ttk.Separator(grid, orient="horizontal").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 8))
            ttk.Label(grid, textvariable=var_sum, wraplength=430,
                      justify="left").grid(row=3, column=0, columnspan=2, sticky="w")

        # ---- 只跑一次：日期 + 时刻 ----
        def build_once() -> None:
            grid = ttk.Frame(dyn)
            grid.pack(fill="x", padx=12, pady=(10, 10))

            row = ttk.Frame(grid)
            row.pack(fill="x")
            ttk.Label(row, text="日期").pack(side="left")
            ttk.Entry(row, textvariable=var_date, width=11, state="readonly").pack(side="left", padx=(8, 3))
            ttk.Button(row, text="选", width=3, command=pick_date).pack(side="left")

            ttk.Label(row, text="时间").pack(side="left", padx=(16, 0))
            cb_h = ttk.Combobox(row, textvariable=var_hh, width=3, state="readonly",
                                values=[f"{h:02d}" for h in range(24)])
            cb_h.pack(side="left", padx=(8, 0))
            cb_h.bind("<<ComboboxSelected>>", lambda e: refresh_summary())
            ttk.Label(row, text=":").pack(side="left")
            cb_m = ttk.Combobox(row, textvariable=var_mm, width=3, state="readonly",
                                values=[f"{m:02d}" for m in range(60)])
            cb_m.pack(side="left")
            cb_m.bind("<<ComboboxSelected>>", lambda e: refresh_summary())

            ttk.Separator(grid, orient="horizontal").pack(fill="x", pady=(12, 8))
            ttk.Label(grid, textvariable=var_sum, wraplength=430,
                      justify="left").pack(anchor="w")

        # ---- 间隔：每 N 小时/天 ----
        def build_interval() -> None:
            grid = ttk.Frame(dyn)
            grid.pack(fill="x", padx=12, pady=(10, 10))

            row = ttk.Frame(grid)
            row.pack(fill="x")
            ttk.Label(row, text="每隔").pack(side="left")
            spin = ttk.Spinbox(row, from_=1, to=999, width=5, textvariable=var_every,
                               command=refresh_summary)
            spin.pack(side="left", padx=(8, 4))
            spin.bind("<KeyRelease>", lambda e: refresh_summary())
            unit_box = ttk.Combobox(row, width=5, state="readonly", values=["小时", "天"])
            unit_box.set(trigger_mod.UNITS[var_unit.get()])
            unit_box.pack(side="left")
            unit_box.bind("<<ComboboxSelected>>", lambda e: (
                var_unit.set("day" if unit_box.get() == "天" else "hour"), refresh_summary()))

            row2 = ttk.Frame(grid)
            row2.pack(fill="x", pady=(10, 0))
            ttk.Label(row2, text="起点").pack(side="left")
            ent = ttk.Entry(row2, textvariable=var_anchor, width=17)
            ent.pack(side="left", padx=(8, 0))
            ent.bind("<KeyRelease>", lambda e: refresh_summary())

            ttk.Separator(grid, orient="horizontal").pack(fill="x", pady=(12, 8))
            ttk.Label(grid, textvariable=var_sum, wraplength=430,
                      justify="left").pack(anchor="w")

        def render() -> None:
            # 切走前把当前行里的时刻存回去，切回来时不丢
            if time_rows:
                saved = [it["var"].get() for it in time_rows]
                init_times[:] = saved or ["09:00"]
            for w in dyn.winfo_children():
                w.destroy()
            time_rows.clear()

            kind = var_kind.get()
            if kind == "once":
                build_once()
            elif kind == "calendar":
                build_calendar()
            else:
                build_interval()
            refresh_summary()

        render()

        # 撑住最小宽度，否则切到「间隔 / 只跑一次」时窗口会变窄、跳一下
        ttk.Frame(body, width=484, height=1).grid(row=8, column=0, columnspan=2)

        ttk.Label(body, text="动作序列").grid(row=3, column=0, sticky="w", pady=(0, 2), padx=(0, 10))
        labels = list(seq_map.keys())
        var_seq = tk.StringVar()
        for k, v in seq_map.items():
            if v == (plan.get("seq_id") or default_seq_id):
                var_seq.set(k)
        if not var_seq.get() and labels:
            var_seq.set(labels[0])
        ttk.Combobox(body, textvariable=var_seq, values=labels, state="readonly",
                     width=32).grid(row=3, column=1, sticky="w", pady=(0, 2))

        def ok() -> None:
            kind = var_kind.get()
            if kind == "once":
                try:
                    d = datetime.strptime(var_date.get().strip(), "%Y-%m-%d")
                    h, mi = int(var_hh.get()), int(var_mm.get())
                    if not (0 <= h <= 23 and 0 <= mi <= 59):
                        raise ValueError
                except Exception:
                    messagebox.showerror("时间不对", "请检查日期与时间（小时 0-23，分钟 0-59）。", parent=win)
                    return
                at = datetime(d.year, d.month, d.day, h, mi)
                if at <= datetime.now() and not messagebox.askyesno(
                    "时间已过", "这个时间已经过去了，保存后不会自动触发。仍然保存吗？", parent=win
                ):
                    return
                raw: Dict[str, Any] = {"kind": "once", "at": at.strftime(trigger_mod.DT_FMT)}
            elif kind == "calendar":
                times: List[str] = []
                for item in time_rows:
                    raw_text = item["var"].get().strip()
                    if not raw_text:
                        continue
                    hm = trigger_mod.parse_time(raw_text)
                    if not hm:
                        messagebox.showerror("时刻格式", f"「{raw_text}」看不懂，请写成 09:00 这样。", parent=win)
                        return
                    if hm not in times:
                        times.append(hm)
                if not times:
                    messagebox.showerror("没有时刻", "至少填一个时刻，比如 09:00。", parent=win)
                    return
                raw = {
                    "kind": "calendar",
                    "times": sorted(times),
                    "days": [d for d in range(1, 8) if var_day[d].get()],
                }
            else:
                try:
                    every = int(float(var_every.get()))
                except Exception:
                    every = 0
                if every <= 0:
                    messagebox.showerror("间隔不对", "间隔必须是大于 0 的整数。", parent=win)
                    return
                if parse_dt(var_anchor.get()) is None:
                    messagebox.showerror("起点不对", "起点格式为 2026-10-21 15:00。", parent=win)
                    return
                raw = {
                    "kind": "interval",
                    "every": every,
                    "unit": var_unit.get(),
                    "anchor": var_anchor.get().strip(),
                }

            label = var_seq.get()
            if label not in seq_map:
                messagebox.showerror("没有序列", "请先创建一个动作序列。", parent=win)
                return
            result["v"] = {
                "name": var_name.get().strip() or "未命名计划",
                "seq_id": seq_map[label],
                "trigger": raw,
                # 结束条件已从界面移除；老数据里若存过就原样带回去，不悄悄清掉
                "end_at": plan.get("end_at", ""),
                "max_runs": plan.get("max_runs", 0),
            }
            win.destroy()

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(bar, text=("保存" if editing else "创建"), width=8, command=ok).pack(side="right")
        ttk.Button(bar, text="取消", width=8, command=win.destroy).pack(side="right", padx=6)
        win.bind("<Escape>", lambda e: win.destroy())
        parent.wait_window(win)
        return result["v"]

