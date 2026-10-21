"""用临时数据渲染主界面并截图，检查「应用档案」改版后的布局。

不碰真实 data/store.json，也不需要单实例互斥锁，所以可以和正在运行的
AutoStep 并存。
"""
import sys
import time
from pathlib import Path

import mss
import mss.tools

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from core import winsys  # noqa: E402

winsys.set_dpi_awareness()

import tkinter as tk  # noqa: E402

from core.store import Store  # noqa: E402
from core.ui import App  # noqa: E402

tmp_store = HERE / "tests" / "_ui_store.json"
tmp_prof = HERE / "tests" / "profiles.json"
out = HERE / "data" / "shots" / "ui_profile.png"
for p in (tmp_store, tmp_prof):
    p.unlink(missing_ok=True)

root = tk.Tk()
app = App(root, Store(tmp_store, tmp_prof))
root.attributes("-topmost", True)
root.lift()
root.focus_force()
for _ in range(6):
    root.update_idletasks()
    root.update()
    time.sleep(0.15)

x, y = root.winfo_rootx(), root.winfo_rooty()
w, h = root.winfo_width(), root.winfo_height()
print(f"window {w}x{h} at ({x},{y})")
with mss.mss() as sct:
    shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
    mss.tools.to_png(shot.rgb, shot.size, output=str(out))
print("saved", out)

root.destroy()
for p in (tmp_store, tmp_prof):
    p.unlink(missing_ok=True)
