# poe2-watch 录制工具

录制协议见平台仓库 `docs/research/watching-survey-2026-10-02.zh-CN.md` 第 8 节。

## 一次性配置 rclone → Cloudflare R2（owner 自己填密钥）

1. Cloudflare 面板 → R2 → Manage R2 API Tokens → Create API Token：权限 Object Read & Write，限定 bucket `vision-model`。
   记下 Access Key ID、Secret Access Key，以及面板右侧的 Account ID。
2. 在 PowerShell 里运行（把三个大写占位符换掉；密钥只存在本机 %APPDATA%\rclone\rclone.conf）：

```powershell
rclone config create r2 s3 provider=Cloudflare access_key_id=ACCESS_KEY_ID secret_access_key=SECRET_ACCESS_KEY endpoint=https://ACCOUNT_ID.r2.cloudflarestorage.com acl=private no_check_bucket=true
rclone lsd r2:vision-model
```

第二条不报错就配好了（空桶也不报错）。

## 每次录制

1. OBS 用 profile `poe2`：Ctrl+F10 开始，鼠标后退侧键（Mouse 4）标「我会在这里说一句」，Ctrl+F11 停止。
2. 复制 `session_template.json` 为 `C:\Users\Leo12\Videos\poe2-raw\poe2_<日期>_<时分>.json`，填 content / patch / notes。
3. `python export_chapters.py C:\Users\Leo12\Videos\poe2-raw` 为每段录像生成 <录像名>.marks.csv。
4. `powershell -File upload_session.ps1` 上传并校验，成功后自动删本地；加 `-KeepLocal` 则保留。

桶内路径：`vision-model/poe2-raw/`。

## 处理一场录像（watch/ 目录，环境 `.venv`，首次 `python -m uv sync`）

```powershell
rclone copy r2:vision-model/poe2-raw C:/Users/Leo12/Videos/poe2-work/raw --include "poe2_<会话>.*"
.venv/Scripts/python watch/extract_frames.py C:/Users/Leo12/Videos/poe2-work/raw/poe2_<会话>.mp4
.venv/Scripts/python watch/extract_features.py C:/Users/Leo12/Videos/poe2-work/frames/poe2_<会话>
.venv/Scripts/python watch/signals.py poe2_<会话>
```

产物：`poe2-work/frames/<会话>/`（4 fps、短边 384 的 JPEG）、`poe2-work/features/<会话>.vjepa2.npz`（V-JEPA 2 ViT-L 池化特征，每秒一条）、
`poe2-work/results/<会话>.signals.md`（三类信号对标记的 AP / AUROC / 预算命中率）。特征和结果另复制到 `r2:vision-model/features/` 与 `results/`。

实测（2026-10-03，RTX 4060 Laptop）：16 帧 256² 的片段 164 ms/片，约 6 倍实时，显存峰值 1.2 GB；64 帧片段 1.18 s/片。

## 标签分层（2026-10-03 决定）

预测器自监督训练，不需要标签；标签只用于评测，分四层：
1. **客观事件**（自动、密集）：`watch/events_from_log.py <会话>` 从游戏自己的 `Client.txt` 取区域切换、读图结束、死亡、升级、NPC/Boss 台词、密语与聊天（只记类型不记内容）、失焦/聚焦，按录像文件名的时间对齐，输出 `<会话>.events.csv` 与 `<会话>.clientlog.txt`。
   `watch/audio_events.py <会话>` 在游戏音轨上检出声音起点，用 CLAP 音频嵌入做层次聚类（v2，2026-10-03；v1 的梅尔指纹 + KMeans 把不同声音混在一起），导出每簇示例 `poe2-work/audio_clusters/<会话>/c<k>_*.wav`；owner 听一次后在同目录写 `labels.txt`（`3: alert sound 3`），簇号就成了掉落/升级等事件标签。
2. **玩家实时标记**：鼠标后退键，稀疏也好，只在真想说时按。
3. **事后旁观标注**：累积约 5 小时后，挑 1–2 小时不玩只看，按「她会不会说一句」标；绝对判断难时改成成对比较。
4. **朋友共看**：有机会再做。

`watch/signals.py` 现在对 marks、events_vis（读图结束 + 死亡 + 升级）、events_zone（读图结束）三组标签分别出表。

### 过滤器提示音的精确检测（模板匹配）

聚类只能粗分。要精确找过滤器提示音，给两三个真实出现的时间点即可：在 `templates.txt` 里一行一个 `<名字> <会话> <秒>`，例如
`alert3 poe2_2026-10-03_024617 1013.5`，然后

