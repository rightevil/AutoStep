"""定时调度：到点触发回放，并在计划时间前唤醒系统。"""
from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from . import executor, winsys
from .config import LOG_DIR
from .store import Store, parse_dt

EventFn = Callable[[str, Any], None]


class Scheduler:
    def __init__(self, store: Store, on_event: Optional[EventFn] = None):
        self.store = store
        self.on_event = on_event or (lambda k, p: None)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = threading.Lock()
        self._awake = False
        self._last_arm_key = ""

    # ---------------- 生命周期 ----------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)
        self._thread.start()
        self.rearm()

    def stop(self) -> None:
        self._stop.set()
        winsys.cancel_wake_timer()
        if self._awake:
            winsys.keep_awake(False)
            self._awake = False

    # ---------------- 事件 ----------------

    def _emit(self, kind: str, payload: Any = None) -> None:
        try:
            self.on_event(kind, payload)
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        self._emit("log", line)

    # ---------------- 唤醒定时器 ----------------

    def rearm(self) -> None:
        """按最近一次计划重设系统唤醒定时器。"""
        if not self.store.settings.get("wake_before_run", True):
            winsys.cancel_wake_timer()
            return
        fires = self.store.next_fires()
        if not fires:
            winsys.cancel_wake_timer()
            return
        nxt = fires[0]["dt"]
        lead = int(self.store.settings.get("wake_lead_seconds", 90))
        due_ts = nxt.timestamp() - lead
        key = f"{nxt.isoformat()}|{lead}"
        if key == self._last_arm_key:
            return
        if due_ts <= time.time():
            return
        ok, msg = winsys.arm_wake_timer(due_ts)
        self._last_arm_key = key if ok else ""
        if ok:
            self._log(f"系统唤醒已布防：{msg}（目标 {nxt:%m-%d %H:%M}）")
        else:
            self._log(f"⚠ 唤醒布防失败：{msg}")

    # ---------------- 主循环 ----------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                self._log("调度异常:\n" + traceback.format_exc())
            self._stop.wait(1.0)

    def _tick(self) -> None:
        now = datetime.now()
        lead = int(self.store.settings.get("wake_lead_seconds", 90))

        # 临近触发或正在执行 → 阻止系统休眠（绑定在本线程上）
        near = False
        for item in self.store.next_fires():
            delta = (item["dt"] - now).total_seconds()
            if -30 <= delta <= lead:
                near = True
                break
        want_awake = near or self._running.locked()
        if want_awake != self._awake:
            winsys.keep_awake(want_awake)
            self._awake = want_awake

        if self._running.locked():
            return

        for item in list(self.store.next_fires()):
            plan = item["plan"]
            if item["dt"] <= now:
                self._run_plan(plan, overdue=(now - item["dt"]).total_seconds())
                break

    # ---------------- 执行 ----------------

    def run_sequence_now(self, seq_id: str, label: str = "手动测试") -> None:
        """手动触发，异步执行，不阻塞 UI。"""
        seq = self.store.get_sequence(seq_id)
        if not seq:
            self._log("序列不存在")
            return
        threading.Thread(
            target=self._do_run,
            args=(seq, label, None, None),
            name="run-now",
            daemon=True,
        ).start()

    def _run_plan(self, plan: Dict[str, Any], overdue: float = 0) -> None:
        seq = self.store.get_sequence(plan.get("seq_id", ""))
        if not seq:
            self._log(f"计划「{plan.get('name')}」引用的序列已不存在")
            self.store.mark_plan_done(plan, "序列缺失")
            self._emit("refresh", None)
            self.rearm()
            return
        self._do_run(seq, f"计划「{plan.get('name')}」", plan, overdue)

    def _do_run(
        self,
        seq: Dict[str, Any],
        label: str,
        plan: Optional[Dict[str, Any]],
        overdue: Optional[float],
    ) -> None:
        if not self._running.acquire(blocking=False):
            self._log("上一次执行尚未结束，跳过")
            return
        try:
            self._log(f"=== 开始执行 {label}（{len(seq.get('steps', []))} 个动作）===")

            # 若严重超时（说明刚从睡眠中醒来），给系统一点时间恢复输入/显示
            if overdue is not None and overdue > 45:
                self._log(f"检测到超时 {overdue:.0f}s（系统可能刚从睡眠恢复），等待 8 秒稳定…")
                time.sleep(8)

            hwnd = winsys.find_target(
                self.store.settings.get("target_process", ""),
                self.store.settings.get("target_title", ""),
            )
            res = executor.execute(seq.get("steps", []), self.store.settings, self._log, hwnd)
            self._log(("✔ " if res["ok"] else "✘ ") + res["message"])

            if plan is not None:
                self.store.mark_plan_done(plan, res["message"][:60])
            self._emit("executed", {"result": res, "label": label})

            # 执行完再确认一次唤醒定时器指向下一个计划
            self._last_arm_key = ""
            self.rearm()
        except Exception:
            self._log("执行失败:\n" + traceback.format_exc())
            if plan is not None:
                self.store.mark_plan_done(plan, "执行异常")
        finally:
            self._running.release()
            self._emit("refresh", None)


def append_log_file(line: str) -> None:
    """把日志同时落盘，方便事后核查。"""
    try:
        p = LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
