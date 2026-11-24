"""Benchmark Example 9: 32x32 4-Direction RPG Battlemage (16f Walk Atlas with Tag-Row Sheet Packing)."""

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
    PartTransform,
    PixelProject,
    add_specular,
    apply_layer_ao,
    apply_outline,
    auto_shade_layer,
    circle,
    despeckle,
    ellipse,
    load_spec,
    paint_ascii_canvas,
    rect,
    rounded_rect,
    walk_cycle_poses,
)
from pixel_forge.exporters import export_all


def _build_front_back_rig(spec, is_back: bool) -> CharacterRig:
    """Construct front ('down') or back ('up') hierarchical battlemage rig."""
    rig = CharacterRig(32, 32, len(spec.palette))
    torso = rig.add_part("torso", z_order=20)
    left_leg = rig.add_part("left_leg", z_order=12)
    right_leg = rig.add_part("right_leg", z_order=13)
    cape = rig.add_part("cape", z_order=5, parent="torso")
    head = rig.add_part("head", z_order=30, parent="torso")
    staff_x = 7 if is_back else 23
    weapon = rig.add_part("weapon", z_order=36, parent="torso", pivot=(staff_x + 1, 19))

    # Boots
    rect(left_leg, 12, 25, 3, 4, spec.color("leather", 1), fill=True, material="leather")
    rect(right_leg, 17, 25, 3, 4, spec.color("leather", 1), fill=True, material="leather")
    auto_shade_layer(left_leg, spec)
    auto_shade_layer(right_leg, spec)

    if is_back:
        # Back view: full crimson arcane cloak covers back of robe with gold collar trim
        rounded_rect(torso, 10, 15, 12, 11, 2, spec.color("cloth_red", 2), fill=True, material="cloth_red")
        auto_shade_layer(torso, spec)
        rect(torso, 11, 15, 10, 2, spec.color("gold", 3), fill=True, material="gold")
    else:
        # Front view: crimson cape behind shoulders + blue robe & gold stole in front
        rounded_rect(cape, 10, 15, 12, 10, 2, spec.color("cloth_red", 2), fill=True, material="cloth_red")
        auto_shade_layer(cape, spec, rim_light=False)
        rounded_rect(torso, 11, 15, 10, 11, 2, spec.color("cloth_blue", 2), fill=True, material="cloth_blue")
        auto_shade_layer(torso, spec)
        rect(torso, 15, 16, 2, 10, spec.color("gold", 3), fill=True, material="gold")
        rect(torso, 11, 20, 10, 2, spec.color("leather", 2), fill=True, material="leather")
        rect(torso, 15, 20, 2, 2, spec.color("gold", 4), fill=True, material="gold")

    # Pointed Wizard Hat + Face / Back Hood via ASCII Canvas
    hat_grid = """
......BB......
.....BBBB.....
....BBBBBB....
...BBBBBBBB...
..GGGGGGGGGG..
BBBBBBBBBBBBBB
"""
    paint_ascii_canvas(head, spec, hat_grid, legend={"B": "cloth_blue", "G": "gold"}, ox=9, oy=4)
    if is_back:
        rect(head, 12, 10, 8, 5, spec.color("cloth_blue", 1), fill=True, material="cloth_blue")
        auto_shade_layer(head, spec)
    else:
        ellipse(head, 12, 10, 19, 15, spec.color("dark_ink", 0), fill=True, material="dark_ink")
        auto_shade_layer(head, spec)
        head.set_px(13, 12, spec.color("gold", -1), "gold")
        head.set_px(14, 12, spec.color("gold", 3), "gold")
        head.set_px(17, 12, spec.color("gold", 3), "gold")
        head.set_px(18, 12, spec.color("gold", -1), "gold")

    # Crystal Staff (consistent world hand: screen-right when facing down, screen-left when facing up!)
    rect(weapon, staff_x, 12, 2, 14, spec.color("wood", 2), fill=True, material="wood")
    auto_shade_layer(weapon, spec, material="wood")
    circle(weapon, staff_x + 0.5, 10.0, 2.2, spec.color("magic", 2), fill=True, material="magic")
    auto_shade_layer(weapon, spec, material="magic", profile="gem")
    add_specular(weapon, staff_x, 9, spec, "magic")
    return rig


