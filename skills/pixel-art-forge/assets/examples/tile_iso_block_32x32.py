"""Benchmark Example 6: 32x32 Isometric 2.5D Grass Block Tileset (3 Natural Variants, 2:1 Pixel Grid)."""

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
    return home / ".gemini" / "config" / "skills" / "pixel-art-forge" / "scripts"


SKILL_SCRIPTS = _find_skill_scripts()
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from pixel_forge import PixelProject, despeckle, draw_iso_block, load_spec
from pixel_forge.exporters import export_all


def build_project(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    # 3 static isometric variants break up tiling repetition across staggered 3x3 maps
    proj = PixelProject("iso_grass_block", 32, 32, spec, category="tilesets", toroidal=False)
    seeds = (42, 137, 271)
    info = {}
    bright_set = {spec.color("grass", -1), spec.color("wood", -1)}
    for idx, seed in enumerate(seeds):
        fr = proj.frame(0) if idx == 0 else proj.add_frame()
        lyr = fr.layer("block")
        info = draw_iso_block(
            lyr,
            spec,
            top_material="grass",
            side_material="wood",
            height_px=10,
            seed=seed,
            outline=True,
        )
        despeckle(lyr, preserve_brightest=True, brightest_indices=bright_set)

    proj.metadata["isometric"] = info
    proj.set_pivot(16, 16)
    return proj


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="pixel_assets")
    args = parser.parse_args()
    root = Path(args.out)
    proj = build_project(root)
    res = export_all(proj, assets_root=root, source_script=__file__)
    print("QA:", res["qa"])
    print("Inspection sheet:", res["inspection_sheet"])


if __name__ == "__main__":
    main()
