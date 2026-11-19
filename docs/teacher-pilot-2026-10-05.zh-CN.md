# 老师讲解试点：24 个窗口（2026-10-05）

老师：本次会话里的 Claude，每个 5 秒窗口看四帧 384 像素的画面，外加自动装配的特权信息（HUD 数值、日志事件、提示音）。
目的：看「扎根的讲解」长什么样，并找出特权信息里的错误。八段、每段连续三个窗口。画面拼图在 `C:/Users/Leo12/Videos/poe2-work/teacher_pilot/sheets/`，机器可读版在同目录的 `pilot_teacher_claude.json`。

## 后期地图：掉落、被秒、回藏身处

**r1w1　2026-10-02_234312　155–160 秒**

Wayward Isle 地图里，Arc 图腾的闪电铺满屏幕，玩家在清 Expedition 的挖掘点，地上有好几个 Excavated Chest 和一颗 Greater Orb of Augmentation，玩家悬停看了它的说明。最后一帧顶部出现精英怪 Goldshriek 的名条（闪电抗性、元素抗性光环、破甲），它脚下掉出一颗 Divine Orb，玩家的法力从满降到一半以下。

- 局面：地图 Wayward Isle，Expedition 挖掘区；清怪并开挖掘宝箱；威胁 中，最后一秒转高
- 特权信息有误：上下文里没有任何掉落提示音，但画面上明确掉了一颗 Divine Orb：提示音检测在这里漏报
- 仅来自特权信息：法力具体数值 2221/4266
- 她可能会说的点：Divine Orb 掉了，值得喊一声
- 考题：顶部名条上的怪物叫什么？→Goldshriek　玩家当前在哪张地图？→Wayward Isle

**r1w2　2026-10-02_234312　160–165 秒**

玩家在 Goldshriek 的范围技能里瞬间死亡：聊天栏出现「GSMZZG has been slain」，屏幕中央弹出「You Have Died」和「Resurrect in Hideout」，生命、Ward、法力全部归零。地上留着刚爆出来的一堆掉落：Expedition Tablet、Expedition Logbook、Regal Orb、Armourer's Scrap、23x Verisium、Superior Ornate Plate (Tier 5)。最后一帧提示正在进入 Shrine Hideout。

- 局面：仍在 Wayward Isle，死亡画面；死亡，选择回藏身处复活；威胁 已经死了
- 特权信息有误：上下文把区域写成 HideoutShrine，但四帧里前三帧还在地图里：区域标签按窗口结束时刻取，在切换处会提前
- 她可能会说的点：刚爆了一地好东西就被秒了，Logbook 和 Tablet 还躺在地上
- 考题：这个窗口里玩家死了吗？→是　死亡后玩家选择去哪里复活？→Shrine Hideout

**r1w3　2026-10-02_234312　165–170 秒**

读图画面「Shrine Hideout」之后回到藏身处，玩家立刻打开 Stash 和 Inventory。先悬停看了一件 Sovereign Alloy，再看背包里一张未鉴定的 Waystone (Tier 15)。背包里排着一列 Waystone，聊天栏还留着刚才的阵亡消息。

- 局面：藏身处 Shrine Hideout；整理仓库和背包；威胁 无
- 仅来自特权信息：生命已回满 1476/1476
- 考题：玩家现在在战斗吗？→否　玩家悬停查看的地图石是几阶？→15

## Olroth Boss 战

**r2w1　2026-10-02_234312　745–750 秒**

Olroth 的 Boss 房：圆形场地，地面有红蓝两色的大符文圈。Olroth 说了一句「The red skies call once more...」后现身，最后一帧顶部出现它的血条，几乎满血。玩家放下图腾，闪电开始打过去，生命和法力都是满的。

- 局面：Expedition Boss 房，对手 Olroth, Origin of the Fall；Boss 战开场；威胁 中
- 仅来自特权信息：Boss 可见血量 0.96
- 她可能会说的点：Olroth 出来了
- 考题：正在打的 Boss 叫什么？→Olroth, Origin of the Fall　Boss 血量大约还剩多少？→九成以上

**r2w2　2026-10-02_234312　750–755 秒**

战斗全面展开，Arc 闪电覆盖全场，Olroth 的血条从接近满降到六成左右，它身上挂着一排减益图标。玩家的血量几乎没动，法力从满掉到三千出头。

- 局面：Olroth Boss 房；Boss 战，图腾持续输出；威胁 中
- 仅来自特权信息：生命 1597/1624、法力 3279/4266
- 考题：这五秒里 Boss 的血量是上升还是下降？→下降　玩家有没有陷入低血？→否

