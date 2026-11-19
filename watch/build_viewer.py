"""Viewer for a labelled session: the video plays and the teacher's narration for the current 5 s window follows it.

Left: the video (the 1280x800 copy in label_src). Right: the outline of the episode the playhead is in, then the three-layer
narration of the current window; below, the list of all windows (click to seek). Each window can be marked right / partly /
wrong with a note; "复制意见" collects the marks as text to paste back into the conversation.

Usage: python watch/build_viewer.py <session>      -> <work>/labels/<session>.viewer.html
"""
import argparse
import json
import os

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("--work", default="C:/Users/Leo12/Videos/poe2-work")
a = ap.parse_args()
S = a.session
LD = os.path.join(a.work, "labels")
vp = os.path.join(LD, f"{S}.validated.jsonl")
src = vp if os.path.exists(vp) else os.path.join(LD, f"{S}.windows.jsonl")
wins = sorted((json.loads(l) for l in open(src, encoding="utf-8")), key=lambda r: r["t0"])
outl = json.load(open(os.path.join(LD, f"{S}.outlines.json"), encoding="utf-8"))
data = {"session": S, "windows": [{k: w.get(k) for k in ("t0", "t1", "scene", "text", "inferred", "state", "context_conflicts", "review")} for w in wins],
        "episodes": [{"t0": e["t0"], "t1": e["t1"], "zone": e.get("zone"), "outline": e["outline"]} for e in outl["episodes"]]}
blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

