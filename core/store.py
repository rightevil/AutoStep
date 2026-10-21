"""数据持久化：动作序列 + 计划。"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DEFAULT_SETTINGS, STORE_PATH

DT_FMT = "%Y-%m-%d %H:%M"


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def now_str() -> str:
    return now().strftime(DT_FMT)


def parse_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s.strip(), DT_FMT)
    except Exception:
        return None


def new_id() -> str:
    return uuid.uuid4().hex[:8]


class Store:
    """简单的 JSON 存储，写入用临时文件 + 替换保证原子性。"""

    def __init__(self, path: Path = STORE_PATH):
        self.path = Path(path)
        self.data: Dict[str, Any] = {
            "settings": {},
            "sequences": [],
            "plans": [],
        }
        self.load()

    # ---------- 读写 ----------

    def load(self) -> None:
        raw: Dict[str, Any] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text("utf-8"))
            except Exception:
                raw = {}
        self.data["settings"] = dict(DEFAULT_SETTINGS)
        self.data["settings"].update(raw.get("settings") or {})
        self.data["sequences"] = raw.get("sequences") or []
        self.data["plans"] = raw.get("plans") or []
        if not self.data["sequences"]:
            self.data["sequences"].append({"id": new_id(), "name": "默认序列", "steps": []})
        self.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, self.path)

    # ---------- 设置 ----------

    @property
    def settings(self) -> Dict[str, Any]:
        return self.data["settings"]

    def set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self.save()

    # ---------- 序列 ----------

    @property
    def sequences(self) -> List[Dict[str, Any]]:
        return self.data["sequences"]

    def get_sequence(self, seq_id: str) -> Optional[Dict[str, Any]]:
        for s in self.sequences:
            if s["id"] == seq_id:
                return s
        return None

    def default_sequence(self) -> Dict[str, Any]:
        return self.sequences[0]

    def add_sequence(self, name: str) -> Dict[str, Any]:
        seq = {"id": new_id(), "name": name, "steps": []}
        self.sequences.append(seq)
        self.save()
        return seq

    def remove_sequence(self, seq_id: str) -> None:
        self.data["sequences"] = [s for s in self.sequences if s["id"] != seq_id]
        # 引用它的计划一并清理
        self.data["plans"] = [p for p in self.plans if p.get("seq_id") != seq_id]
        if not self.sequences:
            self.data["sequences"].append({"id": new_id(), "name": "默认序列", "steps": []})
        self.save()

    # ---------- 计划 ----------

    @property
    def plans(self) -> List[Dict[str, Any]]:
        return self.data["plans"]

    def add_plan(self, **kwargs) -> Dict[str, Any]:
        plan = {
            "id": new_id(),
            "name": kwargs.get("name") or "未命名计划",
            "seq_id": kwargs["seq_id"],
            "run_at": kwargs["run_at"],          # "YYYY-MM-DD HH:MM"
            "repeat": kwargs.get("repeat", "none"),  # none | daily
            "enabled": True,
            "status": "idle",                    # idle | done（done 只表示跑过了，记录仍保留）
            "next_fire": "",
            "last_run": "",
            "last_status": "",
        }
        plan["next_fire"] = self._compute_next_fire(plan, now())
        self.plans.append(plan)
        self.save()
        return plan

    def rename_plan(self, plan_id: str, name: str) -> bool:
        p = self.get_plan(plan_id)
        if not p or not name.strip():
            return False
        p["name"] = name.strip()
        self.save()
        return True

    def update_plan(
        self,
        plan_id: str,
        name: str,
        run_at: str,
        repeat: str,
        seq_id: str,
    ) -> Optional[Dict[str, Any]]:
        """编辑计划。改完时间/重复方式后重新排期，若新时间有效则自动恢复启用。"""
        p = self.get_plan(plan_id)
        if not p:
            return None
        p["name"] = (name or "").strip() or p.get("name", "未命名计划")
        p["run_at"] = run_at
        p["repeat"] = repeat if repeat in ("none", "daily") else "none"
        if seq_id and self.get_sequence(seq_id):
            p["seq_id"] = seq_id
        p["status"] = "idle"
        nxt = self._compute_next_fire(p, now())
        p["next_fire"] = nxt
        p["enabled"] = bool(nxt)
        self.save()
        return p

    def remove_plan(self, plan_id: str) -> None:
        self.data["plans"] = [p for p in self.plans if p["id"] != plan_id]
        self.save()

    def get_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        for p in self.plans:
            if p["id"] == plan_id:
                return p
        return None

    @staticmethod
    def _compute_next_fire(plan: Dict[str, Any], ref: datetime) -> str:
        """计算下一次该触发的时刻；已失效返回空串。"""
        base = parse_dt(plan.get("run_at", ""))
        if base is None:
            return ""
        if plan.get("repeat") == "daily":
            cand = ref.replace(hour=base.hour, minute=base.minute, second=0, microsecond=0)
            if cand <= ref:
                cand += timedelta(days=1)
            return cand.strftime(DT_FMT)
        # 一次性
        return base.strftime(DT_FMT) if base > ref else ""

    def refresh_plan(self, plan: Dict[str, Any]) -> None:
        """保存后重算 next_fire。"""
        if not plan.get("enabled"):
            plan["next_fire"] = ""
        else:
            plan["next_fire"] = self._compute_next_fire(plan, now())
        self.save()

    def mark_plan_done(self, plan: Dict[str, Any], status: str) -> None:
        plan["last_run"] = now_str()
        plan["last_status"] = status
        plan["status"] = "done"
        if plan.get("repeat") == "daily":
            # 每天执行：下一次仍旧是「同一时刻」，只是日期往后一天。
            # 跨过漏执行的日期不补跑，直接落到未来最近的一次。
            base = parse_dt(plan.get("next_fire", "")) or parse_dt(plan.get("run_at", "")) or now()
            nxt = base + timedelta(days=1)
            cur = now()
            while nxt <= cur:
                nxt += timedelta(days=1)
            plan["next_fire"] = nxt.strftime(DT_FMT) if plan.get("enabled") else ""
        else:
            # 只执行一次：跑完就结束，计划记录保留不删
            plan["next_fire"] = ""
            plan["enabled"] = False
        self.save()

    def next_fires(self) -> List[Dict[str, Any]]:
        out = []
        for p in self.plans:
            dt = parse_dt(p.get("next_fire", ""))
            if p.get("enabled") and dt:
                out.append({"plan": p, "dt": dt})
        out.sort(key=lambda x: x["dt"])
        return out
