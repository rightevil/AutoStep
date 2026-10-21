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
from . import profile as profile_mod
from . import trigger as trigger_mod
from .config import APP_ID, APP_NAME, DATA_DIR, LEGACY_IDS, LOG_DIR, SHOT_DIR
from .scheduler import Scheduler, append_log_file
from .store import Store, now_str, parse_dt

FONT = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 9, "bold")
FONT_MONO = ("Consolas", 9)

TYPE_LABEL = {"click": "点击", "type": "输入", "key": "按键"}
SEND_LABEL = "发送（应用默认）"


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
        self._refresh_profile_combo()
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

        # ---- 目标应用（档案）----
        frm_t = ttk.LabelFrame(self.root, text="目标应用（跟随当前序列）")
        frm_t.pack(fill="x", **pad)
        row = ttk.Frame(frm_t)
        row.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(row, text="档案").pack(side="left")
        self.cmb_prof = ttk.Combobox(row, width=34, state="readonly")
        self.cmb_prof.pack(side="left", padx=(4, 10))
        self.cmb_prof.bind("<<ComboboxSelected>>", self._on_pick_profile)
        ttk.Button(row, text="新建档案", width=9, command=self._new_profile).pack(side="left", padx=2)
        ttk.Button(row, text="编辑档案", width=9, command=self._edit_profile).pack(side="left", padx=2)
        ttk.Button(row, text="检测", width=6, command=self._test_target).pack(side="left", padx=2)
        self.lbl_target = ttk.Label(row, text="", foreground="#666")
        self.lbl_target.pack(side="left", padx=10)

        row2 = ttk.Frame(frm_t)
        row2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(row2, text="从窗口列表选择（写入当前档案）").pack(side="left")
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
        ttk.Button(bar2, text="+ 发送", width=8, command=self._add_send).pack(side="left", padx=2)
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
        self.lbl_input = ttk.Label(g, text="（见档案）", foreground="#666")
        self.lbl_input.grid(row=2, column=1, sticky="w", padx=6)
        self.var_shot = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="执行后截图存证", variable=self.var_shot,
                        command=self._save_settings).grid(row=3, column=0, columnspan=2, sticky="w", pady=2)
        self.var_wake = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="执行前唤醒系统", variable=self.var_wake,
                        command=self._on_wake_toggle).grid(row=4, column=0, columnspan=2, sticky="w", pady=2)
        self.var_tray = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="关闭窗口时缩到托盘", variable=self.var_tray,
                        command=self._save_settings).grid(row=5, column=0, columnspan=2, sticky="w", pady=2)
        self.var_boot = tk.BooleanVar(value=False)
        ttk.Checkbutton(g, text="开机自动启动", variable=self.var_boot,
                        command=self._on_autostart_toggle).grid(row=6, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(g, text="输入方式与发送键跟着档案走，\n换应用只需换档案。", foreground="#888",
                  justify="left").grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))
        for w in ("TCombobox",):
            g.option_add("*TCombobox*Listbox.font", FONT)

        frm_p = ttk.LabelFrame(mid, text="计划")
        frm_p.grid(row=0, column=1, sticky="nsew")
        pcols = ("name", "seq", "when", "repeat", "state", "next", "status")
        self.tv_plans = ttk.Treeview(frm_p, columns=pcols, show="headings", height=5)
        for c, w, txt, anc in (
            ("name", 96, "计划名称", "w"),
            ("seq", 132, "动作序列 / 应用", "w"),
            ("when", 150, "设定时间", "center"),
            ("repeat", 88, "触发方式", "center"),
            ("state", 52, "状态", "center"),
            ("next", 96, "下次", "center"),
            ("status", 84, "上次结果", "w"),
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
        got = 0
        try:
            while True:
                kind, payload = self.q.get_nowait()
                got += 1
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
        # 有消息就立刻再看；空闲（尤其缩到托盘后）降频轮询，待命时几乎不占 CPU
        if got:
            wait = 15
        else:
            wait = 800 if self.root.state() == "withdrawn" else 200
        self.root.after(wait, self._drain)

    # ---------------------------------------------------------------- 目标应用（档案）

    def _current_profile(self) -> Optional[Dict[str, Any]]:
        seq = self._current_seq()
        if not seq:
            return None
        return self.store.get_profile(seq.get("profile_id", ""))

    def _set_seq_profile(self, profile_id: str) -> None:
        seq = self._current_seq()
        if not seq or not profile_id:
            return
        seq["profile_id"] = profile_id
        self.store.save()
        self._refresh_plans()

    def _refresh_profile_combo(self) -> None:
        choices = self.store.profile_choices()
        self._prof_labels = [profile_mod.describe(p) for p in choices]
        self._prof_ids = [p["id"] for p in choices]
        self.cmb_prof["values"] = self._prof_labels
        cur = self._current_profile()
        idx = 0
        if cur and cur["id"] in self._prof_ids:
            idx = self._prof_ids.index(cur["id"])
        if self._prof_labels:
            self.cmb_prof.current(idx)
        if cur:
            i = cur.get("input") or {}
            clear = "先清空" if i.get("clear_first") else "不清空"
            send = (cur.get("send") or {}).get("combo", "enter")
            self.lbl_input.configure(text=f"{i.get('mode', 'auto')} · {clear} · 发送 {send}")
        # 换档案必须丢掉旧的 hwnd 缓存，否则会沿用上一个应用匹配到的窗口
        self.target_hwnd = 0
        self._test_target()

    def _on_pick_profile(self, _evt=None) -> None:
        idx = self.cmb_prof.current()
        if 0 <= idx < len(self._prof_ids):
            self._set_seq_profile(self._prof_ids[idx])
            self._refresh_profile_combo()

    def _new_profile(self) -> None:
        prof = ProfileDialog.ask(self.root, None)
        if not prof:
            return
        saved = self.store.upsert_profile(prof)
        self._set_seq_profile(saved["id"])
        self._refresh_profile_combo()
        self._log(f"已新建档案「{saved['name']}」")

    def _edit_profile(self) -> None:
        cur = self._current_profile()
        if not cur:
            return
        prof = ProfileDialog.ask(self.root, cur, deletable=len(self.store.profiles) > 1)
        if not prof:
            return
        if prof.get("__delete__"):
            if self.store.remove_profile(cur["id"]):
                self._refresh_profile_combo()
                self._log(f"已删除档案「{cur.get('name')}」，相关序列改挂默认档案")
            return
        saved = self.store.upsert_profile(prof)
        self._refresh_profile_combo()
        self._log(f"已保存档案「{saved['name']}」")

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
        prof = self._current_profile()
        if not prof:
            return
        info = winsys.window_info(hwnd)
        prof["match"] = {"process": str(info["process"]), "title": ""}
        self.store.upsert_profile(prof)
        self.target_hwnd = hwnd
        self._refresh_profile_combo()
        self._log(f"已把档案「{prof.get('name')}」的目标设为 {info['process']} · {info['title']}")

    def _test_target(self) -> None:
        prof = self._current_profile()
        if not prof:
            self.lbl_target.configure(text="未选择序列", foreground="#c00000")
            return
        if not profile_mod.has_target(prof):
            self.target_hwnd = 0
            self.lbl_target.configure(text="✗ 档案还没设目标窗口", foreground="#c00000")
            return
        hwnd = profile_mod.match_target(prof, self.target_hwnd)
        if hwnd:
            self.target_hwnd = hwnd
            info = winsys.window_info(hwnd)
            _, _, w, h = winsys.client_rect(hwnd)
            self.lbl_target.configure(
                text=f"✓ {info['process']} · 客户区 {w}×{h}", foreground="#0a7d33"
            )
        else:
            self.target_hwnd = 0
            self.lbl_target.configure(text="✗ 该应用的窗口没找到", foreground="#c00000")

    def _ensure_target(self) -> int:
        prof = self._current_profile()
        if not prof:
            return 0
        if not profile_mod.has_target(prof):
            messagebox.showwarning(
                "档案没有目标",
                f"当前档案「{prof.get('name', '')}」还没设置目标窗口。\n"
                "点「编辑档案」填进程名，或从下面的窗口列表选一个。",
            )
            return 0
        hwnd = profile_mod.match_target(prof, self.target_hwnd)
        if not hwnd:
            messagebox.showwarning(
                "没有目标窗口",
                f"没找到「{prof.get('name', '')}」对应的窗口。\n"
                "请确认该应用已启动，再点「检测」，或从窗口列表重新选择。",
            )
            return 0
        self.target_hwnd = hwnd
        return hwnd

    # ---------------------------------------------------------------- 设置

    def _load_settings(self) -> None:
        s = self.store.settings
        self.var_delay.set(float(s.get("step_delay", 1.0)))
        self.var_act.set(float(s.get("activate_delay", 1.0)))
        self.var_shot.set(bool(s.get("screenshot_after_run", True)))
        self.var_wake.set(bool(s.get("wake_before_run", True)))
        self.var_tray.set(bool(s.get("minimize_to_tray", True)))
        self.var_boot.set(bool(s.get("autostart", False)))

    def _save_settings(self) -> None:
        s = self.store.settings
        try:
            s["step_delay"] = round(float(self.var_delay.get()), 2)
        except Exception:
            pass
        try:
            s["activate_delay"] = round(float(self.var_act.get()), 2)
        except Exception:
            pass
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
            self._refresh_profile_combo()

    def _new_seq(self) -> None:
        name = SimplePrompt.ask(self.root, "新建序列", "序列名称", f"序列{len(self.store.sequences)+1}")
        if not name:
            return
        cur = self._current_profile()
        seq = self.store.add_sequence(name, cur["id"] if cur else "")
        self.seq_id = seq["id"]
        self._refresh_sequences()
        self._refresh_steps()
        self._refresh_profile_combo()

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
        self._refresh_profile_combo()

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
                combo = st.get("combo", "enter")
                content = SEND_LABEL if combo == profile_mod.SEND_ALIAS else combo
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

    def _add_send(self) -> None:
        """插入「按当前档案的发送键」，换应用时不用改这一条。"""
        prof = self._current_profile()
        combo = profile_mod.resolve_send(prof)
        self._append_step({"type": "key", "combo": profile_mod.SEND_ALIAS})
        self._log(f"已添加发送动作（当前档案按 {combo}）")

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
            prof = self.store.sequence_profile(seq) if seq else None
            if prof:
                # 一眼看出这条计划会对哪个应用下手（放进程名，比档案名短）
                tag = (prof.get("match") or {}).get("process") or prof.get("name", "")
                seq_name = f"{seq_name} / {tag}"
            repeat = trigger_mod.describe(p.get("trigger"))
            nxt = (p.get("next_fire") or "")[5:] or "—"   # 列窄，省掉年份；完整时间在状态栏和日志里
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
                values=(p.get("name", ""), seq_name, trigger_mod.when_text(p.get("trigger")), repeat, state, nxt, status),
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
            p["id"], res["name"], seq_id=res["seq_id"],
            trigger=res["trigger"], end_at=res["end_at"], max_runs=res["max_runs"],
        )
        self._refresh_plans()
        self.scheduler._last_arm_key = ""
        self.scheduler.rearm()
        if updated and not updated.get("enabled"):
            self._log(f"计划「{updated['name']}」已保存，但没有下一次触发（时间已过或次数用尽）")
        elif updated:
            self._log(f"计划「{updated['name']}」已更新，下次触发 {updated['next_fire']}")

    def _toggle_plan(self) -> None:
        p = self._selected_plan()
        if not p:
            return
        p["enabled"] = not p.get("enabled", True)
        self.store.refresh_plan(p)
        if p["enabled"] and not p.get("next_fire"):
            messagebox.showwarning("无法启用", "这个计划已经没有下一次触发了（时间已过或次数用尽），请先编辑时间。")
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


