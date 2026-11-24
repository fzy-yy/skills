# `pixel-art-forge` 开发共识与设计文档

本文件记录通用像素美术技能 **`pixel-art-forge`** 已达成的设计共识、硬性约束、交付规范与当前实现状态，便于后续会话直接承接开发与迭代。

---

## 1. 核心定位与不可违背的红线

- **Skill 名称与仓库路径**：`pixel-art-forge`，位于 `skills/pixel-art-forge/`（成熟后可按目标客户端规范同步或链接至用户全局技能目录，例如 `~/.gemini/config/skills/pixel-art-forge`）。
- **全品类通用覆盖**：同时支持四大像素美术品类——**道具/图标（`icons`）**、**角色与帧动画（`characters`）**、**无缝地图图块（`tilesets`）**、**UI 元素（`ui`）**。
- **严格纯程序化生图**：**禁止使用任何第三方图像生成 / 扩散模型能力**，也不依赖 Aseprite 客户端等外部二进制工具；仅允许使用 **Python 3.10+ 标准库 + `Pillow`**。
- **混合架构（方案 A）**：**项目风格与调色板用 JSON 锁死（`pixel_spec.json`）+ 具体资产用 Python 脚本调用 `pixel_forge` 引擎绘制**，且**保留资产绘制源码脚本**（“像素资产即代码”）。
- **分辨率原生设计 + 程序锁死（模式一）**：目标逻辑像素尺寸由用户提示词或澄清结果决定，Agent 按目标分辨率套用对应的细节预算进行原生设计，底层引擎以不可变整数网格强校验锁死尺寸与色板，杜绝分辨率幻觉、Mixels（混杂像素大小）、色板越界与半透明脏边。

---

## 2. 交互式需求澄清与共识达成规则（阶段 0）

当用户单独调用 Skill 未加细节，或提示词宽泛（如“画一把剑”、“做个主角”）时，Agent **必须先进入共识澄清阶段**，不得静默瞎猜：

1. **继承去重**：先检测工作区是否存在 `pixel_assets/pixel_spec.json`；若已存在，自动继承已锁定的全局风格（色板、颜色上限、视角、光源、描边、抖动），仅追问当前新资产缺失的细节。
2. **提问工具与格式**：若当前环境提供交互式询问工具（如 `ask_question`、`AskUserQuestion` 等），**必须优先使用询问工具提问**（仅在无询问工具时回退为文本列表）；每个问题必须给出**候选选项 + 明确标注推荐项 + 一句话推荐原因**。
3. **必备询问维度**：
   - **Part A 全局风格契约**（首次建规范时问）：
     - **色板颜色数量上限**（`4色` / `8~16色` / 推荐 `24~32色` / `64色+或自定义精确上限`，写入 `max_colors` 由程序硬校验）
     - **调色板预设与色彩氛围**（`endesga32` / `sweetie16` / `dark_dungeon24` / `pico8` / `nes_classic16` / `gb4` / 自定义 Hue-Shifted 色板）
     - **游戏视角与比例风格**（顶视角 3/4 RPG / 横版侧视 / 纯平图标 / 等距 2.5D）
     - **主光源方向**（推荐左上 45° `[-1, -1]` / 正上 / 右上 45°）
     - **描边风格**（推荐 Sel-Out 选择性深色描边 / 纯黑 1px / 无描边）
     - **着色与抖动技法**（无抖动清晰色块簇 / Bayer 2×2 / Bayer 4×4）
   - **Part B 单资产细节**（按品类动态追问）：素材品类、目标画布尺寸、构图朝向与材质/造型特征、动画动作列表与帧节奏、锚点与 PPU 习惯。
4. **“未作答 = 模型自由选择”机制**：
   - 提问时必须显式告知用户：**只需回答关心的项，未作答的选项（或回复“你来定 / 随意 / 按推荐开始”）由模型按推荐方案或最契合题材的搭配自由选择并锁定**。
   - 用户部分作答或跳过后，直接补全并简短公示最终锁定共识，立刻进入绘制，不反复追问。

