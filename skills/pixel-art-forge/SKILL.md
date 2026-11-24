---
name: pixel-art-forge
description: >-
  纯 Python 程序化像素美术生产技能，支持严格分辨率锁定、调色板与材质色带强校验、交互式需求澄清，以及面向游戏引擎的规范化导出（1x PNG、Godot/Unity 兼容 JSON、原生 .aseprite；动画资产额外导出逐帧 PNG、有序或网格雪碧图与动态 GIF）。凡是用户希望在不依赖第三方扩散模型生图的前提下，以程序化方式创作、统一风格、迭代精修或导出像素美术资产（道具/图标、角色与帧动画、无缝地图图块、9-Slice UI 元素）时均应使用本技能。
compatibility: 需要 Python 3.10+ 与 Pillow 库；需具备本地命令执行能力以运行绘制引擎，并建议客户端支持读取本地 PNG 图像以完成多模态视觉 QA 闭环。
---

# `pixel-art-forge` — 纯 Python 程序化像素美术技能

**完全通过 Python**（`scripts/pixel_forge/`）生成锐利、可直接投入生产、风格统一的像素美术资产，零第三方生图模型、零 Mixels（混杂像素大小）、严格 1-bit Alpha，并强制锁死项目调色板。

> **路径约定**：下文中的 `<SKILL_DIR>` 指代本 `SKILL.md` 所在的技能根目录；所有生成的项目规范与像素资产默认输出到**用户当前工作区**下的 `pixel_assets/` 目录，切勿将产物写入 `<SKILL_DIR>` 内部。

---

## 阶段 0 — 交互式需求澄清与共识门禁（宽泛需求必经）

**规则**：若用户调用本技能时未附带具体说明，或提示词较为宽泛、细节不足（例如“画一把剑”、“做一个主角”、“帮我画像素素材”），**严禁静默猜测并直接编写代码**。必须先进入**共识门禁**，对齐视觉与技术细节。

### 0.1 触发、快速通道与继承规则
先检查工作区中是否已存在 `pixel_assets/pixel_spec.json`，再按用户提示词的完整度决定是否需要澄清：
- **快速通道（跳过提问直接开画）**：若用户已明确给出**题材/主体、目标尺寸、风格/调色板（或已存在 `pixel_spec.json`）与动画范围（若适用）**，或者显式说明“按推荐直接画”，则无需提问——输出 3 行最终锁定共识摘要后立刻进入第 1 步。
- **精准补问（仅问缺失项）**：若用户已指定部分核心参数（如“暗黑风 32x32 冰霜匕首”），自动锁定已明确的维度，**只追问剩余关键缺失项**，不要复读整套问卷。
- **完整澄清**：若 `pixel_spec.json` 不存在且需求宽泛（如“画一把剑”、“帮我做像素素材”），一次性集中询问缺失的**全局风格契约（Part A）**与**单资产细节（Part B）**；若 `pixel_spec.json` 已存在，则自动继承已锁定的全局配置，**仅询问缺失的 Part B 单资产细节**。

### 0.2 提问方式、格式与“未作答 = 自由选择”规则
1. **优先使用询问工具**：达成共识提问时，若当前客户端环境提供交互式询问工具（如 `ask_question`、`AskUserQuestion` 等），**必须优先使用询问工具来提问**，避免直接输出长段纯文本问卷；仅当运行环境未提供询问工具时，才回退为清晰分组的编号列表文本提问。
2. 每个澄清问题都必须提供**具体候选项**，明确标出一个**（推荐）**选项（建议置于首位），并附带**一句话推荐原因**。
3. **必须在澄清时显式告知用户**：
   > **提示**：你只需回复你关心的项目；**任何未作答的问题（或直接回复“你来定 / 随意 / 按推荐开始”）将由我按推荐方案或最契合题材的搭配自由选择并锁定**，确保风格统一后直接出图。
4. **部分作答或跳过时的处理方式**：
   - 若用户回答了**部分**条目、跳过了其余条目 → 采用用户指定项，为所有未作答项自由选择最协调的搭配，简要输出一份紧凑的**共识摘要**公示最终锁定方案，随即直接进入第 1 步（不要再进行第二轮琐碎追问）。
   - 若用户跳过**全部**问题，或回复“你来定 / 直接画 / 默认” → 自由选择最契合题材的整体搭配并锁定写入 `pixel_spec.json`，输出 3 行简要摘要后立刻进入第 1 步。

