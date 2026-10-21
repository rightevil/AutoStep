"""应用档案（profile）：把「怎么跟某个应用打交道」从全局设置与代码里搬出来。

一个档案描述四件事：

- match  怎么认出目标窗口（进程名 / 标题关键字，都留空表示还没配）
- input  输入方式（auto|keys|paste）与是否先 Ctrl+A 清空
- send   这个应用「发出去」按什么键（enter / ctrl+enter …）
- verify 怎么算跑完（L2 才用，现在只占位，不实现）

档案按 id 存在 data/profiles.json 里，内置几条作为模板；序列通过 profile_id
引用档案，所以同一个程序可以同时伺候多个应用，互不干扰。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from . import winsys

# 「按这个应用的默认发送键」的占位符，出现在动作里时在执行时解析
SEND_ALIAS = "@send"

# 没配 target 的兜底档案：不指向任何窗口，避免误点任意前台窗口
GENERIC_ID = "generic"

INPUT_MODES = ("auto", "keys", "paste")

BUILTIN_PROFILES: Dict[str, Dict[str, Any]] = {
    "chatgpt-codex": {
        "id": "chatgpt-codex",
        "name": "ChatGPT（Codex）",
        "match": {"process": "ChatGPT", "title": ""},
        "input": {"mode": "auto", "clear_first": True},
        "send": {"combo": "enter"},
        "verify": {"type": "none"},
    },
    "notepad": {
        "id": "notepad",
        "name": "记事本",
        "match": {"process": "notepad", "title": ""},
        "input": {"mode": "keys", "clear_first": False},
        "send": {"combo": "enter"},
        "verify": {"type": "none"},
    },
    GENERIC_ID: {
        "id": GENERIC_ID,
        "name": "通用（未指定应用）",
        "match": {"process": "", "title": ""},
        "input": {"mode": "auto", "clear_first": True},
        "send": {"combo": "enter"},
        "verify": {"type": "none"},
    },
}


def normalize(raw: Optional[Dict[str, Any]], fallback_id: str = "") -> Dict[str, Any]:
    """补齐字段、纠正类型，保证下游不用到处 .get()。"""
    src = dict(raw or {})
    pid = str(src.get("id") or fallback_id or "").strip()
    out: Dict[str, Any] = {"id": pid, "name": str(src.get("name") or pid or "未命名档案").strip()}

    m = src.get("match") or {}
    out["match"] = {
        "process": str(m.get("process") or "").strip(),
        "title": str(m.get("title") or "").strip(),
    }

    i = src.get("input") or {}
    mode = str(i.get("mode") or "auto").strip().lower()
    out["input"] = {
        "mode": mode if mode in INPUT_MODES else "auto",
        "clear_first": bool(i.get("clear_first", True)),
    }

    s = src.get("send") or {}
    combo = str(s.get("combo") or "enter").strip() or "enter"
    out["send"] = {"combo": combo}

    v = src.get("verify") or {}
    out["verify"] = {"type": str(v.get("type") or "none").strip() or "none"}
    return out


def load_file(path: Path) -> Dict[str, Dict[str, Any]]:
    """读用户档案文件；文件不存在或坏掉都返回空表，不抛异常。"""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text("utf-8"))
    except Exception:
        return {}
    items: Iterable[Any]
    if isinstance(raw, dict):
        items = raw.get("profiles") or []
        if isinstance(items, dict):  # 兼容 {id: {...}} 写法
            items = [dict(v, id=k) for k, v in items.items()]
    elif isinstance(raw, list):
        items = raw
    else:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        prof = normalize(item)
        if prof["id"]:
            out[prof["id"]] = prof
    return out


def save_file(path: Path, profiles: Dict[str, Dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"profiles": [normalize(v, k) for k, v in profiles.items()]}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(p)


def merge(builtin: Dict[str, Dict[str, Any]], custom: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """内置打底、用户文件覆盖；用户自己加的档案全部保留。"""
    out = {k: normalize(v, k) for k, v in builtin.items()}
    for k, v in custom.items():
        out[k] = normalize(v, k)
    return out


# ---------------------------------------------------------------- 运行时解析


def match_target(profile: Optional[Dict[str, Any]], hwnd_hint: int = 0) -> int:
    """按档案找窗口。档案没配目标时返回 0，绝不退化成「随便挑一个窗口」。"""
    if not profile:
        return 0
    m = profile.get("match") or {}
    proc = str(m.get("process") or "").strip()
    title = str(m.get("title") or "").strip()
    if not proc and not title:
        return 0
    return winsys.find_target(proc, title, hwnd_hint)


def has_target(profile: Optional[Dict[str, Any]]) -> bool:
    if not profile:
        return False
    m = profile.get("match") or {}
    return bool(str(m.get("process") or "").strip() or str(m.get("title") or "").strip())


def resolve_input(profile: Optional[Dict[str, Any]], settings: Dict[str, Any]) -> Tuple[str, bool]:
    """输入方式与是否先清空：有档案用档案，没有才退回全局设置。"""
    if not profile:
        return (
            str(settings.get("input_mode", "auto")),
            bool(settings.get("clear_first", True)),
        )
    i = profile.get("input") or {}
    return str(i.get("mode") or "auto"), bool(i.get("clear_first", True))


def resolve_send(profile: Optional[Dict[str, Any]]) -> str:
    """这个应用的发送键。"""
    if not profile:
        return "enter"
    return str((profile.get("send") or {}).get("combo") or "enter")


def describe(profile: Optional[Dict[str, Any]]) -> str:
    if not profile:
        return "（无档案）"
    name = str(profile.get("name", ""))
    m = profile.get("match") or {}
    proc = str(m.get("process") or "").strip()
    title = str(m.get("title") or "").strip()
    if not proc and not title:
        # 没设目标窗口：名字本身通常已经说明了（如「通用（未指定应用）」），不再叠括号
        return name or "（未指定窗口）"
    if proc and not title and proc.lower() in name.lower():
        # 名字里已经写了进程名，别再加一遍括号
        return name
    bits = [b for b in (proc, f"标题含 {title}" if title else "") if b]
    return f"{name}（{' / '.join(bits)}）"
