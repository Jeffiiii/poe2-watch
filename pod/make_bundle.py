"""Pack what the rented GPU needs into <work>/pod: compact sample files that point at the 896 px frames (4 per 5 s window).

  train.jsonl            {images, prompt, target}             narration (teacher, keep=true) + all questions of a window as one JSON answer
  eval_heldout.jsonl     {session, t0, images, prompt, qs}    every window of the held-out recording
  eval_newchar.jsonl     same, a sample of the other character's windows (all level-ups / deaths first, then random, seed 0)
  narrate_heldout.jsonl  {session, t0, images, template, teacher}   in time order; the student's own previous state fills {prev}

Frames come from one ffmpeg pass per recording (fps=4/5), so window k uses files 4k+1 .. 4k+4.
Usage: python pod/make_bundle.py [--newchar-n 150]
"""
import argparse
import collections
import json
import os
import random

ap = argparse.ArgumentParser()
ap.add_argument("--work", default="C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--newchar-n", type=int, default=150)
ap.add_argument("--hires", default="f1280", help="folder of the frames used for the first and last frame (f896 = old setting)")
a = ap.parse_args()
DS, POD = os.path.join(a.work, "dataset"), os.path.join(a.work, "pod")
CHOICES = {"zone_type": "城镇 / 藏身处 / 地图 / 其他区域", "bar_present": "有 / 没有", "died": "是 / 否", "levelled": "是 / 否",
           "mana_trend": "上升 / 下降 / 基本不变", "life_trend": "上升 / 下降 / 基本不变", "totems": "一个整数"}
NARRATE = ("你在实时看一段 Path of Exile 2 的画面。这是最近 5 秒的 4 帧，按时间先后排列。\n上一个 5 秒的局面：{prev}\n"
           "请只根据画面写这 5 秒的讲解，输出 JSON：scene（画面里发生了什么，按先后）；text（屏幕上的文字和读数）；"
           "inferred（由画面推出的东西，每条带 basis 和 confidence，玩家意图只能写在这里）；state（place、activity、threat）。")
QA_HEAD = ("这是一段 Path of Exile 2 画面里连续 5 秒的 4 帧，按时间先后排列。只根据画面回答下面的问题，"
           "输出一个 JSON 对象，键就是引号里的名字，值是简短答案；看不出来就写「看不出」。\n")


def images(S, t0):
    """first and last frame at 1280 px (HUD digits readable: run 2 wrote 1,492 as 492 at 896 px), the two middle ones at 896"""
    k = int(round(t0 / 5))
    ps = [f"{a.hires}/{S}/{4 * k + 1:05d}.jpg", f"f896/{S}/{4 * k + 2:05d}.jpg", f"f896/{S}/{4 * k + 3:05d}.jpg", f"{a.hires}/{S}/{4 * k + 4:05d}.jpg"]
    return ps if all(os.path.exists(os.path.join(POD, p)) for p in ps) else None


def load(name):
    p = os.path.join(DS, name)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []


def grouped(split):
    g = collections.defaultdict(list)
    for r in load(f"qa.{split}.jsonl"):
        g[(r["session"], r["t0"])].append((r["type"], r["messages"][0]["content"].split("只写答案：")[-1], r["messages"][1]["content"]))
    out = {}
    for k, qs in g.items():
        im = images(*k)
        if im:
            lines = [f'"{ty}": {q}' + (f"（{CHOICES[ty]}）" if ty in CHOICES else "") for ty, q, _ in qs]
            out[k] = {"session": k[0], "t0": k[1], "images": im, "prompt": QA_HEAD + "\n".join(lines), "qs": [[ty, g_] for ty, _, g_ in qs]}
    return out


def dump(name, rows):
    with open(os.path.join(POD, name), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{name}: {len(rows)}")


train = []
for r in load("narrate.train.jsonl"):
    im = images(r["session"], r["t0"])
    if im:
        prev = r["messages"][0]["content"].split("上一个 5 秒的局面：")[1].split("\n")[0]
        train.append({"task": "narrate", "images": im, "prompt": NARRATE.format(prev=prev), "target": r["messages"][1]["content"]})
for k, e in sorted(grouped("train").items()):
    rare = any(ty in ("died", "levelled") and g == "是" for ty, g in e["qs"])     # one death and one level-up in 69 min: repeat them
    train += [{"task": "qa", "images": e["images"], "prompt": e["prompt"], "target": json.dumps(dict(e["qs"]), ensure_ascii=False)}] * (5 if rare else 1)
dump("train.jsonl", train)
held = grouped("heldout")
dump("eval_heldout.jsonl", [held[k] for k in sorted(held)])
new = grouped("newchar")
must = [k for k in sorted(new) if any(ty in ("died", "levelled") and g == "是" for ty, g in new[k]["qs"])]
rest = [k for k in sorted(new) if k not in must]
random.Random(0).shuffle(rest)
dump("eval_newchar.jsonl", [new[k] for k in sorted(must + rest[: max(0, a.newchar_n - len(must))])])
nar = []
for r in sorted(load("narrate.heldout.jsonl"), key=lambda r: (r["session"], r["t0"])):
    im = images(r["session"], r["t0"])
    if im:
        nar.append({"session": r["session"], "t0": r["t0"], "images": im, "template": NARRATE, "teacher": r["messages"][1]["content"]})
dump("narrate_heldout.jsonl", nar)
used = {p for f in ("train.jsonl", "eval_heldout.jsonl", "eval_newchar.jsonl", "narrate_heldout.jsonl")
        for l in open(os.path.join(POD, f), encoding="utf-8") for p in json.loads(l)["images"]}
open(os.path.join(POD, "files.txt"), "w", newline="\n").write("\n".join(sorted(used)) + "\n")
print("frames used:", len(used))
