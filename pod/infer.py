"""Run the student (with or without the LoRA adapter) on the exam files and on the held-out narration.

  eval_*.jsonl          -> out/pred_<name>.<tag>.jsonl      one line per question {session, t0, type, answer, gold}
  narrate_heldout.jsonl -> out/narrate_heldout.<tag>.jsonl  {session, t0, student, teacher}; the student's own previous
                           state is fed to the next window, as it would be live

Usage: python infer.py --tag zeroshot            python infer.py --tag lora --adapter out/lora [--narrate]
"""
import argparse
import json
import os
import re
import time

import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="Qwen/Qwen3-VL-4B-Instruct")
ap.add_argument("--adapter", default="")
ap.add_argument("--tag", required=True)
ap.add_argument("--evals", default="eval_heldout.jsonl,eval_newchar.jsonl")
ap.add_argument("--narrate", action="store_true")
ap.add_argument("--limit", type=int, default=0, help="narration windows only; the exams always run in full")
ap.add_argument("--rep", type=float, default=1.1, help="repetition penalty for narration")
a = ap.parse_args()
KEEP = int(os.environ.get("MAX_IMAGES", "99"))      # local smoke test on a small card: MAX_IMAGES=1
proc = AutoProcessor.from_pretrained(a.model)
model = AutoModelForImageTextToText.from_pretrained(a.model, dtype=torch.bfloat16, device_map={"": 0})
if a.adapter:
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, a.adapter)
model.eval()
os.makedirs("out", exist_ok=True)


def ask(images, prompt, max_new, rep=1.0):
    user = {"role": "user", "content": [{"type": "image", "image": Image.open(p).convert("RGB")} for p in images[-KEEP:]] + [{"type": "text", "text": prompt}]}
    x = proc.apply_chat_template([user], add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt").to(model.device)
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        y = model.generate(**x, max_new_tokens=max_new, do_sample=False, repetition_penalty=rep)
    return proc.decode(y[0, x["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def as_json(s):
    m = re.search(r"\{.*\}", s, flags=re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


def lines(p, limit=0):
    rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    return rows[:limit] if limit else rows


t0 = time.time()
for f in [e for e in a.evals.split(",") if e]:
    out = f"out/pred_{f[5:-6]}.{a.tag}.jsonl"
    with open(out, "w", encoding="utf-8") as fh:
        for n, ex in enumerate(lines(f)):
            ans = as_json(ask(ex["images"], ex["prompt"], 220))
            for ty, gold in ex["qs"]:
                fh.write(json.dumps({"session": ex["session"], "t0": ex["t0"], "type": ty, "answer": str(ans.get(ty, "")), "gold": gold}, ensure_ascii=False) + "\n")
            fh.flush()
            if n % 20 == 0:
                print(f"{f} {n} {(time.time() - t0) / 60:.1f} min", flush=True)
if a.narrate:
    prev, last = "（刚开始看，没有上文）", None
    with open(f"out/narrate_heldout.{a.tag}.jsonl", "w", encoding="utf-8") as fh:
        for n, ex in enumerate(lines("narrate_heldout.jsonl", a.limit)):
            if last is None or ex["session"] != last[0] or ex["t0"] - last[1] > 5.5:
                prev = "（刚开始看，没有上文）"
            txt = ask(ex["images"], ex["template"].format(prev=prev), 900, rep=a.rep)   # run 2: 11/44 narrations looped to the cap
            st = as_json(txt).get("state")
            prev = json.dumps(st, ensure_ascii=False) if st else "（上一段没有读出局面）"
            last = (ex["session"], ex["t0"])
            fh.write(json.dumps({"session": ex["session"], "t0": ex["t0"], "student": txt, "teacher": ex["teacher"]}, ensure_ascii=False) + "\n")
            fh.flush()
            if n % 10 == 0:
                print(f"narrate {n} {(time.time() - t0) / 60:.1f} min", flush=True)
print(f"{a.tag} done in {(time.time() - t0) / 60:.1f} min", flush=True)
