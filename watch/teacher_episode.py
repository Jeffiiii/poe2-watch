"""Two-pass teacher: first understand the whole episode, then narrate short windows inside it.

The owner's verdict on the first bake-off: cutting the video into 15 s pieces loses the overall situation. So

  pass 1 (outline)  the model watches a long episode clip (minutes; --outline-fps, default media resolution) and writes a
                    timeline: phases, what the player was doing and why it matters, notable events with timestamps, the
                    causes of the outcomes (e.g. what actually killed the player).
  pass 2 (windows)  for a short clip inside the episode (5 fps, high resolution) the model writes the three-layer narration,
                    now with the outline, the character card and the general mechanics notes as context.

Usage:
  python watch/teacher_episode.py --episode <episode.mp4> --episode-start 0 \
      --clip <clip.mp4> --clip-start 153 --windows r1w1,r1w2,r1w3 --card GSMZZG [--model gemini-3.8-flash]
Times are seconds in the original recording. Output: <work>/teacher_pilot/episode_<name>.json
"""
import argparse
import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

ap = argparse.ArgumentParser()
ap.add_argument("--episode", required=True)
ap.add_argument("--episode-start", type=float, default=0)
ap.add_argument("--clip", required=True)
ap.add_argument("--clip-start", type=float, required=True, help="recording time of the clip's first frame")
ap.add_argument("--windows", required=True)
ap.add_argument("--card", default="GSMZZG")
ap.add_argument("--model", default="gemini-3.8-flash")
ap.add_argument("--outline-fps", type=float, default=2)
ap.add_argument("--fps", type=float, default=5)
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--root", default=r"C:/Users/Leo12/Documents/poe2-watch")
a = ap.parse_args()
load_dotenv(os.path.join(a.root, ".env"))
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
card = open(os.path.join(a.root, "build_cards", a.card + ".md"), encoding="utf-8").read()
mech = open(os.path.join(a.root, "knowledge", "poe2_mechanics.md"), encoding="utf-8").read()


def upload(path):
    f = client.files.upload(file=path)
    for _ in range(150):
        f = client.files.get(name=f.name)
        if getattr(f.state, "name", str(f.state)) == "ACTIVE":
            return f
        time.sleep(2)
    raise RuntimeError("file never became ACTIVE: " + path)


def ask(f, fps, system, user, high):
    cfg = types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", temperature=0.2,
                                      media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH if high else None)
    t0 = time.time()
    r = client.models.generate_content(model=a.model, config=cfg, contents=[types.Content(role="user", parts=[
        types.Part(file_data=types.FileData(file_uri=f.uri, mime_type="video/mp4"), video_metadata=types.VideoMetadata(fps=fps)),
        types.Part(text=user)])])
    um = r.usage_metadata
    try:
        data = json.loads(r.text)
    except Exception as e:
        data = {"error": str(e), "raw": (r.text or "")[:3000]}
    return data, {"seconds": round(time.time() - t0, 1), "prompt": um.prompt_token_count, "output": um.candidates_token_count,
                  "thoughts": getattr(um, "thoughts_token_count", None)}


KNOW = "## 角色卡\n" + card + "\n\n## 通用机制笔记\n" + mech

OUTLINE_SYS = """你是一位精通 Path of Exile 2 的解说老师。你将看到一段几分钟长的连续游戏录像（一个「段落」，例如一张地图从进入到离开）。
请先通读全段，再写出这段的提纲，目的是让之后逐段细讲的人知道每一刻处在什么局面里。全部用中文，游戏专有名词保留英文。时间用视频内的秒数。

要求：
- phases：把全段切成若干阶段（跑图、某个玩法内容、Boss 战、拾取、回城整理等），每个给出起止秒数、在做什么、局面如何。
- events：值得记住的事件，按时间排列，每个给出秒数、发生了什么、依据（画面上看到了什么）。包括：稀有怪或 Boss 的出现与死亡及其名条下的词缀、值钱的掉落、玩家资源的大幅变化、危险时刻、死亡、换区。
- causes：对结果的因果解释。如果玩家死了或险些死了，必须结合角色卡和机制笔记说明是什么造成的，并指出画面证据；说不清就写不确定。
- player_pattern：这段里玩家反复出现的做法（例如先铺什么再打、什么东西不捡）。只写画面上能看到的重复行为，不要猜动机。

意图只能作为推断并注明把握。没有依据的不要写。只输出 JSON：
{"phases":[{"t0":0,"t1":0,"what":"...","situation":"..."}],"events":[{"t":0,"what":"...","evidence":"..."}],"causes":[{"outcome":"...","explanation":"...","evidence":"...","confidence":"高|中|低"}],"player_pattern":["..."]}"""

