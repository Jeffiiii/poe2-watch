"""Build the review page for the teacher pilot: each clip next to every teacher's narration of its three windows.

Columns per window: the first pilot narration (with the owner's verdict), the dense re-narration where it exists, and the
video-native teachers. The two Gemini models are shown blind as "老师 A" / "老师 B" (assignment shuffled per run with a
fixed seed and stored in review_key.json) so the owner judges the text, not the name.

Usage: python watch/build_review.py [--work C:/Users/Leo12/Videos/poe2-work]
"""
import argparse
import html
import json
import os
import random

ap = argparse.ArgumentParser()
ap.add_argument("--work", default="C:/Users/Leo12/Videos/poe2-work")
ap.add_argument("--models", default="gemini-3.1-pro-preview,gemini-3.8-flash")
a = ap.parse_args()
P = os.path.join(a.work, "teacher_pilot")
e = html.escape
pilot = json.load(open(os.path.join(P, "pilot_teacher_claude.json"), encoding="utf-8"))
models = a.models.split(",")
gem = {}
for m in models:
    p = os.path.join(P, "gemini_" + m + ".json")
    if os.path.exists(p):
        gem[m] = json.load(open(p, encoding="utf-8"))
RUNS = {"r1": "后期地图：掉落、被秒、回藏身处", "r2": "Olroth Boss 战", "r3": "Breach 与 Strongbox", "r4": "Crypt 地图沿 Abyss 清怪",
        "r5": "藏身处整理与鉴定", "r6": "新角色：The Bloated Miller", "r7": "新角色：第一次进城交任务", "r8": "新角色：墓地、升级、Lachlann"}
rng = random.Random(20261005)
key = {}


def layers(w):
    if not w:
        return '<p class="mut">（没有输出）</p>'
    out = ['<p><b>画面</b>　' + e(w.get("scene", "")) + "</p>", '<p><b>界面与文字</b>　' + e(w.get("text", "")) + "</p>"]
    inf = w.get("inferred") or []
    if isinstance(inf, str):
        out.append('<p><b>推断</b>　' + e(inf) + "</p>")
    elif inf:
        items = []
        for i in inf:
            if isinstance(i, dict):
                items.append("<li>" + e(str(i.get("claim", ""))) + ' <span class="mut">依据：' + e(str(i.get("basis", ""))) + "；把握 " + e(str(i.get("confidence", ""))) + "</span></li>")
            else:
                items.append("<li>" + e(" / ".join(map(str, i)) if isinstance(i, (list, tuple)) else str(i)) + "</li>")
        out.append("<p><b>推断</b></p><ul>" + "".join(items) + "</ul>")
    st = w.get("state")
    if isinstance(st, dict):
        out.append('<p class="mut">局面：' + e(st.get("place", "")) + "；" + e(st.get("activity", "")) + "；威胁 " + e(st.get("threat", "")) + "</p>")
    cc = [c for c in (w.get("context_conflicts") or []) if c and c != "无"]
    if cc:
        out.append('<p class="warn">它指出自动信息有误：' + e("；".join(cc)) + "</p>")
    if w.get("hook"):
        out.append('<p class="hook">她可能会说：' + e(w["hook"]) + "</p>")
    return "".join(out)


sections = []
for r, title in RUNS.items():
    ws = [w for w in pilot["windows"] if w["id"].startswith(r)]
    order = [m for m in models if m in gem]
    rng.shuffle(order)
    key[r] = {"A": order[0] if order else None, "B": order[1] if len(order) > 1 else None}
    blocks = []
    for k, w in enumerate(ws):
        s0 = 2 + 5 * k
        cards = ['<div class="card old"><h4>第一版（我，每 5 秒 4 帧）· 你的判定：' + e(w.get("owner_verdict", "")) + "</h4><p>" + e(w["narration"]) + "</p>"
                 + ('<p class="note">你的批注：' + e(w["owner_note"]) + "</p>" if w.get("owner_note") else "") + "</div>"]
        if w.get("narration_v2_dense"):
            cards.append('<div class="card"><h4>加密版（我，每 5 秒 12 帧，三层）</h4>' + layers(w["narration_v2_dense"]) + "</div>")
        for lab in ("A", "B"):
            m = key[r][lab]
            if not m:
                continue
            res = gem[m]["runs"].get(r, {}).get("result", {})
            gw = next((x for x in res.get("windows", []) if x.get("id") == w["id"]), None) if isinstance(res, dict) else None
            cards.append('<div class="card"><h4>老师 ' + lab + "（直接看视频）</h4>" + layers(gw) + "</div>")
        blocks.append('<div class="win"><div class="head"><button type="button" onclick="seek(\'' + r + "'," + str(s0) + ')">▶ 片段第 ' + str(s0) + "–" + str(s0 + 5)
                      + ' 秒</button><span class="meta">' + w["id"] + " · 原片 " + str(w["t0"]) + "–" + str(w["t1"]) + " 秒</span></div>" + "".join(cards) + "</div>")
    judge = ('<div class="judge" data-run="' + r + '"><b>这一段谁讲得最好</b> '
             + "".join('<label><input type="radio" name="best_' + r + '" value="' + v + '"> ' + v + "</label> " for v in ("老师 A", "老师 B", "加密版", "第一版", "都不行"))
             + '<input type="text" class="note" placeholder="A、B 各自哪里对、哪里错；还想多看到什么"></div>')
    sections.append("<section><h2>" + e(title) + '</h2><div class="row"><div class="vid"><video id="v_' + r + '" src="clips/' + r + '.mp4" controls preload="metadata"></video>'
                    + judge + '</div><div class="wins">' + "".join(blocks) + "</div></div></section>")

