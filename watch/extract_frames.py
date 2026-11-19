"""Extract frames from a recording once: 4 fps, short side 384 px, JPEG.

Usage: python watch/extract_frames.py <recording.mp4> [--out-root C:/Users/Leo12/Videos/poe2-work/frames] [--fps 4] [--short 384]
Writes <out-root>/<session>/000001.jpg ... and frames.json {fps, short, count, duration}.
Frame i (1-based) is at t = (i-1)/fps seconds.
"""
import argparse
import json
import os
import subprocess
import time

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("--out-root", default=r"C:/Users/Leo12/Videos/poe2-work/frames")
ap.add_argument("--fps", type=float, default=4)
ap.add_argument("--short", type=int, default=384)
a = ap.parse_args()

session = os.path.splitext(os.path.basename(a.video))[0]
out = os.path.join(a.out_root, session)
os.makedirs(out, exist_ok=True)
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.video],
                           capture_output=True, text=True).stdout.strip())
t0 = time.time()
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf", f"fps={a.fps},scale=-2:{a.short}", "-q:v", "3",
                os.path.join(out, "%06d.jpg")], check=True)
n = len([f for f in os.listdir(out) if f.endswith(".jpg")])
json.dump({"session": session, "fps": a.fps, "short": a.short, "count": n, "duration": dur, "source": os.path.abspath(a.video)},
          open(os.path.join(out, "frames.json"), "w"), indent=2)
print(f"{session}: {n} frames at {a.fps} fps ({dur:.0f} s video) in {time.time() - t0:.0f} s -> {out}")