WINDOW_SYS = """你是一位精通 Path of Exile 2 的解说老师，正在为一小段录像写「扎根的讲解」，用来训练一个只看画面的模型，所以每一句都必须能在视频里找到依据。
你已经看过这段录像所属的整个段落，段落提纲会给你；请用它来判断此刻处在什么局面，但逐窗口的描述必须来自这段短视频本身。

短视频里：第 0–2 秒是引子，随后三个连续的 5 秒窗口（第 2–7、7–12、12–17 秒），最后 2 秒是尾巴。只为三个窗口写讲解。全部用中文，游戏专有名词保留英文。

每个窗口三层：
1. scene（画面）：游戏画面本身发生了什么，按时间先后，这一层最详细。地形；玩家在哪、往哪走、做了什么；有哪些怪、大约几只、在什么方位、被什么打、死没死；地面效果和技能特效各是什么颜色形状、是谁放的；伤害来自哪里；掉落物从哪出现、哪些被捡（标签消失且玩家在旁）、哪些没捡。看不清就说看不清。不要在这一层复述 HUD 数字。
2. text（界面与文字）：屏幕上的文字和读数及其变化。HUD 数值；顶部名条的名字、血条比例和**名条下的词缀小字**；掉落物标签；左下角台词与系统消息；目标面板；打开的界面与弹出的说明框。只写确实看到的。
3. inferred（推断）：画面没有直接写出、但能由画面加角色卡、机制笔记或段落提纲推出的东西：机制解释（尤其是怪物词缀或地面效果对这个角色意味着什么）、局面判断、玩家可能的意图。每条给出 basis（画面 / 角色卡 / 机制笔记 / 段落提纲 / 游戏知识）和 confidence（高 / 中 / 低）。玩家意图永远只能是推断。来自游戏知识而非画面的判断必须注明。

另外每个窗口给出 state（place、activity、threat 及其依据的读数；对这个角色威胁要按角色卡的规则判断）和 context_conflicts（提纲或角色卡与这段视频不一致的地方，没有就空数组）。

只输出 JSON：{"windows":[{"id":"...","scene":"...","text":"...","inferred":[{"claim":"...","basis":"...","confidence":"..."}],"state":{"place":"...","activity":"...","threat":"..."},"context_conflicts":[]}]}"""

out = {"model": a.model, "episode": os.path.basename(a.episode), "clip": os.path.basename(a.clip)}
fe = upload(a.episode)
outline, u1 = ask(fe, a.outline_fps, OUTLINE_SYS, KNOW + "\n\n请观看整段视频并输出提纲 JSON。", high=False)
out["outline"], out["outline_usage"] = outline, u1
print("outline:", u1, flush=True)
off = a.clip_start - a.episode_start
wid = a.windows.split(",")
user = (KNOW + "\n\n## 段落提纲（时间为段落视频内的秒数）\n" + json.dumps(outline, ensure_ascii=False)
        + f"\n\n这段短视频的第 0 秒对应段落视频的第 {off:.0f} 秒。三个窗口的 id 依次为 {', '.join(wid)}。请观看短视频并输出 JSON。")
fc = upload(a.clip)
wins, u2 = ask(fc, a.fps, WINDOW_SYS, user, high=True)
out["windows"], out["window_usage"] = wins, u2
print("windows:", u2, flush=True)
for f in (fe, fc):
    try:
        client.files.delete(name=f.name)
    except Exception:
        pass
name = os.path.splitext(os.path.basename(a.clip))[0]
p = os.path.join(a.work, "teacher_pilot", f"episode_{name}_{a.model}.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", p)
