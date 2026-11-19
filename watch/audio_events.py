"""Audio events on the game track (track 1), v2.

Two modes:

1. Unsupervised clustering (default). Onsets from a mel novelty curve, then a CLAP audio embedding of the 1 s
   window at each onset (laion/clap-htsat-unfused, 512-d, general-purpose sound semantics), agglomerative clustering
   with a cosine-distance threshold. Writes <work>/raw/<session>.audio_events.csv (time_seconds, cluster, strength)
   and <work>/audio_clusters/<session>/c<k>_<i>.wav + clusters.md for the owner to name.

2. Template matching (--templates <file>). The file lists known sounds, one per line: `<name> <session> <time_s>`.
   Each example becomes a log-mel template; every target session is scanned by normalised cross-correlation and
   matches above --match-thresh (fraction of the template's self-similarity) are written to
   <work>/raw/<session>.alerts.csv (time_seconds, name, score). This is the precise path for the loot-filter alert
   sounds once the owner points at two or three real occurrences.

Usage:
  python watch/audio_events.py <session> [--k-thresh 0.35] [--max-onsets 3000]
  python watch/audio_events.py <session> --templates templates.txt [--match-thresh 0.8]
"""
import argparse
import csv
import os
import subprocess
import tempfile

import librosa
import numpy as np
import soundfile as sf

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--video", default=None)
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--max-onsets", type=int, default=3000)
ap.add_argument("--k-thresh", type=float, default=0.35, help="cosine distance threshold for agglomerative clustering")
ap.add_argument("--examples", type=int, default=6)
ap.add_argument("--templates", default=None)
ap.add_argument("--match-thresh", type=float, default=0.8)
a = ap.parse_args()

SR = 48000  # CLAP's sample rate; mel work is done on a 22.05 kHz copy
HOP = 512
SR_MEL = 22050


