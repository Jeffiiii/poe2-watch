"""Leave-one-session-out evaluation across all processed sessions.

For each session: the predictor is trained on every OTHER session (features standardised with the training sessions'
statistics), then run causally over the held-out session to produce pred_err / state_change / forecast_change.
Pixel signals and feature drift need no training. Every signal is z-scored within its session, the held-out seconds of
all folds are pooled, and each signal is scored against three label sets:
  marks        the player's live marks
  events_vis   loading_done + death + levelup from Client.txt
  events_zone  loading_done only
Metrics: pooled AP and AUROC with positives = +-2 s around a label (and +-1 s), and recall of labels when each session
gets as many triggers as it has labels (3 s non-max suppression). Chance AP is the positive rate.

Usage: python watch/signals_joint.py [--work C:/Users/Leo12/Videos/poe2-work] [--epochs 2000] [--hidden 256] [--horizon 1]
  --horizon k trains the predictor to predict the feature k seconds ahead (default 1).
"""
import argparse
import csv
import glob
import json
import os

import cv2
import imagehash
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from sklearn.metrics import average_precision_score, roc_auc_score

ap = argparse.ArgumentParser()
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--epochs", type=int, default=2000)
ap.add_argument("--hidden", type=int, default=256)
ap.add_argument("--horizon", type=int, default=1)
ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
torch.manual_seed(a.seed)
rng = np.random.RandomState(a.seed)
dev = "cuda" if torch.cuda.is_available() else "cpu"


def read_times(session, name, keep=None):
    p = os.path.join(a.work, "raw", f"{session}.{name}.csv")
    if not os.path.exists(p):
        return []
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    if keep:
        rows = [r for r in rows if r.get("type") in keep]
    return sorted(float(r["time_seconds"]) for r in rows)


def pixel_signals(session, t):
    cache = os.path.join(a.work, "results", f"{session}.pixel.npz")
    if os.path.exists(cache):
        z = np.load(cache)
        if len(z["dhash"]) == len(t):
            return z["dhash"], z["hsv"]
    fdir = os.path.join(a.work, "frames", session)
    meta = json.load(open(os.path.join(fdir, "frames.json")))
    dh, hsv = np.zeros(len(t)), np.zeros(len(t))
    prev_h = prev_hist = None
    for k, sec in enumerate(t):
        i = min(max(int(round(sec * meta["fps"])) + 1, 1), meta["count"])
        im = Image.open(os.path.join(fdir, f"{i:06d}.jpg")).convert("RGB")
        h = imagehash.dhash(im, 8)
        hist = cv2.calcHist([cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2HSV)], [0, 1, 2], None, [16, 4, 4],
                            [0, 180, 0, 256, 0, 256]).flatten()
        hist /= hist.sum()
        if prev_h is not None:
            dh[k] = h - prev_h
            hsv[k] = np.abs(hist - prev_hist).sum()
        prev_h, prev_hist = h, hist
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    np.savez(cache, dhash=dh, hsv=hsv)
    return dh, hsv


sessions = []
for p in sorted(glob.glob(os.path.join(a.work, "features", "*.vjepa2.npz"))):
    name = os.path.basename(p).replace(".vjepa2.npz", "")
    z = np.load(p)
    t, X = z["t"], z["global"].astype(np.float32)
    if len(t) < 120:            # units shorter than two minutes cannot be sampled for training and say little as a held-out fold
        continue
    dh, hsv = pixel_signals(name, t)
    sessions.append({"name": name, "t": t, "X": X, "dhash": dh, "hsv": hsv,
                     "labels": {"marks": read_times(name, "marks"),
                                "events_vis": read_times(name, "events", {"loading_done", "death", "levelup"}),
                                "events_zone": read_times(name, "events", {"loading_done"}),
                                "hud_outcome": read_times(name, "hud_events", {"death", "low_life", "boss_gone", "map_completed"}),
                                "alerts": read_times(name, "alerts")}})
total = sum(len(s["t"]) for s in sessions)
print(f"{len(sessions)} sessions, {total / 60:.1f} min: " + ", ".join(f"{s['name'][5:]} {len(s['t']) / 60:.0f}m" for s in sessions))
print("labels: " + ", ".join(f"{k} {sum(len(s['labels'][k]) for s in sessions)}" for k in ("marks", "events_vis", "events_zone", "hud_outcome", "alerts")))


class Predictor(nn.Module):
    def __init__(self, d=1024, h=256):
        super().__init__()
        self.inp = nn.Linear(d, h)
        self.gru = nn.GRU(h, h, batch_first=True)
        self.out = nn.Linear(h, d)

    def forward(self, x):
        hs, _ = self.gru(torch.tanh(self.inp(x)))
        return self.out(hs), hs


def z(x):
    x = np.nan_to_num(np.asarray(x, np.float64))
    return (x - x.mean()) / (x.std() + 1e-9)