**r2w3　2026-10-02_234312　755–760 秒**

Olroth 喊出「Never!」，血条继续从约四成掉到两成多。场上出现大片冰霜爆裂的范围技能和一道白色光束，玩家在边缘走位躲开，生命保持满，法力在三千多上下波动。Boss 快要倒了。

- 局面：Olroth Boss 房；Boss 战收尾阶段，躲范围技能；威胁 中
- 仅来自特权信息：Boss 可见血量 0.28
- 她可能会说的点：Olroth 只剩一丝血了
- 考题：Boss 血量大约还剩多少？→两到三成　Boss 在这个窗口里死了吗？→否

## Breach 结束后的掉落与 Strongbox

**r3w1　2026-10-02_234312　415–420 秒**

Caldera 地图。一个 Breach 刚打完，屏幕提示「Unstable Breach Collapsed」，红色的裂隙正在闭合，角色自己说了句「One down, who's next?」。玩家带着图腾继续往前走，地上只有一把 Pronged Spear (Tier 4)。满血满蓝，没有威胁。

- 局面：地图 Caldera；Breach 结束后继续跑图；威胁 低
- 考题：刚结束的是哪种玩法内容？→Breach　地图的目标 Boss 是谁？→The Ravenous Fang

**r3w2　2026-10-02_234312　420–425 秒**

Breach 的奖励炸了一地：好几堆 860 Gold、Ornate Wombgift、Signet Wombgift、13x Breach Splinter、Uncut Support Gem (Level 5)、Armourer's Scrap，还有一颗 Exalted Orb；紧接着又出现 Dousing Charm、Drakeskin Boots (Tier 5) 和 Regal Orb。玩家悬停看了 Breach Splinter（13/300），然后逐个拾取。

- 局面：地图 Caldera；拾取 Breach 掉落；威胁 低
- 仅来自特权信息：掉落提示音在窗口第 2 秒响起
- 她可能会说的点：出了 Exalted Orb，还有一颗 Regal
- 考题：这个窗口里有没有值钱的掉落提示音？→是　地上出现了哪种 Orb？→Exalted Orb（另有 Regal Orb）

**r3w3　2026-10-02_234312　425–430 秒**

捡完东西继续跑图，穿过一片沙尘，在一处金色岩地找到一个 Researcher's Strongbox，说明写着「Guarded by 6 packs of Monsters」。玩家停在箱子前看说明，还没有打开。

- 局面：地图 Caldera；跑图，发现 Strongbox；威胁 低，开箱后会升高
- 仅来自特权信息：上下文说顶部出现过精英 Diretusk Boar 的名条，四帧里没有拍到
- 她可能会说的点：保险箱，六波怪守着，开不开
- 考题：玩家发现了什么可交互的东西？→Researcher's Strongbox　它被几波怪物守卫？→6

## Crypt 地图沿 Abyss 清怪

**r4w1　2026-10-04_211633　300–305 秒**

Crypt 地图，目标是「Complete all Abysses」。地面上有 Abyss 裂缝烧出的火，玩家边走边放图腾清怪，闪电和碎片满屏。要注意生命球大半是灰的：HUD 写着 Life 425/1,492、Reserved 1,067，这是这个 build 主动预留了生命，不是残血。

- 局面：地图 Crypt，Abyss 沿线；沿 Abyss 推进清怪；威胁 低到中
- 特权信息有误：上下文写「本窗口最低生命 28%」，这是误导：1,067 点生命被预留，425 就是这个角色的满血。读数器没有读 Reserved 这一行
- 考题：玩家处于残血状态吗？→否，生命被预留　这张地图的目标是什么？→Complete all Abysses

**r4w2　2026-10-04_211633　305–310 秒**

继续沿 Abyss 推进，掉了一颗 Vaal Orb（红底标签）和一些金币。玩家点了一个 Tempest Shrine，顶部短暂出现神龛的名条，随后闪电和碎片效果更密了。旁边还有一个没开的 Chest。

- 局面：地图 Crypt；清怪，激活神龛；威胁 低到中
- 特权信息有误：同上，28% 不是低血
- 考题：玩家激活了什么？→Tempest Shrine　掉落了哪种通货？→Vaal Orb

**r4w3　2026-10-04_211633　310–315 秒**

