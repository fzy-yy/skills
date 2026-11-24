"""Benchmark Example 2: 32x32 Top-Down RPG Knight (Idle 4f + Walk 4f via Hierarchical CharacterRig)."""

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
    CharacterRig,
    PixelProject,
    add_specular,
    apply_layer_ao,
    apply_outline,
    auto_shade_layer,
    despeckle,
    ellipse,
    idle_cycle_poses,
    line,
    load_spec,
    polygon,
    rect,
    rounded_rect,
    stamp_pattern,
)
from pixel_forge.exporters import export_all


def build_knight(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    # Locked 32x32 character sprite, bottom-center pivot (16, 30)
    proj = PixelProject("knight", 32, 32, spec, category="characters", default_duration_ms=180)
    proj.set_pivot(16, 30)

    # Proportion Budget (32x32 Chibi RPG Knight, 2px top margin so 1px walk bob + 1px outline stays >= y=1):
    #   Plume:  y=3..5
    #   Helmet: y=6..14, x=11..20 (10px wide iconic knight helm)
    #   Torso:  y=15..23, x=11..20 (cuirass + gold belt)
    #   Legs:   y=24..29 (grounded boots; 1px outline bottom lands at y=30)
    #   Shield: left side x=6..11, y=15..23
    #   Sword:  right side x=22..25, y=8..22 (upright held blade)

    rig = CharacterRig(32, 32, len(spec.palette))

    # Root upper-body anchor: torso; cape, head, shield, and weapon bind to parent="torso"
    torso = rig.add_part("torso", z_order=20)
    cape = rig.add_part("cape", z_order=5, parent="torso")
    left_leg = rig.add_part("left_leg", z_order=15)
    right_leg = rig.add_part("right_leg", z_order=16)
    head = rig.add_part("head", z_order=30, parent="torso")
    shield = rig.add_part("shield", z_order=35, parent="torso")
    weapon = rig.add_part("weapon", z_order=36, parent="torso", pivot=(23, 20))

    # 1. Flowing Crimson Cape (back)
    rect(cape, 10, 16, 12, 9, spec.color("cloth_red", 1), fill=True, material="cloth_red")
    rect(cape, 9, 19, 14, 6, spec.color("cloth_red", 1), fill=True, material="cloth_red")
    auto_shade_layer(cape, spec, material="cloth_red", rim_light=False)

    # 2. Grounded Armored Boots (independent of torso so feet stay planted)
    rect(left_leg, 11, 23, 4, 6, spec.color("steel", 2), fill=True, material="steel")
    rect(left_leg, 11, 27, 4, 2, spec.color("leather", 1), fill=True, material="leather")
    auto_shade_layer(left_leg, spec)

    rect(right_leg, 17, 23, 4, 6, spec.color("steel", 2), fill=True, material="steel")
    rect(right_leg, 17, 27, 4, 2, spec.color("leather", 1), fill=True, material="leather")
    auto_shade_layer(right_leg, spec)

    # 3. Torso / Plate Cuirass + Gold Belt & Tabard
    rounded_rect(torso, 11, 14, 10, 10, 1, spec.color("steel", 3), fill=True, material="steel")
    auto_shade_layer(torso, spec, material="steel", rim_light=True)
    rect(torso, 14, 16, 4, 8, spec.color("cloth_red", 2), fill=True, material="cloth_red")
    line(torso, 11, 21, 20, 21, spec.color("leather", 1), material="leather", clean_doubles=False)
    rect(torso, 15, 20, 2, 2, spec.color("gold", 3), fill=True, material="gold")
    add_specular(torso, 12, 15, spec, "steel")

    # 4. Helmet + Crimson Plume + Visor Slit (plume starts at y=3 to preserve safe top margin)
    polygon(head, [(14, 6), (16, 3), (19, 4), (18, 6)], spec.color("cloth_red", 2), fill=True, material="cloth_red")
    head.set_px(16, 3, spec.color("cloth_red", 3), "cloth_red")
    head.set_px(17, 3, spec.color("cloth_red", 3), "cloth_red")
    ellipse(head, 11, 6, 20, 14, spec.color("steel", 3), fill=True, material="steel")
    auto_shade_layer(head, spec, material="steel", rim_light=True)
    line(head, 12, 10, 19, 10, spec.color("gold", 2), material="gold", clean_doubles=False)
    head.set_px(13, 10, spec.color("gold", 3), "gold")
    head.set_px(14, 10, spec.color("gold", 3), "gold")
    stamp_pattern(
        head,
        12,
        11,
        [
            "DDDDDDDD",
            "..DDDD..",
            "..DDDD..",
        ],
        {"D": (spec.color("dark_ink", 0), "dark_ink")},
    )
    add_specular(head, 13, 7, spec, "steel")

    # 5. Kite Shield (left hand)
    rounded_rect(shield, 6, 15, 6, 7, 1, spec.color("cloth_blue", 2), fill=True, material="cloth_blue")
    rect(shield, 7, 22, 4, 1, spec.color("cloth_blue", 2), fill=True, material="cloth_blue")
    rect(shield, 8, 23, 2, 1, spec.color("cloth_blue", 1), fill=True, material="cloth_blue")
    auto_shade_layer(shield, spec, material="cloth_blue", rim_light=True)
    line(shield, 6, 15, 11, 15, spec.color("gold", 3), material="gold", clean_doubles=False)
    line(shield, 8, 17, 9, 17, spec.color("gold", 3), material="gold", clean_doubles=False)
    rect(shield, 8, 16, 2, 6, spec.color("gold", 3), fill=True, material="gold")
    rect(shield, 7, 18, 4, 2, spec.color("gold", 3), fill=True, material="gold")
    add_specular(shield, 7, 16, spec, "gold")

    # 6. Upright Broadsword & Gauntlet (right hand)
    rect(weapon, 23, 8, 2, 11, spec.color("steel", 4), fill=True, material="steel")
    line(weapon, 24, 9, 24, 18, spec.color("steel", 2), material="steel", clean_doubles=False)
    weapon.set_px(23, 8, spec.color("steel", 5), "steel")
    weapon.set_px(23, 9, spec.color("steel", 5), "steel")
    line(weapon, 21, 19, 26, 19, spec.color("gold", 2), material="gold", clean_doubles=False)
    weapon.set_px(22, 19, spec.color("gold", 3), "gold")
    weapon.set_px(23, 19, spec.color("gold", 3), "gold")
    rect(weapon, 22, 20, 3, 2, spec.color("steel", 3), fill=True, material="steel")
    rect(weapon, 23, 22, 2, 1, spec.color("gold", 2), fill=True, material="gold")

    bright_set = {spec.color("steel", -1), spec.color("gold", -1), spec.color("cloth_red", -1)}
    for part_name in ("cape", "left_leg", "right_leg", "torso", "head", "shield", "weapon"):
        despeckle(rig.part(part_name), preserve_brightest=True, brightest_indices=bright_set)

    # --- Assemble Animation Frames using Hierarchical Rig ---
    # Idle (4 frames, 190ms): torso bob automatically carries head, cape, shield & weapon!
    idle_seq = idle_cycle_poses(frames=4, duration_ms=190, hierarchical=True)

    # Walk (4 frames, 130ms): alternating grounded strides + upper-body passing bounce
    walk_poses = [
        {"left_leg": (-1, -1), "right_leg": (1, 0), "torso": (0, 0), "shield": (1, 0), "weapon": (-1, 1), "cape": (-1, 0)},
        {"left_leg": (0, 0), "right_leg": (0, -2), "torso": (0, -1)},
        {"left_leg": (1, 0), "right_leg": (-1, -1), "torso": (0, 0), "shield": (-1, 0), "weapon": (1, 1), "cape": (1, 0)},
        {"left_leg": (0, -2), "right_leg": (0, 0), "torso": (0, -1)},
    ]
    all_frames = idle_seq + [(p, 130) for p in walk_poses]

    for idx, (pose, dur) in enumerate(all_frames):
        fr = proj.frame(0) if idx == 0 else proj.add_frame(duration_ms=dur)
        fr.duration_ms = dur
        out_lyr = fr.layer("outline")
        rig.render_to_frame(fr, pose=pose)
        apply_layer_ao(fr.layer("torso"), fr.layer("head"), spec, step=1)
        apply_layer_ao(fr.layer("torso"), fr.layer("shield"), spec, step=1)
        apply_layer_ao(fr.layer("left_leg"), fr.layer("torso"), spec, step=1)
        apply_layer_ao(fr.layer("right_leg"), fr.layer("torso"), spec, step=1)
        despeckle(fr.layer("torso"), preserve_brightest=True, brightest_indices=bright_set)
        comp = fr.composite()
        apply_outline(out_lyr, comp, spec)

    proj.add_tag("idle", 0, 3, direction="forward", loop=True)
    proj.add_tag("walk", 4, 7, direction="forward", loop=True)
    return proj


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="pixel_assets")
    args = parser.parse_args()
    root = Path(args.out)
    proj = build_knight(root)
    res = export_all(proj, assets_root=root, source_script=__file__)
    print("QA:", res["qa"])
    print("Inspection sheet:", res["inspection_sheet"])


if __name__ == "__main__":
    main()