---

## 3. 交付产物规范（已修订最终版）

> **注意**：已明确**移除 Godot `.tres` 文件输出**，不要再恢复 `.tres` 导出器。

- **静态资产**（图标、静物、UI、无动画标签的静态地砖变体）：
  1. `1x` 原始像素 PNG（`<name>.png` 或多变体地砖 `<name>_sheet.png`，严格 1-bit Alpha，零插值缩放）
  2. 游戏引擎友好的统一 JSON 元数据（`<name>.json`，Aseprite JSON 标准兼容 + `engine_hints.godot` / `engine_hints.unity`）
  3. 原生 `.aseprite` 二进制工程文件（`<name>.aseprite`，纯 Python `struct`+`zlib` 编码，8-bit Indexed 模式，保留图层/帧/时长/色板/动画标签/Pivot/9-Slice）
- **动画资产**（`len(frames) > 1` 且非静态地砖，或带动画标签）：
  1. **逐帧独立 1x PNG**：`frames/<name>_000.png`、`frames/<name>_001.png` …
  2. **按顺序排列的整张雪碧图 PNG**：`<name>_sheet.png`（可直接导入游戏引擎使用）
  3. **透明背景动态 GIF**：`<name>.gif`（严格使用锁定色板、`disposal=2` 无拖影、精确逐帧时长）
  4. 统一 JSON 元数据（`<name>.json`，附带 `frameImages` 与 `gif` 路径）
  5. 原生 `.aseprite` 工程文件（`<name>.aseprite`）

---

## 4. 标准化工作区输出目录结构

所有生成的像素资产必须遵守以下结构（由 `export_all()` 自动维护）：

```text
pixel_assets/
├── pixel_spec.json                      # 项目全局风格契约（含 palette, materials, max_colors, light_dir, outline, dither）
├── catalog.json                         # 自动维护的全项目资产索引清单
├── src/                                 # 保留的可复用资产绘制源码（便携导入路径，支持任意位置运行）
│   ├── icons/<asset_name>_<W>x<H>.py
│   ├── characters/<asset_name>_<W>x<H>.py
│   ├── tilesets/<asset_name>_<W>x<H>.py
│   └── ui/<asset_name>_<W>x<H>.py
├── exports/
│   └── <category>/<asset_name>/         # 最终交付物（动画额外含 frames/*.png 与 <name>.gif）
└── _inspect/                            # 视觉自检图（不污染正式导出目录）
    ├── <category>_<asset_name>_qa.png   # 1x/2x 深浅底可读性 + 带 X/Y 坐标标尺网格放大图 + 专项检验面板
    └── project_contact_sheet.png        # 全项目已生成资产 4x 同屏风格对照表
```

---

## 5. 像素美术通用七步流程与十大避坑红线

每次制作像素素材必须按 `skills/pixel-art-forge/SKILL.md` 中的 SOP 执行：

1. **澄清并锁定规范**（读取/初始化 `pixel_spec.json`，按需读取对应品类 `references/playbook_*.md` 与 `assets/examples/`）
2. **分辨率预算与坐标规划**（显式写明各部位像素坐标与安全边距）
3. **剪影先行（Silhouette First）**（纯黑剪影一眼可辨识）
4. **语义分层与色块成簇（Clustering）**（按逻辑部位建独立图层，仅用 `spec.color(mat, shade)` 与 `material=` 标签）
5. **定向 2.5D 光影与色相偏移（Hue-Shifting）+ 层间 AO**
6. **描边（默认 Sel-Out）与像素清理**（先 `despeckle()`，再点缀 1–2px 宝石/眼神/高光，避免微细节被误清理）
7. **双轨验收与精修闭环（≤3 轮）**：程序硬检必须 0 Error（尺寸、色板、`max_colors`、1-bit Alpha、全帧无缝性）+ 必须用读图能力目检 `_inspect/<category>_<name>_qa.png`（借助 X/Y 坐标标尺与孤立像素橙框标注精准回改脚本）。

