"""全局路径与默认配置。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---- 应用标识（唯一来源，别在别处硬编码）----
APP_NAME = "AutoStep"          # 显示名：窗口标题、托盘提示、消息框
APP_ID = "autostep"            # 机器标识：单实例 mutex、托盘 icon id、注册表项名
LEGACY_IDS = ("autocodex",)    # 改名前用过的标识，启动时清理残留


def _runtime_root() -> Path:
    """数据根目录。

    - 源码运行：项目根目录（data/ 与代码同级）
    - PyInstaller 打包后：exe 同级目录（便携语义）；若该处不可写（例如装在
      Program Files），退回 %APPDATA%\\AutoStep，否则计划会写不进去。
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        try:
            probe_dir = base / "data"
            probe_dir.mkdir(parents=True, exist_ok=True)
            probe = probe_dir / ".write_test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return base
        except OSError:
            return Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    return Path(__file__).resolve().parent.parent


APP_DIR = _runtime_root()
DATA_DIR = APP_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
SHOT_DIR = DATA_DIR / "shots"
STORE_PATH = DATA_DIR / "store.json"

for _d in (DATA_DIR, LOG_DIR, SHOT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {
    # ---- 以下四项已迁到「应用档案」（core/profile.py + data/profiles.json）----
    # 留在默认设置里只作两个用途：
    #   1) 老数据升级时，用它生成第一条「原设置」档案
    #   2) 极端情况下序列没有档案时，执行器退回这里的老行为
    "target_process": "ChatGPT",
    "target_title": "",
    "input_mode": "auto",     # auto | keys | paste
    "clear_first": True,
    # ---- 全局（跟节奏、跟系统相关，与应用无关）----
    "step_delay": 1.0,        # 每步之间的固定等待（秒）
    "activate_delay": 1.0,    # 窗口激活后额外等待（秒）
    "screenshot_after_run": True,
    "wake_before_run": True,
    "wake_lead_seconds": 90,  # 提前多久唤醒系统
    "minimize_to_tray": True,
    "autostart": False,
}
