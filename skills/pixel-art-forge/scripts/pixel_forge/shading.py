"""Directional 2.5D pixel-art shading (anti-pillow-shading), layer AO, Bayer dithering, and Sel-Out."""

from __future__ import annotations

import heapq
import math
from typing import Sequence

from .canvas import TRANSPARENT, IndexedLayer
from .palette import luminance
from .spec import VALID_SHADING_PROFILES, StyleSpec

BAYER_2X2 = (
    (0.0 / 4.0, 2.0 / 4.0),
    (3.0 / 4.0, 1.0 / 4.0),
)

BAYER_4X4 = (
    (0.0 / 16.0, 8.0 / 16.0, 2.0 / 16.0, 10.0 / 16.0),
    (12.0 / 16.0, 4.0 / 16.0, 14.0 / 16.0, 6.0 / 16.0),
    (3.0 / 16.0, 11.0 / 16.0, 1.0 / 16.0, 9.0 / 16.0),
    (15.0 / 16.0, 7.0 / 16.0, 13.0 / 16.0, 5.0 / 16.0),
)


def _bayer_threshold(x: int, y: int, dither: str) -> float:
    if dither == "bayer2x2":
        return BAYER_2X2[y % 2][x % 2] - 0.5
    if dither == "bayer4x4":
        return BAYER_4X4[y % 4][x % 4] - 0.5
    return 0.0


def _in_mask(layer: IndexedLayer, x: int, y: int) -> bool:
    return layer.get_px(x, y) != TRANSPARENT


def _compute_distance_field(layer: IndexedLayer) -> list[list[float]]:
    """Compute exact 8-connected Chamfer/Dijkstra interior distance field (supports toroidal & large canvases)."""
    w, h = layer.width, layer.height
    inf = float("inf")
    dist = [[0.0] * w for _ in range(h)]
    heap: list[tuple[float, int, int]] = []
    diag = math.sqrt(2.0)

    for y in range(h):
        for x in range(w):
            if not _in_mask(layer, x, y):
                continue
            # Check immediate boundary exposure (including outside-canvas for non-toroidal)
            ortho_edge = (
                not _in_mask(layer, x - 1, y)
                or not _in_mask(layer, x + 1, y)
                or not _in_mask(layer, x, y - 1)
                or not _in_mask(layer, x, y + 1)
            )
            if ortho_edge:
                dist[y][x] = 1.0
                heapq.heappush(heap, (1.0, x, y))
            else:
                diag_edge = (
                    not _in_mask(layer, x - 1, y - 1)
                    or not _in_mask(layer, x + 1, y - 1)
                    or not _in_mask(layer, x - 1, y + 1)
                    or not _in_mask(layer, x + 1, y + 1)
                )
                if diag_edge:
                    dist[y][x] = diag
                    heapq.heappush(heap, (diag, x, y))
                else:
                    dist[y][x] = inf

    neighbors = (
        (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, diag), (1, -1, diag), (-1, 1, diag), (1, 1, diag),
    )
    while heap:
        d, x, y = heapq.heappop(heap)
        if d > dist[y][x] + 1e-6:
            continue
        for dx, dy, step in neighbors:
            nx, ny = x + dx, y + dy
            if layer.toroidal:
                nx %= w
                ny %= h
            elif not (0 <= nx < w and 0 <= ny < h):
                continue
            if layer.grid[ny][nx] == TRANSPARENT:
                continue
            nd = d + step
            if nd + 1e-6 < dist[ny][nx]:
                dist[ny][nx] = nd
                heapq.heappush(heap, (nd, nx, ny))

    # Replace any remaining inf (e.g. fully opaque toroidal tile) with uniform depth
    for y in range(h):
        for x in range(w):
            if math.isinf(dist[y][x]):
                dist[y][x] = float(max(w, h))
    return dist


