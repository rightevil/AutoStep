"""计划对话框的交互测试：改时刻 / 点星期 / 切换触发方式时，底部说明要跟着变。

不截图、纯断言，跑完自动关闭。需要桌面环境（会短暂弹出对话框）。
用法：.venv/Scripts/python.exe tests/ui_plan_dialog.py
"""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import ui, winsys  # noqa: E402

winsys.set_dpi_awareness()

SEQ = {"测试workbuddy（3 步）": "abc12345"}
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  <- {detail}" if detail and not ok else ""))


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


def summary(win):
    for w in walk(win):
        if isinstance(w, ttk.Label):
            try:
                tv = str(w.cget("textvariable"))
            except Exception:
                continue
            if tv:
                v = str(w.getvar(tv))
                if v and ("跑一次" in v or "至少" in v or "格式" in v or "间隔要" in v):
                    return v
    return "<空>"


def find(win, cls, text):
    for w in walk(win):
        if isinstance(w, cls) and str(w.cget("text")) == text:
            return w
    return None


def time_entries(win):
    return [w for w in walk(win) if isinstance(w, ttk.Entry)
            and str(w.cget("state")) != "readonly" and str(w.cget("width")) == "8"]


def run_steps(root):
    win = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)][0]
    root.update()
    width0 = win.winfo_width()

    check("初始：两个时刻 → 说明写一天 2 次",
          summary(win) == "每天 09:00、13:30 各跑一次，一天 2 次。", summary(win))

    find(win, (ttk.Button, tk.Button), "+ 再加一个时刻").invoke()
    root.update()
    check("加一个时刻 → 变成三行、说明写 3 次",
          len(time_entries(win)) == 3 and "一天 3 次" in summary(win), summary(win))

    find(win, tk.Checkbutton, "三").invoke()
    root.update()
    check("点星期三 → 说明改成每周三", summary(win).startswith("每周三的"), summary(win))

    find(win, tk.Checkbutton, "三").invoke()
    find(win, tk.Checkbutton, "一").invoke()
    root.update()
    check("取消三、改点一 → 说明只剩每周一", summary(win).startswith("每周一的"), summary(win))

    find(win, ttk.Radiobutton, "间隔").invoke()
    root.update()
    check("切到间隔 → 说明变成每 3 小时", "每 3 小时跑一次" in summary(win), summary(win))
    check("切到间隔 → 窗口宽度不变", win.winfo_width() == width0,
          f"{win.winfo_width()} vs {width0}")
    check("切到间隔 → 时刻行收起来了", len(time_entries(win)) == 0)

    find(win, ttk.Radiobutton, "只跑一次").invoke()
    root.update()
    check("切到只跑一次 → 说明写明只跑一次", "之后不再运行" in summary(win), summary(win))

    find(win, ttk.Radiobutton, "定点").invoke()
    root.update()
    check("切回定点 → 三个时刻还在、星期还勾着",
          len(time_entries(win)) == 3 and summary(win).startswith("每周一的"), summary(win))

    for item in time_entries(win):
        if str(item.get()) == "14:00":
            for c in item.master.winfo_children():
                if isinstance(c, (ttk.Button, tk.Button)) and str(c.cget("text")) == "×":
                    c.invoke()
    root.update()
    check("删掉 14:00 → 回到两行、说明写 2 次",
          len(time_entries(win)) == 2 and "一天 2 次" in summary(win), summary(win))

    win.destroy()
    root.quit()


root = tk.Tk()
root.geometry("600x600+0+0")
root.configure(bg="white")
root.update()
style = ttk.Style()
try:
    style.theme_use("vista")
except Exception:
    pass
style.configure(".", font=ui.FONT)

root.after(700, lambda: run_steps(root))
ui.PlanDialog.ask(root, SEQ, "abc12345",
                  {"name": "凌晨执行", "seq_id": "abc12345",
                   "trigger": {"kind": "calendar", "times": ["09:00", "13:30"], "days": []}})
root.destroy()

passed = sum(1 for _, ok, _ in results if ok)
print(f"\n对话框交互：{passed} 通过 / {len(results) - passed} 失败")
sys.exit(0 if passed == len(results) else 1)
