"""非 GUI 部分的冒烟测试：跑一遍确认核心逻辑与系统层可用。"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import winsys  # noqa: E402
from core.store import Store, parse_dt  # noqa: E402

# 与正式程序一致：必须先声明 DPI 感知，否则拿到的是虚拟化坐标
print("DPI awareness:", winsys.set_dpi_awareness())

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


print("== 1. Store 序列/计划逻辑 ==")
tmp = Path(__file__).parent / "_tmp_store.json"
if tmp.exists():
    tmp.unlink()
st = Store(tmp)
check("默认序列存在", len(st.sequences) == 1, st.sequences[0]["name"])

seq = st.default_sequence()
seq["steps"] = [
    {"type": "click", "rect": {"x1": 0.3, "y1": 0.8, "x2": 0.5, "y2": 0.9}},
    {"type": "type", "rect": {"x1": 0.3, "y1": 0.8, "x2": 0.5, "y2": 0.9}, "text": "测试"},
    {"type": "key", "combo": "enter"},
]
st.save()

future = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
p1 = st.add_plan(name="一次性", seq_id=seq["id"], run_at=future, repeat="none")
check("一次性计划 next_fire = run_at", p1["next_fire"] == future, p1["next_fire"])

past = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
p2 = st.add_plan(name="已过期", seq_id=seq["id"], run_at=past, repeat="none")
check("过期一次性计划不触发", p2["next_fire"] == "", repr(p2["next_fire"]))

p3 = st.add_plan(name="每天", seq_id=seq["id"], run_at="2026-01-01 03:00", repeat="daily")
nf = parse_dt(p3["next_fire"])
check("每日计划 next_fire 在未来且为 03:00", nf is not None and nf > datetime.now() and nf.hour == 3 and nf.minute == 0, str(nf))

st.mark_plan_done(p1, "ok")
check("一次性执行后自动停用", p1["enabled"] is False and p1["next_fire"] == "")
check("一次性执行后记录仍保留", st.get_plan(p1["id"]) is not None and p1.get("status") == "done",
      f"status={p1.get('status')}")

st.mark_plan_done(p3, "ok")
nf2 = parse_dt(p3["next_fire"])
check("每天执行：下一次为次日同一时刻", nf2 is not None and (nf2 - nf).days == 1, f"{nf} -> {nf2}")
check("每天执行后计划仍启用", p3["enabled"] is True)

check("计划可重命名", st.rename_plan(p3["id"], "改过的名字") and st.get_plan(p3["id"])["name"] == "改过的名字",
      st.get_plan(p3["id"])["name"])
check("重命名空字符串被拒绝", st.rename_plan(p3["id"], "   ") is False)

# 编辑计划：改时间 / 重复方式 / 名称 / 序列
later = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
up = st.update_plan(p3["id"], "编辑后的计划", later, "none", seq["id"])
check("编辑后名称生效", up["name"] == "编辑后的计划")
check("编辑后时间生效", up["run_at"] == later)
check("编辑后改回一次性并重新启用", up["enabled"] is True and up["next_fire"] == later,
      f"{up['enabled']} {up['next_fire']}")
check("编辑后排期恢复待执行状态", up["status"] == "idle")

up2 = st.update_plan(p3["id"], "编辑后的计划", past, "none", seq["id"])
check("编辑成过期的一次性计划则不启用", up2["enabled"] is False and up2["next_fire"] == "",
      f"{up2['enabled']} {up2['next_fire']!r}")

up3 = st.update_plan(p3["id"], "编辑后的计划", past, "daily", seq["id"])
check("编辑成每天执行会重排到未来", up3["enabled"] is True and parse_dt(up3["next_fire"]) > datetime.now(),
      str(up3["next_fire"]))

fires = st.next_fires()
check("next_fires 按时间排序", all(fires[i]["dt"] <= fires[i + 1]["dt"] for i in range(len(fires) - 1)),
      str([f["dt"].strftime("%m-%d %H:%M") for f in fires]))

st.remove_sequence(seq["id"])
check("删序列后相关计划被清理", len(st.plans) == 0 and len(st.sequences) == 1)
tmp.unlink(missing_ok=True)

print("\n== 1b. 应用档案（profile）==")
import json  # noqa: E402

from core import profile as profile_mod  # noqa: E402

tmp2 = Path(__file__).parent / "_tmp_store2.json"
pfile = Path(__file__).parent / "_tmp_profiles2.json"
for _p in (tmp2, pfile):
    _p.unlink(missing_ok=True)

# 伪造升级前的数据：序列没有 profile_id，目标与输入方式存在全局设置里
tmp2.write_text(
    json.dumps(
        {
            "settings": {
                "target_process": "Notepad.exe",
                "target_title": "",
                "input_mode": "keys",
                "clear_first": False,
            },
            "sequences": [{"id": "s1", "name": "老序列", "steps": []}],
            "plans": [],
        },
        ensure_ascii=False,
    ),
    "utf-8",
)
st2 = Store(tmp2, pfile)
check("迁移：老序列获得 profile_id", all(s.get("profile_id") for s in st2.sequences),
      str(st2.sequences[0].get("profile_id")))
legacy = st2.get_profile(st2.sequences[0]["profile_id"])
check("迁移：档案沿用原全局目标", legacy["match"]["process"] == "Notepad.exe", legacy["match"]["process"])
check("迁移：档案沿用原输入方式",
      legacy["input"]["mode"] == "keys" and legacy["input"]["clear_first"] is False,
      str(legacy["input"]))
check("迁移：profiles.json 已落盘", pfile.exists())

# 全新安装（store.json 本来不存在）不该生成「原设置」这种迁移产物
fresh_store = Path(__file__).parent / "_tmp_store3.json"
fresh_prof = Path(__file__).parent / "_tmp_profiles3.json"
for _p in (fresh_store, fresh_prof):
    _p.unlink(missing_ok=True)
st4 = Store(fresh_store, fresh_prof)
check("首次安装直接挂内置 ChatGPT 档案",
      st4.sequences[0]["profile_id"] == "chatgpt-codex", str(st4.sequences[0]["profile_id"]))
for _p in (fresh_store, fresh_prof):
    _p.unlink(missing_ok=True)

seq_a = st2.add_sequence("序列A")
check("新序列自动带 profile_id", bool(seq_a.get("profile_id")), str(seq_a.get("profile_id")))

wx = st2.upsert_profile(
    {
        "id": "wx",
        "name": "微信",
        "match": {"process": "WeChat", "title": ""},
        "input": {"mode": "paste", "clear_first": False},
        "send": {"combo": "ctrl+enter"},
    }
)
seq_b = st2.add_sequence("序列B", "wx")
check("两条序列可指向不同档案",
      st2.get_sequence(seq_a["id"])["profile_id"] != st2.get_sequence(seq_b["id"])["profile_id"])
check("按序列能取到各自档案",
      (st2.sequence_profile(st2.get_sequence(seq_b["id"])) or {}).get("name") == "微信")

mode, clear = profile_mod.resolve_input(wx, st2.settings)
check("输入方式取档案值而非全局", mode == "paste" and clear is False, f"{mode} {clear}")
check("发送键取档案值", profile_mod.resolve_send(wx) == "ctrl+enter", profile_mod.resolve_send(wx))
check("无档案时退回全局设置", profile_mod.resolve_input(None, st2.settings) == ("keys", False))

generic = st2.get_profile("generic")
check("未配目标的档案不误点任意窗口", profile_mod.match_target(generic) == 0)
check("has_target 能识别未配置",
      profile_mod.has_target(generic) is False and profile_mod.has_target(wx) is True)
check("未知 profile_id 退回通用档案", st2.get_profile("no-such-id") is not None,
      (st2.get_profile("no-such-id") or {}).get("id"))

# 手改 profiles.json 后重新加载应生效（说明它是可编辑的配置文件）
raw = json.loads(pfile.read_text("utf-8"))
for item in raw["profiles"]:
    if item["id"] == "wx":
        item["name"] = "改名了"
pfile.write_text(json.dumps(raw, ensure_ascii=False), "utf-8")
st3 = Store(tmp2, pfile)
check("手改 profiles.json 后重新加载生效", st3.get_profile("wx")["name"] == "改名了",
      st3.get_profile("wx")["name"])

st3.remove_profile("wx")
check("删除档案后相关序列改挂其他档案",
      st3.get_sequence(seq_b["id"])["profile_id"] in st3.profiles,
      st3.get_sequence(seq_b["id"])["profile_id"])

for _p in (tmp2, pfile):
    _p.unlink(missing_ok=True)

print("\n== 2. 窗口系统层 ==")
wins = winsys.list_windows()
check("能枚举到窗口", len(wins) > 0, f"{len(wins)} 个")
for w in wins[:6]:
    print(f"        {w['process']:<24} {w['title'][:50]}")

hwnd = winsys.find_target("ChatGPT", "")
check("能按进程名匹配 ChatGPT", hwnd != 0, f"hwnd={hwnd}")
if hwnd:
    info = winsys.window_info(hwnd)
    l, t, w, h = winsys.client_rect(hwnd)
    print(f"        标题: {info['title']!r}  客户区: {w}x{h} @ ({l},{t})")
    check("客户区尺寸有效", w > 0 and h > 0, f"{w}x{h}")
    pt = winsys.ratio_to_screen(hwnd, 0.5, 0.5)
    check("比例坐标能换算", pt is not None, str(pt))
    if pt:
        check("换算点在客户区内",
              l <= pt[0] <= l + w and t <= pt[1] <= t + h, str(pt))

check("find_target 对不存在的进程返回 0", winsys.find_target("NoSuchProcessXYZ", "") == 0)
check("锁屏检测可调用", isinstance(winsys.is_locked(), bool), f"locked={winsys.is_locked()}")

print("\n== 3. 电源接口 ==")
check("设置阻止休眠", winsys.keep_awake(True) is not False)
check("恢复正常休眠", winsys.keep_awake(False) is not False)
fut = time.time() + 600
arm_ok, arm_msg = winsys.arm_wake_timer(fut)
print(f"        arm_wake_timer -> {arm_ok}: {arm_msg}")
winsys.cancel_wake_timer()
check("唤醒定时器可设置/取消", arm_ok)

print("\n== 4. 截图 ==")
try:
    from core.capture import grab_client

    if hwnd:
        img = grab_client(hwnd)
        check("能抓取客户区截图", img is not None and img.size[0] > 0, str(img.size) if img else "None")
    else:
        print("  SKIP  没有目标窗口")
except Exception as e:
    check("截图模块", False, str(e))

print(f"\n结果: {ok} 通过, {fail} 失败")
sys.exit(1 if fail else 0)
