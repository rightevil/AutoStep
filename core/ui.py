"""主界面（tkinter）。"""
from __future__ import annotations

import os
import queue
import subprocess
import time
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from . import capture, executor, winsys
from .config import APP_ID, APP_NAME, DATA_DIR, LEGACY_IDS, LOG_DIR, SHOT_DIR
from .scheduler import Scheduler, append_log_file
from .store import Store, now_str, parse_dt

FONT = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 9, "bold")
FONT_MONO = ("Consolas", 9)

TYPE_LABEL = {"click": "点击", "type": "输入", "key": "按键"}


class App:
    def __init__(self, root: tk.Tk, store: Store):
        self.root = root
        self.store = store
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.seq_id: str = store.sequences[0]["id"]
        self.target_hwnd = 0
        self._win_values: Dict[str, int] = {}
        self.tray = None

        self.root.title(f"{APP_NAME} · 定时执行")
        self.root.geometry("1100x862+60+30")
        self.root.minsize(1040, 700)
        self._init_style()
        self._build()
        self._load_settings()
        self._refresh_target_list()
        self._refresh_sequences()
        self._refresh_steps()
        self._refresh_plans()

        self.scheduler = Scheduler(store, lambda k, p: self.q.put((k, p)))
        self.scheduler.start()
        self._start_tray()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, self._drain)
        self._log("已启动。设置好动作与计划后，可最小化到托盘待命。")

    # ---------------------------------------------------------------- 样式

    def _init_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except Exception:
            pass
        style.configure(".", font=FONT)
        style.configure("Treeview", font=FONT, rowheight=24)
        style.configure("Treeview.Heading", font=FONT_BOLD)
        style.configure("TNotebook.Tab", padding=(12, 4))

    # ---------------------------------------------------------------- 布局

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}

        # ---- 目标窗口 ----
        frm_t = ttk.LabelFrame(self.root, text="目标窗口")
        frm_t.pack(fill="x", **pad)
        row = ttk.Frame(frm_t)
        row.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(row, text="进程名").pack(side="left")
        self.var_proc = tk.StringVar()
        ttk.Entry(row, textvariable=self.var_proc, width=18).pack(side="left", padx=(4, 12))
        ttk.Label(row, text="标题含").pack(side="left")
        self.var_title = tk.StringVar()
        ttk.Entry(row, textvariable=self.var_title, width=24).pack(side="left", padx=(4, 12))
        ttk.Button(row, text="刷新", width=6, command=self._refresh_target_list).pack(side="left", padx=2)
        ttk.Button(row, text="检测", width=6, command=self._test_target).pack(side="left", padx=2)
        self.lbl_target = ttk.Label(row, text="", foreground="#666")
        self.lbl_target.pack(side="left", padx=10)

        row2 = ttk.Frame(frm_t)
        row2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(row2, text="从窗口列表选择").pack(side="left")
        self.cmb_win = ttk.Combobox(row2, width=58, state="readonly")
        self.cmb_win.pack(side="left", padx=6, fill="x", expand=True)
        self.cmb_win.bind("<<ComboboxSelected>>", self._on_pick_window)

        # ---- 动作序列 ----
        frm_s = ttk.LabelFrame(self.root, text="动作序列（从上到下即执行顺序）")
        frm_s.pack(fill="both", expand=True, **pad)
        bar = ttk.Frame(frm_s)
        bar.pack(fill="x", padx=8, pady=(6, 0))
        ttk.Label(bar, text="序列").pack(side="left")
        self.cmb_seq = ttk.Combobox(bar, width=28, state="readonly")
        self.cmb_seq.pack(side="left", padx=6)
        self.cmb_seq.bind("<<ComboboxSelected>>", self._on_seq_change)
        ttk.Button(bar, text="新建", width=6, command=self._new_seq).pack(side="left", padx=2)
        ttk.Button(bar, text="重命名", width=7, command=self._rename_seq).pack(side="left", padx=2)
        ttk.Button(bar, text="删除", width=6, command=self._del_seq).pack(side="left", padx=2)

        cols = ("idx", "type", "pos", "content")
        self.tv_steps = ttk.Treeview(frm_s, columns=cols, show="headings", height=6)
        for c, w, txt in (
            ("idx", 44, "#"),
            ("type", 70, "类型"),
            ("pos", 130, "位置(%)"),
            ("content", 620, "内容 / 说明"),
        ):
            self.tv_steps.heading(c, text=txt)
            self.tv_steps.column(c, width=w, anchor="w" if c == "content" else "center")
        self.tv_steps.pack(fill="both", expand=True, padx=8, pady=6)
        self.tv_steps.bind("<Double-1>", lambda e: self._edit_step())

        bar2 = ttk.Frame(frm_s)
        bar2.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(bar2, text="+ 点击", width=8, command=self._add_click).pack(side="left", padx=2)
        ttk.Button(bar2, text="+ 输入", width=8, command=self._add_type).pack(side="left", padx=2)
        ttk.Button(bar2, text="+ 按键", width=8, command=self._add_key).pack(side="left", padx=2)
        ttk.Separator(bar2, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar2, text="编辑", width=6, command=self._edit_step).pack(side="left", padx=2)
        ttk.Button(bar2, text="上移", width=6, command=lambda: self._move(-1)).pack(side="left", padx=2)
        ttk.Button(bar2, text="下移", width=6, command=lambda: self._move(1)).pack(side="left", padx=2)
        ttk.Button(bar2, text="删除", width=6, command=self._del_step).pack(side="left", padx=2)
        ttk.Button(bar2, text="试运行一次", command=self._run_now).pack(side="right", padx=2)

        # ---- 设置 + 计划（左右并排）----
        mid = ttk.Frame(self.root)
        mid.pack(fill="x", **pad)
        mid.columnconfigure(0, weight=0)
        mid.columnconfigure(1, weight=1)

        frm_set = ttk.LabelFrame(mid, text="执行设置")
        frm_set.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        g = ttk.Frame(frm_set)
        g.pack(fill="both", padx=8, pady=6)
        ttk.Label(g, text="步间固定延时(秒)").grid(row=0, column=0, sticky="w", pady=3)
        self.var_delay = tk.DoubleVar(value=1.0)
        ttk.Spinbox(g, from_=0.1, to=60, increment=0.1, width=8, textvariable=self.var_delay,
                    command=self._save_settings).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(g, text="激活后等待(秒)").grid(row=1, column=0, sticky="w", pady=3)
        self.var_act = tk.DoubleVar(value=1.0)
        ttk.Spinbox(g, from_=0, to=30, increment=0.1, width=8, textvariable=self.var_act,
                    command=self._save_settings).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(g, text="输入方式").grid(row=2, column=0, sticky="w", pady=3)
        self.var_mode = tk.StringVar(value="auto")
        ttk.Combobox(g, width=16, state="readonly", textvariable=self.var_mode,
                     values=["auto", "keys", "paste"]).grid(row=2, column=1, sticky="w", padx=6)
        self.var_clear = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="输入前先 Ctrl+A 清空", variable=self.var_clear,
                        command=self._save_settings).grid(row=3, column=0, columnspan=2, sticky="w", pady=2)
        self.var_shot = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="执行后截图存证", variable=self.var_shot,
                        command=self._save_settings).grid(row=4, column=0, columnspan=2, sticky="w", pady=2)
        self.var_wake = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="执行前唤醒系统", variable=self.var_wake,
                        command=self._on_wake_toggle).grid(row=5, column=0, columnspan=2, sticky="w", pady=2)
        self.var_tray = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="关闭窗口时缩到托盘", variable=self.var_tray,
                        command=self._save_settings).grid(row=6, column=0, columnspan=2, sticky="w", pady=2)
        self.var_boot = tk.BooleanVar(value=False)
        ttk.Checkbutton(g, text="开机自动启动", variable=self.var_boot,
                        command=self._on_autostart_toggle).grid(row=7, column=0, columnspan=2, sticky="w", pady=2)
        for w in ("TCombobox",):
            g.option_add("*TCombobox*Listbox.font", FONT)

        frm_p = ttk.LabelFrame(mid, text="计划")
        frm_p.grid(row=0, column=1, sticky="nsew")
        pcols = ("name", "seq", "when", "repeat", "state", "next", "status")
        self.tv_plans = ttk.Treeview(frm_p, columns=pcols, show="headings", height=5)
        for c, w, txt, anc in (
            ("name", 126, "计划名称", "w"),
            ("seq", 96, "动作序列", "w"),
            ("when", 104, "设定时间", "center"),
            ("repeat", 50, "重复", "center"),
            ("state", 62, "状态", "center"),
            ("next", 104, "下次触发", "center"),
            ("status", 108, "上次结果", "w"),
        ):
            self.tv_plans.heading(c, text=txt)
            self.tv_plans.column(c, width=w, anchor=anc)
        self.tv_plans.pack(fill="both", expand=True, padx=8, pady=6)
        pbar = ttk.Frame(frm_p)
        pbar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(pbar, text="+ 新计划", width=9, command=self._new_plan).pack(side="left", padx=2)
        ttk.Button(pbar, text="编辑", width=6, command=self._edit_plan).pack(side="left", padx=2)
        ttk.Button(pbar, text="启用/停用", width=9, command=self._toggle_plan).pack(side="left", padx=2)
        ttk.Button(pbar, text="删除", width=6, command=self._del_plan).pack(side="left", padx=2)
        ttk.Button(pbar, text="打开日志目录", command=lambda: self._open(LOG_DIR)).pack(side="right", padx=2)
        self.tv_plans.bind("<Double-1>", lambda e: self._edit_plan())

        # ---- 日志 ----
        frm_l = ttk.LabelFrame(self.root, text="运行日志")
        frm_l.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(frm_l, height=9, font=FONT_MONO, wrap="word", state="disabled",
                           bg="#fafafa", relief="flat")
        sb = ttk.Scrollbar(frm_l, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True, padx=(8, 0), pady=6)
        self.txt.tag_configure("err", foreground="#c00000")
        self.txt.tag_configure("ok", foreground="#0a7d33")

        self.var_status = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.var_status, anchor="w",
                  relief="sunken", padding=(8, 3)).pack(fill="x", side="bottom")

    # ---------------------------------------------------------------- 日志 / 事件

    def _log(self, msg: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = msg if msg.startswith("[") else f"[{stamp}] {msg}"
        tag = "err" if msg.startswith("✘") or msg.startswith("⚠") else ("ok" if msg.startswith("✔") else "")
        self.txt.configure(state="normal")
        self.txt.insert("end", line + "\n", tag)
        self.txt.see("end")
        self.txt.configure(state="disabled")
        append_log_file(line)
        self.var_status.set(msg[:110])

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "refresh":
                    self._refresh_plans()
                elif kind == "executed":
                    self._refresh_plans()
                elif kind == "show":
                    self._show_window()
                elif kind == "quit":
                    self._quit()
        except queue.Empty:
            pass
        self.root.after(150, self._drain)

    # ---------------------------------------------------------------- 目标窗口

    def _refresh_target_list(self) -> None:
        vals: Dict[str, int] = {}
        labels: List[str] = []
        for w in winsys.list_windows():
            label = f"{w['process']} · {w['title'][:44]}"
            if label in vals:
                label = f"{label} ({w['pid']})"
            vals[label] = int(w["hwnd"])
            labels.append(label)
        self._win_values = vals
        self.cmb_win["values"] = labels
        self._test_target()

    def _on_pick_window(self, _evt=None) -> None:
        label = self.cmb_win.get()
        hwnd = self._win_values.get(label, 0)
        if not hwnd:
            return
        info = winsys.window_info(hwnd)
        self.var_proc.set(str(info["process"]))
        self.var_title.set("")
        self.target_hwnd = hwnd
        self._save_settings()
        self._log(f"已选目标窗口: {info['process']} · {info['title']}")
        self._test_target()

    def _test_target(self) -> None:
        hwnd = winsys.find_target(self.var_proc.get(), self.var_title.get(), self.target_hwnd)
        if hwnd:
            self.target_hwnd = hwnd
            info = winsys.window_info(hwnd)
            l, t, w, h = winsys.client_rect(hwnd)
            self.lbl_target.configure(text=f"✓ 已匹配 (hwnd={hwnd}, 客户区 {w}×{h})", foreground="#0a7d33")
        else:
            self.lbl_target.configure(text="✗ 未找到匹配窗口", foreground="#c00000")
        return

    def _ensure_target(self) -> int:
        hwnd = winsys.find_target(self.var_proc.get(), self.var_title.get(), self.target_hwnd)
        if not hwnd:
            messagebox.showwarning("没有目标窗口", "没找到匹配的窗口。请确认 ChatGPT（Codex）已启动，并点「刷新」重新选择。")
            return 0
        self.target_hwnd = hwnd
        return hwnd

    # ---------------------------------------------------------------- 设置

    def _load_settings(self) -> None:
        s = self.store.settings
        self.var_proc.set(s.get("target_process", ""))
        self.var_title.set(s.get("target_title", ""))
        self.var_delay.set(float(s.get("step_delay", 1.0)))
        self.var_act.set(float(s.get("activate_delay", 1.0)))
        self.var_mode.set(s.get("input_mode", "auto"))
        self.var_clear.set(bool(s.get("clear_first", True)))
        self.var_shot.set(bool(s.get("screenshot_after_run", True)))
        self.var_wake.set(bool(s.get("wake_before_run", True)))
        self.var_tray.set(bool(s.get("minimize_to_tray", True)))
        self.var_boot.set(bool(s.get("autostart", False)))

    def _save_settings(self) -> None:
        s = self.store.settings
        s["target_process"] = self.var_proc.get().strip()
        s["target_title"] = self.var_title.get().strip()
        try:
            s["step_delay"] = round(float(self.var_delay.get()), 2)
        except Exception:
            pass
        try:
            s["activate_delay"] = round(float(self.var_act.get()), 2)
        except Exception:
            pass
        s["input_mode"] = self.var_mode.get()
        s["clear_first"] = bool(self.var_clear.get())
        s["screenshot_after_run"] = bool(self.var_shot.get())
        s["wake_before_run"] = bool(self.var_wake.get())
        s["minimize_to_tray"] = bool(self.var_tray.get())
        self.store.save()

    def _on_wake_toggle(self) -> None:
        self._save_settings()
        self.scheduler._last_arm_key = ""
        self.scheduler.rearm()

    def _on_autostart_toggle(self) -> None:
        enable = bool(self.var_boot.get())
        ok, msg = self._set_autostart(enable)
        if ok:
            self.store.settings["autostart"] = enable
            self.store.save()
            self._log(("已设置开机自启" if enable else "已取消开机自启") + f"（{msg}）")
        else:
            self.var_boot.set(not enable)
            self._log(f"⚠ 设置开机自启失败：{msg}")

    @staticmethod
    def _set_autostart(enable: bool):
        """写 HKCU\\...\\Run，用 venv 里的 pythonw 静默启动。"""
        import sys
        import winreg

        from .config import APP_DIR

        name = APP_ID
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
        except Exception as e:
            return False, str(e)
        try:
            # 清掉旧标识留下的自动启动项，避免改名前后的两条同时生效
            for legacy in LEGACY_IDS:
                try:
                    winreg.DeleteValue(key, legacy)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
            if enable:
                if getattr(sys, "frozen", False):
                    # 打包后没有 main.py，直接指向 exe 自己
                    cmd = f'"{sys.executable}"'
                else:
                    exe = Path(sys.executable)
                    if exe.name.lower() != "pythonw.exe":
                        cand = exe.with_name("pythonw.exe")
                        if cand.exists():
                            exe = cand
                    cmd = f'"{exe}" "{APP_DIR / "main.py"}"'
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, cmd)
                return True, cmd
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
            return True, "removed"
        finally:
            key.Close()

    # ---------------------------------------------------------------- 序列

    def _refresh_sequences(self) -> None:
        names = [f"{s['name']}（{len(s['steps'])}步）" for s in self.store.sequences]
        self.cmb_seq["values"] = names
        idx = 0
        for i, s in enumerate(self.store.sequences):
            if s["id"] == self.seq_id:
                idx = i
        self.cmb_seq.current(idx)
        if self.store.sequences:
            self.seq_id = self.store.sequences[idx]["id"]

    def _current_seq(self) -> Optional[Dict[str, Any]]:
        return self.store.get_sequence(self.seq_id)

    def _on_seq_change(self, _evt=None) -> None:
        idx = self.cmb_seq.current()
        if 0 <= idx < len(self.store.sequences):
            self.seq_id = self.store.sequences[idx]["id"]
            self._refresh_steps()

    def _new_seq(self) -> None:
        name = SimplePrompt.ask(self.root, "新建序列", "序列名称", f"序列{len(self.store.sequences)+1}")
        if not name:
            return
        seq = self.store.add_sequence(name)
        self.seq_id = seq["id"]
        self._refresh_sequences()
        self._refresh_steps()

    def _rename_seq(self) -> None:
        seq = self._current_seq()
        if not seq:
            return
        name = SimplePrompt.ask(self.root, "重命名序列", "序列名称", seq["name"])
        if not name:
            return
        seq["name"] = name
        self.store.save()
        self._refresh_sequences()

    def _del_seq(self) -> None:
        seq = self._current_seq()
        if not seq:
            return
        if not messagebox.askyesno("删除序列", f"确定删除「{seq['name']}」？引用它的计划也会被删除。"):
            return
        self.store.remove_sequence(seq["id"])
        self.seq_id = self.store.sequences[0]["id"]
        self._refresh_sequences()
        self._refresh_steps()
        self._refresh_plans()

    # ---------------------------------------------------------------- 动作

    def _refresh_steps(self) -> None:
        self.tv_steps.delete(*self.tv_steps.get_children())
        seq = self._current_seq()
        if not seq:
            return
        for i, st in enumerate(seq["steps"], 1):
            t = st.get("type")
            pos = ""
            if st.get("rect"):
                r = st["rect"]
                cx = (float(r["x1"]) + float(r["x2"])) / 2 * 100
                cy = (float(r["y1"]) + float(r["y2"])) / 2 * 100
                pos = f"{cx:.1f}%, {cy:.1f}%"
            if t == "type":
                content = st.get("text", "").replace("\n", " ⏎ ")
            elif t == "key":
                content = st.get("combo", "enter")
            else:
                content = st.get("note", "")
            if len(content) > 90:
                content = content[:90] + "…"
            self.tv_steps.insert("", "end", iid=str(i - 1), values=(i, TYPE_LABEL.get(t, t), pos, content))
        self._refresh_sequences_silent()

    def _refresh_sequences_silent(self) -> None:
        names = [f"{s['name']}（{len(s['steps'])}步）" for s in self.store.sequences]
        cur = self.cmb_seq.current()
        self.cmb_seq["values"] = names
        if 0 <= cur < len(names):
            self.cmb_seq.current(cur)

    def _save_seq(self) -> None:
        self.store.save()
        self._refresh_steps()

    def _append_step(self, step: Dict[str, Any]) -> None:
        seq = self._current_seq()
        if not seq:
            return
        seq["steps"].append(step)
        self._save_seq()
        last = len(seq["steps"]) - 1
        self.tv_steps.selection_set(str(last))
        self.tv_steps.see(str(last))

    def _pick_region(self, on_rect: Callable[[Optional[Dict[str, float]]], None]) -> None:
        hwnd = self._ensure_target()
        if not hwnd:
            return
        if not winsys.activate(hwnd):
            messagebox.showwarning("无法激活窗口", "存在前台窗口锁，未能把目标窗口切到前台，请手动点一下 Codex 窗口再试。")
            return
        self.var_status.set("正在抓取目标窗口截图…")
        self.root.withdraw()
        self.root.after(500, lambda: self._do_pick(hwnd, on_rect))

    def _do_pick(self, hwnd: int, on_rect: Callable[[Optional[Dict[str, float]]], None]) -> None:
        img = capture.grab_client(hwnd)
        if img is None:
            self.root.deiconify()
            messagebox.showerror("截图失败", "无法抓取目标窗口，请确认窗口没被最小化。")
            return
        l, t, _, _ = winsys.client_rect(hwnd)

        def done(rect: Optional[Dict[str, float]]) -> None:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.var_status.set("就绪")
            on_rect(rect)

        capture.RegionPicker(self.root, img, l, t, done)

    def _add_click(self) -> None:
        def done(rect: Optional[Dict[str, float]]) -> None:
            if not rect:
                return
            note = SimplePrompt.ask(self.root, "点击动作", "备注（可空）", "点击", allow_empty=True)
            self._append_step({"type": "click", "rect": rect, "note": note or ""})
            self._log(f"已添加点击动作 {rect}")

        self._pick_region(done)

    def _add_type(self) -> None:
        def done(rect: Optional[Dict[str, float]]) -> None:
            if not rect:
                return
            res = TextDialog.ask(self.root, "输入动作", "要输入的内容")
            if res is None:
                return
            text, clear = res
            self._append_step({"type": "type", "rect": rect, "text": text, "clear_first": clear})
            self._log(f"已添加输入动作（{len(text)} 字符）")

        self._pick_region(done)

    def _add_key(self) -> None:
        res = KeyDialog.ask(self.root, "按键动作")
        if not res:
            return
        self._append_step({"type": "key", "combo": res})
        self._log(f"已添加按键动作 {res}")

    def _selected_index(self) -> int:
        sel = self.tv_steps.selection()
        if not sel:
            return -1
        try:
            return int(sel[0])
        except Exception:
            return -1

    def _edit_step(self) -> None:
        idx = self._selected_index()
        seq = self._current_seq()
        if idx < 0 or not seq or idx >= len(seq["steps"]):
            return
        st = seq["steps"][idx]
        if st["type"] == "type":
            res = TextDialog.ask(self.root, "编辑输入内容", "要输入的内容", st.get("text", ""))
            if res is None:
                return
            st["text"], st["clear_first"] = res
        elif st["type"] == "key":
            res = KeyDialog.ask(self.root, "编辑按键", st.get("combo", "enter"))
            if not res:
                return
            st["combo"] = res
        else:
            note = SimplePrompt.ask(self.root, "编辑备注", "备注", st.get("note", ""), allow_empty=True)
            st["note"] = note or ""
        self._save_seq()

    def _move(self, delta: int) -> None:
        idx = self._selected_index()
        seq = self._current_seq()
        if idx < 0 or not seq:
            return
        j = idx + delta
        if not (0 <= j < len(seq["steps"])):
            return
        seq["steps"][idx], seq["steps"][j] = seq["steps"][j], seq["steps"][idx]
        self._save_seq()
        self.tv_steps.selection_set(str(j))

    def _del_step(self) -> None:
        idx = self._selected_index()
        seq = self._current_seq()
        if idx < 0 or not seq:
            return
        del seq["steps"][idx]
        self._save_seq()

    def _run_now(self) -> None:
        seq = self._current_seq()
        if not seq or not seq["steps"]:
            messagebox.showinfo("提示", "当前序列还没有动作。先添加点击/输入动作。")
            return
        self._save_settings()
        self._log("手动触发试运行…")
        if self.root.state() == "normal":
            pass
        self.root.withdraw()  # 让出屏幕，避免自己挡住目标窗口
        self.scheduler.run_sequence_now(seq["id"], "手动试运行")
        self.root.after(1200, self._restore_after_run)

    def _restore_after_run(self) -> None:
        if not self.scheduler._running.locked():
            self._show_window()
        else:
            self.root.after(800, self._restore_after_run)

    # ---------------------------------------------------------------- 计划

    def _refresh_plans(self) -> None:
        self.tv_plans.delete(*self.tv_plans.get_children())
        for i, p in enumerate(self.store.plans):
            seq = self.store.get_sequence(p.get("seq_id", ""))
            seq_name = seq["name"] if seq else "（已删除）"
            repeat = "每天" if p.get("repeat") == "daily" else "一次"
            nxt = p.get("next_fire") or "—"
            if not p.get("enabled"):
                nxt = "—"
            # 状态：已完成 / 已停用 / 待执行 / 已过期
            if not p.get("enabled"):
                state = "已完成" if p.get("status") == "done" else "已停用"
            elif p.get("next_fire"):
                state = "待执行"
            else:
                state = "已过期"
            status = p.get("last_status") or ""
            if len(status) > 16:
                status = status[:16] + "…"
            self.tv_plans.insert(
                "", "end", iid=str(i),
                values=(p.get("name", ""), seq_name, p.get("run_at", ""), repeat, state, nxt, status),
            )
        fires = self.store.next_fires()
        if fires:
            p = fires[0]["plan"]
            self.var_status.set(f"下一个计划：{p['name']} @ {fires[0]['dt']:%m-%d %H:%M}")

    def _selected_plan(self) -> Optional[Dict[str, Any]]:
        sel = self.tv_plans.selection()
        if not sel:
            return None
        idx = int(sel[0])
        if 0 <= idx < len(self.store.plans):
            return self.store.plans[idx]
        return None

    def _new_plan(self) -> None:
        seq = self._current_seq()
        seqs = {f"{s['name']}（{len(s['steps'])}步）": s["id"] for s in self.store.sequences}
        res = PlanDialog.ask(self.root, seqs, seq["id"] if seq else "")
        if not res:
            return
        plan = self.store.add_plan(**res)
        self._refresh_plans()
        self.scheduler._last_arm_key = ""
        self.scheduler.rearm()
        self._log(f"已新建计划「{plan['name']}」下次触发 {plan['next_fire'] or '（时间已过）'}")

    def _rename_plan(self) -> None:
        p = self._selected_plan()
        if not p:
            messagebox.showinfo("提示", "先在计划列表里选中一条计划。")
            return
        name = SimplePrompt.ask(self.root, "重命名计划", "计划名称", p.get("name", ""))
        if not name:
            return
        self.store.rename_plan(p["id"], name)
        self._refresh_plans()
        self._log(f"计划已重命名为「{name}」")

    def _edit_plan(self) -> None:
        p = self._selected_plan()
        if not p:
            messagebox.showinfo("提示", "先在计划列表里选中一条计划，再点「编辑」。")
            return
        seq_map = {f"{s['name']}（{len(s['steps'])}步）": s["id"] for s in self.store.sequences}
        res = PlanDialog.ask(self.root, seq_map, p.get("seq_id", ""), plan=p)
        if not res:
            return
        updated = self.store.update_plan(
            p["id"], res["name"], res["run_at"], res["repeat"], res["seq_id"]
        )
        self._refresh_plans()
        self.scheduler._last_arm_key = ""
        self.scheduler.rearm()
        if updated and not updated.get("enabled"):
            self._log(f"计划「{updated['name']}」已保存，但设定时间已过（一次性），不会自动触发")
        elif updated:
            self._log(f"计划「{updated['name']}」已更新，下次触发 {updated['next_fire']}")

    def _toggle_plan(self) -> None:
        p = self._selected_plan()
        if not p:
            return
        p["enabled"] = not p.get("enabled", True)
        if p["enabled"]:
            base = parse_dt(p.get("run_at", ""))
            if base and base <= datetime.now() and p.get("repeat") != "daily":
                messagebox.showwarning("时间已过", "这个计划设定时间已经过去，一次性计划不会再触发。请新建一个。")
                p["enabled"] = False
        self.store.refresh_plan(p)
        self._refresh_plans()
        self.scheduler._last_arm_key = ""
        self.scheduler.rearm()

    def _del_plan(self) -> None:
        p = self._selected_plan()
        if not p:
            return
        if not messagebox.askyesno("删除计划", f"确定删除计划「{p['name']}」？"):
            return
        self.store.remove_plan(p["id"])
        self._refresh_plans()
        self.scheduler._last_arm_key = ""
        self.scheduler.rearm()

    # ---------------------------------------------------------------- 托盘

    def _start_tray(self) -> None:
        try:
            import pystray

            from .icon import make_icon

            img = make_icon(64)

            menu = pystray.Menu(
                pystray.MenuItem("显示主窗口", lambda: self.q.put(("show", None)), default=True),
                pystray.MenuItem("试运行当前序列", lambda: (self.q.put(("show", None)), self.root.after(300, self._run_now))),
                pystray.MenuItem("退出", lambda: self.q.put(("quit", None))),
            )
            self.tray = pystray.Icon(APP_ID, img, f"{APP_NAME} · 定时执行", menu)
            self.tray.run_detached()
        except Exception as e:
            self.tray = None
            self._log(f"托盘图标不可用（{e}），关闭窗口将直接退出")

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def _on_close(self) -> None:
        if self.var_tray.get() and self.tray is not None:
            self.root.withdraw()
            try:
                self.tray.notify(f"{APP_NAME} 仍在后台待命，计划到点会自动执行。", APP_NAME)
            except Exception:
                pass
            self._log("已缩到托盘，继续后台待命。")
            return
        if messagebox.askyesno("退出", "退出后定时计划将不再执行，确定退出？"):
            self._quit()

    def _quit(self) -> None:
        self.scheduler.stop()
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        self.root.destroy()

    def _open(self, path) -> None:
        try:
            os.startfile(str(path))
        except Exception:
            pass


