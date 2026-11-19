"""Alert-sound detector trained by injection: a small CNN that hears the loot filter's alert sounds inside combat audio.

Why: template correlation finds a clean alert but recovers only ~40% of alerts mixed into real session audio at the level
the game plays them. Training data here is unlimited: take real session audio, mix a calibration template into it at a
random time and level, and ask the network to say which alert (if any) is present.

  positives  1.0 s windows of session audio + one in-game template (alert_sounds/ingame/templates/<name>__n.wav),
             gain 0.2-1.6 of the recorded level, onset 0.05-0.35 s into the window
  negatives  the same kind of window with nothing added, or with a UI sound (alert_sounds/ingame/ui/*.wav),
             or with a template played backwards
  split      by session: the --holdout session's audio is never used for training

Commands
  python watch/alert_cnn.py train  [--holdout poe2_2026-10-04_214636] [--steps 4000]
      trains, reports held-out recall per gain level and false alarms per hour on untouched held-out audio, saves
      alert_sounds/ingame/alert_cnn.pt
  python watch/alert_cnn.py detect <session> [--thresh 0.9]
      slides over <work>/audio/<session>.game.flac every 0.1 s and writes <work>/raw/<session>.alerts.csv
"""
import argparse
import csv
import glob
import os

import librosa
import numpy as np
import torch
import torch.nn as nn

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["train", "detect"])
ap.add_argument("session", nargs="?")
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--sounds", default=r"C:/Users/Leo12/Documents/poe2-watch/alert_sounds/ingame")
ap.add_argument("--holdout", default="poe2_2026-10-04_214636")
ap.add_argument("--steps", type=int, default=4000)
ap.add_argument("--thresh", type=float, default=0.9)
ap.add_argument("--audio", default=None)
ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
SR, NFFT, HOP, NM, WIN = 22050, 1024, 256, 64, 22050          # 1.0 s windows, 87 frames
dev = "cuda" if torch.cuda.is_available() else "cpu"
torch.manual_seed(a.seed)
rng = np.random.RandomState(a.seed)
MODEL = os.path.join(a.sounds, "alert_cnn.pt")
melfb = torch.tensor(librosa.filters.mel(sr=SR, n_fft=NFFT, n_mels=NM, fmin=200, fmax=9000), dtype=torch.float32, device=dev)
window = torch.hann_window(NFFT, device=dev)


def logmel(x):
    """x: (B, samples) on dev -> (B, 1, NM, T) log-mel with per-clip mean removed"""
    S = torch.stft(x, NFFT, HOP, window=window, return_complex=True).abs() ** 2
    M = torch.log(torch.einsum("mf,bft->bmt", melfb, S) + 1e-6)
    return (M - M.mean((1, 2), keepdim=True)).unsqueeze(1)


class Net(nn.Module):
    def __init__(self, k):
        super().__init__()
        def block(i, o):
            return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(), nn.MaxPool2d(2))
        self.f = nn.Sequential(block(1, 24), block(24, 48), block(48, 96), block(96, 128))
        self.head = nn.Linear(128, k)

    def forward(self, m):
        return self.head(self.f(m).amax((2, 3)))


def load(p):
    return librosa.load(p, sr=SR, mono=True)[0].astype(np.float32)


def trim(t):
    on = int(np.argmax(np.abs(t) > 0.08 * np.abs(t).max()))
    return t[max(0, on - 200):][: int(1.3 * SR)]


