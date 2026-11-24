"""CLI helper for pixel-art-forge skill (init specs, scaffold, run, recolor, preview, budgets)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import runpy
import sys
from pathlib import Path
from typing import Any

if sys.version_info < (3, 10):
    raise SystemExit("pixel-art-forge requires Python 3.10 or newer.")

try:
    from PIL import Image
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency 'Pillow'. Install it with: python -m pip install Pillow"
    ) from exc

# Allow running directly as `python scripts/cli.py`
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from pixel_forge.canvas import PixelProject
from pixel_forge.exporters import export_all
from pixel_forge.palette import list_palettes, load_palette
from pixel_forge.qa import render_contact_sheet
from pixel_forge.spec import (
    build_custom_palette_spec,
    list_spec_presets,
    load_spec,
    resolution_budget,
    save_spec,
)


def _parse_light_dir(raw: str) -> tuple[float, float]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError(f"--light-dir must be 'x,y' (e.g. '-1,-1'), got {raw!r}")
    return (float(parts[0]), float(parts[1]))


def _parse_material_map(raw: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for pair in raw.split(","):
        item = pair.strip()
        if not item:
            continue
        sep = "=" if "=" in item else (":" if ":" in item else None)
        if sep is None:
            raise ValueError(f"Invalid material mapping entry {item!r}; use 'src=dst' (e.g. 'steel=gold').")
        src, dst = item.split(sep, 1)
        mapping[src.strip()] = dst.strip()
    if not mapping:
        raise ValueError("--map must contain at least one 'src=dst' entry.")
    return mapping


def _build_scaffold_source(name: str, category: str, width: int, height: int) -> str:
    """Generate a clean, portable asset script template ready for iterative refinement."""
    header = f'''"""Pixel asset source: {category}/{name} ({width}x{height})."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _find_skill_scripts() -> Path:
    env_dir = os.environ.get("PIXEL_ART_FORGE_DIR")
    if env_dir:
        cand = Path(env_dir) / "scripts"
        if (cand / "pixel_forge").is_dir():
            return cand
        if (Path(env_dir) / "pixel_forge").is_dir():
            return Path(env_dir)
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
    raise RuntimeError("Could not locate pixel-art-forge/scripts; set PIXEL_ART_FORGE_DIR or use cli.py run.")


SKILL_SCRIPTS = _find_skill_scripts()
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))
'''

    if category == "characters":
        body = f'''
from pixel_forge import (
    CharacterRig,
    PixelProject,
    apply_layer_ao,
    apply_outline,
    auto_shade_layer,
    ellipse,
    idle_cycle_poses,
    load_spec,
    rect,
    rounded_rect,
)
from pixel_forge.exporters import export_all


