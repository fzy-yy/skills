"""Benchmark Example 8: 48x48 Hi-Bit Ornate Royal Treasure Chest (ASCII Mirror + Boolean Cutouts + Material Profiles)."""

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
    apply_inner_outline,
    apply_layer_ao,
    apply_outline,
    auto_shade_layer,
    circle,
    despeckle,
    erase_circle,
    erase_rect,
    line,
    load_spec,
    paint_ascii_canvas,
    rect,
    rounded_rect,
)
from pixel_forge.exporters import export_all


def build_project(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    # 48x48 Hi-bit icon budget: 2px safe margin, metallic gold trims, matte oak planks, gem clasp
    proj = PixelProject("royal_chest", 48, 48, spec, category="icons")
    f0 = proj.frame(0)

    # Coordinate budget (symmetric front-3/4 view):
    #   Domed Lid: y=8..22, x=6..41
    #   Base Box:  y=22..40, x=6..41
    #   Lock Escutcheon & Ruby Gem: x=19..28, y=18..31
    #   Base Feet: y=40..42, x=7..12 & x=35..40

    box_lyr = f0.layer("box")
    lid_lyr = f0.layer("lid")
    trim_lyr = f0.layer("trim")
    lock_lyr = f0.layer("lock")
    fx_lyr = f0.layer("fx")
    outline_lyr = f0.layer("outline")

    # 1. Oak Wood Lower Box + Side Handles + Grounded Corner Feet (strong chest silhouette!)
    rounded_rect(box_lyr, 7, 22, 34, 18, 2, spec.color("wood", 2), fill=True, material="wood")
    # Side iron carry handles protruding 2px on left & right for unmistakable silhouette
    rect(box_lyr, 4, 26, 3, 6, spec.color("steel", 2), fill=True, material="steel")
    erase_rect(box_lyr, 5, 28, 2, 2)
    rect(box_lyr, 41, 26, 3, 6, spec.color("steel", 2), fill=True, material="steel")
    erase_rect(box_lyr, 41, 28, 2, 2)
    # Sturdy corner bracket feet extending 2px below base
    rect(box_lyr, 8, 39, 6, 3, spec.color("gold", 2), fill=True, material="gold")
    rect(box_lyr, 34, 39, 6, 3, spec.color("gold", 2), fill=True, material="gold")
    auto_shade_layer(box_lyr, spec)  # Automatically applies 'matte' to wood & 'metallic' to steel/gold!
    with box_lyr.lock_alpha():
        for py in (27, 32, 36):
            line(box_lyr, 8, py, 39, py, spec.color("wood", 0), material="wood", clean_doubles=False)
            line(box_lyr, 8, py + 1, 39, py + 1, spec.color("wood", 3), material="wood", clean_doubles=False)

    # 2. Domed Oak Lid (wider slight overhang x=6..41 for classic treasure chest profile)
    rounded_rect(lid_lyr, 6, 9, 36, 13, 5, spec.color("wood", 3), fill=True, material="wood")
    rect(lid_lyr, 6, 17, 36, 5, spec.color("wood", 2), fill=True, material="wood")
    auto_shade_layer(lid_lyr, spec, material="wood")
    with lid_lyr.lock_alpha():
        line(lid_lyr, 8, 14, 39, 14, spec.color("wood", 0), material="wood", clean_doubles=False)
        line(lid_lyr, 8, 15, 39, 15, spec.color("wood", 4), material="wood", clean_doubles=False)
        line(lid_lyr, 6, 21, 41, 21, spec.color("dark_ink", 0), material="dark_ink", clean_doubles=False)

    # 3. Mirrored Golden Straps & Rim Bands via paint_ascii_canvas(mirror=True)
    strap_grid = """
....GGGG..........
...GGGGGG.........
..GGGGGGGG........
.GG..GG...........
GG...GG...........
G....GG...........
G....GG...........
G....GG...........
G....GG...........
G....GG...........
G....GG...........
GGGGGGGGGGGGGGGGGG
GGGGGGGGGGGGGGGGGG
.G...GG...........
.G...GG...........
.G...GG...........
.G...GG...........
.G...GG...........
.G...GG...........
.G...GG...........
.G...GG...........
.GG..GG...........
.GGGGGGG..........
..GGGGGG..........
"""
    paint_ascii_canvas(
        trim_lyr,
        spec,
        strap_grid,
        legend={"G": "gold"},
        ox=6,
        oy=9,
        mirror=True,
    )
    auto_shade_layer(trim_lyr, spec)  # 'gold' & 'steel' use 'metallic' high-contrast profile automatically
    apply_inner_outline(trim_lyr, spec, step=1)
    # Crisp 2x2 rivets on straps (mirrored)
    paint_ascii_canvas(
        trim_lyr,
        spec,
        """
.....HL...........
.....SD...........
""",
        legend={"H": "gold:-1", "L": "gold:3", "S": "gold:2", "D": "gold:0"},
        ox=6,
        oy=12,
        mirror=True,
    )
    paint_ascii_canvas(
        trim_lyr,
        spec,
        """
.....HL...........
.....SD...........
""",
        legend={"H": "gold:-1", "L": "gold:3", "S": "gold:2", "D": "gold:0"},
        ox=6,
        oy=35,
        mirror=True,
    )

    # 4. Ornate Central Lockplate + Boolean Keyhole Cutout + Faceted Gem
    rounded_rect(lock_lyr, 19, 18, 10, 13, 3, spec.color("gold", 3), fill=True, material="gold")
    # Carve crisp keyhole silhouette via boolean erase primitives, then fill dark recess behind it
    erase_circle(lock_lyr, 23.5, 25.5, 1.3)
    erase_rect(lock_lyr, 23, 26, 2, 3)
    auto_shade_layer(lock_lyr, spec, material="gold")
    # Fill keyhole recess with deep dark_ink so box wood doesn't show through
    rect(box_lyr, 22, 24, 4, 6, spec.color("dark_ink", 0), fill=True, material="dark_ink")

    # Crowned Magic Gem set into upper lockplate (uses 'gem' subsurface glow profile!)
    gem_lyr = f0.layer("gem")
    circle(gem_lyr, 23.5, 20.5, 2.4, spec.color("magic", 2), fill=True, material="magic")
    auto_shade_layer(gem_lyr, spec, material="magic", profile="gem")
    add_specular(gem_lyr, 22, 19, spec, "magic")

    # 5. Top FX sparkles (automatically ordered above outline by canonical Z-order!)
    paint_ascii_canvas(
        fx_lyr,
        spec,
        """
..W..
..W..
WWWWW
..W..
..W..
""",
        legend={"W": "gold:-1"},
        ox=35,
        oy=5,
    )

    # 6. Inter-layer Contact Shadows (AO), Cleanup & Sel-Out Outline
    apply_layer_ao(box_lyr, lid_lyr, spec, step=1)
    apply_layer_ao(box_lyr, trim_lyr, spec, step=1)
    apply_layer_ao(lid_lyr, trim_lyr, spec, step=1)
    apply_layer_ao(trim_lyr, lock_lyr, spec, step=1)

    bright_set = {spec.color("gold", -1), spec.color("magic", -1), spec.color("wood", -1), spec.color("steel", -1)}
    for lyr in (box_lyr, lid_lyr, trim_lyr, lock_lyr, gem_lyr):
        despeckle(lyr, preserve_brightest=True, brightest_indices=bright_set)
    # Smooth 1px AO corner under lockplate
    trim_lyr.set_px(21, 22, spec.color("gold", 2), "gold")

    add_specular(trim_lyr, 9, 10, spec, "gold")
    add_specular(lock_lyr, 20, 19, spec, "gold")

    # composite_solid() automatically excludes 'outline' and top 'fx' sparkles!
    apply_outline(outline_lyr, f0.composite_solid(), spec)
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
