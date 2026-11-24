"""Benchmark Example 3: 16x16 Seamless Dungeon Stone Floor Tileset (2 Variants, Toroidal)."""

from __future__ import annotations

import argparse
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
        for rel in ("scripts", ".agents/skills/pixel-art-forge/scripts", ".claude/skills/pixel-art-forge/scripts", "skills/pixel-art-forge/scripts"):
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
    return home / ".gemini" / "config" / "skills" / "pixel-art-forge" / "scripts"


SKILL_SCRIPTS = _find_skill_scripts()
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from pixel_forge import (
    PixelProject,
    fill_stone_brick_tile,
    load_spec,
)
from pixel_forge.exporters import export_all


def build_dungeon_tile(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    # Locked 16x16 seamless tile project (toroidal=True automatically enabled for tilesets)
    proj = PixelProject("dungeon_floor", 16, 16, spec, category="tilesets")

    # Tile variant 0: Clean weathered dungeon stone masonry
    f0 = proj.frame(0)
    fill_stone_brick_tile(f0.layer("stone"), spec, material="stone", rows=4, cols=2, seed=101, weathering=0.25)

    # Tile variant 1: Mossy cracked masonry variant (packed into same TileSet atlas!)
    f1 = proj.add_frame()
    fill_stone_brick_tile(f1.layer("stone"), spec, material="stone", rows=4, cols=2, seed=202, weathering=0.32)
    moss = f1.layer("moss")
    # Subtle clustered moss creeping cleanly along mortar joints
    moss_coords = [
        (3, 3, 1), (4, 3, 2), (5, 3, 1), (4, 4, 1),
        (11, 11, 1), (12, 11, 2), (12, 12, 1),
    ]
    for mx, my, shade in moss_coords:
        moss.set_px(mx, my, spec.color("grass", shade), "grass")

    return proj


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="pixel_assets")
    args = parser.parse_args()
    root = Path(args.out)
    proj = build_dungeon_tile(root)
    res = export_all(proj, assets_root=root, source_script=__file__)
    print("QA:", res["qa"])
    print("Inspection sheet:", res["inspection_sheet"])


if __name__ == "__main__":
    main()
