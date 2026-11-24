"""Programmatic QA checks, coordinate-ruler inspection sheets, and project contact sheets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .canvas import TRANSPARENT, IndexedLayer, PixelProject
from .cleanup import (
    check_nine_slice_consistency,
    check_tile_seams,
    find_orphan_pixels,
    find_outline_doubles,
)
from .palette import Palette


def layer_to_pil(layer: IndexedLayer, palette: Palette) -> Image.Image:
    """Convert an IndexedLayer to a crisp 1x RGBA PIL Image (strict 0 or 255 alpha)."""
    img = Image.new("RGBA", (layer.width, layer.height), (0, 0, 0, 0))
    px = img.load()
    for y in range(layer.height):
        row = layer.grid[y]
        for x in range(layer.width):
            c = row[x]
            if c != TRANSPARENT:
                r, g, b = palette.rgb_at(c)
                px[x, y] = (r, g, b, 255)
    return img


def validate_project(project: PixelProject) -> dict[str, Any]:
    """Run hard error checks and soft quality metrics on a PixelProject."""
    errors: list[str] = []
    warnings: list[str] = []

    if project.width <= 0 or project.height <= 0:
        errors.append(f"Invalid dimensions: {project.width}x{project.height}")
    if not project.frames:
        errors.append("Project has zero frames.")

    pal_size = len(project.spec.palette)
    total_orphans = 0
    total_outline_doubles = 0
    orphan_coords_f0: list[tuple[int, int]] = []
    orphans_by_frame: dict[int, list[tuple[int, int]]] = {}
    frame_bboxes: list[tuple[int, int, int, int] | None] = []
    seam_reports: list[dict[str, Any]] = []
    edge_touch_frames: list[int] = []
    nine_slice_reports: list[dict[str, Any]] = []

    # Exempt intentional specular highlights (brightest shade of 3+ ramps) and outline ink from orphan noise
    exempt_orphans: set[int] = {int(project.spec.outline.get("color_index", project.spec.palette.darkest_index()))}
    for ramp in project.spec.materials.values():
        if len(ramp) >= 3:
            exempt_orphans.add(ramp[-1])

    for fi, fr in enumerate(project.frames):
        comp = project.composite_frame(fi)
        if comp.width != project.width or comp.height != project.height:
            errors.append(f"Frame {fi} size mismatch: {comp.width}x{comp.height} != {project.width}x{project.height}")
        if comp.non_empty_count() == 0:
            errors.append(f"Frame {fi} is completely empty.")
        # Validate palette indices
        for c in comp.used_colors():
            if not (0 <= c < pal_size):
                errors.append(f"Frame {fi} has out-of-palette index {c}.")
        # Collect outline pixels & detect redundant L-doubles on dedicated outline layers
        outline_coords: set[tuple[int, int]] = set()
        solid_body = fr.composite_solid()
        for lname, lyr in fr.layers.items():
            if "outline" in lname.lower():
                total_outline_doubles += len(find_outline_doubles(lyr, solid_layer=solid_body))
                for ox, oy, _ in lyr.iter_opaque():
                    outline_coords.add((ox, oy))

        f_orphans = [
            pt
            for pt in find_orphan_pixels(
                comp,
                exclude_indices=exempt_orphans,
                ignore_material_boundaries=True,
            )
            if pt not in outline_coords
        ]
        orphans_by_frame[fi] = f_orphans
        if fi == 0:
            orphan_coords_f0 = f_orphans
        total_orphans += len(f_orphans)
        bb = comp.bbox()
        frame_bboxes.append(bb)

        # Check safe margin contact for icons & characters (characters may touch bottom y=H-1 for feet)
        if bb is not None:
            min_x, min_y, max_x, max_y = bb
            if project.category == "icons":
                if min_x == 0 or min_y == 0 or max_x == project.width - 1 or max_y == project.height - 1:
                    edge_touch_frames.append(fi)
            elif project.category == "characters":
                if min_x == 0 or min_y == 0 or max_x == project.width - 1:
                    edge_touch_frames.append(fi)

        # Check tile seams for tilesets (skip non-wrapping isometric tiles and non-interior autotile edge cells)
        is_iso_tile = bool(project.metadata.get("isometric")) or project.spec.perspective == "isometric"
        auto_meta = project.metadata.get("autotile")
        if project.category == "tilesets" and not is_iso_tile:
            should_check_seam = True
            if isinstance(auto_meta, dict):
                tiles_info = auto_meta.get("tiles", [])
                full_mask = 255 if auto_meta.get("mode") == "blob47" else (1 | 4 | 16 | 64)
                cell_mask = tiles_info[fi].get("bitmask") if fi < len(tiles_info) else None
                should_check_seam = cell_mask == full_mask
            if should_check_seam:
                sr = check_tile_seams(comp, project.spec.palette)
                sr["frame"] = fi
                seam_reports.append(sr)
                if not sr["seamless_ok"]:
                    warnings.append(
                        f"Tile frame {fi} edge contrast high (LR={sr['avg_lr_diff']}, TB={sr['avg_tb_diff']}); verify 3x3 preview."
                    )

    seam_report: dict[str, Any] | None = None
    if seam_reports:
        seam_report = {
            "frames_checked": len(seam_reports),
            "avg_lr_diff": max(r["avg_lr_diff"] for r in seam_reports),
            "avg_tb_diff": max(r["avg_tb_diff"] for r in seam_reports),
            "max_interior_col_diff": max(r["max_interior_col_diff"] for r in seam_reports),
            "max_interior_row_diff": max(r["max_interior_row_diff"] for r in seam_reports),
            "seamless_ok": all(bool(r["seamless_ok"]) for r in seam_reports),
        }

    # Check tags bounds
    for tag in project.tags:
        if tag.from_frame < 0 or tag.to_frame >= len(project.frames) or tag.from_frame > tag.to_frame:
            errors.append(f"Tag {tag.name!r} has invalid frame range [{tag.from_frame}, {tag.to_frame}].")

    # Check 9-slice bounds & stretchable edge-band pixel consistency
    nine_slice_report: dict[str, Any] | None = None
    if project.nine_slice is not None:
        l, t, r, b = project.nine_slice
        if l + r >= project.width or t + b >= project.height:
            errors.append(f"9-slice margins {project.nine_slice} exceed canvas {project.width}x{project.height}.")
        else:
            for fi in range(len(project.frames)):
                comp_ns = project.composite_frame(fi)
                ns_rep = check_nine_slice_consistency(comp_ns, project.nine_slice)
                ns_rep["frame"] = fi
                nine_slice_reports.append(ns_rep)
                if not ns_rep["consistent"]:
                    warnings.append(
                        f"9-slice stretch band mismatch on frame {fi} "
                        f"(cols={ns_rep['mismatch_columns'][:6]}, rows={ns_rep['mismatch_rows'][:6]}); "
                        "keep ornaments strictly inside corner margins."
                    )
            nine_slice_report = {
                "consistent": all(bool(r_ns["consistent"]) for r_ns in nine_slice_reports),
                "frames": nine_slice_reports,
            }

    # Select non-zero alert frame when later animation frames exhibit border contact or higher noise
    alert_frame: int | None = None
    if len(project.frames) > 1:
        f0_orphans_n = len(orphans_by_frame.get(0, []))
        best_score = 0
        for fi in range(1, len(project.frames)):
            edge_hit = 1 if (fi in edge_touch_frames and 0 not in edge_touch_frames) else 0
            extra_orphans = max(0, len(orphans_by_frame.get(fi, [])) - f0_orphans_n)
            score = edge_hit * 100 + extra_orphans
            if score > best_score:
                best_score = score
                alert_frame = fi

    # Soft checks
    clipped = project.total_clipped_pixels()
    if clipped > 0:
        warnings.append(f"{clipped} pixel writes were clipped outside canvas bounds.")
    avg_orphans = total_orphans / max(1, len(project.frames))
    orphan_thresh = max(3, (project.width * project.height) // 128)
    if avg_orphans > orphan_thresh:
        warnings.append(
            f"Avg {avg_orphans:.1f} isolated pixels/frame ({total_orphans} total, threshold {orphan_thresh}); review for stray noise."
        )
    avg_doubles = total_outline_doubles / max(1, len(project.frames))
    doubles_thresh = max(4, (project.width + project.height) // 8)
    if avg_doubles > doubles_thresh:
        warnings.append(
            f"Avg {avg_doubles:.1f} L-double outline corners/frame ({total_outline_doubles} total); review 1px curves."
        )
    if edge_touch_frames:
        warnings.append(
            f"Sprite touches outer canvas border on frame(s) {edge_touch_frames}; verify safe margin for outline."
        )

    # Animation bottom-anchor drift check for characters
    if project.category == "characters" and len(frame_bboxes) > 1:
        bottoms = [bb[3] for bb in frame_bboxes if bb is not None]
        if bottoms and (max(bottoms) - min(bottoms) > 2):
            warnings.append(
                f"Character feet bottom Y drifts by {max(bottoms) - min(bottoms)}px across frames ({bottoms})."
            )

    used_colors = sorted(project.used_colors())
    if project.spec.max_colors is not None and len(used_colors) > project.spec.max_colors:
        errors.append(
            f"Used {len(used_colors)} colors, exceeding locked max_colors limit of {project.spec.max_colors}."
        )
    return {
        "passed": len(errors) == 0,
        "name": project.name,
        "category": project.category,
        "dimensions": [project.width, project.height],
        "frames": len(project.frames),
        "unique_colors_used": len(used_colors),
        "max_colors": project.spec.max_colors,
        "palette_size": pal_size,
        "used_color_indices": used_colors,
        "clipped_pixels": clipped,
        "orphan_pixels": total_orphans,
        "orphan_coords_f0": orphan_coords_f0,
        "orphans_by_frame": {str(k): v for k, v in orphans_by_frame.items() if v},
        "alert_frame": alert_frame,
        "outline_doubles": total_outline_doubles,
        "edge_touch_frames": edge_touch_frames,
        "nine_slice_report": nine_slice_report,
        "seam_report": seam_report,
        "seam_reports": seam_reports,
        "errors": errors,
        "warnings": warnings,
    }


def _make_checkerboard(w: int, h: int, cell: int = 4) -> Image.Image:
    img = Image.new("RGBA", (w, h))
    px = img.load()
    c1 = (54, 58, 72, 255)
    c2 = (72, 77, 94, 255)
    for y in range(h):
        for x in range(w):
            px[x, y] = c1 if ((x // cell + y // cell) % 2 == 0) else c2
    return img


def _paste_over_bg(sprite: Image.Image, bg: Image.Image) -> Image.Image:
    out = bg.copy()
    out.alpha_composite(sprite)
    return out


def _stretch_nine_slice(img: Image.Image, margins: tuple[int, int, int, int], target_w: int, target_h: int) -> Image.Image:
    """Nearest-neighbor 9-slice stretch test renderer."""
    l, t, r, b = margins
    sw, sh = img.size
    cw = max(1, sw - l - r)
    ch = max(1, sh - t - b)
    dcw = max(1, target_w - l - r)
    dch = max(1, target_h - t - b)

    out = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    # Corners
    out.paste(img.crop((0, 0, l, t)), (0, 0))
    out.paste(img.crop((sw - r, 0, sw, t)), (target_w - r, 0))
    out.paste(img.crop((0, sh - b, l, sh)), (0, target_h - b))
    out.paste(img.crop((sw - r, sh - b, sw, sh)), (target_w - r, target_h - b))
    # Edges
    out.paste(img.crop((l, 0, l + cw, t)).resize((dcw, t), Image.NEAREST), (l, 0))
    out.paste(img.crop((l, sh - b, l + cw, sh)).resize((dcw, b), Image.NEAREST), (l, target_h - b))
    out.paste(img.crop((0, t, l, t + ch)).resize((l, dch), Image.NEAREST), (0, t))
    out.paste(img.crop((sw - r, t, sw, t + ch)).resize((r, dch), Image.NEAREST), (target_w - r, t))
    # Center
    out.paste(img.crop((l, t, l + cw, t + ch)).resize((dcw, dch), Image.NEAREST), (l, t))
    return out


def _render_onion_skin(img_a: Image.Image, img_b: Image.Image) -> Image.Image:
    """Render an alpha silhouette onion skin comparing img_a (cyan) vs img_b (magenta)."""
    w, h = img_a.size
    onion = Image.new("RGBA", (w, h), (22, 24, 34, 255))
    p0, p1 = img_a.load(), img_b.load()
    op = onion.load()
    for yy in range(h):
        for xx in range(w):
            a0 = p0[xx, yy][3] > 0
            a1 = p1[xx, yy][3] > 0
            if a0 and a1:
                op[xx, yy] = (210, 220, 235, 255)
            elif a0:
                op[xx, yy] = (70, 200, 255, 255)
            elif a1:
                op[xx, yy] = (255, 90, 170, 255)
    return onion


def _select_onion_pairs(project: PixelProject) -> list[tuple[str, int, int]]:
    """Select representative frame pairs for onion-skin inspection across animation tags."""
    n = len(project.frames)
    if n < 2:
        return []
    pairs: list[tuple[str, int, int]] = []
    if project.tags:
        for tag in project.tags[:4]:
            if tag.to_frame > tag.from_frame:
                pairs.append((f"{tag.name} F{tag.from_frame}->F{tag.from_frame + 1}", tag.from_frame, tag.from_frame + 1))
        if len(pairs) == 1:
            t0 = project.tags[0]
            if t0.to_frame - t0.from_frame >= 2:
                pairs.append((f"{t0.name} F{t0.to_frame}->F{t0.from_frame}", t0.to_frame, t0.from_frame))
    if not pairs:
        pairs.append(("F0->F1", 0, 1))
    return pairs


def _draw_zoomed_ruler_panel(
    sheet: Image.Image,
    draw: ImageDraw.ImageDraw,
    frame_img: Image.Image,
    frame_idx: int,
    project: PixelProject,
    cx: int,
    cy: int,
    zoom: int,
    ruler_pad: int,
    orphan_coords: list[tuple[int, int]],
    edge_alert: bool,
    font: Any,
    title_prefix: str = "",
) -> int:
    """Render a zoomed frame panel with pixel gridlines, X/Y coordinate rulers, and QA markers. Returns bottom Y."""
    w, h = project.width, project.height
    zoom_w, zoom_h = w * zoom, h * zoom
    label = f"{title_prefix}{zoom}x Zoom + Coordinate Ruler (Frame {frame_idx})"
    title_col = (245, 200, 96, 255) if edge_alert else (195, 202, 220, 255)
    draw.text((cx + ruler_pad, cy), label, fill=title_col, font=font)
    gx = cx + ruler_pad
    gy = cy + ruler_pad

    checker = _make_checkerboard(zoom_w, zoom_h, max(4, zoom // 2))
    zoomed = frame_img.resize((zoom_w, zoom_h), Image.NEAREST)
    panel = _paste_over_bg(zoomed, checker)
    pdraw = ImageDraw.Draw(panel)

    grid_col = (255, 255, 255, 34)
    major_col = (255, 220, 120, 90)
    step = 4 if max(w, h) <= 40 else 8
    for x in range(1, w):
        col = major_col if x % step == 0 else grid_col
        pdraw.line([(x * zoom, 0), (x * zoom, zoom_h)], fill=col, width=1)
    for y in range(1, h):
        col = major_col if y % step == 0 else grid_col
        pdraw.line([(0, y * zoom), (zoom_w, y * zoom)], fill=col, width=1)

    for ox_i, oy_i in orphan_coords:
        if 0 <= ox_i < w and 0 <= oy_i < h:
            pdraw.rectangle(
                [ox_i * zoom + 1, oy_i * zoom + 1, (ox_i + 1) * zoom - 2, (oy_i + 1) * zoom - 2],
                outline=(255, 160, 40, 235),
                width=1,
            )

    px_piv, py_piv = project.pivot
    if 0 <= px_piv < w and 0 <= py_piv < h:
        cx_p = px_piv * zoom + zoom // 2
        cy_p = py_piv * zoom + zoom // 2
        pdraw.line([(cx_p - 5, cy_p), (cx_p + 5, cy_p)], fill=(255, 70, 120, 220), width=1)
        pdraw.line([(cx_p, cy_p - 5), (cx_p, cy_p + 5)], fill=(255, 70, 120, 220), width=1)

    if project.nine_slice is not None:
        sl, st, sr, sb = project.nine_slice
        s_col = (80, 230, 255, 190)
        pdraw.line([(sl * zoom, 0), (sl * zoom, zoom_h)], fill=s_col, width=1)
        pdraw.line([((w - sr) * zoom, 0), ((w - sr) * zoom, zoom_h)], fill=s_col, width=1)
        pdraw.line([(0, st * zoom), (zoom_w, st * zoom)], fill=s_col, width=1)
        pdraw.line([(0, (h - sb) * zoom), (zoom_w, (h - sb) * zoom)], fill=s_col, width=1)

    sheet.alpha_composite(panel, (gx, gy))
    border_col = (245, 120, 96, 255) if edge_alert else (110, 120, 150, 255)
    draw.rectangle([gx - 1, gy - 1, gx + zoom_w, gy + zoom_h], outline=border_col)

    for x in range(0, w, step):
        tx = gx + x * zoom + 1
        draw.text((tx, gy - 14), str(x), fill=(180, 192, 220, 255), font=font)
        draw.line([(gx + x * zoom, gy - 3), (gx + x * zoom, gy - 1)], fill=(180, 192, 220, 255))
    for y in range(0, h, step):
        ty = gy + y * zoom + 1
        draw.text((cx + 2, ty), f"{y:>2}", fill=(180, 192, 220, 255), font=font)
        draw.line([(gx - 3, gy + y * zoom), (gx - 1, gy + y * zoom)], fill=(180, 192, 220, 255))
    return gy + zoom_h


def render_inspection_sheet(
    project: PixelProject,
    out_path: str | Path,
    qa_report: dict[str, Any] | None = None,
    focus_frame: int | None = None,
) -> Path:
    """Generate a high-clarity QA inspection sheet with X/Y coordinate rulers and context tests."""
    report = qa_report or validate_project(project)
    font = ImageFont.load_default()
    pal = project.spec.palette

    w, h = project.width, project.height
    frame_imgs = [layer_to_pil(project.composite_frame(i), pal) for i in range(len(project.frames))]
    main_fi = focus_frame if (focus_frame is not None and 0 <= focus_frame < len(frame_imgs)) else 0
    f0 = frame_imgs[main_fi]

    # Secondary zoomed ruler panel when a non-zero animation frame triggers border/orphan alerts
    raw_alert = report.get("alert_frame")
    alert_fi: int | None = (
        int(raw_alert)
        if (focus_frame is None and isinstance(raw_alert, int) and 0 < raw_alert < len(frame_imgs))
        else None
    )

    # Adaptive zoom so center inspection canvas sits cleanly around 256..384px
    zoom = max(4, min(14, 288 // max(w, h)))
    zoom_w, zoom_h = w * zoom, h * zoom
    alert_zoom = max(4, min(10, 192 // max(w, h)))
    alert_zoom_h = h * alert_zoom

    ruler_pad = 26
    pad = 16
    left_col_w = max(120, w * 2 + 28)
    center_col_w = zoom_w + ruler_pad + 12

    # Compute right panel width & height based on category
    onion_pairs: list[tuple[str, int, int]] = []
    right_needed_h = 280
    is_iso_tile = project.category == "tilesets" and (
        bool(project.metadata.get("isometric")) or project.spec.perspective == "isometric"
    )
    auto_meta = project.metadata.get("autotile") if project.category == "tilesets" else None
    ui_states = project.metadata.get("ui_states") if project.category == "ui" else None

    if isinstance(auto_meta, dict):
        auto_scale = max(2, min(4, 48 // max(w, h)))
        iso_grid_w = w * auto_scale * 3
        atlas_scale = 2 if max(w, h) <= 16 else 1
        atlas_cols = 8 if len(frame_imgs) > 16 else 4
        atlas_rows = (len(frame_imgs) + atlas_cols - 1) // atlas_cols
        atlas_w = atlas_cols * (w * atlas_scale + 3)
        right_col_w = max(220, iso_grid_w + 20, atlas_w + 16)
        right_needed_h = 36 + h * auto_scale * 3 + 26 + atlas_rows * (h * atlas_scale + 3) + 12
    elif is_iso_tile:
        tile_scale = max(2, min(4, 96 // max(w, h)))
        iso_info = project.metadata.get("isometric") if isinstance(project.metadata.get("isometric"), dict) else {}
        dw_iso = int(iso_info.get("diamond_w", max(8, (w // 4) * 4)))
        dh_iso = int(iso_info.get("diamond_h", dw_iso // 2))
        iso_canvas_w = (dw_iso * 3) * tile_scale
        iso_canvas_h = (dh_iso * 3 + h) * tile_scale
        right_col_w = max(220, iso_canvas_w + 20)
        right_needed_h = 40 + iso_canvas_h
    elif project.category == "tilesets":
        tile_scale = max(3, min(6, 72 // max(w, h)))
        grid3_w = w * tile_scale * 3
        grid3_h = h * tile_scale * 3
        right_col_w = max(200, grid3_w + 20)
        right_needed_h = 36 + grid3_h
        if len(frame_imgs) > 1:
            var_scale = max(2, min(4, 48 // max(w, h)))
            var_cell_w = w * var_scale + 10
            var_cols = max(1, (right_col_w - 8) // var_cell_w)
            var_rows = (len(frame_imgs) + var_cols - 1) // var_cols
            right_needed_h += 28 + var_rows * (h * var_scale + 22)
    elif isinstance(ui_states, dict) and len(frame_imgs) > 1:
        st_scale = max(2, min(3, 96 // max(w, h)))
        right_col_w = max(240, 2 * (w * st_scale + 10) + 16)
        st_rows = (len(frame_imgs) + 1) // 2
        right_needed_h = 36 + st_rows * (h * st_scale + 22) + (120 if project.nine_slice is not None else 0)
    elif len(frame_imgs) > 1:
        strip_scale = max(2, min(4, 112 // max(w, h)))
        cell_w, cell_h = w * strip_scale, h * strip_scale
        cols_strip = min(4, len(frame_imgs))
        onion_pairs = _select_onion_pairs(project)
        onion_cols = max(1, min(len(onion_pairs), max(2, cols_strip)))
        right_col_w = max(220, max(cols_strip, onion_cols) * (cell_w + 8) + 16)
        rows_est = (len(frame_imgs) + cols_strip - 1) // cols_strip
        onion_rows = (len(onion_pairs) + onion_cols - 1) // onion_cols if onion_pairs else 0
        right_needed_h = 32 + rows_est * (cell_h + 18) + (16 + onion_rows * (cell_h + 22) if onion_rows else 0)
    elif project.nine_slice is not None:
        right_col_w = 240
    else:
        right_col_w = max(180, w * 3 + 24)

    total_w = pad * 4 + left_col_w + center_col_w + right_col_w
    header_h = 34
    footer_h = 54
    left_needed_h = 28 + 3 * (h + 27) + (h * 2 + 28)
    center_needed_h = zoom_h + ruler_pad + 24
    if alert_fi is not None:
        center_needed_h += alert_zoom_h + ruler_pad + 22
    body_h = max(center_needed_h, left_needed_h, right_needed_h, 280)
    total_h = header_h + body_h + footer_h

    sheet = Image.new("RGBA", (total_w, total_h), (24, 26, 36, 255))
    draw = ImageDraw.Draw(sheet)

    # Header bar
    status = "PASS" if report["passed"] else "FAIL"
    status_col = (102, 217, 138, 255) if report["passed"] else (245, 96, 110, 255)
    cap_txt = f" (cap {report['max_colors']})" if report.get("max_colors") is not None else ""
    draw.rectangle([0, 0, total_w, header_h], fill=(16, 18, 26, 255))
    draw.text(
        (12, 10),
        f"[{status}] {project.name}  |  {project.category}  |  {w}x{h}px  |  {len(frame_imgs)}f  |  palette: {pal.name}{cap_txt}",
        fill=status_col,
        font=font,
    )

    # --- LEFT PANEL: 1x & 2x readability checks on dark/light/checker ---
    lx = pad
    ly = header_h + 10
    draw.text((lx, ly), "1x & 2x Readability", fill=(195, 202, 220, 255), font=font)
    ly += 18

    for label, bg_color in (("1x Checker", None), ("1x Dark", (20, 22, 34, 255)), ("1x Light", (232, 234, 240, 255))):
        draw.text((lx, ly), label, fill=(140, 148, 170, 255), font=font)
        ly += 13
        bg = _make_checkerboard(w + 8, h + 8, 4) if bg_color is None else Image.new("RGBA", (w + 8, h + 8), bg_color)
        bg.alpha_composite(f0, (4, 4))
        sheet.alpha_composite(bg, (lx, ly))
        ly += h + 14

    # 2x preview
    draw.text((lx, ly), "2x Preview", fill=(140, 148, 170, 255), font=font)
    ly += 13
    f0_2x = f0.resize((w * 2, h * 2), Image.NEAREST)
    bg2 = _make_checkerboard(w * 2 + 8, h * 2 + 8, 6)
    bg2.alpha_composite(f0_2x, (4, 4))
    sheet.alpha_composite(bg2, (lx, ly))

    # --- CENTER PANEL: Zoomed view with X/Y Coordinate Rulers & Grid ---
    cx = pad * 2 + left_col_w
    cy = header_h + 10
    orphans_map = report.get("orphans_by_frame", {})
    main_orphans = orphans_map.get(str(main_fi), report.get("orphan_coords_f0", []) if main_fi == 0 else [])
    edge_frames = set(report.get("edge_touch_frames", []))
    bottom_y = _draw_zoomed_ruler_panel(
        sheet=sheet,
        draw=draw,
        frame_img=f0,
        frame_idx=main_fi,
        project=project,
        cx=cx,
        cy=cy,
        zoom=zoom,
        ruler_pad=ruler_pad,
        orphan_coords=main_orphans,
        edge_alert=(main_fi in edge_frames),
        font=font,
    )
    if alert_fi is not None:
        alert_orphans = orphans_map.get(str(alert_fi), [])
        _draw_zoomed_ruler_panel(
            sheet=sheet,
            draw=draw,
            frame_img=frame_imgs[alert_fi],
            frame_idx=alert_fi,
            project=project,
            cx=cx,
            cy=bottom_y + 14,
            zoom=alert_zoom,
            ruler_pad=ruler_pad,
            orphan_coords=alert_orphans,
            edge_alert=(alert_fi in edge_frames),
            font=font,
            title_prefix="[ALERT] ",
        )

    # --- RIGHT PANEL: Context-Specific Visual Verification ---
    rx = pad * 3 + left_col_w + center_col_w
    ry = header_h + 10

    if isinstance(auto_meta, dict):
        auto_scale = max(2, min(4, 48 // max(w, h)))
        mode_lbl = auto_meta.get("mode", "autotile")
        draw.text((rx, ry), f"Auto-Tile 3x3 Island Demo ({mode_lbl})", fill=(195, 202, 220, 255), font=font)
        ry += 18
        # Build mask -> frame_index map to assemble a live 3x3 connected island preview
        mask_to_idx = {int(t["bitmask"]): int(t["frame"]) for t in auto_meta.get("tiles", [])}
        # 3x3 island neighbor bitmasks (N=1, NE=2, E=4, SE=8, S=16, SW=32, W=64, NW=128)
        if mode_lbl == "blob47":
            island_masks = [
                [4 | 8 | 16, 4 | 8 | 16 | 32 | 64, 16 | 32 | 64],
                [1 | 2 | 4 | 8 | 16, 255, 1 | 16 | 32 | 64 | 128],
                [1 | 2 | 4, 1 | 2 | 4 | 64 | 128, 1 | 64 | 128],
            ]
        else:
            island_masks = [
                [4 | 16, 4 | 16 | 64, 16 | 64],
                [1 | 4 | 16, 1 | 4 | 16 | 64, 1 | 16 | 64],
                [1 | 4, 1 | 4 | 64, 1 | 64],
            ]
        grid3 = Image.new("RGBA", (w * auto_scale * 3, h * auto_scale * 3), (22, 24, 34, 255))
        for ty_i in range(3):
            for tx_i in range(3):
                fi_m = mask_to_idx.get(island_masks[ty_i][tx_i], 0)
                t_im = frame_imgs[fi_m].resize((w * auto_scale, h * auto_scale), Image.NEAREST)
                grid3.alpha_composite(t_im, (tx_i * w * auto_scale, ty_i * h * auto_scale))
        sheet.alpha_composite(grid3, (rx, ry))
        draw.rectangle([rx - 1, ry - 1, rx + grid3.width, ry + grid3.height], outline=(110, 120, 150, 255))
        ry += grid3.height + 12

        draw.text((rx, ry), f"Atlas Overview ({len(frame_imgs)} tiles)", fill=(160, 170, 195, 255), font=font)
        ry += 14
        atlas_scale = 2 if max(w, h) <= 16 else 1
        atlas_cols = 8 if len(frame_imgs) > 16 else 4
        aw, ah = w * atlas_scale, h * atlas_scale
        for ai, aim in enumerate(frame_imgs):
            ax = rx + (ai % atlas_cols) * (aw + 3)
            ay = ry + (ai // atlas_cols) * (ah + 3)
            sheet.alpha_composite(aim.resize((aw, ah), Image.NEAREST), (ax, ay))
            draw.rectangle([ax - 1, ay - 1, ax + aw, ay + ah], outline=(76, 84, 108, 255))

    elif is_iso_tile:
        tile_scale = max(2, min(4, 96 // max(w, h)))
        iso_info = project.metadata.get("isometric") if isinstance(project.metadata.get("isometric"), dict) else {}
        dw_iso = int(iso_info.get("diamond_w", max(8, (w // 4) * 4)))
        dh_iso = int(iso_info.get("diamond_h", dw_iso // 2))
        draw.text((rx, ry), f"3x3 Isometric Stagger Test ({tile_scale}x)", fill=(195, 202, 220, 255), font=font)
        ry += 18
        iso_w_raw = dw_iso * 3
        iso_h_raw = dh_iso * 3 + h
        iso_bg = Image.new("RGBA", (iso_w_raw, iso_h_raw), (22, 24, 34, 255))
        origin_x = (iso_w_raw - w) // 2
        origin_y = 2
        for gy_i in range(3):
            for gx_i in range(3):
                px_iso = origin_x + (gx_i - gy_i) * (dw_iso // 2)
                py_iso = origin_y + (gx_i + gy_i) * (dh_iso // 2)
                t_raw = frame_imgs[(gx_i + gy_i * 2) % len(frame_imgs)]
                iso_bg.alpha_composite(t_raw, (px_iso, py_iso))
        iso_z = iso_bg.resize((iso_w_raw * tile_scale, iso_h_raw * tile_scale), Image.NEAREST)
        sheet.alpha_composite(iso_z, (rx, ry))
        draw.rectangle([rx - 1, ry - 1, rx + iso_z.width, ry + iso_z.height], outline=(110, 120, 150, 255))

    elif project.category == "tilesets":
        tile_scale = max(3, min(6, 72 // max(w, h)))
        title_txt = (
            f"3x3 Mixed Variants Test ({tile_scale}x)"
            if len(frame_imgs) > 1
            else f"3x3 Seamless Tile Test ({tile_scale}x)"
        )
        draw.text((rx, ry), title_txt, fill=(195, 202, 220, 255), font=font)
        ry += 18
        scaled_tiles = [im.resize((w * tile_scale, h * tile_scale), Image.NEAREST) for im in frame_imgs]
        grid3 = Image.new("RGBA", (w * tile_scale * 3, h * tile_scale * 3), (0, 0, 0, 255))
        for ty_i in range(3):
            for tx_i in range(3):
                t_im = scaled_tiles[(tx_i + ty_i) % len(scaled_tiles)]
                grid3.alpha_composite(t_im, (tx_i * w * tile_scale, ty_i * h * tile_scale))
        sheet.alpha_composite(grid3, (rx, ry))
        draw.rectangle([rx - 1, ry - 1, rx + grid3.width, ry + grid3.height], outline=(110, 120, 150, 255))
        if len(frame_imgs) > 1:
            ry += grid3.height + 12
            draw.text((rx, ry), "Tile Variants (Per-Frame Seam QA)", fill=(160, 170, 195, 255), font=font)
            ry += 14
            var_scale = max(2, min(4, 48 // max(w, h)))
            vw, vh = w * var_scale, h * var_scale
            var_cols = max(1, (right_col_w - 8) // (vw + 10))
            seam_list = report.get("seam_reports", [])
            for vi, vim in enumerate(frame_imgs):
                vx = rx + (vi % var_cols) * (vw + 10)
                vy = ry + (vi // var_cols) * (vh + 22)
                sheet.alpha_composite(vim.resize((vw, vh), Image.NEAREST), (vx, vy))
                ok_v = seam_list[vi]["seamless_ok"] if vi < len(seam_list) else True
                col_v = (102, 217, 138, 255) if ok_v else (245, 200, 96, 255)
                draw.rectangle([vx - 1, vy - 1, vx + vw, vy + vh], outline=col_v)
                draw.text((vx, vy + vh + 2), f"V{vi} {'OK' if ok_v else 'SEAM'}", fill=col_v, font=font)

    elif isinstance(ui_states, dict) and len(frame_imgs) > 1:
        st_scale = max(2, min(3, 96 // max(w, h)))
        draw.text((rx, ry), f"UI States Preview ({st_scale}x)", fill=(195, 202, 220, 255), font=font)
        ry += 18
        sw, sh = w * st_scale, h * st_scale
        idx_to_name = {int(v): str(k) for k, v in ui_states.items()}
        for si, sim in enumerate(frame_imgs):
            sx = rx + (si % 2) * (sw + 10)
            sy = ry + (si // 2) * (sh + 22)
            bg_u = _make_checkerboard(sw, sh, 4)
            bg_u.alpha_composite(sim.resize((sw, sh), Image.NEAREST))
            sheet.alpha_composite(bg_u, (sx, sy))
            draw.rectangle([sx - 1, sy - 1, sx + sw, sy + sh], outline=(90, 100, 125, 255))
            draw.text((sx, sy + sh + 2), idx_to_name.get(si, f"S{si}"), fill=(160, 170, 195, 255), font=font)
        ry += ((len(frame_imgs) + 1) // 2) * (sh + 22) + 8
        if project.nine_slice is not None:
            draw.text((rx, ry), "9-Slice Wide Test (2x)", fill=(160, 170, 195, 255), font=font)
            ry += 14
            tw = max(w + 24, 64)
            stretched = _stretch_nine_slice(f0, project.nine_slice, tw, h)
            st2 = stretched.resize((tw * 2, h * 2), Image.NEAREST)
            sheet.alpha_composite(st2, (rx, ry))

    elif len(frame_imgs) > 1:
        strip_scale = max(2, min(4, 112 // max(w, h)))
        draw.text((rx, ry), f"Animation Frames ({strip_scale}x) + Onion Skin", fill=(195, 202, 220, 255), font=font)
        ry += 18
        cell_w, cell_h = w * strip_scale, h * strip_scale
        cols_strip = min(4, len(frame_imgs))
        for fi, fimg in enumerate(frame_imgs):
            col_i = fi % cols_strip
            row_i = fi // cols_strip
            fx = rx + col_i * (cell_w + 6)
            fy = ry + row_i * (cell_h + 18)
            bg_c = _make_checkerboard(cell_w, cell_h, 4)
            bg_c.alpha_composite(fimg.resize((cell_w, cell_h), Image.NEAREST))
            sheet.alpha_composite(bg_c, (fx, fy))
            draw.rectangle([fx - 1, fy - 1, fx + cell_w, fy + cell_h], outline=(90, 100, 125, 255))
            draw.text((fx, fy + cell_h + 2), f"F{fi} {project.frames[fi].duration_ms}ms", fill=(160, 170, 195, 255), font=font)

        # Render per-tag onion skins below the frame strip (guaranteed to fit!)
        rows_used = (len(frame_imgs) + cols_strip - 1) // cols_strip
        oy_base = ry + rows_used * (cell_h + 18) + 10
        onion_cols = max(1, min(len(onion_pairs), max(2, cols_strip)))
        for oi, (olabel, fa, fb) in enumerate(onion_pairs):
            ox_o = rx + (oi % onion_cols) * (cell_w + 8)
            oy_o = oy_base + (oi // onion_cols) * (cell_h + 22)
            draw.text((ox_o, oy_o), olabel[:16], fill=(160, 170, 195, 255), font=font)
            onion = _render_onion_skin(frame_imgs[fa], frame_imgs[fb])
            sheet.alpha_composite(onion.resize((cell_w, cell_h), Image.NEAREST), (ox_o, oy_o + 13))
            draw.rectangle([ox_o - 1, oy_o + 12, ox_o + cell_w, oy_o + 13 + cell_h], outline=(90, 100, 125, 255))

    elif project.nine_slice is not None:
        draw.text((rx, ry), "9-Slice Stretch Tests (2x)", fill=(195, 202, 220, 255), font=font)
        ry += 18
        for label, tw, th in (("Wide Bar (96x24)", 96, 24), ("Tall Card (44x72)", 44, 72)):
            draw.text((rx, ry), label, fill=(140, 148, 170, 255), font=font)
            ry += 13
            stretched = _stretch_nine_slice(f0, project.nine_slice, tw, th)
            st2 = stretched.resize((tw * 2, th * 2), Image.NEAREST)
            bg_s = Image.new("RGBA", st2.size, (18, 20, 28, 255))
            bg_s.alpha_composite(st2)
            sheet.alpha_composite(bg_s, (rx, ry))
            ry += st2.height + 10

    else:
        # Silhouette Test + Palette Swatch Strip (especially vital for Icons/Props!)
        sil_scale = max(2, min(4, 128 // max(w, h)))
        draw.text((rx, ry), f"Silhouette Test ({sil_scale}x)", fill=(195, 202, 220, 255), font=font)
        ry += 18
        sil = Image.new("RGBA", (w, h), (235, 238, 245, 255))
        sp = sil.load()
        fp = f0.load()
        for yy in range(h):
            for xx in range(w):
                if fp[xx, yy][3] > 0:
                    sp[xx, yy] = (18, 20, 28, 255)
        sil_z = sil.resize((w * sil_scale, h * sil_scale), Image.NEAREST)
        sheet.alpha_composite(sil_z, (rx, ry))
        ry += sil_z.height + 16

        used = report["used_color_indices"]
        draw.text((rx, ry), f"Used Palette ({len(used)}/{len(pal)})", fill=(195, 202, 220, 255), font=font)
        ry += 16
        sw_size = 16
        per_row = max(1, (right_col_w - 8) // (sw_size + 4))
        for idx_i, c_idx in enumerate(used):
            sx = rx + (idx_i % per_row) * (sw_size + 4)
            sy = ry + (idx_i // per_row) * (sw_size + 4)
            rgb = pal.rgb_at(c_idx)
            draw.rectangle([sx, sy, sx + sw_size, sy + sw_size], fill=(*rgb, 255), outline=(220, 224, 235, 255))

    # --- FOOTER QA METRICS ---
    fy = total_h - footer_h
    draw.rectangle([0, fy, total_w, total_h], fill=(16, 18, 26, 255))
    cap_metric = f"/{report['max_colors']}cap" if report.get("max_colors") is not None else ""
    summary = (
        f"Colors: {report['unique_colors_used']}/{report['palette_size']}{cap_metric}  |  "
        f"Orphans: {report['orphan_pixels']}  |  "
        f"Doubles: {report.get('outline_doubles', 0)}  |  "
        f"Clipped: {report['clipped_pixels']}  |  "
        f"Pivot: {project.pivot}"
    )
    draw.text((12, fy + 8), summary, fill=(190, 200, 220, 255), font=font)

    msg = "OK - All programmatic checks passed."
    msg_col = (102, 217, 138, 255)
    if report["errors"]:
        msg = "ERRORS: " + "; ".join(report["errors"])
        msg_col = (245, 96, 110, 255)
    elif report["warnings"]:
        msg = "WARNINGS: " + "; ".join(report["warnings"])
        msg_col = (245, 200, 96, 255)
    draw.text((12, fy + 28), msg[:140], fill=msg_col, font=font)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def render_contact_sheet(assets_root: str | Path, scale: int = 4) -> Path | None:
    """Render all cataloged assets side-by-side into _inspect/project_contact_sheet.png."""
    root = Path(assets_root)
    catalog_path = root / "catalog.json"
    if not catalog_path.exists():
        return None
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assets = catalog.get("assets", [])
    if not assets:
        return None

    font = ImageFont.load_default()
    thumbs: list[tuple[str, Image.Image]] = []
    for entry in assets:
        png_rel = entry.get("exports", {}).get("png")
        if not png_rel:
            continue
        png_path = root / png_rel
        if not png_path.exists():
            continue
        img = Image.open(png_path).convert("RGBA")
        w, h = entry.get("dimensions", [img.width, img.height])
        # Crop frame 0 if sprite sheet
        frame0 = img.crop((0, 0, min(w, img.width), min(h, img.height)))
        zoomed = frame0.resize((frame0.width * scale, frame0.height * scale), Image.NEAREST)
        label = f"{entry['name']} ({w}x{h})"
        thumbs.append((label, zoomed))

    if not thumbs:
        return None

    cols = min(4, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    cell_w = max(140, max(im.width for _, im in thumbs) + 24)
    cell_h = max(110, max(im.height for _, im in thumbs) + 38)
    pad = 14
    header_h = 32

    sheet_w = pad * (cols + 1) + cols * cell_w
    sheet_h = header_h + pad * (rows + 1) + rows * cell_h
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (24, 26, 36, 255))
    draw = ImageDraw.Draw(sheet)
    draw.rectangle([0, 0, sheet_w, header_h], fill=(16, 18, 26, 255))
    draw.text(
        (12, 10),
        f"Project Contact Sheet ({len(thumbs)} assets @ {scale}x)",
        fill=(210, 220, 240, 255),
        font=font,
    )

    for idx, (label, im) in enumerate(thumbs):
        r = idx // cols
        c = idx % cols
        x0 = pad + c * (cell_w + pad)
        y0 = header_h + pad + r * (cell_h + pad)
        draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], fill=(34, 37, 50, 255), outline=(76, 84, 108, 255))
        ix = x0 + (cell_w - im.width) // 2
        iy = y0 + (cell_h - 20 - im.height) // 2
        sheet.alpha_composite(im, (ix, iy))
        max_chars = max(24, (cell_w - 16) // 6)
        draw.text((x0 + 8, y0 + cell_h - 18), label[:max_chars], fill=(185, 195, 218, 255), font=font)

    out_path = root / "_inspect" / "project_contact_sheet.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path
