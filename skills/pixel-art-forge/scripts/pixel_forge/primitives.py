"""Pixel-perfect drawing primitives with automatic L-double cleanup and symmetry helpers."""

from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING, Mapping, Sequence

from .canvas import TRANSPARENT, IndexedLayer

if TYPE_CHECKING:
    from .spec import StyleSpec

Point = tuple[int, int]


def remove_doubles(points: Sequence[Point]) -> list[Point]:
    """Strip L-shaped extra corner pixels ('doubles') from a 1px path."""
    if len(points) <= 2:
        return list(points)
    dedup: list[Point] = [points[0]]
    for pt in points[1:]:
        if pt != dedup[-1]:
            dedup.append(pt)
    if len(dedup) <= 2:
        return dedup

    cleaned: list[Point] = [dedup[0]]
    i = 1
    while i < len(dedup) - 1:
        prev_pt = cleaned[-1]
        curr_pt = dedup[i]
        next_pt = dedup[i + 1]
        # If prev -> curr -> next forms an orthogonal L-corner whose diagonal shortcut is 1 step
        is_prev_ortho = abs(curr_pt[0] - prev_pt[0]) + abs(curr_pt[1] - prev_pt[1]) == 1
        is_next_ortho = abs(next_pt[0] - curr_pt[0]) + abs(next_pt[1] - curr_pt[1]) == 1
        is_diag = abs(next_pt[0] - prev_pt[0]) == 1 and abs(next_pt[1] - prev_pt[1]) == 1
        if is_prev_ortho and is_next_ortho and is_diag:
            # Skip curr_pt to eliminate the L-double
            i += 1
            continue
        cleaned.append(curr_pt)
        i += 1
    cleaned.append(dedup[-1])
    return cleaned


def bresenham_points(x0: int, y0: int, x1: int, y1: int) -> list[Point]:
    """Generate integer pixel points along a Bresenham line."""
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    pts: list[Point] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


def line(
    layer: IndexedLayer,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: int,
    material: str | None = None,
    clean_doubles: bool = True,
) -> list[Point]:
    """Draw a pixel-perfect 1px line."""
    pts = bresenham_points(x0, y0, x1, y1)
    if clean_doubles:
        pts = remove_doubles(pts)
    for x, y in pts:
        layer.set_px(x, y, color, material)
    return pts


def rect(
    layer: IndexedLayer,
    x: int,
    y: int,
    w: int,
    h: int,
    color: int,
    fill: bool = True,
    material: str | None = None,
) -> None:
    """Draw a filled or outlined integer rectangle."""
    if w <= 0 or h <= 0:
        return
    if fill:
        for py in range(y, y + h):
            for px in range(x, x + w):
                layer.set_px(px, py, color, material)
    else:
        for px in range(x, x + w):
            layer.set_px(px, y, color, material)
            layer.set_px(px, y + h - 1, color, material)
        for py in range(y, y + h):
            layer.set_px(x, py, color, material)
            layer.set_px(x + w - 1, py, color, material)


