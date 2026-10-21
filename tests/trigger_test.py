"""触发时间计算：全部用固定 ref 断言，不依赖「现在几点」。"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import trigger as T  # noqa: E402

ok = 0
fail = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {name} {extra}")


def nf(trig, ref: str):
    return T.next_fire(trig, datetime.strptime(ref, T.DT_FMT))


def show(v):
    return v.strftime(T.DT_FMT) if v else "None"


print("== 1. once ==")
once = {"kind": "once", "at": "2026-10-22 03:00"}
check("未来时刻照原样触发", show(nf(once, "2026-10-21 15:00")) == "2026-10-22 03:00")
check("已过去的时刻没有下一次", nf(once, "2026-10-22 03:00") is None)
check("正好等于 ref 也算过去（严格大于）", nf(once, "2026-10-22 03:01") is None)
check("缺 at 判为非法", T.normalize({"kind": "once"}) == {})

print("\n== 2. calendar：每天 ==")
daily = {"kind": "calendar", "times": ["09:00"], "days": []}
check("今天还没到 → 今天 09:00", show(nf(daily, "2026-10-21 08:59")) == "2026-10-21 09:00")
check("正好 09:00 → 次日", show(nf(daily, "2026-10-21 09:00")) == "2026-10-22 09:00")
check("已过 09:00 → 次日", show(nf(daily, "2026-10-21 15:00")) == "2026-10-22 09:00")

print("\n== 3. calendar：时间序列（多个点） ==")
seq = {"kind": "calendar", "times": ["21:00", "09:00", "13:30"], "days": []}
check("乱序输入被排序去重", T.normalize(seq)["times"] == ["09:00", "13:30", "21:00"])
check("10:00 → 下一个点 13:30", show(nf(seq, "2026-10-21 10:00")) == "2026-10-21 13:30")
check("13:30 → 下一个点 21:00", show(nf(seq, "2026-10-21 13:30")) == "2026-10-21 21:00")
check("跨午夜 → 次日首个点", show(nf(seq, "2026-10-21 23:30")) == "2026-10-22 09:00")

print("\n== 4. calendar：每周 ==")
mwf = {"kind": "calendar", "times": ["09:00"], "days": [1, 3, 5]}
# 2026-10-21 是周三
check("周三 早于 09:00 → 当天", show(nf(mwf, "2026-10-21 08:00")) == "2026-10-21 09:00")
check("周三 晚于 09:00 → 周五", show(nf(mwf, "2026-10-21 10:00")) == "2026-10-23 09:00")
check("周六 → 下周一", show(nf(mwf, "2026-10-24 10:00")) == "2026-10-26 09:00")
check("周日 → 周一", show(nf(mwf, "2026-10-25 10:00")) == "2026-10-26 09:00")

print("\n== 5. interval ==")
h3 = {"kind": "interval", "every": 3, "unit": "hour", "anchor": "2026-10-21 00:00"}
check("与 anchor 同一时刻 → +3h", show(nf(h3, "2026-10-21 00:00")) == "2026-10-21 03:00")
check("anchor 之后 1 分钟 → 03:00", show(nf(h3, "2026-10-21 00:01")) == "2026-10-21 03:00")
check("正好落在周期点 → 下一个周期", show(nf(h3, "2026-10-21 03:00")) == "2026-10-21 06:00")
check("跨过 3 个周期只给最近的下一次", show(nf(h3, "2026-10-21 10:00")) == "2026-10-21 12:00")
check("anchor 在未来 → 直接是 anchor",
      show(nf({"kind": "interval", "every": 3, "unit": "hour", "anchor": "2026-10-22 00:00"},
              "2026-10-21 10:00")) == "2026-10-22 00:00")
d2 = {"kind": "interval", "every": 2, "unit": "day", "anchor": "2026-10-21 03:00"}
check("按天间隔跨日", show(nf(d2, "2026-10-22 10:00")) == "2026-10-23 03:00")
check("every=0 判为非法", T.normalize({"kind": "interval", "every": 0, "anchor": "2026-10-21 00:00"}) == {})
check("未知 kind 判为非法", T.normalize({"kind": "cron"}) == {})

print("\n== 6. 界面文案 ==")
check("once", T.describe(once) == "只跑一次", T.describe(once))
check("每天", T.describe(daily) == "每天", T.describe(daily))
check("每周一三五", T.describe(mwf) == "每周一三五", T.describe(mwf))
check("每天 ×3", T.describe(seq) == "每天 ×3", T.describe(seq))
check("每 3 小时", T.describe(h3) == "每 3 小时", T.describe(h3))
check("设定时间列：定点列时刻", T.when_text(seq) == "09:00/13:30/21:00", T.when_text(seq))
check("设定时间列：间隔看起点", T.when_text(h3) == "自 10-21 00:00", T.when_text(h3))

print("\n== 7. 计划层：结束条件与迁移 ==")
from core.store import Store, parse_dt  # noqa: E402

tmp = Path(__file__).parent / "_tmp_trigger_store.json"
tmp.unlink(missing_ok=True)
st = Store(tmp)
sq = st.default_sequence()
anchor = datetime.now().strftime(T.DT_FMT)

p = st.add_plan(name="每2小时", seq_id=sq["id"],
                trigger={"kind": "interval", "every": 2, "unit": "hour", "anchor": anchor})
gap = (parse_dt(p["next_fire"]) - datetime.strptime(anchor, T.DT_FMT)).total_seconds() / 3600
check("间隔计划排到 2 小时后", abs(gap - 2) < 0.02, f"{gap:.2f}h")

p2 = st.add_plan(name="跑两次", seq_id=sq["id"], max_runs=2,
                 trigger={"kind": "calendar", "times": ["04:00"], "days": []})
st.mark_plan_done(p2, "ok")
check("第一次执行后计数 1、仍启用", p2["runs"] == 1 and p2["enabled"], f"runs={p2['runs']}")
st.mark_plan_done(p2, "ok")
check("达到最多次数后停用", p2["runs"] == 2 and not p2["enabled"] and p2["next_fire"] == "",
      f"runs={p2['runs']} enabled={p2['enabled']}")

p3 = st.add_plan(name="截止今天", seq_id=sq["id"], end_at=datetime.now().strftime("%Y-%m-%d"),
                 trigger={"kind": "interval", "every": 25, "unit": "hour", "anchor": anchor})
check("下一次超出截止日期则不排期", p3["next_fire"] == "", repr(p3["next_fire"]))

p4 = st.add_plan(name="会被跳过", seq_id=sq["id"],
                 trigger={"kind": "interval", "every": 1, "unit": "hour", "anchor": anchor})
st.skip_plan(p4)
check("跳过不计入执行次数", p4["runs"] == 0 and p4["next_fire"] != "", f"runs={p4['runs']}")

st.data["plans"] = [{
    "id": "old", "name": "老计划", "seq_id": sq["id"], "run_at": "2026-01-01 03:00",
    "repeat": "daily", "enabled": True, "status": "idle", "next_fire": "",
    "last_run": "", "last_status": "",
}]
st.save()
st2 = Store(tmp)
old = st2.plans[0]
check("老数据迁移成 calendar", old["trigger"]["kind"] == "calendar" and old["trigger"]["times"] == ["03:00"],
      str(old.get("trigger")))
check("老数据补出结束条件字段", old["end_at"] == "" and old["max_runs"] == 0 and old["runs"] == 0)
tmp.unlink(missing_ok=True)

print(f"\n触发模型：{ok} 通过 / {fail} 失败")
sys.exit(1 if fail else 0)