if a.cmd == "train":
    tfiles = sorted(glob.glob(os.path.join(a.sounds, "templates", "*.wav")))
    names = sorted({os.path.basename(p).split("__")[0] for p in tfiles})
    tpl = [(names.index(os.path.basename(p).split("__")[0]), trim(load(p))) for p in tfiles]
    ui = [trim(load(p)) for p in sorted(glob.glob(os.path.join(a.sounds, "ui", "*.wav")))]
    audio = {os.path.basename(p)[: -len(".game.flac")]: load(p) for p in sorted(glob.glob(os.path.join(a.work, "audio", "*.game.flac")))}
    train_a = [v for k, v in audio.items() if k != a.holdout]
    held = audio[a.holdout]
    print(f"classes {names}; {len(tpl)} template instances, {len(ui)} UI sounds; train audio {sum(len(v) for v in train_a) / SR / 60:.0f} min, "
          f"held-out {a.holdout} {len(held) / SR / 60:.1f} min")

    def add(win, snd, gain, onset):
        seg = snd[: WIN - onset] * gain
        win[onset : onset + len(seg)] += seg

    def batch(src, n, gains=(0.2, 1.6), force=None):
        X = np.zeros((n, WIN), np.float32)
        Y = np.zeros((n, len(names)), np.float32)
        for i in range(n):
            au = src[rng.randint(len(src))]
            j = rng.randint(0, len(au) - WIN)
            w = au[j : j + WIN].copy() * rng.uniform(0.5, 1.5)
            r = rng.rand() if force is None else force
            if r < 0.45:                                           # one alert
                c, t = tpl[rng.randint(len(tpl))]
                add(w, t, rng.uniform(*gains), rng.randint(int(0.05 * SR), int(0.35 * SR)))
                Y[i, c] = 1
            elif r < 0.60 and ui:                                  # a UI sound, not an alert
                add(w, ui[rng.randint(len(ui))], rng.uniform(0.3, 1.5), rng.randint(0, int(0.4 * SR)))
            elif r < 0.72:                                         # a reversed alert, not an alert
                c, t = tpl[rng.randint(len(tpl))]
                add(w, t[::-1].copy(), rng.uniform(*gains), rng.randint(0, int(0.3 * SR)))
            X[i] = np.clip(w, -1, 1)
        return torch.tensor(X, device=dev), torch.tensor(Y, device=dev)

    net = Net(len(names)).to(dev)
    opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-3)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 4e-3, total_steps=a.steps)
    lossf = nn.BCEWithLogitsLoss()
    for step in range(a.steps):
        net.train()
        x, y = batch(train_a, 96)
        loss = lossf(net(logmel(x)), y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
        if step % 500 == 0 or step == a.steps - 1:
            print(f"  step {step} loss {loss.item():.4f}", flush=True)
    net.eval()
    torch.save({"state": net.state_dict(), "names": names}, MODEL)
    # held-out evaluation: recall per gain with an alert present, false alarms on untouched held-out audio
    with torch.no_grad():
        for g in (1.0, 0.5, 0.25):
            hit = tot = 0
            for _ in range(20):
                x, y = batch([held], 100, gains=(g, g), force=0.0)
                p = torch.sigmoid(net(logmel(x)))
                hit += ((p > a.thresh) & (y > 0.5)).any(1).sum().item()
                tot += len(y)
            print(f"  held-out recall at gain {g:.2f} (thr {a.thresh}): {hit / tot:.1%}")
        fa = n = 0
        for j in range(0, len(held) - WIN, WIN // 2):
            n += 1
        xs = torch.tensor(np.stack([held[j : j + WIN] for j in range(0, len(held) - WIN, WIN // 2)]), device=dev)
        ps = torch.cat([torch.sigmoid(net(logmel(xs[b : b + 256]))) for b in range(0, len(xs), 256)])
        fa = (ps > a.thresh).any(1).sum().item()
        print(f"  untouched held-out audio: {fa} of {len(xs)} half-second steps fire (>{a.thresh}) = {fa / (len(held) / SR / 3600):.1f} per hour "
              f"(upper bound on false alarms: real alerts in that audio also count)")
        hard = []
        for force, label in ((0.5, "UI sound"), (0.65, "reversed alert")):
            x, _ = batch([held], 1000, force=force)
            hard.append(f"{label} {(torch.sigmoid(net(logmel(x))) > a.thresh).any(1).float().mean().item():.1%}")
        print("  fires on hard negatives: " + ", ".join(hard))
    print("saved", MODEL)
else:
    ck = torch.load(MODEL, map_location=dev)
    names = ck["names"]
    net = Net(len(names)).to(dev)
    net.load_state_dict(ck["state"])
    net.eval()
    y = load(a.audio or os.path.join(a.work, "audio", f"{a.session}.game.flac"))
    step = SR // 10
    starts = np.arange(0, len(y) - WIN, step)
    P = []
    with torch.no_grad():
        for b in range(0, len(starts), 512):
            x = torch.tensor(np.stack([y[s : s + WIN] for s in starts[b : b + 512]]), device=dev)
            P.append(torch.sigmoid(net(logmel(x))).cpu().numpy())
    P = np.concatenate(P)
    rows = []
    for c, n in enumerate(names):
        idx = np.where(P[:, c] > a.thresh)[0]
        taken = []
        for i in idx[np.argsort(-P[idx, c])]:
            if all(abs(i - j) > 8 for j in taken):                 # 0.8 s apart
                taken.append(i)
        rows += [(starts[i] / SR + 0.2, n, float(P[i, c])) for i in taken]
    rows.sort()
    out = os.path.join(a.work, "raw", f"{a.session}.alerts.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["time_seconds", "sound", "score"])
        for t, n, sc in rows:
            w.writerow([f"{t:.2f}", n, f"{sc:.3f}"])
    cnt = {}
    for _, n, _ in rows:
        cnt[n] = cnt.get(n, 0) + 1
    print(f"{a.session}: {len(y) / SR / 60:.1f} min, {len(rows)} alerts (thr {a.thresh}): " + (", ".join(f"{k}:{v}" for k, v in sorted(cnt.items())) or "none"))
    print("  " + ", ".join(f"{int(t // 60)}:{t % 60:04.1f}({n},{sc:.2f})" for t, n, sc in rows)[:1500])
