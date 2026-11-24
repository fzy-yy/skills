"""Unified Aseprite-compatible JSON exporter with Godot and Unity engine hints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..canvas import PixelProject


def export_json_meta(
    project: PixelProject,
    png_info: dict[str, Any],
    out_dir: str | Path,
    frame_files: list[Path] | None = None,
    gif_path: Path | None = None,
) -> Path:
    """Write `<name>.json` combining Aseprite standard format + Godot/Unity engine hints."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    w, h = project.width, project.height
    frame_rects = png_info["frame_rects"]

    frames_list: list[dict[str, Any]] = []
    for i, (rx, ry, rw, rh) in enumerate(frame_rects):
        f_entry: dict[str, Any] = {
            "filename": f"{project.name} {i}.aseprite",
            "frame": {"x": rx, "y": ry, "w": rw, "h": rh},
            "rotated": False,
            "trimmed": False,
            "spriteSourceSize": {"x": 0, "y": 0, "w": rw, "h": rh},
            "sourceSize": {"w": rw, "h": rh},
            "duration": project.frames[i].duration_ms,
        }
        if frame_files and i < len(frame_files):
            f_entry["frameImage"] = f"frames/{frame_files[i].name}"
        frames_list.append(f_entry)

    frame_tags = [
        {
            "name": tag.name,
            "from": tag.from_frame,
            "to": tag.to_frame,
            "direction": tag.direction,
            "loop": tag.loop,
        }
        for tag in project.tags
    ]

    # Build slices list (always include primary pivot/9-slice descriptor)
    slices_json: list[dict[str, Any]] = []
    primary_key: dict[str, Any] = {
        "frame": 0,
        "bounds": {"x": 0, "y": 0, "w": w, "h": h},
        "pivot": {"x": project.pivot[0], "y": project.pivot[1]},
    }
    if project.nine_slice is not None:
        sl, st, sr, sb = project.nine_slice
        primary_key["center"] = {
            "x": sl,
            "y": st,
            "w": w - sl - sr,
            "h": h - st - sb,
        }
    slices_json.append(
        {
            "name": "nine_slice" if project.nine_slice is not None else "bounds",
            "color": "#0000ffff",
            "keys": [primary_key],
        }
    )

    for s in project.slices:
        skey: dict[str, Any] = {
            "frame": 0,
            "bounds": {"x": s.x, "y": s.y, "w": s.w, "h": s.h},
        }
        if s.pivot is not None:
            skey["pivot"] = {"x": s.pivot[0], "y": s.pivot[1]}
        if s.center_9slice is not None:
            cx, cy, cw, ch = s.center_9slice
            skey["center"] = {"x": cx, "y": cy, "w": cw, "h": ch}
        slices_json.append({"name": s.name, "color": "#00ff00ff", "keys": [skey]})

    # Compute Godot tag FPS metadata
    godot_tags: dict[str, dict[str, Any]] = {}
    if project.tags:
        for tag in project.tags:
            durations = [project.frames[i].duration_ms for i in range(tag.from_frame, tag.to_frame + 1)]
            avg_ms = sum(durations) / max(1, len(durations))
            godot_tags[tag.name] = {
                "from": tag.from_frame,
                "to": tag.to_frame,
                "fps": round(1000.0 / max(1.0, avg_ms), 2),
                "loop": tag.loop,
                "direction": tag.direction,
            }
    elif len(project.frames) > 1:
        avg_ms = sum(f.duration_ms for f in project.frames) / len(project.frames)
        godot_tags["default"] = {
            "from": 0,
            "to": len(project.frames) - 1,
            "fps": round(1000.0 / max(1.0, avg_ms), 2),
            "loop": True,
            "direction": "forward",
        }

    # Unity uses bottom-up normalized pivot [0..1, 0..1]
    unity_pivot_x = round(project.pivot[0] / max(1, w), 4)
    unity_pivot_y = round(1.0 - (project.pivot[1] / max(1, h)), 4)

    unity_hints: dict[str, Any] = {
        "pixelsPerUnit": project.spec.pixels_per_unit,
        "filterMode": "Point",
        "compression": "None",
        "pivotNormalized": [unity_pivot_x, unity_pivot_y],
    }
    if project.nine_slice is not None:
        sl, st, sr, sb = project.nine_slice
        # Unity Sprite.border order: Left, Bottom, Right, Top
        unity_hints["nineSliceLBRT"] = [sl, sb, sr, st]

    godot_hints: dict[str, Any] = {
        "pivotPixels": [project.pivot[0], project.pivot[1]],
        "textureFilter": "CanvasItem.TEXTURE_FILTER_NEAREST",
        "tags": godot_tags,
    }
    if project.category == "tilesets":
        godot_hints["tileSize"] = [w, h]
        if project.metadata.get("isometric") or project.spec.perspective == "isometric":
            godot_hints["tileShape"] = "TILE_SHAPE_ISOMETRIC"
            unity_hints["gridCellLayout"] = "Isometric"
        if "autotile" in project.metadata:
            auto_meta = project.metadata["autotile"]
            godot_hints["autotile"] = {
                "mode": auto_meta.get("mode"),
                "tileCount": auto_meta.get("tile_count"),
                "terrainSet": 0,
            }
            unity_hints["ruleTile"] = {
                "mode": auto_meta.get("mode"),
                "tileCount": auto_meta.get("tile_count"),
            }
    if project.nine_slice is not None:
        godot_hints["nineSliceLTRB"] = list(project.nine_slice)

    meta_block: dict[str, Any] = {
        "app": "pixel-art-forge",
        "version": "1.1.0",
        "image": png_info["filename"],
        "format": "RGBA8888",
        "size": {"w": png_info["sheet_width"], "h": png_info["sheet_height"]},
        "scale": "1",
        "palette": project.spec.palette.name,
        "category": project.category,
        "frameTags": frame_tags,
        "layers": [{"name": ln, "opacity": 255, "blendMode": "normal"} for ln in project.all_layer_names()],
        "slices": slices_json,
        "engine_hints": {
            "unity": unity_hints,
            "godot": godot_hints,
        },
    }
    if frame_files:
        meta_block["frameImages"] = [f"frames/{p.name}" for p in frame_files]
    if gif_path is not None:
        meta_block["gif"] = gif_path.name
    if "autotile" in project.metadata:
        meta_block["autotile"] = project.metadata["autotile"]
    if "ui_states" in project.metadata:
        meta_block["ui_states"] = project.metadata["ui_states"]
    if "isometric" in project.metadata:
        meta_block["isometric"] = project.metadata["isometric"]

    payload = {
        "frames": frames_list,
        "meta": meta_block,
    }

    out_path = out / f"{project.name}.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path
