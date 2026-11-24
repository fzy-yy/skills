"""Benchmark Example 7: RPG UI HUD Kit (4-State Button, Segmented Health Bar, Selected Item Slot)."""

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
    build_button_states,
    draw_health_bar,
    draw_item_slot,
    load_spec,
)
from pixel_forge.exporters import export_all


def build_project(assets_root: Path) -> PixelProject:
    """Build the 4-state RPG UI button sheet (primary entry point for cli.py recolor)."""
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")
    return build_button_states(
        "rpg_button",
        width=48,
        height=18,
        spec=spec,
        frame_material="wood",
        fill_material="cloth_blue",
        accent_material="gold",
        corner_radius=2,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="pixel_assets")
    args = parser.parse_args()
    root = Path(args.out)

    spec_path = root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    # 1. 4-State Button (normal / hover / pressed / disabled)
    btn_proj = build_project(root)
    res_btn = export_all(btn_proj, assets_root=root, source_script=__file__)

    # 2. Segmented 64x12 Health Bar
    hp_proj = PixelProject("hp_bar", 64, 12, spec, category="ui")
    draw_health_bar(hp_proj.layer("bar"), spec, ratio=0.72, frame_material="steel", fill_material="cloth_red", segmented=4)
    res_hp = export_all(hp_proj, assets_root=root, source_script=__file__)

    # 3. 24x24 Selected Inventory Slot with Magic Rarity Rim
    slot_proj = PixelProject("item_slot_selected", 24, 24, spec, category="ui")
    margins = draw_item_slot(slot_proj.layer("slot"), spec, selected=True, rarity_material="magic")
    slot_proj.set_nine_slice(*margins)
    res_slot = export_all(slot_proj, assets_root=root, source_script=__file__)

    print("Button QA:", res_btn["qa"]["passed"], "|", res_btn["inspection_sheet"])
    print("HP Bar QA:", res_hp["qa"]["passed"], "|", res_hp["inspection_sheet"])
    print("Slot QA:", res_slot["qa"]["passed"], "|", res_slot["inspection_sheet"])


if __name__ == "__main__":
    main()
