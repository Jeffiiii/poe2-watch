"""The student's exam: answer the automatic questions from pixels only, and be scored against the symbolic stream.

  run    ask a local model (Ollama, vision) every question of a sample of windows; one call per window
         python watch/eval_student.py run --split heldout --model qwen3.5:9b [--n 60] [--frames 4] [--width 1280]
         -> <work>/dataset/pred/<split>.<model>.f<frames>w<width>.jsonl   (resumable)
  score  score a prediction file (from `run`, or from any other model that wrote the same lines)
         python watch/eval_student.py score <pred.jsonl>

A prediction line is {session, t0, type, answer, gold}. Scoring is by question type; next to each accuracy the table
shows what always answering the most common answer would get, because most questions are lopsided (the player rarely
dies). For yes/no questions the recall on the rare answer is the number to look at.

The sample of windows is not uniform: every window whose answer to died / levelled is "是" is taken first, the rest is
drawn at random (seed 0), so rare events are present even in a small sample.
"""
import argparse
import base64
import collections
import difflib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["run", "score"])
ap.add_argument("pred", nargs="?")
ap.add_argument("--work", default="C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--split", default="heldout")
ap.add_argument("--model", default="qwen3.5:9b")
ap.add_argument("--n", type=int, default=60)
ap.add_argument("--frames", type=int, default=4)
ap.add_argument("--width", type=int, default=1280)
ap.add_argument("--host", default="http://127.0.0.1:11434")
a = ap.parse_args()
DS = os.path.join(a.work, "dataset")

CHOICES = {"zone_type": "城镇 / 藏身处 / 地图 / 其他区域", "bar_present": "有 / 没有", "died": "是 / 否", "levelled": "是 / 否",
           "mana_trend": "上升 / 下降 / 基本不变", "life_trend": "上升 / 下降 / 基本不变", "totems": "一个整数"}


def letters(s):
    return re.sub(r"[^a-z]", "", str(s).lower())


def words(s):
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(s))
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in ("map", "the", "l")}


def norm(ty, s):
    s = str(s).strip()
    if ty in ("died", "levelled"):
        return "否" if re.search(r"否|没|不|^no|false", s, flags=re.I) else "是" if re.search(r"是|^yes|true|死了|升级了", s, flags=re.I) else "?"
    if ty == "bar_present":
        return "没有" if re.search(r"没|无|否|^no|false", s, flags=re.I) else "有" if re.search(r"有|是|^yes|true", s, flags=re.I) else "?"
    if ty.endswith("_trend"):
        return next((k for k in ("基本不变", "上升", "下降") if k[-2:] in s), "?")
    if ty == "zone_type":
        return next((k for k in ("藏身处", "城镇", "地图", "其他区域") if k[:2] in s), "?")
    if ty == "totems":
        m = re.search(r"\d+", s)
        return m.group(0) if m else "?"
    return s


def right(ty, pred, gold):
    if ty == "zone_name":
        return bool(words(gold)) and words(gold) <= words(pred)
    if ty in ("bar_name", "objective"):
        return difflib.SequenceMatcher(None, letters(pred), letters(gold)).ratio() >= 0.8
    return norm(ty, pred) == gold


