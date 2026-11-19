# poe2-watch

给 AI 角色做一双"眼睛"：让一个小的本地视觉语言模型持续看游戏画面，知道此刻在哪、在发生什么、危险不危险。做法是**特权信息蒸馏**——离线的大模型老师带着游戏日志和 HUD 读数讲解录像，小模型学生只看像素学着讲。第一个游戏是 Path of Exile 2。

*A small vision-language model that watches gameplay in real time, distilled from a large teacher that narrates recordings with privileged context (game log, HUD readings, episode outlines). First game: Path of Exile 2.*

状态：2026-10-09 起训练线暂停，以下是到那时为止的方法、结果和代码。

## 方法

```
录像 (OBS, 1920×1200@30)
  ├─ 游戏日志 Client.txt ──→ 区域切换、死亡、升级              watch/events_from_log.py
  ├─ HUD 区域每秒一帧 ────→ OCR 读生命/法力/Spirit、名条、目标   watch/hud_extract.py, hud_read.py, hud_clean.py
  └─ 游戏音轨 ───────────→ 掉落提示音检测（小 CNN）             watch/alert_cnn.py
        │
        ▼  每 5 秒一个窗口的"特权上下文"                         watch/build_context.py
老师 (Gemini 3.8 Flash, 批量模式)                               watch/label_session.py
  先通读整段写提纲，再对每个窗口写三层讲解：
  scene 画面 / text 界面与读数 / inferred 推断（带依据和把握）+ state（在哪、在做什么、威胁）
        │
        ├─ 校验：老师的话和日志、HUD 读数对不上的窗口剔除        watch/validate_labels.py
        └─ 自动考题：答案来自日志和读数器，不来自任何模型        watch/make_qa.py
        ▼
学生 (Qwen3-VL-4B / 8B + LoRA)：每窗口 4 帧 → 讲解或答题        watch/build_dataset.py, pod/train_lora.py, pod/infer.py
        ▼
实时：收流 → 感知(2 fps + 每秒 HUD 快路径) → 理解(6–12 秒一次) → 说话候选   pod/live/
```

学生的输入里没有任何特权信息；老师讲解里引用提纲或自动上下文的依据，在组装数据时改写掉（否则学生会照抄它看不到的来源）。

## 结果

数据：10 段录像 242 分钟（两个账号、四种职业：刷图、超级 Boss、一二章剧情、三次阵亡），3,355 个 5 秒窗口有老师讲解，校验保留 97–100%。留出两份：同角色的一段刷图录像（89 个窗口）、另一个角色的两段剧情录像（150 个窗口）。

考题正确率（"地板"= 永远答最常见的答案）：

| 同角色留出录像 | 未微调 4B | 第 1 次 (0.6 遍, 3 段) | 第 5 次 (4B, 10 段) | 第 6 次 (8B, 10 段) | 地板 |
|---|---|---|---|---|---|
| 场上图腾数 | 25% | 77% | 77% | 79% | 40% |
| 顶部有没有名条 | 57% | 88% | 90% | 91% | 78% |
| 法力升降 | 59% | 64% | 76% | 80% | 75% |
| 区域类型 | 69% | 100% | 100% | 99% | 68% |
| 目标面板第一条 | 49% | 100% | 100% | 100% | — |
| 区域名字 | 49% | 40% | 32% | 76% | — |

| 另一角色的留出录像 | 未微调 4B | 第 5 次 (4B) | 第 6 次 (8B) | 地板 |
|---|---|---|---|---|
| 顶部有没有名条 | 83% | 93% | 93% | 51% |
| 区域类型 | 24% | 94% | 96% | 77% |
| 生命升降 | 71% | 91% | 96% | 90% |
| 名条名字 | 84% | 88% | 90% | — |

讲解：第 4 次起留出录像的 44 个窗口全部是合法 JSON；HUD 生命读数约一半窗口写对（数据量从 3 段加到 5 段时从 4/44 升到 21/44，提高分辨率没有治好它）。

实时（云端 4090/5090，vLLM 合并权重）：一次理解 3–7 秒，HUD 快路径每秒一次、不经语言模型。

和老师的差距：判断类（在哪、在干什么、有没有名条、威胁）学生已接近老师；读字读数差一截（名字和地名 4B 差 20–60 个百分点，8B 差 10–25）；讲解里的细节和因果明显弱于老师。原因按影响排序：输入少（4 帧对老师的 75 帧加整段提纲）、数据少（4 小时）、模型小。

完整的六次训练记录、每次的失败和更正见 [docs/student-runs-2026-10.zh-CN.md](docs/student-runs-2026-10.zh-CN.md)。

## 费用（实测）

- 老师标注：批量模式约 US$4.5 / 小时录像（同步模式约 US$10）。
- 学生训练：5,853 个样本 1 遍，RTX 4090 约 2.6 小时、US$2.2；8B 在 5090 上约 US$3.2。
- 实时：云端一台 4090 约 US$0.9 / 小时。

## 仓库内容

| 路径 | 内容 |
|---|---|
| `watch/` | 录像处理、HUD 读取、日志事件、提示音、老师标注、校验、考题、数据集、学生评测、RunPod 控制 |
| `pod/` | 在租用 GPU 上跑的脚本：`train_lora.py`、`infer.py`、`make_bundle.py`、`intake.sh`（录像预处理）、`live/`（实时运行时） |
| `knowledge/` | 给老师的通用机制笔记 |
| `build_cards/` | 给老师的角色卡 |
| `models/` | 两个 LoRA 适配器（Git LFS）：`run5-qwen3-vl-4b-lora`、`run6-qwen3-vl-8b-lora`，底座分别是 `Qwen/Qwen3-VL-4B-Instruct` 和 `Qwen/Qwen3-VL-8B-Instruct` |
| `results/` | 六次训练的损失曲线和各题型分数 |
| `docs/` | 方向调研、老师试点与盲评、六次训练记录、工具说明 |

不在仓库里：录像、帧、音频、老师的讲解文本和数据集（留在私有存储）；API 密钥（`.env`）。

## 用适配器

```python
import torch
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoProcessor

base = "Qwen/Qwen3-VL-4B-Instruct"
model = AutoModelForImageTextToText.from_pretrained(base, dtype=torch.bfloat16, device_map={"": 0})
model = PeftModel.from_pretrained(model, "models/run5-qwen3-vl-4b-lora")
proc = AutoProcessor.from_pretrained(base)
```

输入格式和提示词见 `pod/infer.py`：一个窗口 4 帧（首尾 1280 px、中间两帧 896 px）加上一刻的 state。训练时用的版本：transformers 5.18.0、peft 0.21.2。

## 文档

- [docs/watching-survey-2026-10-02.zh-CN.md](docs/watching-survey-2026-10-02.zh-CN.md)：为什么不是"冻结 VLM 上加一个门"，流式视频模型与基准的现状，方向选择
- [docs/teacher-pilot-2026-10-05.zh-CN.md](docs/teacher-pilot-2026-10-05.zh-CN.md)：老师的试点、纠错与盲评
- [docs/student-runs-2026-10.zh-CN.md](docs/student-runs-2026-10.zh-CN.md)：六次学生训练
- [docs/tools.zh-CN.md](docs/tools.zh-CN.md)：录制设置和每个脚本的用法
