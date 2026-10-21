"""设置页：执行参数、系统行为、外观、文件位置。

和主界面是**同级标签页**，不是弹窗——想调设置就切页，看完切回来，
不占主界面宽度，也不多一层「保存 / 取消」的心智负担（改一下即生效）。
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Any

from ..config import DATA_DIR, LOG_DIR


class SettingsPage(ttk.Frame):
    """控件直接绑 App 上的状态变量与保存方法，所以这页没有「保存」按钮。

    App 是唯一真相：`var_delay` 等变量和 `_save_settings` / `_on_*_toggle`
    都还在 App 上，这里只负责摆控件，不另存一份值。
    """

    def __init__(self, parent, app: Any):
        super().__init__(parent)
        self.app = app

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=14, pady=(14, 0))
        wrap.columnconfigure(0, weight=1, uniform="col")
        wrap.columnconfigure(1, weight=1, uniform="col")

        # ---- 执行 ----
        g1 = ttk.LabelFrame(wrap, text=" 执行")
        g1.grid(row=0, column=0, sticky="new", padx=(0, 10), pady=(0, 12))
        f1 = ttk.Frame(g1)
        f1.pack(fill="x", padx=14, pady=(12, 12))
        f1.columnconfigure(0, minsize=120)

        ttk.Label(f1, text="步间延时(秒)").grid(row=0, column=0, sticky="w", pady=(0, 8))
        sp1 = ttk.Spinbox(f1, from_=0.1, to=60, increment=0.1, width=8,
                          textvariable=app.var_delay, command=app._save_settings)
        sp1.grid(row=0, column=1, sticky="w", pady=(0, 8))
        ttk.Label(f1, text="激活等待(秒)").grid(row=1, column=0, sticky="w", pady=(0, 8))
        sp2 = ttk.Spinbox(f1, from_=0, to=30, increment=0.1, width=8,
                          textvariable=app.var_act, command=app._save_settings)
        sp2.grid(row=1, column=1, sticky="w", pady=(0, 8))
        # 手输数字不会触发 command，失焦或回车时补存一次
        for sp in (sp1, sp2):
            sp.bind("<FocusOut>", lambda e: app._save_settings())
            sp.bind("<Return>", lambda e: app._save_settings())

        ttk.Checkbutton(f1, text="执行后截图存证", variable=app.var_shot,
                        command=app._save_settings).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(f1, text="截图存在 data/shots，事后能核对点错了哪一步。",
                  style="Hint.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", padx=(24, 0))

        # ---- 系统 ----
        g2 = ttk.LabelFrame(wrap, text=" 系统")
        g2.grid(row=1, column=0, sticky="new", padx=(0, 10))
        f2 = ttk.Frame(g2)
        f2.pack(fill="x", padx=14, pady=(12, 12))
        ttk.Checkbutton(f2, text="执行前唤醒系统", variable=app.var_wake,
                        command=app._on_wake_toggle).pack(anchor="w")
        ttk.Label(f2, text="到点让睡着的电脑醒来执行；不勾则睡眠期间的计划直接跳过。",
                  style="Hint.TLabel").pack(anchor="w", padx=(24, 0), pady=(0, 8))
        ttk.Checkbutton(f2, text="关闭窗口时缩到托盘", variable=app.var_tray,
                        command=app._save_settings).pack(anchor="w", pady=(0, 8))
        ttk.Checkbutton(f2, text="开机自动启动", variable=app.var_boot,
                        command=app._on_autostart_toggle).pack(anchor="w")

        # ---- 外观 ----
        g3 = ttk.LabelFrame(wrap, text=" 外观")
        g3.grid(row=0, column=1, sticky="new", pady=(0, 12))
        f3 = ttk.Frame(g3)
        f3.pack(fill="x", padx=14, pady=(12, 12))
        cb_dark = ttk.Checkbutton(f3, text="深色界面", variable=app.var_dark,
                                  command=app._on_theme_toggle)
        cb_dark.pack(anchor="w")
        if app.theme_ok:
            ttk.Label(f3, text="切换后立即生效。", style="Hint.TLabel").pack(
                anchor="w", padx=(24, 0))
        else:
            # 没装 sv-ttk 就把开关灰掉，别让人点了没反应还以为坏了
            cb_dark.state(["disabled"])
            ttk.Label(f3, text="没装 sv-ttk 主题包，深色界面不可用。", style="Hint.TLabel").pack(
                anchor="w", padx=(24, 0))

        # ---- 文件位置 ----
        g4 = ttk.LabelFrame(wrap, text=" 文件位置")
        g4.grid(row=1, column=1, sticky="new")
        f4 = ttk.Frame(g4)
        f4.pack(fill="x", padx=14, pady=(12, 12))
        b4 = ttk.Frame(f4)
        b4.pack(anchor="w")
        ttk.Button(b4, text="数据目录", width=10,
                   command=lambda: self._open(DATA_DIR)).pack(side="left", padx=(0, 6))
        ttk.Button(b4, text="日志目录", width=10,
                   command=lambda: self._open(LOG_DIR)).pack(side="left")
        ttk.Label(f4, text="序列、应用档案、计划都在数据目录里，换机器直接拷走。",
                  style="Hint.TLabel", wraplength=470).pack(anchor="w", pady=(8, 0))

        ttk.Label(self, text="改动即时保存，切回「执行」页就生效。",
                  style="Hint.TLabel").pack(side="bottom", anchor="w", padx=16, pady=(0, 12))

    @staticmethod
    def _open(path) -> None:
        try:
            os.startfile(str(path))
        except Exception:
            pass
