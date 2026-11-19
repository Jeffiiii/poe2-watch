"""Find loot-filter alert sounds in a session's game audio, using templates cut from the owner's own calibration recording.

Templates: alert_sounds/ingame/templates/<name>__<n>.wav, each the sound the game actually played when a known item was
dropped (calibration of 2026-10-05). Several instances may share a name; a name's score is the max over its instances.
Control: every template played BACKWARDS. A reversed template has the same spectrum and level but the wrong temporal
pattern, so any match on it is a false positive; the threshold is the lowest one at which the reversed set fires at most
once per 30 minutes (and never below --min-thresh).

Features: log-mel (22.05 kHz, 128 bands, 23 ms hop) of the first --tpl-seconds after the onset, with each frame's mean and
each band's mean removed, so only the time-frequency pattern counts (plain correlation scored 0.9 on everything).

Writes <work>/raw/<session>.alerts.csv (time_seconds, sound, score) and prints counts, including the reversed control.

Usage: python watch/alert_match.py <session> [--thresh auto|0.6] [--tpl-seconds 0.8]
"""
import argparse
import csv
import glob
import os

import librosa
import numpy as np
from scipy.signal import correlate

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--templates", default=r"C:/Users/Leo12/Documents/poe2-watch/alert_sounds/ingame/templates")
ap.add_argument("--audio", default=None, help="audio file to scan instead of <work>/audio/<session>.game.flac")
ap.add_argument("--thresh", default="auto")
ap.add_argument("--min-thresh", type=float, default=0.45)
ap.add_argument("--tpl-seconds", type=float, default=0.8)
a = ap.parse_args()
SR, HOP, NM = 22050, 512, 128


def logmel(y):
    S = librosa.feature.melspectrogram(y=y, sr=SR, n_fft=2048, hop_length=HOP, n_mels=NM, fmin=200, fmax=9000)
    return np.maximum(librosa.power_to_db(S, ref=1.0, top_db=None), -80.0).astype(np.float64)


y, _ = librosa.load(a.audio or os.path.join(a.work, "audio", f"{a.session}.game.flac"), sr=SR, mono=True)
L = logmel(y)
L = L - L.mean(0, keepdims=True)                 # remove each frame's broadband level
N = L.shape[1]
W = int(round(a.tpl_seconds * SR / HOP))
cs = np.concatenate([np.zeros((NM, 1)), np.cumsum(L, 1)], 1)
cq = np.concatenate([np.zeros((NM, 1)), np.cumsum(L ** 2, 1)], 1)
n_out = N - W + 1
band_sum = cs[:, W:] - cs[:, :-W]
band_sq = cq[:, W:] - cq[:, :-W]
win_energy = np.maximum((band_sq - band_sum ** 2 / W).sum(0), 1e-6)
flat = win_energy < np.percentile(win_energy, 5)


def score_template(ty):
    T = logmel(ty)[:, :W]
    if T.shape[1] < W:
        T = np.pad(T, ((0, 0), (0, W - T.shape[1])), constant_values=-80.0)
    T = T - T.mean(0, keepdims=True)
    Tz = T - T.mean(1, keepdims=True)
    num = np.zeros(n_out)
    for b in range(NM):
        num += correlate(L[b], Tz[b], mode="valid", method="fft")
    sc = num / (np.sqrt(win_energy) * np.sqrt((Tz ** 2).sum()))
    sc[flat] = 0.0
    return sc


scores, ctrl = {}, {}
for p in sorted(glob.glob(os.path.join(a.templates, "*.wav"))):
    name = os.path.basename(p).split("__")[0]
    ty, _ = librosa.load(p, sr=SR, mono=True)
    on = int(np.argmax(np.abs(ty) > 0.08 * np.abs(ty).max()))
    seg = ty[on : on + int((a.tpl_seconds + 0.1) * SR)]
    s = score_template(seg)
    scores[name] = np.maximum(scores[name], s) if name in scores else s
    r = score_template(seg[::-1].copy())
    ctrl[name] = np.maximum(ctrl[name], r) if name in ctrl else r
if not scores:
    raise SystemExit(f"no templates in {a.templates}")


def peaks(sc, thr, gap=int(0.6 * SR / HOP)):
    idx = np.where(sc >= thr)[0]
    out = []
    for i in idx[np.argsort(-sc[idx])]:
        if all(abs(i - j) > gap for j in out):
            out.append(i)
    return sorted(out)


minutes = N * HOP / SR / 60
if a.thresh == "auto":
    limit = max(1.0, minutes / 30)
    thr = 0.95
    for cand in np.arange(0.95, a.min_thresh - 1e-9, -0.01):
        if sum(len(peaks(ctrl[n], cand)) for n in ctrl) > limit:
            break
        thr = cand
else:
    thr = float(a.thresh)

rows = sorted((i * HOP / SR, n, float(scores[n][i])) for n in scores for i in peaks(scores[n], thr))
keep = []
for r in rows:                                   # one sound per moment
    if keep and r[0] - keep[-1][0] < 0.6:
        if r[2] > keep[-1][2]:
            keep[-1] = r
    else:
        keep.append(r)
out = os.path.join(a.work, "raw", f"{a.session}.alerts.csv")
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["time_seconds", "sound", "score"])
    for t, n, sc in keep:
        w.writerow([f"{t:.2f}", n, f"{sc:.3f}"])
cnt = {n: sum(1 for r in keep if r[1] == n) for n in sorted(scores)}
print(f"{a.session}: {minutes:.1f} min, threshold {thr:.2f}; matches " + ", ".join(f"{n}:{c}" for n, c in cnt.items()) +
      f"; reversed-control matches at this threshold {sum(len(peaks(ctrl[n], thr)) for n in ctrl)}")
print("  max score  real: " + ", ".join(f"{n}:{scores[n].max():.2f}" for n in sorted(scores)))
print("  max score  reversed: " + ", ".join(f"{n}:{ctrl[n].max():.2f}" for n in sorted(ctrl)))
print("  hits: " + ", ".join(f"{int(t // 60)}:{t % 60:04.1f}({n},{sc:.2f})" for t, n, sc in keep)[:1800])
print("->", out)
