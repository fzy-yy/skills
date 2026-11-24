"""Benchmark Example 4: 48x48 Beveled Wooden & Gold 9-Slice RPG UI Panel."""

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
    draw_nine_slice_panel,
    load_spec,
)
from pixel_forge.exporters import export_all


def build_ui_panel(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    # Locked 48x48 UI panel with exact 9-slice margins exported to JSON and .aseprite
    proj = PixelProject("rpg_panel", 48, 48, spec, category="ui")
    panel_lyr = proj.layer("panel")

    margins = draw_nine_slice_panel(
        panel_lyr,
        spec,
        frame_material="wood",
        bg_material="stone",
        accent_material="gold",
        border=6,
        corner_radius=2,
    )
    proj.set_nine_slice(*margins)
    return proj


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="pixel_assets")
    args = parser.parse_args()
    root = Path(args.out)
    proj = build_ui_panel(root)
    res = export_all(proj, assets_root=root, source_script=__file__)
    print("QA:", res["qa"])
    print("Inspection sheet:", res["inspection_sheet"])


if __name__ == "__main__":
    main()
