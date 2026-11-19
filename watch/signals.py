"""Per-second signals scored against two kinds of labels: the player's marks and the game's objective events.

Signals
  pixel_dhash / pixel_hsv : dHash Hamming distance / HSV histogram L1 between the frame at t and at t-1 s
  feat_drift              : ||x_t - x_{t-1}|| on frozen V-JEPA 2 global features (CLIP-drift style)
  pred_err                : ||xhat_t - x_t||^2 from a small GRU predictor trained on the first --train-frac of the session
  state_change            : ||h_t - h_{t-1}||, change of the predictor's hidden state after seeing x_t (belief change)
  forecast_change         : ||xhat_{t+1|t} - xhat_{t+1|t-1}||, how much the forecast of the next second moved
  err_vs_mean             : error of the trivial predictor "next = training mean" (sanity reference)

Label sets (each evaluated separately)
  marks        the player's live marks (<session>.marks.csv)
  events_vis   visual game events from Client.txt (<session>.events.csv): loading_done, death, levelup
  events_zone  loading_done only (zone transitions)

Metrics: average precision and AUROC on the held-out tail and the whole session, plus recall / precision when the
signal gets exactly as many triggers as there are labels (3 s non-max suppression). Positives are +-W s around a label.

Usage: python watch/signals.py <session> [--work C:/Users/Leo12/Videos/poe2-work] [--train-frac 0.7]
"""
import argparse
import csv
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
ap.add_argument("session")
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--train-frac", type=float, default=0.7)
ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
torch.manual_seed(a.seed)
np.random.seed(a.seed)

fdir = os.path.join(a.work, "frames", a.session)
fmeta = json.load(open(os.path.join(fdir, "frames.json")))
fps = fmeta["fps"]
z = np.load(os.path.join(a.work, "features", f"{a.session}.vjepa2.npz"))
t = z["t"]
X = z["global"].astype(np.float32)
T = len(t)


def read_times(name, keep=None):
    p = os.path.join(a.work, "raw", f"{a.session}.{name}.csv")
    if not os.path.exists(p):
        return None
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    if keep:
        rows = [r for r in rows if r.get("type") in keep]
    return sorted(float(r["time_seconds"]) for r in rows)


label_sets = {"marks": read_times("marks"),
              "events_vis": read_times("events", {"loading_done", "death", "levelup"}),
              "events_zone": read_times("events", {"loading_done"})}
label_sets = {k: v for k, v in label_sets.items() if v}
print(f"{a.session}: {T} s of features; labels: " + ", ".join(f"{k} {len(v)}" for k, v in label_sets.items()))


# ---------------------------------------------------------------- pixel signals on the same time grid
def frame_at(sec):
    i = int(round(sec * fps)) + 1
    return os.path.join(fdir, f"{min(max(i, 1), fmeta['count']):06d}.jpg")


dh, hsv = np.zeros(T), np.zeros(T)
prev_h = prev_hist = None
for k, sec in enumerate(t):
    im = Image.open(frame_at(sec)).convert("RGB")
    h = imagehash.dhash(im, 8)
    hist = cv2.calcHist([cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2HSV)], [0, 1, 2], None, [16, 4, 4],
                        [0, 180, 0, 256, 0, 256]).flatten()
    hist /= hist.sum()
    if prev_h is not None:
        dh[k] = h - prev_h
        hsv[k] = np.abs(hist - prev_hist).sum()
    prev_h, prev_hist = h, hist

# ---------------------------------------------------------------- feature drift
Xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-6)
drift = np.r_[0, np.linalg.norm(Xn[1:] - Xn[:-1], axis=1)]

# ---------------------------------------------------------------- tiny GRU predictor: x_{t+1} from x_{<=t}
ntr = int(T * a.train_frac)
mu, sd = X[:ntr].mean(0), X[:ntr].std(0) + 1e-6
Z = torch.tensor((X - mu) / sd)


class Predictor(nn.Module):
    def __init__(self, d=1024, h=256):
        super().__init__()
        self.inp = nn.Linear(d, h)
        self.gru = nn.GRU(h, h, batch_first=True)
        self.out = nn.Linear(h, d)

    def forward(self, x, h0=None):
        hs, _ = self.gru(torch.tanh(self.inp(x)), h0)
        return self.out(hs), hs


