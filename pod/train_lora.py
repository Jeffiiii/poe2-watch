"""LoRA fine-tune of a small vision-language model on train.jsonl (frames of a 5 s window -> narration or answers).

Only the language model gets adapters (the vision tower keeps its weights); the loss is on the assistant turn only.
Each sample is seen once per epoch.

Usage: python train_lora.py [--model Qwen/Qwen3-VL-4B-Instruct] [--epochs 2] [--limit 0] [--out out/lora]
"""
import argparse
import json
import math
import os
import random
import time

import torch
from peft import LoraConfig, get_peft_model
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="Qwen/Qwen3-VL-4B-Instruct")
ap.add_argument("--data", default="train.jsonl")
ap.add_argument("--out", default="out/lora")
ap.add_argument("--epochs", type=int, default=2)
ap.add_argument("--lr", type=float, default=1e-4)
ap.add_argument("--accum", type=int, default=8)
ap.add_argument("--rank", type=int, default=16)
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--max-minutes", type=float, default=75, help="stop and save when this much time has gone")
a = ap.parse_args()
KEEP = int(os.environ.get("MAX_IMAGES", "99"))      # local smoke test on a small card: MAX_IMAGES=1
random.seed(0)
torch.manual_seed(0)
rows = [json.loads(l) for l in open(a.data, encoding="utf-8")]
# (narration used to be repeated once per epoch while it was scarcer than the questions; since run 5 the two are balanced)
if a.limit:
    random.shuffle(rows)
    rows = rows[: a.limit]
proc = AutoProcessor.from_pretrained(a.model)
model = AutoModelForImageTextToText.from_pretrained(a.model, dtype=torch.bfloat16, device_map={"": 0})
model = get_peft_model(model, LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, task_type="CAUSAL_LM",
                                         target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
model.print_trainable_parameters()
# 4 frames of 896 px make ~2.5k tokens; storing every layer's activations for backprop ran a 32 GB card out of memory.
# Checkpointing recomputes them in the backward pass instead: slower, but the peak drops to a fraction.
model.gradient_checkpointing_enable()
model.enable_input_require_grads()


def encode(ex):
    user = {"role": "user", "content": [{"type": "image", "image": Image.open(p).convert("RGB")} for p in ex["images"][-KEEP:]] + [{"type": "text", "text": ex["prompt"]}]}
    full = proc.apply_chat_template([user, {"role": "assistant", "content": [{"type": "text", "text": ex["target"]}]}],
                                    tokenize=True, return_dict=True, return_tensors="pt")
    head = proc.apply_chat_template([user], add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt")
    n = head["input_ids"].shape[1]
    assert torch.equal(full["input_ids"][0, :n], head["input_ids"][0]), "prompt is not a prefix of the full sequence"
    labels = full["input_ids"].clone()
    labels[:, :n] = -100
    full["labels"] = labels
    return full


params = [p for p in model.parameters() if p.requires_grad]
opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
total = math.ceil(len(rows) * a.epochs / a.accum)
sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 20) * 0.5 * (1 + math.cos(math.pi * min(s, total) / total)))
os.makedirs(a.out, exist_ok=True)
log = open(os.path.join(os.path.dirname(a.out) or ".", "train.log"), "a", encoding="utf-8")
t0, step, run, seen, stop = time.time(), 0, 0.0, 0, False
model.train()
for ep in range(a.epochs):
    random.shuffle(rows)
    for i, ex in enumerate(rows):
        batch = {k: v.to(model.device) for k, v in encode(ex).items()}
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss = model(**batch).loss
        (loss / a.accum).backward()
        run += loss.item()
        seen += 1
        if seen % a.accum == 0:
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            if step % 10 == 0 or step == 1:
                msg = f"epoch {ep + 1} step {step}/{total} loss {run / (a.accum if step == 1 else a.accum * 10):.3f} tokens {batch['input_ids'].shape[1]} {(time.time() - t0) / 60:.1f} min"
                print(msg, flush=True)
                log.write(msg + "\n")
                log.flush()
                run = 0.0 if step % 10 == 0 else run
                if step == 1:
                    run = 0.0
        if (time.time() - t0) / 60 > a.max_minutes:
            stop = True
            break
    model.save_pretrained(a.out)
    if stop:
        print("time limit reached, adapter saved", flush=True)
        break
print(f"done: {seen} samples, {step} steps, {(time.time() - t0) / 60:.1f} min -> {a.out}", flush=True)