### 0.3 Part A — 全局风格契约问题 *（若 `pixel_spec.json` 已存在则跳过）*

1. **色板颜色数量上限**：
   - `4 色` — 极简复古掌机感（如 Game Boy），风格辨识度极强。
   - `8 ~ 16 色` — 紧凑统一（如 Sweetie 16 / PICO-8），适合 8-bit 或轻快 16-bit 游戏，绝不显杂乱。
   - `（推荐）24 ~ 32 色` — 兼顾多材质表现力与整体色彩和谐（如 Endesga 32 / Dark Dungeon 24），最适合通用 RPG 与独立游戏。
   - `64 色以上 / 自定义精确上限（如 12 色）` — 适合高精大尺寸素材或复杂场景；确定上限后将写入 `pixel_spec.json` 的 `max_colors` 由程序硬校验。
2. **调色板预设与色彩氛围**：
   - `（推荐）Endesga 32 (endesga32)` — 32 色自带优秀冷暖色相偏移，奇幻/冒险/通用题材最稳。
   - `Sweetie 16 (sweetie16)` — 16 色明快清爽，适合休闲、平台跳跃、治愈风。
   - `Dark Dungeon 24 (dark_dungeon24)` — 24 色低饱和冷石 + 火光，适合暗黑地牢/魂系氛围。
   - `PICO-8 (pico8)` / `NES 16 色 (nes_classic16)` — 高饱和复古街机/红白机风。
   - `GB 4 色 (gb4)` — 经典 4 阶橄榄绿掌机风。
   - `自定义主题色板` — 由用户指定 1~3 个主色或题材氛围，引擎按色相偏移（Hue-Shifting）自动生成色带。
3. **视角与比例风格**：
   - `（推荐）顶视角 3/4 RPG (topdown_3_4)` — 经典俯视 3/4 视角与二头身/三头身 Q 版比例（对应内置预设 `topdown_rpg`），通用度最高。
   - `横版侧视平台 (side_view)` — 清晰侧向剪影（对应内置预设 `side_platformer`），适合动作/横版过关。
   - `纯平正视 (flat_icon)` — 适合背包图标、卡片立绘与平面 UI。
   - `等距 2.5D (isometric)` — 斜 45° 等距 2:1 网格视角，适合战棋与模拟经营。
4. **主光源方向**：
   - `（推荐）左上 45° ([-1, -1])` — 像素美术黄金默认光向，体积感与图标可读性最自然。
   - `正上方 ([0, -1])` — 适合严格左右对称的 UI、正面角色与俯视地砖。
   - `右上 45° ([1, -1])` — 适合需要反向光照或特定场景构图的项目。
5. **描边风格**：
   - `（推荐）Sel-Out 选择性深色描边` — 按相邻材质自动取最深色并在受光面微提亮，精致不生硬。
   - `纯黑 1px 描边 (black)` — 复古高对比度，在复杂背景中轮廓最跳。
   - `无描边 (none)` — 现代柔和像素风（如《Hyper Light Drifter》风格）。
6. **着色与抖动技法**：
   - `（推荐）清晰色块簇 + 无抖动 (none)` — 16~32px 下最干净利落、拒绝画面显脏。
   - `轻度有序抖动 (bayer2x2)` — 适合 48px+ 较大曲面过渡或暗黑复古纹理质感。
   - `强复古网点抖动 (bayer4x4)` — 浓郁 90 年代 PC/掌机像素风味。

### 0.4 Part B — 单资产共识问题 *（仅询问与当前任务相关且未指定的项）*

7. **素材品类**：
   - `（推荐）道具/图标 (icons)` — 适合快速验证风格与色板定调。
   - `角色与帧动画 (characters)` — 自动启用骨架分层，输出逐帧 PNG + 有序雪碧图 + GIF。
   - `地图图块 (tilesets)` — 自动启用环形无缝画布与 3×3 无缝验收。
   - `UI 元素 (ui)` — 适合 9-Slice 面板、按钮、血条等界面资产。
8. **目标画布逻辑像素尺寸**：
   - `16x16` — 极简复古符号风（每材质 2~3 色）。
   - `（推荐）32x32` — 16-bit 黄金精度（兼顾清晰剪影与材质细节）。
   - `48x48` / `64x64` — 高精像素（可容纳纹饰、次级质感与高光细节）。
   - `自定义尺寸` — 如 `24x32` 角色、`16x16` 地砖、`96x32` 血条。
