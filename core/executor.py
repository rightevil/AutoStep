"""动作回放执行器。"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pyperclip
import win32api
import win32con
import win32gui

from . import winsys
from . import profile as profile_mod
from .config import SHOT_DIR

LogFn = Callable[[str], None]

VK_MAP = {
    "enter": win32con.VK_RETURN,
    "return": win32con.VK_RETURN,
    "tab": win32con.VK_TAB,
    "esc": win32con.VK_ESCAPE,
    "escape": win32con.VK_ESCAPE,
    "space": win32con.VK_SPACE,
    "backspace": win32con.VK_BACK,
    "delete": win32con.VK_DELETE,
    "up": win32con.VK_UP,
    "down": win32con.VK_DOWN,
    "left": win32con.VK_LEFT,
    "right": win32con.VK_RIGHT,
    "home": win32con.VK_HOME,
    "end": win32con.VK_END,
    "ctrl": win32con.VK_CONTROL,
    "control": win32con.VK_CONTROL,
    "shift": win32con.VK_SHIFT,
    "alt": win32con.VK_MENU,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[_c] = ord(_c.upper())
for _c in "0123456789":
    VK_MAP[_c] = ord(_c)


def _key_down(vk: int) -> None:
    win32api.keybd_event(vk, 0, 0, 0)


def _key_up(vk: int) -> None:
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)


def send_combo(combo: str) -> None:
    """发送形如 'enter' / 'ctrl+a' / 'ctrl+shift+enter' 的按键。"""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        return
    vks = [VK_MAP.get(p) for p in parts]
    if any(v is None for v in vks):
        raise ValueError(f"无法识别的按键: {combo}")
    for v in vks:
        _key_down(v)
        time.sleep(0.02)
    for v in reversed(vks):
        _key_up(v)
        time.sleep(0.02)


def _type_unicode(text: str) -> None:
    """逐字符发送（支持任意 Unicode，不占用剪贴板）。"""
    for ch in text:
        code = ord(ch)
        if code > 0xFFFF:
            # 增补平面字符拆成代理对
            code -= 0x10000
            for unit in (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)):
                win32api.keybd_event(0, unit, win32con.KEYEVENTF_UNICODE, 0)
                win32api.keybd_event(0, unit, win32con.KEYEVENTF_UNICODE | win32con.KEYEVENTF_KEYUP, 0)
        elif ch == "\n":
            send_combo("enter")
        elif ch == "\r":
            continue
        else:
            win32api.keybd_event(0, code, win32con.KEYEVENTF_UNICODE, 0)
            win32api.keybd_event(0, code, win32con.KEYEVENTF_UNICODE | win32con.KEYEVENTF_KEYUP, 0)
            if ch == " ":
                time.sleep(0.005)
        time.sleep(0.008)


def _paste(text: str) -> None:
    """走剪贴板粘贴，之后恢复原剪贴板内容。"""
    backup: Optional[str] = None
    try:
        backup = pyperclip.paste()
    except Exception:
        backup = None
    pyperclip.copy(text)
    time.sleep(0.12)
    send_combo("ctrl+v")
    time.sleep(0.45)
    if backup is not None:
        try:
            pyperclip.copy(backup)
        except Exception:
            pass


def type_text(text: str, mode: str = "auto") -> str:
    if not text:
        return "空文本"
    if mode == "paste":
        _paste(text)
        return "剪贴板粘贴"
    if mode == "keys":
        _type_unicode(text)
        return "逐字符输入"
    # auto
    if all(ord(c) < 128 for c in text):
        _type_unicode(text)
        return "逐字符输入"
    _paste(text)
    return "剪贴板粘贴"


def click_at(x: int, y: int) -> None:
    win32api.SetCursorPos((x, y))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.04)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def _step_point(hwnd: int, step: Dict[str, Any]) -> Optional[tuple]:
    r = step.get("rect") or {}
    rx = (float(r["x1"]) + float(r["x2"])) / 2
    ry = (float(r["y1"]) + float(r["y2"])) / 2
    return winsys.ratio_to_screen(hwnd, rx, ry)


def shoot(hwnd: int, tag: str = "") -> str:
    """执行后抓一张图存证，返回路径。"""
    try:
        from .capture import grab_client

        img = grab_client(hwnd)
        if not img:
            return ""
        name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{tag or 'run'}.png"
        p = SHOT_DIR / name
        img.save(p)
        return str(p)
    except Exception:
        return ""


def describe_step(i: int, step: Dict[str, Any]) -> str:
    t = step.get("type")
    if t == "click":
        r = step.get("rect") or {}
        return f"#{i} 点击 ({float(r.get('x1',0))*100:.0f}%,{float(r.get('y1',0))*100:.0f}%)"
    if t == "type":
        txt = step.get("text", "")
        one = txt.replace("\n", " ⏎ ")
        if len(one) > 28:
            one = one[:28] + "…"
        return f"#{i} 输入「{one}」"
    if t == "key":
        combo = step.get("combo", "enter")
        if combo == profile_mod.SEND_ALIAS:
            return f"#{i} 发送（应用默认键）"
        return f"#{i} 按键 {combo}"
    return f"#{i} 未知动作"


def execute(
    steps: List[Dict[str, Any]],
    settings: Dict[str, Any],
    log: LogFn = lambda m: None,
    hwnd_hint: int = 0,
    profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按顺序回放。返回 {ok, message, shot}。

    profile 为序列所属的应用档案：目标窗口、输入方式、发送键都从它来；
    传 None 时退回全局 settings 的老行为。
    """
    if profile is not None:
        if not profile_mod.has_target(profile):
            return {
                "ok": False,
                "message": f"档案「{profile.get('name', '')}」还没设置目标窗口，跳过本次",
                "shot": "",
            }
        hwnd = profile_mod.match_target(profile, hwnd_hint)
        who = profile_mod.describe(profile)
    else:
        hwnd = winsys.find_target(
            settings.get("target_process", ""), settings.get("target_title", ""), hwnd_hint
        )
        who = "全局目标"
    if not hwnd:
        return {"ok": False, "message": f"没找到目标窗口（{who}），跳过本次", "shot": ""}
    info = winsys.window_info(hwnd)
    log(f"目标窗口: {info['process']} · {info['title']}")

    if winsys.is_locked():
        return {"ok": False, "message": "当前处于锁屏状态，无法操作界面", "shot": ""}

    if not steps:
        return {"ok": False, "message": "动作序列为空", "shot": ""}

    if not winsys.activate(hwnd):
        return {"ok": False, "message": "无法把目标窗口切到前台", "shot": ""}
    time.sleep(float(settings.get("activate_delay", 1.0)))

    if win32gui.GetForegroundWindow() != hwnd:
        return {"ok": False, "message": "窗口激活后又被抢走焦点", "shot": ""}

    delay = float(settings.get("step_delay", 1.0))
    mode, clear_first = profile_mod.resolve_input(profile, settings)

    for idx, step in enumerate(steps, 1):
        time.sleep(delay)
        # 每步都确认焦点还在目标窗口
        if win32gui.GetForegroundWindow() != hwnd:
            if not winsys.activate(hwnd, timeout=1.5):
                return {"ok": False, "message": f"执行到 {describe_step(idx, step)} 时焦点丢失且无法恢复", "shot": ""}
            time.sleep(0.4)

        t = step.get("type")
        if t == "click":
            pt = _step_point(hwnd, step)
            if not pt:
                return {"ok": False, "message": f"第 {idx} 步坐标换算失败", "shot": ""}
            click_at(*pt)
            log(f"{describe_step(idx, step)} -> 屏幕 {pt}")
        elif t == "type":
            pt = _step_point(hwnd, step)
            if pt:
                click_at(*pt)
                time.sleep(0.25)
            if clear_first and step.get("clear_first", True):
                send_combo("ctrl+a")
                time.sleep(0.08)
            how = type_text(step.get("text", ""), mode)
            log(f"{describe_step(idx, step)} [{how}]")
        elif t == "key":
            combo = step.get("combo", "enter")
            if combo == profile_mod.SEND_ALIAS:
                combo = profile_mod.resolve_send(profile)
                log(f"{describe_step(idx, step)} -> {combo}")
            else:
                log(describe_step(idx, step))
            send_combo(combo)
        else:
            log(f"第 {idx} 步类型未知，忽略: {t}")

    shot = ""
    if settings.get("screenshot_after_run", True):
        time.sleep(0.6)
        shot = shoot(hwnd, "done")
        if shot:
            log(f"执行后截图: {shot}")
    return {"ok": True, "message": "执行完成", "shot": shot}
