# Agent Skills 个人技能仓库

本仓库用于开发、维护与沉淀遵循 [Agent Skills 规范](https://agentskills.io/specification) 的可复用 AI 编码助手技能（Skills）。每个正式技能在 `skills/` 下保持独立自包含，便于按需安装到不同客户端环境中使用。

## 仓库目录结构

```text
.
├── skills/                 # 正式技能目录（每个子目录为独立可分发的技能单元）
│   └── pixel-art-forge/    # 纯 Python 程序化像素美术生产技能
├── docs/                   # 仓库级与单技能架构设计、开发共识文档（不随技能分发）
├── template/               # 新建技能使用的基础模板（不作为正式技能安装）
├── AGENTS.md               # 仓库维护与技能编写规范
└── LICENSE                 # 仓库开源许可证
```

## 技能清单

| 技能名称 | 目录路径 | 功能概述与适用场景 | 运行依赖 |
| :--- | :--- | :--- | :--- |
| [`pixel-art-forge`](./skills/pixel-art-forge/SKILL.md) | `skills/pixel-art-forge/` | 纯 Python 程序化像素美术生产技能。支持交互式风格共识澄清、全局调色板与材质色带强校验、分辨率细节预算，覆盖道具/图标、角色与多方向帧动画、无缝/等距地图图块与 Auto-Tile、9-Slice UI 组件，自动完成程序硬检与坐标标尺视觉 QA，导出 `1x PNG`、逐帧图与有序/网格雪碧图、透明背景 `GIF`、Godot/Unity 兼容 `JSON` 及原生 `.aseprite` 工程文件。 | Python 3.10+、`Pillow` |

## 安装方式

仓库根目录下的 `skills/` 仅用于源码管理，不会被各客户端自动全局加载。请将单个技能目录 `skills/<skill-name>` 复制或建立目录软链接（Windows 下推荐使用 Junction）到目标客户端的技能发现路径：

### 1. 全局安装（跨项目可用）

以 `pixel-art-forge` 为例，按所使用的客户端选择对应目标目录：

- **Antigravity**：`~/.gemini/config/skills/pixel-art-forge`
- **Claude Code**：`~/.claude/skills/pixel-art-forge`
- **Codex**：`~/.codex/skills/pixel-art-forge`

**Windows PowerShell（创建目录联接，便于同步更新）：**

```powershell
# 示例：链接到 Antigravity 全局技能目录
New-Item -ItemType Directory -Force -Path "$HOME\.gemini\config\skills" | Out-Null
New-Item -ItemType Junction -Path "$HOME\.gemini\config\skills\pixel-art-forge" -Target "$PWD\skills\pixel-art-forge"
```

**macOS / Linux：**

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/pixel-art-forge" ~/.claude/skills/pixel-art-forge
```

### 2. 项目级安装（仅当前项目可用）

也可将 `skills/<skill-name>` 复制或链接到目标业务仓库的客户端技能目录（如 `<project>/.agents/skills/<skill-name>` 或 `<project>/.claude/skills/<skill-name>`，具体发现路径以对应客户端官方文档为准）。

## 环境准备与使用说明

### 安装 `pixel-art-forge` 运行依赖

```powershell
python -m pip install Pillow
```

### 触发方式

安装完成后，在任意游戏或美术工程工作区中直接向 AI 助手描述像素资产需求即可自动匹配触发（部分客户端也支持通过 `/pixel-art-forge` 显式调用）：

- **宽泛需求（自动进入阶段 0 交互澄清）**：“帮我画一把像素风火焰长剑”、“给我的 RPG 做一个主角骑士”
- **明确规格（走快速通道直接出图）**：“用 `endesga32` 色板画一个 `32x32` 的暗黑地牢宝箱图标，左上光源，Sel-Out 描边，按推荐直接画”

生成的绘制源码、锁定风格契约（`pixel_spec.json`）、游戏引擎交付产物与视觉 QA 检验图会统一输出在当前工作区的 `pixel_assets/` 目录下。

### 本地校验与自测

在仓库根目录下可执行以下命令运行自动化测试与内置 CLI：

```powershell
# 运行引擎、导出器与 CLI 自动化测试（-B 避免生成字节码缓存）
python -B skills/pixel-art-forge/scripts/test_pixel_forge.py

# 查看内置调色板与分辨率细节预算
python -B skills/pixel-art-forge/scripts/cli.py list-palettes
python -B skills/pixel-art-forge/scripts/cli.py budget --width 32 --height 32
```

## 许可证

本仓库采用 [LICENSE](./LICENSE) 许可证发布。