def load_track(session):
    video = a.video if (a.video and session == a.session) else os.path.join(a.work, "raw", f"{session}.mp4")
    if not os.path.exists(video):
        raise SystemExit(f"recording not found: {video} (rclone copy it back from r2:vision-model/poe2-raw first)")
    tmp = os.path.join(tempfile.gettempdir(), f"{session}_track1.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), tmp], check=True)
    y48, _ = librosa.load(tmp, sr=SR, mono=True)
    os.remove(tmp)
    y22 = librosa.resample(y48, orig_sr=SR, target_sr=SR_MEL)
    S = librosa.feature.melspectrogram(y=y22, sr=SR_MEL, n_fft=2048, hop_length=HOP, n_mels=64, fmin=100, fmax=9000)
    return y48, librosa.power_to_db(S, ref=np.max)


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


# ------------------------------------------------------------------ mode 2: templates
if a.templates:
    tpl = []
    cache = {}
    for line in open(a.templates, encoding="utf-8"):
        parts = line.split()
        if len(parts) < 3 or line.startswith("#"):
            continue
        name, sess, t0 = parts[0], parts[1], float(parts[2])
        if sess not in cache:
            cache[sess] = load_track(sess)
        L = cache[sess][1]
        f0 = int(t0 * SR_MEL / HOP)
        W = int(0.6 * SR_MEL / HOP)
        patch = L[:, f0 : f0 + W]
        patch = (patch - patch.mean()) / (patch.std() + 1e-6)
        tpl.append((name, patch))
    y, L = cache[a.session] if a.session in cache else load_track(a.session)
    rows = []
    for name, patch in tpl:
        W = patch.shape[1]
        n = L.shape[1] - W
        # sliding normalised cross-correlation over time
        win = np.lib.stride_tricks.sliding_window_view(L, W, axis=1)[:, :n]  # (mels, n, W)
        win = np.transpose(win, (1, 0, 2))
        wz = (win - win.mean((1, 2), keepdims=True)) / (win.std((1, 2), keepdims=True) + 1e-6)
        score = (wz * patch[None]).mean((1, 2))  # 1.0 = identical shape
        peaks = librosa.util.peak_pick(np.maximum(score, 0), pre_max=10, post_max=10, pre_avg=20, post_avg=20, delta=0.05, wait=20)
        for p in peaks:
            if score[p] >= a.match_thresh:
                rows.append((f"{p * HOP / SR_MEL:.2f}", name, f"{score[p]:.3f}"))
    rows.sort(key=lambda r: float(r[0]))
    out = os.path.join(a.work, "raw", f"{a.session}.alerts.csv")
    write_csv(out, ["time_seconds", "name", "score"], rows)
    counts = {}
    for r in rows:
        counts[r[1]] = counts.get(r[1], 0) + 1
    print(f"{a.session}: {len(rows)} template matches -> {out}; " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    raise SystemExit

# ------------------------------------------------------------------ mode 1: CLAP clustering
import torch
from sklearn.cluster import AgglomerativeClustering
from transformers import ClapModel, ClapProcessor

y, L = load_track(a.session)
env = librosa.onset.onset_strength(S=L, sr=SR_MEL, hop_length=HOP)
peaks = librosa.util.peak_pick(env, pre_max=6, post_max=6, pre_avg=20, post_avg=20, delta=0.3, wait=8)
strength = env[peaks]
if len(peaks) > a.max_onsets:
    keep = np.argsort(-strength)[: a.max_onsets]
    peaks, strength = peaks[keep], strength[keep]
times = librosa.frames_to_time(peaks, sr=SR_MEL, hop_length=HOP)
order = np.argsort(times)
times, strength = times[order], strength[order]
print(f"{len(times)} onsets")

dev = "cuda" if torch.cuda.is_available() else "cpu"
proc = ClapProcessor.from_pretrained("laion/clap-htsat-unfused")
model = ClapModel.from_pretrained("laion/clap-htsat-unfused").to(dev).eval()
clips = []
for t0 in times:
    s0 = max(0, int((t0 - 0.1) * SR))
    seg = y[s0 : s0 + SR]
    if len(seg) < SR:
        seg = np.pad(seg, (0, SR - len(seg)))
    clips.append(seg)
embs = []
with torch.inference_mode():
    for b in range(0, len(clips), 64):
        inp = proc(audio=clips[b : b + 64], sampling_rate=SR, return_tensors="pt").to(dev)
        e = model.get_audio_features(**inp)
        if not torch.is_tensor(e):
            e = e.pooler_output if getattr(e, 'pooler_output', None) is not None else e[0]
        if b == 0:
            print('embedding shape', tuple(e.shape))
        embs.append(torch.nn.functional.normalize(e, dim=-1).cpu())
E = torch.cat(embs).numpy()
lab = AgglomerativeClustering(n_clusters=None, distance_threshold=a.k_thresh, metric="cosine", linkage="average").fit_predict(E)
k = lab.max() + 1
# order clusters by size
sizes = np.bincount(lab)
remap = {old: new for new, old in enumerate(np.argsort(-sizes))}
lab = np.array([remap[x] for x in lab])

write_csv(os.path.join(a.work, "raw", f"{a.session}.audio_events.csv"), ["time_seconds", "cluster", "strength"],
          [(f"{t:.2f}", int(c), f"{s:.2f}") for t, c, s in zip(times, lab, strength)])
cdir = os.path.join(a.work, "audio_clusters", a.session)
os.makedirs(cdir, exist_ok=True)
for f in os.listdir(cdir):
    if f.endswith(".wav"):
        os.remove(os.path.join(cdir, f))
lines = [f"# {a.session}: {len(times)} onsets, {k} clusters (CLAP embeddings, cosine threshold {a.k_thresh})", "",
         "| cluster | count | mean strength | example times (s) |", "|---|---|---|---|"]
for c in range(k):
    idx = np.where(lab == c)[0]
    # examples closest to the cluster centre, so they are typical rather than loud
    centre = E[idx].mean(0)
    idx = idx[np.argsort(-(E[idx] @ centre))]
    ex = idx[: a.examples]
    for i, j in enumerate(ex):
        s0 = max(0, int((times[j] - 0.15) * SR))
        sf.write(os.path.join(cdir, f"c{c:02d}_{i}.wav"), y[s0 : s0 + SR], SR)
    lines.append(f"| {c} | {len(idx)} | {strength[idx].mean():.2f} | " + ", ".join(f"{times[j]:.1f}" for j in ex) + " |")
lines += ["", "Name the clusters in labels.txt as `<k>: <name>`. Clusters with fewer than 3 members are listed but can be ignored."]
open(os.path.join(cdir, "clusters.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines[:4] + lines[4 : 4 + min(k, 25)]))
print("snippets in", cdir)