神龛效果生效中，聊天栏有一句「Open the eye of the storm.」。玩家在怪堆里清场，先后瞄到两只精英 Pure Fury 和 Vile Vulture，顺手捡起了 Vaal Orb 和金币。生命读数始终是 425，没有受到实质伤害。

- 局面：地图 Crypt；带着神龛增益清怪；威胁 低到中
- 特权信息有误：上下文把顶部名条记成「boss，名字为空」，实际是精英怪的名条
- 考题：顶部名条上出现过的怪物名字有哪些？→Pure Fury、Vile Vulture　玩家捡起 Vaal Orb 了吗？→是

## 藏身处整理与鉴定

**r5w1　2026-10-04_211633　1020–1025 秒**

藏身处里，Stash 和 Inventory 并排开着。玩家在把背包里的战利品往仓库里放：悬停看了 Simulacrum Splinter（13/300），四帧之间背包里的东西一件件变少，只有那排红色的 Waystone 留着。

- 局面：藏身处；把战利品存进仓库；威胁 无
- 考题：玩家在做什么？→整理背包，把物品存入仓库　玩家悬停查看了哪种碎片？→Simulacrum Splinter

**r5w2　2026-10-04_211633　1025–1030 秒**

继续清背包，最后只剩 Waystone 和一两样零碎。随后玩家关掉面板，露出藏身处全景：Map Device、Waypoint、标着「Ice Cave (Completed)」的传送门，以及 NPC Doryani、Ange、Zolin、Jado、Farrow。玩家朝 Doryani 走去。

- 局面：藏身处；整理完毕，走向 NPC；威胁 无
- 考题：上一张打完的地图叫什么？→Ice Cave　藏身处里能看到哪些 NPC？→Doryani、Ange、Zolin、Jado、Farrow

**r5w3　2026-10-04_211633　1030–1035 秒**

玩家找 Doryani 鉴定，聊天栏显示「11 Items identified」。然后重新打开仓库，切到专门放 Waystone 的页签，悬停查看背包里一张 Waystone (Tier 15)，说明上写着 Revives Available: 5。看样子是在挑下一张要打的图。

- 局面：藏身处；鉴定物品，挑选下一张地图；威胁 无
- 考题：这个窗口里鉴定了多少件物品？→11　玩家接下来最可能要做什么？→开下一张地图

## 新角色：The Bloated Miller

**r6w1　2026-10-05_024430　115–120 秒**

第一幕开头的 Boss 战：雨夜的林地里，Monk 对上 The Bloated Miller，它吼着「Die!」「Split you!」。Monk 用带闪电的近身攻击贴着它打，Boss 血条大约一半，旁边还混着一只 Drowned 小怪。玩家生命从 32/42 掉到 22/42，生命球明显空了一截。

- 局面：第一幕野外，任务 Reaching Clearfell；Boss 战 The Bloated Miller；威胁 高（硬核模式，生命只剩一半）
- 特权信息有误：上下文里有一条「值钱掉落提示音 (divine)」，画面上没有任何掉落物：应为提示音检测的误报；区域为 unknown：录制开始前就已进入这张图，日志窗口里没有它
- 她可能会说的点：硬核号，四十二点血已经掉了一半
- 考题：正在打的 Boss 叫什么？→The Bloated Miller　玩家生命是上升还是下降？→下降

**r6w2　2026-10-05_024430　120–125 秒**

玩家拉开距离周旋，生命从 22 回到 30 再回满 42。随后重新贴上去，对着 Miller 打出一记闪电攻击。Boss 血条略低于一半，头上多了一个减益标记。

- 局面：第一幕野外；Boss 战，先拉开回血再反打；威胁 中
- 考题：窗口结束时玩家生命是否回满？→是　Boss 死了吗？→否

**r6w3　2026-10-05_024430　125–130 秒**

Monk 绕着 Miller 走位，躲开它的重击后再反打，法力从 42 一路用到 21。Boss 血条降到四成左右，玩家生命保持 42/42。打法很稳：打两下就退。

- 局面：第一幕野外；Boss 战，走位消耗；威胁 中
- 仅来自特权信息：法力具体数值 42 → 23
- 考题：玩家的法力是上升还是下降？→下降　Boss 血量大约还剩多少？→四成

## 新角色：第一次进城交任务

**r7w1　2026-10-05_024430　190–195 秒**

刚进 Clearfell Encampment：屏幕中央提示新任务「Talk to the Blacksmith」，上方出现地名横幅。Mortimer 说「Well done! Please come inside.」，角色回了一句「How have the Ezomytes fallen this far?」。四周很暗，只有木栅和火光，满血满蓝。

