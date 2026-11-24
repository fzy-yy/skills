# 实战手册：地图图块与无缝纹理（`category="tilesets"`）

## 1. 数学级无缝平铺（`toroidal=True`）
- 设置 `category="tilesets"` 会自动为每个图层开启 `toroidal=True`（环形画布模式）：所有像素坐标自动按 `(W, H)` 取模回绕。
- 除非刻意制作方格边框地砖，否则**切勿**沿 `x=0`、`x=W-1`、`y=0` 或 `y=H-1` 绘制无法无缝衔接的生硬边线。
- 地表/背景图块的整体对比度应**低于**角色与道具，让场景中的可交互主体在地板和背景之上清晰跳脱。

## 2. 内置程序化地砖、Auto-Tile 与等距 2.5D 生成器（`procedural.py`）
请传入确定性随机种子（`seed`），确保同一变体可稳定复现：
- 基础无缝地表：
  - `fill_stone_brick_tile(lyr, spec, material="stone", rows=4, cols=2, seed=42, weathering=0.25)`
  - `fill_grass_tile(lyr, spec, material="grass", seed=42, tuft_density=0.22)`
  - `fill_wood_plank_tile(lyr, spec, material="wood", planks=4, seed=42)`
  - `fill_water_tile(lyr, spec, material="water", phase=frame_idx, seed=42)`（支持跨 4 帧循环动画）
- 跨地表过渡与自动拼装（Auto-Tile）：
  - `fill_transition_tile(lyr, spec, top_material="grass", bottom_material="stone", edge="top", seed=42)`
  - `proj = build_autotile_set("grass_cliff", 16, spec, fill_material="grass", bg_material="wood", mode="blob47")`（支持 `cardinal16` 16 块与 `blob47` 47 块标准位掩码图集，自动输出 Godot/Unity 规则元数据，并在自检图中生成 3×3 岛屿拼装实测预览）
- 等距 2.5D（Isometric）2:1 像素图块：
  - `draw_iso_diamond(lyr, spec, material="grass")` 与 `draw_iso_block(lyr, spec, top_material="grass", side_material="wood", height_px=10)`；创建等距图块时请关闭环形包裹（`toroidal=False`）并写入 `proj.metadata["isometric"] = info`，自检图将自动切换为 **3×3 交错菱形等距拼铺测试**。

## 3. 避免平铺格纹感与视觉疲劳
- 避免在单块地砖中放置孤立的超高对比度黑洞或极亮石子——在 `3x3` 拼铺下，它会立刻变成刺眼的波点网格重复图案。
- 叠加密度适中、低对比度的次级细节（例如在独立的 `moss` 图层上沿砖缝点缀 2–3px 的低对比青苔色块），并在 `3x3 Seamless Tile Test` 面板中反复核验。

## 4. 多变体图集与动态图块
- **静态多变体地砖**（例如干净、裂纹、青苔、碎石地板变体，或多 `seed` 等距草砖变体）：通过 `proj.add_frame()` 将每个变体作为一帧添加，且**不添加动画标签**——`export_png` 会将其打包为整齐的图集 `<name>_sheet.png`（47 块 Auto-Tile 等大图集可通过 `sheet_columns=8` 或 `proj.set_sheet_layout(columns=8)` 排成紧凑多行网格），并在 `<name>.json` 中记录各图块坐标。
- **动态图块**（例如 4 帧流动水面）：调用 `proj.add_tag("flow", 0, 3, loop=True)` 注册动画标签，`export_all()` 会额外输出逐帧 `frames/*.png` 与动态 `<name>.gif`。

## 5. 地图图块 QA 检查清单
- 目检 `_inspect/<category>_<name>_qa.png` 中的 **3x3 无缝拼铺/多变体混拼测试（3x3 Seamless / Mixed Variants Test）**，确认所有变体帧无接缝、无刺眼的重复斑点。
- 确认 `seam_report["seamless_ok"] == True`。
- 参考示例：`assets/examples/tile_dungeon_16x16.py`（俯视无缝变体）、`assets/examples/tile_iso_block_32x32.py`（等距 2.5D 方砖）。
