"""Windows 系统层：DPI、窗口枚举/激活、坐标换算、防休眠、唤醒。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import time
from typing import Dict, List, Optional, Tuple

import win32api
import win32con
import win32gui
import win32process

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)


# ---------------------------------------------------------------- DPI

def set_dpi_awareness() -> str:
    """必须在创建任何窗口之前调用，否则 125%/150% 缩放下坐标全偏。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return "per-monitor"
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except Exception:
        return "none"


# ---------------------------------------------------------------- 窗口

_pid_name_cache: Dict[int, str] = {}


def _process_name(pid: int) -> str:
    if pid in _pid_name_cache:
        return _pid_name_cache[pid]
    name = ""
    try:
        h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wt.DWORD(1024)
                if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = buf.value.rsplit("\\", 1)[-1]
            finally:
                _kernel32.CloseHandle(h)
    except Exception:
        pass
    _pid_name_cache[pid] = name
    return name


def list_windows() -> List[Dict[str, object]]:
    """列出可见的顶层窗口（排除工具窗口/无标题）。"""
    result: List[Dict[str, object]] = []

    def cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return True
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex & win32con.WS_EX_TOOLWINDOW:
                return True
            if win32gui.GetParent(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = _process_name(pid)
            if not proc:
                return True
            result.append(
                {
                    "hwnd": hwnd,
                    "title": title,
                    "process": proc,
                    "pid": pid,
                    "class": win32gui.GetClassName(hwnd),
                }
            )
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return result


def find_target(process: str = "", title: str = "", hwnd_hint: int = 0) -> int:
    """按进程名 + 标题关键字找窗口，返回 hwnd（0 = 未找到）。"""
    if hwnd_hint and win32gui.IsWindow(hwnd_hint):
        return hwnd_hint
    proc = (process or "").strip().lower()
    ttl = (title or "").strip().lower()
    best, best_score = 0, -1
    for w in list_windows():
        score = 0
        p = str(w["process"]).lower()
        t = str(w["title"]).lower()
        if proc and proc in p:
            score += 10
        if ttl and ttl in t:
            score += 5
        if not proc and not ttl:
            score = 1
        if score > best_score:
            best, best_score = int(w["hwnd"]), score
    return best if best_score > 0 else 0


def window_info(hwnd: int) -> Dict[str, object]:
    if not hwnd or not win32gui.IsWindow(hwnd):
        return {"hwnd": 0, "title": "", "process": "", "alive": False}
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return {
            "hwnd": hwnd,
            "title": win32gui.GetWindowText(hwnd),
            "process": _process_name(pid),
            "alive": True,
        }
    except Exception:
        return {"hwnd": 0, "title": "", "process": "", "alive": False}


def client_rect(hwnd: int) -> Tuple[int, int, int, int]:
    """客户区在屏幕上的物理像素矩形：left, top, width, height。"""
    l, t, r, b = win32gui.GetClientRect(hwnd)
    w, h = r - l, b - t
    sl, st = win32gui.ClientToScreen(hwnd, (0, 0))
    return sl, st, w, h


def ratio_to_screen(hwnd: int, rx: float, ry: float) -> Optional[Tuple[int, int]]:
    """窗口客户区百分比坐标 -> 屏幕绝对坐标（窗口移动/缩放后依然对得上）。"""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return None
    l, t, w, h = client_rect(hwnd)
    if w <= 0 or h <= 0:
        return None
    return int(l + rx * w), int(t + ry * h)


def activate(hwnd: int, timeout: float = 3.0) -> bool:
    """把窗口弄到前台并确认成功。Windows 有前台锁，这里用几种手段叠加绕过。"""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    try:
        if win32gui.IsIconic(hwnd):
            _user32.ShowWindowAsync(hwnd, win32con.SW_RESTORE)
            time.sleep(0.25)
    except Exception:
        pass
    deadline = time.time() + timeout
    for _ in range(3):
        try:
            if win32gui.GetForegroundWindow() == hwnd:
                return True
            # 1) 经典手法：先发一次 ALT 解除前台锁
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            # 2) 未文档化的 SwitchToThisWindow，对前台限制免疫
            try:
                _user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass
            try:
                win32gui.BringWindowToTop(hwnd)
            except Exception:
                pass
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        if win32gui.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.2)
    # 3) 最后手段：线程输入队列附加
    try:
        cur = win32api.GetCurrentThreadId()
        fg = win32gui.GetForegroundWindow()
        fg_tid = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
        tgt_tid = win32process.GetWindowThreadProcessId(hwnd)[0]
        attached = []
        for tid in (fg_tid, tgt_tid):
            if tid and tid != cur:
                try:
                    win32process.AttachThreadInput(cur, tid, True)
                    attached.append(tid)
                except Exception:
                    pass
        win32gui.SetForegroundWindow(hwnd)
        win32gui.SetActiveWindow(hwnd)
        for tid in attached:
            try:
                win32process.AttachThreadInput(cur, tid, False)
            except Exception:
                pass
    except Exception:
        pass
    while time.time() < deadline:
        if win32gui.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.1)
    return win32gui.GetForegroundWindow() == hwnd


