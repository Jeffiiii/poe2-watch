"""Objective events for one recording, from the game's own Client.txt log (GGG permits reading it).

The recording's wall-clock start is taken from its file name (OBS writes local time: poe2_YYYY-MM-DD_HHMMSS),
its length from frames.json. Lines inside that window become events on the recording's time axis:

  zone_enter     Generating level <L> area "<area>"          subtype hideout / town / map / other
  loading_done   [LOADING SCREEN] (<name>) Duration = <s>    the moment play resumes (best visual anchor)
  death          : <name> has been slain.                    subtype self / other
  levelup        : <name> (<class>) is now level <N>
  items_identified : <N> Items identified
  npc_speech     <Speaker>: <text containing <i>{ or <it>}   bosses and NPCs talking
  whisper_in / whisper_out / chat   @From / @To / # $ & % channels (text is NOT kept, only the type)
  focus_lost / focus_gained         [WINDOW] Lost focus / Gained focus (alt-tab)

Writes <work>/raw/<session>.events.csv (time_seconds, wallclock, type, subtype, detail) and
<work>/raw/<session>.clientlog.txt (the filtered log slice, chat text removed).

Usage: python watch/events_from_log.py <session> [--log <Client.txt>] [--work ...] [--offset 0.0]
"""
import argparse
import csv
import datetime as dt
import json
import os
import re

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--log", default=r"C:/Program Files (x86)/Steam/steamapps/common/Path of Exile 2/logs/Client.txt")
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--offset", type=float, default=0.0, help="seconds to add to log times (log - recording clock skew)")
a = ap.parse_args()

m = re.match(r"poe2_(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})", a.session)
if not m:
    raise SystemExit("session name must look like poe2_YYYY-MM-DD_HHMMSS")
start = dt.datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}", "%Y-%m-%d %H:%M:%S")
fj = os.path.join(a.work, "frames", a.session, "frames.json")
dur = json.load(open(fj))["duration"] if os.path.exists(fj) else None
if dur is None:
    meta = json.load(open(os.path.join(a.work, "raw", f"{a.session}.json"), encoding="utf-8"))
    dur = float(meta.get("duration_seconds", 0)) or 4 * 3600
end = start + dt.timedelta(seconds=dur)

character = None
mj = os.path.join(a.work, "raw", f"{a.session}.json")
if os.path.exists(mj):
    character = json.load(open(mj, encoding="utf-8")).get("character", {}).get("name")

LINE = re.compile(r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \d+ [0-9a-f]+ \[(\w+) Client \d+\] (.*)$")
NOISE = re.compile(r"Tile hash|Doodad hash|\[SHADER\]|\[RENDER\]|\[STORE\]|\[ENTITY\]|\[D3D|Got Instance|Just before|\[JOB\]|"
                   r"\[RESOURCE\]|\[TEXTURE\]|\[SOUND\]|\[ENGINE\]|\[VIDEO\]|\[BUNDLE\]|\[PATCH\]|Send patching|\[SCENE\]|"
                   r"\[PRELOAD\]|Async connecting|Connected to|Precache|Actor is dead when trying|Joined guild|"
                   r"InstanceClientSet|Client-Safe Instance|Connect time to instance|Atlas input suspension|Failed to apply item")


def subtype_of_area(area):
    al = area.lower()
    if "hideout" in al:
        return "hideout"
    if "town" in al or al.endswith("_town"):
        return "town"
    if al.startswith("map"):
        return "map"
    return "other"


events, keep = [], []
with open(a.log, encoding="utf-8", errors="replace") as fh:
    for line in fh:
        mm = LINE.match(line.rstrip("\n"))
        if not mm:
            continue
        ts = dt.datetime.strptime(mm.group(1), "%Y/%m/%d %H:%M:%S")
        if ts < start - dt.timedelta(seconds=5):
            continue
        if ts > end + dt.timedelta(seconds=5):
            break
        body = mm.group(3)
        if NOISE.search(body):
            continue
        rel = (ts - start).total_seconds() + a.offset
        ev = None
        if (x := re.search(r'Generating level (\d+) area "([^"]+)"', body)):
            ev = ("zone_enter", subtype_of_area(x.group(2)), f"{x.group(2)} L{x.group(1)}")
        elif (x := re.search(r"\[LOADING SCREEN\] \((.+?)\) Duration = ([\d.]+)", body)):
            ev = ("loading_done", "", f"{x.group(1)} {float(x.group(2)):.1f}s")
        elif (x := re.search(r": (\S+) has been slain\.", body)):
            ev = ("death", "self" if x.group(1) == character else "other", x.group(1))
        elif (x := re.search(r": (\S+) \((.+?)\) is now level (\d+)", body)):
            ev = ("levelup", "self" if x.group(1) == character else "other", f"{x.group(1)} L{x.group(3)}")
        elif (x := re.search(r": (\d+) Items? identified", body)):
            ev = ("items_identified", "", x.group(1))
        elif body.startswith("@From"):
            ev = ("whisper_in", "", "")
            body = "@From <redacted>"
        elif body.startswith("@To"):
            ev = ("whisper_out", "", "")
            body = "@To <redacted>"
        elif body[:1] in "#$&%":
            ev = ("chat", body[0], "")
            body = body[0] + " <redacted>"
        elif "[WINDOW] Lost focus" in body:
            ev = ("focus_lost", "", "")
        elif "[WINDOW] Gained focus" in body:
            ev = ("focus_gained", "", "")
        elif (x := re.match(r"([^:\[\]<>]{2,40}): (.*)", body)) and ("<i>" in body or "<it>" in body or "{" in body):
            ev = ("npc_speech", "", x.group(1).strip())
        keep.append(f"{mm.group(1)} {rel:8.1f}s [{mm.group(2)}] {body}")
        if ev:
            events.append({"time_seconds": round(rel, 1), "wallclock": mm.group(1), "type": ev[0], "subtype": ev[1], "detail": ev[2]})

out_csv = os.path.join(a.work, "raw", f"{a.session}.events.csv")
with open(out_csv, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["time_seconds", "wallclock", "type", "subtype", "detail"])
    w.writeheader()
    w.writerows(events)
open(os.path.join(a.work, "raw", f"{a.session}.clientlog.txt"), "w", encoding="utf-8").write("\n".join(keep) + "\n")
counts = {}
for e in events:
    counts[e["type"]] = counts.get(e["type"], 0) + 1
print(f"{a.session}: window {start:%H:%M:%S}-{end:%H:%M:%S} ({dur:.0f} s), {len(events)} events -> {out_csv}")
print("  " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
