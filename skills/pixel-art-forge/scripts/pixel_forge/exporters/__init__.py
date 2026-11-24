"""Unified export pipeline + automatic catalog.json & contact sheet updates.

Outputs per asset:
  - Static assets: 1x PNG (`<name>.png`), Godot/Unity JSON (`<name>.json`), native `.aseprite`
  - Animated assets: ordered 1x Sprite Sheet PNG (`<name>_sheet.png`), individual per-frame 1x PNGs
    (`frames/<name>_000.png`...), animated GIF (`<name>.gif`), Godot/Unity JSON, and native `.aseprite`
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..canvas import PixelProject
from ..qa import render_contact_sheet, render_inspection_sheet, validate_project
from ..spec import save_spec
from .aseprite_exporter import export_aseprite
from .gif_exporter import export_gif
from .meta_exporter import export_json_meta
from .png_exporter import export_frame_pngs, export_png


def is_animated_project(project: PixelProject) -> bool:
    """Return True when a multi-frame project represents an animation (vs static tiles/UI states)."""
    return len(project.frames) > 1 and (project.category not in ("tilesets", "ui") or bool(project.tags))


def _update_catalog(
    assets_root: Path,
    project: PixelProject,
    export_paths: dict[str, Any],
    qa_report: dict[str, Any],
    source_script: str | Path | None = None,
) -> Path:
    catalog_path = assets_root / "catalog.json"
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    else:
        catalog = {"project_name": project.spec.project_name, "assets": []}

    def _rel(p: Path) -> str:
        try:
            return p.resolve().relative_to(assets_root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()

    rel_exports: dict[str, Any] = {}
    for k, v in export_paths.items():
        if isinstance(v, list):
            rel_exports[k] = [_rel(item) for item in v]
        else:
            rel_exports[k] = _rel(v)

    entry = {
        "name": project.name,
        "category": project.category,
        "dimensions": [project.width, project.height],
        "frames": len(project.frames),
        "animated": is_animated_project(project),
        "tags": [t.name for t in project.tags],
        "palette": project.spec.palette.name,
        "unique_colors": qa_report["unique_colors_used"],
        "qa_passed": qa_report["passed"],
        "source_script": _rel(Path(source_script)) if source_script else None,
        "exports": rel_exports,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    assets = [
        a
        for a in catalog.get("assets", [])
        if not (a["name"] == project.name and a["category"] == project.category)
    ]
    assets.append(entry)
    assets.sort(key=lambda a: (a["category"], a["name"]))
    catalog["project_name"] = project.spec.project_name
    catalog["assets"] = assets
    catalog_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return catalog_path


def export_all(
    project: PixelProject,
    assets_root: str | Path = "pixel_assets",
    source_script: str | Path | None = None,
    generate_qa: bool = True,
    update_contact_sheet: bool = True,
    strict: bool = False,
    sheet_columns: int | None = None,
    split_rows_by_tag: bool | None = None,
) -> dict[str, Any]:
    """Run QA checks and export PNG (+ per-frame PNGs & GIF for animations), JSON, and .aseprite."""
    root = Path(assets_root)
    root.mkdir(parents=True, exist_ok=True)

    # Ensure project pixel_spec.json exists in assets_root
    spec_path = root / "pixel_spec.json"
    if not spec_path.exists():
        save_spec(project.spec, spec_path)

    qa_report = validate_project(project)
    if strict and not qa_report["passed"]:
        raise RuntimeError(f"QA validation failed for {project.name}: {qa_report['errors']}")

    out_dir = root / "exports" / project.category / project.name
    png_info = export_png(
        project,
        out_dir,
        columns=sheet_columns,
        split_rows_by_tag=split_rows_by_tag,
    )

    animated = is_animated_project(project)
    frame_files: list[Path] | None = None
    gif_path: Path | None = None
    if animated:
        frame_files = export_frame_pngs(project, out_dir)
        gif_path = export_gif(project, out_dir)

    json_path = export_json_meta(
        project,
        png_info,
        out_dir,
        frame_files=frame_files,
        gif_path=gif_path,
    )
    ase_path = export_aseprite(project, out_dir)

    export_paths: dict[str, Any] = {
        "png": png_info["path"],
        "json": json_path,
        "aseprite": ase_path,
    }
    if animated and frame_files is not None and gif_path is not None:
        export_paths["frames"] = frame_files
        export_paths["gif"] = gif_path

    qa_img_path = None
    if generate_qa:
        qa_img_path = render_inspection_sheet(
            project,
            root / "_inspect" / f"{project.category}_{project.name}_qa.png",
            qa_report=qa_report,
        )

    catalog_path = _update_catalog(
        assets_root=root,
        project=project,
        export_paths=export_paths,
        qa_report=qa_report,
        source_script=source_script,
    )

    contact_sheet_path = None
    if update_contact_sheet:
        contact_sheet_path = render_contact_sheet(root)

    serialized_exports: dict[str, Any] = {}
    for k, v in export_paths.items():
        serialized_exports[k] = [str(p) for p in v] if isinstance(v, list) else str(v)

    return {
        "qa": qa_report,
        "exports": serialized_exports,
        "inspection_sheet": str(qa_img_path) if qa_img_path else None,
        "catalog": str(catalog_path),
        "contact_sheet": str(contact_sheet_path) if contact_sheet_path else None,
    }


__all__ = [
    "export_all",
    "export_aseprite",
    "export_frame_pngs",
    "export_gif",
    "export_json_meta",
    "export_png",
    "is_animated_project",
]
