# 「看」的能力调研：角色要看游戏，需要一个自己会预测的内部状态——门只是基线

日期：2026-10-02。修订：2026-10-02，方向改为学出来的预测状态，PoE2 先行。性质：文献与系统调研，不含实现。读取范围：本项目目录与公开网页；未读 .env，未参考其他本地项目。每条事实后附 URL；来源只有摘要或二手转述、或数字是推算的地方，正文标为「未验证」「二手」「推算」。

背景：2026-10-02 重置后 owner 定下的第二条线（视觉能力）。重置前把游戏截图和屏幕录像交给角色反应，效果差；owner 的观察是现有 VLM 至多能说两帧之间变了什么，不能像人那样「看」。初稿的答案是「在冻结 VLM 前加一道门」；owner 读后否决了这个目标——要的是模型自己有视觉、自己对游戏有一个预测中的内部状态，不受 CSC490 课程约束（结果可以喂给课程项目，方向不受它限制）。本文据此修订：第 1–4 节的调研不变，第 5、7、8 节重写。

**要点**：观看机制必须造，现成的没有：所有托管 API（Gemini、GPT-5.x、Qwen、Kimi、GLM）都是「客户端选帧、模型答题」，发言时机由音频 VAD 或客户端决定（[Gemini Live 指南](https://ai.google.dev/gemini-api/docs/live-guide)、[Qwen 实时指南](https://www.alibabacloud.com/help/en/model-studio/realtime)）；开源流式模型有「何时说话」的头，但全是 7–9B、数据中心级，在逐秒决策基准上离人类仍差 40 分以上（LiveProBench 人类 92.99 vs 最佳 51.37，[arXiv 2609.12658](https://arxiv.org/html/2609.12658v2)）。要造的不是一道规则门，而是一个**从游戏自己的录像里学出来的预测状态**：冻结的 V-JEPA 2 编码器（ViT-L 300M，MIT，[GitHub](https://github.com/facebookresearch/vjepa2)）加一个只在 PoE2 录像上训练的小预测器，不看操作，预测几秒后的潜变量。注意力和开口时机从这个状态里长出来：值得说的是「我的看法变了」（信念变化，[Kumar et al. 2023](https://onlinelibrary.wiley.com/doi/10.1111/cogs.13343)），不是「这一帧不太可能」——冻结 V-JEPA 2 的原始预测误差在同一数据集内接近随机（AP 0.29 vs 随机 0.24，[Asleep at the Wheel](https://arxiv.org/html/2608.01336)），所以用的信号是状态变化而非原始误差。初稿的廉价门（dHash/HSV + 手写的惊讶）降为基线，不是产品；VLM 退为按需描述，LLM + CharacterPack 给意义和立场。第一个游戏 PoE2，Apex 之后再做、不并行；数据是 owner 自录、传云。决定性的第一个实验：录约 10 小时 PoE2，训小预测器，拿像素差、原始预测误差、状态变化三个信号对照玩家标的「我会在这里说一句」时间戳。

## 0. 结论先行

1. **要不要造**：要。托管模型与开源流式模型都没有可直接复用的「看游戏并在合适时机开口」能力；现有「主动」机制要么是轮询（Qwen-Live-Harness 每 2 秒切块问模型，[GitHub](https://github.com/QwenLM/Qwen-Live-Harness)），要么是 7–9B 模型里的二分类头（[StreamBridge](https://arxiv.org/html/2505.05467)、[Proact-VL](https://arxiv.org/html/2603.03447)）。前沿 LLM 自决「要不要说」时假警报率 51.85%（[ProactiveBench](https://arxiv.org/abs/2410.12361)）；固定间隔解说 55–97% 的发言互相重叠（[arXiv 2603.02655](https://arxiv.org/html/2603.02655)）。
2. **造什么**：一个预测状态，不是一道门。冻结 V-JEPA 2 ViT-L（潜空间预测、16/64 帧片段，[arXiv 2506.09985](https://arxiv.org/html/2506.09985v1)）+ 小预测器，只用 PoE2 录像、不看操作，输出状态轨迹与预测误差。公开先例是 DINO-world（冻结 DINOv2 空间里的无动作未来预测，[arXiv 2507.19468](https://arxiv.org/abs/2507.19468)）；没有任何论文把这类模型的预测误差曲线对过游戏画面或事件标签——这是空白，也是第一个实验。
3. **用什么信号**：状态变化（预测器信念的变化量），不是原始误差。依据：人的边界跟贝叶斯惊讶走、不跟 surprisal 走（[Kumar 2023](https://onlinelibrary.wiley.com/doi/10.1111/cogs.13343)）；冻结 V-JEPA 2 的原始误差在数据集内接近随机、跨数据集变成「哪个数据集」探测器（[arXiv 2608.01336](https://arxiv.org/html/2608.01336)）。
4. **分工**：预测器管「何时、多反常、在哪个阶段」；VLM 按需管「长什么样」；LLM + 游戏知识 + CharacterPack 管「意味着什么、她怎么看」。第 4 节的门留作基线对照。
5. **硬件与数据**：ViT-L 300M 在 4060 上可做特征提取（显存官方未标，第 7 节实测）；预测器训练在 RunPod 3090/4090（$0.22–0.34/h，[RunPod](https://www.runpod.io/pricing)）；数据 owner 用 OBS 自录、传 R2/B2（第 8 节）。PoE 没有任何公开录像数据集，Apex 只有小检测集（第 5b 节）。
6. **人格入口**不变：identity.viewpoint 决定看哪里，relationship.initiative 决定阈值，presence.idleBehaviour 是状态平稳时的默认行为，identity.value/tension 决定权重与迟疑（第 5d 节）。
7. **CSC490**：可以切一片（信号比较实验本身就是一个课程项目），但不约束方向（第 5e 节）。

## 1. 「看」需要什么，而逐帧 VLM 缺什么

| 能力 | 人类证据 | 逐帧 VLM 的缺口 | 设计含义 |
|---|---|---|---|
| 持续注意：维持一个「事件模型」，帧是确认而非新闻 | Event Segmentation Theory：预测误差瞬时上升时门打开、事件模型重置，其余时间稳定（[Zacks et al. 2007](https://bpb-us-e2.wpmucdn.com/sites.wustl.edu/dist/e/952/files/2017/09/zackspsychbull07-sbm4za.pdf)）；边界处记忆更新（[Swallow et al. 2009](https://www.semanticscholar.org/paper/Event-boundaries-in-perception-affect-memory-and-Swallow-Zacks/30168f19b2508c4d163d9b73a818f53f6ca0f313)） | 每帧独立问答，没有跨帧状态；托管实时 API 的视频记忆只有 2–4 分钟（Gemini Live 音视频会话 2 分钟，[指南](https://ai.google.dev/gemini-api/docs/live-guide)；Qwen 240 s，[指南](https://www.alibabacloud.com/help/en/model-studio/realtime)） | 门外维护一个紧凑状态（地点、角色、目标、HUD 数值），只在边界处重写 |
| 事件切分：知道什么时候「一件事结束了」 | 人类对边界位置一致性好、重测稳定（[Zacks 2007](https://bpb-us-e2.wpmucdn.com/sites.wustl.edu/dist/e/952/files/2017/09/zackspsychbull07-sbm4za.pdf)）；边界强度是分级的（按标注者比例，[bioRxiv 2024](https://www.biorxiv.org/content/10.1101/2024.04.10.588931v2.full.pdf)）；粗边界紧随细边界之后；运动变化与目标完成是廉价代理 | 逐帧决策「闪烁」、过渡边界模糊（STRIDE 的分析，[arXiv 2603.27593](https://arxiv.org/html/2603.27593v1)） | 输出分级边界强度；先检到细边界，短暂等待看粗边界是否到来再发完整评论 |
| 显著性：什么值得看 | 吸引注视的是贝叶斯惊讶而非信息量（72% 的注视转向更惊讶处；电视雪花信息多 20 倍却惊讶少 17 倍，[Itti & Baldi 2009](http://ilab.usc.edu/publications/doc/Itti_Baldi09vr.pdf)）；任务驱动注视（[Yarbus](https://www.researchgate.net/publication/235442324_Yarbus_Eye_Movements_and_Vision)、[Hayhoe & Ballard 2005](https://www.semanticscholar.org/paper/Eye-movements-in-natural-behavior-Hayhoe-Ballard/1ec3c533e569ff3bd8b2935df7eafb661a1ea5de)）；变化盲视与无意盲视说明人会漏掉未注意的变化（[Simons & Chabris 1999](https://experts.illinois.edu/en/publications/gorillas-in-our-midst-sustained-inattentional-blindness-for-dynam)） | 「两帧有什么不同」= 像素差，没有「相对我的模型和目标」的惊讶；会报告雪花 | 显著性 = 相对自身状态的信念变化（KL 式）× 人格目标先验；允许漏看未注意区域，这反而更像人 |
| 何时开口 | 对话间隙众数 0–200 ms，靠预测而非反应（[Stivers et al. 2009](https://pmc.ncbi.nlm.nih.gov/articles/PMC2705608/)；生产延迟 >600 ms，[Levinson & Torreira 2015](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2015.00731/full)）；短反应（backchannel）与完整发言是两种行为；打断在粗断点处代价最低，用户接受平均 1.5 分钟的延后（[Iqbal & Bailey 2008](https://interruptions.net/literature/Iqbal-CHI08.pdf)）；主动性应按期望效用算，「不做」是基线（[Horvitz 1999](https://erichorvitz.com/chi99horvitz.pdf)） | 没有「沉默」这个动作；LLM 自决时假警报过半（[ProactiveBench](https://arxiv.org/abs/2410.12361)） | 两道门、两个阈值：backchannel 低阈值可在 ~200 ms 内触发，完整发言等边界且过高阈值；在细边界处开始起草、粗边界处放出 |
| 警觉动态 | Mackworth 时钟：30 分钟内检出率下降 10–15%，被搭话后恢复（[Shalev 2022](https://www.nature.com/articles/s44159-022-00036-0)；[Wikipedia](https://en.wikipedia.org/wiki/Mackworth_Clock)） | 机器不疲劳，一小时刷怪期间均匀警觉，读起来不像人 | 建模「参与度」：单调时衰减、事件或被搭话时恢复；Let's Play 主播在空档讲故事而不是沉默（[Guzdial et al. 2018](https://arxiv.org/pdf/1809.09424)） |

补两条与设计直接相关的发现。第一，边界检测的两个独立信号：预测误差和预测不确定性，二者解释了大部分人类边界判断但仍有约 16% 的可解释方差未被解释（Bezdek & Zacks，[eLife 预印本](https://elifesciences.org/reviewed-preprints/107955)，搜索摘要层面，全文未读），这给「目标完成 / 游戏脚本结构」留了第三条输入。第二，在语言上，边界对应贝叶斯惊讶（信念变化）而非 surprisal（[Kumar et al. 2023](https://onlinelibrary.wiley.com/doi/full/10.1111/cogs.13343)）——「这一帧不太可能」是错的信号，「我对局面的看法变了」才是对的。笔记没有找到任何研究测量「看别人打游戏的观众」的注视或发言时机，这一块只能从电视共视（[Ducheneaut 2008](https://www.researchgate.net/publication/220302406_Social_TV_Designing_for_Distributed_Sociable_Television_Viewing)，仅摘要）与监控任务迁移。

## 2. 流式/在线视频理解的现状

### 2.1 系统

「4060 可否」一列全部是从论文数字推算的，没有任何论文在 8 GB 卡上报告过结果。

| 系统（年） | 做什么 | 何时说话的机制 | 弱点 | 开源 | 基座与大小 | 4060 可否 |
|---|---|---|---|---|---|---|
| [VideoLLM-online](https://arxiv.org/html/2406.11816)（CVPR 2024） | Ego4D 叙述式流式对话，2 fps，1–10 token/帧 | LM 在该沉默的帧上学会输出 EOS，概率阈值 | StreamingBench 32.48，Proactive Output 3.92（[Dispider 表](https://arxiv.org/html/2501.03218)）；输出冗余、空间理解弱 | 代码 + 权重，许可证未标 | Llama-3-8B + CLIP/SigLIP；3090 上 5–10 FPS，A100 <20 GB（[README](https://raw.githubusercontent.com/showlab/videollm-online/main/README.md)） | 推算：4-bit 约 5 GB 可塞，无官方量化；带宽推算 ~2–3 FPS |
| [Dispider](https://arxiv.org/html/2501.03218v1)（CVPR 2025） | 感知/决策/反应解耦 | <TODO> token 上的二分类头（BCE） | OVO-Bench 41.78；延迟未报；训练代码不放 | 权重 Apache-2.0（[GitHub](https://github.com/Mark12Ding/Dispider)） | Qwen2-1.5B + Qwen2-7B | 否（两个 LLM，bf16 ≈17 GB；两张 80 GB 演示——未验证） |
| [Flash-VStream](https://arxiv.org/html/2506.23825)（ICCV 2025 版） | 固定容量记忆流式问答，<1 s 响应 | 无——「responses require user queries」 | StreamingBench 24.04，常只答「A」（[StreamingBench](https://arxiv.org/html/2411.03628)） | Apache-2.0（[GitHub](https://github.com/IVGSZ/Flash-VStream)） | Qwen2-7B；2024 版 16.03 GB | 否（如发布版本） |
| [LiveCC](https://arxiv.org/html/2504.16030v1)（CVPR 2025） | 2 FPS 持续体育解说，0.17 s/帧 | 不决策：沉默帧输出「…」 | 解说腔，GPT-4o 判胜率 41.5%，无人类评测 | 代码 + 权重，许可证未标（[GitHub](https://github.com/showlab/livecc)） | Qwen2-VL-7B | 推算：权重可塞，2 fps 视觉 token 预算塞不下 |
| StreamChat（NVIDIA，[arXiv 2412.08646](https://arxiv.org/abs/2412.08646)） | 每个解码步更新视觉上下文 | 无（答题） | 代码/模型「soon」，截至抓取未放（[项目页](https://jihaonew.github.io/projects/streamchat.html)） | 否 | 未说明 | — |
| StreamChat（ICLR 2025，[arXiv 2501.13468](https://arxiv.org/abs/2501.13468)） | 免训练分层记忆 + 运动向量选帧 | 无 | 基座/显存未说明 | 代码（[GitHub](https://github.com/hmxiong/StreamChat)） | 未说明 | 未知 |
| [MMDuet](https://arxiv.org/html/2411.17991) / [MMDuet2](https://arxiv.org/abs/2512.06810)（EMNLP 2025 / ICLR 2026） | 视频-文本「二重奏」，模型在播放中插话 | 两个二分类头（informative + relevance）+ need_response 阈值；2 代加 RL | 作者承认重复回答；需要更长直播数据 | MIT（[GitHub](https://github.com/yellow-binary-tree/MMDuet)） | LLaVA-OneVision-7B | 推算：4-bit 未验证 |
| [TimeChat-Online](https://arxiv.org/html/2504.17343v1)（2025） | 差分 token 丢弃（丢 82.8% 保 98% 准确率） | 丢弃率曲线的谷值 = 场景变化即触发 | 把「看」显式做成变化检测（引 Change Blindness），不是解决 | 项目页，URL 未抓到（未验证） | Qwen2.5-VL-7B，1 FPS | 推算：int4 ≈4.5 GB 加 DTD 可能 |
| [StreamBridge](https://arxiv.org/html/2505.05467)（NeurIPS 2025，Apple） | 把离线 Video-LLM 变流式 | **独立**激活模型 LLaVA-OV-0.5B + <ACT> token，阈值 0.35，与主模型并行 | 合成拼接数据有域偏移 | Apple Sample Code License，数据 CC-BY-NC-ND（[GitHub](https://github.com/apple/ml-streambridge)） | 7B 主模型 + 0.5B 激活模型 | 激活模型可；主模型同 7B int4 问题 |
| [StreamingVLM](https://arxiv.org/html/2510.09608)（ICLR 2026） | 注意力汇 + 16 s 视觉窗，每秒叙述 | 不决策：持续解说 | 偶发幻觉；解说腔 | MIT（[GitHub](https://github.com/mit-han-lab/streaming-vlm)） | Qwen2.5-VL-7B；H100 8 FPS | 推算：固定 16 s 窗有利，int4 未验证 |
| [VideoChat-Online](https://arxiv.org/html/2501.00584v2)（CVPR 2025） | 金字塔记忆库 832 token | 无 | 无说话决策 | 公开（[GitHub](https://github.com/MCG-NJU/VideoChat-Online)） | InternVL2-4B；**8.71 GB 实测** | 最接近，需 int8/4 或缩记忆 |
| [MiniCPM-o 2.6](https://huggingface.co/openbmb/MiniCPM-o-2_6) / [4.5](https://arxiv.org/html/2604.27393v1)（2025-01 / 2026-02） | 全双工音视频流 | 4.5：生成前先预测 listen/speak 控制 token | 语音偶不稳；4.5 全双工演示要 28 GB（[README](https://github.com/OpenBMB/MiniCPM-o)） | Apache-2.0 | 8B / 9B；2.6 int4 「7 GB」或「9 GB」（两页矛盾） | 2.6 int4 勉强，流式模式在 8 GB 未记录；4.5 否 |
| [IXC2.5-OmniLive](https://arxiv.org/html/2412.09596v1)（2024-12） | 感知/记忆/推理三模块 | 查询或语音活动触发 | 延迟待降 | 代码（InternLM 仓库） | 1.8B + 1.8B + 7B | 否 |
| Qwen2.5/3/3.5-Omni（[2.5](https://github.com/QwenLM/Qwen2.5-Omni)、[3](https://github.com/QwenLM/Qwen3-Omni)、[3.5 报告](https://arxiv.org/html/2604.15804v1)） | 分块输入即时输出 | 轮次式，「不主动说话」 | 7B bf16 31–60 GB；30B-A3B 79–145 GB | Apache-2.0（3.5 开源范围各博客矛盾，未验证） | 7B/3B；30B-A3B | 仅 2.5-Omni-3B int4 有机会（推算） |
| [Streamo](https://arxiv.org/html/2512.21334)（CVPR 2026） | 流式指令微调 | <Silence>/<Standby>/<Response> 状态 token | 序列变长后显存与延迟「prohibitive」 | 是 | Qwen2.5-VL 3B/7B，1 fps | 3B int4 推算可 |
| [Proact-VL](https://arxiv.org/html/2603.03447)（2026-03，v4 06） | 游戏直播陪伴式解说，561 h / 12 款游戏 | <\|FLAG\|> 上的门控 MLP，sigmoid 阈值 0.3，「先决定再生成」 | 指导场景仍弱；~200 H100 小时训练 | CC BY 4.0；数据/代码可下载性未验证 | 从 LiveCC-7B-Base；~0.35 s/块 | 推算：同 7B int4 |
| [STRIDE](https://arxiv.org/html/2603.27593v1)（2026-03，含 Google DeepMind） | 2B 激活模块驱动 4–8B Video-LLM | 掩码扩散「序列去噪」激活窗口，替代逐帧 0/1 | 仍是数据中心级 | 代码 + HF（interlive） | Qwen3-VL-2B + 4–8B | 2B 模块可；整套否 |
| [LiveStar](https://arxiv.org/abs/2511.05299) / [LiveStarPro](https://arxiv.org/abs/2606.17798)（NeurIPS 2025 / 2026-06） | 单次前向验证决定回应时机 | 困惑度验证，无需沉默 token | 基座/显存未抓到 | 是（[GitHub](https://github.com/sotayang/LiveStarPro)） | 未抓到 | 未知 |
| [StreamPro](https://arxiv.org/abs/2605.16381)（2026-05） | GRPO 训练说/沉默策略 | RL 轮次 + 轨迹奖励 | 数据中心级 | 未抓到 | 未抓到 | 未知 |
| [Harnessing Streaming Video in the Wild](https://arxiv.org/html/2606.08615v1)（2026-06） | 逐秒对齐训练，12 h 上下文 | 每步 </response> 或 </silence> | 开源「承诺」，抓取时未放 | 待放 | Qwen3-VL-8B | 推算：int4 |
| [StreamMind](https://arxiv.org/abs/2503.06220)（ICCV 2025） | 编码器与 LLM 之间的认知门 | 「仅在相关事件发生时」调用 LLM | 基座未抓到 | 代码 aka.ms/StreamMind | A100 100 fps | 未知 |
| [ProAssist](https://arxiv.org/html/2506.05904)（EMNLP 2025，Meta） | 任务助手，说话 = 二元决策序列 | VideoLLM-online 架构 | 作者：「低于可接受阈值」，时机与一致性差 | 是 | LLaMA-3.1-8B | 推算：同 8B |
| [AURA](https://arxiv.org/abs/2604.04184)（2026-04） | 反应式 + 主动式 | 未抓到细节 | 演示用两张 80 GB | 模型已放（链接未抓到） | 未抓到 | 否 |

三类机制：(a) 主 LM 预测特殊 token/EOS，(b) 侧头或侧模型，(c) 推理时验证；STRIDE 的分析指出 (a) 的逐帧决策闪烁较多（[arXiv 2603.27593](https://arxiv.org/html/2603.27593v1)）。「主动」在这些论文里几乎都指「在正确时刻回答一个站立问题」或「给出下一步叙述」，无站立问题的社交式评论只有 Proact-VL、MiniCPM-o 4.5、Harnessing 三个例外。解说质量全靠 LLM 判胜率（LiveCC 41.5% vs GPT-4o，StreamingVLM 66.18% vs GPT-4o mini，MiniCPM-o 4.5 54.4%），笔记没有找到任何一个系统的解说做过人类偏好评测。

### 2.2 基准

| 基准（年） | 规模 | 计时怎么打分 | 人类 vs 最佳模型 | 弱点 | 数据可得 |
|---|---|---|---|---|---|
| [StreamingBench](https://arxiv.org/html/2411.03628)（2024-11） | 900 视频 / 4,500 QA / 18 任务，含「video games」类 | 只有 Proactive Output 子集（300 题）：每秒轮询，±2 s 内算对 | 人类 91.66；Gemini 1.5 Pro 67.07；PO 子集 Seed1.5-VL 82.80（[GitHub](https://github.com/THUNLP-MT/StreamingBench)） | 「伪流式」：视频在问题时间截断后离线处理（[StreamingEval 批评](https://arxiv.org/html/2603.21493)） | HF 203 GB，代码 MIT |
| [OVO-Bench](https://arxiv.org/html/2501.05510)（CVPR 2025） | 644 视频 / ~2,800–3,100 QA，含 gaming 域 | Forward Active Responding：密集查询，罚答错与不及时 | 人类 92.81；Gemini 1.5 Pro 63.0；Forward 仅 57.15 | 作者承认离线模型在 forward 任务「随机猜」 | CC BY-NC-SA，44–144 GB（[GitHub](https://github.com/JoeLeelyf/OVO-Bench)） |
| [OVBench](https://arxiv.org/html/2501.00584v2)（CVPR 2025） | 1,463 视频 / ~7,000 标注 | 无 | 无人类基线；VideoChat-Online-4B 54.9 | 纯准确率 | 公开 |
| [SVBench](https://github.com/sotayang/SVBench)（ICLR 2025） | 1,353 视频 / 49,979 QA 对话链 | 无（LLM 判答案质量） | GPT-4o 领先 | 「需要大量算力」 | HF |
| [RTV-Bench](https://arxiv.org/html/2505.02064)（NeurIPS 2025） | 552 视频 / 167 h / 4,608 QA | 无 | GPT-4o 50.02；多数 <50 | 模型变大只多 2–3 分 | CC BY 4.0 |
| [OmniMMI](https://arxiv.org/html/2503.22952)（CVPR 2025） | 1,121 视频 / 2,290 题 | Proactive Alerting 首次回应在窗内；Proactive Turn-taking = 对噪声查询**不回应**的比例 | 无人类基线；Gemini 1.5 Pro 27.46 | 商用模型平均约 15–16% | CC BY-NC-SA |
| [ProactiveBench / PAUC](https://arxiv.org/html/2507.09313)（2025-07） | 1,377 视频 / 3,510 回复轮 | PAUC：GPT-4 逐时刻 0/1/2 打分，曲线下面积，ω 调时效 vs 正确 | 人类分数「人为偏低」，WEB 上人类 38.6 < LLaVA-OV 55.0 | 依赖 GPT-4 判官；主动专用模型反而不如离线模型 | CC BY 4.0 |
| [LiveSports-3K](https://arxiv.org/html/2504.16030)（CVPR 2025） | 3,000 体育事件，CC 轨 1,702 | 无（只判每个事件的解说文本） | LiveCC 41.5% 胜率 vs GPT-4o | 解说锚定 ASR 转录 | HF 22.4 GB，许可证未示 |
| [LiveProBench](https://arxiv.org/html/2609.12658v2)（2026-09） | 5.4 h，18,146 个逐秒决策，六子任务含 Sustained Silence（60–194 s 必须沉默） | SES = √(回应率 × 沉默率)；过早 = 漏掉；容差 0–25 s | **人类 92.99 vs Qwen3-Omni-SFT 51.37**；过早回应比漏掉多 2.1–28.2 倍 | 未测 Gemini/GPT-5/Dispider/LiveCC | CC BY-NC-SA |
| [Streaming-Eval](https://arxiv.org/html/2606.08615v1)（2026-06） | 138 视频，Proactive/Punctual/Contextual × Backward/Present/Forward | SW-F1：TP/FN 权重 2.0，FP 仅 0.2 | 无人类基线；GPT-5.4 18.3，Gemini 3.1 Pro 13.8，Claude Opus 4.6 9.5 vs StreamingHarness-8B 45.8 | 故意轻罚多说 | CC BY 4.0，待放 |
| [SPOT-Bench](https://arxiv.org/html/2604.24317)（2026-04） | 940 视频 / 68 h，含 Unsolicited Intervention | T-F1：非对称高斯时间罚（早优于晚），计 FP 罚刷屏，窗 ±0.5–2.5 s | 最佳 AsynKV 10.2% T-F1@5；现有流式模型 <3.4% | 「离线 MLLM 能检到事件但未经提示就刷屏」 | 发布未确认 |
| [OmniInteract](https://arxiv.org/abs/2605.26485)（2026-05） | 250 视频 / 1,430 槽位 | IA-QTF1 | 最佳 0.368；持续监控 0.052 | — | 承诺 |
| [PaSBench-Video](https://arxiv.org/abs/2606.02443)（2026-06） | 740 视频（481 风险 / 259 安全） | 必须在危险初现与事故之间警告；安全片段计 FP | 无模型超过 20%；召回与 FP 相关 0.64 | — | CC0 |
| Proact-VL [Live Gaming Benchmark](https://arxiv.org/html/2603.03447)（2026） | 561 h 英语解说 / 12 款游戏；测试 3,014 片段 + 10 段 30 min–2 h 整场 | TimeDiff、F1（时间戳落在真值区间）、PAUC、CC 胜率 vs Gemini 2.5 Pro | GPT-4o F1 54.88 / TimeDiff 3.07；Proact-VL 64.87 / 1.71 | 真值是职业解说 ASR，不是陪伴式评论 | CC BY 4.0；可下载性未验证 |
| [Pause-Aware Decoding](https://arxiv.org/html/2603.02655v1)（2026-03） | 赛车（200 段）+ 格斗（64 段）游戏解说 | 逐秒时间戳相关 + 人类 0–5 停顿感知 | 固定间隔 55–97% 重叠；动态间隔把时机评分 2.22→3.50 | 两款游戏 | CC BY 4.0，[代码](https://github.com/anum94/Video2Text) |
| [EgoStream](https://arxiv.org/abs/2605.31557)（2026-05） | 2,250 题，Answer Validity Window | 记忆诊断，非何时说话 | 最佳 ~45%，全部 >1 s/帧 | — | CC BY 4.0 |

名字核对：「Mind the Time」（arXiv 2412.05263）是多事件视频**生成**模型 MinT，不是理解基准（[arXiv](https://arxiv.org/abs/2412.05263)）；「Streaming-QA」找不到独立评测基准，最近的是 STRIDE 的训练集 StreamingQA-120K（[HF](https://huggingface.co/datasets/interlive/streamqa-120k)）与 StreamEQA（[arXiv 2512.04451](https://arxiv.org/html/2512.04451)），标为未验证。笔记另外列出但未抓取的 2026 名字：EgoSAT、OVIBench、StreamPro-Bench、PhoStream、EgoServe、SVCBench（见 [Awesome-Streaming-Video-Understanding](https://github.com/sotayang/Awesome-Streaming-Video-Understanding)）。

**没有一个基准打分「这句话值不值得说」**：所有「显著性」都是参考式的——人类标了事件就该说，否则是 FP（LiveProBench 沉默率、SPOT-Bench 刷屏 FP、OmniMMI 轮次、PaSBench 安全片段）；解说文本也只判与参考转录的对齐。没有找到以「有趣 / 值得」为目标的独立人类偏好研究。对 CSC490 来说，LiveProBench（5.4 h）与 ProactiveBench WEB（500 段平均 16.6 s）是 4060 能整体跑完的两个。

### 2.3 论文自己承认的差距

StreamingBench：模型「lack precision in timing」且「struggles to adapt to the proactive output format」，而且 Proactive Output 必须靠每秒轮询「Is it the right time to output?」来跑，因为「current MLLMs cannot autonomously produce output」（[arXiv 2411.03628](https://arxiv.org/html/2411.03628)）。OVO-Bench：实时处理能力与理解深度之间存在 trade-off（[arXiv 2501.05510](https://arxiv.org/html/2501.05510)）。StreamPro：see-then-answer 范式把主动推理「reducing proactive reasoning to delayed perception」（[arXiv 2605.16381](https://arxiv.org/abs/2605.16381)）。TimeChat-Online 把流直接定义为变化检测（「over 80% of visual content … naturally redundant」，[arXiv 2504.17343](https://arxiv.org/html/2504.17343v1)），这是把 owner 的观察变成工程技巧而非解决它。Proact-VL 点名三件未解之事：低延迟流式、「autonomously deciding when to respond」、控制「quality and quantity」（[arXiv 2603.03447](https://arxiv.org/html/2603.03447)）。文献把「看」拆成 (1) 有界记忆、(2) 检测发生了什么、(3) 决定是否值得说；(1)(2) 被当作够用，(3) 是每个基准仍差人类 30–50 分的地方，而且每个机制都是特殊 token 上的阈值二分类，没有一篇建模「观看者为什么在乎」。

## 3. 托管大模型的视频能力对照 owner 的观察

| 提供方 / 模式 | 视频输入形式 | 实时流？ | 时机与显著性由谁决定 | 定价（抓取日） | 判定 |
|---|---|---|---|---|---|
| Gemini 文件模式（[文档](https://ai.google.dev/gemini-api/docs/video-understanding)） | 文件/URL，1 fps，66 或 258 token/帧，1M 上下文最长 3 h；3.8/3.7/3.6 Flash 有「agentic」按需加载模式 | 否 | 客户端定 fps；agentic 模式是离线问题驱动 | 2.5 Flash $0.30/1M 输入；3.8 Flash $0.75（2027 起 $1.50）（[定价](https://ai.google.dev/gemini-api/docs/pricing)） | 回答关于采样帧的问题，带时间戳 |
| Gemini Live（[指南](https://ai.google.dev/gemini-api/docs/live-guide)） | 客户端推 JPEG，**≤1 fps**；音视频会话 2 分钟（可用会话管理延长）；128k 上下文 | 是 | 音频 VAD；`proactiveAudio` 只是「can proactively decide **not** to respond」；无视频触发门 | 3.8 Live 音频 $0.005/min 入；视频帧价未找到（未验证） | 唯一有「沉默开关」的 API，但没有「开口开关」 |
| OpenAI GPT-5.x（[视觉指南](https://developers.openai.com/api/docs/guides/images-vision)） | 仅图片，patch 计费（1024² = 1,229 token）；官方 cookbook 每 25 帧抽一张（[cookbook](https://developers.openai.com/cookbook/examples/gpt_with_vision_for_video_understanding)）；原生视频输入请求被关为 not planned（[issue #1778](https://github.com/openai/openai-node/issues/1778)） | 否 | 全在客户端 | gpt-5-mini $0.25/1M 入（[定价](https://developers.openai.com/api/docs/pricing)） | 帧 + 问题；720p 1 fps 一小时 ≈4.0M token（推算） |
| OpenAI Realtime / GPT-Live（[Realtime 指南](https://developers.openai.com/api/docs/guides/realtime)） | 图片作为会话快照；LiveKit 说话时 1 fps、否则 1/3 fps（[LiveKit](https://docs.livekit.io/agents/models/realtime/plugins/openai/)） | 音频是；视频否 | 音频 VAD；GPT-Live 全双工「每秒多次决定是否说」但仅消费端、无摄像头/屏幕（[MacRumors](https://www.macrumors.com/2026/07/08/openai-gpt-live-voice/)，二手） | 未抓到 | 不看 |
| Qwen3-VL / DashScope（[视觉指南](https://www.alibabacloud.com/help/en/model-studio/vision)） | 文件或帧列表，fps 0.1–10 默认 2，时间戳对齐 | 否 | 客户端 | qwen3-vl-flash $0.05/1M 入（[定价](https://www.alibabacloud.com/help/en/model-studio/model-pricing)） | 采样帧工具最全，仍是答题 |
| Qwen3.8-Omni-Flash（[MarkTechPost](https://www.marktechpost.com/2026/09/18/alibaba-qwen-releases-qwen3-8-omni-flash/)，二手） | 文件最长 2 h，1M 上下文，「决定看什么听什么」粗到细 | 否（仅文件） | 模型自选帧，但对文件 | $0.15/1M 入 | 离线 agentic，非观看 |
| Qwen Omni-Realtime + [Live-Harness](https://github.com/QwenLM/Qwen-Live-Harness)（[实时指南](https://www.alibabacloud.com/help/en/model-studio/realtime)） | 客户端推 JPEG，建议 1 fps；视频记忆 240 s；会话 120 min | 是 | semantic_vad / server_vad / 手动 `response.create`；「手动模式下无显式请求不生成」；Harness 的「主动监控」= 1 fps 两秒切块问模型是否满足用户设定条件 | 未找到 | 主动性在 harness 里轮询，正是 owner 看到的循环 |
| Kimi K3（[视觉指南](https://platform.kimi.com/docs/guide/use-kimi-vision-model)） | 上传文件 `ms://`，服务端挑关键帧，无 fps 参数 | 否 | 无 | ¥20/1M 入，视频 token「动态」（[定价](https://platform.kimi.com/docs/pricing/chat)） | 上传后问 |
| Claude（[视觉文档](https://platform.claude.com/docs/en/build-with-claude/vision)）/ Grok（[文档](https://docs.x.ai/docs/guides/image-understanding)） | 仅图片 | 否 | — | — | 不在局内 |
| 智谱 GLM-Realtime / GLM-4.6V（[Realtime](https://docs.bigmodel.cn/cn/guide/models/sound-and-video/glm-realtime)、[4.6V](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-4.6v)） | 实时：客户端 fps 推帧，~2 分钟记忆；文件：128K ≈1 h | 是 | VAD；主动只有 `greeting_config` 开场白 | 视频 ¥1.2/min（Flash）≈ ¥72/h | 实时但被动 |
| 字节 SeedRealtime（[Seed 页](https://seed.bytedance.com/en/direction/multimodal)；[eesel](https://www.eesel.ai/blog/seedrealtime)，二手） | 「看、听、说」原生全双工 | 是（豆包 app 内） | 厂商称模型自己决定对话时机 | 无 API、无论文、无权重（截至 2026-08-18） | 唯一宣称会「看」的产品，无法构建 |
| MiniMax（[H3](https://www.minimax.io/blog/minimax-h3)） | 视频生成 | — | — | — | 不适用 |

**判定**：owner 的观察对每个托管 API 都成立。基准测托管模型的方式与 owner 一样——抽帧、轮询、打分；需要时机的两条赛道恰是闭源模型最低处（OVO-Bench Gemini 1.5 Pro forward 57.15 vs real-time 69.32，[arXiv 2501.05510](https://arxiv.org/html/2501.05510)）；StreamingBench PO 上 Claude 3.5 Sonnet 64.71、GPT-4o 56.86、Gemini 1.5 Pro 45.10 也全是轮询出来的（[arXiv 2411.03628](https://arxiv.org/html/2411.03628)）。Gemini 2.5/3.x、GPT-5.x、Qwen3-VL、Kimi K3 在 StreamingBench/OVO-Bench 官方榜上没有数字（榜单停在 2025-01/03）。游戏解说研究是最直接的文书证据：GPT-4.1 等「excel at generating commentary content, they largely ignore when to speak」，固定间隔重叠 55–97%，生成 677–2,989 词 vs 人类 546–681（[arXiv 2603.02655](https://arxiv.org/html/2603.02655)）。结论：托管栈以每小时几美分到一美元提供「帧里有什么、变了什么、带时间戳」，不提供「何时」；时机与显著性必须在客户端造。一个尚未有人发表的直接测试：Gemini Live 开 proactiveAudio + 1 fps 屏幕推流，看它是否会因画面主动开口——笔记没有找到任何此类记录。

## 4. 变化检测与事件边界作为积木

**图像对变化描述（第一阶段的数据）**。Spot-the-Diff：13,192 对 VIRAT 监控图像，每对**至少一处变化**，没有「没变」类（[仓库](https://github.com/harsh19/spot-the-diff)；[Img-Diff 综述](https://arxiv.org/html/2408.04594v1)）；SOTA OneDiff CIDEr 56.6（[arXiv 2407.05645](https://arxiv.org/html/2407.05645v1)），MEDIC+DIRL 45.5（[arXiv 2609.01136](https://arxiv.org/html/2609.01136v1)）。CLEVR-Change：79,606 对，COLOR/TEXTURE/ADD/DROP/MOVE 加 **DISTRACTOR**（仅视角/光照变化，标注「no change was made」等），并单独报 distractor-only 分数，这是经典基准里唯一自带「没变」标签的（[ar5iv 1901.02527](https://ar5iv.labs.arxiv.org/html/1901.02527)）；2025–26 SOTA CIDEr 131.7（MCT-CCDiff）/ 129.2（MEDIC+DIRL，[arXiv 2609.01136](https://arxiv.org/html/2609.01136v1)）。LLM 时代的基准全部假定有差异：DiffCap-Bench 明确过滤掉无差异对（Gemini 3 Pro F1* 83.1，Qwen3VL-32B 68.7，[arXiv 2605.04503](https://arxiv.org/html/2605.04503)）；OmniDiff、VDiff-Bench、ViDiC 亦然。含义：冻结 VLM 被问「有什么不同」时会在 distractor 对上编一个变化，「先判没变再让 VLM 说」是可测且有用的。两套数据的许可证页面未标，需查 LICENSE 文件。与屏幕最接近的是 2026 年 web-UI 视觉回归描述基准（[arXiv 2607.01728](https://arxiv.org/pdf/2607.01728)，仅见标题/摘要）。

**通用事件边界检测（第二阶段的公开数字）**。Kinetics-GEBD：54,691 段 Kinetics-400，平均 4.94 位标注者，指标 F1@Rel.Dis 0.05，监督基线 PC 0.625（[ar5iv 2101.10511](https://ar5iv.labs.arxiv.org/html/2101.10511)）；标注在 [StanLei52/GEBD](https://github.com/StanLei52/GEBD)（搜索摘要称代码 MIT、标注 CC BY-NC 4.0，需到仓库确认），视频需另从 Kinetics-400 下载。离线 SOTA：DDM-Net 76.4（[arXiv 2112.04771](https://arxiv.org/pdf/2112.04771)）、SC-Transformer 77.7（[arXiv 2206.02985](https://arxiv.org/pdf/2206.02985)）、EfficientGEBD 78.3–82.9，ResNet-50 仅 2–6 GFLOPs，仓库表报 1,000–2,400 fps（GPU 未说明，[仓库](https://github.com/Ziwei-Zheng/EfficientGEBD)）。**在线/因果变体 ESTimator**：预测下一帧特征，误差超过过去误差队列的均值 + 1.5 σ 即判边界；ResNet-50 24 fps，Kinetics-GEBD F1@0.05 0.620，端到端 96.3 fps（[arXiv 2510.06855](https://arxiv.org/html/2510.06855)）——这正是 EST「预测误差尖峰」的视觉实现，简单到可以在 CLIP/DINO 特征上重做。免训练的 STITCH 用冻结视频-文本骨干的嵌入序列变化做边界（[arXiv 2608.27929](https://arxiv.org/abs/2608.27929)，F1 未在摘要）。警告：GEBD 边界无分类且密集（约 4.8 个 / 10 s 片段），单独用会比陪伴者该说话的频率高得多——它给「这里变了」，不给「值得说」。镜头切换检测（TransNet V2，MIT，CPU 实时，[仓库](https://github.com/soCzech/TransNetV2)；PySceneDetect HSV 阈值 27 / 自适应滚动均值，[文档](https://www.scenedetect.com/docs/latest/api/detectors.html)）在连续游戏画面上几乎无用（只有过场/菜单/加载），但是录播与菜单转换的廉价第一级。笔记没有找到任何游戏画面或屏幕录像的 GEBD 数据集。

**视频显著性**。DHF1K（1,000 视频、17 位观察者，[mmcheng.net](https://mmcheng.net/videosal/)）上，适合 4060 的是 UNISAL（MobileNet，比竞品小 5–20 倍，AUC-J 0.901，[arXiv 2003.05477](https://arxiv.org/pdf/2003.05477)）与 ViNet（1080 Ti 上 62.5 fps，AUC-J 0.908，[arXiv 2012.06170](https://arxiv.org/pdf/2012.06170)）；精度榜首 SalFoM 0.922（[arXiv 2404.03097](https://arxiv.org/pdf/2404.03097)），速度未知。没有任何显著性模型在游戏画面上训练；游戏注视数据只有 Atari-HEAD（117 h、4 人，[arXiv 1903.06754](https://arxiv.org/pdf/1903.06754)）与 GSET Somi（84 名玩家、一款横版云游戏，[IEEE DataPort](https://ieee-dataport.org/open-access/gset-somi-game-specific-eye-tracking-dataset-somi)），都离现代 3D 游戏很远。「VideoSalMod」「GameVideoSaliency」**找不到**。对门来说显著性是**空间先验**（裁剪 VLM 看的区域、给变化信号加权），不是触发器。

**廉价信号**。dHash（8×9 灰度缩略、64 位汉明距离，对亮度/对比度免疫，[dev.to](https://dev.to/ahmet_gedik778845/implementing-perceptual-hashing-for-video-deduplication-in-python-4ail)）、PySceneDetect HSV 差、SSIM 都是 CPU 数千 fps 级（推算，无屏幕录像的实测对比）；CLIP 嵌入漂移在工业界用作场景变点（Amazon 的自相似矩阵，[amazon.science](https://www.amazon.science/blog/automatically-identifying-scene-boundaries-in-movies-and-tv-shows)），但没有论文报它在 Kinetics-GEBD 上的 F1。光流幅度在游戏里是坏触发器（镜头旋转产生大流量却无事件；笔记未找到任何论文推荐它）。游戏音频可能是最便宜的高精度「出事了」线索（枪声、拾取、音乐提示），已验证的数据集只有 PUBG 的 BattleSound（WEAPON/VOICE/MIXTURE，>90% 准确率，[Sensors 2023](https://doi.org/10.3390/s23020770)），需按游戏标注。HUD、小地图、聊天框造成恒定小像素变化，需掩膜 + 滚动基线。

**弃答校准**。ReCoVERR 用相关问题的高置信证据来提高覆盖率（+20%，[arXiv 2402.15610](https://arxiv.org/abs/2402.15610)）；「Explicit Abstention Knobs」在 Gemini 2.0 Flash 上，阈值 0.71 时覆盖 63.7%、风险 9.4%（未过滤 23.6%），但帧数减少 67% 后置信度中位数仍 0.9，覆盖只降 16%——**置信度不跟踪证据量**（[arXiv 2601.00138](https://arxiv.org/html/2601.00138v2)）。含义：门要用证据特征（实际变了多少）而不是 VLM 自报的置信度。

**冻结 VLM 前的门如何组合**（综合三个已发表的「冻结模型前的触发器」：VideoLLM-online 的 EOS 头、StreamBridge 的解耦 0.5B 激活模型（阈值 0.35）、ESTimator 的预测误差检测器）：

```
DXcam 1–2 fps ──► L0 dHash/HSV（CPU，HUD 掩膜）──无变化──► 丢弃
                      │变化
                      ▼
            L1 SigLIP/CLIP 嵌入（<1 GB）+ 音频特征
                      │
            L2 预测误差 / 信念变化（ESTimator 式，均值+kσ 滚动阈）
               + 粗/细边界强度（分级）+ 显著性空间先验
                      │
            L3 门（逻辑回归/小 MLP/LightGBM，CPU）：
               输入 = L2 特征 × 人格先验 + 参与度状态 + 距上次发言时间
               输出 = 沉默 | backchannel（低阈） | 完整发言（高阈，等粗边界）
                      │开
                      ▼
            冻结 VLM（Qwen3-VL-4B 本地 / Gemini Flash-Lite 托管）
            只描述被裁剪的显著区域 + 事件模型差异 → 角色语音（k3）
```

细边界到达时起草、粗边界到达时放出（粗边界通常紧随细边界，[Zacks 2007](https://bpb-us-e2.wpmucdn.com/sites.wustl.edu/dist/e/952/files/2017/09/zackspsychbull07-sbm4za.pdf)），以抵消 VLM 的秒级延迟；场面混乱（预测误差持续高）时退回细粒度、停止粗评论。

**修订（2026-10-02）**：上图 L2 的「预测误差 / 信念变化」在初稿里是手写的（ESTimator 式滚动阈），整道门是一组规则加一个小分类器。owner 否决了把它当目标：它没有自己的看法，只是把像素差包装成惊讶。此后这道门只作**基线**保留——L0 的 dHash/HSV 像素差是第 5a 节三个对照信号里的第一个，L3 的阈值逻辑是第 5d 节人格入口的落点。
学出来的替代——预测器的状态变化——在第 5 节；评测时门与预测器跑同一批片段、同一组标记。

## 5. 建议：学出来的预测状态

### 5a. 方向与机制

**骨干**：V-JEPA 2 ViT-L/16，300M 参数，MIT 许可，权重公开（256 px 的 16 帧与 64 帧两种检查点；[GitHub](https://github.com/facebookresearch/vjepa2)、[HF 卡](https://huggingface.co/facebook/vjepa2-vitl-fpc64-256)）。它本身就是潜空间预测模型：预测器回归 EMA 编码器对被遮住的时空块的表示，L1 损失，预训练主阶段 16 帧 256²、冷却阶段 64 帧 384²，约 100 万小时视频（[arXiv 2506.09985](https://arxiv.org/html/2506.09985v1)）。V-JEPA 2-AC 证明了「冻结编码器 + 另训一个 300M 预测器」只需 62 小时无标注视频（4 fps、16 帧片段）就能学到可用于规划的动力学（同上）。冻结特征上的轻探针表现好（V-JEPA ViT-L 冻结 K400 82.1 / SSv2 71.2，[arXiv 2404.08471](https://arxiv.org/pdf/2404.08471)；DIAMOND/IRIS 潜变量对球、板、分数的线性 R² 0.81–0.99，[arXiv 2603.21546](https://arxiv.org/html/2603.21546)），所以「冻结 + 小预测器」是合理起点。ViT-L 推理显存官方没有数字（未验证，第 7 节实测）；64 帧 384 px 是 8,192–18,000+ token 的服务器任务（二手，[Medium](https://medium.com/@cryptofairy/how-i-got-a-4-reduction-in-v-jepa-2s-heaviest-computation-d54376052d8d)），4060 上用 16 帧 256–384 px。

**预测器**：只在 PoE2 录像上训练，不看键鼠（action-free），输入过去几秒的 V-JEPA 2 特征，预测 2–8 秒后的特征（视野由第 7 天的实验定）。先例：DINO-world 在冻结 DINOv2 空间做无动作的未来帧预测（[arXiv 2507.19468](https://arxiv.org/abs/2507.19468)）；V-JEPA 2 自身的预训练也是无动作的。输出两样东西：**状态轨迹**（预测器隐状态随时间的序列）和**预测误差**（预测特征与实际特征之差）。

**用哪个信号**：状态变化，不是原始误差。两条依据。(1) 人在听故事时的事件边界跟「贝叶斯惊讶」（信念的变化量）走，不跟 surprisal（这一步多不可能）走（[Kumar et al. 2023](https://onlinelibrary.wiley.com/doi/10.1111/cogs.13343)）；这在视觉上从未检验过。(2) 「Asleep at the Wheel」把冻结 V-JEPA 2 + 可训练预测头的原始误差当新奇度，跨数据集 AP 0.89 但 nuScenes 内 0.29（随机 0.24），误差实际在探测「哪个数据集」（AUC 0.965），同一冻结特征上的监督探针反而到 AP 0.50（[arXiv 2608.01336](https://arxiv.org/html/2608.01336)）——原始误差被域方差淹没，必须在流内归一化、看变化量。具体做法：对预测器隐状态（或它预测的未来特征）取滚动窗口内的变化幅度，按流内均值 + kσ 定阈（ESTimator 对过去误差做统计检验的方式，[arXiv 2510.06855](https://arxiv.org/abs/2510.06855)）；原始误差与像素差作对照。

**分工**：预测器管**何时、多反常、在哪个阶段**（刷图 / 城镇 / boss / 背包 / 对话，这些「体制」从状态轨迹里聚出来）；VLM（Qwen3-VL-4B 本地或 Gemini Flash-Lite 托管，第 6 节）只在被叫到时管**长什么样**；LLM 带游戏知识与 CharacterPack 管**意味着什么、她怎么看**（立场仍来自 k3 的声音）。两条后续：一个**潜变量到语言的适配器**，用 VLM 对关键时刻的描述作伪标签训练，让预测器的状态能直接变成几个词而不必每次调 VLM；一个**「LLM 给期望、预测器核对」的回路**——LLM 按游戏知识说「这波该是 boss 第二阶段」，预测器的状态是否随之改变；不一致本身就是值得说的事。

### 5b. PoE2 与 Apex 的分层预估

| | 能稳定做到 | 大概率做到 | 做不到 | 依据 |
|---|---|---|---|---|
| PoE2（先做） | 体制切分（刷图 / 城镇 / boss / 背包 / 对话）；大场面变化（进图、boss 现身、死亡、回城）；节奏估计（这张图多久、停了多久） | 掉落时刻（过滤器给物品标签染色、加光柱与音效，[NeverSink PoE2](https://github.com/NeverSinkDev/NeverSink-Filter-for-PoE2)）；战斗吃紧（血球下降 + 画面密度）；「这局比平时慢」 | 读物品名与词缀；懂机制与规则；玩家意图；战斗内每一下 | 节奏慢：优化 build 20 秒清图，其他数分钟，弱 build 打 boss 可到 10 分钟（社区，未验证，[Steam](https://steamcommunity.com/app/2694490/discussions/0/598514698788361542)）→ 1–2 fps 够用；没有任何公开 PoE 录像数据集（只有 Kaggle 联赛统计与 RePoE 表格，[Kaggle](https://www.kaggle.com/datasets/gagazet/path-of-exile-league-statistic)、[RePoE](https://github.com/brather1ng/RePoE)），只能自录；ToS 第 8 条明文允许录像与直播，第 7 条禁自动化与改客户端，无 AI/读屏条款（[GGG 条款](https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy)） |
| Apex（之后） | 阶段切分（跳伞 / 搜刮 / 交战 / 缩圈 / 结算）；交战开始与结束；被击倒、复活、换区 | 交战激烈度；「这局打得比平时急」；队友状态变化 | 战斗内细节（谁打谁、打中没）；敌人位置；语音协同的内容 | 节奏快：满甲 200 HP 的 TTK 约 0.8–1.1 s（R-99 0.78，R-301 1.11，[GameRevolution](https://www.gamerevolution.com/guides/492585-apex-legends-ttk-what-is-the-time-to-kill)），4 fps 一次击倒只见 4 帧 → 交战段需 4–8 fps，CS:GO 数据集用 16 fps（[arXiv 2104.04258](https://arxiv.org/abs/2104.04258)）；公开数据只有几百到 2,589 张的检测集（[Roboflow](https://universe.roboflow.com/da-boy/apex-legends-o8ivc)）与 AMD 一段 20 分钟的私有测试（[arXiv 2505.07721](https://arxiv.org/html/2505.07721v1)）；EA 条款第 6 条禁「绕过、修改或破解游戏界面」的第三方程序，第 7.C 条反作弊监视进程（[EA 用户协议](https://www.ea.com/legal/user-agreement)）→ 只能被动录屏，不向进程注入任何东西 |

两款游戏不并行：PoE2 先验证信号，Apex 之后用同一编码器换一个预测器（5c「换游戏」行）。

### 5c. 做不到的范围、原因、将来的解法

| 范围 | 为什么做不到 | 将来的解法 |
|---|---|---|
| 读文字 | 预测器看的是 256–384 px 的缩图，物品名、词缀、聊天框不可读 | 由状态触发的 HUD 区域 OCR（在 1080p 原帧上裁剪）；PoE2 自带 Ctrl+C 把悬停物品文本复制到剪贴板，Awakened PoE Trade 只靠读剪贴板工作、不触碰游戏进程（[FAQ](https://snosme.github.io/awakened-poe-trade/faq)） |
| 规则与知识 | 像素里没有机制、词缀含义、build 逻辑 | LLM + poewiki/poedb 检索 + pack 的 knowledge.knows |
| 因果与意图 | 无动作预测器把玩家边缘化了：只看到结果，不知道是她做的还是世界做的 | 键鼠日志做动作条件化（V-JEPA 2-AC 的做法，[arXiv 2506.09985](https://arxiv.org/html/2506.09985v1)；PoE2 条款不禁止外部记录输入）；LLM 在事件日志上推意图；或者直接问玩家 |
| 战斗内部 | 1–2 fps 加潜变量平均，单次技能、单次受击被抹平 | 高帧率的裁剪读数器：血/魔/药瓶/boss 血条区域的小模型 |
| 长时记忆 | 预测器的上下文是秒级（GameNGen 约 3.2 s，[arXiv 2408.14837](https://arxiv.org/html/2408.14837)；Genie 3 约 1 分钟，[DeepMind](https://deepmind.google/discover/blog/genie-3-a-new-frontier-for-world-models/)） | 事件日志写进平台的记忆线：RecallBasis.OBSERVED 得到一个生产者 |
| 没见过的东西 | 惊讶高，但没有名字 | 按设计这正是调昂贵 VLM + 检索的时刻 |
| 声音 | V-JEPA 2 只看视频 | 加一路音频嵌入流；过滤器音效是固定集合（[NeverSink](https://github.com/NeverSinkDev/NeverSink-Filter-for-PoE2)），可当高精度事件标签 |
| 玩家的状态 | 只看得到打法，看不到情绪 | 在她自己的录像上持续训练后，用「偏离她自己的基线」；不做情感识别 |
| 换游戏 | 预测器是按游戏学的 | 共享编码器，每款游戏一个预测器，每款几小时录像（V-JEPA 2-AC 的 62 小时是上限参照） |

### 5d. 人格如何进入

| CharacterPack 字段 | 具体输入 | 形式 | 文献依据 |
|---|---|---|---|
| identity.viewpoint「它怎么看世界，以自己的立场」 | **事件类型先验**：哪些体制/变化类型的权重高（血条 vs 风景、对话 vs 战斗） | 对预测器的状态变化与惊讶的逐类权重向量；VLM 裁剪区域的候选排序 | 任务驱动注视：同一画面不同指令产生不同扫描路径（[Yarbus](https://www.researchgate.net/publication/235442324_Yarbus_Eye_Movements_and_Vision)）；两个角色看同一屏幕注意不同处是忠实于人类数据的 |
| identity.value | **事件价值**：Horvitz 期望效用里的 value(comment) 项 | 与 viewpoint 先验相乘的标量/按类表 | [Horvitz 1999](https://erichorvitz.com/chi99horvitz.pdf) |
| identity.tension | **迟疑与非对称**：想说与忍住之间的拉扯 | 完整发言阈值的滞回宽度；说错的 cost 项；正向反应可快于批评（确认比否认快 100–500 ms，[Stivers](https://pmc.ncbi.nlm.nih.gov/articles/PMC2705608/)） | 「等待的期权价值」（[Tang et al. 2026](https://arxiv.org/abs/2609.03727)） |
| relationship.initiative「多容易开口、等待或保持安静」 | **沉默/发言阈值**：backchannel 与完整发言在状态变化量上的两个阈值及最小间隔 | 两个标量 + 每分钟上限；低 initiative 的角色只在粗边界说 | 断点处打断代价最低、用户接受延后（[Iqbal & Bailey 2008](https://interruptions.net/literature/Iqbal-CHI08.pdf)） |
| presence.idleBehaviour「在场但没被搭话时是什么样」 | **状态平稳时的默认行为**：参与度衰减曲线与空档行为（讲故事 / 哼歌 / 沉默） | 参与度状态机的初值与衰减率；空档触发的非画面话题 | 警觉衰减与被搭话恢复（[Shalev 2022](https://www.nature.com/articles/s44159-022-00036-0)）；Let's Play 的空档讲故事（[Guzdial 2018](https://arxiv.org/pdf/1809.09424)） |

CharacterPack 不改一字：pack 定义「她是谁」，这些字段把预测器的状态变化与惊讶翻译成「她看哪里、多久开口、不说话时在干什么」。owner 的人格判据——每一句安慰都是 AI、有自己立场才是人——与此一致：预测器决定「说不说」，VLM 的描述只是素材，立场仍来自 k3 的声音。

### 5e. 可发表性

约 6 个月内可到 workshop 级：CVPR 的 EgoVis（[CVPR26 页](https://egovis.github.io/cvpr26/)）或 LOVEU（[2024 页](https://sites.google.com/view/loveucvpr24/track1)，2026/27 届未验证）；FDG 2027 有「Game Spectatorship and Non-Player Experiences」赛道，墨尔本 2027-06-21–24（[FDG 2027](http://fdg2027.org/)）；CHI PLAY 2027 征稿未找到（未验证；CHI 2027 论文截稿 2026-09-10 已过，[CHI 2027](https://chi2027.acm.org/authors/papers/)）；CogSci 2027 毕尔巴鄂 2027-07-28–31（[CogSci](https://cognitivesciencesociety.org/cogsci-2027/)）。三个新颖点：(1) 没有论文把视频基础模型的信念变化对过游戏画面上人类「我会在这里说一句」的时间戳（笔记搜「V-JEPA event boundary」「JEPA surprise event segmentation」无果）；(2) Kumar 2023「信念变化而非 surprisal」从未在视觉上检验，驾驶视频上原始误差近随机的结果（[arXiv 2608.01336](https://arxiv.org/html/2608.01336)）是现成的反衬；(3) 一个陪伴式时机数据集，对照职业解说转录（Proact-VL 的真值是解说 ASR，[arXiv 2603.03447](https://arxiv.org/html/2603.03447)）。主会级别还需要：>1 位玩家、>1 款游戏、标注者间一致性、同一批片段上的流式 VLM 基线（第 2 节的模型在 RunPod 24 GB 上跑一次）。主要风险是零结果——三个信号都对不上人的时间戳；所以把研究框成**信号的比较**而不是一个方法的胜利，零结果在 workshop 也是可接受的发现。CSC490 可以切一片（信号比较 + 评测协议），不约束方向。

### 5f. 不需要造的东西（已存在）

V-JEPA 2 权重与代码（MIT，[GitHub](https://github.com/facebookresearch/vjepa2)）；无动作潜空间预测的先例（DINO-world，[arXiv 2507.19468](https://arxiv.org/abs/2507.19468)；V-JEPA 2-AC 的预测器配方）；感知本身（Qwen3-VL-4B 本地 Q4 3.3 GB / Gemini 或 Qwen3-VL-Flash 托管）；屏幕捕获（DXcam ~240 fps，[仓库](https://github.com/ra1nty/DXcam)；录制用 OBS，第 8 节）；镜头切换（TransNet V2、PySceneDetect）；GEBD 骨干与权重（EfficientGEBD ResNet-18/50）；显著性（UNISAL/ViNet）；嵌入（SigLIP-400M，<1 GB，基线用）；评测协议与代码（StreamingBench PO 的每秒轮询、ProactiveVideoQA 的 PAUC 代码 [GitHub](https://github.com/yellow-binary-tree/ProactiveVideoQA)、Proact-VL 的 F1/TimeDiff 若已放出、Pause-Aware 的 [Video2Text](https://github.com/anum94/Video2Text)）；LLM 判官；**不要训练流式视频 LLM**（7–9B、数据中心级、仍差人类 40 分）；不要训练像素级世界模型（DIAMOND 的 CS:GO 要 87 小时、一张 4090 跑 12 天，[arXiv 2405.12399](https://arxiv.org/html/2405.12399)）；不要做 CORe50 式物体持续学习；不要自建显著性数据集。

## 6. 成本与硬件

**本地 vs 云端候选（显存 / 延迟）**。4060 桌面版 8 GB、272 GB/s、Windows 下约 7 GB 可用（[NVIDIA](https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4060-4060ti/)；[PhotoPrism](https://docs.photoprism.app/developer-guide/vision/model-comparison/)）；笔记本版 TGP 35–115 W 可配置，低功耗档明显更慢（[Notebookcheck](https://www.notebookcheck.net/NVIDIA-GeForce-RTX-4060-vs-NVIDIA-GeForce-RTX-4060-Laptop-GPU-vs-NVIDIA-GeForce-RTX-4060-Ti-8G_11593_11455_11592.247598.0.html)）。

| 候选 | 显存 | 每帧延迟 | 4060 可否 | 来源类型 |
|---|---|---|---|---|
| MiniCPM-V 4.6 1B（Ollama） | 1.6 GB | 0.6 s 描述 | 是，可 2 fps | 实测（[PhotoPrism](https://docs.photoprism.app/developer-guide/vision/model-comparison/)） |
| Qwen3-VL-4B Q4（Ollama） | 3.3 GB | 1.2 s 描述 / 2.4 s 标签 | 是，短答 ~1 fps | 实测（同上）；屏幕/游戏读图幻觉少于 MiniCPM-V 2.6 int4（[InabaPet devlog](https://wa11a.itch.io/inabapet/devlog/1403543/devlog2-dont-trust-the-benchmarks-the-ultimate-8gb-vram-vision-model-showdown-qwen3-vl-vs-minicpm-v)） |
| Qwen3-VL-8B Q4_K_M + mmproj | 5.03 + ~0.9 + KV ≈ 6.7 GB | 2–5 s | 勉强，0.2–0.5 fps，无空间给门 | GGUF 尺寸（[HF](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF)）+ 推算 |
| MiniCPM-V 4.5 8B int4 | — | 4.5 s 标签 | 慢 | 实测（PhotoPrism） |
| MiniCPM-o 2.6 int4 | 「7 GB」或「9 GB」 | 未测 | 边缘；流式模式 8 GB 未记录 | 厂商两页矛盾（[HF](https://huggingface.co/openbmb/MiniCPM-o-2_6)） |
| SigLIP-400M 门编码器 | ~0.8 GB fp16 / 0.4 int8 | 未在 4060 实测 | 是，或放 CPU | 推算 |
| EfficientGEBD ResNet-50 / TransNet V2 / ViNet | 几 GB / CPU / 1080 Ti 62.5 fps | 远超实时 | 是 | 仓库数字，GPU 未标 |
| VideoLLM-online 8B | <20 GB fp16 | 3090 5–10 FPS | 否（RunPod 24 GB） | [README](https://raw.githubusercontent.com/showlab/videollm-online/main/README.md) |
| Flash-VStream（LLaVA 版）/ LiveVLM | 16.03 GB / 4090D 24 GB | — | 否（24 GB） | [arXiv 2406.08085](https://arxiv.org/abs/2406.08085)；[arXiv 2505.15269](https://arxiv.org/html/2505.15269) |
| Dispider / MiniCPM-o 4.5 全双工 / Qwen3-Omni | 两张 80 GB（未验证）/ 28 GB / 79–145 GB | — | 否（48–80 GB） | 各 README |

结论：Qwen3-VL-8B Q4 + SigLIP 门 ≈7.5 GB，在 Windows 上超预算；**2–4B VLM + 门**是 8 GB 的实际配置，8B 只有在门把 VLM 调用压到每分钟几次时才可用（这恰好更像「会注意到的陪伴者」）。4060 Ti 16 GB 的价值是容量而非速度（带宽仅多 6%）。门的头在 CPU 几分钟训完，嵌入只需提取一次缓存（[TDS](https://towardsdatascience.com/why-we-fine-tuned-siglip-and-why-thats-not-always-the-right-call/)），不需要 RunPod。

**RunPod（2026-09-27 页面）与托管 API 每小时**（[RunPod](https://www.runpod.io/pricing)；API 为 1 fps 输入 token 推算，[Gemini 定价](https://ai.google.dev/gemini-api/docs/pricing)、[OpenAI 定价](https://developers.openai.com/api/docs/pricing)、[阿里云定价](https://www.alibabacloud.com/help/en/model-studio/model-pricing)）：

| 项目 | $/h | 备注 |
|---|---|---|
| RunPod 3090 / 4090 / A5000 / A6000 48 GB（Community） | 0.22 / 0.34 / 0.16 / 0.33 | Secure 为 1.3–2.2 倍；serverless 2–3 倍且计冷启动 |
| RunPod A100 80 GB / H100 SXM | 1.19–1.39 / 2.69 | 仅在 24 GB OOM 时用 |
| Gemini 2.5 Flash-Lite 低分辨率 / 标准 | 0.024 / 0.093 | 258 token/帧；加 20 输出 token/帧约 +$0.03 |
| Gemini 2.5 Flash / 3.8 Flash | 0.28 / 0.70 | 3.8 Flash 2027 起翻倍 |
| GPT-5-nano / GPT-5-mini（448²） | 0.042 / 0.21 | 1024² 时 mini ≈1.11；无视频 API |
| Qwen3-VL-Flash / Plus（新加坡，假设 32 px/token） | 0.036 / 0.14 | 托管 token 规则未在定价页标明（未验证） |
| 智谱 GLM-Realtime Flash 视频 | ≈10（¥72） | 唯一按分钟计费的实时视频 |
| 本地 4060 | 电费 | ~0.1–0.2 kWh/h（电价未查） |

**学期预算（推算，≈$100–125，在 $100–300 之内）**：LoRA 4B–7B 两次 4090 24 h $8；流式模型复现 40 h 3090/4090 $9–14；评测扫 A6000 30 h $10；A100 备用 10 h $12；网络卷 50 GB × 4 月 $14；托管基线 100 h Flash-Lite $10–15；前沿模型抽查 10 h $7–10；意外（忘关 pod 一个周末 = $20）$30。存储和闲置比训练贵：数据只在用时放卷上，每次会话脚本化「stop pod」。LoRA 一个 7B VLM 在 24 GB 上 4–12 h / 10K 图（[Labellerr](https://www.labellerr.com/blog/fine-tune-qwen-2-5-vl/)），不需要 A100。

## 7. 第一周的工作

目标：到周末有 8–10 小时带标记的 PoE2 录像在云上、V-JEPA 2 在 4060 上的吞吐数字、三个信号的第一次对比，和一个决定（预测视野 2 s 还是 8 s）。

- **第 1 天 录制链路**（2026-10-02 已完成，见第 8 节）。OBS 32.2.2 装好并写好配置；两段 40 s 试录验证了画面、两条音轨、章节标记和码率。剩余：建 R2 或 B2 桶，装 rclone，试传一段并核对校验和。
- **第 2 天 元数据与首场**。实时标记已由 OBS 的章节标记热键（F9）承担，不再需要单独的日志脚本；写每次会话的元数据模板（第 8 节），写从 MP4 章节表导出时间戳的小脚本；第一次正式会话 2 小时。
- **第 3 天 V-JEPA 2 ViT-L 上 4060**。fp16 跑 16 帧 256 与 384 px，量每秒能处理多少帧（目标 ≥ 4 fps 的实时倍数）与显存峰值（官方无数字）；决定特征提取放本地还是 RunPod（4060 跑不动 384 px 就把提取放 3090/4090，$0.22–0.34/h）。 **已于 2026-10-03 完成**：V-JEPA 2 ViT-L（`facebook/vjepa2-vitl-fpc64-256`，transformers 5.18，torch 2.11 cu128）在 4060 Laptop 上，16 帧 256² 片段 164 ms/片（含 CPU 预处理），约 6 倍实时，显存峰值 1.2 GB；64 帧片段 1.18 s/片。本地抽特征即可，不需要 RunPod。抽帧、特征、三信号评测三个脚本在 `C:/Users/Leo12/Documents/poe2-watch/watch/`。第一场 16 分钟 17 个标记上的首轮数字全部在随机水平附近（留出段 7 个标记：state_change AUROC 0.64、forecast_change 0.63、pixel 0.53–0.57、pred_err 0.44），样本太少，不构成任何结论，只说明链路通了。
- **第 4–5 天 再录三次会话，写脚本**。累计到 8–10 小时；写 ffmpeg 抽帧（4 fps、短边 384）与特征缓存脚本（逐帧池化特征全存，完整 token 图只存 1 小时评测样本）；每次会话结束即上传。
- **第 6 天 三个信号与评测**。实现 dHash/HSV 像素差；在缓存特征上训第一个小预测器（几层 transformer，输入过去 4 s、预测 2 s 后），取原始预测误差；取预测器隐状态的滚动变化量作「状态变化」，流内均值 + kσ 定阈。评测：对标记的 ±1 s / ±2 s 命中率、每分钟触发数、沉默率（LiveProBench 式 SES）。
- **第 7 天 第一次对比与决定**。在 1 小时评测样本上跑三个信号；owner 事后再标一遍同一小时，算实时标记与事后标记的 ±2 s 一致率；按结果决定预测视野是否从 2 s 改到 8 s、k 是否要改；把本周所有「推算」项换成实测数字。

## 8. 录制与数据协议

本节在 2026-10-02 晚按实际机器配置并试录验证：ROG 笔记本，RTX 4060 Laptop 8 GB，内屏 2560×1600 165 Hz，PoE2 Steam 版无边框全屏。标「实测」的数字来自两段 40 s 试录。

**软件**。OBS Studio 32.2.2（免费、开源，[obsproject.com](https://obsproject.com/)），配置为 profile `poe2` 与场景集合 `poe2`，输出目录 `C:/Users/Leo12/Videos/poe2-raw`。安装时旧钩子被 Armoury Crate 的 `asus_framework.exe` 占用，停掉 ROG Live Service / Armoury Crate Service / ASUS App Service 并结束 `ArmourySocketServer.exe` 后才能写入。来源**不用 Game Capture**：它对 PoE2 的注入持续失败（日志每 4 s 一次「attempting to hook… capture stopped」），改用 Window Capture 的 Windows Graphics Capture 方式抓 `Path of Exile 2:POEWindowClass:PathOfExileSteam.exe`，无需注入，实测画面完整、HUD 文字清晰。OBS 出问题时的备选是 NVIDIA App 的录制（[NVIDIA](https://www.nvidia.com/en-us/geforce/news/nvidia-app-beta-update-av1-performance-tuning/)，二手），但它不分音轨、不按时分段，只作应急。

**视频**。画布 2560×1600（与游戏窗口一致），输出缩放到 1920×1200（保持 16:10，不裁不变形，Lanczos），恒定 30 fps：30 可以之后抽成 1/2/4/8/15 fps，Apex 交战段需要 4–8 fps，60 fps 只会把存储翻倍；预测器只看 256–384 px，但 1920 宽原帧留给 HUD OCR（5c）。编码器 OBS 原生 NVENC HEVC（`obs_nvenc_hevc_tex`），预设 P6、tune hq、两遍 qres（[OBS NVENC 指南](https://obsproject.com/forum/resources/nvidia-nvenc-guide.740/)），关键帧 2 s，B 帧 2。速率控制 **VBR 10 Mbps、上限 16 Mbps**：先试的 CQP 24 在 Boss 战粒子画面上实测 86 Mbps，合 39 GB/h，不可用；VBR 10 Mbps 实测 9.7 Mbps，**4.2 GB/h**，HUD 小字仍可读。容器 **Hybrid MP4**（OBS 30+，非正常停止不丢整文件，支持多音轨与章节，[OBS 录制指南](https://obsproject.com/kb/standard-recording-output-guide)），不需要 MKV 加 remux。AV1 NVENC 可再省 20–30%（指南相对效率推算），工具链验证前保持 HEVC。

**音频**。两条独立音轨，实测都在：轨 1 只有游戏音，用「应用音频捕获」只抓 PoE2 进程（`wasapi_process_output_capture`），Discord 等不会混入，实测均值 −26 dB；轨 2 麦克风（默认设备，Realtek），实测静音时 −57 dB，owner 可以边玩边说。48 kHz AAC 160 kbps。

**实时标记**。用 OBS 自带的**章节标记热键，绑在鼠标后退侧键（Mouse 4，G502）**，F9 曾是首版（`OBSBasic.AddChapterMarker`，写进 Hybrid MP4 的章节表），含义是「我会在这里说一句」；实测 ffprobe 能读出章节与毫秒级时间。不再需要单独的日志脚本，只要一个从章节表导出时间戳的小脚本。开始 / 停止录制为 Ctrl+F10 / Ctrl+F11，热键在游戏窗口有焦点时也生效（HotkeyFocusType=NeverDisableHotkeys）。之后在 1 小时样本上做一次事后标注，量实时与事后标记的一致率（第 7 天）；稍后找第二位标注者。键鼠日志（做动作条件化用）暂缓——打字聊天会进日志，隐私先放一边。

**分段与元数据**。每 30 分钟自动分文件（RecSplitFile=Time，重置时间戳），文件名 `poe2_%CCYY-%MM-%DD_%hh%mm%ss.mp4`。每次会话一个元数据文本文件：日期；联赛 / 角色 / build；章节或地图类型；过滤器名称与严格度（NeverSink 有七档，[GitHub](https://github.com/NeverSinkDev/NeverSink-Filter-for-PoE2)；**数据集中途不要换过滤器**）；分辨率；OBS 设置版本号；当天的游戏补丁。

**目标量**。第一个实验 10 小时（按实测 4.2 GB/h ≈ 42 GB）；之后 50 小时（≈ 210 GB）。本机 C 盘剩 152 GB，所以每场结束必须上传后删本地。

**云端**。用 S3 兼容的对象存储，RunPod 的 pod 可以直接拉：Cloudflare R2 标准存储 $0.015/GB-月，出口流量免费，Class A 操作 $4.50/百万、Class B $0.36/百万（[R2 定价](https://developers.cloudflare.com/r2/pricing/)）；Backblaze B2 $6.95/TB-月，每月免费出口为存量的 3 倍，超出 $0.01/GB（[B2 定价](https://www.backblaze.com/cloud-storage/pricing)）。42 GB 在 R2 每月约 $0.63，210 GB 约 $3.15；B2 对应 $0.29 / $1.46（推算）。上传用 rclone：R2 走 S3 后端，B2 有专用后端；rclone 单段上传带 Content-Md5、分段上传每段带 SHA256 与 MD5，上传后 HEAD 回读 ETag 核对（[rclone S3](https://rclone.org/s3/)、[rclone B2](https://rclone.org/b2/)）。每次会话后由脚本上传、核对校验和、再删本地副本。Google Drive 可作 owner 自己的归档，但 pod 拉取不便。RunPod 网络卷 $0.07/GB-月（1 TB 以上 $0.05，[RunPod](https://www.runpod.io/pricing)），只放派生特征，不放原始视频。

**本机控制口**。obs-websocket 5.7.4 已开启（端口 4455，需密码，密码在 OBS 的 plugin_config 里），本次试录就是经它触发的；之后的上传脚本和元数据脚本可以用它读录制状态和输出路径。不需要时在 OBS「工具 → WebSocket 服务器设置」关闭。

**已落地（2026-10-02 23:14）**。桶 Cloudflare R2 `vision-model`，前缀 `poe2-raw/`；rclone 1.75.1 远端 `r2`，密钥由 owner 自己配置在本机。40 s 样本经 `upload_session.ps1` 上传、`rclone check` 零差异、本地与桶内 MD5 一致。工具与元数据模板在 `C:/Users/Leo12/Documents/poe2-watch/`（README、session_template.json、export_chapters.py、upload_session.ps1），不在平台仓库内。第一份元数据：联赛 Forbidden Rites，角色 GSMZZG（Gemling Legionnaire），build ky 的 Arc Totem，过滤器 FilterBlade Uber Strict，Steam buildid 25568465。

**标签分层（2026-10-03）**。owner 指出后期刷图时很久没有想说的话，实时标记会很稀疏。这不是标签失效，而是现象本身：陪伴者大部分时间也该沉默，刷图录像是预测器最好的常态训练数据。但玩家的标记记的是「玩家想说」而非「旁观者会说」，是有已知偏差的代理。于是标签分四层：客观事件（PoE2 自己的 `Client.txt`，GGG 允许读取：区域切换、读图结束、死亡、升级、Boss 台词、密语类型、失焦；加游戏音轨里过滤器提示音的无监督聚簇，owner 听一次命名簇）；玩家实时标记；累积约 5 小时后 1–2 小时的事后旁观标注，难判时用成对比较；有机会时朋友共看。第一场核对：日志事件与标记在时间上一致（死亡 161 s 对标记 161.6/161.8 s，回藏身处 689 s 对标记 686.9 s），说明文件名时钟对齐误差在 3 s 内。对 11 个客观视觉事件（读图结束、死亡、升级）的首轮数字：留出段 state_change AUROC 0.81、forecast_change 0.75、feat_drift 0.69、pixel 0.53–0.65、pred_err 0.31；方向与假设一致，但这些事件大多是读图切换，是链路的健全性检查，不是研究结果。

**派生数据**。ffmpeg 抽帧一次：4 fps、短边 384 px，给预测器；逐帧池化的 V-JEPA 2 特征（小）全部缓存；完整 token 图只为 1 小时评测样本保留。
