"""应用档案对话框。"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional

from .. import profile as profile_mod

from .common import FONT, FONT_BOLD


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
        ttk.Label(body, text="包含即可，如 ChatGPT 能匹配 ChatGPT.exe", style="Hint.TLabel").grid(
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
            body, text="auto=含中文走剪贴板；keys=一律逐键；paste=一律粘贴", style="Hint.TLabel"
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
        ttk.Label(body, text="「+ 发送」动作按这里设置的键发出去", style="Hint.TLabel").grid(
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

