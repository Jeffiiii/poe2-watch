"""Production teacher labelling of one recording unit: episode outlines, then three-layer narration of every 5 s window.

The recording (1280x800 H.264 copy in <work>/label_src/<session>.mp4) is uploaded once; every call addresses a time range of
that file through video offsets, so nothing is cut locally.

  episodes   the unit is split where the player changes zone (Client.txt loading_done events); pieces longer than
             --max-episode seconds are split evenly. Pass 1 writes an outline per episode (2 fps, default resolution).
  windows    the 5 s windows from <work>/context/<session>.jsonl are narrated three at a time: the call sees the 15 s plus a
             2 s lead-in and tail (5 fps, high resolution), the episode outline, the character card, the general mechanics
             notes and the automatically extracted context of each window (flagged as fallible).

Output (resumable; finished episodes and windows are skipped on re-run):
  <work>/labels/<session>.outlines.json     {episodes: [{t0, t1, zone, outline, usage}]}
  <work>/labels/<session>.windows.jsonl     one line per window: t0, t1, scene, text, inferred, state, context_conflicts, usage share
  <work>/labels/<session>.usage.json        token totals and a cost estimate

Cost (2026-10-06): --batch sends every call of a stage through the Batch API (50% off, results within a day; the job name
is kept in <session>.batch.json so a rerun resumes polling). --text-first puts the fixed text (card, notes, outline) before
the video so the prefix is identical across the groups of an episode and the implicit cache can price it at 10%.
--fps 3 (default 5) cuts the video tokens by 40%; the owner judged it against 5 fps blind before it was adopted.

Usage: python watch/label_session.py <session> [--model gemini-3.8-flash] [--workers 4] [--limit-groups N]
       [--batch] [--text-first] [--fps 3] [--tag name] [--windows 105,135]
"""
import argparse
import concurrent.futures as cf
import csv
import json
import os
import threading
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--model", default="gemini-3.8-flash")
ap.add_argument("--workers", type=int, default=4)
ap.add_argument("--max-episode", type=float, default=300)
ap.add_argument("--outline-fps", type=float, default=2)
ap.add_argument("--fps", type=float, default=5)
ap.add_argument("--limit-groups", type=int, default=0, help="only the first N window groups (test)")
ap.add_argument("--windows", default="", help="only windows [a,b) by index, e.g. 105,135 (test)")
ap.add_argument("--batch", action="store_true", help="Batch API: half price, answers within a day")
ap.add_argument("--text-first", action="store_true", help="fixed text before the video (cacheable prefix)")
ap.add_argument("--tag", default="", help="output files get <session>.<tag>.* (for side-by-side tests)")
ap.add_argument("--price-in", type=float, default=0.75, help="assumed USD per 1M input tokens (for the estimate only)")
ap.add_argument("--price-out", type=float, default=3.75, help="assumed USD per 1M output+thinking tokens (for the estimate only)")
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--root", default=r"C:/Users/Leo12/Documents/poe2-watch")
a = ap.parse_args()
load_dotenv(os.path.join(a.root, ".env"))
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
S = a.session
LD = os.path.join(a.work, "labels")
os.makedirs(LD, exist_ok=True)
pre = f"{S}.{a.tag}" if a.tag else S
p_out, p_win, p_use, p_bat = (os.path.join(LD, f"{pre}.{x}") for x in ("outlines.json", "windows.jsonl", "usage.json", "batch.json"))
if a.tag and not os.path.exists(p_out) and os.path.exists(os.path.join(LD, f"{S}.outlines.json")):
    import shutil                                   # a tagged test reuses the outlines already paid for
    shutil.copy(os.path.join(LD, f"{S}.outlines.json"), p_out)
windows = [json.loads(l) for l in open(os.path.join(a.work, "context", f"{S}.jsonl"), encoding="utf-8")]
dur = json.load(open(os.path.join(a.work, "frames", S, "frames.json")))["duration"]
meta_p = os.path.join(a.work, "raw", f"{S}.json")
meta = json.load(open(meta_p, encoding="utf-8")) if os.path.exists(meta_p) else {}
char = (meta.get("character") or {}).get("name", "")
card_p = os.path.join(a.root, "build_cards", f"{char}.md")
if os.path.exists(card_p) and "这张卡写一次" not in open(card_p, encoding="utf-8").read()[:400]:
    card = open(card_p, encoding="utf-8").read()
