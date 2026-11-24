# 实战手册：道具与图标（`category="icons"`）

## 1. 构图与画幅留白
- 在画布四周预留 `1px` 安全边距（`64x64` 及以上预留 `2px`），防止 1px 外描边被画布边缘裁切。
- **45° 斜向构图**（手柄在左下、尖端在右上）能最大化利用对角线像素长度，最适合剑、法杖、战斧、魔杖和钥匙等长条形道具。
- **垂直对称构图**（结合 `mirror_x`）最适合药水瓶、盾牌、头盔、宝箱、书籍与宝石。

## 2. 图层堆叠与复杂轮廓构建
1. 引擎默认按语义角色排定图层 Z 序：`outline`（底层 `-100`）-> 实体结构层（如 `hilt`、`guard`、`blade`）-> `fx`（顶层 `+100`）。绘制完成后调用 `apply_outline(outline_lyr, frame.composite_solid(), spec)`，即可只为实体部件描边而不切穿发光特效。
2. 对称或雕花结构（如宝箱金边、头盔、盾纹）优先使用 `paint_ascii_canvas(..., mirror=True)` 快速定出精准像素轮廓，再用 `erase_rect` / `erase_circle` / `erase_polygon` 布尔挖出锁孔、血槽或战损缺口。

## 3. 材质感知着色工艺配方
- 先以各自材质的中间调铺出每个部件，并显式标注 `material="<mat>"`。
- 对各部件执行 `auto_shade_layer(part_lyr, spec)`——引擎会自动按材质名切换 `metallic`（金属高反差高光带+边缘反光）、`gem`（晶石/药水底部透光反亮）、`emissive`（内热外冷火焰）与 `matte`（木/皮/布柔和色块簇）。
- 为刃部添加锐利的**中脊明暗分界高光**（受光面用亮银/白，背光面用深钢色——形成经典的斜面金属对比）。
- 使用 `apply_layer_ao` 与 `apply_inner_outline` 强化部件交界与同层异材质拼缝。
- 在金属棱角或玻璃反光顶点处克制地点缀 1–2 个 `add_specular()` 高光点，并在最终描边前执行 `despeckle()`。

## 4. 图标 QA 检查清单
- 在 `_inspect/<category>_<name>_qa.png` 中核验深色与浅色双背景下 `1x` 尺寸的可读性。
- 检查**剪影测试（Silhouette Test）**面板：仅看纯黑剪影时，物品能否被一眼认出（如宝箱两侧提手与底脚）？
- 确认 `clipped_pixels == 0`。
- 参考示例：`assets/examples/icon_sword_32x32.py`（32×32 精绘武器）、`assets/examples/icon_potion_16x16.py`（16×16 微缩药水瓶）、`assets/examples/icon_treasure_chest_48x48.py`（48×48 高精宝箱，示范对称字符画布 + 布尔挖空 + 多材质着色）。