def _build_side_rig(spec) -> CharacterRig:
    """Construct right-facing side profile rig (left-facing reuses this rig via hierarchical flip_x!)."""
    rig = CharacterRig(32, 32, len(spec.palette))
    torso = rig.add_part("torso", z_order=20)
    back_leg = rig.add_part("back_leg", z_order=10)
    front_leg = rig.add_part("front_leg", z_order=24)
    cape = rig.add_part("cape", z_order=8, parent="torso")
    head = rig.add_part("head", z_order=30, parent="torso")
    front_arm = rig.add_part("front_arm", z_order=34, parent="torso", pivot=(16, 17))
    weapon = rig.add_part("weapon", z_order=36, parent="front_arm", pivot=(21, 18))

    rect(back_leg, 14, 25, 3, 4, spec.color("leather", 0), fill=True, material="leather")
    rect(front_leg, 15, 25, 3, 4, spec.color("leather", 2), fill=True, material="leather")
    auto_shade_layer(front_leg, spec)

    rounded_rect(cape, 9, 15, 7, 10, 2, spec.color("cloth_red", 2), fill=True, material="cloth_red")
    auto_shade_layer(cape, spec)

    rounded_rect(torso, 12, 15, 8, 11, 2, spec.color("cloth_blue", 2), fill=True, material="cloth_blue")
    auto_shade_layer(torso, spec)
    rect(torso, 12, 20, 8, 2, spec.color("gold", 3), fill=True, material="gold")

    # Side-profile pointed hat curving back + glowing eye
    side_hat = """
.....BBB......
....BBBBB.....
...BBBBBBB....
..GGGGGGGGGG..
.BBBBBBBBBBBBB
"""
    paint_ascii_canvas(head, spec, side_hat, legend={"B": "cloth_blue", "G": "gold"}, ox=9, oy=5)
    ellipse(head, 13, 10, 19, 15, spec.color("dark_ink", 0), fill=True, material="dark_ink")
    auto_shade_layer(head, spec)
    head.set_px(17, 12, spec.color("gold", -1), "gold")
    head.set_px(18, 12, spec.color("gold", 3), "gold")

    rounded_rect(front_arm, 15, 17, 6, 3, 1, spec.color("cloth_blue", 3), fill=True, material="cloth_blue")
    rect(weapon, 20, 11, 2, 14, spec.color("wood", 2), fill=True, material="wood")
    auto_shade_layer(weapon, spec, material="wood")
    circle(weapon, 20.5, 9.5, 2.2, spec.color("magic", 2), fill=True, material="magic")
    auto_shade_layer(weapon, spec, material="magic", profile="gem")
    add_specular(weapon, 20, 8, spec, "magic")
    return rig


def build_project(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    proj = PixelProject("battlemage_4dir", 32, 32, spec, category="characters", default_duration_ms=135)
    proj.set_pivot(16, 29)
    # Pack sprite sheet neatly into 4 rows (1 row per directional walk tag: 4x4 = 128x128 sheet!)
    proj.set_sheet_layout(split_rows_by_tag=True)

    rig_down = _build_front_back_rig(spec, is_back=False)
    rig_up = _build_front_back_rig(spec, is_back=True)
    rig_side = _build_side_rig(spec)
    bright_set = {spec.color("gold", -1), spec.color("magic", -1)}

    directions = [
        ("walk_down", rig_down, walk_cycle_poses("down", frames=4, duration_ms=135), False),
        ("walk_up", rig_up, walk_cycle_poses("up", frames=4, duration_ms=135), False),
        ("walk_right", rig_side, walk_cycle_poses("right", frames=4, duration_ms=135), False),
        ("walk_left", rig_side, walk_cycle_poses("right", frames=4, duration_ms=135), True),
    ]

    f_cursor = 0
    for tag_name, rig, seq, mirror_left in directions:
        start_f = f_cursor
        for pose_raw, dur in seq:
            fr = proj.frame(0) if f_cursor == 0 else proj.add_frame(duration_ms=dur)
            fr.duration_ms = dur
            pose = dict(pose_raw)
            if mirror_left:
                # Flip torso (propagates flip_x automatically to head, cape, front_arm & weapon!)
                t_val = pose.get("torso", (0, 0))
                tdx, tdy = (t_val.dx, t_val.dy) if isinstance(t_val, PartTransform) else t_val
                pose["torso"] = PartTransform(dx=-tdx, dy=tdy, flip_x=True)
                for leg_name in ("front_leg", "back_leg"):
                    l_val = pose.get(leg_name, (0, 0))
                    ldx, ldy = (l_val.dx, l_val.dy) if isinstance(l_val, PartTransform) else l_val
                    pose[leg_name] = PartTransform(dx=-ldx, dy=ldy, flip_x=True)

            rig.render_to_frame(fr, pose=pose)
            apply_layer_ao(fr.layer("torso"), fr.layer("head"), spec, step=1)
            for lyr in fr.layers.values():
                despeckle(lyr, preserve_brightest=True, brightest_indices=bright_set)
            apply_outline(fr.layer("outline"), fr.composite_solid(), spec)
            f_cursor += 1

        proj.add_tag(tag_name, start_f, f_cursor - 1, direction="forward", loop=True)

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