net = Predictor()
opt = torch.optim.Adam(net.parameters(), 1e-3, weight_decay=1e-4)
L = 32
for ep in range(300):
    i = np.random.randint(0, ntr - L - 1, 16)
    xb = torch.stack([Z[j : j + L] for j in i])
    yb = torch.stack([Z[j + 1 : j + L + 1] for j in i])
    pred, _ = net(xb)
    loss = ((pred - yb) ** 2).mean()
    opt.zero_grad()
    loss.backward()
    opt.step()
    if ep % 100 == 0:
        print(f"  predictor epoch {ep} train mse {loss.item():.3f}")
net.eval()
with torch.no_grad():
    pred, hs = net(Z[None])
    pred, hs = pred[0], hs[0]  # pred[k] = xhat_{k+1} given x_{<=k}; hs[k] = h_k
pred_err = np.r_[0, ((pred[:-1] - Z[1:]) ** 2).mean(1).numpy()]
state = np.r_[0, torch.norm(hs[1:] - hs[:-1], dim=1).numpy()]
forecast = np.r_[0, 0, torch.norm(pred[1:-1] - pred[:-2], dim=1).numpy()]
mean_ref = np.r_[0, ((Z[1:] - Z[:ntr].mean(0)) ** 2).mean(1).numpy()]
signals = {"pixel_dhash": dh, "pixel_hsv": hsv, "feat_drift": drift, "pred_err": pred_err,
           "state_change": state, "forecast_change": forecast, "err_vs_mean": mean_ref}
test = np.arange(T) >= ntr
allm = np.ones(T, bool)


# ---------------------------------------------------------------- evaluation
def nms(score, min_gap=3):
    order = np.argsort(-score)
    taken = np.zeros(T, bool)
    out = []
    for i in order:
        if not taken[max(0, i - min_gap) : i + min_gap + 1].any():
            taken[i] = True
            out.append(i)
    return np.array(out)


def evaluate(marks, title):
    def labels(W):
        return np.array([any(abs(s - m) <= W for m in marks) for s in t], int)

    def budget(score, mask, W=2):
        idx = np.where(mask)[0]
        ms = [m for m in marks if t[idx[0]] <= m <= t[idx[-1]]]
        if not ms:
            return float("nan"), float("nan"), 0
        sc = np.full(T, -np.inf)
        sc[idx] = score[idx]
        tt = t[nms(sc)[: len(ms)]]
        rec = np.mean([any(abs(x - m) <= W for x in tt) for m in ms])
        prec = np.mean([any(abs(x - m) <= W for m in ms) for x in tt])
        return rec, prec, len(ms)

    rows = []
    for name, s in signals.items():
        s = np.nan_to_num(s)
        r = {"signal": name}
        for W in (1, 2):
            y = labels(W)
            for part, mask in (("test", test), ("all", allm)):
                yy, ss = y[mask], s[mask]
                r[f"AP@{W}s/{part}"] = average_precision_score(yy, ss) if yy.sum() else float("nan")
                r[f"AUC@{W}s/{part}"] = roc_auc_score(yy, ss) if 0 < yy.sum() < len(yy) else float("nan")
        r["recall@budget/test"], r["prec@budget/test"], r["n/test"] = budget(s, test)
        r["recall@budget/all"], r["prec@budget/all"], r["n/all"] = budget(s, allm)
        rows.append(r)
    cols = ["signal", "AP@1s/test", "AP@2s/test", "AUC@2s/test", "recall@budget/test", "prec@budget/test",
            "AP@2s/all", "AUC@2s/all", "recall@budget/all", "prec@budget/all"]
    out = [f"### {title}: {len(marks)} labels ({rows[0]['n/test']} in the held-out last {100 - int(a.train_frac * 100)}%). "
           f"Chance AP @2s: all {labels(2).mean():.3f}, test {labels(2)[test].mean():.3f}.",
           "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(r["signal"] if c == "signal" else f"{r[c]:.3f}" for c in cols) + " |")
    return "\n".join(out)


report = [f"# {a.session}: {T} s. pred_err / state_change / forecast_change are in-sample on 'all' "
          f"(predictor trained on the first {int(a.train_frac * 100)}%)."]
for name, marks in label_sets.items():
    report.append(evaluate(marks, name))
text = "\n\n".join(report) + "\n"
print(text)
os.makedirs(os.path.join(a.work, "results"), exist_ok=True)
open(os.path.join(a.work, "results", f"{a.session}.signals.md"), "w", encoding="utf-8").write(text)
np.savez(os.path.join(a.work, "results", f"{a.session}.signals.npz"), t=t,
         **{f"labels_{k}": np.array(v) for k, v in label_sets.items()}, **signals)
