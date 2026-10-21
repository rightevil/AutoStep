"""界面层：主窗口与各类对话框。

拆包只是为了别让单个文件涨到 1500 行，对外接口和原来一样——
`from core.ui import App`、`from core import ui; ui.PlanDialog` 都照旧能用。
"""
from __future__ import annotations

from .app import App
from .calendar_dialog import CalendarDialog
from .common import FONT, FONT_BOLD, FONT_MONO
from .plan_dialog import PlanDialog
from .profile_dialog import ProfileDialog
from .prompts import KeyDialog, SimplePrompt, TextDialog
from .settings_page import SettingsPage

__all__ = [
    "App",
    "CalendarDialog",
    "FONT",
    "FONT_BOLD",
    "FONT_MONO",
    "KeyDialog",
    "PlanDialog",
    "ProfileDialog",
    "SettingsPage",
    "SimplePrompt",
    "TextDialog",
]
