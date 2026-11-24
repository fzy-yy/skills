"""Benchmark Example 1: 32x32 Flame-Enchanted Longsword Icon (Diagonal 45° Composition)."""

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
    add_specular,
    apply_layer_ao,
    apply_outline,
    auto_shade_layer,
    circle,
    despeckle,
    line,
    load_spec,
    polygon,
    stamp_pattern,
)
from pixel_forge.exporters import export_all


def build_flame_sword(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    # Locked 32x32 canvas, 1px safe margin for Sel-Out outline
    proj = PixelProject("flame_sword", 32, 32, spec, category="icons")
    f0 = proj.frame(0)

    # Coordinate budget (diagonal bottom-left -> top-right):
    #   Pommel: (4..7, 24..27)
    #   Grip:   (6..10, 21..25)
    #   Guard:  (8..17, 14..23) perpendicular diagonal
    #   Blade:  (13..28, 3..18) sharp tip at (28, 3)

    outline_lyr = f0.layer("outline")
    hilt_lyr = f0.layer("hilt")
    blade_lyr = f0.layer("blade")
    guard_lyr = f0.layer("guard")
    fx_lyr = f0.layer("fx")

    # 1. Hilt (leather grip + gold pommel)
    for t in range(6):
        gx = 6 + t
        gy = 25 - t
        hilt_lyr.set_px(gx, gy, spec.color("leather", 2), "leather")
        hilt_lyr.set_px(gx + 1, gy, spec.color("leather", 1), "leather")
        hilt_lyr.set_px(gx, gy - 1, spec.color("leather", 3), "leather")
    # Leather cross-wrap accents
    hilt_lyr.set_px(8, 23, spec.color("leather", 0), "leather")
    hilt_lyr.set_px(10, 21, spec.color("leather", 0), "leather")
    # Gold pommel
    circle(hilt_lyr, 5, 26, 1.8, spec.color("gold", 2), fill=True, material="gold")
    auto_shade_layer(hilt_lyr, spec, rim_light=True)
    add_specular(hilt_lyr, 4, 25, spec, "gold")

    # 2. Steel Blade (crisp beveled diamond profile along 45° axis)
    blade_poly = [
        (13, 16),  # upper-left root
        (24, 5),   # upper-left shoulder near tip
        (28, 3),   # razor tip
        (26, 7),   # lower-right shoulder near tip
        (15, 18),  # lower-right root
    ]
    polygon(blade_lyr, blade_poly, spec.color("steel", 3), fill=True, material="steel")
    # Manual crisp pixel-art sword bevel: top-left half bright silver, bottom-right half cool shadow steel!
    for i in range(13):
        bx = 14 + i
        by = 17 - i
        # Center spine ridge (bright)
        blade_lyr.set_px(bx, by, spec.color("steel", 4), "steel")
        # Upper-left lit cutting edge
        blade_lyr.set_px(bx - 1, by - 1, spec.color("steel", 5), "steel")
        if i % 3 == 0:
            blade_lyr.set_px(bx - 1, by, spec.color("steel", 5), "steel")
        else:
            blade_lyr.set_px(bx - 1, by, spec.color("steel", 4), "steel")
        # Lower-right shaded bevel
        blade_lyr.set_px(bx + 1, by, spec.color("steel", 2), "steel")
        blade_lyr.set_px(bx + 1, by + 1, spec.color("steel", 1), "steel")

    # Razor tip glint
    blade_lyr.set_px(27, 4, spec.color("steel", 5), "steel")
    add_specular(blade_lyr, 28, 3, spec, "steel")
    add_specular(blade_lyr, 22, 8, spec, "steel")

    # 3. Ornate Golden Crossguard (perpendicular to blade with ruby center gem)
    guard_pts = [
        (8, 15),
        (10, 14),
        (17, 21),
        (16, 23),
        (14, 22),
        (9, 17),
    ]
    polygon(guard_lyr, guard_pts, spec.color("gold", 2), fill=True, material="gold")
    # Flared crossguard tips
    guard_lyr.set_px(8, 14, spec.color("gold", 3), "gold")
    guard_lyr.set_px(17, 23, spec.color("gold", 1), "gold")
    auto_shade_layer(guard_lyr, spec, material="gold", rim_light=True)
    add_specular(guard_lyr, 9, 15, spec, "gold")

    # 4. Flame Enchantment Wisps curling dynamically off upper blade
    flame_patch = [
        "....yY..",
        "...oYy..",
        "..roOy..",
        ".rRo....",
        "....r...",
    ]
    stamp_pattern(
        fx_lyr,
        16,
        3,
        flame_patch,
        {
            "r": (spec.color("fire", 0), "fire"),
            "R": (spec.color("fire", 1), "fire"),
            "o": (spec.color("fire", 2), "fire"),
            "O": (spec.color("fire", 3), "fire"),
            "y": (spec.color("fire", 4), "fire"),
            "Y": (spec.color("fire", 5), "fire"),
        },
    )
    # Secondary lower flame lick & floating ember sparks
    stamp_pattern(
        fx_lyr,
        22,
        10,
        [
            "..oY",
            ".rOy",
            "rRo.",
        ],
        {
            "r": (spec.color("fire", 0), "fire"),
            "R": (spec.color("fire", 1), "fire"),
            "o": (spec.color("fire", 2), "fire"),
            "O": (spec.color("fire", 3), "fire"),
            "y": (spec.color("fire", 4), "fire"),
            "Y": (spec.color("fire", 5), "fire"),
        },
    )
    # Subtle ember sparks (2px clusters so they read cleanly without orphan noise)
    fx_lyr.set_px(13, 7, spec.color("fire", 4), "fire")
    fx_lyr.set_px(14, 7, spec.color("fire", 2), "fire")
    fx_lyr.set_px(26, 14, spec.color("fire", 4), "fire")
    fx_lyr.set_px(26, 15, spec.color("fire", 2), "fire")

    # 5. Inter-layer Contact Shadow (AO) + Cleanup + Sel-Out Outline
    apply_layer_ao(blade_lyr, guard_lyr, spec, step=1)
    apply_layer_ao(hilt_lyr, guard_lyr, spec, step=1)

    bright_set = {spec.color("steel", -1), spec.color("fire", -1), spec.color("gold", -1)}
    for lyr in (hilt_lyr, blade_lyr, guard_lyr):
        despeckle(lyr, preserve_brightest=True, brightest_indices=bright_set)

    # Stamp intentional 2x2 inlaid ruby gem AFTER despeckle so micro-details stay crisp!
    stamp_pattern(
        guard_lyr,
        12,
        18,
        [
            "LR",
            "RD",
        ],
        {
            "L": (spec.color("cloth_red", 3), "cloth_red"),
            "R": (spec.color("cloth_red", 2), "cloth_red"),
            "D": (spec.color("cloth_red", 1), "cloth_red"),
        },
    )

    # Outline only the solid weapon body (leave glowing flames outline-free so they look luminous!)
    solid = hilt_lyr.copy()
    solid.blit(blade_lyr)
    solid.blit(guard_lyr)
    apply_outline(outline_lyr, solid, spec)

    return proj


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="pixel_assets")
    args = parser.parse_args()
    root = Path(args.out)
    proj = build_flame_sword(root)
    res = export_all(proj, assets_root=root, source_script=__file__)
    print("QA:", res["qa"])
    print("Inspection sheet:", res["inspection_sheet"])


if __name__ == "__main__":
    main()
