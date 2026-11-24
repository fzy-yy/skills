# 实战手册：UI 元素与 9-Slice 面板（`category="ui"`）

## 1. 9-Slice 工程约束
- 务必调用 `proj.set_nine_slice(left, top, right, bottom)`，使九宫格拉伸边距自动写入：
  - `.aseprite` 的切片区块（Slice Chunk `0x2022`）
  - `.json` 元数据（`meta.slices`、`unity.nineSliceLBRT` 与 `godot.nineSliceLTRB`）
- **核心不变量**：中间可拉伸区域（`x in [left, W - right)` 与 `y in [top, H - bottom)`）必须沿其拉伸方向保持 **100% 像素一致**：
  - 上下边框中间段：`[left, W - right)` 范围内的每一列必须完全相同，确保水平拉伸时不产生断裂或伪影。
  - 左右边框中间段：`[top, H - bottom)` 范围内的每一行必须完全相同，确保垂直拉伸时边缘依然锐利。
  - 中心填充区域：使用纯色或可干净重复的平铺纹理。
- 四角铆钉、螺钉、金色花纹或圆角倒角必须严格限制在 **4 个固定角区域之内**。

## 2. 内置 UI 组件生成器（`procedural.py`）
- **9-Slice 面板**：`margins = draw_nine_slice_panel(lyr, spec, frame_material="wood", bg_material="stone", accent_material="gold", border=5, corner_radius=2)`，随后调用 `proj.set_nine_slice(*margins)`。
- **多状态按钮**：`proj = build_button_states("rpg_button", 48, 18, spec)` 一键生成 4 帧静态状态图集（`normal` / `hover` / `pressed` / `disabled`，自动设置 9-Slice 与 `ui_states` 元数据，不会误导出动态 GIF），或用 `draw_ui_button(lyr, spec, state="hover")` 单独绘制指定状态。
- **血条 / 蓝条 / 经验条**：`draw_health_bar(lyr, spec, ratio=0.75, frame_material="steel", fill_material="cloth_red", segmented=4)`。
- **物品栏槽位**：`margins = draw_item_slot(lyr, spec, selected=True, rarity_material="magic")`。

## 3. 斜面立体感与文字可读性
- 遵循全局主光源 `spec.light_dir`：顶部与左侧外斜面受光提亮（`ramp[-1]`），底部与右侧外斜面背光压暗（`ramp[1]`）。
- 面板内凹框反向处理光照（顶部与左侧施加内阴影，底部与右侧保留微弱受光反边），打造一眼可辨的凹陷对话框/背包面板层次。
- 中心内容区保持低噪点、低对比的沉稳底色，确保白色或米黄色像素文字叠加在上方清晰易读。

## 4. UI QA 检查清单
- 确认 `qa["nine_slice_report"]["consistent"] == True`（引擎会自动逐列/逐行校验可拉伸边带像素一致性，一旦四角装饰越界混入拉伸带将立即告警）。
- 检查 `_inspect/<category>_<name>_qa.png` 中的 **9-Slice 拉伸测试（宽横条 Wide Bar 与高卡片 Tall Card）**——四个角必须保持 1:1 锐利不变形，中间边条拉伸无缝自然。
- 检查坐标放大图上的青色 9-Slice 辅助参考线，确认其干净落在所有四角装饰元素之外。
- 参考示例：`assets/examples/ui_panel_9slice.py`（9-Slice 面板）、`assets/examples/ui_hud_pack.py`（4 态按钮 / 血条 / 选中态物品槽）。
