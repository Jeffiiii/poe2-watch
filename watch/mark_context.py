"""What is on screen / in the log around the moments the player marked "I would say something here"?

For every session with marks: collect all cue events (Client.txt events, HUD events, alert-sound matches) and
  1. print, per mark, the cues within --near seconds before and after it (a readable timeline), and
  2. per cue type, compare the share of marks that have that cue within the window against the share expected by chance
     (the fraction of the session covered by windows around that cue type), with the lift = observed / expected.

A cue type with a lift well above 1 and several supporting marks is a candidate reason for speaking.

Usage: python watch/mark_context.py [--work C:/Users/Leo12/Videos/poe2-work] [--before 8] [--after 3]
"""
import argparse
import csv
import glob
import json
import os

ap = argparse.ArgumentParser()
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--before", type=float, default=8, help="a cue up to this many seconds BEFORE the mark counts")
ap.add_argument("--after", type=float, default=3, help="a cue up to this many seconds AFTER the mark counts")
a = ap.parse_args()
raw = os.path.join(a.work, "raw")


def load(session, suffix, type_col="type", detail_col="detail", prefix=""):
    p = os.path.join(raw, f"{session}.{suffix}.csv")
    if not os.path.exists(p):
        return []
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8")):
        ty = prefix + (r.get(type_col) or suffix)
        out.append((float(r["time_seconds"]), ty, (r.get(detail_col) or "")[:50]))
    return out


sessions = sorted(os.path.basename(p)[: -len(".marks.csv")] for p in glob.glob(os.path.join(raw, "*.marks.csv")))
tot_marks, stats, lines = 0, {}, []
for s in sessions:
    marks = [float(r["time_seconds"]) for r in csv.DictReader(open(os.path.join(raw, f"{s}.marks.csv"), encoding="utf-8"))]
    fj = os.path.join(a.work, "frames", s, "frames.json")
    if not marks or not os.path.exists(fj):
        continue
    dur = json.load(open(fj))["duration"]
    cues = load(s, "events", prefix="log:") + load(s, "hud_events", prefix="hud:")
    for t, ty, d in load(s, "alerts", type_col="sound", detail_col="score", prefix="alert:#"):
        cues.append((t, ty, d))
    cues = [c for c in cues if not c[1].startswith(("log:focus", "log:zone_enter"))]
    cues.sort()
    tot_marks += len(marks)
    lines.append(f"## {s}: {len(marks)} marks, {len(cues)} cues, {dur / 60:.0f} min")
    for m in marks:
        near = [(t - m, ty, d) for t, ty, d in cues if -a.before <= t - m <= a.after]
        txt = "; ".join(f"{ty}{' ' + d if d else ''} ({dt:+.0f}s)" for dt, ty, d in near) or "nothing in the log or on the HUD"
        lines.append(f"- {int(m // 60):02d}:{m % 60:04.1f}  {txt}")
    for ty in sorted({c[1] for c in cues}):
        ts = [c[0] for c in cues if c[1] == ty]
        hit = sum(any(-a.before <= t - m <= a.after for t in ts) for m in marks)
        # chance: fraction of the session inside a window after/before any cue of this type (union of intervals)
        iv = sorted((max(0, t - a.after), min(dur, t + a.before)) for t in ts)
        cov, end = 0.0, 0.0
        for x0, x1 in iv:
            x0 = max(x0, end)
            if x1 > x0:
                cov += x1 - x0
                end = x1
        st = stats.setdefault(ty, {"hit": 0, "marks": 0, "exp": 0.0, "n": 0})
        st["hit"] += hit
        st["marks"] += len(marks)
        st["exp"] += cov / dur * len(marks)
        st["n"] += len(ts)
    lines.append("")
tab = ["| cue | occurrences | marks with it nearby | expected by chance | lift |", "|---|---|---|---|---|"]
for ty, st in sorted(stats.items(), key=lambda kv: -(kv[1]["hit"] / max(kv[1]["exp"], 1e-9))):
    tab.append(f"| {ty} | {st['n']} | {st['hit']}/{st['marks']} | {st['exp']:.1f} | {st['hit'] / max(st['exp'], 1e-9):.1f} |")
text = (f"# Cues around the player's marks ({tot_marks} marks; window {a.before:.0f} s before to {a.after:.0f} s after the mark)\n\n"
        + "\n".join(tab) + "\n\n" + "\n".join(lines))
print(text)
os.makedirs(os.path.join(a.work, "results"), exist_ok=True)
open(os.path.join(a.work, "results", "mark_context.md"), "w", encoding="utf-8").write(text)