def _evaluate_material_profile(
    profile: str,
    local_dot: float,
    global_light: float,
    dist_px: float,
    max_dist: float,
    rim_light: bool,
) -> float:
    """Compute normalized [0..1] shade value according to material reflectance physics."""
    if profile == "metallic":
        # High-contrast S-curve: crisp specular highlight band on lit side + core shadow + subtle bounce rim
        raw = 0.50 + 0.34 * local_dot + 0.38 * global_light
        # Steep contrast curve around 0.52 creates distinct metallic specular vs shadow planes
        centered = raw - 0.52
        val = 0.50 + math.copysign(min(0.50, abs(centered) ** 0.72 * 0.68), centered)
        if rim_light and dist_px <= 1.1 and local_dot > 0.30:
            val += 0.26
        elif dist_px <= 1.1 and local_dot < -0.45 and max_dist >= 3.0:
            # Classic pixel-art metallic bounce light on outer shadow edge (prevents banding against outline)
            val = max(val, 0.30)
        elif dist_px <= 2.2 and local_dot < -0.25:
            val -= 0.16
        return val

    if profile == "gem":
        # Translucent crystal/potion: dark upper-left refractive facet + sharp glint + warm bottom-right subsurface glow
        depth_norm = min(1.0, dist_px / max(1.5, max_dist))
        # Strong upper-left entry glint, deep interior core, luminous opposite-side transmission
        if local_dot > 0.45 and global_light > 0.12:
            val = 0.88 + 0.12 * local_dot
        elif local_dot < -0.20 and dist_px <= 2.2 and max_dist >= 2.2:
            # Subsurface transmitted glow along opposite lower-right rim
            val = 0.72
        else:
            val = 0.32 + 0.24 * global_light + 0.18 * (1.0 - depth_norm)
        return val

    if profile == "emissive":
        # Hot incandescent core (brightest inside) cooling toward outer silhouette
        depth_norm = min(1.0, dist_px / max(1.5, max_dist))
        return 0.24 + 0.72 * depth_norm + 0.10 * global_light

    # Default 'matte' (cloth, wood, leather, stone, skin, grass): clean clustered diffuse ramps
    val = 0.52 + 0.30 * local_dot + 0.32 * global_light
    if rim_light and dist_px <= 1.1 and local_dot > 0.35:
        val += 0.22
    if dist_px <= 1.1 and local_dot < -0.35:
        val -= 0.18
    return val


def auto_shade_layer(
    layer: IndexedLayer,
    spec: StyleSpec,
    material: str | None = None,
    dither: str | None = None,
    rim_light: bool = True,
    preserve_brightest: bool = False,
    profile: str | None = None,
) -> None:
    """Apply directional pixel-art shading to opaque pixels without pillow shading.

    Uses a full 2D distance-transform surface-normal gradient combined with global object-space
    light projection along `spec.light_dir` and material-aware reflectance (`profile='auto'|'matte'|'metallic'|'gem'|'emissive'`).
    """
    if profile is not None and profile != "auto" and profile not in VALID_SHADING_PROFILES:
        raise ValueError(f"Invalid shading profile {profile!r}; expected 'auto' or one of {VALID_SHADING_PROFILES}.")

    bbox = layer.bbox()
    if bbox is None:
        return
    min_x, min_y, max_x, max_y = bbox
    span_x = max(1, max_x - min_x)
    span_y = max(1, max_y - min_y)
    lx, ly = spec.light_dir
    dither_mode = spec.dither if dither is None else dither

    w, h = layer.width, layer.height
    dist = _compute_distance_field(layer)
    max_dist = max((dist[y][x] for y in range(h) for x in range(w) if layer.grid[y][x] != TRANSPARENT), default=1.0)

    def _dist_at(px: int, py: int) -> float:
        if layer.toroidal:
            return dist[py % h][px % w]
        if 0 <= px < w and 0 <= py < h:
            return dist[py][px]
        return 0.0

    # Compute directional normal from full distance gradient + overall light projection
    updates: list[tuple[int, int, int, str]] = []
    for y in range(h):
        for x in range(w):
            c = layer.grid[y][x]
            if c == TRANSPARENT:
                continue
            mat = layer.material_map[y][x] or material
            if not mat or mat not in spec.materials:
                continue
            ramp = spec.materials[mat]
            if len(ramp) <= 1:
                continue
            if preserve_brightest and c == ramp[-1]:
                continue

            eff_profile = spec.material_profile(mat) if (profile is None or profile == "auto") else profile

            # Local outward normal approximation (handles canvas edges & toroidal wrap cleanly)
            gx = _dist_at(x + 1, y) - _dist_at(x - 1, y)
            gy = _dist_at(x, y + 1) - _dist_at(x, y - 1)
            nx, ny = -gx, -gy
            nmag = math.hypot(nx, ny)
            if nmag > 1e-4:
                nx /= nmag
                ny /= nmag
            else:
                nx, ny = 0.0, 0.0

            local_dot = nx * lx + ny * ly  # [-1, +1]
            px_norm = ((x - min_x) / span_x) * 2.0 - 1.0
            py_norm = ((y - min_y) / span_y) * 2.0 - 1.0
            global_light = -(px_norm * lx + py_norm * ly) * 0.55

            val = _evaluate_material_profile(
                profile=eff_profile,
                local_dot=local_dot,
                global_light=global_light,
                dist_px=dist[y][x],
                max_dist=max_dist,
                rim_light=rim_light,
            )

            if dither_mode in ("bayer2x2", "bayer4x4"):
                val += _bayer_threshold(x, y, dither_mode) * (0.65 / max(1, len(ramp) - 1))

            val = max(0.0, min(1.0, val))
            # Reserve darkest shade mostly for AO/Sel-Out when len>=4 (except emissive outer rim)
            low_idx = 0 if (eff_profile == "emissive" or len(ramp) < 4) else 1
            span = (len(ramp) - 1) - low_idx
            shade_idx = low_idx + round(val * span)
            shade_idx = max(0, min(len(ramp) - 1, shade_idx))
            updates.append((x, y, ramp[shade_idx], mat))

    for x, y, new_c, mat in updates:
        layer.set_px(x, y, new_c, mat)