9. **构图、材质与核心视觉特征**：
   - *道具/武器*：构图朝向（`（推荐）45° 斜向最大化长度` vs `垂直/水平对称`）、主材质搭配（如精钢 + 黄金 + 红宝石）、是否带附魔特效/发光/做旧磨损。
   - *角色/生物*：朝向（正面 / 3/4 侧视 / 纯侧面）、职业与剪影记忆点（头盔/披风/手持武器/盾牌/配饰）、主次配色倾向。
   - *地图图块*：单张无缝地砖 vs 多变体图集（2~4 种干净/裂纹/青苔变体）、材质（石砖/草地/木板/水面）、是否需要动画帧。
   - *UI 元素*：组件类型（对话框面板 / 按钮 / 血条 / 图标槽）、边框材质（木框/金属/石雕）、是否启用 9-Slice 拉伸与四角铆钉装饰。
10. **动画范围与帧节奏（仅角色或动态资产触发）**：
    - 动作列表：`（推荐）待机 4 帧 + 行走 4 帧` / `仅静态单帧` / `完整套装（待机 + 行走 + 攻击 + 受击）`
    - 动画节奏：`柔和慢速（180~220ms/帧）` / `（推荐）标准 RPG（待机 180ms、行走 130ms、攻击 80ms）` / `快节奏动作（70~100ms/帧）`
11. **锚点与引擎导入习惯（可选）**：
    - `（推荐）按品类自动设置（角色脚底居中、图标居中、图块/UI 左上角，PPU = 画布宽度）`
    - `自定义 Pivot 像素坐标或特定 PPU（如 Unity 固定 16 PPU）`

在开始编写代码之前，等待用户回复（或确认交由模型自由选择）。

---

## 标准化输出目录结构

所有生成的源码脚本、导出产物、风格规范与视觉自检图都必须严格遵循 `pixel_assets/` 下的以下目录布局，确保多次生成后依然井井有条、易于检索：

```text
pixel_assets/
├── pixel_spec.json                      # 锁定的项目风格契约（色板、材质色带、主光源、描边等）
├── catalog.json                         # 自动维护的全项目已生成资产索引清单
├── src/                                 # 可复用的资产绘制源码脚本（“像素资产即代码”）
│   ├── icons/<asset_name>_<W>x<H>.py
│   ├── characters/<asset_name>_<W>x<H>.py
│   ├── tilesets/<asset_name>_<W>x<H>.py
│   └── ui/<asset_name>_<W>x<H>.py
├── exports/                             # 面向游戏引擎的正式交付物（严格按品类与资产名分组）
│   ├── <static_category>/<asset_name>/  # 静态资产（图标、静态地砖、UI）
│   │   ├── <asset_name>.png             # 1x 原始像素 PNG（多变体地砖为 <asset_name>_sheet.png）
│   │   ├── <asset_name>.json            # Aseprite 兼容 + Godot/Unity 统一元数据
│   │   └── <asset_name>.aseprite        # 保留图层、帧与切片的原生 Aseprite 工程文件
│   └── <animated_category>/<asset_name>/# 动画资产（多帧角色 / 带动画标签的动态资产）
│       ├── <asset_name>_sheet.png       # 1x 按顺序排列的雪碧图 PNG（可直接导入游戏引擎）
│       ├── frames/                      # 按帧序导出的逐帧独立 1x 原始 PNG
│       │   ├── <asset_name>_000.png
│       │   ├── <asset_name>_001.png
│       │   └── ...
│       ├── <asset_name>.gif             # 严格采用锁定色板的透明背景动态 GIF 预览
│       ├── <asset_name>.json            # Aseprite 兼容 + Godot/Unity 统一元数据
│       └── <asset_name>.aseprite        # 保留图层、帧、标签与切片的原生 Aseprite 工程文件
└── _inspect/                            # 视觉 QA 自检产物（与正式导出目录分离）
    ├── <category>_<asset_name>_qa.png   # 带 X/Y 坐标标尺的视觉自检图（按品类防重名）
    └── project_contact_sheet.png        # 全项目已生成资产的同屏风格一致性对照表
```

调用 `export_all(project, assets_root="pixel_assets", source_script=...)` 将自动强制执行该目录结构、输出全部交付物（动画资产自动包含逐帧 PNG、有序雪碧图与动态 GIF）、更新 `catalog.json`，并刷新 `_inspect/project_contact_sheet.png`。

