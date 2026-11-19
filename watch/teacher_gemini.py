"""Teacher narration with a video-native model (Gemini), for the pilot runs.

For each pilot run (a 19 s clip = 2 s lead-in + three 5 s windows + 2 s tail) the model gets
  - the clip itself (uploaded, sampled at --fps, high media resolution),
  - the character card (mechanics and habits; build_cards/<character>.md) when there is one,
  - the automatically extracted context for each window (HUD numbers, log events, alert sounds), flagged as fallible,
and must return, per window, three layers: what is on screen in the play area, what the on-screen text says, and what
can be inferred, each inference with its basis and confidence. Intent may never be stated as fact.

Output: <work>/teacher_pilot/gemini_<model>.json

Usage: python watch/teacher_gemini.py --model gemini-3.1-pro-preview [--runs r1,r2] [--fps 5]
The API key is read from poe2-watch/.env (GEMINI_API_KEY); it is never printed.
"""
import argparse
import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="gemini-3.1-pro-preview")
ap.add_argument("--runs", default="r1,r2,r3,r4,r5,r6,r7,r8")
ap.add_argument("--fps", type=float, default=5)
ap.add_argument("--work", default=r"C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--root", default=r"C:/Users/Leo12/Documents/poe2-watch")
a = ap.parse_args()
load_dotenv(os.path.join(a.root, ".env"))
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
P = os.path.join(a.work, "teacher_pilot")
windows = json.load(open(os.path.join(P, "pilot_windows.json"), encoding="utf-8"))

CARDS = {"GSMZZG": "GSMZZG.md"}
MONK = ("角色 GGSMZZHCSSF，Monk，Solo Self-Found Hardcore（硬核：死亡即角色终结），这一场从 1 级打到 13 级，第一幕剧情。"
        "没有角色卡；不要假设它有任何特殊天赋。")

SYSTEM = """你是一位精通 Path of Exile 2 的解说老师，正在为一段游戏录像写「扎根的讲解」。这些讲解将用来训练一个只看画面的模型，所以每一句都必须能在视频里找到依据。

视频是一段 19 秒的片段：第 0–2 秒是引子，随后是三个连续的 5 秒窗口（第 2–7 秒、7–12 秒、12–17 秒），最后 2 秒是尾巴。只为这三个窗口写讲解，但可以用引子和尾巴帮助理解前因后果。

每个窗口写三层，全部用中文，游戏专有名词保留英文原文：

1. scene（画面）：游戏画面本身发生了什么。地形与场景；玩家角色在哪、往哪移动、做了什么动作；有哪些怪、大约几只、在什么方位、被什么打、死没死；有哪些技能特效和地面效果、是谁放的；掉落物从哪里出现、被没被捡。按时间先后写，这一层要最详细。不要在这一层复述 HUD 数字。
2. text（界面与文字）：屏幕上出现的文字和读数。HUD 的生命、法力、Spirit 等数值及其变化；顶部名条的名字和血条比例；掉落物标签；聊天栏与系统消息；任务或地图目标；打开的界面和悬停出现的说明框。只写确实看到的。
3. inferred（推断）：从画面和角色卡能推出、但画面上没有直接写出来的东西：机制层面的解释、局面判断、玩家可能的意图。每一条必须给出 basis（依据：画面 / 角色卡 / 自动上下文）和 confidence（高 / 中 / 低）。**玩家的意图永远只能作为推断，不能写成事实。** 鼠标划过物品标签时会自动弹出说明框，这不等于玩家在阅读它。没有依据就不要写。

另外每个窗口给出：
- state：place（在哪）、activity（在做什么）、threat（威胁：无 / 低 / 中 / 高，并说明依据的是哪个读数）。
- context_conflicts：自动上下文与视频不一致的地方。自动上下文是程序从 HUD、日志和声音里提取的，**可能有错**；与视频冲突时以视频为准，并在这里指出。
- hook：一位坐在旁边看的同伴此刻可能会说的点，一句话；没有值得说的就留空字符串。

只输出 JSON，结构为：
{"windows":[{"id":"...","scene":"...","text":"...","inferred":[{"claim":"...","basis":"...","confidence":"高|中|低"}],"state":{"place":"...","activity":"...","threat":"..."},"context_conflicts":["..."],"hook":"..."}]}"""


def wait_active(f):
    for _ in range(60):
        f = client.files.get(name=f.name)
        if getattr(f.state, "name", str(f.state)) == "ACTIVE":
            return f
        time.sleep(2)
    raise RuntimeError("file never became ACTIVE")


out = {"model": a.model, "fps": a.fps, "runs": {}}
for r in a.runs.split(","):
    ws = [w for w in windows if w["id"].startswith(r)]
    char = "GSMZZG" if "GSMZZG (" in ws[0]["context_text"] else "GGSMZZHCSSF"
    card = open(os.path.join(a.root, "build_cards", CARDS[char]), encoding="utf-8").read() if char in CARDS else MONK
    ctx = "\n".join(f"[{w['id']}，片段第 {2 + 5 * k}–{7 + 5 * k} 秒，原片 {w['t0']:.0f}–{w['t1']:.0f} 秒] {w['context_text']}" for k, w in enumerate(ws))
    user = (f"## 角色卡\n{card}\n\n## 三个窗口的自动上下文（可能有错）\n{ctx}\n\n"
            f"窗口 id 依次为 {', '.join(w['id'] for w in ws)}。请观看视频并按要求输出 JSON。")
    f = wait_active(client.files.upload(file=os.path.join(P, "clips", f"{r}.mp4")))
    t0 = time.time()
    resp = client.models.generate_content(
        model=a.model,
        contents=[types.Content(role="user", parts=[
            types.Part(file_data=types.FileData(file_uri=f.uri, mime_type="video/mp4"), video_metadata=types.VideoMetadata(fps=a.fps)),
            types.Part(text=user)])],
        config=types.GenerateContentConfig(system_instruction=SYSTEM, response_mime_type="application/json", temperature=0.2,
                                           media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH))
    dt = time.time() - t0
    um = resp.usage_metadata
    try:
        data = json.loads(resp.text)
    except Exception as e:
        data = {"error": str(e), "raw": (resp.text or "")[:2000]}
    out["runs"][r] = {"result": data, "seconds": round(dt, 1), "character": char,
                      "tokens": {"prompt": um.prompt_token_count, "output": um.candidates_token_count, "thoughts": getattr(um, "thoughts_token_count", None),
                                 "total": um.total_token_count}}
    print(f"{r}: {dt:.0f} s, tokens in {um.prompt_token_count} out {um.candidates_token_count} thoughts {getattr(um, 'thoughts_token_count', None)}; "
          f"windows {len(data.get('windows', [])) if isinstance(data, dict) else '?'}", flush=True)
    try:
        client.files.delete(name=f.name)
    except Exception:
        pass
    json.dump(out, open(os.path.join(P, f"gemini_{a.model}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", os.path.join(P, f"gemini_{a.model}.json"))
