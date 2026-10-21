"""调度端到端测试：让计划在几秒后到点，验证自动触发全链路。

会接管鼠标约 5 秒。
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import winsys  # noqa: E402

winsys.set_dpi_awareness()

from core.scheduler import Scheduler  # noqa: E402
from core.store import Store  # noqa: E402

TITLE = "autostep-sched-test"
state = {"clicks": 0, "got": ""}


def ratio_of(widget, hwnd) -> dict:
    l, t, cw, ch = winsys.client_rect(hwnd)
    cx = widget.winfo_rootx() + widget.winfo_width() / 2
    cy = widget.winfo_rooty() + widget.winfo_height() / 2
    rx, ry = (cx - l) / cw, (cy - t) / ch
    return {
        "x1": round(rx - 4 / cw, 4),
        "y1": round(ry - 3 / ch, 4),
        "x2": round(rx + 4 / cw, 4),
        "y2": round(ry + 3 / ch, 4),
    }


def main() -> int:
    tmp = Path(__file__).parent / "_tmp_sched.json"
    tmp.unlink(missing_ok=True)

    root = tk.Tk()
    root.title(TITLE)
    root.geometry("620x220+380+300")
    root.attributes("-topmost", True)
    ttk.Label(root, text="调度自检窗口（测试中请勿动鼠标）",
              font=("Microsoft YaHei UI", 11)).pack(pady=10)
    entry = ttk.Entry(root, width=52, font=("Microsoft YaHei UI", 11))
    entry.pack(pady=6)
    btn = ttk.Button(root, text="确认", width=14)
    btn.pack(pady=6)
    lbl = ttk.Label(root, text="", foreground="#0a7d33")
    lbl.pack()

    def on_click():
        state["clicks"] += 1
        state["got"] = entry.get()
        lbl.configure(text=f"点击 {state['clicks']} 次")

    btn.configure(command=on_click)
    root.update()

    hwnd = winsys.find_target("python", TITLE)
    assert hwnd, "找不到自检窗口"

    store = Store(tmp)
    # 目标现在跟着序列所属的档案走，不再读全局设置
    prof = store.upsert_profile(
        {
            "id": "selftest",
            "name": "调度自检窗口",
            "match": {"process": "python", "title": TITLE},
            "input": {"mode": "auto", "clear_first": True},
            "send": {"combo": "enter"},
        }
    )
    store.settings.update({
        "step_delay": 0.5,
        "activate_delay": 0.6,
        "screenshot_after_run": False,
        "wake_before_run": True,
    })
    seq = store.default_sequence()
    seq["profile_id"] = prof["id"]
    seq["steps"] = [
        {"type": "click", "rect": ratio_of(entry, hwnd), "note": ""},
        {"type": "type", "rect": ratio_of(entry, hwnd), "text": "定时任务自动执行 OK", "clear_first": True},
        {"type": "click", "rect": ratio_of(btn, hwnd), "note": ""},
    ]
    store.save()

    plan = store.add_plan(name="调度测试", seq_id=seq["id"],
                          run_at=(datetime.now() + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
                          repeat="none")
    # 手动把触发时刻提前到 3 秒后
    plan["next_fire"] = (datetime.now() + timedelta(seconds=3)).strftime("%Y-%m-%d %H:%M")
    plan["_due_ts"] = (datetime.now() + timedelta(seconds=3)).timestamp()
    store.save()

    events = []
    sch = Scheduler(store, lambda k, p: events.append((k, p)))

    # 直接改 next_fire 为可比较的时间串会因分钟精度丢秒，
    # 这里借用 _tick 的比较逻辑：把 next_fire 设成当前分钟即可立即到期。
    plan["next_fire"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    sch.start()

    t0 = time.time()
    fired = False
    while time.time() - t0 < 20:
        root.update()
        time.sleep(0.05)
        if "executed" in [e[0] for e in events]:
            fired = True
            break

    for _ in range(20):
        root.update()
        time.sleep(0.05)

    ok = fail = 0

    def check(name, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  PASS  {name} {extra}")
        else:
            fail += 1
            print(f"  FAIL  {name} {extra}")

    logs = [p for k, p in events if k == "log"]
    print("调度日志:")
    for line in logs[-12:]:
        print("   ", line)

    check("计划被自动触发", fired)
    check("输入内容写入成功", state["got"] == "定时任务自动执行 OK", repr(state["got"]))
    check("点击动作生效", state["clicks"] >= 1, f"clicks={state['clicks']}")
    stored = store.get_plan(plan["id"])
    check("计划记录仍保留（未删除）", stored is not None)
    check("一次性计划执行后停用", stored and stored["enabled"] is False, str(stored.get("enabled") if stored else ""))
    check("记录了上次结果", bool(stored and stored.get("last_status")), (stored or {}).get("last_status", ""))

    sch.stop()
    root.destroy()
    tmp.unlink(missing_ok=True)
    print(f"\n结果: {ok} 通过, {fail} 失败")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
