"""全局路径与默认配置。"""
from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
SHOT_DIR = DATA_DIR / "shots"
STORE_PATH = DATA_DIR / "store.json"

for _d in (DATA_DIR, LOG_DIR, SHOT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    # 目标窗口匹配：进程名 + 标题关键字（大小写不敏感，包含即可）
    "target_process": "ChatGPT",
    "target_title": "",  # 留空=只按进程名匹配（Codex 界面在 ChatGPT 进程里，标题不稳定）
    # 回放节奏
    "step_delay": 1.0,        # 每步之间的固定等待（秒）
    "activate_delay": 1.0,    # 窗口激活后额外等待（秒）
    # 输入方式 auto: 纯 ASCII 走逐字符，含中文走剪贴板粘贴
    "input_mode": "auto",     # auto | keys | paste
    "clear_first": True,      # 输入前先 Ctrl+A 清空
    # 执行前后
    "screenshot_after_run": True,
    "wake_before_run": True,
    "wake_lead_seconds": 90,  # 提前多久唤醒系统
    "minimize_to_tray": True,
    "autostart": False,
}
