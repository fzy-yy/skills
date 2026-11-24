"""Benchmark Example 5: 16x16 Micro Health Potion Icon (Low-Res 2-3 Shade Budget + Alpha Lock)."""

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

from pixel_forge import (
    PixelProject,
    add_specular,
    apply_outline,
    load_spec,
    rect,
    shaded_sphere,
)
from pixel_forge.exporters import export_all


def build_project(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    # 16x16 micro icon budget: bold flask silhouette, 1px safe margin, 2-3 shades per material
    proj = PixelProject("health_potion", 16, 16, spec, category="icons")
    f0 = proj.frame(0)

    outline_lyr = f0.layer("outline")
    bottle_lyr = f0.layer("bottle")
    cork_lyr = f0.layer("cork")

    # 1. Bulbous glass flask filled with crimson potion (y=6..13, x=4..11)
    shaded_sphere(bottle_lyr, 7.5, 9.5, 3.8, spec, material="cloth_red", specular=False)
    # Alpha Lock: paint clear glass top air-gap & bright meniscus strictly inside bottle silhouette
    with bottle_lyr.lock_alpha():
        rect(bottle_lyr, 4, 6, 8, 2, spec.color("steel", 4), fill=True, material="steel")
        rect(bottle_lyr, 5, 8, 6, 1, spec.color("cloth_red", 3), fill=True, material="cloth_red")
    # Bottle neck & rim (y=4..6, x=6..9)
    rect(bottle_lyr, 6, 4, 4, 2, spec.color("steel", 4), fill=True, material="steel")
    bottle_lyr.set_px(9, 4, spec.color("steel", 2), "steel")
    bottle_lyr.set_px(9, 5, spec.color("steel", 2), "steel")
    # Crisp glass reflection glint on lit top-left curve
    add_specular(bottle_lyr, 5, 9, spec, "steel")
    add_specular(bottle_lyr, 5, 10, spec, "cloth_red")

    # 2. Wooden cork stopper (y=2..3, x=6..9)
    rect(cork_lyr, 6, 2, 4, 2, spec.color("wood", 3), fill=True, material="wood")
    cork_lyr.set_px(6, 2, spec.color("wood", 4), "wood")
    cork_lyr.set_px(9, 3, spec.color("wood", 1), "wood")

    solid = bottle_lyr.copy()
    solid.blit(cork_lyr)
    apply_outline(outline_lyr, solid, spec)
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