else:
    c = meta.get("character") or {}
    card = (f"角色 {c.get('name', '?')}，{c.get('class') or c.get('ascendancy') or '?'}，{c.get('mode', '')}，等级范围 {c.get('level_range', '?')}。"
            f"本场内容：{meta.get('content', '?')}。没有详细角色卡：不要假设它有任何特殊天赋或机制。")
mech = open(os.path.join(a.root, "knowledge", "poe2_mechanics.md"), encoding="utf-8").read()
KNOW = "## 角色卡\n" + card + "\n\n## 通用机制笔记\n" + mech
if meta.get("content"):                     # per-recording notes: which character, which content, deaths, mid-recording character switches
    KNOW += "\n\n## 本场录像说明\n" + str(meta["content"])

OUTLINE_SYS = """你是一位精通 Path of Exile 2 的解说老师。你将看到一段连续游戏录像中的一个「段落」（通常是从进入一个区域到离开它）。请先通读全段，再写出提纲，让之后逐段细讲的人知道每一刻处在什么局面里。全部用中文，游戏专有名词保留英文。时间一律用「段落内的秒数」，段落第 0 秒就是你看到的第一帧。

- phases：把全段切成若干阶段（跑图、某个玩法内容、Boss 战、拾取、城镇或藏身处里的整理与对话等），每个给出起止秒数、在做什么、局面如何。
- events：值得记住的事件，按时间排列，每个给出秒数、发生了什么、依据（画面上看到了什么）。包括：稀有怪或 Boss 的出现与死亡及其名条下的词缀、值钱的掉落、玩家资源的大幅变化、危险时刻、死亡、升级、任务进展、换区。
- causes：对结果的因果解释。如果玩家死了或险些死了，必须结合角色卡和机制笔记说明原因并指出画面证据；说不清就写不确定。没有值得解释的结果就给空数组。
- player_pattern：这段里玩家反复出现的做法。只写画面上能看到的重复行为，不要猜动机。

意图只能作为推断并注明把握。没有依据的不要写。只输出 JSON：
{"phases":[{"t0":0,"t1":0,"what":"...","situation":"..."}],"events":[{"t":0,"what":"...","evidence":"..."}],"causes":[{"outcome":"...","explanation":"...","evidence":"...","confidence":"高|中|低"}],"player_pattern":["..."]}"""

WINDOW_SYS = """你是一位精通 Path of Exile 2 的解说老师，正在为一小段录像写「扎根的讲解」，用来训练一个只看画面的模型，所以每一句都必须能在这段视频里找到依据。
你已经看过它所属的整个段落，段落提纲会给你；用它判断此刻处在什么局面，但逐窗口的描述必须来自这段短视频本身。

你看到的短视频由若干个连续的 5 秒窗口组成，前后各带最多 2 秒的引子和尾巴。每个窗口在短视频里的起止秒数会告诉你。只为列出的窗口写讲解。全部用中文，游戏专有名词保留英文。

每个窗口三层：
1. scene（画面）：游戏画面本身发生了什么，按时间先后，这一层最详细。地形；玩家在哪、往哪走、做了什么；有哪些怪、大约几只、在什么方位、被什么打、死没死；地面效果和技能特效各是什么颜色形状、是谁放的；伤害来自哪里；掉落物从哪出现、哪些被捡（标签消失且玩家在旁）、哪些没捡。在城镇、藏身处或界面里时，写玩家点了什么、打开了什么、移动了什么物品。看不清就说看不清。不要在这一层复述 HUD 数字。
2. text（界面与文字）：屏幕上的文字和读数及其变化。HUD 数值；顶部名条的名字、血条比例和名条下的词缀小字；掉落物标签；左下角台词与系统消息；目标面板；打开的界面与弹出的说明框。只写确实看到的。
3. inferred（推断）：画面没有直接写出、但能由画面加角色卡、机制笔记或段落提纲推出的东西：机制解释（尤其是怪物词缀或地面效果对这个角色意味着什么）、局面判断、玩家可能的意图。每条给出 basis（画面 / 角色卡 / 机制笔记 / 段落提纲 / 游戏知识）和 confidence（高 / 中 / 低）。玩家意图永远只能是推断。来自游戏知识而非画面的判断必须注明。没有可推断的就给空数组。

另外每个窗口给出 state（place、activity、threat；threat 要写依据的读数，并按角色卡的规则判断）和 context_conflicts（自动上下文、提纲或角色卡与这段视频不一致的地方；自动上下文是程序提取的，可能有错，冲突时以视频为准；没有就空数组）。

只输出 JSON：{"windows":[{"id":0,"scene":"...","text":"...","inferred":[{"claim":"...","basis":"...","confidence":"..."}],"state":{"place":"...","activity":"...","threat":"..."},"context_conflicts":[]}]}
其中 id 用我给出的窗口编号。"""

