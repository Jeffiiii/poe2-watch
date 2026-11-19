"""The eyes, first live version: watch an incoming video stream and keep a running understanding of the game.

Three loops, as agreed with the owner (docs/research/watching-survey, section on the runtime):
  sense       every frame (2 fps): a cheap pixel-change score; once a second a HUD read (life / mana) that raises
              immediate events (life_drop, low_life, death) without any language model  — the fast path (< 500 ms)
  understand  every `interval` seconds (adaptive: 6 s when the picture is changing, 12 s when quiet; at once on a fast-path
              event): the last 5 s as four frames (first and last at 1280 px, the middle two at 896) -> the fine-tuned
              student (served by vLLM, OpenAI-compatible) -> {scene, text, inferred, state}; the previous state is fed back
  speak       decides whether this moment is worth a line: death, level-up, a new name bar, a threat change -> a candidate
              utterance queued for the character (v1 just records the candidates)

HTTP (port 8000): /state (latest), /events?since=N, /speak (pending candidates, cleared on read), /frame.jpg,
/monitor (a page that shows frame, state and narration, refreshing itself).

Usage: python live.py --stream rtsp://127.0.0.1:8554/game --vllm http://127.0.0.1:8001/v1 --model student [--log /workspace/live/log.jsonl]
"""
import argparse
import base64
import collections
import io
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--stream", default="rtsp://127.0.0.1:8554/game")
ap.add_argument("--vllm", default="http://127.0.0.1:8001/v1")
ap.add_argument("--model", default="student")
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--log", default="/workspace/live/log.jsonl")
ap.add_argument("--fps", type=float, default=2)
ap.add_argument("--fast-interval", type=float, default=6)
ap.add_argument("--slow-interval", type=float, default=12)
ap.add_argument("--max-tokens", type=int, default=700)
a = ap.parse_args()
os.makedirs(os.path.dirname(a.log), exist_ok=True)

NARRATE = ("你在实时看一段 Path of Exile 2 的画面。这是最近 5 秒的 4 帧，按时间先后排列。\n上一个 5 秒的局面：{prev}\n"
           "请只根据画面写这 5 秒的讲解，输出 JSON：scene（画面里发生了什么，按先后）；text（屏幕上的文字和读数）；"
           "inferred（由画面推出的东西，每条带 basis 和 confidence，玩家意图只能写在这里）；state（place、activity、threat）。")

frames = collections.deque(maxlen=int(a.fps * 30))      # (t, jpeg bytes)
lock = threading.Lock()
S = {"state": None, "narration": None, "prev": "（刚开始看，没有上文）", "last_understand": 0.0, "change": 0.0, "interval": a.slow_interval,
     "hud": {}, "events": [], "speak": [], "n_calls": 0, "last_latency": 0.0, "started": time.time(), "wake": False}
ev_id = 0


