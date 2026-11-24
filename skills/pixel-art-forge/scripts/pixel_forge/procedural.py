"""Procedural pixel-art tile textures, 16/47-tile Auto-Tile, Isometric 2.5D, and UI widgets."""

from __future__ import annotations

import math
import random
from typing import Any

from .canvas import TRANSPARENT, IndexedLayer, PixelProject
from .primitives import line, rect, rounded_rect
from .shading import apply_outline
from .spec import StyleSpec

# Standard 8-direction bitmask constants (compatible with Godot Blob 3x3 & Unity RuleTile)
BIT_N = 1
BIT_NE = 2
BIT_E = 4
BIT_SE = 8
BIT_S = 16
BIT_SW = 32
BIT_W = 64
BIT_NW = 128


def _canonical_blob_mask(mask: int) -> int:
    """Strip irrelevant corner bits unless both adjacent cardinal neighbors are present."""
    out = mask & (BIT_N | BIT_E | BIT_S | BIT_W)
    if (mask & BIT_N) and (mask & BIT_E) and (mask & BIT_NE):
        out |= BIT_NE
    if (mask & BIT_S) and (mask & BIT_E) and (mask & BIT_SE):
        out |= BIT_SE
    if (mask & BIT_S) and (mask & BIT_W) and (mask & BIT_SW):
        out |= BIT_SW
    if (mask & BIT_N) and (mask & BIT_W) and (mask & BIT_NW):
        out |= BIT_NW
    return out


# Strictly 16 cardinal (4-bit) masks and 47 canonical Blob (8-bit minimal) masks
CARDINAL16_MASKS: tuple[int, ...] = tuple(
    (BIT_N if (i & 1) else 0)
    | (BIT_E if (i & 2) else 0)
    | (BIT_S if (i & 4) else 0)
    | (BIT_W if (i & 8) else 0)
    for i in range(16)
)
BLOB47_MASKS: tuple[int, ...] = tuple(sorted({_canonical_blob_mask(m) for m in range(256)}))


