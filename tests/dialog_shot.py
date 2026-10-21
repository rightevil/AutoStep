"""截图检查计划编辑对话框与日历对话框的布局。"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from typing import Any, Dict

import mss
import mss.tools

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import winsys  # noqa: E402

winsys.set_dpi_awareness()

from core.ui import CalendarDialog, PlanDialog  # noqa: E402

SHOTS = Path(__file__).resolve().parent.parent / "data" / "shots"


def grab_toplevel(root, name):
    """抓取 root 下最后一个 Toplevel 的窗口区域。"""
    wins = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    if not wins:
        print("没有找到对话框")
        return
    w = wins[-1]
    w.attributes("-topmost", True)
    w.deiconify()
    w.lift()
    w.focus_force()
    w.update_idletasks()
    w.update()
    time.sleep(0.6)
    x, y = w.winfo_rootx() - 10, w.winfo_rooty() - 34
    ww, hh = w.winfo_width() + 20, w.winfo_height() + 48
    with mss.mss() as sct:
        shot = sct.grab({"left": max(0, x), "top": max(0, y), "width": ww, "height": hh})
        out = SHOTS / f"dialog_{name}.png"
        mss.tools.to_png(shot.rgb, shot.size, output=str(out))
    print("saved", out, w.winfo_width(), w.winfo_height())
    w.destroy()


def main():
    root = tk.Tk()
    root.geometry("260x120+40+40")

    plan: Dict[str, Any] = {
        "id": "x1", "name": "work", "seq_id": "s1",
        "run_at": "2026-10-22 03:00", "repeat": "daily",
    }
    seq_map = {"测试workbuddy（3步）": "s1", "另一套动作（1步）": "s2"}

    root.after(900, lambda: grab_toplevel(root, "plan_edit"))
    PlanDialog.ask(root, seq_map, "s1", plan=plan)

    root.after(900, lambda: grab_toplevel(root, "calendar"))
    CalendarDialog.ask(root)

    root.destroy()
    print("done")


if __name__ == "__main__":
    main()