def apply_layer_ao(
    target_layer: IndexedLayer,
    occluder_layer: IndexedLayer,
    spec: StyleSpec,
    step: int = 1,
    offset: tuple[int, int] | None = None,
) -> None:
    """Cast 1px contact shadow (AO) from occluder_layer onto target_layer along -light_dir."""
    if offset is None:
        lx, ly = spec.light_dir
        dx = -1 if lx > 0.25 else (1 if lx < -0.25 else 0)
        dy = -1 if ly > 0.25 else (1 if ly < -0.25 else 0)
        if dx == 0 and dy == 0:
            dy = 1
    else:
        dx, dy = int(offset[0]), int(offset[1])

    probes: list[tuple[int, int]] = [(dx, dy)]
    if dx != 0 and dy != 0:
        probes.append((0, dy))

    # Collect shadow mask: pixels immediately behind occluder in shadow direction
    w, h = target_layer.width, target_layer.height
    for y in range(h):
        for x in range(w):
            c = target_layer.grid[y][x]
            if c == TRANSPARENT:
                continue
            if occluder_layer.get_px(x, y) != TRANSPARENT:
                continue
            # Check if occluder sits upstream toward the light
            if any(occluder_layer.get_px(x - pdx, y - pdy) != TRANSPARENT for pdx, pdy in probes):
                mat = target_layer.material_map[y][x]
                if mat and mat in spec.materials:
                    ramp = spec.materials[mat]
                    if c in ramp:
                        idx = ramp.index(c)
                    else:
                        c_lum = luminance(spec.palette.rgb_at(c))
                        idx = min(
                            range(len(ramp)),
                            key=lambda ri: abs(luminance(spec.palette.rgb_at(ramp[ri])) - c_lum),
                        )
                    new_idx = max(0, idx - step)
                    target_layer.set_px(x, y, ramp[new_idx], mat)


