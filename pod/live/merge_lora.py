"""Fold a LoRA adapter into the base weights so vLLM can serve the student as a plain model.
Usage: python merge_lora.py --base Qwen/Qwen3-VL-4B-Instruct --adapter /workspace/lora --out /workspace/merged
"""
import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoProcessor

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="Qwen/Qwen3-VL-4B-Instruct")
ap.add_argument("--adapter", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
model = AutoModelForImageTextToText.from_pretrained(a.base, dtype=torch.bfloat16, device_map={"": 0})
model = PeftModel.from_pretrained(model, a.adapter).merge_and_unload()
model.save_pretrained(a.out, safe_serialization=True)
AutoProcessor.from_pretrained(a.base).save_pretrained(a.out)
print("merged ->", a.out)