# ==================================================================== 对话框


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
                ttk.Label(grid, text=wd, width=4, anchor="center", foreground="#888").grid(row=0, column=c)
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


class PlanDialog:
    @staticmethod
    def ask(parent, seq_map: Dict[str, str], default_seq_id: str = "", plan: Optional[Dict[str, Any]] = None):
        editing = plan is not None
        win = tk.Toplevel(parent)
        win.title("编辑计划" if editing else "新建计划")
        win.transient(parent)
        win.grab_set()
        win.resizable(False, False)
        result: Dict[str, Optional[Dict[str, Any]]] = {"v": None}

        default_dt = (datetime.now() + timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
        if editing:
            init_dt = parse_dt(plan.get("run_at", "")) or default_dt
            init_name = plan.get("name", "") or "未命名计划"
            init_rep = plan.get("repeat", "none")
            init_seq = plan.get("seq_id", "") or default_seq_id
        else:
            init_dt = default_dt
            init_name = "凌晨执行"
            init_rep = "none"
            init_seq = default_seq_id

        body = ttk.Frame(win)
        body.pack(fill="both", padx=14, pady=12)

        ttk.Label(body, text="名称").grid(row=0, column=0, sticky="w", pady=4)
        var_name = tk.StringVar(value=init_name)
        ttk.Entry(body, textvariable=var_name, width=34).grid(row=0, column=1, columnspan=4, sticky="w")

        # ---- 日期：只读输入框 + 日历按钮 ----
        ttk.Label(body, text="日期").grid(row=1, column=0, sticky="w", pady=4)
        var_date = tk.StringVar(value=init_dt.strftime("%Y-%m-%d"))
        ent_date = ttk.Entry(body, textvariable=var_date, width=13, state="readonly")
        ent_date.grid(row=1, column=1, sticky="w")

        def open_cal():
            cur = parse_dt(f"{var_date.get()} 00:00")
            picked = CalendarDialog.ask(win, cur.date() if cur else None)
            if picked:
                var_date.set(picked.strftime("%Y-%m-%d"))

        ttk.Button(body, text="📅 选择", width=9, command=open_cal).grid(row=1, column=2, sticky="w", padx=(6, 12))

        # ---- 时间：小时/分钟下拉，可直接改写 ----
        ttk.Label(body, text="时间").grid(row=1, column=3, sticky="e", padx=(0, 4))
        tframe = ttk.Frame(body)
        tframe.grid(row=1, column=4, sticky="w")
        var_hh = tk.StringVar(value=init_dt.strftime("%H"))
        var_mm = tk.StringVar(value=init_dt.strftime("%M"))
        ttk.Combobox(tframe, textvariable=var_hh, values=[f"{h:02d}" for h in range(24)], width=4).pack(side="left")
        ttk.Label(tframe, text=":").pack(side="left", padx=2)
        ttk.Combobox(tframe, textvariable=var_mm, values=[f"{m:02d}" for m in range(60)], width=4).pack(side="left")

        ttk.Label(body, text="重复").grid(row=2, column=0, sticky="w", pady=4)
        var_rep = tk.StringVar(value=init_rep)
        rep = ttk.Frame(body)
        rep.grid(row=2, column=1, columnspan=4, sticky="w")
        ttk.Radiobutton(rep, text="只跑一次", variable=var_rep, value="none").pack(side="left")
        ttk.Radiobutton(rep, text="每天同一时间", variable=var_rep, value="daily").pack(side="left", padx=12)

        ttk.Label(body, text="动作序列").grid(row=3, column=0, sticky="w", pady=4)
        labels = list(seq_map.keys())
        var_seq = tk.StringVar()
        for k, v in seq_map.items():
            if v == init_seq:
                var_seq.set(k)
        if not var_seq.get() and labels:
            var_seq.set(labels[0])
        ttk.Combobox(body, textvariable=var_seq, values=labels, state="readonly", width=34).grid(
            row=3, column=1, columnspan=4, sticky="w"
        )

        tip = ttk.Label(
            body,
            text="提示：到点前会自动尝试唤醒系统；若系统处于锁屏界面，界面操作无法完成。",
            foreground="#888",
            wraplength=380,
        )
        tip.grid(row=4, column=0, columnspan=5, sticky="w", pady=(10, 0))

        def ok():
            ds = var_date.get().strip()
            try:
                d = datetime.strptime(ds, "%Y-%m-%d").date()
            except Exception:
                messagebox.showerror("日期不对", "请点「📅 选择」挑一个日期。", parent=win)
                return
            try:
                h, mi = int(var_hh.get()), int(var_mm.get())
                if not (0 <= h <= 23 and 0 <= mi <= 59):
                    raise ValueError
            except Exception:
                messagebox.showerror("时间不对", "小时 0-23，分钟 0-59，例如 03 : 00。", parent=win)
                return
            dt = datetime(d.year, d.month, d.day, h, mi)
            if dt <= datetime.now() and var_rep.get() == "none":
                if not messagebox.askyesno(
                    "时间已过",
                    "这个时间已经过去了，保存后不会自动触发。仍然保存吗？",
                    parent=win,
                ):
                    return
            label = var_seq.get()
            if label not in seq_map:
                messagebox.showerror("没有序列", "请先创建一个动作序列。", parent=win)
                return
            result["v"] = {
                "name": var_name.get().strip() or "未命名计划",
                "seq_id": seq_map[label],
                "run_at": dt.strftime("%Y-%m-%d %H:%M"),
                "repeat": var_rep.get(),
            }
            win.destroy()

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(bar, text=("保存" if editing else "创建"), width=8, command=ok).pack(side="right")
        ttk.Button(bar, text="取消", width=8, command=win.destroy).pack(side="right", padx=6)
        win.bind("<Escape>", lambda e: win.destroy())
        parent.wait_window(win)
        return result["v"]