**十大红线**：禁止 Mixels、Pillow Shading（枕头阴影）、Banding（阶梯色带粘连）、Jaggies & Doubles（断层锯齿与 L 型双像素）、Orphan Pixels（孤立碎点）、直线加黑加白脏渐变、半透明脏边、低分辨率过度塞细节、地砖接缝与格纹感、动画帧脚底锚点漂移。

---

## 6. 当前已完成进度与验证命令

### 已落地目录与核心特性
- Skill 主体：`skills/pixel-art-forge/`
  - `SKILL.md`（含 `compatibility` 声明、`<SKILL_DIR>` 路径约定、阶段 0 共识门禁、目录规范、七步 SOP、环境异常处理、十大红线与按需加载路由）
  - `scripts/pixel_forge/`：`palette.py`, `spec.py`（含 `matte`/`metallic`/`gem`/`emissive` 材质感知反射模型推断与配置）, `canvas.py`（含规范图层 Z 序、`composite_solid()` 与网格图集布局配置）, `primitives.py`（含对称语义字符画布 `paint_ascii_canvas` 与布尔挖空 `erase_rect`/`erase_circle`/`erase_polygon`/`cutout_mask`）, `shading.py`, `cleanup.py`（含 9-Slice 拉伸一致性校验与精准凹角免误报 `find_outline_doubles`）, `procedural.py`（成簇砖石/草地/等距纹理、16/47 Auto-Tile、UI 组件）, `rig.py`（完整父子级联正向运动学：翻转/挤压/关节旋转单次重采样合成）, `qa.py`（含多帧异常关键帧 `[ALERT]` 双标尺放大自检）
  - `scripts/pixel_forge/exporters/`：`__init__.py`, `png_exporter.py`（支持单行横排、固定列数网格与按动画 Tag 分行打包）, `gif_exporter.py`, `meta_exporter.py`, `aseprite_exporter.py`
  - `scripts/cli.py`（Python 3.10+ / `Pillow` 友好校验、`--perspective` 别名容错、`list-palettes` / `list-specs` / `init-spec` / `budget` / `contact-sheet` / `scaffold` / `run` / `recolor` / `preview`）
  - `scripts/test_pixel_forge.py`（23 项自动化单元测试，覆盖引擎、色板、`max_colors`、材质反射模型、字符画布与布尔挖空、父子级联旋转与翻转、图层 Z 序、9-Slice 一致性、网格雪碧图、CLI 与 `.aseprite` 二进制回读）
  - `references/`（`engine_api.md`, `art_fundamentals.md`, 4 份品类实战手册）
  - `assets/palettes/`（6 套内置调色板）与 `assets/specs/`（4 套内置风格预设，统一 13 项核心材质 Schema）
  - `assets/examples/`（9 个零告警基准示例：32×32 火焰剑、16×16 微缩生命药水、48×48 皇家宝箱、32×32 骑士 8 帧动画、32×32 四方向战斗法师 16 帧按行打包图集、16×16 无缝地牢地砖、32×32 等距 2.5D 草地方块 3 变体、48×48 9-Slice UI 面板、RPG UI HUD 组件包）

### 常用验证命令（在仓库根目录执行）
```powershell
# 运行引擎与导出器自动化测试（含 .aseprite 二进制回读、GIF/单帧、max_colors、Auto-Tile、等距、UI 组件、CLI 与骨架校验）
python -B skills/pixel-art-forge/scripts/test_pixel_forge.py

# 查看内置色板与分辨率预算
python -B skills/pixel-art-forge/scripts/cli.py list-palettes
python -B skills/pixel-art-forge/scripts/cli.py budget --width 32 --height 32
```

### 后续可继续迭代的方向
- 扩充 `assets/examples/`：按需补充 `48x48` 高精角色或 4 方向 RPG 行走完整示例。
- 视实际使用反馈持续调优 `auto_shade_layer` 材质反射模型（如金属高光带 vs 哑光布料差异化）。
- 按目标客户端（Claude Code / Codex / Antigravity 等）安装方式分发或软链接到全局技能目录供跨项目使用。
