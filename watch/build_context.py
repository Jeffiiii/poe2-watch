"""Assemble the "privileged context" for teacher labelling: what the game itself says is happening, window by window.

For each --win second window of a session this gathers everything we can read without understanding the picture:
  zone            the area the player is in (Client.txt), and how long they have been there
  hud             life / shield / ward / mana / spirit at the start and end of the window, min life fraction inside it
  target          boss or elite name bar and its visible hp, if any
  objectives      the quest / map objective text
  events          Client.txt events, HUD events and alert sounds inside the window (and the 10 s before it, marked as earlier)
  mark            whether the player pressed the "I would say something here" key in the window
and lists the frames (4 fps, 384 px) that belong to the window. One JSON object per line:
  <work>/context/<session>.jsonl   {session, t0, t1, frames:[...], context:{...}, context_text:"..."}
context_text is the compact human-readable form that is given to the teacher model next to the frames.
The student never sees it.

Usage: python watch/build_context.py <session> [--win 5] [--frames-per-win 4]
"""
import argparse
import csv
import json
import os
import re
import collections

import hud_clean

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--win", type=float, default=5)
ap.add_argument("--frames-per-win", type=int, default=4)
a = ap.parse_args()
raw = os.path.join(a.work, "raw")
fmeta = json.load(open(os.path.join(a.work, "frames", a.session, "frames.json")))
fps, nfr, dur = fmeta["fps"], fmeta["count"], fmeta["duration"]


def rows(suffix):
    p = os.path.join(raw, f"{a.session}.{suffix}.csv")
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


log = [(float(r["time_seconds"]), r["type"], r.get("subtype", ""), r.get("detail", "")) for r in rows("events")]
hudev = [(float(r["time_seconds"]), r["type"], r.get("detail", "")) for r in rows("hud_events")]
alerts = [(float(r["time_seconds"]), r["sound"]) for r in rows("alerts")]
marks = [float(r["time_seconds"]) for r in rows("marks")]
hud_p = os.path.join(raw, f"{a.session}.hud.csv")
hud = {int(r["t"]): r for r in hud_clean.load(hud_p)} if os.path.exists(hud_p) else {}
meta_p = os.path.join(raw, f"{a.session}.json")
meta = json.load(open(meta_p, encoding="utf-8")) if os.path.exists(meta_p) else {}
ch = meta.get("character", {})
who = f"{ch.get('name', '?')} ({ch.get('class') or ch.get('ascendancy') or '?'})"


def num(r, k):
    return (r[k], r[k + "_max"]) if r.get(k) is not None else None


# The name on a bar is read once a second and misread now and then: take the spelling most seconds agree on over the
# whole run of the bar (gaps up to 2 s). A name seen only once is kept but marked unconfirmed.
bar_name = {}
run = []
for s_ in sorted(hud) + [10 ** 9]:
    if s_ < 10 ** 9 and hud[s_]["bar"] and (not run or s_ - run[-1] <= 3):
        run.append(s_)
        continue
    if run:
        names = [hud[q]["bar_name"] for q in run if hud[q]["bar_name"]]
        cnt = collections.Counter(re.sub(r"[^a-z]", "", x.lower()) for x in names)
        if cnt:
            best, nbest = cnt.most_common(1)[0]
            spell = collections.Counter(x for x in names if re.sub(r"[^a-z]", "", x.lower()) == best).most_common(1)[0][0]
            for q in run:
                bar_name[q] = (spell, nbest >= 2)
    run = [s_] if s_ < 10 ** 9 and hud[s_]["bar"] else []


def hud_at(sec):
    for d in range(0, 4):                      # nearest readable second
        for s in (int(sec) - d, int(sec) + d):
            if s in hud and num(hud[s], "life"):
                return hud[s]
    return hud.get(int(sec), {})