# ---------------------------------------------------------------- 锁屏/会话

def is_locked() -> bool:
    """当前输入桌面不可访问 → 大概率锁屏，自动化会打到锁屏界面上。"""
    try:
        DESKTOP_READOBJECTS = 0x0001
        h = _user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
        if not h:
            return True
        _user32.CloseDesktop(h)
        return False
    except Exception:
        return False


# ---------------------------------------------------------------- 电源

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def keep_awake(enable: bool, keep_display: bool = False) -> bool:
    """阻止系统休眠。必须在长期存活的线程里调用（状态是线程级的）。"""
    flags = ES_CONTINUOUS
    if enable:
        flags |= ES_SYSTEM_REQUIRED
        if keep_display:
            flags |= ES_DISPLAY_REQUIRED
    try:
        return bool(_kernel32.SetThreadExecutionState(flags))
    except Exception:
        return False


def enable_shutdown_privilege() -> bool:
    """唤醒系统需要 SE_SHUTDOWN_NAME 特权。"""
    try:
        import win32security

        h = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY,
        )
        win32security.AdjustTokenPrivileges(
            h,
            False,
            [
                (
                    win32security.LookupPrivilegeValue(None, win32security.SE_SHUTDOWN_NAME),
                    win32con.SE_PRIVILEGE_ENABLED,
                )
            ],
        )
        return True
    except Exception:
        return False


_timer_handle = None


def arm_wake_timer(due_ts: float) -> Tuple[bool, str]:
    """在 due_ts（Unix 时间戳）让系统从睡眠中恢复。返回 (是否成功, 说明)。"""
    global _timer_handle
    rel = due_ts - time.time()
    if rel < 1:
        rel = 1
    try:
        if _timer_handle:
            _kernel32.CancelWaitableTimer(_timer_handle)
            _kernel32.CloseHandle(_timer_handle)
            _timer_handle = None
        CREATE_WAITABLE_TIMER_MANUAL_RESET = 0x00000001
        TIMER_ALL_ACCESS = 0x1F0003
        _kernel32.CreateWaitableTimerExW.restype = wt.HANDLE
        h = _kernel32.CreateWaitableTimerExW(None, None, CREATE_WAITABLE_TIMER_MANUAL_RESET, TIMER_ALL_ACCESS)
        if not h:
            return False, "创建定时器失败"
        priv = enable_shutdown_privilege()
        due = ctypes.c_longlong(-int(rel * 10_000_000))  # 负数 = 相对时间，单位 100ns
        ok = _kernel32.SetWaitableTimer(h, ctypes.byref(due), 0, None, None, True)
        if not ok:
            _kernel32.CloseHandle(h)
            return False, f"设置唤醒定时器失败(err={ctypes.get_last_error()})"
        _timer_handle = h
        extra = "" if priv else "（未取得 SE_SHUTDOWN 特权，唤醒可能无效）"
        return True, f"已设定 {rel/60:.1f} 分钟后唤醒系统{extra}"
    except Exception as e:
        return False, f"唤醒定时器异常: {e}"


def cancel_wake_timer() -> None:
    global _timer_handle
    if _timer_handle:
        try:
            _kernel32.CancelWaitableTimer(_timer_handle)
            _kernel32.CloseHandle(_timer_handle)
        except Exception:
            pass
        _timer_handle = None
