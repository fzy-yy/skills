"""Pixel-level cleanup, orphan noise detection, double-corner check, and tile seam checks."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .canvas import TRANSPARENT, IndexedLayer
from .palette import Palette, oklab_distance


def find_orphan_pixels(
    layer: IndexedLayer,
    exclude_indices: set[int] | None = None,
    ignore_material_boundaries: bool = False,
) -> list[tuple[int, int]]:
    """Find isolated single-pixel color noise (all 8 neighbors different color, interior only)."""
    orphans: list[tuple[int, int]] = []
    w, h = layer.width, layer.height
    for y in range(h):
        for x in range(w):
            c = layer.grid[y][x]
            if c == TRANSPARENT:
                continue
            if exclude_indices and c in exclude_indices:
                continue
            n4 = [
                layer.get_px(x - 1, y),
                layer.get_px(x + 1, y),
                layer.get_px(x, y - 1),
                layer.get_px(x, y + 1),
            ]
            # Ignore outer silhouette edge pixels (touching transparent)
            if any(nc == TRANSPARENT for nc in n4):
                continue
            if ignore_material_boundaries:
                mat = layer.material_map[y][x]
                if mat is not None:
                    n4_mats = (
                        layer.get_material(x - 1, y),
                        layer.get_material(x + 1, y),
                        layer.get_material(x, y - 1),
                        layer.get_material(x, y + 1),
                    )
                    if any(nm != mat for nm in n4_mats):
                        continue
            # Also check diagonals — intentional 1px specular dots or eyes are often diagonal-connected;
            # flag only if ALL 8 neighbors differ from c!
            n8 = n4 + [
                layer.get_px(x - 1, y - 1),
                layer.get_px(x + 1, y - 1),
                layer.get_px(x - 1, y + 1),
                layer.get_px(x + 1, y + 1),
            ]
            if all(nc != c for nc in n8):
                orphans.append((x, y))
    return orphans


def find_outline_doubles(
    layer: IndexedLayer,
    solid_layer: IndexedLayer | None = None,
) -> list[tuple[int, int]]:
    """Detect redundant L-shaped 1px double corner pixels on thin outline/line layers.

    A pixel is flagged when it has exactly two orthogonal opaque neighbors forming a 90° L-corner
    and the diagonal pixel inside that corner is transparent. When `solid_layer` is supplied,
    concave notch outline pixels touching two orthogonal solid body pixels are excluded because
    removing them would expose a diagonal gap in a 4-connected outline.
    """
    doubles: list[tuple[int, int]] = []
    w, h = layer.width, layer.height
    has_solid = solid_layer is not None and solid_layer.non_empty_count() > 0
    corner_pairs = (
        ((-1, 0), (0, -1), (-1, -1)),
        ((1, 0), (0, -1), (1, -1)),
        ((-1, 0), (0, 1), (-1, 1)),
        ((1, 0), (0, 1), (1, 1)),
    )
    for y in range(h):
        for x in range(w):
            if layer.grid[y][x] == TRANSPARENT:
                continue
            if has_solid and solid_layer is not None:
                solid_ortho = sum(
                    1
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
                    if solid_layer.get_px(x + dx, y + dy) != TRANSPARENT
                )
                if solid_ortho >= 2:
                    continue
            l_on = layer.get_px(x - 1, y) != TRANSPARENT
            r_on = layer.get_px(x + 1, y) != TRANSPARENT
            u_on = layer.get_px(x, y - 1) != TRANSPARENT
            d_on = layer.get_px(x, y + 1) != TRANSPARENT
            ortho_count = int(l_on) + int(r_on) + int(u_on) + int(d_on)
            if ortho_count != 2:
                continue
            for (ax, ay), (bx, by), (cx, cy) in corner_pairs:
                if (
                    layer.get_px(x + ax, y + ay) != TRANSPARENT
                    and layer.get_px(x + bx, y + by) != TRANSPARENT
                    and layer.get_px(x + cx, y + cy) == TRANSPARENT
                ):
                    doubles.append((x, y))
                    break
    return doubles


def despeckle(
    layer: IndexedLayer,
    preserve_brightest: bool = True,
    brightest_indices: set[int] | None = None,
) -> int:
    """Replace isolated orphan interior noise pixels with their dominant 4-neighbor color."""
    orphans = find_orphan_pixels(layer)
    fixed = 0
    updates: list[tuple[int, int, int, str | None]] = []
    for x, y in orphans:
        c = layer.grid[y][x]
        if preserve_brightest and brightest_indices and c in brightest_indices:
            continue
        n4 = [
            (layer.get_px(x - 1, y), layer.get_material(x - 1, y)),
            (layer.get_px(x + 1, y), layer.get_material(x + 1, y)),
            (layer.get_px(x, y - 1), layer.get_material(x, y - 1)),
            (layer.get_px(x, y + 1), layer.get_material(x, y + 1)),
        ]
        counts = Counter(nc for nc, _ in n4 if nc != TRANSPARENT)
        if not counts:
            continue
        dominant = counts.most_common(1)[0][0]
        dom_mat = next((m for nc, m in n4 if nc == dominant and m is not None), layer.material_map[y][x])
        updates.append((x, y, dominant, dom_mat))
        fixed += 1

    for x, y, new_c, mat in updates:
        layer.set_px(x, y, new_c, mat)
    return fixed


def check_tile_seams(layer: IndexedLayer, palette: Palette) -> dict[str, float | bool]:
    """Evaluate perceptual continuity across left-right and top-bottom tile edges."""
    w, h = layer.width, layer.height
    lr_diffs: list[float] = []
    tb_diffs: list[float] = []

    for y in range(h):
        c_left = layer.grid[y][0]
        c_right = layer.grid[y][w - 1]
        if c_left == TRANSPARENT or c_right == TRANSPARENT:
            lr_diffs.append(0.0 if c_left == c_right else 1.0)
        else:
            lr_diffs.append(oklab_distance(palette.rgb_at(c_left), palette.rgb_at(c_right)))

    for x in range(w):
        c_top = layer.grid[0][x]
        c_bot = layer.grid[h - 1][x]
        if c_top == TRANSPARENT or c_bot == TRANSPARENT:
            tb_diffs.append(0.0 if c_top == c_bot else 1.0)
        else:
            tb_diffs.append(oklab_distance(palette.rgb_at(c_top), palette.rgb_at(c_bot)))

    avg_lr = sum(lr_diffs) / max(1, len(lr_diffs))
    avg_tb = sum(tb_diffs) / max(1, len(tb_diffs))

    # Measure maximum interior column-to-column and row-to-row average contrast so
    # structured repeating patterns (like brick mortar rows) are not false-flagged as seams.
    col_diffs: list[float] = []
    for x in range(w - 1):
        ds = [
            oklab_distance(palette.rgb_at(layer.grid[y][x]), palette.rgb_at(layer.grid[y][x + 1]))
            for y in range(h)
            if layer.grid[y][x] != TRANSPARENT and layer.grid[y][x + 1] != TRANSPARENT
        ]
        if ds:
            col_diffs.append(sum(ds) / len(ds))

    row_diffs: list[float] = []
    for y in range(h - 1):
        ds = [
            oklab_distance(palette.rgb_at(layer.grid[y][x]), palette.rgb_at(layer.grid[y + 1][x]))
            for x in range(w)
            if layer.grid[y][x] != TRANSPARENT and layer.grid[y + 1][x] != TRANSPARENT
        ]
        if ds:
            row_diffs.append(sum(ds) / len(ds))

    max_col_int = max(col_diffs) if col_diffs else 0.0
    max_row_int = max(row_diffs) if row_diffs else 0.0
    lr_thresh = max(0.18, max_col_int * 1.25)
    tb_thresh = max(0.18, max_row_int * 1.25)
    return {
        "avg_lr_diff": round(avg_lr, 4),
        "avg_tb_diff": round(avg_tb, 4),
        "max_interior_col_diff": round(max_col_int, 4),
        "max_interior_row_diff": round(max_row_int, 4),
        "seamless_ok": (avg_lr <= lr_thresh and avg_tb <= tb_thresh),
    }


def check_nine_slice_consistency(
    layer: IndexedLayer,
    margins: tuple[int, int, int, int],
) -> dict[str, Any]:
    """Verify that 9-slice stretchable edge bands stay pixel-identical along their stretch axes."""
    left, top, right, bottom = (int(v) for v in margins)
    w, h = layer.width, layer.height
    x0, x1 = left, w - right
    y0, y1 = top, h - bottom

    mismatch_cols: list[int] = []
    mismatch_rows: list[int] = []

    if x1 - x0 >= 2:
        top_ref = [layer.grid[y][x0] for y in range(0, top)]
        bot_ref = [layer.grid[y][x0] for y in range(h - bottom, h)]
        for x in range(x0 + 1, x1):
            top_col = [layer.grid[y][x] for y in range(0, top)]
            bot_col = [layer.grid[y][x] for y in range(h - bottom, h)]
            if top_col != top_ref or bot_col != bot_ref:
                mismatch_cols.append(x)

    if y1 - y0 >= 2:
        left_ref = [layer.grid[y0][x] for x in range(0, left)]
        right_ref = [layer.grid[y0][x] for x in range(w - right, w)]
        for y in range(y0 + 1, y1):
            left_row = [layer.grid[y][x] for x in range(0, left)]
            right_row = [layer.grid[y][x] for x in range(w - right, w)]
            if left_row != left_ref or right_row != right_ref:
                mismatch_rows.append(y)

    return {
        "consistent": not mismatch_cols and not mismatch_rows,
        "mismatch_columns": mismatch_cols,
        "mismatch_rows": mismatch_rows,
    }
