"""设置页结构测试：设置必须是和主界面同级的标签页，不能是弹窗、也不能挤在主页。

顺便验两条行为：改设置即时落盘（没有「保存」按钮），以及主界面上不再残留设置控件。
用法：.venv/Scripts/python.exe tests/ui_settings_tab.py
"""
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import winsys  # noqa: E402

winsys.set_dpi_awareness()

from tkinter import ttk  # noqa: E402

from core.store import Store  # noqa: E402
from core.ui import App  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  <- {detail}" if detail and not ok else ""))


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


HERE = Path(__file__).resolve().parent.parent
tmp_store = HERE / "tests" / "_tab_store.json"
tmp_prof = HERE / "tests" / "_tab_profiles.json"
for p in (tmp_store, tmp_prof):
    p.unlink(missing_ok=True)

store = Store(tmp_store, tmp_prof)
root = tk.Tk()
root.geometry("1000x760+0+0")
app = App(root, store)
root.update_idletasks()

tabs = app.nb.tabs()
check("有标签页容器", len(tabs) == 2, f"{len(tabs)} 页")
check("页签是「执行」「设置」",
      [app.nb.tab(t, "text").strip() for t in tabs] == ["执行", "设置"],
      str([app.nb.tab(t, "text") for t in tabs]))

page_main = root.nametowidget(tabs[0])
page_set = root.nametowidget(tabs[1])

main_checks = [w for w in walk(page_main) if isinstance(w, (ttk.Checkbutton, tk.Checkbutton))]
check("主界面已无设置开关", not main_checks, f"还剩 {len(main_checks)} 个")

set_spins = [w for w in walk(page_set) if isinstance(w, ttk.Spinbox)]
set_checks = [w for w in walk(page_set) if isinstance(w, (ttk.Checkbutton, tk.Checkbutton))]
check("设置页有 2 个数值输入", len(set_spins) == 2, str(len(set_spins)))
check("设置页有 5 个开关", len(set_checks) == 5, str(len(set_checks)))

# 改数值后失焦要落盘（这页没有保存按钮）
root.update()
sp = set_spins[0]
sp.delete(0, "end")
sp.insert(0, "2.4")
sp.event_generate("<FocusOut>")
root.update_idletasks()
check("改延时即时保存", store.settings.get("step_delay") == 2.4, str(store.settings.get("step_delay")))

# 深色开关在设置页里，点一下要真的切主题并落盘
app.var_dark.set(True)
app._on_theme_toggle()
root.update_idletasks()
check("设置页切深色生效", app.theme_mode == "dark" and store.settings.get("dark_ui") is True,
      f"{app.theme_mode} / {store.settings.get('dark_ui')}")
app.var_dark.set(False)
app._on_theme_toggle()
root.update_idletasks()

# 切页不该影响状态栏（状态栏在标签页之外，属于整窗）
app.nb.select(1)
root.update_idletasks()
check("切到设置页", app.nb.index("current") == 1, str(app.nb.index("current")))
check("状态栏仍在", app.var_status.get() != "", app.var_status.get())
app.nb.select(0)
root.update_idletasks()
check("能切回执行页", app.nb.index("current") == 0, str(app.nb.index("current")))

app._quit()
for p in (tmp_store, tmp_prof):
    p.unlink(missing_ok=True)

passed = sum(1 for _, ok, _ in results if ok)
print(f"\n设置标签页：{passed} 通过 / {len(results) - passed} 失败")
sys.exit(0 if passed == len(results) else 1)