```powershell
.venv/Scripts/python watch/audio_events.py poe2_<会话> --templates templates.txt
```

输出 `<会话>.alerts.csv`（时间、名字、相似度），阈值 `--match-thresh 0.8` 可调。

## 待实现：按需变化的更新率（owner 2026-10-04 要求）
状态更新率不定死在 1 Hz：PoE2 状态 1 Hz、帧 4 fps；Apex 交战时状态约 4 Hz、帧 8–15 fps；现实世界状态约 2 Hz、帧 8 fps。
状态变化升高时自动提到 4 Hz，平静后降回；另设一条不经语言模型的快反应路径（<500 ms）。合训预测器时一并实现。

## HUD 读取与提示音（2026-10-05）

- `watch/hud_extract.py <录像.mp4>`：从 1920×1200 原片每秒切出四块 HUD 拼成一张小图（生命/护盾/Ward 数值、法力/Spirit 数值、顶部 Boss 或精英名条、右侧地图目标），之后读 HUD 不再需要原片。
- `watch/hud_read.py <会话>`：固定位置的识别式 OCR（RapidOCR，CPU，约 0.5 s 处理 1 s 录像）读数值；用红色检出顶部名条并区分 boss / elite、估血条比例；目标面板每 5 s 读一次。
  输出 `<会话>.hud.csv` 与 `<会话>.hud_events.csv`：life_drop、low_life、life_recovered、death、boss_appear、boss_gone、boss_hp_low、elite_appear、map_completed、objective_changed。
- 提示音检测（2026-10-05 定型）：FilterBlade 的预览音频与游戏内实际声音不符（最高相似度 0.5），作废。owner 的校准录像（藏身处逐个丢物品）给出真实模板，放在 `alert_sounds/ingame/templates/`：alertA（Exalted / Chaos / Uncut Gem 同一个声音）、alertB（Breach / Delirium Tablet）、divine、waystone15、logbook、splinter_breach、splinter_simulacrum、belt；`ui/` 是拾取与悬停等界面音。
  `watch/alert_match.py` 的模板相关法在真实战斗音里只找回 40% 的注入样本，保留作对照。
  **正式检测器是 `watch/alert_cnn.py`**：把模板随机混进各场游戏音轨训练的小 CNN，按场次留出。`train` 后 `detect <会话>` 输出 `<会话>.alerts.csv`。留出场次上：原音量召回 99%、半音量 88%、四分之一音量 62%；对界面音与倒放提示音误触发 0.2%。四场共检出 16 次，其中 13 次由画面上新出现的物品标签证实（Exalted Orb、Chaos Orb、Divine Orb、Breach Splinter、Delirium / Ritual Tablet 等）。
  新增一种提示音时：再录一段校准、把片段放进 templates、重新 `train`。
- `watch/mark_context.py`：列出每个标记前后 8 s / 3 s 内的日志事件、HUD 事件、提示音，并给出各类线索相对随机的提升倍数。
- 每场的游戏音轨与麦克风音轨另存为 `poe2-work/audio/<会话>.game.flac` / `.mic.flac`。

## 实时的"眼睛"（2026-10-08，云端）

`pod/live/`：`serve.sh`（机器上的启动脚本）、`live.py`（三个循环 + HTTP）、`merge_lora.py`（把 LoRA 合并进底座给 vLLM）、`mediamtx.yml`（收流）。
开机：`python watch/runpod_ctl.py create eyes-live-pt <serve_pt.sh 的限时链接> --ports "8888/http,8000/http,8002/http,1935/tcp,22/tcp" --gpu "NVIDIA GeForce RTX 5090" --gpu "NVIDIA GeForce RTX 4090"`，
然后 `runpod_ctl.py get <id>` 取公网 IP 和 1935 的映射端口；OBS 推 `rtmp://<ip>:<port>/game`。
`/monitor` 看画面、局面、讲解、说话候选；`/state` `/events?since=` `/speak` 给平台用；`/restart` 让机器重新下载 `pod/live.py`（R2 `pod/live.py`）并重启，改脚本不用重开机器。
实测（2026-10-08，4B 合并模型，vLLM CUDA graph）：一次理解 4–6 秒，画面变化大时每 6 秒一次，平静时每 12 秒；HUD 快路径每秒一次，不经模型。
PyTorch 镜像里 8001 端口被占，vLLM 用 8011；vllm/vllm-openai 镜像在 RunPod 上 50 分钟没起来，弃用。