CSS = """
:root{--bg:#f6f5f1;--fg:#1d1c19;--mut:#6b6860;--card:#fff;--line:#dedbd2;--acc:#2f5d8a;--warn:#8a4b12;--hl:#e7eef6}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ebe8e0;--mut:#a09c92;--card:#22201d;--line:#3a3732;--acc:#8ab4dc;--warn:#e0a96a;--hl:#243240}}
*{box-sizing:border-box} body{background:var(--bg);color:var(--fg);font:14.5px/1.65 system-ui,"Microsoft YaHei",sans-serif;margin:0;padding:14px 16px 70px}
main{max-width:1600px;margin:0 auto} h1{font-size:19px;margin:0 0 10px} h3{font-size:13px;margin:0 0 6px;color:var(--acc)}
.row{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:16px;align-items:start}
.left{position:sticky;top:8px} video{width:100%;border-radius:6px;background:#000}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin-bottom:10px} .card p{margin:4px 0} .card ul{margin:2px 0 4px 18px;padding:0}
.mut{color:var(--mut);font-size:12.5px} .warn{color:var(--warn);font-size:13px}
details summary{cursor:pointer;color:var(--acc);font-size:13px} table{border-collapse:collapse;width:100%;font-size:13px} td{border-top:1px solid var(--line);padding:4px 6px;vertical-align:top} td:first-child{white-space:nowrap;color:var(--acc)}
.list{max-height:46vh;overflow:auto;border:1px solid var(--line);border-radius:6px;background:var(--card)}
.item{padding:5px 10px;border-top:1px solid var(--line);cursor:pointer;font-size:13px;display:flex;gap:8px} .item:first-child{border-top:0} .item.cur{background:var(--hl)}
.item .tm{color:var(--acc);white-space:nowrap} .item .mk{margin-left:auto;white-space:nowrap}
.judge{display:flex;gap:10px;align-items:center;flex-wrap:wrap;border-top:1px dashed var(--line);padding-top:7px;margin-top:6px}
.judge input[type=text]{flex:1;min-width:160px;font:inherit;padding:3px 7px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg)}
button{font:inherit;color:var(--acc);background:none;border:1px solid var(--line);border-radius:4px;padding:3px 10px;cursor:pointer}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:8px 16px;display:flex;gap:12px;align-items:center;justify-content:center}
textarea{width:100%;height:90px;font:13px/1.5 ui-monospace,Consolas,monospace;margin-top:8px;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:8px}
@media (max-width:900px){.row{grid-template-columns:1fr} .left{position:static}}
"""
JS = r"""
var D = JSON.parse(document.getElementById('data').textContent);
var v = document.getElementById('v'), cur = -1, marks = {};
function mmss(t){t=Math.floor(t);return Math.floor(t/60)+':'+('0'+(t%60)).slice(-2);}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function inferred(x){ if(!x||!x.length) return ''; if(typeof x==='string') return '<p><b>推断</b>　'+esc(x)+'</p>';
  return '<p><b>推断</b></p><ul>'+x.map(function(i){ return (i&&typeof i==='object'&&!Array.isArray(i)) ? '<li>'+esc(i.claim)+' <span class="mut">依据：'+esc(i.basis)+'；把握 '+esc(i.confidence)+'</span></li>' : '<li>'+esc(Array.isArray(i)?i.join(' / '):i)+'</li>'; }).join('')+'</ul>'; }
function showWin(k){ var w=D.windows[k]; if(!w) return; cur=k;
  var st=w.state||{}, cc=(w.context_conflicts||[]).filter(function(c){return c&&c!=='无';});
  var m=marks[k]||{};
  document.getElementById('win').innerHTML='<h3>'+mmss(w.t0)+'–'+mmss(w.t1)+'　第 '+(k+1)+' / '+D.windows.length+' 个窗口</h3>'
    +'<p><b>画面</b>　'+esc(w.scene)+'</p><p><b>界面与文字</b>　'+esc(w.text)+'</p>'+inferred(w.inferred)
    +'<p class="mut">局面：'+esc(st.place)+'；'+esc(st.activity)+'；威胁 '+esc(st.threat)+'</p>'
    +(cc.length?'<p class="warn">老师指出自动信息有误：'+esc(cc.join('；'))+'</p>':'')
    +((w.review&&w.review.length)?'<p class="warn">自动校验对不上的项：'+esc(w.review.join('、'))+'</p>':'')
    +'<div class="judge">'+['对','部分对','错'].map(function(x){return '<label><input type="radio" name="j" value="'+x+'"'+(m.v===x?' checked':'')+' onchange="setMark('+k+',this.value,null)"> '+x+'</label>';}).join('')
    +'<input type="text" placeholder="哪里不对（可不填）" value="'+esc(m.n||'').replace(/"/g,'&quot;')+'" oninput="setMark('+k+',null,this.value)"></div>';
  var its=document.querySelectorAll('.item'); for(var i=0;i<its.length;i++) its[i].classList.toggle('cur', i===k);
  var el=its[k]; if(el){ var box=document.getElementById('list'); if(el.offsetTop<box.scrollTop||el.offsetTop>box.scrollTop+box.clientHeight-40) box.scrollTop=el.offsetTop-80; }
  showEp(w.t0); }
function showEp(t){ var e=null; for(var i=0;i<D.episodes.length;i++){ if(D.episodes[i].t0<=t+0.01 && t<D.episodes[i].t1) e=D.episodes[i]; }
  if(!e||e===showEp.last) return; showEp.last=e; var o=e.outline||{};
  var ph=(o.phases||[]).map(function(p){return '<tr><td>'+mmss(e.t0+p.t0)+'–'+mmss(e.t0+p.t1)+'</td><td>'+esc(p.what)+'</td><td class="mut">'+esc(p.situation)+'</td></tr>';}).join('');
  var ev=(o.events||[]).map(function(x){return '<li><b>'+mmss(e.t0+Number(x.t))+'</b>　'+esc(x.what)+'</li>';}).join('');
  var ca=(o.causes||[]).map(function(c){return '<li><b>'+esc(c.outcome)+'</b>（'+esc(c.confidence)+'）'+esc(c.explanation)+'</li>';}).join('');
  var pp=(o.player_pattern||[]).map(function(x){return '<li>'+esc(x)+'</li>';}).join('');
  document.getElementById('ep').innerHTML='<h3>所在段落：'+mmss(e.t0)+'–'+mmss(e.t1)+'　'+esc(e.zone||'')+'</h3><table>'+ph+'</table>'
    +'<details><summary>事件 '+(o.events||[]).length+' 条</summary><ul>'+ev+'</ul></details>'
    +(ca?'<details open><summary>因果</summary><ul>'+ca+'</ul></details>':'')
    +(pp?'<details><summary>反复出现的做法</summary><ul>'+pp+'</ul></details>':''); }
function setMark(k,val,note){ var m=marks[k]||{}; if(val!==null) m.v=val; if(note!==null) m.n=note; marks[k]=m;
  var mk=document.querySelectorAll('.item .mk')[k]; if(mk) mk.textContent=m.v||(m.n?'有批注':'');
  document.getElementById('count').textContent='已判 '+Object.keys(marks).length+' 个'; }
function seekWin(k){ v.currentTime=D.windows[k].t0+0.05; showWin(k); }
function collect(){ var NL=String.fromCharCode(10), lines=[D.session];
  Object.keys(marks).sort(function(a,b){return a-b;}).forEach(function(k){ var w=D.windows[k], m=marks[k]; lines.push(mmss(w.t0)+'：'+(m.v||'未选')+(m.n?'；'+m.n:'')); });
  var o=document.getElementById('overall').value.trim(); if(o) lines.push('总体：'+o);
  var t=lines.join(NL), out=document.getElementById('out'); out.value=t; out.select(); try{navigator.clipboard.writeText(t)}catch(e){document.execCommand('copy')} }
document.getElementById('list').innerHTML=D.windows.map(function(w,k){ var st=w.state||{};
  return '<div class="item" onclick="seekWin('+k+')"><span class="tm">'+mmss(w.t0)+'</span><span>'+esc(st.activity||'')+'</span><span class="mk'+((w.review&&w.review.length)?' warn':'')+'">'+((w.review&&w.review.length)?'待核':'')+'</span></div>'; }).join('');
v.addEventListener('timeupdate',function(){ var t=v.currentTime, k=-1; for(var i=0;i<D.windows.length;i++){ if(D.windows[i].t0<=t && t<D.windows[i].t1){k=i;break;} } if(k>=0&&k!==cur) showWin(k); });
showWin(0);
"""
page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>讲解浏览</title><style>' + CSS
        + "</style></head><body><main><h1>" + S + "：" + str(len(wins)) + ' 个窗口的讲解（视频播到哪，右边跟到哪）</h1><div class="row"><div class="left">'
        + '<video id="v" src="../label_src/' + S + '.mp4" controls preload="metadata"></video><div class="card" id="ep" style="margin-top:10px"></div></div>'
        + '<div><div class="card" id="win"></div><div class="list" id="list"></div>'
        + '<textarea id="overall" placeholder="总体意见"></textarea><textarea id="out" readonly placeholder="点底部按钮后，意见会出现在这里并进剪贴板"></textarea></div></div></main>'
        + '<div class="bar"><span id="count">已判 0 个</span><button type="button" onclick="collect()">复制意见</button></div>'
        + '<script id="data" type="application/json">' + blob + "</script><script>" + JS + "</script></body></html>")
out = os.path.join(LD, f"{S}.viewer.html")
open(out, "w", encoding="utf-8", newline="\n").write(page)
print(out, len(page) // 1024, "KB,", len(wins), "windows,", len(outl["episodes"]), "episodes")