def rounded_rect(
    layer: IndexedLayer,
    x: int,
    y: int,
    w: int,
    h: int,
    radius: int,
    color: int,
    fill: bool = True,
    material: str | None = None,
) -> None:
    """Draw a crisp pixel-art rounded rectangle (chamfered corners at small radii)."""
    if w <= 0 or h <= 0:
        return
    r = max(0, min(int(radius), w // 2, h // 2))
    x1 = x + w - 1
    y1 = y + h - 1

    def _inside(px: int, py: int) -> bool:
        if r == 0:
            return True
        # Check distance to each corner's inner center
        cx = x + r if px < x + r else (x1 - r if px > x1 - r else px)
        cy = y + r if py < y + r else (y1 - r if py > y1 - r else py)
        if cx == px and cy == py:
            return True
        dx = abs(px - cx)
        dy = abs(py - cy)
        # Pixel-art friendly threshold: r=1 cuts exact 1px corner
        return (dx * dx + dy * dy) <= (r * r + r * 0.25)

    for py in range(y, y + h):
        for px in range(x, x + w):
            if not _inside(px, py):
                continue
            if fill:
                layer.set_px(px, py, color, material)
            else:
                # Outline pixel if any 4-neighbor is outside the rounded rect
                on_edge = (
                    px == x
                    or px == x1
                    or py == y
                    or py == y1
                    or not _inside(px - 1, py)
                    or not _inside(px + 1, py)
                    or not _inside(px, py - 1)
                    or not _inside(px, py + 1)
                )
                if on_edge:
                    layer.set_px(px, py, color, material)


def circle(
    layer: IndexedLayer,
    cx: float,
    cy: float,
    r: float,
    color: int,
    fill: bool = True,
    material: str | None = None,
) -> None:
    """Draw a symmetric pixel-perfect circle."""
    if r <= 0:
        layer.set_px(round(cx), round(cy), color, material)
        return
    x0 = math.floor(cx - r)
    x1 = math.ceil(cx + r)
    y0 = math.floor(cy - r)
    y1 = math.ceil(cy + r)
    r2 = (r + 0.25) ** 2

    def _in(px: int, py: int) -> bool:
        return (px - cx) ** 2 + (py - cy) ** 2 <= r2

    for py in range(y0, y1 + 1):
        for px in range(x0, x1 + 1):
            if not _in(px, py):
                continue
            if fill:
                layer.set_px(px, py, color, material)
            else:
                if not (_in(px - 1, py) and _in(px + 1, py) and _in(px, py - 1) and _in(px, py + 1)):
                    layer.set_px(px, py, color, material)


def ellipse(
    layer: IndexedLayer,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: int,
    fill: bool = True,
    material: str | None = None,
) -> None:
    """Draw a symmetric pixel-perfect ellipse bounded by inclusive [x0..x1, y0..y1]."""
    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    rx = max(0.5, (x1 - x0) / 2.0 + 0.35)
    ry = max(0.5, (y1 - y0) / 2.0 + 0.35)

    def _in(px: int, py: int) -> bool:
        return ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 <= 1.0

    for py in range(y0, y1 + 1):
        for px in range(x0, x1 + 1):
            if not _in(px, py):
                continue
            if fill:
                layer.set_px(px, py, color, material)
            else:
                if not (_in(px - 1, py) and _in(px + 1, py) and _in(px, py - 1) and _in(px, py + 1)):
                    layer.set_px(px, py, color, material)


def polygon(
    layer: IndexedLayer,
    points: Sequence[Point],
    color: int,
    fill: bool = True,
    material: str | None = None,
) -> None:
    """Draw a filled or outlined polygon using scanline rasterization."""
    if len(points) < 2:
        return
    if not fill or len(points) == 2:
        for i in range(len(points)):
            p0 = points[i]
            p1 = points[(i + 1) % len(points)]
            line(layer, p0[0], p0[1], p1[0], p1[1], color, material=material)
        return

    ys = [p[1] for p in points]
    min_y, max_y = min(ys), max(ys)
    n = len(points)

    # Scanline fill using half-pixel center sampling
    for py in range(min_y, max_y + 1):
        scan_y = py + 0.5
        xs: list[float] = []
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            if y1 == y2:
                continue
            if (y1 <= scan_y < y2) or (y2 <= scan_y < y1):
                ix = x1 + (scan_y - y1) * (x2 - x1) / (y2 - y1)
                xs.append(ix)
        xs.sort()
        for j in range(0, len(xs) - 1, 2):
            sx = math.ceil(xs[j] - 0.5)
            ex = math.floor(xs[j + 1] - 0.5)
            for px in range(sx, ex + 1):
                layer.set_px(px, py, color, material)

    # Also rasterize boundary edges cleanly so sharp tips (e.g. sword tips) stay crisp
    for i in range(n):
        p0 = points[i]
        p1 = points[(i + 1) % n]
        line(layer, p0[0], p0[1], p1[0], p1[1], color, material=material, clean_doubles=False)


def bezier(
    layer: IndexedLayer,
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    color: int,
    material: str | None = None,
    clean_doubles: bool = True,
) -> list[Point]:
    """Draw a clean 1px quadratic Bezier curve with optional double removal."""
    est_len = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) + math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    steps = max(8, int(est_len * 4))
    raw: list[Point] = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        x = round(mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0])
        y = round(mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1])
        if not raw or raw[-1] != (x, y):
            # Connect gaps with Bresenham if jump > 1
            if raw and (abs(x - raw[-1][0]) > 1 or abs(y - raw[-1][1]) > 1):
                bridge = bresenham_points(raw[-1][0], raw[-1][1], x, y)
                raw.extend(bridge[1:])
            else:
                raw.append((x, y))
    pts = remove_doubles(raw) if clean_doubles else raw
    for x, y in pts:
        layer.set_px(x, y, color, material)
    return pts


