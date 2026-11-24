# `pixel_forge` Python 引擎 API 参考

在每个资产绘制脚本顶部添加以下便携式技能路径解析代码（支持 `PIXEL_ART_FORGE_DIR` 环境变量、仓库相对路径以及主流客户端全局目录；也可直接用 `python scripts/cli.py scaffold ...` 一键生成，并用 `python scripts/cli.py run <script.py>` 免配置运行）：

```python
import os
import sys
from pathlib import Path

def _find_skill_scripts() -> Path:
    env_dir = os.environ.get("PIXEL_ART_FORGE_DIR")
    if env_dir:
        for cand in (Path(env_dir) / "scripts", Path(env_dir)):
            if (cand / "pixel_forge").is_dir():
                return cand
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        for rel in (
            "scripts",
            ".agents/skills/pixel-art-forge/scripts",
            ".claude/skills/pixel-art-forge/scripts",
            "skills/pixel-art-forge/scripts",
        ):
            cand = parent / rel
            if (cand / "pixel_forge").is_dir():
                return cand
    home = Path.home()
    for rel in (
        ".gemini/config/skills/pixel-art-forge/scripts",
        ".claude/skills/pixel-art-forge/scripts",
        ".codex/skills/pixel-art-forge/scripts",
        ".config/agents/skills/pixel-art-forge/scripts",
    ):
        cand = home / rel
        if (cand / "pixel_forge").is_dir():
            return cand
    raise RuntimeError("Could not locate pixel-art-forge/scripts; set PIXEL_ART_FORGE_DIR or use cli.py run.")

if str(_find_skill_scripts()) not in sys.path:
    sys.path.insert(0, str(_find_skill_scripts()))

from pixel_forge import (
    PixelProject, CharacterRig, PartTransform, load_spec, save_spec, resolution_budget,
    line, rect, rounded_rect, circle, ellipse, polygon, bezier,
    capsule, tapered_stroke, flood_fill, mirror_x, stamp_pattern, paint_ascii_canvas,
    erase_rect, erase_circle, erase_polygon, cutout_mask,
    auto_shade_layer, apply_layer_ao, apply_outline, apply_inner_outline, apply_pixel_aa,
    add_specular, dither_gradient_fill, shaded_sphere, shaded_cylinder,
    despeckle, check_nine_slice_consistency, fill_stone_brick_tile, fill_grass_tile,
    fill_wood_plank_tile, fill_water_tile, draw_nine_slice_panel, draw_smear_arc,
    idle_cycle_poses, walk_cycle_poses, attack_swing_poses,
)
from pixel_forge.exporters import export_all
```

---

## 1. 风格规范与调色板（`spec.py`、`palette.py`）
- `spec = load_spec("pixel_assets/pixel_spec.json")` — 加载已锁定的项目风格规范（也可传入内置预设名称：`"topdown_rpg"`、`"side_platformer"`、`"dark_dungeon"`、`"retro_handheld"`）。
- `spec.ramp("steel") -> list[int]` — 获取材质对应的调色板索引列表，按从最暗（`0`）到最亮（`-1`）排序。
- `spec.color("steel", shade=2) -> int` — 获取指定明度档位的调色板索引（自动夹紧越界索引，`0` 为最暗，`-1` 为最亮）。
- `spec.register_material_from_hex("emerald", "#2eb872", steps=4, lock_to_palette=True)` — 基于十六进制基准色注册一条带色相偏移（Hue-Shifted）的新材质色带。
- `spec.remap_to_palette(new_pal)` — 将已有材质色带保序无塌缩重映射到新调色板。
- `build_custom_palette_spec(base_spec, ["hero:#3a6ea5", "gem:#d9534f"])` — 由用户主色自动构建自定义 Hue-Shifted 调色板并补齐标准材质。
- `budget = resolution_budget(width, height)` — 查询目标尺寸对应的细节预算档位与推荐明度阶数。

## 2. 项目、帧与索引图层（`canvas.py`）
- `proj = PixelProject(name, width, height, spec, category="icons", toroidal=False, default_duration_ms=150)`
  - `category`：`"icons" | "characters" | "tilesets" | "ui"`
  - `width`、`height`：严格锁定的正整数逻辑像素宽高。
