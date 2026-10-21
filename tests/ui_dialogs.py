"""逐个打开每个对话框再关掉，专门用来抓「拆文件后漏 import」这类错误。

拆包（core/ui.py -> core/ui/ 包）时最容易犯的错是某个类少了 FONT_BOLD、
少了一级相对导入，而这些只有真的把窗口建出来才会炸。所以这里不做断言，
只要求每个对话框都能成功构建出控件。
"""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import winsys  # noqa: E402

winsys.set_dpi_awareness()

from core.ui import (  # noqa: E402
    CalendarDialog,
    KeyDialog,
    PlanDialog,
    ProfileDialog,
    SimplePrompt,
    TextDialog,
)

CASES = [
    ("SimplePrompt 单行输入", lambda r: SimplePrompt.ask(r, "重命名", "名称", "测试")),
    ("TextDialog 多行文本", lambda r: TextDialog.ask(r, "输入文本", "内容", "你好")),
    ("KeyDialog 按键", lambda r: KeyDialog.ask(r, "发送键", "enter")),
    ("ProfileDialog 新建", lambda r: ProfileDialog.ask(r, None)),
    ("ProfileDialog 编辑", lambda r: ProfileDialog.ask(
        r, {"name": "ChatGPT", "match": {"process": "ChatGPT", "title": ""}}, True)),
    ("CalendarDialog 日历", lambda r: CalendarDialog.ask(r)),
    ("PlanDialog 计划", lambda r: PlanDialog.ask(
        r, {"默认序列（3 步）": "s1"}, "s1",
        {"name": "测试", "seq_id": "s1",
         "trigger": {"kind": "calendar", "times": ["09:00"], "days": []}})),
]

results = []

for name, build in CASES:
    root = tk.Tk()
    root.geometry("420x320+40+40")
    root.update()
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except Exception:
        pass

    stat = {"widgets": 0, "error": ""}

    def closer():
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                stat["widgets"] = sum(1 for _ in _walk(w))
                w.destroy()

    def _walk(w):
        for c in w.winfo_children():
            yield c
            yield from _walk(c)

    root.after(350, closer)
    try:
        build(root)
    except Exception as e:  # noqa: BLE001
        stat["error"] = f"{type(e).__name__}: {e}"
    root.destroy()

    ok = not stat["error"] and stat["widgets"] >= 4
    results.append((name, ok))
    detail = stat["error"] or f"{stat['widgets']} 个控件"
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<22} {detail}")

passed = sum(1 for _, ok in results if ok)
print(f"\n对话框构建：{passed} 通过 / {len(results) - passed} 失败")
sys.exit(0 if passed == len(results) else 1)
