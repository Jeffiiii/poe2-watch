"""Check the teacher's narration against facts read independently of any model (Client.txt, HUD reader).

A disagreement is not automatically the teacher's fault: the HUD reader misreads too. So every check yields one of
  agree / disagree / n-a
and a window is marked `keep` only when it has no hard disagreement; the rest go to a review list.

Checks per window
  death      log says the player died  <->  narration mentions death (死亡 / 阵亡 / You Have Died); and the reverse
  levelup    log says level up         <->  narration mentions it (升级 / level N)
  bar_name   HUD reader read a name on the top bar  <->  that name (letters only, >= 70% of it) occurs in the narration
  life_num   a "Life a/b" style number in the narration's text layer  <->  some HUD reading of life in that window (+-3%)
  mana_num   same for mana
  zone       log zone type (hideout / town / map)  <->  the narration's state.place wording

Output: <work>/labels/<session>.validated.jsonl (the label row + checks + keep) and a printed summary.
Usage: python watch/validate_labels.py <session>
"""
import argparse
import collections
import csv
import json
import os
import re

import hud_clean

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
a = ap.parse_args()
S = a.session
labels = sorted((json.loads(l) for l in open(os.path.join(a.work, "labels", f"{S}.windows.jsonl"), encoding="utf-8")), key=lambda r: r["t0"])
ctx = {round(json.loads(l)["t0"]): json.loads(l)["context"] for l in open(os.path.join(a.work, "context", f"{S}.jsonl"), encoding="utf-8")}
hud = {}
hp = os.path.join(a.work, "raw", f"{S}.hud.csv")
if os.path.exists(hp):
    for r in hud_clean.load(hp):
        hud[int(r["t"])] = r


def letters(s):
    return re.sub(r"[^a-z]", "", s.lower())


def nums(text, word):
    """all 'a/b' pairs that follow the given word (Life / 生命 / Mana / 法力) within a short distance"""
    out = []
    for m in re.finditer(word + r"[^0-9]{0,12}(\d[\d,]*)\s*/\s*(\d[\d,]*)", text, flags=re.I):
        try:
            out.append((int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))))
        except ValueError:
            pass
    return out


tot = collections.Counter()
rows = []
for lab in labels:
    c = ctx.get(round(lab["t0"]), {})
    full = " ".join([lab.get("scene", ""), lab.get("text", ""), json.dumps(lab.get("inferred", ""), ensure_ascii=False), json.dumps(lab.get("state", ""), ensure_ascii=False)])
    evs = " ".join(c.get("events", []))
    chk = {}
    said_death = bool(re.search(r"阵亡|死亡|You Have Died|已死|倒地身亡|暴毙", full, flags=re.I))
    log_death = "log:death/self" in evs
    chk["death"] = "agree" if said_death == log_death else ("disagree" if log_death and not said_death else "n-a" if not log_death and said_death else "agree")
    if "log:levelup/self" in evs:
        chk["levelup"] = "agree" if re.search(r"升级|升到|level\s*\d+|now level", full, flags=re.I) else "disagree"
    tgt = c.get("target") or {}
    if tgt.get("name") and tgt.get("name_confirmed") and len(letters(tgt["name"])) >= 5:
        want = letters(tgt["name"])
        hay = letters(full)
        hit = want in hay or any(want[i : i + max(5, int(len(want) * 0.7))] in hay for i in range(0, max(1, len(want) - int(len(want) * 0.7) + 1)))
        chk["bar_name"] = "agree" if hit else "disagree"
    for key, word in (("life", r"(?:Life|生命)"), ("mana", r"(?:Mana|法力)")):
        said = nums(lab.get("text", ""), word)
        seen = []
        for s in range(int(lab["t0"]) - 2, int(lab["t1"]) + 3):
            r = hud.get(s)
            if r and r.get(key) is not None:
                seen.append((int(r[key]), int(r[key + "_max"])))
        if said and seen:
            ok = any(abs(sm - hm) <= 0.03 * hm and abs(sc - hc) <= max(3, 0.03 * hm) for sc, sm in said for hc, hm in seen)
            ok_max = any(abs(sm - hm) <= 0.03 * hm for _, sm in said for _, hm in seen)
            chk[key + "_num"] = "agree" if ok else ("partial" if ok_max else "disagree")
    z = (c.get("zone") or "").lower()
    place = json.dumps(lab.get("state", ""), ensure_ascii=False).lower()
    if z and not c.get("loading") and not c.get("zone_change"):
        zt = "hideout" if "hideout" in z else "town" if "town" in z else "map" if z.startswith("map") else ""
        if zt == "hideout":
            chk["zone"] = "agree" if ("hideout" in place or "藏身处" in place) else "disagree"
        elif zt == "town":
            chk["zone"] = "agree" if re.search(r"encampment|town|城镇|营地|村", place) else "disagree"
        elif zt == "map":
            chk["zone"] = "disagree" if ("hideout" in place or "藏身处" in place) else "agree"
    hard = [k for k in ("death", "levelup", "bar_name", "zone") if chk.get(k) == "disagree"]
    soft = [k for k in ("life_num", "mana_num") if chk.get(k) == "disagree"]
    lab2 = dict(lab, checks=chk, keep=not hard, review=hard + soft)
    rows.append(lab2)
    for k, v in chk.items():
        tot[(k, v)] += 1
p = os.path.join(a.work, "labels", f"{S}.validated.jsonl")
with open(p, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
keep = sum(r["keep"] for r in rows)
conf = sum(1 for r in rows if [c for c in r.get("context_conflicts", []) if c and c != "无"])
print(f"{S}: {len(rows)} labelled windows, keep {keep} ({keep / max(len(rows), 1):.0%}), teacher flagged a context conflict in {conf}")
for k in ("death", "levelup", "bar_name", "zone", "life_num", "mana_num"):
    ag, di, pa = tot[(k, "agree")], tot[(k, "disagree")], tot[(k, "partial")]
    if ag + di + pa:
        print(f"   {k:9s} agree {ag:4d}  disagree {di:4d}" + (f"  max-only {pa}" if pa else "") + f"   ({ag / (ag + di + pa):.0%})")