def apply_outline(
    target_layer: IndexedLayer,
    source_layer: IndexedLayer,
    spec: StyleSpec,
    mode: str | None = None,
    corners: str | None = None,
    lit_boost: bool | None = None,
) -> None:
    """Generate a clean 1px pixel-art outline around source_layer into target_layer.

    Modes:
      - 'sel_out': Selective Outlining using the darkest shade of adjacent pixel's material ramp
                   (optionally boosted +1 shade on strongly lit-facing outer pixels).
      - 'black' / 'colored': uniform outline using spec.outline['color_index'].
      - 'none': no-op.
    """
    out_mode = mode if mode is not None else spec.outline.get("mode", "sel_out")
    if out_mode == "none":
        return

    out_corners = corners if corners is not None else spec.outline.get("corners", "round")
    use_lit_boost = lit_boost if lit_boost is not None else bool(spec.outline.get("lit_boost", True))
    base_outline_idx = int(spec.outline.get("color_index", spec.palette.darkest_index()))

    neighbors_4 = ((-1, 0), (1, 0), (0, -1), (0, 1))
    neighbors_8 = neighbors_4 + ((-1, -1), (1, -1), (-1, 1), (1, 1))
    offsets = neighbors_4 if out_corners == "round" else neighbors_8
    lx, ly = spec.light_dir

    w, h = source_layer.width, source_layer.height
    to_draw: list[tuple[int, int, int]] = []

    for y in range(h):
        for x in range(w):
            if source_layer.get_px(x, y) != TRANSPARENT:
                continue
            adj_mats: list[str] = []
            adj_dirs: list[tuple[int, int]] = []
            hit = False
            for dx, dy in offsets:
                if source_layer.get_px(x + dx, y + dy) != TRANSPARENT:
                    hit = True
                    m = source_layer.get_material(x + dx, y + dy)
                    if m:
                        adj_mats.append(m)
                    # Outward normal points from filled neighbor toward (x, y)
                    adj_dirs.append((-dx, -dy))
            if not hit:
                continue

            if out_mode == "sel_out" and adj_mats:
                # Pick dominant adjacent material
                mat = max(set(adj_mats), key=adj_mats.count)
                ramp = spec.materials.get(mat)
                if ramp:
                    # Check if this outline pixel faces the light source
                    nx = sum(d[0] for d in adj_dirs)
                    ny = sum(d[1] for d in adj_dirs)
                    nmag = math.hypot(nx, ny)
                    dot = ((nx / nmag) * lx + (ny / nmag) * ly) if nmag > 1e-4 else 0.0
                    if use_lit_boost and dot > 0.55 and len(ramp) >= 4:
                        col = ramp[1]
                    else:
                        col = ramp[0]
                else:
                    col = base_outline_idx
            else:
                col = base_outline_idx
            to_draw.append((x, y, col))

    for x, y, col in to_draw:
        target_layer.set_px(x, y, col, material=None)


def add_specular(
    layer: IndexedLayer,
    x: int,
    y: int,
    spec: StyleSpec,
    material: str | None = None,
) -> None:
    """Place a crisp specular highlight pixel using the brightest shade of the ramp."""
    mat = material or layer.get_material(x, y)
    if mat and mat in spec.materials:
        col = spec.materials[mat][-1]
        layer.set_px(x, y, col, mat)
    else:
        layer.set_px(x, y, spec.palette.brightest_index(), None)


def dither_gradient_fill(
    layer: IndexedLayer,
    x: int,
    y: int,
    w: int,
    h: int,
    ramp: Sequence[int],
    direction: str = "vertical",
    dither: str = "bayer2x2",
    material: str | None = None,
) -> None:
    """Fill a rectangle with an ordered-dithered pixel-art gradient along a color ramp."""
    if not ramp or w <= 0 or h <= 0:
        return
    n = len(ramp)
    for py in range(y, y + h):
        for px in range(x, x + w):
            if direction == "horizontal":
                t = (px - x) / max(1, w - 1)
            elif direction == "diagonal":
                t = ((px - x) / max(1, w - 1) + (py - y) / max(1, h - 1)) * 0.5
            else:
                t = (py - y) / max(1, h - 1)
            val = t * (n - 1) + _bayer_threshold(px, py, dither) * 0.85
            idx = max(0, min(n - 1, round(val)))
            layer.set_px(px, py, ramp[idx], material)


