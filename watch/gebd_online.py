"""Online (causal) generic event boundary detection on the Kinetics-GEBD validation subset, same signals as signals.py.

Per video: frames at --fps (default 8), squashed to 256x256; frozen V-JEPA 2 ViT-L features for sliding clips of --clip
frames (default 16 = 2 s) with stride --stride frames (default 2 = 0.25 s); per step the signals
  pixel_dhash  Hamming distance between the frame at the step and the previous step
  feat_drift   ||x_t - x_{t-1}|| on global features
  pred_err     GRU predictor error (predictor trained on the train split of videos only)
  state_change ||h_t - h_{t-1}||
  forecast_change ||xhat_{t+1|t} - xhat_{t+1|t-1}||
  pred_err_adaptive  ESTimator-style: pred_err standardised by a running mean/std of past errors in the same video
Detection is causal with a --lookahead of 2 steps (0.5 s): a step is a boundary if it is the local max within +-lookahead
and its score exceeds a threshold tuned on the train split. Metric: F1@Rel.Dis 0.05 (tolerance = 0.05 x annotated duration),
matching ported from the official Challenge_eval_Code/eval.py (best annotator, micro-averaged), plus stricter companions
(Rel.Dis 0.025, absolute 0.25 s, mean-annotator) because a 1 Hz comb saturates F1@0.05 (~0.72 on the full val set). Also reports the threshold-free AUROC of each score against +-tolerance labels.

Usage: python watch/gebd_online.py [--root C:/Users/Leo12/Videos/gebd-work] [--limit N] [--train-frac 0.6]
"""
import argparse
import csv
import json
import os
import subprocess
import time

import imagehash
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from sklearn.metrics import roc_auc_score

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=r"C:/Users/Leo12/Videos/gebd-work")
ap.add_argument("--model", default="facebook/vjepa2-vitl-fpc64-256")
ap.add_argument("--fps", type=int, default=8)
ap.add_argument("--clip", type=int, default=16)
ap.add_argument("--stride", type=int, default=2)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--train-frac", type=float, default=0.6)
ap.add_argument("--lookahead", type=int, default=2)
ap.add_argument("--rel-dis", type=float, default=0.05)
ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
torch.manual_seed(a.seed)
rng = np.random.RandomState(a.seed)

rows = list(csv.DictReader(open(os.path.join(a.root, "subset.csv"), encoding="utf-8")))
if a.limit:
    rows = rows[: a.limit]
fdir = os.path.join(a.root, "features")
os.makedirs(fdir, exist_ok=True)
RES = 256


def decode(path):
    """frames at a.fps, squashed to RES x RES, uint8 (T, RES, RES, 3)"""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={a.fps},scale={RES}:{RES}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (RES * RES * 3)
    return np.frombuffer(raw[: n * RES * RES * 3], np.uint8).reshape(n, RES, RES, 3)


# ------------------------------------------------------------------ 1. features (cached per video)
todo = [r for r in rows if not os.path.exists(os.path.join(fdir, r["file_name"] + ".npz"))]
print(f"{len(rows)} videos, {len(todo)} need features")
if todo:
    from transformers import AutoVideoProcessor, VJEPA2Model

    proc = AutoVideoProcessor.from_pretrained(a.model)
    model = VJEPA2Model.from_pretrained(a.model, dtype=torch.float16).to("cuda").eval()
    t0 = time.time()
    nclips = 0
    for i, r in enumerate(todo):
        frames = decode(os.path.join(a.root, "videos", r["file_name"]))
        if len(frames) < a.clip + a.stride:
            np.savez(os.path.join(fdir, r["file_name"] + ".npz"), t=np.zeros(0), **{"global": np.zeros((0, 1024), np.float16)}, dhash=np.zeros(0))
            continue
        starts = list(range(0, len(frames) - a.clip + 1, a.stride))
        G = []
        with torch.inference_mode():
            for b in range(0, len(starts), a.batch):
                vids = [frames[s : s + a.clip] for s in starts[b : b + a.batch]]
                pv = proc(videos=vids, return_tensors="pt")["pixel_values_videos"].to("cuda", torch.float16)
                h = model(pixel_values_videos=pv).last_hidden_state.float()
                G.append(h.mean(1).half().cpu())
        ends = [s + a.clip - 1 for s in starts]
        dh = np.zeros(len(ends))
        prev = None
        for k, e in enumerate(ends):
            hsh = imagehash.dhash(Image.fromarray(frames[e]), 8)
            dh[k] = (hsh - prev) if prev is not None else 0
            prev = hsh
        np.savez(os.path.join(fdir, r["file_name"] + ".npz"), t=np.array([(e + 0.5) / a.fps for e in ends], np.float32),
                 **{"global": torch.cat(G).numpy()}, dhash=dh)
        nclips += len(starts)
        if (i + 1) % 25 == 0:
            dt = time.time() - t0
            print(f"  {i + 1}/{len(todo)} videos, {nclips} clips, {dt / nclips * 1000:.0f} ms/clip, {dt / 60:.1f} min elapsed", flush=True)
    print(f"features done: {nclips} clips in {(time.time() - t0) / 60:.1f} min, peak VRAM {torch.cuda.max_memory_allocated() / 1e9:.2f} GB")