- `lyr = proj.layer("blade", frame_idx=0, z_index=None)` — 获取或创建语义化索引图层 `IndexedLayer`（默认按规范角色自动分层：`shadow` `-200` -> `outline` `-100` -> 普通实体层 `0` -> `fx`/`vfx`/`glow` `+100`，避免描边切穿顶层特效）。
- `fr.composite_solid()` — 仅合成可见的实体部件图层（自动跳过 `outline`、`fx`、`shadow`），可直接传给 `apply_outline`。
- `fr = proj.add_frame(duration_ms=140, clone_from=None)` — 追加新动画帧。
- `proj.add_tag("idle", from_frame=0, to_frame=3, direction="forward", loop=True)` — 注册动画片段标签。
- `proj.set_pivot(x, y)` / `proj.set_nine_slice(left, top, right, bottom)` — 设置锚点坐标或 9-Slice 拉伸边距。
- `proj.set_sheet_layout(columns=None, split_rows_by_tag=False)` — 配置多帧雪碧图打包布局（按固定列数网格换行，或按动画 Tag 一行一个动作导出标准角色表）。
- `lyr.set_px(x, y, color_idx, material="steel")` — 写入单个像素并校验索引有效性；越界时自动记录 `clipped_count`。
- `with lyr.lock_alpha():` — 开启 Alpha Lock 透明锁定遮罩，仅在已有不透明像素内绘制纹理、条纹或高光，绝不破坏剪影。
- `lyr.remap_material({"steel": "gold"}, spec)` / `proj.remap_material({"cloth_red": "cloth_blue"}, reoutline=True)` — 基于 `material_map` 按明度比例无损换色（Palette Swap），项目级调用支持自动重绘 Sel-Out 描边。
- `lyr.rotate(angle_deg, pivot=None)` — RotSprite（Scale3x + 反向采样）像素级干净旋转（90°/180°/270° 走精确无损整数旋转路径）。
- `lyr.squash_stretch(sx=1.0, sy=1.0, anchor=None)` — 保持 1× 整数网格的局部挤压拉伸（默认以底部中心为锚点）。
- `lyr.blit(src_layer, ox=0, oy=0)` / `lyr.shift(dx, dy)` / `lyr.flip_x()` / `lyr.bbox()` — 图层合成、平移、水平翻转与边界框计算。

## 3. 像素级绘制原语（`primitives.py`）
所有绘制原语均支持 `material: str | None = None` 参数，以便下游的 `auto_shade_layer` 与 `apply_outline` 准确识别每个像素所属的材质色带：
- `line(lyr, x0, y0, x1, y1, color, material=None, clean_doubles=True)`
- `rect(lyr, x, y, w, h, color, fill=True, material=None)`
- `rounded_rect(lyr, x, y, w, h, radius, color, fill=True, material=None)`
- `circle(lyr, cx, cy, r, color, fill=True, material=None)`
- `ellipse(lyr, x0, y0, x1, y1, color, fill=True, material=None)`
- `polygon(lyr, points, color, fill=True, material=None)`
- `bezier(lyr, p0, p1, p2, color, material=None, clean_doubles=True)`
- `capsule(lyr, x0, y0, x1, y1, radius, color, material=None)`
- `tapered_stroke(lyr, points, r_start, r_end, color, material=None)`
- `flood_fill(lyr, x, y, color, material=None)`
- `mirror_x(lyr, axis_x=None)` — 将左半边像素沿对称轴镜像到右半边。
- `stamp_pattern(lyr, ox, oy, pattern_lines, char_map)` — 盖印局部 ASCII 像素点阵（`'.'` 或 `' '` 表示透明；映射值可为 `idx` 或 `(idx, material)`）。
- `paint_ascii_canvas(lyr, spec, grid, legend, ox=0, oy=0, mirror=False)` — 用语义化字符画布快速雕刻复杂轮廓（图例支持 `"gold"`、`"steel:3"`、`"erase"`；开启 `mirror=True` 自动镜像生成左右对称造型）。
- `erase_rect(lyr, x, y, w, h)` / `erase_circle(lyr, cx, cy, r)` / `erase_polygon(lyr, points)` / `cutout_mask(target_lyr, mask_lyr)` — 布尔减法挖空原语（轻松制作锁孔、面甲眼缝、战损缺口等负空间细节）。

