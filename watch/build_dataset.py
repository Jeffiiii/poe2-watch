"""Turn the teacher's narration and the automatic questions into training / test samples for a small student model.

The student sees pixels only. So a sample holds the frames of one 5 s window, what the student itself said about the
previous window (during training: the teacher's state for it), and the target. Nothing from the client log, the HUD
reader, the outline or the character card goes into the input: that is the privileged side.

Two tasks
  narrate   frames + previous state -> the three-layer narration {scene, text, inferred, state}   (teacher, keep=true only)
  qa        frames + one question   -> a short answer                                              (symbolic stream, no model)

Three splits, by whole recording (never by window: neighbouring windows are near-duplicates)
  train     the recordings not named in --heldout, played by the main character
  heldout   recordings of the same character that the student never trains on
  newchar   recordings of any other character (a harder test: different skills, different HUD numbers)

Each line is {id, task, split, session, t0, t1, video, frames, messages, images}: `messages` + `images` is the chat form
most VLM fine-tuning code reads (one "<image>" per frame in the user turn). `video`, t0, t1 are kept so a trainer can cut
its own frames at a higher resolution: the 384 px frames listed here are too small to read HUD numbers.

Usage: python watch/build_dataset.py [--heldout s1,s2] [--main-character GSMZZG] [--frames 8]
Output: <work>/dataset/{narrate,qa}.{train,heldout,newchar}.jsonl and stats.json
"""
import argparse
import collections
import glob
import json
import os
import re

ap = argparse.ArgumentParser()
ap.add_argument("--work", default="C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--heldout", default="poe2_2026-10-04_211633,poe2_2026-10-04_214636")
ap.add_argument("--main-character", default="GSMZZG")
ap.add_argument("--frames", type=int, default=8, help="frames per window given to the student (the store has 4 fps = 20)")
a = ap.parse_args()
held = set(a.heldout.split(","))
OUT = os.path.join(a.work, "dataset")
os.makedirs(OUT, exist_ok=True)

NARRATE = ("你在实时看一段 Path of Exile 2 的画面。下面是最近 5 秒的 {n} 帧，按时间先后排列。\n"
           "上一个 5 秒的局面：{prev}\n"
           "请只根据画面写这 5 秒的讲解，输出 JSON：\n"
           "scene（画面里发生了什么，按先后）；text（屏幕上的文字和读数）；"
           "inferred（由画面推出的东西，每条带 basis 和 confidence，玩家意图只能写在这里）；state（place、activity、threat）。")
QA = "你在实时看一段 Path of Exile 2 的画面。下面是最近 5 秒的 {n} 帧，按时间先后排列。\n只根据画面回答，只写答案：{q}"


def clean_basis(inferred):
    """The teacher cites sources the student never sees (the episode outline, the automatic context). Run 5's student
    copied them ('basis: 段落提纲'). Outline-based reasoning is, for the student, reasoning from what it saw earlier."""
    if not isinstance(inferred, list):
        return inferred
    out = []
    for x in inferred:
        if isinstance(x, dict) and isinstance(x.get("basis"), str):
            x = dict(x, basis=re.sub("段落提纲|提纲", "上文", re.sub("自动上下文|上下文", "画面", x["basis"])))
        out.append(x)
    return out


def frames_of(session, t0, t1, fps, count):
    first, last = int(round(t0 * fps)) + 1, min(count, int(round(t1 * fps)))
    idx = [first + round(k * (last - first) / max(a.frames - 1, 1)) for k in range(a.frames)]
    return [f"frames/{session}/{i:06d}.jpg" for i in idx]


def sample(sid, task, split, S, t0, t1, frames, user, target):
    return {"id": sid, "task": task, "split": split, "session": S, "t0": t0, "t1": t1, "video": f"label_src/{S}.mp4", "frames": frames,
            "messages": [{"role": "user", "content": "<image>" * len(frames) + user}, {"role": "assistant", "content": target}],
            "images": frames}


files = collections.defaultdict(list)
stats = collections.defaultdict(collections.Counter)
for cp in sorted(glob.glob(os.path.join(a.work, "context", "*.jsonl"))):
    S = os.path.basename(cp)[:-6]
    ctx = [json.loads(l) for l in open(cp, encoding="utf-8")]
    if not ctx:
        continue
    fm = json.load(open(os.path.join(a.work, "frames", S, "frames.json")))
    who = ctx[0]["context"].get("character", "")
    # a recording named in --heldout is a test set: "heldout" for the main character, "newchar" for any other character;
    # every other recording trains, whoever plays it (run 4: the Monk recordings joined the training set)
    main = who.startswith(a.main_character + " ")
    split = ("heldout" if main else "newchar") if S in held else "train"
    stats[split]["sessions"] += 1
    stats[split]["minutes"] += round(fm["duration"] / 60)
    vp = os.path.join(a.work, "labels", f"{S}.validated.jsonl")
    if os.path.exists(vp):
        labs = sorted((json.loads(l) for l in open(vp, encoding="utf-8")), key=lambda r: r["t0"])
        by_t = {round(l["t0"]): l for l in labs}
        for lab in labs:
            if not lab.get("keep"):
                stats[split]["narrate_dropped"] += 1
                continue
            prev = by_t.get(round(lab["t0"] - 5))
            prev_txt = json.dumps(prev["state"], ensure_ascii=False) if prev and prev.get("keep") and prev.get("state") else "（刚开始看，没有上文）"
            fr = frames_of(S, lab["t0"], lab["t1"], fm["fps"], fm["count"])
            tgt = json.dumps({k: (clean_basis(lab.get(k)) if k == "inferred" else lab.get(k)) for k in ("scene", "text", "inferred", "state")}, ensure_ascii=False)
            files[("narrate", split)].append(sample(f"{S}@{lab['t0']:.0f}#narrate", "narrate", split, S, lab["t0"], lab["t1"], fr,
                                                    NARRATE.format(n=len(fr), prev=prev_txt), tgt))
            stats[split]["narrate"] += 1
    qp = os.path.join(a.work, "qa", f"{S}.jsonl")
    if os.path.exists(qp):
        for q in (json.loads(l) for l in open(qp, encoding="utf-8")):
            fr = frames_of(S, q["t0"], q["t1"], fm["fps"], fm["count"])
            s = sample(f"{S}@{q['t0']:.0f}#{q['type']}", "qa", split, S, q["t0"], q["t1"], fr, QA.format(n=len(fr), q=q["question"]), q["answer"])
            s["type"] = q["type"]
            files[("qa", split)].append(s)
            stats[split]["qa"] += 1
            stats[split]["qa:" + q["type"]] += 1
for (task, split), rows in sorted(files.items()):
    p = os.path.join(OUT, f"{task}.{split}.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{task:8s} {split:8s} {len(rows):6d} samples -> {p}")
json.dump({k: dict(v) for k, v in stats.items()}, open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in stats.items():
    print(f"{k}: {v['sessions']} recordings, {v['minutes']} min, narration {v['narrate']} (dropped {v['narrate_dropped']}), questions {v['qa']}")