# ------------------------------------------------------------------ 2. load, split
vids = []
for r in rows:
    z = np.load(os.path.join(fdir, r["file_name"] + ".npz"))
    if len(z["t"]) < 4:
        continue
    vids.append({"name": r["file_name"], "t": z["t"], "X": z["global"].astype(np.float32), "dhash": z["dhash"],
                 "dur": float(r["duration_s"]), "ann": json.loads(r["boundaries_json"])})
perm = rng.permutation(len(vids))
ntr = int(len(vids) * a.train_frac)
train, test = [vids[i] for i in perm[:ntr]], [vids[i] for i in perm[ntr:]]
print(f"{len(vids)} usable videos: {len(train)} train, {len(test)} test")

# ------------------------------------------------------------------ 3. predictor on train videos
allX = np.concatenate([v["X"] for v in train])
mu, sd = allX.mean(0), allX.std(0) + 1e-6
for v in vids:
    v["Z"] = torch.tensor((v["X"] - mu) / sd)


class Predictor(nn.Module):
    def __init__(self, d=1024, h=256):
        super().__init__()
        self.inp = nn.Linear(d, h)
        self.gru = nn.GRU(h, h, batch_first=True)
        self.out = nn.Linear(h, d)

    def forward(self, x):
        hs, _ = self.gru(torch.tanh(self.inp(x)))
        return self.out(hs), hs


net = Predictor().cuda()
opt = torch.optim.Adam(net.parameters(), 1e-3, weight_decay=1e-4)
L = 24
for ep in range(1500):
    batch = [train[i] for i in rng.randint(0, len(train), 32)]
    xb, yb = [], []
    for v in batch:
        n = len(v["Z"])
        if n < L + 1:
            continue
        j = rng.randint(0, n - L)
        xb.append(v["Z"][j : j + L])
        yb.append(v["Z"][j + 1 : j + L + 1])
    xb, yb = torch.stack(xb).cuda(), torch.stack(yb).cuda()
    pred, _ = net(xb)
    loss = ((pred - yb) ** 2).mean()
    opt.zero_grad()
    loss.backward()
    opt.step()
    if ep % 300 == 0:
        print(f"  predictor epoch {ep} train mse {loss.item():.3f}")
net.eval()


def signals_for(v):
    with torch.no_grad():
        pred, hs = net(v["Z"][None].cuda())
        pred, hs = pred[0].cpu(), hs[0].cpu()
    Z = v["Z"]
    n = len(Z)
    pe = np.r_[0, ((pred[:-1] - Z[1:]) ** 2).mean(1).numpy()]
    st = np.r_[0, torch.norm(hs[1:] - hs[:-1], dim=1).numpy()]
    fc = np.r_[0, 0, torch.norm(pred[1:-1] - pred[:-2], dim=1).numpy()] if n > 2 else np.zeros(n)
    Xn = v["X"] / (np.linalg.norm(v["X"], axis=1, keepdims=True) + 1e-6)
    dr = np.r_[0, np.linalg.norm(Xn[1:] - Xn[:-1], axis=1)]
    # ESTimator-style standardisation by running statistics of past errors (causal)
    ad = np.zeros(n)
    for k in range(2, n):
        past = pe[1:k]
        ad[k] = (pe[k] - past.mean()) / (past.std() + 1e-6)
    return {"pixel_dhash": v["dhash"], "feat_drift": dr, "pred_err": pe, "pred_err_adaptive": ad,
            "state_change": st, "forecast_change": fc}


for v in vids:
    v["sig"] = signals_for(v)


# ------------------------------------------------------------------ 4. causal detection + F1 (official matching ported from eval.py)
def detect(score, thr, la):
    n = len(score)
    out = []
    for k in range(n):
        lo, hi = max(0, k - la), min(n, k + la + 1)
        if score[k] >= thr and score[k] == score[lo:hi].max():
            out.append(k)
    return out


