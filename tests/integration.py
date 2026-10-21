"""端到端集成测试：开一个自检窗口代替 Codex，真实跑一遍点击/输入/按键。

注意：测试期间会接管鼠标约 5 秒。
"""
from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import executor, winsys  # noqa: E402
from core import profile as profile_mod  # noqa: E402

winsys.set_dpi_awareness()

TITLE = "autostep-selftest"
state = {"clicks": 0, "got": "", "dots": 0}


def ratio_of(widget, hwnd) -> dict:
    """控件中心换算成客户区百分比矩形。"""
    l, t, cw, ch = winsys.client_rect(hwnd)
    w, h = widget.winfo_width(), widget.winfo_height()
    cx = widget.winfo_rootx() + w / 2
    cy = widget.winfo_rooty() + h / 2
    rx, ry = (cx - l) / cw, (cy - t) / ch
    pad_x = 4 / cw
    pad_y = 3 / ch
    return {
        "x1": round(rx - pad_x, 4),
        "y1": round(ry - pad_y, 4),
        "x2": round(rx + pad_x, 4),
        "y2": round(ry + pad_y, 4),
    }


def main() -> int:
    root = tk.Tk()
    root.title(TITLE)
    root.geometry("620x240+380+260")
    root.attributes("-topmost", True)

    ttk.Label(root, text="AutoStep 自检窗口（测试中请勿动鼠标）", font=("Microsoft YaHei UI", 11)).pack(pady=10)

    entry = ttk.Entry(root, width=52, font=("Microsoft YaHei UI", 11))
    entry.pack(pady=8)
    entry.insert(0, "OLD-CONTENT")  # 用于验证 Ctrl+A 清空

    btn = ttk.Button(root, text="确认按钮", width=16)
    btn.pack(pady=6)

    lbl = ttk.Label(root, text="", foreground="#0a7d33")
    lbl.pack()

    def on_click():
        state["clicks"] += 1
        state["got"] = entry.get()
        lbl.configure(text=f"已点击 {state['clicks']} 次 · 内容长度 {len(state['got'])}")

    btn.configure(command=on_click)
    root.update()

    hwnd = winsys.find_target("python", TITLE)
    if not hwnd:
        print("FAIL 无法定位自检窗口")
        return 1
    print(f"自检窗口 hwnd={hwnd}  客户区={winsys.client_rect(hwnd)}")

    rect_entry = ratio_of(entry, hwnd)
    rect_btn = ratio_of(btn, hwnd)
    print(f"entry rect={rect_entry}")
    print(f"btn   rect={rect_btn}")

    text = "Hello Codex 你好，这是一次自检。"
    steps = [
        {"type": "click", "rect": rect_entry, "note": "点输入框"},
        {"type": "type", "rect": rect_entry, "text": text, "clear_first": True},
        {"type": "click", "rect": rect_btn, "note": "点确认"},
        {"type": "key", "combo": "tab"},
    ]

    settings = {
        "target_process": "python",
        "target_title": TITLE,
        "step_delay": 0.7,
        "activate_delay": 0.7,
        "input_mode": "auto",
        "clear_first": True,
        "screenshot_after_run": False,
    }

    logs = []
    res_box = {}

    def worker():
        res_box["r"] = executor.execute(steps, settings, logs.append, hwnd)

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    t0 = time.time()
    while th.is_alive() and time.time() - t0 < 40:
        root.update()
        time.sleep(0.02)
    for _ in range(10):
        root.update()
        time.sleep(0.05)

    ok = 0
    fail = 0

    def check(name, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  PASS  {name} {extra}")
        else:
            fail += 1
            print(f"  FAIL  {name} {extra}")

    print("\n执行日志:")
    for line in logs:
        print("   ", line)

    r = res_box.get("r") or {}
    check("执行返回成功", r.get("ok") is True, str(r.get("message")))
    check("按钮收到点击", state["clicks"] >= 1, f"clicks={state['clicks']}")
    check("输入内容完全一致", state["got"] == text, repr(state["got"]))
    check("旧内容被清空", "OLD-CONTENT" not in state["got"], repr(state["got"]))
    check("中文正常写入", "你好" in state["got"], repr(state["got"]))
    check("Unicode 标点正常", "，" in state["got"] and "。" in state["got"])

    # ---- 第二阶段：档案驱动 ----
    # 全局设置故意指向不存在的进程，只有档案能找对窗口：
    # 跑通就证明目标来自序列所属档案，而不是全局设置。
    prof = profile_mod.normalize(
        {
            "id": "selftest",
            "name": "自检窗口",
            "match": {"process": "python", "title": TITLE},
            "input": {"mode": "paste", "clear_first": True},
            "send": {"combo": "tab"},
        },
        "selftest",
    )
    bad_settings = dict(
        settings, target_process="NoSuchProcessXYZ", target_title="", input_mode="keys"
    )
    text2 = "档案驱动 paste 测试"
    steps2 = [
        {"type": "click", "rect": rect_entry},
        {"type": "type", "rect": rect_entry, "text": text2},
        {"type": "key", "combo": profile_mod.SEND_ALIAS},
    ]
    state["got"] = ""
    state["clicks"] = 0
    logs2 = []
    box2 = {}

    def worker2():
        box2["r"] = executor.execute(steps2, bad_settings, logs2.append, 0, prof)

    th2 = threading.Thread(target=worker2, daemon=True)
    th2.start()
    t1 = time.time()
    while th2.is_alive() and time.time() - t1 < 40:
        root.update()
        time.sleep(0.02)
    for _ in range(10):
        root.update()
        time.sleep(0.05)

    print("\n档案模式日志:")
    for line in logs2:
        print("   ", line)

    r2 = box2.get("r") or {}
    typed = entry.get()
    check("档案模式：全局目标无效时仍能跑通", r2.get("ok") is True, str(r2.get("message")))
    check("档案模式：内容一致（读输入框实际值）", typed == text2, repr(typed))
    check("档案模式：@send 解析成档案里的按键",
          any("-> tab" in line for line in logs2), str(logs2[-1] if logs2 else ""))

    root.destroy()
    print(f"\n结果: {ok} 通过, {fail} 失败")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