class ProfileDialog:
    """应用档案编辑框：目标怎么找、怎么输入、按什么键发送。"""

    @staticmethod
    def ask(
        parent, profile: Optional[Dict[str, Any]], deletable: bool = False
    ) -> Optional[Dict[str, Any]]:
        win = tk.Toplevel(parent)
        win.title("编辑应用档案" if profile else "新建应用档案")
        win.transient(parent)
        win.grab_set()
        win.resizable(False, False)
        p = profile_mod.normalize(profile or {}, "")
        result: Dict[str, Any] = {"v": None}

        body = ttk.Frame(win)
        body.pack(fill="both", padx=14, pady=12)

        ttk.Label(body, text="档案名称").grid(row=0, column=0, sticky="w", pady=4)
        var_name = tk.StringVar(value=p.get("name", ""))
        ttk.Entry(body, textvariable=var_name, width=32).grid(row=0, column=1, sticky="w")

        ttk.Label(body, text="进程名").grid(row=1, column=0, sticky="w", pady=4)
        var_proc = tk.StringVar(value=(p.get("match") or {}).get("process", ""))
        ttk.Entry(body, textvariable=var_proc, width=32).grid(row=1, column=1, sticky="w")
        ttk.Label(body, text="包含即可，如 ChatGPT 能匹配 ChatGPT.exe", foreground="#888").grid(
            row=2, column=1, sticky="w"
        )

        ttk.Label(body, text="标题含（可空）").grid(row=3, column=0, sticky="w", pady=4)
        var_title = tk.StringVar(value=(p.get("match") or {}).get("title", ""))
        ttk.Entry(body, textvariable=var_title, width=32).grid(row=3, column=1, sticky="w")

        ttk.Label(body, text="输入方式").grid(row=4, column=0, sticky="w", pady=4)
        var_mode = tk.StringVar(value=(p.get("input") or {}).get("mode", "auto"))
        ttk.Combobox(
            body, textvariable=var_mode, width=29, state="readonly",
            values=["auto", "keys", "paste"],
        ).grid(row=4, column=1, sticky="w")
        ttk.Label(
            body, text="auto=含中文走剪贴板；keys=一律逐键；paste=一律粘贴", foreground="#888"
        ).grid(row=5, column=1, sticky="w")

        var_clear = tk.BooleanVar(value=(p.get("input") or {}).get("clear_first", True))
        ttk.Checkbutton(body, text="输入前先 Ctrl+A 清空", variable=var_clear).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=2
        )

        ttk.Label(body, text="发送键").grid(row=7, column=0, sticky="w", pady=4)
        var_send = tk.StringVar(value=(p.get("send") or {}).get("combo", "enter"))
        ttk.Combobox(
            body, textvariable=var_send, width=29,
            values=["enter", "ctrl+enter", "shift+enter", "tab"],
        ).grid(row=7, column=1, sticky="w")
        ttk.Label(body, text="「+ 发送」动作按这里设置的键发出去", foreground="#888").grid(
            row=8, column=1, sticky="w"
        )

        def ok() -> None:
            proc = var_proc.get().strip()
            title = var_title.get().strip()
            if not proc and not title:
                if not messagebox.askyesno(
                    "还没设目标",
                    "进程名和标题都是空的，这条档案找不到任何窗口，执行时会直接失败。\n仍然保存吗？",
                    parent=win,
                ):
                    return
            result["v"] = {
                "id": p.get("id", ""),
                "name": var_name.get().strip() or proc or "未命名档案",
                "match": {"process": proc, "title": title},
                "input": {"mode": var_mode.get(), "clear_first": bool(var_clear.get())},
                "send": {"combo": var_send.get().strip() or "enter"},
                "verify": {"type": "none"},
            }
            win.destroy()

        def do_delete() -> None:
            if not messagebox.askyesno(
                "删除档案", "删除后，用它的序列会改挂默认档案。确定？", parent=win
            ):
                return
            result["v"] = {"__delete__": True}
            win.destroy()

        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(bar, text="保存", width=8, command=ok).pack(side="right")
        ttk.Button(bar, text="取消", width=8, command=win.destroy).pack(side="right", padx=6)
        if deletable and profile:
            ttk.Button(bar, text="删除", width=8, command=do_delete).pack(side="left")
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
                tk.Checkbutton(
                    daybar, text=trigger_mod.WEEK[d - 1], variable=var_day[d],
                    indicatoron=False, width=2, bd=1, relief="raised", overrelief="raised",
                    selectcolor="#cfe3f7", font=FONT, padx=2, pady=1,
                    command=refresh_summary,
                ).pack(side="left", padx=(0, 3))
            ttk.Label(daybar, text="不选 = 每天", foreground="#888").pack(side="left", padx=(9, 0))

            ttk.Separator(grid, orient="horizontal").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 8))
            ttk.Label(grid, textvariable=var_sum, foreground="#444", wraplength=352,
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
            ttk.Label(grid, textvariable=var_sum, foreground="#444", wraplength=352,
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
            ttk.Label(grid, textvariable=var_sum, foreground="#444", wraplength=352,
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
        ttk.Frame(body, width=386, height=1).grid(row=8, column=0, columnspan=2)

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