lock = threading.Lock()
usage = json.load(open(p_use)) if os.path.exists(p_use) else {"prompt": 0, "output": 0, "thoughts": 0, "calls": 0, "seconds": 0.0}


def request(f, t0, t1, fps, system, user, high, key):
    cfg = types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", temperature=0.2,
                                      media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH if high else None)
    video = types.Part(file_data=types.FileData(file_uri=f.uri, mime_type="video/mp4"),
                       video_metadata=types.VideoMetadata(start_offset=f"{t0:.0f}s", end_offset=f"{t1:.0f}s", fps=fps))
    if isinstance(user, tuple):                                   # (fixed text, per-call text)
        parts = [types.Part(text=user[0]), video, types.Part(text=user[1])] if a.text_first else [video, types.Part(text=user[0] + user[1])]
    else:
        parts = [video, types.Part(text=user)]
    return {"key": key, "cfg": cfg, "contents": [types.Content(role="user", parts=parts)]}


def account(um, seconds):
    with lock:
        usage["prompt"] += um.prompt_token_count or 0
        usage["output"] += um.candidates_token_count or 0
        usage["thoughts"] += getattr(um, "thoughts_token_count", 0) or 0
        usage["cached"] = usage.get("cached", 0) + (getattr(um, "cached_content_token_count", 0) or 0)
        usage["calls"] += 1
        usage["seconds"] += seconds


def call_sync(rq):
    last = None
    for attempt in range(5):
        try:
            ts = time.time()
            r = client.models.generate_content(model=a.model, config=rq["cfg"], contents=rq["contents"])
            data = json.loads(r.text)
            account(r.usage_metadata, time.time() - ts)
            return data
        except Exception as ex:  # rate limits, transient errors, malformed JSON
            last = ex
            time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"call failed after retries: {last}")


DONE_STATES = ("JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED", "JOB_STATE_PARTIALLY_SUCCEEDED")


def run_stage(stage, rqs, on_result):
    """run every request of a stage; on_result(key, data) is called as answers arrive. Batch mode submits once and polls."""
    if not rqs:
        return
    if not a.batch:
        with cf.ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(call_sync, rq): rq["key"] for rq in rqs}
            for fu in cf.as_completed(futs):
                try:
                    on_result(futs[fu], fu.result())
                except Exception as exn:
                    print("  call failed:", str(exn)[:200], flush=True)
        return
    bat = json.load(open(p_bat)) if os.path.exists(p_bat) else {}
    job = bat.get(stage)
    keys = [str(rq["key"]) for rq in rqs]
    if job and set(keys) <= set(job.get("keys", [])):
        name = job["name"]
        print(f"{stage}: resuming batch job {name} ({len(keys)} of {len(job['keys'])} requests still wanted)", flush=True)
    else:
        inl = [types.InlinedRequest(contents=rq["contents"], config=rq["cfg"], metadata={"key": str(rq["key"])}) for rq in rqs]
        jb = client.batches.create(model=a.model, src=inl, config=types.CreateBatchJobConfig(display_name=f"{pre}-{stage}"))
        name = jb.name
        bat[stage] = {"name": name, "keys": keys, "submitted": time.strftime("%Y-%m-%d %H:%M")}
        json.dump(bat, open(p_bat, "w"), indent=1)
        print(f"{stage}: submitted batch job {name} with {len(rqs)} requests", flush=True)
    ts = time.time()
    while True:
        jb = client.batches.get(name=name)
        st = getattr(jb.state, "name", str(jb.state))
        if st in DONE_STATES:
            break
        if int(time.time() - ts) % 600 < 60:
            print(f"  {stage}: {st} after {(time.time() - ts) / 60:.0f} min", flush=True)
        time.sleep(60)
    print(f"{stage}: {st} in {(time.time() - ts) / 60:.0f} min", flush=True)
    resp = (jb.dest.inlined_responses if jb.dest else None) or []
    bykey = {str(rq["key"]): rq["key"] for rq in rqs}
    for k, ir in enumerate(resp):
        mk = (ir.metadata or {}).get("key") if ir.metadata else None
        if mk is not None and str(mk) not in bykey:
            continue                                   # already written by an earlier run
        key = bykey.get(str(mk), rqs[k]["key"] if k < len(rqs) else None)
        if ir.error or not ir.response:
            print(f"  {stage} {key}: error {str(ir.error)[:160]}", flush=True)
            continue
        try:
            data = json.loads(ir.response.text)
        except Exception as exn:
            print(f"  {stage} {key}: bad JSON {str(exn)[:100]}", flush=True)
            continue
        account(ir.response.usage_metadata, 0.0)
        on_result(key, data)
    bat.pop(stage, None)
    json.dump(bat, open(p_bat, "w"), indent=1)


