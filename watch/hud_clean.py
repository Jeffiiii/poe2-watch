"""Load <session>.hud.csv and drop the readings that are OCR accidents. Shared by hud_read (events), build_context, validate_labels.

Three rules, all found by checking the teacher's narration against the reader (2026-10-05):
  max filter      a reading is trusted only if its maximum is within 0.6-1.6x of the local median maximum (+-15 s).
                  Buffs, death and weapon-set swaps move the maximum a little; misreads move it 10x (42 -> 421).
  dropped digit   "1,624/1,624" is sometimes read as "624/1,624". A current value that is the maximum minus its leading
                  digit(s) is dropped unless a neighbouring second (+-3 s) reads the same value.
  reserved life   with a "Reserved 1,067" line under Life, "Life 425/1,492" is a FULL life pool. life_frac is therefore
                  life / (life_max - reserved); reserved is the same-second reading, else the local median.

Every row comes back with ints or None for life/shield/ward/mana/spirit (+ _max), reserved, and life_frac.
"""
import csv

KEYS = ("life", "shield", "ward", "mana", "spirit")


def load(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        d = {"t": float(r["t"]), "bar": r["bar"], "bar_name": r["bar_name"], "objectives": r["objectives"],
             "bar_hp": float(r["bar_hp"]) if r["bar_hp"] != "" else None}
        for k in KEYS:
            ok = r[k] != "" and r[k + "_max"] != ""
            d[k], d[k + "_max"] = (int(r[k]), int(r[k + "_max"])) if ok else (None, None)
        d["reserved"] = int(r["reserved"]) if r.get("reserved") else None
        rows.append(d)
    clean(rows)
    return rows


def _median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def clean(rows):
    n = len(rows)
    for key in KEYS:
        mx = [r[key + "_max"] for r in rows]
        for k, r in enumerate(rows):
            if r[key] is None:
                continue
            med = _median([x for x in mx[max(0, k - 15) : k + 16] if x])
            if not med or not (0.6 * med <= r[key + "_max"] <= 1.6 * med):
                r[key] = r[key + "_max"] = None
        cur = [r[key] for r in rows]
        for k, r in enumerate(rows):
            c, m = r[key], r[key + "_max"]
            if c is None or c >= m or len(str(c)) >= len(str(m)) or not str(m).endswith(str(c)):
                continue
            near = [x for x in cur[max(0, k - 3) : k] + cur[k + 1 : k + 4] if x is not None]
            if c not in near:
                r[key] = r[key + "_max"] = None
    res = [r["reserved"] for r in rows]
    for k, r in enumerate(rows):
        r["life_frac"] = None
        if r["life"] is None:
            continue
        lo, hi = max(0, k - 15), min(n, k + 16)
        seen = [x for x in res[lo:hi] if x]
        med = _median(seen) if len(seen) >= 5 else 0
        rv = r["reserved"] if r["reserved"] and r["reserved"] < r["life_max"] else med
        if not rv or rv >= r["life_max"]:
            rv = 0
        r["reserved"] = rv
        r["life_frac"] = min(1.0, r["life"] / (r["life_max"] - rv))