def score(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["type"]].append(r)
    print(f"{os.path.basename(path)}: {len(rows)} answers over {len({(r['session'], r['t0']) for r in rows})} windows")
    print(f"{'question':12s} {'n':>4s} {'right':>6s} {'always-common':>14s}   rare answer recall")
    out = {}
    for ty, rs in sorted(by.items()):
        ok = [right(ty, r["answer"], r["gold"]) for r in rs]
        gold = collections.Counter(r["gold"] for r in rs)
        common, ncommon = gold.most_common(1)[0]
        base = ncommon / len(rs) if ty in CHOICES else 0.0
        extra = ""
        if ty in ("died", "levelled", "bar_present") and len(gold) > 1:
            rare = min(gold, key=gold.get)
            hit = sum(1 for r, o in zip(rs, ok) if r["gold"] == rare and o)
            extra = f"「{rare}」 {hit}/{gold[rare]}"
        unans = sum(1 for r in rs if ty in CHOICES and norm(ty, r["answer"]) == "?")
        print(f"{ty:12s} {len(rs):4d} {sum(ok) / len(rs):6.0%} {base:14.0%}   {extra}" + (f"  (unparsed {unans})" if unans else ""))
        out[ty] = {"n": len(rs), "acc": round(sum(ok) / len(rs), 3), "majority": round(base, 3)}
    json.dump(out, open(path[:-6] + ".score.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def cut_frames(session, t0):
    d = os.path.join(DS, "eval_frames", session, f"{t0:06.0f}_f{a.frames}w{a.width}")
    got = sorted(f for f in os.listdir(d)) if os.path.isdir(d) else []
    if len(got) < a.frames:
        os.makedirs(d, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0 + 2.5 / a.frames:.2f}", "-i", os.path.join(a.work, "label_src", session + ".mp4"),
                        "-vf", f"fps={a.frames}/5,scale={a.width}:-2", "-frames:v", str(a.frames), "-q:v", "3", os.path.join(d, "%02d.jpg")], check=True)
        got = sorted(os.listdir(d))
    return [os.path.join(d, f) for f in got[: a.frames]]


def run():
    qs = collections.defaultdict(list)
    for r in (json.loads(l) for l in open(os.path.join(DS, f"qa.{a.split}.jsonl"), encoding="utf-8")):
        qs[(r["session"], r["t0"])].append((r["type"], r["messages"][0]["content"].split("只写答案：")[-1], r["messages"][1]["content"]))
    keys = sorted(qs)
    must = [k for k in keys if any(ty in ("died", "levelled") and g == "是" for ty, _, g in qs[k])]
    rest = [k for k in keys if k not in must]
    random.Random(0).shuffle(rest)
    pick = sorted(must + rest[: max(0, a.n - len(must))])
    os.makedirs(os.path.join(DS, "pred"), exist_ok=True)
    out = os.path.join(DS, "pred", f"{a.split}.{a.model.replace(':', '-').replace('/', '_')}.f{a.frames}w{a.width}.jsonl")
    done = {(r["session"], r["t0"]) for r in map(json.loads, open(out, encoding="utf-8"))} if os.path.exists(out) else set()
    print(f"{len(pick)} windows ({len(must)} with a death or level-up), {len(done & set(pick))} already answered -> {out}", flush=True)
    t_start = time.time()
    for n, k in enumerate(pick):
        if k in done:
            continue
        S, t0 = k
        imgs = [base64.b64encode(open(p, "rb").read()).decode() for p in cut_frames(S, t0)]
        lines = [f'"{ty}": {q}' + (f"（{CHOICES[ty]}）" if ty in CHOICES else "") for ty, q, _ in qs[k]]
        prompt = (f"这是一段 Path of Exile 2 画面里连续 5 秒的 {len(imgs)} 帧，按时间先后排列。只根据画面回答下面的问题，"
                  "输出一个 JSON 对象，键就是引号里的名字，值是简短答案；看不出来就写「看不出」。\n" + "\n".join(lines))
        body = {"model": a.model, "stream": False, "think": False, "format": "json", "options": {"temperature": 0, "num_ctx": 16384},
                "messages": [{"role": "user", "content": prompt, "images": imgs}]}
        t1 = time.time()
        try:
            req = urllib.request.Request(a.host + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            txt = json.loads(urllib.request.urlopen(req, timeout=600).read())["message"]["content"]
            ans = json.loads(txt)
        except Exception as e:
            print(f"  {S} {t0:.0f}: {type(e).__name__} {str(e)[:120]}", flush=True)
            ans = {}
        with open(out, "a", encoding="utf-8") as fh:
            for ty, _, g in qs[k]:
                fh.write(json.dumps({"session": S, "t0": t0, "type": ty, "answer": str(ans.get(ty, "")), "gold": g}, ensure_ascii=False) + "\n")
        if n % 10 == 0:
            print(f"  {n + 1}/{len(pick)}  {time.time() - t1:.0f} s this window, {(time.time() - t_start) / 60:.1f} min so far", flush=True)
    return out


if a.cmd == "run":
    score(run())
else:
    if not a.pred:
        sys.exit("score needs a prediction file")
    score(a.pred)