def cost():
    # 2026-10-07: the bill for 10-06 was 1.5x this estimate (US$15.7 vs 10.3), so the estimate carries that factor
    disc = (0.5 if a.batch else 1.0) * 1.5
    cached = usage.get("cached", 0)
    return disc * ((usage["prompt"] - cached) / 1e6 * a.price_in + cached / 1e6 * a.price_in * 0.1 + (usage["output"] + usage["thoughts"]) / 1e6 * a.price_out)


def save_usage():
    with lock:
        u = dict(usage)
        u["estimated_usd"] = round(cost(), 3)
        u["price_assumption"] = {"in_per_M": a.price_in, "out_per_M": a.price_out}
        json.dump(u, open(p_use, "w"), indent=1)


# ------------------------------------------------------------------ upload once
src = os.path.join(a.work, "label_src", f"{S}.mp4")
try:
    f = client.files.upload(file=src)
    for _ in range(300):
        f = client.files.get(name=f.name)
        if getattr(f.state, "name", str(f.state)) == "ACTIVE":
            break
        time.sleep(3)
    else:
        raise SystemExit("upload never became ACTIVE")
except Exception as exn:
    if "402" not in str(exn) or not a.batch:
        raise
    print("upload refused (no credit); only results of batches submitted earlier can be collected in this run", flush=True)
    f = types.File(name="none", uri="https://generativelanguage.googleapis.com/v1beta/files/none")
print(f"{S}: uploaded {os.path.getsize(src) / 1e6:.0f} MB, {dur:.0f} s, {len(windows)} windows, card: {'full' if '## 1.' in card else 'brief'}", flush=True)