- 局面：城镇 Clearfell Encampment；刚进城，接到新任务；威胁 无
- 她可能会说的点：第一次进城
- 考题：玩家现在在哪里？→Clearfell Encampment　当前任务要找谁？→Blacksmith（铁匠）

**r7w2　2026-10-05_024430　195–200 秒**

玩家沿木栈道往营地里走，找到头顶带任务标记的 NPC Renly，旁边是发着蓝光的 Waypoint。城镇里没有战斗。

- 局面：城镇 Clearfell Encampment；走向任务 NPC；威胁 无
- 考题：带任务标记的 NPC 叫什么？→Renly　附近有 Waypoint 吗？→有

**r7w3　2026-10-05_024430　200–205 秒**

和 Renly 对话：先弹出「Select One Reward」，选完后出现「Quest Complete」，背包里多了一颗 Uncut Skill Gem (Level 1)。Renly 接着讲起 Grelwood 里一头在土里潜行、专门偷袭的野兽。随后玩家打开 Gemcutting 界面，在 Quarterstaff 技能里翻看，悬停在 Hand of Chayula 上，它要 31 级才能用，现在只是看看。

- 局面：城镇 Clearfell Encampment；交任务、领技能石、浏览技能；威胁 无
- 她可能会说的点：拿到第一颗技能石，在挑学什么
- 考题：任务奖励是什么？→Uncut Skill Gem (Level 1)　玩家最后打开了哪个界面？→Gemcutting（刻技能石）

## 新角色：墓地、升级、Lachlann

**r8w1　2026-10-05_034433　335–340 秒**

墓地场景，任务是「Sorrow Among Stones：Put Lachlann to rest」。Lachlann the Lost 在念白，哀悼他被杀的家人，说要让他们付出代价。地上有 Ringmail Gauntlets 和 Withered Wand 两件掉落。玩家在墓碑间和一只 Cultist Warrior 交手，能量护盾从 6 掉到 3，生命 190 是满的。

- 局面：第一幕墓地（Cemetery of the Eternals 一带）；Boss 出场前清小怪；威胁 中
- 考题：当前任务要让谁安息？→Lachlann　玩家的护盾是上升还是下降？→下降

**r8w2　2026-10-05_034433　340–345 秒**

打掉 Cultist Warrior 后，顶部换成了 Boss「Lachlann of Endless Lament」的血条。同时聊天栏提示角色升到 10 级，屏幕下方出现「1 Passive Skill Point available」。玩家当场打开天赋树，在一个 Attribute 节点上弹出「+5 Strength / Dexterity / Intelligence」三选一。

- 局面：第一幕墓地；Boss 刚出场，玩家抽空点天赋；威胁 中
- 她可能会说的点：十级了，而且是在 Boss 面前开天赋树
- 考题：玩家升到了几级？→10　新出现的 Boss 叫什么？→Lachlann of Endless Lament

**r8w3　2026-10-05_034433　345–350 秒**

玩家点「Apply Points」确认了天赋，回到战斗。Lachlann 现身为一个高大的红色幽魂，朝玩家放出绿色投射物，Monk 用一排闪电还击。Boss 血条几乎还是满的，玩家生命 212/212、护盾 10/10。

- 局面：第一幕墓地；Boss 战开场 Lachlann；威胁 中
- 仅来自特权信息：生命上限随升级从 202 变为 212
- 考题：Boss 血量大约还剩多少？→接近满　玩家确认天赋点了吗？→是

## 老师对流水线的意见

1. 地面物品标签是最丰富的扎根来源，384 像素下我能读清，但目前的特权信息里没有它们；应加一遍画面中部的标签 OCR。
2. 左下角的绿色对白与系统消息（Boss 台词、阵亡、升级、鉴定数量）同样重要，也应读入特权信息。
3. HUD 第三行在不同角色上是 Ward 或 Reserved；不读 Reserved 会把预留生命的 build 误判为长期残血。
4. 区域标签在换图的那个窗口里会提前，应按窗口内每秒各自取。
5. 提示音检测在 24 个窗口里有一次漏报（Divine Orb）和一次误报（Bloated Miller 战斗中）。
6. 每 5 秒 4 帧足以讲清先后顺序和局面；战斗只能讲到「什么样的战斗、谁占上风」，讲不到每一下。
7. 顶部名条的 boss / elite 分类不可靠：神龛、小怪名条都会出现在那里。