## 4. 着色、体积原语、AO、描边与像素清理（`shading.py`、`cleanup.py`）
- `auto_shade_layer(lyr, spec, material=None, dither=None, rim_light=True, profile=None)` — 定向 2.5D 材质感知自动着色（`profile` 默认 `'auto'` 按材质名自动区分 `'matte'` 柔和漫反射、`'metallic'` 高反差金属高光带与边缘反光、`'gem'` 晶石透光反亮、`'emissive'` 内热外冷自发光）。
- `shaded_sphere(lyr, cx, cy, r, spec, material, dither=None, specular=True)` — 按真实 3D 球面法线与主光源绘制带高光的球体/宝石/药水瓶。
- `shaded_cylinder(lyr, x, y, w, h, spec, material, axis="vertical", dither=None, specular=True)` — 按 3D 柱面法线绘制石柱、剑柄、木桶或金属杆。
- `apply_layer_ao(target_lyr, occluder_lyr, spec, step=1, offset=None)` — 计算遮挡图层沿 `-spec.light_dir` 投射到目标图层上的层间接触阴影。
- `apply_inner_outline(lyr, spec, step=1)` — 在同一图层不同材质相邻交界线的背光侧加深 1px，强化材质边界分隔。
- `apply_pixel_aa(lyr, spec, material=None, min_run=2)` — 严格色板内的克制斜边抗锯齿（不向透明区扩散，推荐 48×48+ 高精素材使用）。
- `apply_outline(outline_lyr, source_lyr, spec, mode=None, corners=None, lit_boost=None)` — 围绕 `source_lyr` 生成 1px Sel-Out / 纯黑 / 彩色描边。
- `add_specular(lyr, x, y, spec, material=None)` — 点缀锐利的高光像素点。
- `dither_gradient_fill(lyr, x, y, w, h, ramp, direction="vertical", dither="bayer2x2", material=None)` — 填充带 Bayer 有序抖动的色带渐变区域。
- `despeckle(lyr, preserve_brightest=True, brightest_indices=None)` — 清理色块内部的孤立杂点像素。
- `check_nine_slice_consistency(lyr, margins)` — 校验 9-Slice 九宫格可拉伸边带沿拉伸轴是否 100% 像素一致。

## 5. 角色父子骨架与程序化图块/UI（`rig.py`、`procedural.py`）
- `rig = CharacterRig(width, height, len(spec.palette))`
  - `part_lyr = rig.add_part("head", z_order=30, parent="torso", pivot=(16, 12))` — 注册角色部件及其层级顺序、父节点绑定与旋转枢轴（完整正向运动学：父节点的平移、翻转、挤压拉伸与关节旋转自动传递至子节点，单次重采样合成无脱手）。
  - `rig.render_to_frame(frame, pose={"torso": (0, 1), "weapon": PartTransform(dx=0, rotate_deg=45)}, overrides=None, hidden=())` — 支持 `(dx, dy)` 元组或 `PartTransform`（平移、翻转、RotSprite 旋转、挤压拉伸）。
