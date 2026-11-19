"""Automatic exam questions for every 5 s window, with answers taken from the symbolic stream, not from any model.

These questions serve two purposes: they score a student model that only sees the pixels, and they check the teacher's
narration against facts we can read independently (HUD numbers, Client.txt events, the Spirit-to-totem rule).

Question types (a window only gets the ones whose answer is known):
  zone_type      在城镇 / 藏身处 / 地图 / 其他区域 中的哪一类               from the client log
  zone_name      区域名                                                     from the client log
  bar_present    顶部有没有带红色血条的名条                                 from the HUD reader
  bar_name       名条上的名字                                               from the HUD reader (only when read with a name)
  died           玩家是否死亡                                               from the client log / HUD
  levelled       玩家是否升级                                               from the client log
  mana_trend     法力 上升 / 下降 / 基本不变（变化不到上限的 15% 算不变）   from the HUD reader
  life_trend     生命 上升 / 下降 / 基本不变                                from the HUD reader
  totems         窗口结束时场上有几个图腾（仅限 Spirit 规则已验证的角色）    from Spirit: (idle - spirit) / 60
  objective      目标面板第一条是什么                                       from the HUD reader (kept as reference text, scored leniently)

Output: <work>/qa/<session>.jsonl  one line per question {session, t0, t1, type, question, answer}
Usage: python watch/make_qa.py <session>
"""
import argparse
import collections
import re
import json
import os

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
a = ap.parse_args()
rows = [json.loads(l) for l in open(os.path.join(a.work, "context", f"{a.session}.jsonl"), encoding="utf-8")]
os.makedirs(os.path.join(a.work, "qa"), exist_ok=True)
is_totem_char = any("GSMZZG (" in r["context"].get("character", "") for r in rows[:1])
# idle Spirit for this recording = the highest value that occurs often (no totems up)
sp = collections.Counter()
for r in rows:
    for k in ("hud_start", "hud_end"):
        v = r["context"].get(k, {}).get("spirit")
        if v:
            sp[v[0]] += 1
common = [v for v, n in sp.items() if n >= max(3, sum(sp.values()) * 0.02)]
idle = max(common) if common else None


def trend(h0, h1, key):
    a0, a1 = h0.get(key), h1.get(key)
    if not a0 or not a1 or not a0[1]:
        return None
    d = (a1[0] - a0[0]) / a0[1]
    return "上升" if d > 0.15 else "下降" if d < -0.15 else "基本不变"


out = []
for r in rows:
    c = r["context"]
    q = []
    z = c.get("zone")
    if z and not c.get("loading") and not c.get("zone_change"):
        zl = z.lower()
        zt = "藏身处" if "hideout" in zl else "城镇" if "town" in zl else "地图" if zl.startswith("map") else "其他区域"
        q.append(("zone_type", "玩家此刻在城镇、藏身处、地图还是其他区域？", zt))
        if not re.match(r"^[A-Z]\d*_", z):        # campaign areas are logged as codes (G1_2); their names are not on screen
            q.append(("zone_name", "玩家所在区域叫什么名字？", z.split(" L")[0]))
    tgt = c.get("target")
    q.append(("bar_present", "屏幕顶部有没有带红色血条的怪物名条？", "有" if tgt else "没有"))
    if tgt and tgt.get("name") and tgt.get("name_confirmed"):
        q.append(("bar_name", "顶部名条上的名字是什么？", tgt["name"]))
    evs = " ".join(c.get("events", []))
    q.append(("died", "这个窗口里玩家死了吗？", "是" if ("log:death/self" in evs or "hud:death" in evs) else "否"))
    q.append(("levelled", "这个窗口里玩家升级了吗？", "是" if "log:levelup/self" in evs else "否"))
    for key, name in (("mana", "法力"), ("life", "生命")):
        t = trend(c.get("hud_start", {}), c.get("hud_end", {}), key)
        if t:
            q.append((key + "_trend", f"这个窗口里玩家的{name}是上升、下降还是基本不变？", t))
    s1 = c.get("hud_end", {}).get("spirit")
    if is_totem_char and idle and s1 and (idle - s1[0]) % 60 == 0 and 0 <= (idle - s1[0]) // 60 <= 8:
        q.append(("totems", "窗口结束时场上有几个图腾？", str((idle - s1[0]) // 60)))
    # the objective is the line right after the "MAP OBJECTIVES" / "OBJECTIVES" header; without the header the panel was
    # not read cleanly and the question is skipped (quest titles further down were being taken as the objective)
    lines = [o.strip() for o in (c.get("objectives") or "").split("|")]
    head = next((k for k, o in enumerate(lines) if "OBJECTIVES" in o.upper()), None)
    obj = [o for o in lines[head + 1 : head + 2] if len(o) > 6 and "CONTENT" not in o.upper()] if head is not None else []
    if obj:
        q.append(("objective", "目标面板上的第一条目标是什么？", obj[0]))
    out += [{"session": a.session, "t0": r["t0"], "t1": r["t1"], "type": ty, "question": qq, "answer": aa} for ty, qq, aa in q]
p = os.path.join(a.work, "qa", f"{a.session}.jsonl")
with open(p, "w", encoding="utf-8") as fh:
    for o in out:
        fh.write(json.dumps(o, ensure_ascii=False) + "\n")
cnt = collections.Counter(o["type"] for o in out)
print(f"{a.session}: {len(out)} questions over {len(rows)} windows (idle spirit {idle}): " + ", ".join(f"{k} {v}" for k, v in cnt.most_common()))
