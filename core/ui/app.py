"""主窗口。"""
from __future__ import annotations

import queue
import subprocess
import time
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from .. import capture, executor, winsys
from .. import profile as profile_mod
from .. import trigger as trigger_mod
from ..config import APP_ID, APP_NAME, LEGACY_IDS
from ..scheduler import Scheduler, append_log_file
from ..store import Store, now_str, parse_dt

from . import theme
from .common import FONT, FONT_BOLD, FONT_MONO
from .plan_dialog import PlanDialog
from .profile_dialog import ProfileDialog
from .prompts import KeyDialog, SimplePrompt, TextDialog
from .settings_page import SettingsPage

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
        self._closing = False
        self._after_id: Optional[str] = None

        # 设置项的状态变量：由「设置」对话框编辑，主界面不再摆这些控件
        self.var_delay = tk.DoubleVar(value=1.0)
        self.var_act = tk.DoubleVar(value=1.0)
        self.var_shot = tk.BooleanVar(value=True)
        self.var_wake = tk.BooleanVar(value=True)
        self.var_tray = tk.BooleanVar(value=True)
        self.var_boot = tk.BooleanVar(value=False)
        self.var_dark = tk.BooleanVar(value=False)

        self.root.title(f"{APP_NAME} · 定时执行")
        self.root.geometry("1140x856+60+24")
        self.root.minsize(1080, 680)
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
        self._after_id = self.root.after(120, self._drain)
        self._log("已启动。设置好动作与计划后，可最小化到托盘待命。")

    # ---------------------------------------------------------------- 样式

    def _init_style(self) -> None:
        self.theme_mode = "dark" if self.store.settings.get("dark_ui") else "light"
        self.pal = theme.palette(self.theme_mode)
        self.theme_ok = theme.apply(self.theme_mode)
        self._style_ttk()

    def _style_ttk(self) -> None:
        """字体与行高。换主题会重置 ttk 里的这些配置，所以初始化与切换都要调一次。"""
        style = ttk.Style()
        style.configure(".", font=FONT)
        style.configure("Treeview", font=FONT, rowheight=26)
        style.configure("Treeview.Heading", font=FONT_BOLD)

    def _stripe(self, tv: ttk.Treeview) -> None:
        """隔行淡色底。表格没有横向分隔线，靠这个分行的。"""
        tv.tag_configure("odd", background=self.pal["stripe"])
        for i, iid in enumerate(tv.get_children()):
            tv.item(iid, tags=("odd",) if i % 2 else ())

    def _apply_theme(self) -> None:
        """切主题。ttk 控件自动跟着变，tk 原生控件（日志框）要手动刷。"""
        self.theme_mode = "dark" if self.var_dark.get() else "light"
        self.pal = theme.palette(self.theme_mode)
        self.theme_ok = theme.apply(self.theme_mode)
        self._style_ttk()
        self.txt.configure(
            bg=self.pal["card"], fg=self.pal["text"], insertbackground=self.pal["text"]
        )
        self.txt.tag_configure("err", foreground=self.pal["err"])
        self.txt.tag_configure("ok", foreground=self.pal["ok"])
        self._stripe(self.tv_steps)
        self._stripe(self.tv_plans)

    def _on_theme_toggle(self) -> None:
        self._apply_theme()
        self._save_settings()
        if not self.theme_ok:
            self._log("⚠ 没找到 sv-ttk 主题包，界面保持系统默认样式")

    # ---------------------------------------------------------------- 布局

    def _build(self) -> None:
        # 状态栏先按 bottom 打包，末尾再建的话会被上面 expand 的日志区挤出窗口。
        # 「设置」也放这儿：全局入口，不属于任何一个区块。
        self.var_status = tk.StringVar(value="就绪")
        foot = ttk.Frame(self.root)
        foot.pack(fill="x", side="bottom")
        ttk.Separator(foot).pack(fill="x", padx=12)
        frow = ttk.Frame(foot)
        frow.pack(fill="x", padx=14, pady=6)
        ttk.Label(frow, textvariable=self.var_status, anchor="w", style="Hint.TLabel").pack(
            side="left", fill="x", expand=True)
        self.root.option_add("*TCombobox*Listbox.font", FONT)

        # 设置与主界面同级：两个标签页，切页就到，不用再多一个弹窗
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, pady=(10, 0))
        self.nb = nb
        page = ttk.Frame(nb)
        nb.add(page, text="  执行  ")
        nb.add(SettingsPage(nb, self), text="  设置  ")

        # ---- 目标应用（档案）----
        frm_t = ttk.LabelFrame(page, text=" 目标应用（跟随当前序列）")
        frm_t.pack(fill="x", padx=12, pady=(12, 10))
        row = ttk.Frame(frm_t)
        row.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(row, text="档案", width=6).pack(side="left")
        self.cmb_prof = ttk.Combobox(row, width=30, state="readonly")
        self.cmb_prof.pack(side="left", padx=(2, 10))
        self.cmb_prof.bind("<<ComboboxSelected>>", self._on_pick_profile)
        ttk.Button(row, text="新建档案", width=9, command=self._new_profile).pack(side="left", padx=(0, 4))
        ttk.Button(row, text="编辑档案", width=9, command=self._edit_profile).pack(side="left", padx=(0, 4))
        ttk.Button(row, text="检测", width=6, command=self._test_target).pack(side="left")
        self.lbl_target = ttk.Label(row, text="", style="Hint.TLabel")
        self.lbl_target.pack(side="left", padx=12)

        row2 = ttk.Frame(frm_t)
        row2.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Label(row2, text="窗口", width=6).pack(side="left")
        self.cmb_win = ttk.Combobox(row2, width=50, state="readonly")
        self.cmb_win.pack(side="left", padx=(2, 8), fill="x", expand=True)
        self.cmb_win.bind("<<ComboboxSelected>>", self._on_pick_window)
        # 输入方式是从档案推出来的，不是可调设置，所以挂在档案这一栏，跟着档案一起刷新
        self.lbl_input = ttk.Label(row2, text="选中窗口即写入档案", style="Hint.TLabel")
        self.lbl_input.pack(side="left")

        # ---- 动作序列 ----
        frm_s = ttk.LabelFrame(page, text=" 动作序列（从上到下即执行顺序）")
        frm_s.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        bar = ttk.Frame(frm_s)
        bar.pack(fill="x", padx=12, pady=(10, 0))
        ttk.Label(bar, text="序列", width=6).pack(side="left")
        self.cmb_seq = ttk.Combobox(bar, width=28, state="readonly")
        self.cmb_seq.pack(side="left", padx=(2, 10))
        self.cmb_seq.bind("<<ComboboxSelected>>", self._on_seq_change)
        ttk.Button(bar, text="新建", width=6, command=self._new_seq).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="重命名", width=7, command=self._rename_seq).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="删除", width=6, command=self._del_seq).pack(side="left")

        cols = ("idx", "type", "pos", "content")
        self.tv_steps = ttk.Treeview(frm_s, columns=cols, show="headings", height=4)
        for c, w, txt in (
            ("idx", 44, "#"),
            ("type", 70, "类型"),
            ("pos", 130, "位置(%)"),
            ("content", 620, "内容 / 说明"),
        ):
            self.tv_steps.heading(c, text=txt)
            self.tv_steps.column(c, width=w, anchor="w" if c == "content" else "center")
        self.tv_steps.pack(fill="both", expand=True, padx=12, pady=10)
        self.tv_steps.bind("<Double-1>", lambda e: self._edit_step())

        bar2 = ttk.Frame(frm_s)
        bar2.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(bar2, text="+ 点击", width=8, command=self._add_click).pack(side="left", padx=(0, 4))
        ttk.Button(bar2, text="+ 输入", width=8, command=self._add_type).pack(side="left", padx=(0, 4))
        ttk.Button(bar2, text="+ 发送", width=8, command=self._add_send).pack(side="left", padx=(0, 4))
        ttk.Button(bar2, text="+ 按键", width=8, command=self._add_key).pack(side="left")
        ttk.Separator(bar2, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar2, text="编辑", width=6, command=self._edit_step).pack(side="left", padx=(0, 4))
        ttk.Button(bar2, text="上移", width=6, command=lambda: self._move(-1)).pack(side="left", padx=(0, 4))
        ttk.Button(bar2, text="下移", width=6, command=lambda: self._move(1)).pack(side="left", padx=(0, 4))
        ttk.Button(bar2, text="删除", width=6, command=self._del_step).pack(side="left")
        # 主操作给强调色，其余保持默认，一眼能看出该点哪个
        ttk.Button(bar2, text="试运行一次", style="Accent.TButton",
                   command=self._run_now).pack(side="right")

        # ---- 计划 ----
        frm_p = ttk.LabelFrame(page, text=" 计划")
        frm_p.pack(fill="x", padx=12, pady=(0, 10))
        pcols = ("name", "seq", "when", "repeat", "state", "next", "status")
        self.tv_plans = ttk.Treeview(frm_p, columns=pcols, show="headings", height=5)
        for c, w, txt, anc in (
            ("name", 140, "计划名称", "w"),
            ("seq", 280, "动作序列 / 应用", "w"),
            ("when", 140, "设定时间", "center"),
            ("repeat", 96, "触发方式", "center"),
            ("state", 60, "状态", "center"),
            ("next", 96, "下次", "center"),
            ("status", 120, "上次结果", "w"),
        ):
            self.tv_plans.heading(c, text=txt)
            self.tv_plans.column(c, width=w, anchor=anc)
        self.tv_plans.pack(fill="both", expand=True, padx=12, pady=10)
        pbar = ttk.Frame(frm_p)
        pbar.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(pbar, text="+ 新计划", width=9, style="Accent.TButton",
                   command=self._new_plan).pack(side="left", padx=(0, 4))
        ttk.Button(pbar, text="编辑", width=6, command=self._edit_plan).pack(side="left", padx=(0, 4))
        ttk.Button(pbar, text="启用/停用", width=9, command=self._toggle_plan).pack(side="left", padx=(0, 4))
        ttk.Button(pbar, text="删除", width=6, command=self._del_plan).pack(side="left")
        self.tv_plans.bind("<Double-1>", lambda e: self._edit_plan())

        # ---- 日志 ----
        frm_l = ttk.LabelFrame(page, text=" 运行日志")
        frm_l.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.txt = tk.Text(frm_l, height=5, font=FONT_MONO, wrap="word", state="disabled",
                           bg=self.pal["card"], fg=self.pal["text"],
                           insertbackground=self.pal["text"], relief="flat",
                           highlightthickness=0, borderwidth=0, padx=10, pady=8)
        sb = ttk.Scrollbar(frm_l, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 8), pady=10)
        self.txt.pack(fill="both", expand=True, padx=(12, 0), pady=10)
        self.txt.tag_configure("err", foreground=self.pal["err"])
        self.txt.tag_configure("ok", foreground=self.pal["ok"])


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
        if self._closing:      # 已经退出，别再往销毁后的 root 上排回调
            return
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
                    return
        except queue.Empty:
            pass
        # 有消息就立刻再看；空闲（尤其缩到托盘后）降频轮询，待命时几乎不占 CPU
        if got:
            wait = 15
        else:
            wait = 800 if self.root.state() == "withdrawn" else 200
        self._after_id = self.root.after(wait, self._drain)

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
            self.lbl_input.configure(
                text=f"选中窗口即写入档案 · 输入 {i.get('mode', 'auto')} · {clear} · 发送 {send}")
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
            self.lbl_target.configure(text="未选择序列", foreground=self.pal["err"])
            return
        if not profile_mod.has_target(prof):
            self.target_hwnd = 0
            self.lbl_target.configure(text="✗ 档案还没设目标窗口", foreground=self.pal["err"])
            return
        hwnd = profile_mod.match_target(prof, self.target_hwnd)
        if hwnd:
            self.target_hwnd = hwnd
            info = winsys.window_info(hwnd)
            _, _, w, h = winsys.client_rect(hwnd)
            self.lbl_target.configure(
                text=f"✓ {info['process']} · 客户区 {w}×{h}", foreground=self.pal["ok"]
            )
        else:
            self.target_hwnd = 0
            self.lbl_target.configure(text="✗ 该应用的窗口没找到", foreground=self.pal["err"])

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
        self.var_dark.set(bool(s.get("dark_ui", False)))

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
        s["dark_ui"] = bool(self.var_dark.get())
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

        from ..config import APP_DIR

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
        self._stripe(self.tv_steps)
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
            when_disp = trigger_mod.when_text(p.get("trigger"))
            if when_disp[:2] == "20" and len(when_disp) > 11:
                when_disp = when_disp[5:]     # 完整日期省掉年份，列宽才放得下
            status = p.get("last_status") or ""
            if len(status) > 16:
                status = status[:16] + "…"
            self.tv_plans.insert(
                "", "end", iid=str(i),
                values=(p.get("name", ""), seq_name, when_disp, repeat, state, nxt, status),
            )
        self._stripe(self.tv_plans)
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

            from ..icon import make_icon

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
        self._closing = True
        self.scheduler.stop()
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        self.root.destroy()


# ==================================================================== 对话框