K = a.horizon
for fold, held in enumerate(sessions):
    train = [s for s in sessions if s is not held]
    allX = np.concatenate([s["X"] for s in train])
    mu, sd = allX.mean(0), allX.std(0) + 1e-6
    Ztr = [torch.tensor((s["X"] - mu) / sd) for s in train]
    net = Predictor(h=a.hidden).to(dev)
    opt = torch.optim.Adam(net.parameters(), 1e-3, weight_decay=1e-4)
    L = 64
    for ep in range(a.epochs):
        xb, yb = [], []
        for _ in range(32):
            Z = Ztr[rng.randint(len(Ztr))]
            j = rng.randint(0, len(Z) - L - K)
            xb.append(Z[j : j + L])
            yb.append(Z[j + K : j + L + K])
        xb, yb = torch.stack(xb).to(dev), torch.stack(yb).to(dev)
        pred, _ = net(xb)
        loss = ((pred - yb) ** 2).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
    net.eval()
    Z = torch.tensor((held["X"] - mu) / sd)
    with torch.no_grad():
        pred, hs = net(Z[None].to(dev))
        pred, hs = pred[0].cpu(), hs[0].cpu()
    n = len(Z)
    pe = np.zeros(n)
    pe[K:] = ((pred[:-K] - Z[K:]) ** 2).mean(1).numpy()          # at t: error of the forecast made K s earlier
    st = np.r_[0, torch.norm(hs[1:] - hs[:-1], dim=1).numpy()]
    fc = np.r_[0, torch.norm(pred[1:] - pred[:-1], dim=1).numpy()]  # how much the K-ahead forecast moved in one step
    Xn = held["X"] / (np.linalg.norm(held["X"], axis=1, keepdims=True) + 1e-6)
    dr = np.r_[0, np.linalg.norm(Xn[1:] - Xn[:-1], axis=1)]
    held["sig"] = {"pixel_dhash": z(held["dhash"]), "pixel_hsv": z(held["hsv"]), "feat_drift": z(dr),
                   "pred_err": z(pe), "state_change": z(st), "forecast_change": z(fc)}
    print(f"  fold {fold + 1}/{len(sessions)} held out {held['name'][5:]}: final train mse {loss.item():.3f}, held-out mse {pe[K:].mean():.3f}")


def nms_topk(score, k, gap=3):
    order = np.argsort(-score)
    taken = np.zeros(len(score), bool)
    out = []
    for i in order:
        if len(out) >= k:
            break
        if not taken[max(0, i - gap) : i + gap + 1].any():
            taken[i] = True
            out.append(i)
    return out


names = ["pixel_dhash", "pixel_hsv", "feat_drift", "pred_err", "state_change", "forecast_change"]
report = [f"# Leave-one-session-out over {len(sessions)} sessions ({total / 60:.1f} min), predictor horizon {K} s, hidden {a.hidden}, {a.epochs} steps."]
for lab in ("marks", "events_vis", "events_zone", "hud_outcome", "alerts"):
    nlab = sum(len(s["labels"][lab]) for s in sessions)
    if nlab == 0:
        continue
    rows = []
    for name in names:
        r = {"signal": name}
        for W in (1, 2):
            ys = np.concatenate([[int(any(abs(x - m) <= W for m in s["labels"][lab])) for x in s["t"]] for s in sessions])
            ss = np.concatenate([s["sig"][name] for s in sessions])
            r[f"AP@{W}s"] = average_precision_score(ys, ss)
            r[f"AUC@{W}s"] = roc_auc_score(ys, ss)
            r[f"chance@{W}s"] = ys.mean()
        hit = tot = thit = ttot = 0
        for s in sessions:
            ms = s["labels"][lab]
            if not ms:
                continue
            tt = s["t"][nms_topk(s["sig"][name], len(ms))]
            hit += sum(any(abs(x - m) <= 2 for x in tt) for m in ms)
            tot += len(ms)
            thit += sum(any(abs(x - m) <= 2 for m in ms) for x in tt)
            ttot += len(tt)
        r["recall@budget"] = hit / tot
        r["prec@budget"] = thit / max(ttot, 1)
        rows.append(r)
    cols = ["signal", "AP@1s", "AP@2s", "AUC@1s", "AUC@2s", "recall@budget", "prec@budget"]
    out = [f"### {lab}: {nlab} labels; chance AP @1s {rows[0]['chance@1s']:.3f}, @2s {rows[0]['chance@2s']:.3f}", "",
           "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(r["signal"] if c == "signal" else f"{r[c]:.3f}" for c in cols) + " |")
    report.append("\n".join(out))
text = "\n\n".join(report) + "\n"
print(text)
os.makedirs(os.path.join(a.work, "results"), exist_ok=True)
open(os.path.join(a.work, "results", f"joint_loso_h{K}.md"), "w", encoding="utf-8").write(text)
