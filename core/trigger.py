"""触发时间：什么时候跑、下一次是什么时候。

kind:
  once     指定时刻跑一次
  calendar 每天/每周的若干时间点（times 有多个就是「时间序列」）
  interval 每隔 N 小时 / N 天，从 anchor 起算
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

DT_FMT = "%Y-%m-%d %H:%M"
WEEK = "一二三四五六日"
UNITS = {"hour": "小时", "day": "天"}


def parse_time(text: Any) -> Optional[str]:
    """'9:5' / '09:05' → '09:05'；非法返回 None。"""
    try:
        h, m = str(text).replace("：", ":").strip().split(":")
        h, m = int(h), int(m)
    except Exception:
        return None
    return f"{h:02d}:{m:02d}" if 0 <= h <= 23 and 0 <= m <= 59 else None


def _dt(text: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(text).strip()[:16], DT_FMT)
    except Exception:
        return None


def normalize(raw: Any) -> Dict[str, Any]:
    """收敛成标准结构；不合法返回 {}（调用方据此判定「计划没设时间」）。"""
    if not isinstance(raw, dict):
        return {}
    kind = raw.get("kind")
    if kind == "once":
        at = _dt(raw.get("at"))
        return {"kind": "once", "at": at.strftime(DT_FMT)} if at else {}
    if kind == "calendar":
        times: List[str] = []
        for item in raw.get("times") or []:
            hm = parse_time(item)
            if hm and hm not in times:
                times.append(hm)
        if not times:
            return {}
        days: List[int] = []
        for item in raw.get("days") or []:
            try:
                d = int(item)
            except Exception:
                continue
            if 1 <= d <= 7 and d not in days:
                days.append(d)
        return {"kind": "calendar", "times": sorted(times), "days": sorted(days)}
    if kind == "interval":
        try:
            every = int(raw.get("every") or 0)
        except Exception:
            return {}
        anchor = _dt(raw.get("anchor"))
        if every <= 0 or anchor is None:
            return {}
        unit = raw.get("unit") if raw.get("unit") in UNITS else "hour"
        return {"kind": "interval", "every": every, "unit": unit, "anchor": anchor.strftime(DT_FMT)}
    return {}


def next_fire(trigger: Any, ref: datetime) -> Optional[datetime]:
    """严格晚于 ref 的下一次触发时刻；没有下一次返回 None。"""
    t = normalize(trigger)
    if not t:
        return None
    if t["kind"] == "once":
        at = _dt(t["at"])
        return at if at and at > ref else None

    if t["kind"] == "calendar":
        days: List[int] = t["days"]
        day0 = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        for i in range(8):  # days 非空时最远要跨 7 天才轮回到同一个星期几
            cur = day0 + timedelta(days=i)
            if days and cur.isoweekday() not in days:
                continue
            for hm in t["times"]:
                h, m = int(hm[:2]), int(hm[3:])
                cand = cur.replace(hour=h, minute=m)
                if cand > ref:
                    return cand
        return None

    anchor = _dt(t["anchor"])
    if anchor is None:
        return None
    step = timedelta(hours=t["every"]) if t["unit"] == "hour" else timedelta(days=t["every"])
    if anchor > ref:
        return anchor
    return anchor + ((ref - anchor) // step + 1) * step


def describe(trigger: Any) -> str:
    """列表里的频率摘要。"""
    t = normalize(trigger)
    if not t:
        return "未设定"
    if t["kind"] == "once":
        return "只跑一次"
    if t["kind"] == "interval":
        return f"每 {t['every']} {UNITS[t['unit']]}"
    when = "每天" if not t["days"] else "每周" + "".join(WEEK[d - 1] for d in t["days"])
    return when if len(t["times"]) == 1 else f"{when} ×{len(t['times'])}"


def when_text(trigger: Any) -> str:
    """列表里的「设定时间」列：定点看时刻，间隔看起点。"""
    t = normalize(trigger)
    if not t:
        return ""
    if t["kind"] == "once":
        return t["at"]
    if t["kind"] == "calendar":
        return "/".join(t["times"])
    return f"自 {t['anchor'][5:]}"