def log(kind, **kw):
    global ev_id
    with lock:
        ev_id += 1
        rec = {"id": ev_id, "t": round(time.time() - S["started"], 1), "kind": kind, **kw}
        S["events"].append(rec)
        S["events"] = S["events"][-500:]
    with open(a.log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# ------------------------------------------------------------------ frames from the stream (ffmpeg -> mjpeg pipe)
def reader():
    while True:
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", a.stream, "-vf", f"fps={a.fps},scale=1280:-2",
               "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        buf = b""
        while True:
            chunk = p.stdout.read(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                i = buf.find(b"\xff\xd8")
                j = buf.find(b"\xff\xd9", i + 2) if i >= 0 else -1
                if i < 0 or j < 0:
                    break
                jpg, buf = buf[i : j + 2], buf[j + 2 :]
                with lock:
                    frames.append((time.time(), jpg))
                sense(jpg)
        p.wait()
        log("stream", note="reader restarted (stream ended or not yet available)")
        time.sleep(3)


# ------------------------------------------------------------------ sense: pixel change + HUD fast path
_prev_small = None
_last_hud = 0.0
_ocr = None
_life_hist = collections.deque(maxlen=6)
_pool = collections.deque(maxlen=90)        # ~90 s of once-a-second life readings


def sense(jpg):
    global _prev_small, _last_hud, _ocr
    im = Image.open(io.BytesIO(jpg)).convert("L").resize((32, 20))
    x = np.asarray(im, dtype=np.float32) / 255
    if _prev_small is not None:
        d = float(np.abs(x - _prev_small).mean())
        with lock:
            S["change"] = 0.7 * S["change"] + 0.3 * d
            S["interval"] = a.fast_interval if S["change"] > 0.04 else a.slow_interval
    _prev_small = x
    now = time.time()
    if now - _last_hud < 1.0:
        return
    _last_hud = now
    try:
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
        full = Image.open(io.BytesIO(jpg)).convert("RGB")           # 1280x800 = 2/3 of the 1920x1200 layout
        life = read_line(full, (27, 587, 163, 605))                   # "Life 1,624/1,624" line, slot 1 of the left block
        mana = read_line(full, (50, 670, 190, 688))
        third = read_line(full, (27, 620, 163, 638))                  # slot 3: "Ward 34/34" or "Reserved 1,067"
        reserved = int(re.sub(r"\D", "", third.split("eserv")[-1]) or 0) if "eserv" in third.lower() else 0
        hud = {}
        for key, txt in (("life", life), ("mana", mana)):
            m = re.search(r"(\d[\d,\.]*)\s*/\s*(\d[\d,\.]*)", txt.replace(" ", ""))
            if m:
                cur, mx = int(re.sub(r"\D", "", m.group(1)) or 0), int(re.sub(r"\D", "", m.group(2)) or 0)
                if mx and cur <= mx * 1.6:
                    hud[key] = [cur, mx]
        with lock:
            S["hud"] = hud
        if "life" in hud:
            # the usable pool = the highest current value seen lately (reserved life never shows as current; an OCR slip
            # on the Reserved line must not look like a wound)
            _pool.append(hud["life"][0])
            usable = max(max(_pool), 1)
            hud["reserved"] = reserved
            hud["usable"] = usable
            fr = min(1.0, hud["life"][0] / usable)
            _life_hist.append(fr)
            if len(_life_hist) >= 3:
                prev = max(list(_life_hist)[:-1])
                if fr == 0 and _life_hist[-2] == 0:
                    fire("death", f"生命 0/{hud['life'][1]}")
                elif prev - fr > 0.30:
                    fire("life_drop", f"{prev:.0%} -> {fr:.0%}")
                elif fr < 0.35 and _life_hist[-2] < 0.35:
                    fire("low_life", f"{fr:.0%}")
    except Exception as exn:
        log("sense_error", error=str(exn)[:120])


_last_fire = {}


def fire(kind, detail):
    now = time.time()
    if now - _last_fire.get(kind, 0) < 10:
        return
    _last_fire[kind] = now
    log("fast", event=kind, detail=detail)
    with lock:
        S["wake"] = True
        S["speak"].append({"t": round(now - S["started"], 1), "why": kind, "text": f"（快路径）{kind}：{detail}"})


def read_line(im, box):
    crop = im.crop(box)
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.BICUBIC)
    res, _ = _ocr(np.asarray(crop), use_det=False, use_cls=False, use_rec=True)
    return str(res[0][0]) if res else ""


# ------------------------------------------------------------------ understand: the student via vLLM
def pick_frames():
    with lock:
        fs = list(frames)
    if len(fs) < 4:
        return None
    now = fs[-1][0]
    want = [now - 5 + 1.25, now - 5 + 2.5, now - 5 + 3.75, now]
    out = []
    for k, tw in enumerate(want):
        t, jpg = min(fs, key=lambda f: abs(f[0] - tw))
        if k in (1, 2):
            im = Image.open(io.BytesIO(jpg)).convert("RGB")
            im = im.resize((896, int(im.height * 896 / im.width)))
            b = io.BytesIO()
            im.save(b, "JPEG", quality=85)
            jpg = b.getvalue()
        out.append(jpg)
    return out


def ask_student(jpgs, prompt):
    content = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(j).decode()}} for j in jpgs]
    content.append({"type": "text", "text": prompt})
    body = {"model": a.model, "messages": [{"role": "user", "content": content}], "max_tokens": a.max_tokens, "temperature": 0.0,
            "repetition_penalty": 1.1}
    req = urllib.request.Request(a.vllm + "/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def as_json(s):
    m = re.search(r"\{.*\}", s, flags=re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


_last_bar = ""


def understander():
    global _last_bar
    while True:
        time.sleep(0.5)
        with lock:
            due = time.time() - S["last_understand"] >= S["interval"] or S["wake"]
            S["wake"] = False
        if not due:
            continue
        jpgs = pick_frames()
        if not jpgs:
            continue
        t0 = time.time()
        try:
            txt = ask_student(jpgs, NARRATE.format(prev=S["prev"]))
        except Exception as exn:
            log("understand_error", error=str(exn)[:160])
            with lock:
                S["last_understand"] = time.time()
            continue
        d = as_json(txt)
        st = d.get("state") if isinstance(d, dict) else None
        with lock:
            S["narration"] = d if d else {"raw": txt[:800]}
            S["last_understand"] = time.time()
            S["n_calls"] += 1
            S["last_latency"] = round(time.time() - t0, 1)
            old = S["state"]
            if st:
                S["state"] = st
                S["prev"] = json.dumps(st, ensure_ascii=False)
        log("understand", latency=S["last_latency"], state=st, scene=(d.get("scene") if isinstance(d, dict) else None))
        # speak: what is worth a line
        if st and isinstance(st, dict):
            why = None
            text = ""
            threat = str(st.get("threat", ""))
            old_threat = str((old or {}).get("threat", ""))
            full = json.dumps(d, ensure_ascii=False)
            bar = re.search(r"名条(?:显示|出现|为|：|:)?「([^」]{3,60})」", full)      # the name bar itself, not a drop label mentioned nearby
            if re.search("阵亡|死亡|You Have Died", full):
                why, text = "death", f"玩家倒下了：{st.get('activity', '')}"
            elif re.search(r"升级了|升到 ?\d+ ?级|now level|LEVEL UP", full):
                why, text = "levelup", "升级了"
            elif bar and re.sub(r"[^a-z]", "", bar.group(1).lower())[:10] != _last_bar:     # same monster, varying spelling -> one line
                _last_bar = re.sub(r"[^a-z]", "", bar.group(1).lower())[:10]
                why, text = "new_bar", f"出现了 {bar.group(1)}"
            elif old is not None and (("安全" in old_threat) != ("安全" in threat)) and threat:
                why, text = "threat", f"局面变了：{threat[:60]}"
            if why:
                with lock:
                    S["speak"].append({"t": round(time.time() - S["started"], 1), "why": why, "text": text})
                log("speak", why=why, text=text)


# ------------------------------------------------------------------ HTTP
MON = """<!doctype html><meta charset=utf-8><title>eyes</title><style>body{font:14px/1.5 system-ui;margin:0;padding:12px;background:#111;color:#eee}
.row{display:flex;gap:14px}img{width:640px;border-radius:6px}pre{white-space:pre-wrap;font:13px/1.4 ui-monospace,monospace;background:#1b1b1b;padding:8px;border-radius:6px;max-height:70vh;overflow:auto}
h3{margin:8px 0 4px;color:#9cf}</style><body><div class=row><div><img id=f src=/frame.jpg><h3>局面</h3><pre id=s></pre><h3>说话候选</h3><pre id=k></pre></div>
<div style="flex:1"><h3>讲解</h3><pre id=n></pre></div></div><script>
async function tick(){var r=await fetch('/state');var j=await r.json();document.getElementById('s').textContent=JSON.stringify({state:j.state,hud:j.hud,interval:j.interval,change:j.change,calls:j.n_calls,latency:j.last_latency},null,1);
document.getElementById('n').textContent=JSON.stringify(j.narration,null,1);document.getElementById('k').textContent=(j.speak_recent||[]).map(x=>x.t+'s ['+x.why+'] '+x.text).join('\\n');document.getElementById('f').src='/frame.jpg?'+Date.now();}
setInterval(tick,2000);tick();</script>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/frame.jpg":
            with lock:
                jpg = frames[-1][1] if frames else b""
            return self.send(200 if jpg else 404, jpg, "image/jpeg")
        if path == "/monitor" or path == "/":
            return self.send(200, MON.encode(), "text/html; charset=utf-8")
        if path == "/state":
            with lock:
                body = {k: S[k] for k in ("state", "narration", "hud", "interval", "change", "n_calls", "last_latency")}
                body["speak_recent"] = S["speak"][-8:]
                body["uptime"] = round(time.time() - S["started"])
            return self.send(200, json.dumps(body, ensure_ascii=False).encode())
        if path == "/events":
            since = int((re.search(r"since=(\d+)", self.path) or [0, 0])[1])
            with lock:
                body = [e for e in S["events"] if e["id"] > since]
            return self.send(200, json.dumps(body, ensure_ascii=False).encode())
        if path == "/restart":                 # serve.sh re-downloads live.py and starts it again
            self.send(200, b'{"restarting": true}')
            threading.Timer(0.5, lambda: os._exit(0)).start()
            return
        if path == "/speak":
            with lock:
                body, S["speak"] = S["speak"], []
            return self.send(200, json.dumps(body, ensure_ascii=False).encode())
        self.send(404, b"{}")


threading.Thread(target=reader, daemon=True).start()
threading.Thread(target=understander, daemon=True).start()
log("start", stream=a.stream, vllm=a.vllm)
ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