---

## 通用像素美术七步工作流（强制 SOP）

每次执行像素资产生成任务时，都必须按顺序执行以下 7 个步骤，以保证输出品质与风格一致：

1. **锁定规范并加载对应手册**：
   - 若当前工作区尚未存在 `pixel_assets/pixel_spec.json`，通过 `python "<SKILL_DIR>/scripts/cli.py" init-spec ...` 初始化（支持 `--preset`、`--palette`、`--custom-colors`、`--perspective`、`--light-dir`、`--ppu`、`--max-colors`）；若已存在则直接加载。
   - 按渐进式披露原则，**仅阅读**本技能 `references/` 下对应品类的实战手册及 `assets/examples/` 中匹配的示例模板；可用 `python "<SKILL_DIR>/scripts/cli.py" scaffold ...` 在工作区 `pixel_assets/src/` 下快速生成标准资产脚本骨架。
   - 通过 `resolution_budget(W, H)`（或 `python "<SKILL_DIR>/scripts/cli.py" budget --width W --height H`）查看当前分辨率的细节预算。
2. **坐标与比例预算**：
   - 在绘制前，在脚本中显式定义整数坐标常量（例如：为描边预留 `1px` 安全边距，头部 `y=3..12`，躯干 `y=13..22`，双脚 `y=23..30`，锚点 `(16, 30)`）。
3. **剪影先行（Silhouette Test）**：
   - 先用干净的几何图元、渐细笔触或对称形状铺出整体外轮廓。确保在 `1x` 分辨率下，即便压成纯黑剪影也能一眼辨识主体。
4. **语义分层与色块成簇（Color Clustering）**：
   - 将逻辑部位拆分到独立命名图层（如 `blade`、`guard`、`hilt`、`fx` 或 `back_leg`、`torso`、`head`、`weapon`、`outline`），保证 `.aseprite` 文件保持可编辑性，并让动画与层间环境光遮蔽（AO）正常工作。
   - 使用 `spec.color(material, shade)` 并显式传入 `material=` 标签填充成片色块——严禁硬编码原始 RGB 值。
5. **定向光影、层间 AO 与色相偏移（Hue-Shifting）**：
   - 严格依据 `spec.light_dir` 施加定向光照（通过 `auto_shade_layer` 结合针对性的手动高光与阴影精修）。
   - 在相互遮挡的部位交界处使用 `apply_layer_ao` 施加层间接触阴影。
   - 仅在分辨率预算允许且需要大面积平滑过渡时，才使用 Bayer 有序抖动。
6. **描边与像素级清理**：
   - 在独立的 `outline` 图层（视情况置于底层或顶层合成）上调用 `apply_outline`，按 `spec.outline` 设定生成描边（默认为 `sel_out`）。
   - 运行 `cleanup.despeckle()` 清除内部孤立碎点，检查 1px 曲线确保无 L 型双像素粘连，再克制地点缀锐利高光（`add_specular`）。
7. **双轨 QA 验收与视觉精修闭环（最多 3 轮）**：
   - 运行资产源码脚本（推荐 `python "<SKILL_DIR>/scripts/cli.py" run pixel_assets/src/<category>/<name>_<W>x<H>.py`，自动注入引擎路径；需要换色变体或整数倍展示图时可调用 `cli.py recolor` / `cli.py preview`）。
   - 检查程序化 QA 输出：**必须达到 0 Error**（尺寸精确、100% 符合调色板、`max_colors` 未超限、0 越界裁切像素、地砖无缝与 9-Slice 拉伸一致性校验通过）。
   - **必须使用客户端读图工具目检 `pixel_assets/_inspect/<category>_<name>_qa.png`**：
     - 核验深色与浅色双背景下 `1x` 原始尺寸的可读性。
     - 借助放大面板上的 **X/Y 坐标标尺**（及多帧异常关键帧放大面板）精准定位像素缺陷（比例失调、锯齿、枕头阴影、局部发平、动画脚底漂移、地砖接缝等）。
     - 回到 `pixel_assets/src/...py` 修正坐标或着色并重跑脚本，直至画面锐利清晰、无非预期告警，且与 `pixel_assets/_inspect/project_contact_sheet.png` 风格完全协调。

---

## 环境依赖检查与异常处理

