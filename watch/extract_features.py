"""Frozen V-JEPA 2 ViT-L features for one session, from its 4 fps frames.

Sliding clips of --clip frames (default 16 = 4 s at 4 fps) with stride --stride frames (default 4 = 1 s).
Each frame is squashed to 256x256 (keeps the whole screen including the HUD); --mode crop gives the standard
short-side resize + center crop instead.

Saves <out-root>/<session>.vjepa2.npz with fp16 arrays:
  t        (N,)          clip END time in seconds
  global   (N, 1024)     mean over all tokens
  temporal (N, T/2, 1024) mean over space per temporal slot (2 frames per slot)
  spatial  (N, 16, 1024) mean over time, 4x4 spatial pooling of the 16x16 token grid
Prints throughput and peak VRAM, then times one batch of 64-frame clips as a second data point.

Usage: python watch/extract_features.py <frames-dir> [--batch 8] [--limit N]
"""
import argparse
import json
import os
import time

import numpy as np
import torch
from PIL import Image
from transformers import AutoVideoProcessor, VJEPA2Model

ap = argparse.ArgumentParser()
ap.add_argument("frames")
ap.add_argument("--out-root", default=r"C:/Users/Leo12/Videos/poe2-work/features")
ap.add_argument("--model", default="facebook/vjepa2-vitl-fpc64-256")
ap.add_argument("--clip", type=int, default=16)
ap.add_argument("--stride", type=int, default=4)
ap.add_argument("--batch", type=int, default=8)
ap.add_argument("--mode", choices=["squash", "crop"], default="squash")
ap.add_argument("--limit", type=int, default=0, help="only the first N clips (smoke test)")
a = ap.parse_args()

meta = json.load(open(os.path.join(a.frames, "frames.json")))
fps = meta["fps"]
session = meta["session"]
files = sorted(f for f in os.listdir(a.frames) if f.endswith(".jpg"))
dev, dtype = "cuda", torch.float16

proc = AutoVideoProcessor.from_pretrained(a.model)
model = VJEPA2Model.from_pretrained(a.model, dtype=dtype).to(dev).eval()
crop = getattr(proc, "crop_size", None)
res = crop["height"] if isinstance(crop, dict) else 256


def load(f):
    im = Image.open(os.path.join(a.frames, f)).convert("RGB")
    if a.mode == "squash":
        im = im.resize((res, res), Image.BICUBIC)
    return np.asarray(im)


t0 = time.time()
frames = np.stack([load(f) for f in files])
print(f"loaded {len(files)} frames in {time.time() - t0:.0f} s, {frames.nbytes / 1e9:.2f} GB RAM")

starts = list(range(0, len(files) - a.clip + 1, a.stride))
if a.limit:
    starts = starts[: a.limit]
N = len(starts)
print(f"{N} clips of {a.clip} frames, stride {a.stride}")

G, Tm, Sp, Ts = [], [], [], []
torch.cuda.reset_peak_memory_stats()
t0 = time.time()
with torch.inference_mode():
    for b in range(0, N, a.batch):
        idx = starts[b : b + a.batch]
        vids = [frames[s : s + a.clip] for s in idx]
        pv = proc(videos=vids, return_tensors="pt")["pixel_values_videos"].to(dev, dtype)
        h = model(pixel_values_videos=pv).last_hidden_state.float()  # (B, T/2*256, 1024)
        B = h.shape[0]
        Tt = a.clip // 2
        h = h.view(B, Tt, 16, 16, -1)
        G.append(h.mean((1, 2, 3)).half().cpu())
        Tm.append(h.mean((2, 3)).half().cpu())
        sp = h.mean(1).view(B, 4, 4, 4, 4, -1).mean((2, 4)).reshape(B, 16, -1)
        Sp.append(sp.half().cpu())
        Ts += [(s + a.clip - 1) / fps for s in idx]
        if b == 0:
            torch.cuda.synchronize()
            print("pixel_values", tuple(pv.shape), "tokens per clip", Tt * 256)
torch.cuda.synchronize()
dt = time.time() - t0
print(f"{N} clips in {dt:.1f} s = {dt / N * 1000:.0f} ms/clip = {N / dt:.1f} clips/s "
      f"(one clip per video second, so {N / dt:.1f}x realtime)")
print(f"peak VRAM {torch.cuda.max_memory_allocated() / 1e9:.2f} GB (reserved {torch.cuda.max_memory_reserved() / 1e9:.2f} GB)")

os.makedirs(a.out_root, exist_ok=True)
out = os.path.join(a.out_root, f"{session}.vjepa2.npz")
np.savez(out, t=np.array(Ts, np.float32), **{"global": torch.cat(G).numpy(), "temporal": torch.cat(Tm).numpy(),
         "spatial": torch.cat(Sp).numpy()},
         meta=json.dumps({"model": a.model, "clip": a.clip, "stride": a.stride, "fps": fps, "mode": a.mode}))
print("saved", out, f"{os.path.getsize(out) / 1e6:.1f} MB")

# second timing point: 64-frame clips, the model's pretraining clip length
with torch.inference_mode():
    if len(files) >= 128:
        vids = [frames[0:64], frames[64:128]]
        pv = proc(videos=vids, return_tensors="pt")["pixel_values_videos"].to(dev, dtype)
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        t0 = time.time()
        for _ in range(3):
            model(pixel_values_videos=pv)
        torch.cuda.synchronize()
        print(f"64-frame clips: {(time.time() - t0) / 3 / len(vids) * 1000:.0f} ms/clip, "
              f"peak VRAM {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")
