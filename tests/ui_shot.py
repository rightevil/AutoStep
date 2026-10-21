"""启动应用 -> 截图自检 -> 关闭，用于验证界面布局。"""
import subprocess
import sys
import time
from pathlib import Path

import mss
import mss.tools

HERE = Path(__file__).resolve().parent.parent
out = HERE / "data" / "shots" / "ui_check.png"

p = subprocess.Popen([str(HERE / ".venv" / "Scripts" / "pythonw.exe"), "main.py"], cwd=str(HERE))
time.sleep(5)
sys.path.insert(0, str(HERE))
from core import winsys  # noqa: E402

winsys.set_dpi_awareness()
hwnd = winsys.find_target("pythonw", "AutoStep")
print("hwnd =", hwnd)
if hwnd:
    winsys.activate(hwnd)
    time.sleep(1.2)
try:
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        mss.tools.to_png(shot.rgb, shot.size, output=str(out))
    print("saved", out)
finally:
    p.terminate()
    p.wait(timeout=10)