def match_video(det_times, v, tol, pick="best"):
    """Official Challenge_eval_Code/eval.py logic: detections inside [0, dur]; per annotator greedy one-to-one matching
    with the outer loop over GT boundaries in time order, each taking its nearest unmatched detection; precision 0 when
    no detections, recall 1 when the annotator has no boundaries; best annotator = first argmax of per-video F1.
    pick="mean" instead averages tp/num_det/num_pos over annotators (companion metric the comb cannot game)."""
    dets = sorted(d for d in det_times if 0 <= d <= v["dur"])
    per = []
    for ann in v["ann"]:
        remaining = list(dets)
        tp = 0
        for g in sorted(ann):
            if not remaining:
                break
            j = int(np.argmin([abs(d - g) for d in remaining]))
            if abs(remaining[j] - g) <= tol:
                tp += 1
                remaining.pop(j)
        nd, ng = len(dets), len(ann)
        p = tp / nd if nd else 0.0
        r = tp / ng if ng else 1.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        per.append((f1, tp, nd, ng))
    if pick == "mean":
        return (np.mean([x[1] for x in per]), np.mean([x[2] for x in per]), np.mean([x[3] for x in per]))
    best = per[int(np.argmax([x[0] for x in per]))]
    return best[1:]


METRICS = {"F1@Rel0.05": ("rel", 0.05, "best"), "F1@Rel0.025": ("rel", 0.025, "best"),
           "F1@abs0.25s": ("abs", 0.25, "best"), "F1@Rel0.05 mean-ann": ("rel", 0.05, "mean")}


def f1_set(vs, dets_fn, metric):
    kind, val, pick = METRICS[metric]
    TP = ND = NG = 0.0
    for v in vs:
        tol = val * v["dur"] if kind == "rel" else val
        tp, nd, ng = match_video(dets_fn(v), v, tol, pick)
        TP += tp
        ND += nd
        NG += ng
    p = TP / ND if ND else 0.0
    r = TP / NG if NG else 0.0
    return (2 * p * r / (p + r) if p + r else 0.0), p, r


def auroc(vs, name, rel=0.05):
    ys, ss = [], []
    for v in vs:
        tol = rel * v["dur"]
        allb = [b for ann in v["ann"] for b in ann]
        for k, t in enumerate(v["t"]):
            ys.append(int(any(abs(t - b) <= tol for b in allb)))
            ss.append(v["sig"][name][k])
    ys, ss = np.array(ys), np.nan_to_num(np.array(ss))
    return roc_auc_score(ys, ss) if 0 < ys.sum() < len(ys) else float("nan")


names = ["pixel_dhash", "feat_drift", "pred_err", "pred_err_adaptive", "state_change", "forecast_change"]
cols = ["signal", "thr (train, F1@0.05)", "dets/10s test"] + list(METRICS) + ["P@0.05", "R@0.05", "AUROC@0.05"]
lines = [f"# Kinetics-GEBD val subset, online protocol: {len(train)} train / {len(test)} test videos, {a.fps} fps, clip {a.clip} stride {a.stride}, "
         f"lookahead {a.lookahead} steps ({a.lookahead * a.stride / a.fps:.2f} s). Matching ported from the official eval.py "
         f"(best annotator, micro-averaged); the 1 Hz comb row is the null: under the official F1@Rel.Dis 0.05 it scores ~0.72 on the full val set, "
         f"above the PC baseline 0.625 and ESTimator 0.620, because a 0.5 s tolerance at 1 Hz covers every boundary (see gebd-work/EVAL_PROTOCOL_NOTES.md).",
         "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]


def row(label, thr_txt, dets_fn, auc_txt):
    rate = np.mean([len(dets_fn(v)) / v["dur"] * 10 for v in test])
    vals = [f1_set(test, dets_fn, m)[0] for m in METRICS]
    _, p, r = f1_set(test, dets_fn, "F1@Rel0.05")
    lines.append("| " + " | ".join([label, thr_txt, f"{rate:.1f}"] + [f"{x:.3f}" for x in vals] + [f"{p:.3f}", f"{r:.3f}", auc_txt]) + " |")


for name in names:
    allv = np.concatenate([v["sig"][name] for v in train])
    cands = np.quantile(np.nan_to_num(allv), np.linspace(0.5, 0.995, 40))
    best = max(((f1_set(train, lambda v, c=c: [v["t"][k] for k in detect(v["sig"][name], c, a.lookahead)], "F1@Rel0.05")[0], c) for c in cands),
               key=lambda x: x[0])
    thr = best[1]
    row(name, f"{thr:.3f} (train F1 {best[0]:.3f})", lambda v, thr=thr, name=name: [v["t"][k] for k in detect(v["sig"][name], thr, a.lookahead)],
        f"{auroc(test, name):.3f}")
for period in (1.0, 1.5, 2.0):
    row(f"comb every {period:.1f} s", "-", lambda v, period=period: list(np.arange(period, v["dur"], period)), "-")
row("midpoint only", "-", lambda v: [v["dur"] / 2], "-")
text = "\n".join(lines) + "\n"
print(text)
open(os.path.join(a.root, "results_online_gebd.md"), "w", encoding="utf-8").write(text)