def fill_stone_brick_tile(
    layer: IndexedLayer,
    spec: StyleSpec,
    material: str = "stone",
    rows: int = 4,
    cols: int = 2,
    seed: int = 42,
    weathering: float = 0.25,
) -> None:
    """Fill a toroidal layer with staggered beveled stone masonry bricks."""
    rng = random.Random(seed)
    ramp = spec.ramp(material)
    mortar = ramp[0]
    dark = ramp[min(1, len(ramp) - 1)]
    mid = ramp[min(2, len(ramp) - 1)]
    light = ramp[min(3, len(ramp) - 1)]
    hi = ramp[-1]

    w, h = layer.width, layer.height
    rows = max(1, int(rows))
    cols = max(1, int(cols))
    x_edges = [(c * w) // cols for c in range(cols + 1)]

    # Base fill with mortar
    rect(layer, 0, 0, w, h, mortar, fill=True, material=material)

    for r in range(rows):
        y0 = (r * h) // rows
        y1 = ((r + 1) * h) // rows
        bh = y1 - y0
        x_offset = ((w // cols) // 2) if (r % 2 == 1) else 0

        for c in range(cols):
            bx = (x_edges[c] + x_offset) % w
            bw = x_edges[c + 1] - x_edges[c]
            # Brick interior (leaving 1px mortar on bottom and right)
            inner_h = max(1, bh - 1)
            inner_w = max(1, bw - 1)
            # Slight per-brick value variation
            base_c = mid if rng.random() > 0.3 else dark
            top_c = light if base_c == mid else mid
            bot_c = dark if base_c == mid else mortar

            for dy in range(inner_h):
                for dx in range(inner_w):
                    px = (bx + dx) % w
                    py = (y0 + dy) % h
                    if dy == 0 and dx == 0:
                        col = hi if rng.random() > 0.4 else top_c
                    elif dy == 0 or dx == 0:
                        col = top_c
                    elif dy == inner_h - 1 or dx == inner_w - 1:
                        col = bot_c
                    else:
                        col = base_c
                    layer.set_px(px, py, col, material)

            # Subtle clustered 2px surface pitting (avoids single-pixel orphan noise)
            if rng.random() < weathering * 0.65 and inner_w >= 4 and inner_h >= 3:
                wx = (bx + rng.randint(1, inner_w - 3)) % w
                wy = (y0 + rng.randint(1, inner_h - 2)) % h
                pit_col = dark if base_c == mid else mid
                layer.set_px(wx, wy, pit_col, material)
                layer.set_px((wx + 1) % w, wy, pit_col, material)

            # Occasional crisp 2px stone crack
            if rng.random() < weathering and inner_w >= 4 and inner_h >= 3:
                cx = (bx + rng.randint(1, inner_w - 3)) % w
                cy = (y0 + rng.randint(1, inner_h - 2)) % h
                layer.set_px(cx, cy, mortar, material)
                layer.set_px((cx + 1) % w, cy, mortar, material)


def fill_grass_tile(
    layer: IndexedLayer,
    spec: StyleSpec,
    material: str = "grass",
    seed: int = 42,
    tuft_density: float = 0.22,
) -> None:
    """Fill a toroidal layer with clustered organic grass ground and subtle blade tufts."""
    rng = random.Random(seed)
    ramp = spec.ramp(material)
    dark = ramp[0]
    shadow = ramp[min(1, len(ramp) - 1)]
    mid = ramp[min(2, len(ramp) - 1)]
    light = ramp[-1]

    w, h = layer.width, layer.height
    rect(layer, 0, 0, w, h, mid, fill=True, material=material)

    # Organic low-frequency color clusters (avoid noisy single pixels)
    patches = max(3, (w * h) // 36)
    for _ in range(patches):
        px = rng.randrange(w)
        py = rng.randrange(h)
        pw = rng.randint(2, 4)
        ph = rng.randint(1, 3)
        col = shadow if rng.random() < 0.65 else light
        for dy in range(ph):
            for dx in range(pw):
                if (dx == 0 and dy == 0) or rng.random() > 0.25:
                    layer.set_px((px + dx) % w, (py + dy) % h, col, material)

    # Crisp 2-3px clustered grass blade tufts (connected pairs prevent orphan noise)
    num_tufts = max(2, int((w * h) * tuft_density / 18))
    for _ in range(num_tufts):
        tx = rng.randrange(w)
        ty = rng.randrange(h)
        # Connected 2px shadow root + 2px lit blade tips
        layer.set_px(tx, ty, shadow, material)
        layer.set_px((tx + 1) % w, ty, shadow, material)
        layer.set_px(tx, (ty - 1) % h, light, material)
        layer.set_px((tx + 1) % w, (ty - 1) % h, light, material)


def fill_wood_plank_tile(
    layer: IndexedLayer,
    spec: StyleSpec,
    material: str = "wood",
    planks: int = 4,
    seed: int = 42,
) -> None:
    """Fill a toroidal layer with horizontal wooden floorboards and nail details."""
    rng = random.Random(seed)
    ramp = spec.ramp(material)
    seam = ramp[0]
    dark = ramp[min(1, len(ramp) - 1)]
    mid = ramp[min(2, len(ramp) - 1)]
    light = ramp[-1]

    w, h = layer.width, layer.height
    rect(layer, 0, 0, w, h, mid, fill=True, material=material)

    for p in range(planks):
        y0 = (p * h) // planks
        y1 = ((p + 1) * h) // planks
        ph = y1 - y0
        # Bottom seam and top highlight ridge
        for x in range(w):
            layer.set_px(x, (y1 - 1) % h, seam, material)
            if ph >= 3:
                layer.set_px(x, y0, light if rng.random() > 0.2 else mid, material)
            if ph >= 4 and rng.random() < 0.22:
                layer.set_px(x, (y0 + 2) % h, dark, material)
        # Staggered vertical plank joint + twin nails
        jx = ((p * (w // 2 + 3)) + rng.randint(0, 2)) % w
        for dy in range(ph):
            layer.set_px(jx, (y0 + dy) % h, seam, material)
        if ph >= 3:
            layer.set_px((jx - 2) % w, (y0 + 1) % h, dark, material)
            layer.set_px((jx + 2) % w, (y0 + 1) % h, dark, material)


def fill_water_tile(
    layer: IndexedLayer,
    spec: StyleSpec,
    material: str = "water",
    phase: int = 0,
    seed: int = 42,
) -> None:
    """Fill a toroidal layer with animatable pixel-art water ripples."""
    rng = random.Random(seed)
    ramp = spec.ramp(material)
    deep = ramp[0]
    mid = ramp[min(1, len(ramp) - 1)]
    light = ramp[min(2, len(ramp) - 1)]
    foam = ramp[-1]

    w, h = layer.width, layer.height
    rect(layer, 0, 0, w, h, mid, fill=True, material=material)

    # Subtle horizontal wave bands shifting cleanly by phase
    for y in range(h):
        for x in range(w):
            v = math.sin((x + phase * 2) * (2 * math.pi / max(4, w)) + y * 0.7)
            if v < -0.45:
                layer.set_px(x, y, deep, material)
            elif v > 0.65:
                layer.set_px(x, y, light, material)

    # Crisp animated surface glints
    num_glints = max(2, w // 5)
    for i in range(num_glints):
        gx = (rng.randrange(w) + phase * 2) % w
        gy = (rng.randrange(h) + (1 if (i + phase) % 2 == 0 else 0)) % h
        layer.set_px(gx, gy, foam, material)
        layer.set_px((gx + 1) % w, gy, light, material)


def draw_nine_slice_panel(
    layer: IndexedLayer,
    spec: StyleSpec,
    frame_material: str = "wood",
    bg_material: str = "stone",
    accent_material: str | None = "gold",
    border: int = 5,
    corner_radius: int = 2,
) -> tuple[int, int, int, int]:
    """Draw a crisp beveled pixel-art 9-slice RPG UI panel and return (L, T, R, B) margins."""
    w, h = layer.width, layer.height
    fr = spec.ramp(frame_material)
    bg = spec.ramp(bg_material)
    ac = spec.ramp(accent_material) if (accent_material and accent_material in spec.materials) else fr

    f_out = fr[0]
    f_dark = fr[min(1, len(fr) - 1)]
    f_mid = fr[min(2, len(fr) - 1)]
    f_hi = fr[-1]

    bg_dark = bg[0]
    bg_mid = bg[min(1, len(bg) - 1)]
    bg_hi = bg[min(2, len(bg) - 1)]

    # 1. Outer silhouette (darkest frame border)
    rounded_rect(layer, 0, 0, w, h, corner_radius, f_out, fill=True, material=frame_material)
    # 2. Main frame bevel body (1px inset)
    rounded_rect(layer, 1, 1, w - 2, h - 2, max(0, corner_radius - 1), f_mid, fill=True, material=frame_material)

    # Directional bevel highlights honoring spec.light_dir
    lx, ly = spec.light_dir
    top_lit = ly <= 0.15
    left_lit = lx <= 0.15
    top_col = f_hi if top_lit else f_dark
    bot_col = f_dark if top_lit else f_hi
    left_col = f_hi if left_lit else f_dark
    right_col = f_dark if left_lit else f_hi

    for x in range(corner_radius, w - corner_radius):
        layer.set_px(x, 1, top_col, frame_material)
        layer.set_px(x, h - 2, bot_col, frame_material)
    for y in range(corner_radius, h - corner_radius):
        layer.set_px(1, y, left_col, frame_material)
        layer.set_px(w - 2, y, right_col, frame_material)

    # 3. Inner recessed trim + content panel
    b = max(3, int(border))
    # Inner dark recess line
    rect(layer, b - 1, b - 1, w - 2 * (b - 1), h - 2 * (b - 1), f_out, fill=False, material=frame_material)
    # Panel interior fill
    rect(layer, b, b, w - 2 * b, h - 2 * b, bg_mid, fill=True, material=bg_material)
    # Inner drop shadow on lit-side recess wall & subtle bounce light on opposite wall
    in_top_col = bg_dark if top_lit else bg_hi
    in_bot_col = bg_hi if top_lit else bg_dark
    in_left_col = bg_dark if left_lit else bg_hi
    in_right_col = bg_hi if left_lit else bg_dark
    line(layer, b, b, w - b - 1, b, in_top_col, material=bg_material, clean_doubles=False)
    line(layer, b, h - b - 1, w - b - 1, h - b - 1, in_bot_col, material=bg_material, clean_doubles=False)
    line(layer, b, b, b, h - b - 1, in_left_col, material=bg_material, clean_doubles=False)
    line(layer, w - b - 1, b, w - b - 1, h - b - 1, in_right_col, material=bg_material, clean_doubles=False)

    # 4. Crisp metallic corner rivets/ornaments (safely inside the 9-slice corner margins!)
    if b >= 5:
        corners = [
            (2, 2),
            (w - 4, 2),
            (2, h - 4),
            (w - 4, h - 4),
        ]
        ac_mid = ac[min(2, len(ac) - 1)]
        hi_dx = 0 if left_lit else 1
        hi_dy = 0 if top_lit else 1
        sh_dx = 1 - hi_dx
        sh_dy = 1 - hi_dy
        for cx, cy in corners:
            for rdy in (0, 1):
                for rdx in (0, 1):
                    if rdx == hi_dx and rdy == hi_dy:
                        rcol = ac[-1]
                    elif rdx == sh_dx and rdy == sh_dy:
                        rcol = ac[0]
                    else:
                        rcol = ac_mid
                    layer.set_px(cx + rdx, cy + rdy, rcol, accent_material)

    margin = b + 1
    return (margin, margin, margin, margin)


def _fill_material_base(layer: IndexedLayer, spec: StyleSpec, material: str, seed: int = 42) -> None:
    """Fill a tile layer using the best-matching built-in procedural surface texture."""
    m = material.lower()
    if "grass" in m:
        fill_grass_tile(layer, spec, material=material, seed=seed, tuft_density=0.18)
    elif "stone" in m:
        fill_stone_brick_tile(layer, spec, material=material, rows=4, cols=2, seed=seed, weathering=0.22)
    elif "wood" in m:
        fill_wood_plank_tile(layer, spec, material=material, planks=4, seed=seed)
    elif "water" in m:
        fill_water_tile(layer, spec, material=material, phase=0, seed=seed)
    else:
        rng = random.Random(seed)
        ramp = spec.ramp(material)
        dark = ramp[min(1, len(ramp) - 1)]
        mid = ramp[min(2, len(ramp) - 1)]
        light = ramp[-1]
        w, h = layer.width, layer.height
        rect(layer, 0, 0, w, h, mid, fill=True, material=material)
        for _ in range(max(3, (w * h) // 32)):
            px, py = rng.randrange(w), rng.randrange(h)
            col = dark if rng.random() < 0.6 else light
            for dy in range(rng.randint(1, 2)):
                for dx in range(rng.randint(2, 3)):
                    layer.set_px((px + dx) % w, (py + dy) % h, col, material)


def _mask_to_peering_bits(mask: int) -> dict[str, bool]:
    return {
        "top_side": bool(mask & BIT_N),
        "top_right_corner": bool(mask & BIT_NE),
        "right_side": bool(mask & BIT_E),
        "bottom_right_corner": bool(mask & BIT_SE),
        "bottom_side": bool(mask & BIT_S),
        "bottom_left_corner": bool(mask & BIT_SW),
        "left_side": bool(mask & BIT_W),
        "top_left_corner": bool(mask & BIT_NW),
    }


def render_autotile_cell(
    layer: IndexedLayer,
    spec: StyleSpec,
    mask: int,
    fill_material: str = "grass",
    bg_material: str | None = None,
    border_px: int | None = None,
    seed: int = 42,
    organic: bool = True,
) -> None:
    """Render one 16-tile or 47-tile Blob Auto-Tile cell for `mask` onto `layer`."""
    w, h = layer.width, layer.height
    eff = _canonical_blob_mask(mask)
    m = max(2, min(w, h) // 6) if border_px is None else max(1, int(border_px))

    # 1. Optional background terrain fill
    if bg_material is not None:
        _fill_material_base(layer, spec, bg_material, seed=seed + 101)

    # 2. Prepare foreground terrain texture in a scratch layer
    fg_tex = IndexedLayer("__fg__", w, h, len(spec.palette), toroidal=True)
    _fill_material_base(fg_tex, spec, fill_material, seed=seed)

    has_n = bool(eff & BIT_N)
    has_e = bool(eff & BIT_E)
    has_s = bool(eff & BIT_S)
    has_w = bool(eff & BIT_W)
    has_ne = bool(eff & BIT_NE)
    has_se = bool(eff & BIT_SE)
    has_sw = bool(eff & BIT_SW)
    has_nw = bool(eff & BIT_NW)

    # Deterministic organic edge jitter (strictly 0 on connected boundaries so adjacent tiles match!)
    def _jitter(coord: int, salt: int) -> int:
        if not organic or m < 2:
            return 0
        # Periodic subtle 0..1 wave that stays clean at tile corners
        if coord < m + 1 or coord >= max(w, h) - m - 1:
            return 0
        return 1 if ((coord * 7 + salt * 13 + seed) % 5 == 0) else 0

    fg_mask = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            in_fg = True
            # Exposed cardinal edges
            if not has_n and y < m + _jitter(x, 1):
                in_fg = False
            if not has_s and y >= h - m - _jitter(x, 2):
                in_fg = False
            if not has_w and x < m + _jitter(y, 3):
                in_fg = False
            if not has_e and x >= w - m - _jitter(y, 4):
                in_fg = False

            # Rounded outer corners when two adjacent cardinal sides are exposed
            if in_fg:
                if (not has_n and not has_w) and (x == m and y == m):
                    in_fg = False
                if (not has_n and not has_e) and (x == w - m - 1 and y == m):
                    in_fg = False
                if (not has_s and not has_w) and (x == m and y == h - m - 1):
                    in_fg = False
                if (not has_s and not has_e) and (x == w - m - 1 and y == h - m - 1):
                    in_fg = False

            # Inner-corner cutouts when both cardinal neighbors exist but diagonal does not
            if in_fg:
                if has_n and has_w and not has_nw and x < m and y < m:
                    if not (x == m - 1 and y == m - 1 and m >= 3):
                        in_fg = False
                if has_n and has_e and not has_ne and x >= w - m and y < m:
                    if not (x == w - m and y == m - 1 and m >= 3):
                        in_fg = False
                if has_s and has_w and not has_sw and x < m and y >= h - m:
                    if not (x == m - 1 and y == h - m and m >= 3):
                        in_fg = False
                if has_s and has_e and not has_se and x >= w - m and y >= h - m:
                    if not (x == w - m and y == h - m and m >= 3):
                        in_fg = False

            fg_mask[y][x] = in_fg

    ramp = spec.ramp(fill_material)
    edge_dark = ramp[0]
    edge_shadow = ramp[min(1, len(ramp) - 1)]
    edge_hi = ramp[-1]
    lx, ly = spec.light_dir
    top_lit = ly <= 0.15
    left_lit = lx <= 0.15

    bg_ramp = spec.ramp(bg_material) if bg_material is not None else None

    def _in_fg(px: int, py: int) -> bool:
        if 0 <= px < w and 0 <= py < h:
            return fg_mask[py][px]
        # Outside tile bounds: treat as foreground if connected in that direction!
        if py < 0:
            if px < 0:
                return has_nw
            if px >= w:
                return has_ne
            return has_n
        if py >= h:
            if px < 0:
                return has_sw
            if px >= w:
                return has_se
            return has_s
        if px < 0:
            return has_w
        return has_e

    # 3. Blit foreground pixels with directional beveled lip & contact shadow on background
    for y in range(h):
        for x in range(w):
            if fg_mask[y][x]:
                n_open = not _in_fg(x, y - 1)
                s_open = not _in_fg(x, y + 1)
                w_open = not _in_fg(x - 1, y)
                e_open = not _in_fg(x + 1, y)
                if n_open or s_open or w_open or e_open:
                    if (n_open and top_lit) or (w_open and left_lit):
                        col = edge_hi
                    elif (s_open and top_lit) or (e_open and left_lit):
                        col = edge_dark
                    else:
                        col = edge_shadow
                    layer.set_px(x, y, col, fill_material)
                else:
                    layer.set_px(x, y, fg_tex.grid[y][x], fill_material)
            elif bg_ramp is not None:
                # 1px contact shadow cast onto background along shadow side
                sh_dx = 1 if left_lit else -1
                sh_dy = 1 if top_lit else -1
                if _in_fg(x - sh_dx, y - sh_dy) or _in_fg(x, y - sh_dy):
                    layer.set_px(x, y, bg_ramp[0], bg_material)


def build_autotile_set(
    name: str,
    tile_size: int,
    spec: StyleSpec,
    fill_material: str = "grass",
    bg_material: str | None = "wood",
    mode: str = "blob47",
    border_px: int | None = None,
    seed: int = 42,
    organic: bool = True,
    sheet_columns: int | None = None,
) -> PixelProject:
    """Build a complete 16-tile cardinal or 47-tile Blob Auto-Tile PixelProject with engine metadata."""
    mode_norm = mode.lower()
    if mode_norm == "cardinal16":
        masks = CARDINAL16_MASKS
    elif mode_norm == "blob47":
        masks = BLOB47_MASKS
    else:
        raise ValueError(f"Unsupported autotile mode {mode!r}; use 'cardinal16' or 'blob47'.")

    proj = PixelProject(name, tile_size, tile_size, spec, category="tilesets")
    if sheet_columns is not None:
        proj.set_sheet_layout(columns=sheet_columns)
    entries: list[dict[str, Any]] = []
    for idx, mask in enumerate(masks):
        fr = proj.frame(0) if idx == 0 else proj.add_frame()
        lyr = fr.layer("terrain")
        render_autotile_cell(
            lyr,
            spec,
            mask=mask,
            fill_material=fill_material,
            bg_material=bg_material,
            border_px=border_px,
            seed=seed,
            organic=organic,
        )
        entries.append(
            {
                "frame": idx,
                "bitmask": mask,
                "peering_bits": _mask_to_peering_bits(mask),
            }
        )

    proj.metadata["autotile"] = {
        "mode": mode_norm,
        "tile_size": [tile_size, tile_size],
        "tile_count": len(masks),
        "fill_material": fill_material,
        "bg_material": bg_material,
        "tiles": entries,
    }
    return proj


def fill_transition_tile(
    layer: IndexedLayer,
    spec: StyleSpec,
    top_material: str = "grass",
    bottom_material: str = "stone",
    edge: str = "top",
    thickness: int | None = None,
    seed: int = 42,
) -> None:
    """Fill a terrain transition tile where `top_material` organically overlaps `bottom_material`."""
    edge_norm = edge.lower()
    if edge_norm not in ("top", "bottom", "left", "right"):
        raise ValueError(f"Invalid transition edge {edge!r}; use 'top', 'bottom', 'left', or 'right'.")
    w, h = layer.width, layer.height
    _fill_material_base(layer, spec, bottom_material, seed=seed + 53)

    fg_tex = IndexedLayer("__trans_fg__", w, h, len(spec.palette), toroidal=True)
    _fill_material_base(fg_tex, spec, top_material, seed=seed)

    span = h if edge_norm in ("top", "bottom") else w
    thick = max(3, span // 2) if thickness is None else max(2, min(span - 2, int(thickness)))
    fg_ramp = spec.ramp(top_material)
    bg_ramp = spec.ramp(bottom_material)

    # Periodic organic wave along the seamless axis so opposite edges match 100% seamlessly
    axis_len = w if edge_norm in ("top", "bottom") else h
    wave = [
        round(math.sin((i / max(1, axis_len)) * 2.0 * math.pi * 2.0 + seed) * 1.1)
        for i in range(axis_len)
    ]

    for y in range(h):
        for x in range(w):
            if edge_norm == "top":
                bound = thick + wave[x]
                in_top = y < bound
                on_lip = y == bound - 1
                on_shadow = y == bound
            elif edge_norm == "bottom":
                bound = h - thick - wave[x]
                in_top = y >= bound
                on_lip = y == bound
                on_shadow = y == bound - 1
            elif edge_norm == "left":
                bound = thick + wave[y]
                in_top = x < bound
                on_lip = x == bound - 1
                on_shadow = x == bound
            else:
                bound = w - thick - wave[y]
                in_top = x >= bound
                on_lip = x == bound
                on_shadow = x == bound - 1

            if in_top:
                col = fg_ramp[-1] if (on_lip and edge_norm in ("bottom", "right")) else (
                    fg_ramp[0] if on_lip else fg_tex.grid[y][x]
                )
                layer.set_px(x, y, col, top_material)
            elif on_shadow:
                layer.set_px(x, y, bg_ramp[0], bottom_material)


def draw_iso_diamond(
    layer: IndexedLayer,
    spec: StyleSpec,
    material: str = "grass",
    top_y: int = 0,
    width_px: int | None = None,
    seed: int = 42,
    textured: bool = True,
) -> tuple[int, int]:
    """Draw a crisp 2:1 pixel-art isometric diamond surface and return (diamond_w, diamond_h)."""
    w, h = layer.width, layer.height
    dw = (w if width_px is None else int(width_px))
    # Force multiple of 4 for symmetric 2:1 steps (4, 8, 12, ... -> dw)
    dw = max(8, (dw // 4) * 4)
    dh = dw // 2
    cx = w // 2

    tex = IndexedLayer("__iso_tex__", w, h, len(spec.palette), toroidal=True)
    if textured:
        _fill_material_base(tex, spec, material, seed=seed)
    else:
        rect(tex, 0, 0, w, h, spec.color(material, 2), fill=True, material=material)

    ramp = spec.ramp(material)
    hi = ramp[-1]
    dark = ramp[min(1, len(ramp) - 1)]
    lx, _ = spec.light_dir
    left_lit = lx <= 0.15

    half_h = dh // 2
    for row in range(dh):
        py = top_y + row
        if not (0 <= py < h):
            continue
        k = row if row < half_h else (dh - 1 - row)
        half_w = (k + 1) * 2
        x0 = cx - half_w
        x1 = cx + half_w - 1
        for px in range(x0, x1 + 1):
            # Subtle directional rim highlight along upper-lit edges
            if row < half_h and (px == x0 or px == x0 + 1) and left_lit:
                col = hi
            elif row < half_h and (px == x1 or px == x1 - 1) and not left_lit:
                col = hi
            elif row >= half_h and (px == x1 or px == x1 - 1) and left_lit:
                col = dark
            elif row >= half_h and (px == x0 or px == x0 + 1) and not left_lit:
                col = dark
            else:
                col = tex.grid[py % h][px % w]
            layer.set_px(px, py, col, material)
    return (dw, dh)


def draw_iso_block(
    layer: IndexedLayer,
    spec: StyleSpec,
    top_material: str = "grass",
    side_material: str = "wood",
    height_px: int | None = None,
    seed: int = 42,
    outline: bool = True,
) -> dict[str, int]:
    """Draw a 2:1 pixel-art isometric 3D block (lit top, left/right shaded faces, optional Sel-Out)."""
    w, h = layer.width, layer.height
    rng = random.Random(seed)
    pad_top = 1 if outline else 0
    dw = max(8, ((w - (2 if outline else 0)) // 4) * 4)
    dh = dw // 2
    max_side_h = max(2, h - dh - (2 if outline else 0))
    sh = min(max_side_h, max(4, dh // 2)) if height_px is None else max(2, min(max_side_h, int(height_px)))
    top_y = pad_top
    cx = w // 2
    half_h = dh // 2

    # 1. Top isometric diamond face
    body = IndexedLayer("__iso_body__", w, h, len(spec.palette), toroidal=False)
    draw_iso_diamond(body, spec, material=top_material, top_y=top_y, width_px=dw, seed=seed, textured=True)

    # 2. Left & right vertical extruded faces honoring spec.light_dir
    side_ramp = spec.ramp(side_material)
    s_deep = side_ramp[0]
    s_dark = side_ramp[min(1, len(side_ramp) - 1)]
    s_mid = side_ramp[min(2, len(side_ramp) - 1)]
    s_lit = side_ramp[min(3, len(side_ramp) - 1)]

    lx, _ = spec.light_dir
    left_lit = lx <= 0.15
    left_base = s_lit if left_lit else s_dark
    left_var = s_mid if left_lit else s_deep
    right_base = s_dark if left_lit else s_lit
    right_var = s_deep if left_lit else s_mid

    top_ramp = spec.ramp(top_material)
    overhang = "grass" in top_material.lower()

    # Extrude downward from the lower V-edge of the diamond with clustered vertical strata
    half_span = dw // 2
    left_strata = [rng.random() < 0.3 for _ in range(half_span)]
    right_strata = [rng.random() < 0.3 for _ in range(half_span)]

    for x_off in range(half_span):
        # Left face: x goes from cx - dw//2 .. cx - 1; bottom of diamond slopes down by 1 every 2px
        lx_px = cx - half_span + x_off
        start_y = top_y + half_h + (x_off // 2)
        over_len = (2 if (x_off % 4 < 2) else 1) if overhang else 0
        use_l_var = left_strata[x_off]
        for dy in range(1, sh + 1):
            py = start_y + dy
            if dy <= over_len:
                col = top_ramp[min(1, len(top_ramp) - 1)] if dy == over_len else top_ramp[min(2, len(top_ramp) - 1)]
                body.set_px(lx_px, py, col, top_material)
            else:
                if dy == sh:
                    col = s_deep
                elif lx_px == cx - 1:
                    col = side_ramp[-1] if left_lit else s_mid  # Crisp center ridge highlight
                elif use_l_var and 2 <= dy <= max(2, sh - 2):
                    col = left_var
                else:
                    col = left_base
                body.set_px(lx_px, py, col, side_material)

        # Right face: x goes from cx .. cx + dw//2 - 1
        rx_px = cx + x_off
        start_yr = top_y + dh - 1 - (x_off // 2)
        over_len_r = (2 if ((x_off + 2) % 4 < 2) else 1) if overhang else 0
        use_r_var = right_strata[x_off]
        for dy in range(1, sh + 1):
            py = start_yr + dy
            if dy <= over_len_r:
                col = top_ramp[0] if dy == over_len_r else top_ramp[min(1, len(top_ramp) - 1)]
                body.set_px(rx_px, py, col, top_material)
            else:
                if dy == sh:
                    col = s_deep
                elif rx_px == cx:
                    col = s_mid if left_lit else side_ramp[-1]
                elif use_r_var and 2 <= dy <= max(2, sh - 2):
                    col = right_var
                else:
                    col = right_base
                body.set_px(rx_px, py, col, side_material)

    if outline:
        out_lyr = IndexedLayer("__iso_out__", w, h, len(spec.palette), toroidal=False)
        apply_outline(out_lyr, body, spec)
        layer.blit(out_lyr)
    layer.blit(body)
    return {"diamond_w": dw, "diamond_h": dh, "side_height": sh}


def draw_ui_button(
    layer: IndexedLayer,
    spec: StyleSpec,
    state: str = "normal",
    frame_material: str = "wood",
    fill_material: str = "cloth_blue",
    accent_material: str | None = "gold",
    corner_radius: int = 2,
) -> tuple[int, int, int, int]:
    """Draw a pixel-art UI button in 'normal', 'hover', 'pressed', or 'disabled' state."""
    st = state.lower()
    if st not in ("normal", "hover", "pressed", "disabled"):
        raise ValueError(f"Invalid button state {state!r}; use normal, hover, pressed, or disabled.")

    w, h = layer.width, layer.height
    use_frame = "stone" if st == "disabled" else frame_material
    use_fill = "stone" if st == "disabled" else fill_material
    fr = spec.ramp(use_frame)
    fl = spec.ramp(use_fill)
    ac = spec.ramp(accent_material) if (accent_material and accent_material in spec.materials and st != "disabled") else fr

    y_off = 1 if st == "pressed" else 0
    btn_h = h - 1 if st == "pressed" else h
    r = max(0, min(corner_radius, w // 4, btn_h // 4))

    # Outer frame silhouette
    rounded_rect(layer, 0, y_off, w, btn_h, r, fr[0], fill=True, material=use_frame)

    # Inner button face
    if st == "hover":
        face_col = fl[min(len(fl) - 1, 3)]
        top_edge = fl[-1]
        bot_edge = fl[min(len(fl) - 1, 2)]
    elif st == "pressed":
        face_col = fl[min(len(fl) - 1, 1)]
        top_edge = fl[0]
        bot_edge = fl[min(len(fl) - 1, 2)]
    elif st == "disabled":
        face_col = fl[min(len(fl) - 1, 1)]
        top_edge = fl[min(len(fl) - 1, 2)]
        bot_edge = fl[0]
    else:
        face_col = fl[min(len(fl) - 1, 2)]
        top_edge = fl[-1]
        bot_edge = fl[min(len(fl) - 1, 1)]

    inner_h = max(2, btn_h - (3 if st != "pressed" else 2))
    rounded_rect(layer, 1, y_off + 1, w - 2, inner_h, max(0, r - 1), face_col, fill=True, material=use_fill)

    # Top highlight & bottom depth lip
    for x in range(max(1, r), w - max(1, r)):
        layer.set_px(x, y_off + 1, top_edge, use_fill)
        layer.set_px(x, y_off + inner_h, bot_edge, use_fill)
        if st != "pressed" and y_off + inner_h + 1 < h - 1:
            layer.set_px(x, y_off + inner_h + 1, fr[min(1, len(fr) - 1)], use_frame)

    # Side trim accents
    if w >= 12 and btn_h >= 10:
        acc_col = ac[-1] if st == "hover" else ac[min(2, len(ac) - 1)]
        layer.set_px(2, y_off + 2, acc_col, accent_material if st != "disabled" else use_frame)
        layer.set_px(w - 3, y_off + 2, acc_col, accent_material if st != "disabled" else use_frame)

    mx = max(3, r + 2)
    my = max(3, r + 2)
    return (mx, my, mx, my)


def build_button_states(
    name: str,
    width: int,
    height: int,
    spec: StyleSpec,
    frame_material: str = "wood",
    fill_material: str = "cloth_blue",
    accent_material: str | None = "gold",
    corner_radius: int = 2,
) -> PixelProject:
    """Create a 4-frame UI button state sheet (normal, hover, pressed, disabled) with 9-slice metadata."""
    states = ("normal", "hover", "pressed", "disabled")
    proj = PixelProject(name, width, height, spec, category="ui")
    margins = (3, 3, 3, 3)
    for idx, st in enumerate(states):
        fr = proj.frame(0) if idx == 0 else proj.add_frame(duration_ms=250)
        margins = draw_ui_button(
            fr.layer("button"),
            spec,
            state=st,
            frame_material=frame_material,
            fill_material=fill_material,
            accent_material=accent_material,
            corner_radius=corner_radius,
        )
    proj.set_nine_slice(*margins)
    proj.metadata["ui_states"] = {st: idx for idx, st in enumerate(states)}
    return proj


def draw_health_bar(
    layer: IndexedLayer,
    spec: StyleSpec,
    ratio: float = 0.75,
    frame_material: str = "steel",
    fill_material: str = "cloth_red",
    bg_material: str = "dark_ink",
    segmented: int = 0,
) -> None:
    """Draw a beveled pixel-art RPG health/mana/XP bar with specular sheen and optional tick marks."""
    w, h = layer.width, layer.height
    if w < 8 or h < 5:
        raise ValueError(f"Health bar canvas must be at least 8x5, got {w}x{h}.")
    r_clamped = max(0.0, min(1.0, float(ratio)))
    fr = spec.ramp(frame_material)
    fl = spec.ramp(fill_material)
    bg = spec.ramp(bg_material)

    # Outer metallic/wood bevel frame
    rounded_rect(layer, 0, 0, w, h, 1, fr[0], fill=True, material=frame_material)
    rect(layer, 1, 1, w - 2, h - 2, fr[min(2, len(fr) - 1)], fill=False, material=frame_material)
    # Lit top frame edge
    line(layer, 1, 1, w - 2, 1, fr[-1], material=frame_material, clean_doubles=False)
    line(layer, 1, h - 2, w - 2, h - 2, fr[min(1, len(fr) - 1)], material=frame_material, clean_doubles=False)

    # Recessed dark trough
    ix, iy = 2, 2
    iw, ih = w - 4, h - 4
    rect(layer, ix, iy, iw, ih, bg[0], fill=True, material=bg_material)
    if ih >= 2:
        line(layer, ix, iy + ih - 1, ix + iw - 1, iy + ih - 1, bg[min(1, len(bg) - 1)], material=bg_material, clean_doubles=False)

    # Filled bar with top highlight strip, midtone body, bottom shadow, and crisp leading edge
    fill_w = round(iw * r_clamped)
    if fill_w > 0:
        mid_c = fl[min(2, len(fl) - 1)]
        hi_c = fl[-1]
        sh_c = fl[min(1, len(fl) - 1)]
        rect(layer, ix, iy, fill_w, ih, mid_c, fill=True, material=fill_material)
        line(layer, ix, iy, ix + fill_w - 1, iy, hi_c, material=fill_material, clean_doubles=False)
        if ih >= 3:
            line(layer, ix, iy + ih - 1, ix + fill_w - 1, iy + ih - 1, sh_c, material=fill_material, clean_doubles=False)
        # Bright leading glint at bar tip when partially filled
        if 0 < fill_w < iw:
            line(layer, ix + fill_w - 1, iy, ix + fill_w - 1, iy + ih - 1, hi_c, material=fill_material, clean_doubles=False)

    # Optional segment ticks
    if segmented > 1 and iw >= segmented * 3:
        for s in range(1, segmented):
            tx = ix + (s * iw) // segmented
            line(layer, tx, iy, tx, iy + ih - 1, fr[0], material=frame_material, clean_doubles=False)


def draw_item_slot(
    layer: IndexedLayer,
    spec: StyleSpec,
    frame_material: str = "wood",
    bg_material: str = "stone",
    accent_material: str = "gold",
    selected: bool = False,
    rarity_material: str | None = None,
) -> tuple[int, int, int, int]:
    """Draw a recessed inventory item slot with optional selection brackets and rarity rim."""
    w, h = layer.width, layer.height
    fr = spec.ramp(frame_material)
    bg = spec.ramp(bg_material)
    ac = spec.ramp(accent_material) if accent_material in spec.materials else fr

    rounded_rect(layer, 0, 0, w, h, 1, fr[0], fill=True, material=frame_material)
    rect(layer, 1, 1, w - 2, h - 2, fr[min(2, len(fr) - 1)], fill=False, material=frame_material)
    line(layer, 1, 1, w - 2, 1, fr[-1], material=frame_material, clean_doubles=False)
    line(layer, 1, 1, 1, h - 2, fr[-1], material=frame_material, clean_doubles=False)
    line(layer, 2, h - 2, w - 2, h - 2, fr[min(1, len(fr) - 1)], material=frame_material, clean_doubles=False)
    line(layer, w - 2, 2, w - 2, h - 2, fr[min(1, len(fr) - 1)], material=frame_material, clean_doubles=False)

    # Inner recessed well
    rect(layer, 2, 2, w - 4, h - 4, bg[min(1, len(bg) - 1)], fill=True, material=bg_material)
    # Recessed inner shadow (top & left) + bounce (bottom & right)
    line(layer, 2, 2, w - 3, 2, bg[0], material=bg_material, clean_doubles=False)
    line(layer, 2, 2, 2, h - 3, bg[0], material=bg_material, clean_doubles=False)
    line(layer, 3, h - 3, w - 3, h - 3, bg[min(2, len(bg) - 1)], material=bg_material, clean_doubles=False)
    line(layer, w - 3, 3, w - 3, h - 3, bg[min(2, len(bg) - 1)], material=bg_material, clean_doubles=False)

    # Optional rarity glow border inside the well
    if rarity_material and rarity_material in spec.materials:
        rr = spec.ramp(rarity_material)
        rect(layer, 2, 2, w - 4, h - 4, rr[-1], fill=False, material=rarity_material)

    # Crisp corner L-brackets when selected
    if selected and w >= 12 and h >= 12:
        arm = max(2, min(4, w // 5))
        c_hi = ac[-1]
        c_mid = ac[min(2, len(ac) - 1)]
        for i in range(arm):
            # Top-left & top-right
            layer.set_px(i, 0, c_hi, accent_material)
            layer.set_px(0, i, c_hi, accent_material)
            layer.set_px(w - 1 - i, 0, c_hi, accent_material)
            layer.set_px(w - 1, i, c_mid, accent_material)
            # Bottom-left & bottom-right
            layer.set_px(i, h - 1, c_mid, accent_material)
            layer.set_px(0, h - 1 - i, c_mid, accent_material)
            layer.set_px(w - 1 - i, h - 1, c_mid, accent_material)
            layer.set_px(w - 1, h - 1 - i, c_mid, accent_material)

    return (3, 3, 3, 3)