json.dump(key, open(os.path.join(P, "review_key.json"), "w", encoding="utf-8"), indent=1)
CSS = """
:root{--bg:#f6f5f1;--fg:#1d1c19;--mut:#6b6860;--card:#fff;--line:#dedbd2;--acc:#2f5d8a;--warn:#8a4b12;--hook:#3d6b3a;--old:#f0eee8}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ebe8e0;--mut:#a09c92;--card:#22201d;--line:#3a3732;--acc:#8ab4dc;--warn:#e0a96a;--hook:#9ccf97;--old:#1c1b18}}
body{background:var(--bg);color:var(--fg);font:14.5px/1.65 system-ui,"Microsoft YaHei",sans-serif;margin:0;padding:20px 16px 90px}
main{max-width:1500px;margin:0 auto} h1{font-size:22px;margin:0 0 6px} h2{font-size:17px;margin:36px 0 10px} h4{font-size:13px;margin:0 0 6px;color:var(--acc)}
.lead{color:var(--mut);max-width:80ch} .row{display:grid;grid-template-columns:minmax(0,0.9fr) minmax(0,1.3fr);gap:18px;align-items:start}
.vid{position:sticky;top:10px} video{width:100%;border-radius:6px;background:#000}
.win{border-top:2px solid var(--line);padding-top:10px;margin-bottom:16px} .head{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.meta,.mut{color:var(--mut);font-size:12.5px} .card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:9px 12px;margin-bottom:8px}
.card.old{background:var(--old)} .card p{margin:4px 0} .card ul{margin:2px 0 4px 18px;padding:0} .note{color:var(--warn)} .warn{color:var(--warn);font-size:13px} .hook{color:var(--hook);font-size:13px}
button{font:inherit;color:var(--acc);background:none;border:1px solid var(--line);border-radius:4px;padding:2px 9px;cursor:pointer}
.judge{margin-top:10px;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:9px 12px} .judge label{margin-right:8px;white-space:nowrap}
input.note{display:block;width:100%;box-sizing:border-box;margin-top:7px;font:inherit;padding:4px 7px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg)}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;align-items:center;justify-content:center}
.bar button{padding:6px 16px;font-weight:600} textarea{width:100%;box-sizing:border-box;height:130px;font:13px/1.5 ui-monospace,Consolas,monospace;margin-top:10px;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px}
@media (max-width:900px){.row{grid-template-columns:1fr} .vid{position:static}}
"""
JS = """
function seek(r,s){var v=document.getElementById('v_'+r);v.currentTime=s;v.play();clearTimeout(v._t);v._t=setTimeout(function(){v.pause()},5000);}
function tally(){document.getElementById('count').textContent='已选 '+document.querySelectorAll('input[type=radio]:checked').length+' / 8';}
document.addEventListener('change',tally);
function collect(){var NL=String.fromCharCode(10);var lines=[];
  document.querySelectorAll('.judge').forEach(function(j){var c=j.querySelector('input[type=radio]:checked');var n=j.querySelector('.note').value.trim();
    if(c||n)lines.push(j.dataset.run+'：'+(c?c.value:'未选')+(n?'；'+n:''));});
  var o=document.getElementById('overall').value.trim();if(o)lines.push('总体：'+o);
  var t=lines.join(NL)||'（还没有填写）';var out=document.getElementById('out');out.value=t;out.select();
  try{navigator.clipboard.writeText(t)}catch(err){document.execCommand('copy')}}
"""
page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>老师对比</title><style>'
        + CSS + "</style></head><body><main><h1>老师对比：同一段视频，四种讲解</h1>"
        '<p class="lead">每段视频 19 秒，右边按三个 5 秒窗口排列。灰底是第一版和你当时的批注；「加密版」只有 Breach 那一段有；老师 A 和老师 B 是两个直接看视频的模型，'
        "名字先不告诉你，每段的 A、B 顺序是打乱的。每段视频下面选谁讲得最好，写哪里对哪里错。最后点底部按钮复制结果贴回对话。</p>"
        + "".join(sections)
        + '<h2>总体意见</h2><textarea id="overall" placeholder="粒度够不够，画面讲得够不够，还缺什么"></textarea>'
        '<textarea id="out" readonly placeholder="点下面的按钮后，结果会出现在这里并复制到剪贴板"></textarea></main>'
        '<div class="bar"><span id="count">已选 0 / 8</span><button type="button" onclick="collect()">复制全部意见</button></div><script>' + JS + "</script></body></html>")
open(os.path.join(P, "review.html"), "w", encoding="utf-8", newline="\n").write(page)
print("review.html written;", len(page) // 1024, "KB; teachers present:", list(gem))