def capsule(
    layer: IndexedLayer,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    radius: float,
    color: int,
    material: str | None = None,
) -> None:
    """Draw a filled capsule/pill segment (ideal for limbs, handles, staffs)."""
    min_x = math.floor(min(x0, x1) - radius)
    max_x = math.ceil(max(x0, x1) + radius)
    min_y = math.floor(min(y0, y1) - radius)
    max_y = math.ceil(max(y0, y1) + radius)
    dx = x1 - x0
    dy = y1 - y0
    len2 = dx * dx + dy * dy
    r2 = (radius + 0.25) ** 2

    for py in range(min_y, max_y + 1):
        for px in range(min_x, max_x + 1):
            if len2 < 1e-6:
                dist2 = (px - x0) ** 2 + (py - y0) ** 2
            else:
                t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / len2))
                cx = x0 + t * dx
                cy = y0 + t * dy
                dist2 = (px - cx) ** 2 + (py - cy) ** 2
            if dist2 <= r2:
                layer.set_px(px, py, color, material)


def tapered_stroke(
    layer: IndexedLayer,
    points: Sequence[tuple[float, float]],
    r_start: float,
    r_end: float,
    color: int,
    material: str | None = None,
) -> None:
    """Draw a smoothly tapering stroke along control points (blades, horns, tails, flames)."""
    if len(points) < 2:
        if points:
            circle(layer, points[0][0], points[0][1], r_start, color, fill=True, material=material)
        return

    # Measure cumulative arc length
    seg_lens = [
        math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
        for i in range(len(points) - 1)
    ]
    total_len = sum(seg_lens)
    if total_len < 1e-6:
        circle(layer, points[0][0], points[0][1], r_start, color, fill=True, material=material)
        return

    acc = 0.0
    for i in range(len(points) - 1):
        p0, p1 = points[i], points[i + 1]
        slen = seg_lens[i]
        steps = max(2, int(slen * 3))
        for s in range(steps + 1):
            local_t = s / steps
            global_t = (acc + slen * local_t) / total_len
            cx = p0[0] + (p1[0] - p0[0]) * local_t
            cy = p0[1] + (p1[1] - p0[1]) * local_t
            r = r_start + (r_end - r_start) * global_t
            circle(layer, cx, cy, r, color, fill=True, material=material)
        acc += slen


def flood_fill(
    layer: IndexedLayer,
    x: int,
    y: int,
    color: int,
    material: str | None = None,
) -> int:
    """4-connected integer flood fill starting at (x, y). Returns filled pixel count."""
    target = layer.get_px(x, y)
    if target == color:
        return 0
    if not layer.toroidal and not (0 <= x < layer.width and 0 <= y < layer.height):
        return 0

    q: deque[Point] = deque([(x % layer.width if layer.toroidal else x, y % layer.height if layer.toroidal else y)])
    visited: set[Point] = set()
    filled = 0
    while q:
        cx, cy = q.popleft()
        if (cx, cy) in visited:
            continue
        if layer.get_px(cx, cy) != target:
            continue
        visited.add((cx, cy))
        layer.set_px(cx, cy, color, material)
        filled += 1
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if layer.toroidal:
                nx %= layer.width
                ny %= layer.height
                if (nx, ny) not in visited:
                    q.append((nx, ny))
            elif 0 <= nx < layer.width and 0 <= ny < layer.height and (nx, ny) not in visited:
                q.append((nx, ny))
    return filled


def mirror_x(layer: IndexedLayer, axis_x: float | None = None) -> None:
    """Mirror pixels from the left side of axis_x onto the right side."""
    axis = (layer.width - 1) / 2.0 if axis_x is None else float(axis_x)
    for y in range(layer.height):
        for x in range(layer.width):
            if x <= axis:
                c = layer.grid[y][x]
                if c != TRANSPARENT:
                    mx = round(2 * axis - x)
                    layer.set_px(mx, y, c, layer.material_map[y][x])


def stamp_pattern(
    layer: IndexedLayer,
    ox: int,
    oy: int,
    pattern: Sequence[str],
    char_map: Mapping[str, int | tuple[int, str]],
) -> None:
    """Stamp a small localized ASCII pixel patch onto a layer.

    '.' and ' ' are skipped (transparent). char_map maps characters to either
    a palette index `int` or `(palette_index, material_name)`.
    """
    for dy, row in enumerate(pattern):
        for dx, ch in enumerate(row):
            if ch in (".", " "):
                continue
            if ch not in char_map:
                raise KeyError(f"Character {ch!r} in stamp_pattern not found in char_map.")
            val = char_map[ch]
            if isinstance(val, tuple):
                c_idx, mat = val
                layer.set_px(ox + dx, oy + dy, c_idx, mat)
            else:
                layer.set_px(ox + dx, oy + dy, val, None)


