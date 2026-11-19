"""Blind side-by-side page for two labellings of the same windows (e.g. 5 fps vs 3 fps). Which side is which is drawn at
random per window; the key goes to <work>/labels/<session>.<tagA>-vs-<tagB>.key.json and is never shown on the page.

Usage: python watch/build_ab.py <session> <tagA> <tagB>   -> <work>/labels/<session>.<tagA>-vs-<tagB>.html
Then: python watch/build_ab.py <session> <tagA> <tagB> --score "0:左 1:右 2:同 ..."  (what the page's copy button gives)
"""
import argparse
import json
import os
import random

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("tagA")
ap.add_argument("tagB")
ap.add_argument("--score", default="")
ap.add_argument("--work", default="C:/Users/Leo12/Videos/poe2-work")
a = ap.parse_args()
S, LD = a.session, os.path.join(a.work, "labels")
name = f"{S}.{a.tagA}-vs-{a.tagB}"
kp = os.path.join(LD, name + ".key.json")


def load(tag):
    return {round(r["t0"]): r for r in map(json.loads, open(os.path.join(LD, f"{S}.{tag}.windows.jsonl"), encoding="utf-8"))}


A, B = load(a.tagA), load(a.tagB)
ts = sorted(set(A) & set(B))
if a.score:
    key = json.load(open(kp))
    won = {a.tagA: 0, a.tagB: 0, "same": 0}
    for tok in a.score.split():
        k, v = tok.split(":")
        left_is_a = key[str(ts[int(k)])]
        won[a.tagA if (v == "左") == left_is_a else a.tagB if v in ("左", "右") else "same"] += 1
    print(won)
    raise SystemExit
rng = random.Random(S + a.tagA + a.tagB)
key = {str(t): rng.random() < 0.5 for t in ts}          # True = A on the left
json.dump(key, open(kp, "w"), indent=1)


def fmt(r):
    inf = r.get("inferred") or []
    inf = "".join(f"<li>{x.get('claim', x) if isinstance(x, dict) else x}" + (f" <span class=mut>（{x.get('basis', '')}，{x.get('confidence', '')}）</span>" if isinstance(x, dict) else "") + "</li>" for x in inf)
    st = r.get("state") or {}
    return (f"<p><b>画面</b> {r.get('scene', '')}</p><p><b>界面与文字</b> {r.get('text', '')}</p>" + (f"<p><b>推断</b></p><ul>{inf}</ul>" if inf else "")
            + f"<p class=mut>局面：{st.get('place', '')}；{st.get('activity', '')}；威胁 {st.get('threat', '')}</p>")


def mmss(t):
    return f"{int(t) // 60}:{int(t) % 60:02d}"


rows = []
for i, t in enumerate(ts):
    l, r = (A[t], B[t]) if key[str(t)] else (B[t], A[t])
    rows.append(f'<section id=w{i}><h3>{mmss(t)}–{mmss(t + 5)}　第 {i + 1} / {len(ts)} 个 <a href="#" onclick="seek({t});return false">▶ 跳到视频</a></h3>'
                f'<div class=two><div class=col>{fmt(l)}</div><div class=col>{fmt(r)}</div></div>'
                f'<div class=judge>' + "".join(f'<label><input type=radio name=j{i} value="{v}" onchange="mark({i},this.value)"> {v}</label>' for v in ("左好", "右好", "差不多")) + "</div></section>")
page = f"""<!doctype html><html lang=zh-CN><head><meta charset=utf-8><title>盲评：{name}</title><style>
body{{font:14.5px/1.6 system-ui,"Microsoft YaHei",sans-serif;margin:0;padding:14px 16px 70px;background:#f6f5f1;color:#1d1c19}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .col{{background:#fff;border:1px solid #dedbd2;border-radius:6px;padding:8px 12px}}
.col p{{margin:4px 0}} .col ul{{margin:2px 0 4px 18px;padding:0}} .mut{{color:#6b6860;font-size:12.5px}} h3{{margin:18px 0 6px;color:#2f5d8a;font-size:14px}}
.judge{{margin:6px 0 0;display:flex;gap:16px}} video{{width:100%;max-width:900px;display:block;border-radius:6px;background:#000}}
.bar{{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid #dedbd2;padding:8px 16px;display:flex;gap:12px;align-items:center}}
button{{font:inherit;padding:3px 10px}} textarea{{flex:1;height:34px;font:12px ui-monospace,Consolas,monospace}}
@media (prefers-color-scheme:dark){{body{{background:#171614;color:#ebe8e0}} .col,.bar{{background:#22201d;border-color:#3a3732}} h3{{color:#8ab4dc}}}}
</style></head><body><h1 style="font-size:18px">同一段录像的两种讲解，左右随机。哪边更准、更有用就选哪边。</h1>
<video id=v src="../label_src/{S}.mp4" controls preload=metadata></video>
{"".join(rows)}
<div class=bar><span id=c>已判 0</span><button onclick="collect()">复制结果</button><textarea id=out readonly></textarea></div>
<script>
var M={{}};function mark(i,v){{M[i]=v;document.getElementById('c').textContent='已判 '+Object.keys(M).length;}}
function seek(t){{var v=document.getElementById('v');v.currentTime=t;v.play();window.scrollTo(0,0);}}
function collect(){{var s=Object.keys(M).sort(function(a,b){{return a-b}}).map(function(k){{return k+':'+M[k].replace('好','').replace('差不多','同')}}).join(' ');var o=document.getElementById('out');o.value=s;o.select();try{{navigator.clipboard.writeText(s)}}catch(e){{document.execCommand('copy')}}}}
</script></body></html>"""
out = os.path.join(LD, name + ".html")
open(out, "w", encoding="utf-8", newline="\n").write(page)
print(out, len(ts), "windows; key in", kp)