def shaded_sphere(
    layer: IndexedLayer,
    cx: float,
    cy: float,
    r: float,
    spec: StyleSpec,
    material: str,
    dither: str | None = None,
    specular: bool = True,
) -> None:
    """Draw a 3D Lambert + specular shaded pixel-art sphere strictly aligned with `spec.light_dir`."""
    ramp = spec.ramp(material)
    if r <= 0:
        layer.set_px(round(cx), round(cy), ramp[-1], material)
        return
    dither_mode = spec.dither if dither is None else dither
    lx, ly = spec.light_dir
    lz = 0.75
    lmag = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / lmag, ly / lmag, lz / lmag

    # Halfway vector for Blinn-Phong specular glint (view vector = (0, 0, 1))
    hx, hy, hz = lx, ly, lz + 1.0
    hmag = math.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx / hmag, hy / hmag, hz / hmag

    x0, x1 = math.floor(cx - r), math.ceil(cx + r)
    y0, y1 = math.floor(cy - r), math.ceil(cy + r)
    r_eff = r + 0.25
    low_idx = 1 if len(ramp) >= 4 else 0
    span = max(1, (len(ramp) - 1) - low_idx)

    for py in range(y0, y1 + 1):
        for px in range(x0, x1 + 1):
            u = (px - cx) / r_eff
            v = (py - cy) / r_eff
            d2 = u * u + v * v
            if d2 > 1.0:
                continue
            nz = math.sqrt(max(0.0, 1.0 - d2))
            ndotl = u * lx + v * ly + nz * lz
            # Soft ambient bounce so shadow core keeps rich hue-shifted depth
            val = 0.25 + 0.78 * max(0.0, ndotl)
            if specular and len(ramp) >= 3:
                ndoth = max(0.0, u * hx + v * hy + nz * hz)
                if ndoth > 0.94:
                    layer.set_px(px, py, ramp[-1], material)
                    continue
            if dither_mode in ("bayer2x2", "bayer4x4"):
                val += _bayer_threshold(px, py, dither_mode) * (0.6 / max(1, span))
            val = max(0.0, min(1.0, val))
            if ndotl < -0.25 and len(ramp) >= 4:
                shade_idx = 0
            else:
                shade_idx = low_idx + round(val * span)
            shade_idx = max(0, min(len(ramp) - 1, shade_idx))
            layer.set_px(px, py, ramp[shade_idx], material)


def shaded_cylinder(
    layer: IndexedLayer,
    x: int,
    y: int,
    w: int,
    h: int,
    spec: StyleSpec,
    material: str,
    axis: str = "vertical",
    dither: str | None = None,
    specular: bool = True,
) -> None:
    """Draw a 3D shaded cylindrical rod/pillar/handle honoring `spec.light_dir`."""
    if w <= 0 or h <= 0:
        return
    ramp = spec.ramp(material)
    dither_mode = spec.dither if dither is None else dither
    lx, ly = spec.light_dir
    lz = 0.75
    lmag = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / lmag, ly / lmag, lz / lmag

    hx, hy, hz = lx, ly, lz + 1.0
    hmag = math.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx / hmag, hy / hmag, hz / hmag

    low_idx = 1 if len(ramp) >= 4 else 0
    span = max(1, (len(ramp) - 1) - low_idx)

    for py in range(y, y + h):
        for px in range(x, x + w):
            if axis == "horizontal":
                t = ((py - y) / max(1, h - 1)) * 2.0 - 1.0 if h > 1 else 0.0
                along = ((px - x) / max(1, w - 1)) * 2.0 - 1.0 if w > 1 else 0.0
                nx, ny = 0.0, t * 0.92
                nz = math.sqrt(max(0.0, 1.0 - ny * ny))
                axial_bias = -along * lx * 0.12
            else:
                t = ((px - x) / max(1, w - 1)) * 2.0 - 1.0 if w > 1 else 0.0
                along = ((py - y) / max(1, h - 1)) * 2.0 - 1.0 if h > 1 else 0.0
                nx, ny = t * 0.92, 0.0
                nz = math.sqrt(max(0.0, 1.0 - nx * nx))
                axial_bias = -along * ly * 0.12

            ndotl = nx * lx + ny * ly + nz * lz
            val = 0.22 + 0.76 * max(0.0, ndotl) + axial_bias
            if specular and len(ramp) >= 3:
                ndoth = max(0.0, nx * hx + ny * hy + nz * hz)
                if ndoth > 0.95:
                    layer.set_px(px, py, ramp[-1], material)
                    continue
            if dither_mode in ("bayer2x2", "bayer4x4"):
                val += _bayer_threshold(px, py, dither_mode) * (0.6 / max(1, span))
            val = max(0.0, min(1.0, val))
            shade_idx = low_idx + round(val * span)
            shade_idx = max(0, min(len(ramp) - 1, shade_idx))
            layer.set_px(px, py, ramp[shade_idx], material)