# ------------------------------------------------------------------ episodes
ev_p = os.path.join(a.work, "raw", f"{S}.events.csv")
cuts = sorted({float(r["time_seconds"]) for r in csv.DictReader(open(ev_p, encoding="utf-8")) if r["type"] == "loading_done"}) if os.path.exists(ev_p) else []
bounds = [0.0] + [c for c in cuts if 20 < c < dur - 20] + [dur]
eps = []
for b0, b1 in zip(bounds[:-1], bounds[1:]):
    if b1 - b0 < 20 and eps:              # a very short stop-over joins the previous episode
        eps[-1][1] = b1
        continue
    n = max(1, int((b1 - b0) // a.max_episode + (1 if (b1 - b0) % a.max_episode > 30 else 0)))
    step = (b1 - b0) / n
    eps += [[b0 + i * step, b0 + (i + 1) * step] for i in range(n)]
outl = json.load(open(p_out, encoding="utf-8")) if os.path.exists(p_out) else {"session": S, "model": a.model, "episodes": []}
done_ep = {(round(e["t0"]), round(e["t1"])) for e in outl["episodes"]}


def outline_request(e):
    t0, t1 = e
    zone = next((w["context"].get("zone") for w in windows if w["t0"] >= t0 and w["context"].get("zone")), None)
    user = KNOW + f"\n\n这个段落是录像的第 {t0:.0f}–{t1:.0f} 秒（共 {t1 - t0:.0f} 秒），日志显示所在区域：{zone or '未知'}。请观看并输出提纲 JSON。"
    return request(f, t0, t1, a.outline_fps, OUTLINE_SYS, user, False, f"{round(t0)}-{round(t1)}"), zone


todo = [e for e in eps if (round(e[0]), round(e[1])) not in done_ep]
print(f"episodes: {len(eps)} ({len(todo)} to do)", flush=True)
rq_zone = {}
rqs = []
for e in todo:
    rq, zone = outline_request(e)
    rq_zone[rq["key"]] = (e, zone)
    rqs.append(rq)


def on_outline(key, data):
    (t0, t1), zone = rq_zone[key]
    outl["episodes"].append({"t0": t0, "t1": t1, "zone": zone, "outline": data})
    outl["episodes"].sort(key=lambda x: x["t0"])
    json.dump(outl, open(p_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    save_usage()


run_stage("outlines", rqs, on_outline)
print(f"outlines done; est. cost so far ${cost():.2f}", flush=True)

# ------------------------------------------------------------------ windows, three per call
done_w = set()
if os.path.exists(p_win):
    done_w = {round(json.loads(l)["t0"]) for l in open(p_win, encoding="utf-8")}
if a.windows:
    lo, hi = (int(x) for x in a.windows.split(","))
    windows = windows[lo:hi]
groups = [windows[i : i + 3] for i in range(0, len(windows), 3)]
groups = [g for g in groups if any(round(w["t0"]) not in done_w for w in g)]
if a.limit_groups:
    groups = groups[: a.limit_groups]
print(f"window groups to do: {len(groups)}", flush=True)


def group_request(g):
    g0, g1 = g[0]["t0"], g[-1]["t1"]
    c0, c1 = max(0.0, g0 - 2), min(dur, g1 + 2)
    ep = next((e for e in outl["episodes"] if e["t0"] <= g0 < e["t1"]), outl["episodes"][-1])
    lines = [f"窗口 {k}：短视频第 {w['t0'] - c0:.0f}–{w['t1'] - c0:.0f} 秒。自动上下文（可能有错）：{w['context_text']}" for k, w in enumerate(g)]
    fixed = (KNOW + f"\n\n## 段落提纲（段落内秒数；段落第 0 秒 = 录像第 {ep['t0']:.0f} 秒，区域 {ep.get('zone') or '未知'}）\n"
             + json.dumps(ep["outline"], ensure_ascii=False))
    per = f"\n\n这段短视频的第 0 秒 = 段落内第 {c0 - ep['t0']:.0f} 秒。\n" + "\n".join(lines) + "\n\n请观看短视频并输出 JSON。"
    return request(f, c0, c1, a.fps, WINDOW_SYS, (fixed, per), True, round(g0)), ep


n_done = 0
t_start = time.time()
rq_group = {}
rqs = []
for g in groups:
    rq, ep = group_request(g)
    rq_group[rq["key"]] = (g, ep)
    rqs.append(rq)
fh = open(p_win, "a", encoding="utf-8")


def on_group(key, data):
    global n_done
    g, ep = rq_group[key]
    wins = data if isinstance(data, list) else data.get("windows", []) if isinstance(data, dict) else []   # the model sometimes returns the bare list
    got = {int(x.get("id", -1)): x for x in wins if isinstance(x, dict) and str(x.get("id", "")).lstrip("-").isdigit()}
    for k, w in enumerate(g):
        x = got.get(k)
        if x is None:
            continue
        fh.write(json.dumps({"session": S, "t0": w["t0"], "t1": w["t1"], "episode_t0": ep["t0"], "model": a.model, "scene": x.get("scene", ""),
                             "text": x.get("text", ""), "inferred": x.get("inferred", []), "state": x.get("state", {}),
                             "context_conflicts": x.get("context_conflicts", [])}, ensure_ascii=False) + "\n")
    fh.flush()
    n_done += 1
    if n_done % 10 == 0 or n_done == len(groups):
        save_usage()
        print(f"  {n_done}/{len(groups)} groups, {(time.time() - t_start) / 60:.1f} min, est. ${cost():.2f} "
              f"(tokens in {usage['prompt']}, cached {usage.get('cached', 0)}, out {usage['output']}, thoughts {usage['thoughts']})", flush=True)


run_stage("windows", rqs, on_group)
fh.close()
save_usage()
try:
    client.files.delete(name=f.name)
except Exception:
    pass
nrows = sum(1 for _ in open(p_win, encoding="utf-8"))
print(f"{S}: {nrows}/{len(windows)} windows labelled; estimated ${cost():.2f} at the assumed prices -> {p_win}")
