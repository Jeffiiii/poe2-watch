"""Read the HUD montages (hud_extract.py) and turn them into per-second values and events. v2: fixed fields, no detector.

The HUD layout is fixed, so the numbers are read with recognition-only OCR on fixed line crops (fast), the boss / elite
bar is found by its red colour, and only the objectives panel uses full detection, every --obj-every seconds.

Per second -> <work>/raw/<session>.hud.csv:
  t, life, life_max, shield, shield_max, ward, ward_max, mana, mana_max, spirit, spirit_max, bar, bar_hp, bar_name, objectives
  bar = "boss" | "elite" | "" (red name bar at the top centre; elites sit ~10 px higher than bosses), bar_hp = visible red fraction
Events -> <work>/raw/<session>.hud_events.csv (time_seconds, type, detail):
  life_drop (>30% of max within 2 s), low_life (<35%), life_recovered (>80% after low), death (life reads 0),
  boss_appear / boss_gone, boss_hp_low (<20%), elite_appear, map_completed, objective_changed

Usage: python watch/hud_read.py <session> [--work C:/Users/Leo12/Videos/poe2-work] [--obj-every 5]
"""
import argparse
import csv
import json
import os
import re
import time

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

import hud_clean

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--obj-every", type=int, default=5)
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--events-only", action="store_true", help="recompute events from the existing hud.csv, no OCR")
ap.add_argument("--patch-reserved", action="store_true", help="keep the existing hud.csv, only read the Reserved line (left block) and add the column")
a = ap.parse_args()
hdir = os.path.join(a.work, "hud", a.session)
meta = json.load(open(os.path.join(hdir, "hud.json")))
fps = meta["fps"]
files = sorted(f for f in os.listdir(hdir) if f.endswith(".jpg"))
if a.limit:
    files = files[: a.limit]
ocr = None if a.events_only else RapidOCR()
NUM = re.compile(r"(\d[\d,\.]*)\s*/\s*(\d[\d,\.]*)")
# The value block is bottom-anchored: with no Ward line, Life and Shield move down one slot. So read whole line slots
# (label + number) and let the label say which value it is. (x0, y0, x1, y1) in montage coordinates.
SLOTS = [(40, 55, 245, 82), (40, 80, 245, 107), (40, 105, 245, 132),      # left block, three line slots
         (75, 180, 285, 207), (75, 205, 285, 232)]                         # right block, two line slots
KEYS = ("life", "shield", "ward", "mana", "spirit")
ONE = re.compile(r"(\d[\d,\.]*)$")      # the Reserved line has a single number
T_X0, T_X1 = 320, 960          # top-centre region inside the montage
O_BOX = (960, 0, 1420, 480)    # objectives region


def rec(img_np, scale=2):
    """recognition-only OCR of one text line"""
    im = Image.fromarray(img_np)
    if scale != 1:
        im = im.resize((im.width * scale, im.height * scale), Image.BICUBIC)
    res, _ = ocr(np.asarray(im), use_det=False, use_cls=False, use_rec=True)
    if not res:
        return "", 0.0
    return str(res[0][0]).strip(), float(res[0][1])


def to_int(s):
    s = s.replace(",", "").replace(".", "")
    return int(s) if s.isdigit() else None


def red_mask(x):
    x = x.astype(int)
    return (x[..., 0] > 90) & (x[..., 0] > 2.2 * x[..., 1]) & (x[..., 0] > 1.6 * x[..., 2])


out = os.path.join(a.work, "raw", f"{a.session}.hud.csv")
t0 = time.time()
if a.events_only:
    pass
elif a.patch_reserved:
    raw = list(csv.DictReader(open(out, encoding="utf-8")))
    by_t = {round(float(r["t"])): r for r in raw}
    for i, f in enumerate(files):
        r = by_t.get(round((int(os.path.splitext(f)[0]) - 1) / fps))
        if r is None:
            continue
        r["reserved"] = ""
        if r["ward"] != "":                     # the third line is Ward, there is no Reserved line
            continue
        img = np.asarray(Image.open(os.path.join(hdir, f)).convert("RGB"))
        for (x0, y0, x1, y1) in SLOTS[:3]:
            text, conf = rec(img[y0:y1, x0:x1])
            flat = text.lower().replace(" ", "")
            m = ONE.search(flat)
            if "reserv" in flat[:9] and m and conf > 0.5 and to_int(m.group(1)):
                r["reserved"] = to_int(m.group(1))
        if (i + 1) % 300 == 0:
            print(f"  {i + 1}/{len(files)} seconds, {(time.time() - t0) / (i + 1) * 1000:.0f} ms each", flush=True)
    rows = raw
