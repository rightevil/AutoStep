"""主题与配色测试：深浅切换要真的生效，切完字体/行高不能被重置。

不需要 sv-ttk，没装时只验「不报错 + 退回系统主题」这条退路。
用法：.venv/Scripts/python.exe tests/ui_theme.py
"""
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import winsys  # noqa: E402

winsys.set_dpi_awareness()

from tkinter import ttk  # noqa: E402

from core.store import Store  # noqa: E402
from core.ui import App, theme  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  <- {detail}" if detail and not ok else ""))


HERE = Path(__file__).resolve().parent.parent
tmp_store = HERE / "tests" / "_theme_store.json"
tmp_prof = HERE / "tests" / "_theme_profiles.json"
for p in (tmp_store, tmp_prof):
    p.unlink(missing_ok=True)

store = Store(tmp_store, tmp_prof)
has_theme = theme.apply("light")          # 先探一下装没装
store.settings["dark_ui"] = False

root = tk.Tk()
root.geometry("900x700+0+0")
app = App(root, store)
root.update_idletasks()

style = ttk.Style()
check("默认走浅色", app.theme_mode == "light", app.theme_mode)
check("字体已设", str(style.lookup(".", "font")) != "", str(style.lookup(".", "font")))
check("行高 26", style.lookup("Treeview", "rowheight") == 26, style.lookup("Treeview", "rowheight"))
if has_theme:
    check("主题已切到 sun-valley-light", style.theme_use() == "sun-valley-light", style.theme_use())
else:
    check("没装 sv-ttk 时退回系统主题", app.theme_ok is False, str(style.theme_use()))

light_bg = app.txt.cget("bg")

# 切到深色
app.var_dark.set(True)
app._on_theme_toggle()   # 走真实入口：切主题 + 存设置
root.update_idletasks()

check("切到深色", app.theme_mode == "dark", app.theme_mode)
check("日志框底色跟着换", app.txt.cget("bg") != light_bg, f"{light_bg} -> {app.txt.cget('bg')}")
check("日志框文字变浅", app.pal["text"] != "#1c1c1c", app.pal["text"])
check("切主题后行高还在", style.lookup("Treeview", "rowheight") == 26,
      style.lookup("Treeview", "rowheight"))
check("深色已存进设置", store.settings.get("dark_ui") is True, str(store.settings.get("dark_ui")))
if has_theme:
    check("主题已切到 sun-valley-dark", style.theme_use() == "sun-valley-dark", style.theme_use())

# 切回浅色
app.var_dark.set(False)
app._on_theme_toggle()
root.update_idletasks()
check("切回浅色", app.theme_mode == "light" and app.txt.cget("bg") == light_bg,
      f"{app.theme_mode} / {app.txt.cget('bg')}")
check("浅色已存进设置", store.settings.get("dark_ui") is False, str(store.settings.get("dark_ui")))

app._quit()
for p in (tmp_store, tmp_prof):
    p.unlink(missing_ok=True)

passed = sum(1 for _, ok, _ in results if ok)
print(f"\n主题与配色：{passed} 通过 / {len(results) - passed} 失败")
sys.exit(0 if passed == len(results) else 1)