- `idle_cycle_poses(frames=4, duration_ms=190, hierarchical=True)` — 内置呼吸待机姿态序列。
- `walk_cycle_poses(direction="down", frames=4, duration_ms=130)` — 内置 4 方向（`down`/`up`/`left`/`right`）行走循环姿态序列。
- `attack_swing_poses(direction="right", frames=4, hierarchical=True)` — 内置蓄力→旋转斩击→收招攻击姿态序列（默认适配 `torso -> front_arm -> weapon` 父子链）。
- `draw_smear_arc(lyr, cx, cy, r_inner, r_outer, start_deg, end_deg, ramp, material=None)` — 绘制武器挥砍残影弧线。
- `fill_stone_brick_tile(lyr, spec, material="stone", rows=4, cols=2, seed=42, weathering=0.25)` — 生成无缝石砖地砖。
- `fill_grass_tile(lyr, spec, material="grass", seed=42, tuft_density=0.22)` — 生成无缝草地地砖。
- `fill_wood_plank_tile(lyr, spec, material="wood", planks=4, seed=42)` — 生成无缝木地板地砖。
- `fill_water_tile(lyr, spec, material="water", phase=0, seed=42)` — 生成可循环动画的无缝水面地砖。
- `fill_transition_tile(lyr, spec, top_material="grass", bottom_material="stone", edge="top", thickness=None, seed=42)` — 生成沿边缘无缝闭合的跨地表有机过渡块。
- `proj = build_autotile_set(name, tile_size, spec, fill_material="grass", bg_material="wood", mode="blob47"|"cardinal16", seed=42)` — 一键生成 16 块正交或 47 块 Blob Auto-Tile 图集，自动附带 Godot Terrain / Unity RuleTile 位掩码元数据与 3×3 岛屿拼装自检。
- `draw_iso_diamond(lyr, spec, material="grass", top_y=0, width_px=None, seed=42)` / `draw_iso_block(lyr, spec, top_material="grass", side_material="wood", height_px=None, seed=42, outline=True)` — 生成严格 2:1 像素网格的等距 2.5D 菱形地表与立体方砖。
- `margins = draw_nine_slice_panel(lyr, spec, frame_material="wood", bg_material="stone", accent_material="gold", border=5)` — 绘制标准 9-Slice UI 面板并返回边距四元组。
- `draw_ui_button(lyr, spec, state="normal"|"hover"|"pressed"|"disabled", ...)` / `build_button_states(name, w, h, spec, ...)` — 绘制单态或 4 状态 UI 按钮图集（自动设置 9-Slice 与 `ui_states` 元数据）。
- `draw_health_bar(lyr, spec, ratio=0.75, frame_material="steel", fill_material="cloth_red", segmented=0)` — 绘制立体 RPG 血条/蓝条/经验条。
- `margins = draw_item_slot(lyr, spec, frame_material="wood", bg_material="stone", selected=False, rarity_material=None)` — 绘制内凹物品栏槽位（支持选中 L 角框与品质光环）。

## 6. 统一导出入口（`exporters/__init__.py`）
```python
result = export_all(
    proj,
    assets_root="pixel_assets",
    source_script=__file__,
    generate_qa=True,
    update_contact_sheet=True,
)
print(result["qa"])
```
- **静态资产**：输出 `1x PNG`、Godot/Unity 兼容 `JSON`、`.aseprite` 工程文件以及 `_inspect/<category>_<name>_qa.png`。
- **动画资产**（`len(frames) > 1` 且非静态地砖）：额外输出逐帧独立 PNG（`frames/<name>_000.png` 等）、按序排列的雪碧图（`<name>_sheet.png`）以及严格采用锁定色板的透明背景动态 GIF（`<name>.gif`）。
- 每次导出均会自动更新 `catalog.json` 并刷新 `_inspect/project_contact_sheet.png`。

## 7. 常用 CLI 提效命令（`<SKILL_DIR>/scripts/cli.py`）
- `python "<SKILL_DIR>/scripts/cli.py" init-spec --preset topdown_rpg [--palette sweetie16 | --custom-colors "hero:#3a6ea5,ruby:#c93b4b"] [--perspective topdown_3_4] [--light-dir -1,-1] [--ppu 32] [--max-colors 16]`
- `python "<SKILL_DIR>/scripts/cli.py" scaffold --category icons --name fire_orb --width 32 --height 32` — 在当前工作区 `pixel_assets/src/` 下一键生成标准可运行源码模板。
- `python "<SKILL_DIR>/scripts/cli.py" run pixel_assets/src/icons/fire_orb_32x32.py -- --out pixel_assets` — 自动注入引擎路径并运行任意资产脚本。
- `python "<SKILL_DIR>/scripts/cli.py" recolor --script pixel_assets/src/icons/flame_sword_32x32.py --map "steel=gold,fire=magic" --name arcane_sword` — 一键生成换色变体（自动重绘 Sel-Out 并导出全套产物）。
- `python "<SKILL_DIR>/scripts/cli.py" preview --png pixel_assets/exports/icons/flame_sword/flame_sword.png --scale 8` — 导出整数倍 Nearest 无损放大展示图。