def apply_inner_outline(
    layer: IndexedLayer,
    spec: StyleSpec,
    step: int = 1,
) -> int:
    """Crisp up seams between adjacent distinct materials by darkening the shaded side 1px."""
    lx, ly = spec.light_dir
    w, h = layer.width, layer.height
    updates: list[tuple[int, int, int, str]] = []

    for y in range(h):
        for x in range(w):
            c = layer.grid[y][x]
            mat = layer.material_map[y][x]
            if c == TRANSPARENT or not mat or mat not in spec.materials:
                continue
            ramp = spec.materials[mat]
            if len(ramp) <= 1:
                continue
            # Check if a different material borders this pixel on the light-facing side
            boundary_dirs: list[tuple[int, int]] = []
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nc = layer.get_px(x + dx, y + dy)
                nmat = layer.get_material(x + dx, y + dy)
                if nc != TRANSPARENT and nmat is not None and nmat != mat:
                    boundary_dirs.append((dx, dy))
            if not boundary_dirs:
                continue
            # Darken only the shadow-receiving side of the material seam (prevents thick 2px dark bars)
            bx = sum(d[0] for d in boundary_dirs)
            by = sum(d[1] for d in boundary_dirs)
            if (bx * lx + by * ly) > 0.1:
                if c in ramp:
                    idx = ramp.index(c)
                else:
                    c_lum = luminance(spec.palette.rgb_at(c))
                    idx = min(
                        range(len(ramp)),
                        key=lambda i: abs(luminance(spec.palette.rgb_at(ramp[i])) - c_lum),
                    )
                new_idx = max(0, idx - step)
                if ramp[new_idx] != c:
                    updates.append((x, y, ramp[new_idx], mat))

    for x, y, new_c, mat in updates:
        layer.set_px(x, y, new_c, mat)
    return len(updates)


def apply_pixel_aa(
    layer: IndexedLayer,
    spec: StyleSpec,
    material: str | None = None,
    min_run: int = 2,
) -> int:
    """Apply restrained, strictly in-palette interior Pixel AA on diagonal stair-step corners.

    Never writes into transparent pixels (preserves 1-bit silhouette) and only uses existing
    material ramp shades. Best suited for 48x48+ curves and diagonal blades.
    """
    w, h = layer.width, layer.height
    updates: list[tuple[int, int, int, str]] = []
    min_run = max(2, int(min_run))

    def _run_len(x: int, y: int, dx: int, dy: int, col: int) -> int:
        cnt = 0
        cx, cy = x + dx, y + dy
        while 0 <= cx < w and 0 <= cy < h and layer.grid[cy][cx] == col:
            cnt += 1
            cx += dx
            cy += dy
            if cnt >= min_run:
                break
        return cnt

    for y in range(1, h - 1):
        for x in range(1, w - 1):
            c = layer.grid[y][x]
            if c == TRANSPARENT:
                continue
            mat = layer.material_map[y][x] or material
            if not mat or mat not in spec.materials:
                continue
            ramp = spec.materials[mat]
            if len(ramp) < 3 or c not in ramp:
                continue
            idx = ramp.index(c)
            # Check 4 diagonal step corners where an opaque pixel sits at a stair-step kink
            corners = (
                ((-1, 0), (0, -1), (1, 0), (0, 1)),
                ((1, 0), (0, -1), (-1, 0), (0, 1)),
                ((-1, 0), (0, 1), (1, 0), (0, -1)),
                ((1, 0), (0, 1), (-1, 0), (0, -1)),
            )
            for (ax, ay), (bx, by), (cx_d, cy_d), (dx_d, dy_d) in corners:
                ca = layer.get_px(x + ax, y + ay)
                cb = layer.get_px(x + bx, y + by)
                # Two adjacent sides share another ramp shade (or darker border) while opposite sides run straight
                if ca == cb and ca != c and ca in ramp:
                    ia = ramp.index(ca)
                    if abs(ia - idx) >= 2:
                        if _run_len(x, y, cx_d, cy_d, c) >= min_run or _run_len(x, y, dx_d, dy_d, c) >= min_run:
                            mid_idx = (idx + ia) // 2
                            if ramp[mid_idx] != c:
                                updates.append((x, y, ramp[mid_idx], mat))
                            break

    for x, y, new_c, mat in updates:
        layer.set_px(x, y, new_c, mat)
    return len(updates)