LegendEntry = str | int | tuple[str, int] | tuple[int, str | None] | None


def _resolve_legend_entry(spec: "StyleSpec", entry: LegendEntry) -> tuple[int, str | None]:
    """Resolve a human-friendly legend spec ('steel:3', 'gold', ('wood', 2), 'erase', -1) to (color_idx, mat)."""
    if entry is None or entry == TRANSPARENT:
        return (TRANSPARENT, None)
    if isinstance(entry, int):
        return (entry, None)
    if isinstance(entry, str):
        s = entry.strip()
        if s.lower() in ("erase", "transparent", "clear", "none"):
            return (TRANSPARENT, None)
        if ":" in s:
            mat_raw, shade_raw = s.split(":", 1)
            mat = mat_raw.strip()
            shade = int(shade_raw.strip())
            return (spec.color(mat, shade), mat)
        mat = s
        ramp = spec.ramp(mat)
        return (ramp[len(ramp) // 2], mat)
    if isinstance(entry, tuple) and len(entry) == 2:
        first, second = entry
        if isinstance(first, str) and isinstance(second, int):
            return (spec.color(first, second), first)
        if isinstance(first, int) and (second is None or isinstance(second, str)):
            return (first, second)
    raise ValueError(f"Unsupported paint_ascii_canvas legend entry: {entry!r}")


def paint_ascii_canvas(
    layer: IndexedLayer,
    spec: "StyleSpec",
    grid: str | Sequence[str],
    legend: Mapping[str, LegendEntry],
    ox: int = 0,
    oy: int = 0,
    mirror: bool = False,
    mirror_axis_x: float | None = None,
) -> None:
    """Paint or carve complex organic silhouettes using a semantic ASCII matrix.

    Legend values support concise material notation:
      - `'steel'` -> middle shade of `steel` ramp with `material='steel'` (ready for `auto_shade_layer`)
      - `'gold:3'` or `('gold', -1)` -> exact shade index of material ramp
      - `'erase'` / `TRANSPARENT` / `None` -> carves pixel back to transparent
      - `'.'` and `' '` are skipped (leave underlying pixels untouched)
    When `mirror=True`, left-half strokes are mirrored cleanly across `mirror_axis_x` (default: canvas center).
    """
    if isinstance(grid, str):
        lines = grid.strip("\n").splitlines()
    else:
        lines = list(grid)

    resolved: dict[str, tuple[int, str | None]] = {
        ch: _resolve_legend_entry(spec, val) for ch, val in legend.items()
    }
    axis = (layer.width - 1) / 2.0 if mirror_axis_x is None else float(mirror_axis_x)

    for dy, row in enumerate(lines):
        py = oy + dy
        for dx, ch in enumerate(row):
            if ch in (".", " "):
                continue
            if ch not in resolved:
                raise KeyError(f"Character {ch!r} in paint_ascii_canvas not found in legend.")
            c_idx, mat = resolved[ch]
            px = ox + dx
            layer.set_px(px, py, c_idx, mat)
            if mirror:
                mx = round(2.0 * axis - px)
                layer.set_px(mx, py, c_idx, mat)


def erase_rect(layer: IndexedLayer, x: int, y: int, w: int, h: int) -> None:
    """Boolean cutout: carve a rectangular region back to transparent."""
    rect(layer, x, y, w, h, TRANSPARENT, fill=True, material=None)


def erase_circle(layer: IndexedLayer, cx: float, cy: float, r: float) -> None:
    """Boolean cutout: carve a circular region back to transparent."""
    circle(layer, cx, cy, r, TRANSPARENT, fill=True, material=None)


def erase_polygon(layer: IndexedLayer, points: Sequence[Point]) -> None:
    """Boolean cutout: carve a polygonal notch/slit/damage cutout back to transparent."""
    polygon(layer, points, TRANSPARENT, fill=True, material=None)


def cutout_mask(target_layer: IndexedLayer, mask_layer: IndexedLayer, ox: int = 0, oy: int = 0) -> int:
    """Boolean difference (`target = target - mask`): erase pixels wherever `mask_layer` is opaque."""
    erased = 0
    for y in range(mask_layer.height):
        for x in range(mask_layer.width):
            if mask_layer.grid[y][x] != TRANSPARENT:
                tx, ty = x + ox, y + oy
                if target_layer.get_px(tx, ty) != TRANSPARENT:
                    target_layer.set_px(tx, ty, TRANSPARENT, None)
                    erased += 1
    return erased