else:
    rows = []
    last_obj = ""
    for i, f in enumerate(files):
        idx = int(os.path.splitext(f)[0])
        t = (idx - 1) / fps
        img = np.asarray(Image.open(os.path.join(hdir, f)).convert("RGB"))
        row = {"t": t}
        for (x0, y0, x1, y1) in SLOTS:
            text, conf = rec(img[y0:y1, x0:x1])
            flat = text.lower().replace(" ", "")
            key = next((k for k in KEYS if k in flat[:8]), None)
            m1 = ONE.search(flat)
            if "reserv" in flat[:9] and m1 and conf > 0.5 and to_int(m1.group(1)):
                row["reserved"] = to_int(m1.group(1))
            m = NUM.search(flat)
            if key and m and conf > 0.5 and key not in row:
                cur, mx = to_int(m.group(1)), to_int(m.group(2))
                if cur is not None and mx and cur <= mx * 1.6:
                    row[key], row[key + "_max"] = cur, mx
        # boss / elite bar: strongest red 8-row band in the top-centre region
        T = img[0:110, T_X0:T_X1]
        best_y, best = 0, 0.0
        for y in range(24, 72, 4):
            fr = red_mask(T[y : y + 8]).mean()
            if fr > best:
                best_y, best = y, fr
        row["bar"], row["bar_hp"], row["bar_name"] = "", "", ""
        if best > 0.25:
            row["bar"] = "boss" if best_y >= 40 else "elite"
            cols = red_mask(T[best_y : best_y + 8]).mean(0) > 0.5
            row["bar_hp"] = round(float(cols.mean()), 3)
            name, conf = rec(T[max(0, best_y - 8) : best_y + 22, 110:530], scale=2)
            if conf > 0.6 and len(re.sub(r"[^A-Za-z]", "", name)) >= 4:
                row["bar_name"] = name
        if i % a.obj_every == 0:
            x0, y0, x1, y1 = O_BOX
            res, _ = ocr(img[y0:y1, x0:x1])
            lines = sorted(((sum(p[1] for p in b) / 4, tx) for b, tx, cf in (res or []) if float(cf) > 0.6), key=lambda z: z[0])
            last_obj = " | ".join(tx.strip() for _, tx in lines)
        row["objectives"] = last_obj
        rows.append(row)
        if (i + 1) % 300 == 0:
            print(f"  {i + 1}/{len(files)} seconds, {(time.time() - t0) / (i + 1) * 1000:.0f} ms each", flush=True)

cols = ["t", "life", "life_max", "shield", "shield_max", "ward", "ward_max", "mana", "mana_max", "spirit", "spirit_max",
        "bar", "bar_hp", "bar_name", "objectives", "reserved"]
if not a.events_only:
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

# ------------------------------------------------------------------ events
ev = []
# cleaned readings (hud_clean): max filter, dropped leading digit, life fraction against the unreserved pool
rows = hud_clean.load(out)
frac = [(r["t"], r["life_frac"]) for r in rows]
low = dead = False
for k, (t, fr) in enumerate(frac):
    if fr is None:
        continue
    prev = [x for x in frac[max(0, k - 2) : k] if x[1] is not None]
    nxt = next((x[1] for x in frac[k + 1 : k + 3] if x[1] is not None), None)
    confirmed = nxt is not None and nxt < 0.6          # still hurt one or two seconds later, or it was a misread
    if prev and max(p[1] for p in prev) - fr > 0.30 and (confirmed or fr == 0):
        ev.append((t, "life_drop", f"{max(p[1] for p in prev):.2f}->{fr:.2f}"))
    if fr == 0 and not dead and (nxt == 0 or nxt is None):
        dead = True
        ev.append((t, "death", ""))
    elif fr > 0:
        dead = False
    if not low and fr < 0.35 and (confirmed or fr == 0):
        low = True
        ev.append((t, "low_life", f"{fr:.2f}"))
    elif low and fr > 0.80:
        low = False
        ev.append((t, "life_recovered", f"{fr:.2f}"))


def sig(s):
    return re.sub(r"[^a-z]", "", s.lower())


# boss / elite bar with debounce: present for 2 consecutive seconds = appear; absent for 4 = gone
state, run_on, run_off, cur_name, hp_low, last_elite = "", 0, 0, "", False, -99.0
for r in rows:
    kind = r["bar"]
    if kind:
        run_on += 1
        run_off = 0
        if r["bar_name"] and not cur_name:
            cur_name = r["bar_name"]
        if run_on == 2 and state != kind:
            state = kind
            if kind == "boss":
                ev.append((r["t"] - 1, "boss_appear", r["bar_name"] or cur_name))
            elif r["t"] - last_elite > 10:
                ev.append((r["t"] - 1, "elite_appear", r["bar_name"] or cur_name))
                last_elite = r["t"]
        if state == "boss" and r["bar_hp"] is not None and r["bar_hp"] < 0.2 and not hp_low and run_on > 3:
            hp_low = True
            ev.append((r["t"], "boss_hp_low", cur_name))
    else:
        run_off += 1
        run_on = 0
        if run_off == 4 and state:
            if state == "boss":
                ev.append((r["t"] - 3, "boss_gone", cur_name))
            state, cur_name, hp_low = "", "", False

done_at = -99.0
for r in rows:
    if "mapcompleted" in sig(r["objectives"]):
        if r["t"] - done_at > 15:
            ev.append((r["t"], "map_completed", ""))
        done_at = r["t"]
last_sig, pend, pend_n = None, None, 0
for r in rows[:: a.obj_every]:
    s = sig(r["objectives"])[:160]
    if s == pend:
        pend_n += 1
    else:
        pend, pend_n = s, 1
    if pend_n == 2 and s != last_sig:
        if last_sig is not None:
            ev.append((r["t"] - a.obj_every, "objective_changed", r["objectives"][:90]))
        last_sig = s
ev.sort()
out_ev = os.path.join(a.work, "raw", f"{a.session}.hud_events.csv")
with open(out_ev, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["time_seconds", "type", "detail"])
    for t, ty, d in ev:
        w.writerow([f"{t:.1f}", ty, d])
got = sum(1 for r in rows if r.get("life") is not None)
counts = {}
for _, ty, _ in ev:
    counts[ty] = counts.get(ty, 0) + 1
print(f"{a.session}: {len(rows)} s read in {(time.time() - t0) / 60:.1f} min ({(time.time() - t0) / max(len(rows), 1) * 1000:.0f} ms/s); "
      f"life read in {got / max(len(rows), 1):.0%}; events: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
print("->", out, "and", out_ev)
