# 实战手册：角色与帧动画（`category="characters"`）

## 1. 比例规划与锚点锁定
- 默认锚点（Pivot）位于**脚底居中** `(W // 2, H - 1)`——所有落地帧中，角色双脚必须稳定落于 `y = H - 2`（底部 1px 描边落在 `y = H - 1`），确保导入游戏引擎后不会出现悬空或上下抖动。
- **经典 32×32 Q 版 / RPG 比例参考**：
  - 顶部边距 + 羽饰/头冠：`y = 2..4`
  - 头部 / 头盔：`y = 5..14`（约占总高 35%–40%——像素美术中略微偏大的头部辨识度最高）
  - 躯干 / 铠甲：`y = 15..22`
  - 腿部 / 战靴：`y = 23..29`（底部描边位于 `y = 30`）
  - 武器 / 盾牌：布置在清晰的侧向剪影区域，避免与躯干粘连成一团。
- **经典 16×16 迷你比例参考**：
  - 头部：`y = 2..7`，躯干：`y = 8..11`，腿部：`y = 12..14`。

## 2. 模块化父子锚点骨架工作流（`CharacterRig`）
务必使用 `CharacterRig` 搭建角色，让每个身体部位在每一帧动画中都保持独立的语义图层：
- 从后到前的 Z 轴层级顺序：`cape` (5) -> `back_arm` (10) -> `back_leg` (15) -> `torso` (20) -> `front_leg` (25) -> `head` (30) -> `front_arm` (35) -> `weapon` (40) -> `fx` (45)。
- 推荐使用**父子层级绑定**（如 `head`、`front_arm`、`back_arm`、`cape` 绑定 `parent="torso"`，`weapon` 绑定 `parent="front_arm"` 并设置握柄 `pivot`）。`CharacterRig` 支持完整的正向运动学传递：父节点的平移、翻转（如 `torso` 设 `flip_x=True` 一键将朝右骨架镜像为朝左姿态）和关节旋转会自动合成到子部件，单次重采样无脱手；双腿保持独立以锁死脚底接地。
- 注意同一 `PixelProject` 内所有帧共享全局图层上下顺序（Z 序）：制作 4 方向角色时，避免让同名图层在正面帧垫底而在背面帧置顶（可将正面后披风与背面主斗篷区分处理），并注意面朝南/面朝北时手持武器的左右屏幕手性反转。
- 多动作或 4 方向角色推荐调用 `proj.set_sheet_layout(split_rows_by_tag=True)`，使 `<name>_sheet.png` 自动按动作 Tag 分行排列（如 4 行 × 4 列标准 RPG 角色行走图）。
- 先对骨架的各个部件一次性调用 `auto_shade_layer()` 完成定向着色，并通过 `stamp_pattern()` 添加面部或面甲等精细特征。
- 通过 `rig.render_to_frame(frame, pose={...}, overrides={...})` 渲染每一帧姿态（支持 `(dx, dy)` 元组或 `PartTransform` 实现武器 RotSprite 旋转、翻转与挤压拉伸），也可直接复用内置的 `idle_cycle_poses()`、`walk_cycle_poses(direction="down|up|left|right")` 与 `attack_swing_poses()`，再逐帧施加层间接触阴影（如 `apply_layer_ao(torso, head, spec)`）并生成干净的逐帧 `outline` 描边图层（`apply_outline`）。

## 3. 动画节奏与姿态公式
- **待机（Idle，4 帧，180–220ms/帧，循环）**：
  - F0：自然站立姿态
  - F1：轻微呼吸下沉（`head: (0, 1)`、`torso: (0, 1)`、`front_arm: (0, 1)`、`weapon: (0, 1)`，双腿保持接地不动）
  - F2：停顿/披风微动（`head: (0, 1)`、`cape: (1, 1)`）
  - F3：回弹至自然站立（`cape: (0, 0)`）
- **行走（Walk，4 帧，120–140ms/帧，循环）**：
  - F0（左脚着地 Contact L）：`front_leg: (-2, 0)`、`back_leg: (2, 0)`、`front_arm: (1, 0)`、`back_arm: (-1, 0)`，身体 `dy=0`
  - F1（迈步过渡 Passing）：双腿居中（`front_leg: (0, -1)` 抬起），`torso/head` 向上颠起 `(0, -1)`
  - F2（右脚着地 Contact R）：`front_leg: (2, 0)`、`back_leg: (-2, 0)`、`front_arm: (-1, 0)`、`back_arm: (1, 0)`，身体 `dy=0`
  - F3（迈步过渡 Passing）：双腿居中（`back_leg: (0, -1)` 抬起），`torso/head` 向上颠起 `(0, -1)`
- **攻击（Attack，3–4 帧，有效打击帧快速 70–90ms，`loop=False`）**：
  - 蓄力前摇（向后引武器） -> 爆发挥砍（在 `fx` 图层调用 `draw_smear_arc` 绘制刀光残影） -> 收招缓冲与回位。

## 4. 质量验收与动画导出检查清单
- 通过 `proj.add_tag("idle", 0, 3, loop=True)` 等方式注册全部动画标签。
- `export_all()` 会自动输出：
  - `<name>_sheet.png`（按从左到右顺序排列的整张雪碧图，可直接导入游戏引擎）
  - `frames/<name>_000.png` ... `frames/<name>_00N.png`（逐帧独立 1x 原始 PNG）
  - `<name>.gif`（严格使用锁定色板、保留逐帧时长的透明背景动态 GIF）
  - `<name>.json` 与 `<name>.aseprite`
- 重点检查 `_inspect/<category>_<name>_qa.png` 中的**动画帧预览（Animation Frames）**、**洋葱皮叠加（Onion Skin）**以及当后续动作帧出现触边/高噪点时自动生成的 **`[ALERT]` 关键帧坐标标尺放大面板**。
- 确认脚底锚点漂移告警数为 0，顶部预留至少 `2px` 边距以容纳行走颠起 `dy=-1` 与 `1px` 描边。
- 参考示例：`assets/examples/char_knight_32x32_anim.py`（8 帧待机+行走骑士）、`assets/examples/char_mage_4dir_32x32.py`（4 方向 16 帧按 Tag 分行打包法师）。