def build_project(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    proj = PixelProject({name!r}, {width}, {height}, spec, category="characters", default_duration_ms=180)
    proj.set_pivot({width // 2}, {height - 2})

    rig = CharacterRig({width}, {height}, len(spec.palette))
    legs = rig.add_part("legs", z_order=10)
    torso = rig.add_part("torso", z_order=20)
    head = rig.add_part("head", z_order=30, parent="torso")

    # Coordinate budget (replace placeholder shapes with character design)
    cx = {width // 2}
    rect(legs, cx - 3, {max(2, height - 7)}, 2, 5, spec.color("leather", 2), fill=True, material="leather")
    rect(legs, cx + 1, {max(2, height - 7)}, 2, 5, spec.color("leather", 2), fill=True, material="leather")
    rounded_rect(torso, cx - 4, {max(2, height - 15)}, 8, 8, 1, spec.color("cloth_blue", 2), fill=True, material="cloth_blue")
    ellipse(head, cx - 4, {max(2, height - 23)}, cx + 3, {max(4, height - 16)}, spec.color("skin", 2), fill=True, material="skin")

    for part_name in ("legs", "torso", "head"):
        auto_shade_layer(rig.part(part_name), spec)

    for idx, (pose, dur) in enumerate(idle_cycle_poses(frames=4, hierarchical=True)):
        fr = proj.frame(0) if idx == 0 else proj.add_frame(duration_ms=dur)
        fr.duration_ms = dur
        out_lyr = fr.layer("outline")
        rig.render_to_frame(fr, pose=pose)
        apply_layer_ao(fr.layer("torso"), fr.layer("head"), spec, step=1)
        apply_outline(out_lyr, fr.composite(), spec)

    proj.add_tag("idle", 0, 3, direction="forward", loop=True)
    return proj
'''
    elif category == "tilesets":
        body = f'''
from pixel_forge import PixelProject, fill_stone_brick_tile, load_spec
from pixel_forge.exporters import export_all


def build_project(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    proj = PixelProject({name!r}, {width}, {height}, spec, category="tilesets")
    fill_stone_brick_tile(proj.layer("base"), spec, material="stone", rows=4, cols=2, seed=42)
    return proj
'''
    elif category == "ui":
        body = f'''
from pixel_forge import PixelProject, draw_nine_slice_panel, load_spec
from pixel_forge.exporters import export_all


def build_project(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    proj = PixelProject({name!r}, {width}, {height}, spec, category="ui")
    margins = draw_nine_slice_panel(proj.layer("panel"), spec, frame_material="wood", bg_material="stone", accent_material="gold")
    proj.set_nine_slice(*margins)
    return proj
'''
    else:
        r = max(2, min(width, height) // 3)
        body = f'''
from pixel_forge import PixelProject, apply_outline, load_spec, shaded_sphere
from pixel_forge.exporters import export_all


def build_project(assets_root: Path) -> PixelProject:
    spec_path = assets_root / "pixel_spec.json"
    spec = load_spec(spec_path if spec_path.exists() else "topdown_rpg")

    proj = PixelProject({name!r}, {width}, {height}, spec, category="icons")
    f0 = proj.frame(0)
    out_lyr = f0.layer("outline")
    main_lyr = f0.layer("main")

    # Replace placeholder orb with target icon silhouette & layered parts
    shaded_sphere(main_lyr, {width / 2.0 - 0.5}, {height / 2.0 - 0.5}, {r}, spec, material="magic")
    apply_outline(out_lyr, main_lyr, spec)
    return proj
'''

    footer = '''

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
'''
    return header + body + footer


def _load_project_from_script(script_path: Path, assets_root: Path) -> PixelProject:
    """Import an asset script module and invoke its `build_project` or `build_*` factory."""
    spec = importlib.util.spec_from_file_location("_pixel_forge_user_script", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Python module from {script_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    builder = getattr(mod, "build_project", None)
    if builder is None:
        candidates = [
            fn
            for fn_name, fn in vars(mod).items()
            if fn_name.startswith("build_") and callable(fn)
        ]
        if len(candidates) == 1:
            builder = candidates[0]
        else:
            raise RuntimeError(
                f"Script {script_path} must define `build_project(assets_root)` or a single `build_*(assets_root)` function."
            )
    proj = builder(assets_root)
    if not isinstance(proj, PixelProject):
        raise TypeError(f"Builder in {script_path} returned {type(proj).__name__}, expected PixelProject.")
    return proj


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pixel-art-forge", description="Procedural pixel art skill CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-palettes", help="List built-in palette presets")
    sub.add_parser("list-specs", help="List built-in StyleSpec presets")

    p_init = sub.add_parser("init-spec", help="Initialize pixel_assets/pixel_spec.json from a preset")
    p_init.add_argument("--preset", default="topdown_rpg", help="Built-in spec preset name")
    p_init.add_argument("--palette", default=None, help="Override palette preset name")
    p_init.add_argument(
        "--custom-colors",
        default=None,
        help="Comma-separated base hex colors (or 'name:#hex') to build a custom hue-shifted palette",
    )
    p_init.add_argument("--project", default="my_pixel_game", help="Project name")
    p_init.add_argument("--outline", default=None, choices=["sel_out", "black", "colored", "none"])
    p_init.add_argument("--light-dir", default=None, help="Light direction vector 'x,y' (e.g. '-1,-1', '0,-1', '1,-1')")
    p_init.add_argument(
        "--perspective",
        default=None,
        choices=["topdown_3_4", "side_view", "flat_icon", "isometric", "topdown_rpg", "side_platformer"],
    )
    p_init.add_argument("--dither", default=None, choices=["none", "bayer2x2", "bayer4x4"])
    p_init.add_argument("--ppu", type=int, default=None, help="Pixels per unit for game engine hints")
    p_init.add_argument("--max-colors", type=int, default=None, help="Hard cap on unique colors used per asset")
    p_init.add_argument("--out", default="pixel_assets/pixel_spec.json", help="Output path")

    p_bud = sub.add_parser("budget", help="Show pixel-art detail budget for a target resolution")
    p_bud.add_argument("--width", type=int, required=True)
    p_bud.add_argument("--height", type=int, required=True)

    p_cs = sub.add_parser("contact-sheet", help="Rebuild _inspect/project_contact_sheet.png from catalog.json")
    p_cs.add_argument("--root", default="pixel_assets", help="Assets root directory")
    p_cs.add_argument("--scale", type=int, default=4)

    p_run = sub.add_parser("run", help="Run any pixel asset script with pixel_forge automatically on sys.path")
    p_run.add_argument("script", help="Path to asset Python script")
    p_run.add_argument("script_args", nargs=argparse.REMAINDER, help="Arguments passed through to the script")

    p_scaf = sub.add_parser("scaffold", help="Generate a starter asset Python script following skill conventions")
    p_scaf.add_argument("--category", required=True, choices=["icons", "characters", "tilesets", "ui"])
    p_scaf.add_argument("--name", required=True, help="Asset name (lowercase snake_case)")
    p_scaf.add_argument("--width", type=int, required=True)
    p_scaf.add_argument("--height", type=int, required=True)
    p_scaf.add_argument("--root", default="pixel_assets", help="Assets root directory")
    p_scaf.add_argument("--out", default=None, help="Explicit output script path")
    p_scaf.add_argument("--force", action="store_true", help="Overwrite existing script if present")

    p_rec = sub.add_parser("recolor", help="Generate a palette-swapped variant from an existing asset script")
    p_rec.add_argument("--script", required=True, help="Source asset script defining build_project / build_*")
    p_rec.add_argument("--map", required=True, help="Material mapping 'src=dst,src2=dst2' (e.g. 'steel=gold')")
    p_rec.add_argument("--name", default=None, help="New variant asset name (default: <orig>_recolor)")
    p_rec.add_argument("--root", default="pixel_assets", help="Assets root directory")
    p_rec.add_argument("--no-reoutline", action="store_true", help="Keep original outline pixels untouched")

    p_prev = sub.add_parser("preview", help="Export an integer nearest-neighbor upscaled PNG preview")
    p_prev.add_argument("--png", required=True, help="Input 1x PNG path")
    p_prev.add_argument("--scale", type=int, default=8, help="Integer upscale factor (>= 2)")
    p_prev.add_argument("--out", default=None, help="Output PNG path (default: <stem>_<scale>x.png)")

    args = parser.parse_args(argv)

    if args.cmd == "list-palettes":
        print(json.dumps({"palettes": list_palettes()}, indent=2))
        return 0

    if args.cmd == "list-specs":
        print(json.dumps({"specs": list_spec_presets()}, indent=2))
        return 0

    if args.cmd == "init-spec":
        spec = load_spec(args.preset)
        spec.project_name = args.project
        if args.max_colors is not None:
            spec.max_colors = args.max_colors
        if args.custom_colors:
            entries = [e.strip() for e in args.custom_colors.split(",") if e.strip()]
            spec = build_custom_palette_spec(spec, entries, palette_name=f"{args.project}_custom")
        elif args.palette:
            new_pal = load_palette(args.palette)
            spec.remap_to_palette(new_pal)
        if args.outline:
            spec.outline["mode"] = args.outline
        if args.light_dir:
            lx, ly = _parse_light_dir(args.light_dir)
            spec.light_dir = (lx, ly)
            spec.__post_init__()
        if args.perspective:
            persp_aliases = {
                "topdown_rpg": "topdown_3_4",
                "side_platformer": "side_view",
            }
            spec.perspective = persp_aliases.get(args.perspective, args.perspective)
        if args.dither:
            spec.dither = args.dither
        if args.ppu is not None:
            spec.pixels_per_unit = max(1, int(args.ppu))
        out_path = save_spec(spec, args.out)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "spec_path": str(out_path),
                    "palette": spec.palette.name,
                    "palette_size": len(spec.palette),
                    "light_dir": [round(spec.light_dir[0], 4), round(spec.light_dir[1], 4)],
                    "pixels_per_unit": spec.pixels_per_unit,
                    "max_colors": spec.max_colors,
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "budget":
        b = resolution_budget(args.width, args.height)
        print(json.dumps(b.__dict__, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "contact-sheet":
        out = render_contact_sheet(args.root, scale=args.scale)
        print(json.dumps({"contact_sheet": str(out) if out else None}, indent=2))
        return 0

    if args.cmd == "run":
        script_path = Path(args.script).resolve()
        if not script_path.exists():
            raise FileNotFoundError(f"Asset script not found: {script_path}")
        extra = list(args.script_args)
        if extra and extra[0] == "--":
            extra = extra[1:]
        os.environ["PIXEL_ART_FORGE_DIR"] = str(SCRIPTS_DIR.parent)
        old_argv = sys.argv[:]
        try:
            sys.argv = [str(script_path), *extra]
            runpy.run_path(str(script_path), run_name="__main__")
        finally:
            sys.argv = old_argv
        return 0

    if args.cmd == "scaffold":
        out_path = (
            Path(args.out)
            if args.out
            else Path(args.root) / "src" / args.category / f"{args.name}_{args.width}x{args.height}.py"
        )
        if out_path.exists() and not args.force:
            raise FileExistsError(f"Script already exists: {out_path} (use --force to overwrite)")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_build_scaffold_source(args.name, args.category, args.width, args.height), encoding="utf-8")
        print(json.dumps({"status": "ok", "script_path": str(out_path)}, indent=2))
        return 0

    if args.cmd == "recolor":
        script_path = Path(args.script).resolve()
        root = Path(args.root)
        mapping = _parse_material_map(args.map)
        proj = _load_project_from_script(script_path, root)
        proj.name = args.name or f"{proj.name}_recolor"
        changed = proj.remap_material(mapping, reoutline=not args.no_reoutline)
        res = export_all(proj, assets_root=root, source_script=script_path)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "name": proj.name,
                    "pixels_remapped": changed,
                    "qa_passed": res["qa"]["passed"],
                    "exports": res["exports"],
                    "inspection_sheet": res["inspection_sheet"],
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "preview":
        in_path = Path(args.png)
        if not in_path.exists():
            raise FileNotFoundError(f"Input PNG not found: {in_path}")
        scale = max(2, int(args.scale))
        out_path = Path(args.out) if args.out else in_path.with_name(f"{in_path.stem}_{scale}x.png")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(in_path) as raw_im:
            im = raw_im.convert("RGBA")
            up = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
            up.save(out_path, format="PNG")
            out_size = [up.width, up.height]
        print(json.dumps({"status": "ok", "out": str(out_path), "size": out_size, "scale": scale}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
