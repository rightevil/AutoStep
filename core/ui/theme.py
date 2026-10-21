"""配色与主题。

界面统一走 sv-ttk（Sun Valley，Win11 风格）；没装就退回系统 vista 主题，
功能不受影响，只是回到老样子。这里只做两件事：套主题、给 tk 原生控件
（Text / Listbox）提供与当前主题匹配的颜色——ttk 会自动跟着主题变，
tk 原生控件不会。
"""
from __future__ import annotations

from typing import Dict

MODES = ("light", "dark")

# sv-ttk 的 card 是白/深灰卡片，stripe 是隔行底色（表格没分隔线时靠它分行的）
_PALETTES: Dict[str, Dict[str, str]] = {
    "light": {
        "card": "#ffffff",
        "stripe": "#f4f5f7",
        "muted": "#6b6b6b",
        "text": "#1c1c1c",
        "err": "#c00000",
        "ok": "#0a7d33",
    },
    "dark": {
        "card": "#272727",
        "stripe": "#2e2e2e",
        "muted": "#a6a6a6",
        "text": "#eaeaea",
        "err": "#ff8080",
        "ok": "#6ccb7b",
    },
}


def palette(mode: str) -> Dict[str, str]:
    return _PALETTES.get(mode if mode in MODES else "light", _PALETTES["light"])


def apply(mode: str) -> bool:
    """套用主题。返回 False 表示没装 sv-ttk，调用方应保持系统默认主题。"""
    from tkinter import ttk

    try:
        import sv_ttk  # type: ignore
    except Exception:
        return False
    try:
        sv_ttk.set_theme("dark" if mode == "dark" else "light")
    except Exception:
        return False
    # 灰字提示：主题里统一定义一次，各对话框直接 style="Hint.TLabel"
    ttk.Style().configure("Hint.TLabel", foreground=palette(mode)["muted"])
    return True