zones = [(t, d) for t, ty, _, d in log if ty == "zone_enter"]
done = [t for t, ty, _, _ in log if ty == "loading_done"]
loads = [(t, next((x for x in done if t <= x <= t + 60), t + 3)) for t, _ in zones]      # loading screens
os.makedirs(os.path.join(a.work, "context"), exist_ok=True)
out = os.path.join(a.work, "context", f"{a.session}.jsonl")
n = 0
with open(out, "w", encoding="utf-8") as fh:
    t0 = 0.0
    while t0 + a.win <= dur:
        t1 = t0 + a.win
        # the zone is the one at the START of the window; an arrival inside the window is listed separately
        zone = next((z for z in reversed(zones) if z[0] <= t0), None)
        changes = [z for z in zones if t0 < z[0] < t1]
        loading = any(lo < t1 and hi > t0 for lo, hi in loads)
        h0, h1 = hud_at(t0), hud_at(t1 - 1)
        minfrac = min((hud[s]["life_frac"] for s in range(int(t0), int(t1)) if s in hud and hud[s]["life_frac"] is not None), default=None)
        reserved = h1.get("reserved") or h0.get("reserved") or 0
        ctx = {"character": who, "zone": zone[1] if zone else None,
               "seconds_in_zone": round(t0 - zone[0]) if zone else None,
               "zone_change": [f"{z[0] - t0:+.0f}s {z[1]}" for z in changes], "loading": loading, "reserved_life": reserved,
               "hud_start": {k: num(h0, k) for k in ("life", "shield", "ward", "mana", "spirit") if num(h0, k)},
               "hud_end": {k: num(h1, k) for k in ("life", "shield", "ward", "mana", "spirit") if num(h1, k)},
               "min_life_fraction": round(minfrac, 2) if minfrac is not None else None,
               "target": None, "objectives": (h1.get("objectives") or "")[:200],
               "events": [], "earlier_events": [], "player_mark": any(t0 <= m < t1 for m in marks)}
        bars = [hud[s] for s in range(int(t0), int(t1)) if s in hud and hud[s].get("bar")]
        if bars:
            b = bars[-1]
            nm = next((bar_name[int(x["t"])] for x in bars if int(x["t"]) in bar_name), ("", False))
            ctx["target"] = {"name": nm[0], "name_confirmed": nm[1], "visible_hp": b.get("bar_hp")}
        for lo, hi, key in ((t0, t1, "events"), (t0 - 10, t0, "earlier_events")):
            ev = [(t, f"log:{ty}{'/' + st if st else ''}{' ' + d if d else ''}") for t, ty, st, d in log
                  if lo <= t < hi and not ty.startswith("focus") and ty != "zone_enter"]
            ev += [(t, f"hud:{ty}{' ' + d if d else ''}") for t, ty, d in hudev if lo <= t < hi and ty != "objective_changed"]
            ev += [(t, f"sound:valuable_drop_alert({s})") for t, s in alerts if lo <= t < hi]
            ctx[key] = [f"{t - t0:+.0f}s {e}" for t, e in sorted(ev)]
        idx = [min(nfr, max(1, int(round((t0 + (k + 0.5) * a.win / a.frames_per_win) * fps)) + 1)) for k in range(a.frames_per_win)]
        frames = [f"frames/{a.session}/{i:06d}.jpg" for i in idx]

        def hv(h):
            return ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in h.items()) or "unreadable"

        text = [f"Character: {who}. Zone at the start of the window: {ctx['zone'] or 'unknown'}" + (f" (for {ctx['seconds_in_zone']} s)" if zone else "") + "."
                + (" During the window the player arrives elsewhere: " + "; ".join(ctx["zone_change"]) + "." if changes else "")
                + (" A loading screen covers part of the window." if loading else ""),
                f"HUD at start: {hv(ctx['hud_start'])}. HUD at end: {hv(ctx['hud_end'])}."
                + (f" {reserved} life is reserved, so the usable pool is life_max - {reserved}." if reserved else "")
                + (f" Lowest life in this window: {int(ctx['min_life_fraction'] * 100)}% of the usable pool." if ctx["min_life_fraction"] is not None else "")]
        if ctx["target"]:
            text.append(f"A monster name bar is at the top: '{ctx['target']['name']}'" + ("" if ctx["target"]["name_confirmed"] else " (name read once, may be misread)")
                        + f", visible hp {ctx['target']['visible_hp']}. Whether it is a rare, a unique or a boss is not known from the bar.")
        if ctx["objectives"]:
            text.append(f"Objectives panel: {ctx['objectives']}")
        text.append("Events in this window: " + ("; ".join(ctx["events"]) or "none") + ".")
        if ctx["earlier_events"]:
            text.append("In the 10 s before: " + "; ".join(ctx["earlier_events"]) + ".")
        fh.write(json.dumps({"session": a.session, "t0": t0, "t1": t1, "frames": frames, "context": ctx,
                             "context_text": " ".join(text)}, ensure_ascii=False) + "\n")
        n += 1
        t0 = t1
print(f"{a.session}: {n} windows of {a.win:.0f} s -> {out}")
