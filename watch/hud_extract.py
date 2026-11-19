"""Cut the PoE2 HUD regions out of a full-resolution recording, once, as one small montage per second.

Regions are for the owner's layout: 1920x1200 output, default PoE2 HUD with life/mana values shown.
  L  life / shield / ward text above the life orb       crop 320x140 at (0, 825)
  R  mana / spirit text above the mana orb               crop 320x100 at (1600, 865)
  T  boss name + bar at the top centre                   crop 640x110 at (640, 10)
  O  map objectives / quest tracker on the right         crop 460x480 at (1460, 230)
Montage layout (1420x480): L at (0,0), R at (0,140), T at (320,0), O at (960,0).
After this pass the raw video is no longer needed for HUD reading.

Usage: python watch/hud_extract.py <recording.mp4> [--fps 1] [--out-root C:/Users/Leo12/Videos/poe2-work/hud]
"""
import argparse
import json
import os
import subprocess
import time

REGIONS = {  # name: (w, h, x, y) in the 1920x1200 frame, and position in the montage
    "L": ((320, 140, 0, 825), (0, 0)),
    "R": ((320, 100, 1600, 865), (0, 140)),
    "T": ((640, 110, 640, 10), (320, 0)),
    "O": ((460, 480, 1460, 230), (960, 0)),
}

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("--fps", type=float, default=1)
ap.add_argument("--out-root", default=r"C:/Users/Leo12/Videos/poe2-work/hud")
a = ap.parse_args()
session = os.path.splitext(os.path.basename(a.video))[0]
out = os.path.join(a.out_root, session)
os.makedirs(out, exist_ok=True)
names = list(REGIONS)
fg = f"[0:v]fps={a.fps},split={len(names)}" + "".join(f"[s{n}]" for n in names) + ";"
for n in names:
    (w, h, x, y), _ = REGIONS[n]
    fg += f"[s{n}]crop={w}:{h}:{x}:{y}[c{n}];"
layout = "|".join(f"{px}_{py}" for _, (px, py) in REGIONS.values())
fg += "".join(f"[c{n}]" for n in names) + f"xstack=inputs={len(names)}:layout={layout}:fill=black[v]"
t0 = time.time()
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-filter_complex", fg, "-map", "[v]", "-q:v", "2",
                os.path.join(out, "%06d.jpg")], check=True)
n = len([f for f in os.listdir(out) if f.endswith(".jpg")])
json.dump({"session": session, "fps": a.fps, "count": n, "regions": {k: {"crop": v[0], "at": v[1]} for k, v in REGIONS.items()}},
          open(os.path.join(out, "hud.json"), "w"), indent=2)
print(f"{session}: {n} HUD montages at {a.fps} fps in {time.time() - t0:.0f} s -> {out}")
