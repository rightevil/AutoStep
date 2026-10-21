"""数据持久化：动作序列 + 计划。"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import profile as profile_mod
from . import trigger as trigger_mod
from .config import DEFAULT_SETTINGS, STORE_PATH

DT_FMT = "%Y-%m-%d %H:%M"
PROFILE_FILE = "profiles.json"


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


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _trigger_from(trigger: Any, run_at: Any = None, repeat: Any = None) -> Dict[str, Any]:
    """新结构优先；老字段（run_at + repeat）转成等价结构，兼容旧数据与旧调用方。"""
    t = trigger_mod.normalize(trigger)
    if t:
        return t
    dt = parse_dt(str(run_at or ""))
    if dt is None:
        return {}
    if repeat == "daily":
        return {"kind": "calendar", "times": [dt.strftime("%H:%M")], "days": []}
    return {"kind": "once", "at": dt.strftime(DT_FMT)}


class Store:
    """简单的 JSON 存储，写入用临时文件 + 替换保证原子性。

    应用档案（profile）与序列、计划存在同一目录：
    - <store 所在目录>/store.json     设置 / 序列 / 计划
    - <store 所在目录>/profiles.json  应用档案（可以手改）
    """

    def __init__(self, path: Path = STORE_PATH, profile_path: Optional[Path] = None):
        self.path = Path(path)
        self.profile_path = (
            Path(profile_path) if profile_path else self.path.parent / PROFILE_FILE
        )
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self.data: Dict[str, Any] = {
            "settings": {},
            "sequences": [],
            "plans": [],
        }
        self.load()

    # ---------- 读写 ----------

    def load(self) -> None:
        raw: Dict[str, Any] = {}
        # 文件是否存在决定「首次安装」还是「老数据升级」，两者给的默认档案不同
        self._fresh = not self.path.exists()
        if not self._fresh:
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
        self._load_profiles()
        self._migrate_profiles()
        self._migrate_plans()
        self.save()

    def _load_profiles(self) -> None:
        disk = profile_mod.load_file(self.profile_path)
        self.profiles = profile_mod.merge(profile_mod.BUILTIN_PROFILES, disk)

    def _migrate_profiles(self) -> None:
        """给没有 profile_id 的序列挂上档案。

        - 首次安装：直接挂内置的 ChatGPT 档案（默认目标就是它）
        - 老数据升级：用当前的全局目标生成一条「原设置」档案，
          保证升级前后行为完全一致，用户既有序列不必重录
        """
        missing = [s for s in self.data["sequences"] if not s.get("profile_id")]
        if not missing:
            return
        s = self.data["settings"]
        if getattr(self, "_fresh", False):
            pid = (
                "chatgpt-codex"
                if "chatgpt" in str(s.get("target_process", "")).lower()
                and "chatgpt-codex" in self.profiles
                else profile_mod.GENERIC_ID
            )
        else:
            pid = "default"
            if pid not in self.profiles:
                proc = str(s.get("target_process", "")).strip()
                self.profiles[pid] = profile_mod.normalize(
                    {
                        "id": pid,
                        # 名字里带上原目标，下拉里一眼能认出来
                        "name": f"原设置（{proc}）" if proc else "原设置",
                        "match": {
                            "process": proc,
                            "title": s.get("target_title", ""),
                        },
                        "input": {
                            "mode": s.get("input_mode", "auto"),
                            "clear_first": s.get("clear_first", True),
                        },
                        "send": {"combo": "enter"},
                    }
                )
        for seq in missing:
            seq["profile_id"] = pid

    def _migrate_plans(self) -> None:
        """老计划只有 run_at/repeat：补出 trigger 与结束条件字段。

        run_at/repeat 保留不删——万一回退旧版本，那边还能读到时间。
        """
        for p in self.data["plans"]:
            if not p.get("trigger"):
                p["trigger"] = _trigger_from(None, p.get("run_at"), p.get("repeat"))
            p.setdefault("end_at", "")
            p.setdefault("max_runs", 0)
            p.setdefault("runs", 0)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, self.path)
        try:
            profile_mod.save_file(self.profile_path, self.profiles)
        except Exception:
            pass

    # ---------- 设置 ----------

    @property
    def settings(self) -> Dict[str, Any]:
        return self.data["settings"]

    def set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value
        self.save()

    # ---------- 应用档案 ----------

    def get_profile(self, profile_id: str = "") -> Optional[Dict[str, Any]]:
        """按 id 取档案；找不到退回通用档案，避免整条序列跑不起来。"""
        p = self.profiles.get(str(profile_id or ""))
        if p:
            return p
        return self.profiles.get(profile_mod.GENERIC_ID) or next(
            iter(self.profiles.values()), None
        )

    def profile_choices(self) -> List[Dict[str, Any]]:
        """给界面下拉用：通用档案排最后。"""
        items = sorted(
            self.profiles.values(), key=lambda p: (p.get("id") == profile_mod.GENERIC_ID, p.get("name", ""))
        )
        return items

    def default_profile_id(self) -> str:
        """新序列默认用哪个档案：优先沿用当前第一条序列的选择。"""
        for s in self.sequences:
            pid = s.get("profile_id")
            if pid and pid in self.profiles:
                return pid
        return profile_mod.GENERIC_ID if profile_mod.GENERIC_ID in self.profiles else ""

    def upsert_profile(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        prof = profile_mod.normalize(raw)
        if not prof["id"]:
            prof["id"] = new_id()
        self.profiles[prof["id"]] = prof
        self.save()
        return prof

    def remove_profile(self, profile_id: str) -> bool:
        """删档案：引用它的序列改挂默认档案，不允许把最后一条删光。"""
        pid = str(profile_id or "")
        if pid not in self.profiles or len(self.profiles) <= 1:
            return False
        del self.profiles[pid]
        fallback = self.default_profile_id() or profile_mod.GENERIC_ID
        for s in self.sequences:
            if s.get("profile_id") == pid:
                s["profile_id"] = fallback
        self.save()
        return True

    def sequence_profile(self, seq: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not seq:
            return None
        return self.get_profile(seq.get("profile_id", ""))

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

    def add_sequence(self, name: str, profile_id: str = "") -> Dict[str, Any]:
        pid = profile_id or self.default_profile_id()
        seq = {"id": new_id(), "name": name, "profile_id": pid, "steps": []}
        self.sequences.append(seq)
        self.save()
        return seq

    def remove_sequence(self, seq_id: str) -> None:
        self.data["sequences"] = [s for s in self.sequences if s["id"] != seq_id]
        # 引用它的计划一并清理
        self.data["plans"] = [p for p in self.plans if p.get("seq_id") != seq_id]
        if not self.sequences:
            self.data["sequences"].append(
                {
                    "id": new_id(),
                    "name": "默认序列",
                    "profile_id": self.default_profile_id(),
                    "steps": [],
                }
            )
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
            # 触发规则见 core/trigger.py：once / calendar / interval
            "trigger": _trigger_from(kwargs.get("trigger"), kwargs.get("run_at"), kwargs.get("repeat")),
            "end_at": str(kwargs.get("end_at") or "")[:10],  # 截止日期，空=不限
            "max_runs": _int(kwargs.get("max_runs")),        # 最多执行次数，0=不限
            "runs": 0,
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
        run_at: str = "",
        repeat: str = "none",
        seq_id: str = "",
        trigger: Any = None,
        end_at: Any = "",
        max_runs: Any = 0,
    ) -> Optional[Dict[str, Any]]:
        """编辑计划。改完时间/重复方式后重新排期，若新时间有效则自动恢复启用。"""
        p = self.get_plan(plan_id)
        if not p:
            return None
        p["name"] = (name or "").strip() or p.get("name", "未命名计划")
        p["trigger"] = _trigger_from(trigger, run_at, repeat)
        p["end_at"] = str(end_at or "")[:10]
        p["max_runs"] = _int(max_runs)
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
        """下一次触发时刻；没有下一次（过期/次数用尽/过截止日）返回空串。

        end_at / max_runs 目前界面上不提供入口——「每天跑」配「最多 N 次」自相矛盾，
        新建计划时一律留空。这里保留判断只是为了兼容早期数据，没有值就不生效。
        """
        nxt = trigger_mod.next_fire(plan.get("trigger"), ref)
        if nxt is None:
            return ""
        end_at = str(plan.get("end_at") or "")
        if end_at and nxt.strftime("%Y-%m-%d") > end_at:
            return ""
        limit = _int(plan.get("max_runs"))
        if limit and _int(plan.get("runs")) >= limit:
            return ""
        return nxt.strftime(DT_FMT)

    def refresh_plan(self, plan: Dict[str, Any]) -> None:
        """保存后重算 next_fire。"""
        if not plan.get("enabled"):
            plan["next_fire"] = ""
        else:
            plan["next_fire"] = self._compute_next_fire(plan, now())
        self.save()

    def skip_plan(self, plan: Dict[str, Any], status: str = "错过（超时未执行）") -> None:
        """跳过本次：不计入执行次数，只把下次触发往后排。"""
        plan["last_status"] = status
        nxt = self._compute_next_fire(plan, now())
        plan["next_fire"] = nxt
        if not nxt:
            plan["enabled"] = False
        self.save()

    def mark_plan_done(self, plan: Dict[str, Any], status: str) -> None:
        plan["last_run"] = now_str()
        plan["last_status"] = status
        plan["status"] = "done"
        plan["runs"] = _int(plan.get("runs")) + 1
        # 从「本次该触发的时刻」往后排，而不是从现在：否则一次性计划跑完还会算作未来有效
        ref = parse_dt(plan.get("next_fire", "")) or now()
        kind = str((plan.get("trigger") or {}).get("kind"))
        # 一次性计划跑过就收摊。不靠 ref 推断：手改过 store.json 时 next_fire 可能和 trigger 对不上
        nxt = "" if kind == "once" else self._compute_next_fire(plan, ref)
        if nxt and parse_dt(nxt) <= now():
            # 延迟执行时，按计划时刻推出来的下一次可能已经过去了，退回到从此刻重算
            nxt = self._compute_next_fire(plan, now())
        plan["next_fire"] = nxt
        if not nxt:
            # 一次性 / 次数用尽 / 过截止日期：跑完收摊，记录保留不删
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