- **Python 或 `Pillow` 缺失**：执行脚本前若发现当前环境 Python 版本低于 `3.10` 或缺少 `Pillow`（`ModuleNotFoundError: No module named 'PIL'`），必须立即向用户说明缺失项，并在征得用户同意后再安装 `Pillow`（如 `python -m pip install Pillow`）；严禁伪造执行结果、手写残缺图片字节或退回调用第三方生图模型。
- **程序化 QA 失败或脚本异常**：若脚本运行抛错或 `qa["passed"]` 为 `False`，必须依据 `errors` / `warnings` 定位问题坐标并修改源码重跑，严禁静默跳过校验或交付存在硬错误的产物。
- **客户端不支持本地读图时的降级说明**：若当前运行客户端无多模态读图能力，无法目检 `_inspect/<category>_<name>_qa.png`，必须在完成程序化 QA（0 Error）后明确告知用户“已完成程序硬检，但受限于当前客户端环境未执行视觉目检”，并附上 `_inspect/` 检验图路径供用户人工审阅。

---

## 像素美术十大反模式（严格红线）

在宣告任务完成前，必须对照以下 10 条禁止事项逐一排查所生成的资产：

1. **禁止 Mixels（混杂像素大小）**：所有像素严格落在 1× 原生整数网格上，零非整数缩放、零模糊插值。
2. **禁止枕头阴影（Pillow Shading）**：严禁单纯按到边缘的距离环状明暗渐变；光照必须严格服从 `spec.light_dir`。
3. **禁止阶梯色带粘连（Banding）**：避免明暗交界线与 1px 外描边逐像素平行贴合形成阶梯感。
4. **禁止断层锯齿与双像素（Jaggies / Doubles）**：消除 1px 曲线上的 L 型角点双像素以及不均匀的步长序列（例如 `1-3-1-4`）。
5. **禁止孤立碎点（Orphan Pixels）**：清除色块内部散落的单个杂点像素（`cleanup.despeckle()`）。
6. **禁止发灰发脏的直线渐变**：必须使用 `pixel_spec.json` 中带色相偏移（Hue-Shifted）的材质色带。
7. **禁止半透明脏边**：严格执行 1-bit Alpha（仅允许 `0` 或 `255`——由 `IndexedLayer` 强制保障）。
8. **禁止低分辨率过度塞细节**：不要试图把 64×64 的微缩细节硬塞进 16×16 的精灵图中。
9. **禁止地砖接缝与格纹重复感**：地图图块必须启用 `toroidal=True`，并通过 `3x3` 拼铺视觉检验。
10. **禁止动画锚点漂移**：角色双脚与地面接触点在所有动画帧中必须稳定锚定（结合 `rig.py` 与洋葱皮检查）。

---

## 按需加载的参考文档与示例

仅加载当前任务实际需要的参考资料：

- **引擎 API 参考**：[engine_api.md](./references/engine_api.md)
- **像素美术核心工艺基础**：[art_fundamentals.md](./references/art_fundamentals.md)
- **道具与图标实战手册**：[playbook_icons.md](./references/playbook_icons.md) | 示例：[icon_sword_32x32.py](./assets/examples/icon_sword_32x32.py)（32×32）、[icon_potion_16x16.py](./assets/examples/icon_potion_16x16.py)（16×16 微缩）、[icon_treasure_chest_48x48.py](./assets/examples/icon_treasure_chest_48x48.py)（48×48 高精宝箱）
- **角色与帧动画实战手册**：[playbook_characters.md](./references/playbook_characters.md) | 示例：[char_knight_32x32_anim.py](./assets/examples/char_knight_32x32_anim.py)（8 帧骑士）、[char_mage_4dir_32x32.py](./assets/examples/char_mage_4dir_32x32.py)（4 方向 16 帧法师网格图集）
- **地图图块与无缝纹理实战手册**：[playbook_tilesets.md](./references/playbook_tilesets.md) | 示例：[tile_dungeon_16x16.py](./assets/examples/tile_dungeon_16x16.py)（俯视无缝）、[tile_iso_block_32x32.py](./assets/examples/tile_iso_block_32x32.py)（等距 2.5D）
- **UI 元素与 9-Slice 实战手册**：[playbook_ui.md](./references/playbook_ui.md) | 示例：[ui_panel_9slice.py](./assets/examples/ui_panel_9slice.py)（9-Slice 面板）、[ui_hud_pack.py](./assets/examples/ui_hud_pack.py)（4 态按钮/血条/物品槽）
- **命令行工具**：[cli.py](./scripts/cli.py)
