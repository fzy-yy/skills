"""Strict indexed-color canvas, layers, frames, tags, slices, and PixelProject container."""

from __future__ import annotations

import math
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping

from .palette import luminance
from .spec import StyleSpec

TRANSPARENT = -1
VALID_CATEGORIES = ("icons", "characters", "tilesets", "ui")
_BOTTOM_SHADOW_NAMES = frozenset({"shadow", "ground_shadow", "drop_shadow"})
_TOP_FX_NAMES = frozenset({"fx", "vfx", "glow", "smear"})


def _default_layer_z(name: str) -> int:
    """Assign sensible canonical Z-buckets so outlines never slice top FX and stay behind solids."""
    low = name.lower()
    if low in _BOTTOM_SHADOW_NAMES or low.endswith("_shadow"):
        return -200
    if "outline" in low:
        return -100
    if low in _TOP_FX_NAMES or low.endswith(("_fx", "_vfx", "_glow")):
        return 100
    return 0


class IndexedLayer:
    """2D strictly indexed pixel buffer (-1 = transparent, 0..N-1 = palette index).

    Because only integer palette indices can be stored, semi-transparent alpha halos
    and out-of-palette colors are impossible by construction.
    """

    def __init__(
        self,
        name: str,
        width: int,
        height: int,
        palette_size: int,
        toroidal: bool = False,
        visible: bool = True,
        opacity: int = 255,
        z_index: int | None = None,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"Canvas dimensions must be positive integers, got {width}x{height}")
        self.name = name
        self._width = int(width)
        self._height = int(height)
        self._palette_size = int(palette_size)
        self.toroidal = bool(toroidal)
        self.visible = bool(visible)
        self.opacity = max(0, min(255, int(opacity)))
        self.z_index: int | None = int(z_index) if z_index is not None else None
        self.grid: list[list[int]] = [[TRANSPARENT] * self._width for _ in range(self._height)]
        self.material_map: list[list[str | None]] = [
            [None] * self._width for _ in range(self._height)
        ]
        self.clipped_count: int = 0
        self.alpha_lock: bool = False

    @contextmanager
    def lock_alpha(self) -> Iterator["IndexedLayer"]:
        """Temporarily lock transparency so drawing only affects already-opaque pixels."""
        prev = self.alpha_lock
        self.alpha_lock = True
        try:
            yield self
        finally:
            self.alpha_lock = prev

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def palette_size(self) -> int:
        return self._palette_size

    def _resolve_coord(self, x: int, y: int) -> tuple[int, int] | None:
        ix, iy = int(x), int(y)
        if self.toroidal:
            return (ix % self._width, iy % self._height)
        if 0 <= ix < self._width and 0 <= iy < self._height:
            return (ix, iy)
        return None

    def set_px(
        self,
        x: int,
        y: int,
        color_idx: int,
        material: str | None = None,
    ) -> bool:
        """Set a pixel to a validated palette index (or TRANSPARENT)."""
        if color_idx != TRANSPARENT and not (0 <= color_idx < self._palette_size):
            raise ValueError(
                f"Invalid palette index {color_idx}; must be -1 or in [0, {self._palette_size - 1}]."
            )
        pos = self._resolve_coord(x, y)
        if pos is None:
            if color_idx != TRANSPARENT:
                self.clipped_count += 1
            return False
        rx, ry = pos
        if self.alpha_lock and self.grid[ry][rx] == TRANSPARENT:
            return False
        self.grid[ry][rx] = color_idx
        if color_idx == TRANSPARENT:
            self.material_map[ry][rx] = None
        elif material is not None or not self.alpha_lock:
            self.material_map[ry][rx] = material
        return True

    def get_px(self, x: int, y: int) -> int:
        pos = self._resolve_coord(x, y)
        if pos is None:
            return TRANSPARENT
        return self.grid[pos[1]][pos[0]]

    def get_material(self, x: int, y: int) -> str | None:
        pos = self._resolve_coord(x, y)
        if pos is None:
            return None
        return self.material_map[pos[1]][pos[0]]

    def clear(self) -> None:
        for y in range(self._height):
            for x in range(self._width):
                self.grid[y][x] = TRANSPARENT
                self.material_map[y][x] = None

    def copy(self, new_name: str | None = None) -> "IndexedLayer":
        dup = IndexedLayer(
            name=new_name or self.name,
            width=self._width,
            height=self._height,
            palette_size=self._palette_size,
            toroidal=self.toroidal,
            visible=self.visible,
            opacity=self.opacity,
            z_index=self.z_index,
        )
        dup.grid = [row[:] for row in self.grid]
        dup.material_map = [row[:] for row in self.material_map]
        dup.clipped_count = self.clipped_count
        return dup

    def shift(self, dx: int, dy: int) -> "IndexedLayer":
        """Return a shifted copy of this layer by exact integer pixel offsets."""
        out = IndexedLayer(
            name=self.name,
            width=self._width,
            height=self._height,
            palette_size=self._palette_size,
            toroidal=self.toroidal,
            visible=self.visible,
            opacity=self.opacity,
            z_index=self.z_index,
        )
        for y in range(self._height):
            for x in range(self._width):
                c = self.grid[y][x]
                if c != TRANSPARENT:
                    out.set_px(x + dx, y + dy, c, self.material_map[y][x])
        return out

    def flip_x(self) -> "IndexedLayer":
        out = self.copy()
        for y in range(self._height):
            out.grid[y] = list(reversed(self.grid[y]))
            out.material_map[y] = list(reversed(self.material_map[y]))
        return out

    def flip_y(self) -> "IndexedLayer":
        out = self.copy()
        out.grid = [row[:] for row in reversed(self.grid)]
        out.material_map = [row[:] for row in reversed(self.material_map)]
        return out

    def remap_material(self, mapping: Mapping[str, str], spec: StyleSpec) -> int:
        """Palette-swap pixels belonging to source materials onto target materials by shade ratio."""
        changed = 0
        for y in range(self._height):
            row = self.grid[y]
            mrow = self.material_map[y]
            for x in range(self._width):
                c = row[x]
                if c == TRANSPARENT:
                    continue
                src_mat = mrow[x]
                if not src_mat or src_mat not in mapping:
                    continue
                dst_mat = mapping[src_mat]
                src_ramp = spec.ramp(src_mat)
                dst_ramp = spec.ramp(dst_mat)
                if c in src_ramp:
                    s_idx = src_ramp.index(c)
                else:
                    c_lum = luminance(spec.palette.rgb_at(c))
                    s_idx = min(
                        range(len(src_ramp)),
                        key=lambda i: abs(luminance(spec.palette.rgb_at(src_ramp[i])) - c_lum),
                    )
                if len(src_ramp) > 1:
                    t = s_idx / (len(src_ramp) - 1)
                    d_idx = round(t * (len(dst_ramp) - 1))
                else:
                    d_idx = min(s_idx, len(dst_ramp) - 1)
                row[x] = dst_ramp[max(0, min(len(dst_ramp) - 1, d_idx))]
                mrow[x] = dst_mat
                changed += 1
        return changed

    def _scale3x_crop(
        self, min_x: int, min_y: int, max_x: int, max_y: int
    ) -> tuple[list[list[int]], list[list[str | None]]]:
        """Edge-preserving Scale3x (AdvMAME3x) upscaling of the bounded region for clean RotSprite rotation."""
        cw = max_x - min_x + 1
        ch = max_y - min_y + 1
        sw, sh = cw * 3, ch * 3
        s_grid = [[TRANSPARENT] * sw for _ in range(sh)]
        s_mat: list[list[str | None]] = [[None] * sw for _ in range(sh)]

        for ly in range(ch):
            gy = min_y + ly
            for lx in range(cw):
                gx = min_x + lx
                e = self.get_px(gx, gy)
                em = self.get_material(gx, gy)
                a = self.get_px(gx - 1, gy - 1)
                b = self.get_px(gx, gy - 1)
                c = self.get_px(gx + 1, gy - 1)
                d = self.get_px(gx - 1, gy)
                f = self.get_px(gx + 1, gy)
                g = self.get_px(gx - 1, gy + 1)
                h = self.get_px(gx, gy + 1)
                i_px = self.get_px(gx + 1, gy + 1)

                if b != h and d != f:
                    e0 = d if d == b else e
                    e1 = b if ((d == b and e != c) or (b == f and e != a)) else e
                    e2 = f if b == f else e
                    e3 = d if ((d == b and e != g) or (d == h and e != a)) else e
                    e4 = e
                    e5 = f if ((b == f and e != i_px) or (h == f and e != c)) else e
                    e6 = d if d == h else e
                    e7 = h if ((d == h and e != i_px) or (h == f and e != g)) else e
                    e8 = f if h == f else e
                else:
                    e0 = e1 = e2 = e3 = e4 = e5 = e6 = e7 = e8 = e

                bm = self.get_material(gx, gy - 1)
                dm = self.get_material(gx - 1, gy)
                fm = self.get_material(gx + 1, gy)
                hm = self.get_material(gx, gy + 1)

                def _mat_for(val: int) -> str | None:
                    if val == TRANSPARENT:
                        return None
                    if val == e:
                        return em
                    if val == d:
                        return dm
                    if val == f:
                        return fm
                    if val == b:
                        return bm
                    if val == h:
                        return hm
                    return em

                cells = (
                    (0, 0, e0), (1, 0, e1), (2, 0, e2),
                    (0, 1, e3), (1, 1, e4), (2, 1, e5),
                    (0, 2, e6), (1, 2, e7), (2, 2, e8),
                )
                ox, oy = lx * 3, ly * 3
                for dx, dy, val in cells:
                    s_grid[oy + dy][ox + dx] = val
                    s_mat[oy + dy][ox + dx] = _mat_for(val)
        return s_grid, s_mat

    def rotate(
        self,
        angle_deg: float,
        pivot: tuple[float, float] | None = None,
    ) -> "IndexedLayer":
        """Rotate layer cleanly around `pivot` using RotSprite (Scale3x + inverse rotation + vote downsample)."""
        out = IndexedLayer(
            name=self.name,
            width=self._width,
            height=self._height,
            palette_size=self._palette_size,
            toroidal=self.toroidal,
            visible=self.visible,
            opacity=self.opacity,
            z_index=self.z_index,
        )
        bb = self.bbox()
        if bb is None:
            return out
        norm_deg = float(angle_deg) % 360.0
        if abs(norm_deg) < 1e-4 or abs(norm_deg - 360.0) < 1e-4:
            return self.copy()

        min_x, min_y, max_x, max_y = bb
        px, py = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0) if pivot is None else (float(pivot[0]), float(pivot[1]))

        # Fast exact lossless integer path for 90 / 180 / 270 degrees
        for q_deg, cos_i, sin_i in ((90.0, 0, 1), (180.0, -1, 0), (270.0, 0, -1)):
            if abs(norm_deg - q_deg) < 1e-4:
                for y in range(min_y, max_y + 1):
                    for x in range(min_x, max_x + 1):
                        c = self.grid[y][x]
                        if c == TRANSPARENT:
                            continue
                        dx = x - px
                        dy = y - py
                        nx = round(px + dx * cos_i - dy * sin_i)
                        ny = round(py + dx * sin_i + dy * cos_i)
                        out.set_px(nx, ny, c, self.material_map[y][x])
                return out

        # Scale3x RotSprite path for arbitrary angles
        s_grid, s_mat = self._scale3x_crop(min_x, min_y, max_x, max_y)
        sh = len(s_grid)
        sw = len(s_grid[0])

        rad = math.radians(norm_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        # Conservative bounding radius in output space
        corners = ((min_x, min_y), (max_x, min_y), (min_x, max_y), (max_x, max_y))
        max_r = max(math.hypot(cx - px, cy - py) for cx, cy in corners) + 2.0
        out_x0 = max(0, math.floor(px - max_r))
        out_x1 = min(self._width - 1, math.ceil(px + max_r))
        out_y0 = max(0, math.floor(py - max_r))
        out_y1 = min(self._height - 1, math.ceil(py + max_r))

        for oy in range(out_y0, out_y1 + 1):
            for ox in range(out_x0, out_x1 + 1):
                votes: list[tuple[int, str | None]] = []
                # Sample 3x3 subpixels inside destination pixel for clean RotSprite downsampling
                for sub_y in (-1, 0, 1):
                    for sub_x in (-1, 0, 1):
                        dx = (ox + sub_x / 3.0) - px
                        dy = (oy + sub_y / 3.0) - py
                        # Inverse rotation
                        src_x = px + dx * cos_a + dy * sin_a
                        src_y = py - dx * sin_a + dy * cos_a
                        sx = math.floor((src_x - min_x + 0.5) * 3.0)
                        sy = math.floor((src_y - min_y + 0.5) * 3.0)
                        if 0 <= sx < sw and 0 <= sy < sh:
                            sc = s_grid[sy][sx]
                            sm = s_mat[sy][sx]
                        else:
                            sc, sm = TRANSPARENT, None
                        weight = 2 if (sub_x == 0 and sub_y == 0) else 1
                        for _ in range(weight):
                            votes.append((sc, sm))
                opaque_votes = [v for v in votes if v[0] != TRANSPARENT]
                if len(opaque_votes) * 2 >= len(votes):
                    best_c = Counter(c for c, _ in opaque_votes).most_common(1)[0][0]
                    best_m = next((m for c, m in opaque_votes if c == best_c and m is not None), None)
                    out.set_px(ox, oy, best_c, best_m)
        return out

    def squash_stretch(
        self,
        sx: float = 1.0,
        sy: float = 1.0,
        anchor: tuple[float, float] | None = None,
    ) -> "IndexedLayer":
        """Apply nearest-neighbor 1x-grid squash & stretch around `anchor` (default: bottom-center of bbox)."""
        if sx <= 0 or sy <= 0:
            raise ValueError(f"Scale factors must be positive, got sx={sx}, sy={sy}")
        out = IndexedLayer(
            name=self.name,
            width=self._width,
            height=self._height,
            palette_size=self._palette_size,
            toroidal=self.toroidal,
            visible=self.visible,
            opacity=self.opacity,
            z_index=self.z_index,
        )
        bb = self.bbox()
        if bb is None:
            return out
        if abs(sx - 1.0) < 1e-4 and abs(sy - 1.0) < 1e-4:
            return self.copy()
        min_x, min_y, max_x, max_y = bb
        ax, ay = ((min_x + max_x) / 2.0, float(max_y)) if anchor is None else (float(anchor[0]), float(anchor[1]))

        out_x0 = max(0, math.floor(ax + (min_x - ax) * sx) - 1)
        out_x1 = min(self._width - 1, math.ceil(ax + (max_x - ax) * sx) + 1)
        out_y0 = max(0, math.floor(ay + (min_y - ay) * sy) - 1)
        out_y1 = min(self._height - 1, math.ceil(ay + (max_y - ay) * sy) + 1)

        for y in range(out_y0, out_y1 + 1):
            src_y = round(ay + (y - ay) / sy)
            if not (min_y <= src_y <= max_y):
                continue
            for x in range(out_x0, out_x1 + 1):
                src_x = round(ax + (x - ax) / sx)
                if not (min_x <= src_x <= max_x):
                    continue
                c = self.grid[src_y][src_x]
                if c != TRANSPARENT:
                    out.set_px(x, y, c, self.material_map[src_y][src_x])
        return out

    def blit(self, src: "IndexedLayer", ox: int = 0, oy: int = 0) -> None:
        """Composite non-transparent pixels from src onto this layer at offset (ox, oy)."""
        for y in range(src.height):
            for x in range(src.width):
                c = src.grid[y][x]
                if c != TRANSPARENT:
                    self.set_px(x + ox, y + oy, c, src.material_map[y][x])

    def bbox(self) -> tuple[int, int, int, int] | None:
        """Return (min_x, min_y, max_x, max_y) inclusive of non-transparent pixels, or None."""
        min_x, min_y = self._width, self._height
        max_x, max_y = -1, -1
        for y in range(self._height):
            row = self.grid[y]
            for x in range(self._width):
                if row[x] != TRANSPARENT:
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    if y > max_y:
                        max_y = y
        if max_x < min_x:
            return None
        return (min_x, min_y, max_x, max_y)

    def non_empty_count(self) -> int:
        return sum(1 for row in self.grid for c in row if c != TRANSPARENT)

    def used_colors(self) -> set[int]:
        return {c for row in self.grid for c in row if c != TRANSPARENT}

    def iter_opaque(self) -> Iterable[tuple[int, int, int]]:
        for y in range(self._height):
            row = self.grid[y]
            for x in range(self._width):
                c = row[x]
                if c != TRANSPARENT:
                    yield (x, y, c)


class Frame:
    """One animation frame containing ordered semantic layers (bottom -> top)."""

    def __init__(
        self,
        width: int,
        height: int,
        palette_size: int,
        duration_ms: int = 150,
        toroidal: bool = False,
    ) -> None:
        self.width = width
        self.height = height
        self.palette_size = palette_size
        self.duration_ms = max(10, int(duration_ms))
        self.toroidal = toroidal
        self.layers: dict[str, IndexedLayer] = {}

    def layer(
        self,
        name: str,
        create: bool = True,
        z_index: int | None = None,
    ) -> IndexedLayer:
        if name not in self.layers:
            if not create:
                raise KeyError(f"Layer {name!r} does not exist in frame.")
            self.layers[name] = IndexedLayer(
                name=name,
                width=self.width,
                height=self.height,
                palette_size=self.palette_size,
                toroidal=self.toroidal,
                z_index=z_index,
            )
        elif z_index is not None:
            self.layers[name].z_index = int(z_index)
        return self.layers[name]

    def ordered_layers(self, layer_order: Iterable[str] | None = None) -> list[IndexedLayer]:
        """Return layers sorted bottom-to-top using explicit z_index or canonical layer roles."""
        if layer_order is not None:
            seen: set[str] = set()
            ordered: list[IndexedLayer] = []
            for lname in layer_order:
                if lname in self.layers and lname not in seen:
                    ordered.append(self.layers[lname])
                    seen.add(lname)
            for lname, lyr in self.layers.items():
                if lname not in seen:
                    ordered.append(lyr)
            return ordered

        indexed = list(enumerate(self.layers.values()))
        indexed.sort(
            key=lambda item: (
                item[1].z_index if item[1].z_index is not None else _default_layer_z(item[1].name),
                item[0],
            )
        )
        return [lyr for _, lyr in indexed]

    def set_layer(self, layer: IndexedLayer) -> None:
        if layer.width != self.width or layer.height != self.height:
            raise ValueError(
                f"Layer {layer.name!r} dimensions {layer.width}x{layer.height} do not match "
                f"locked frame dimensions {self.width}x{self.height}."
            )
        self.layers[layer.name] = layer

    def copy(self, duration_ms: int | None = None) -> "Frame":
        out = Frame(
            width=self.width,
            height=self.height,
            palette_size=self.palette_size,
            duration_ms=self.duration_ms if duration_ms is None else duration_ms,
            toroidal=self.toroidal,
        )
        for name, lyr in self.layers.items():
            out.layers[name] = lyr.copy()
        return out

    def composite(
        self,
        include_hidden: bool = False,
        layer_order: Iterable[str] | None = None,
        exclude_layers: Iterable[str] = (),
    ) -> IndexedLayer:
        """Flatten visible layers bottom-to-top into a single IndexedLayer."""
        merged = IndexedLayer(
            name="__composite__",
            width=self.width,
            height=self.height,
            palette_size=self.palette_size,
            toroidal=self.toroidal,
        )
        excluded = set(exclude_layers)
        for lyr in self.ordered_layers(layer_order=layer_order):
            if lyr.name in excluded:
                continue
            if not include_hidden and not lyr.visible:
                continue
            merged.blit(lyr)
        return merged

    def composite_solid(
        self,
        outline_exclude: Iterable[str] = ("fx", "vfx", "glow", "smear", "shadow"),
    ) -> IndexedLayer:
        """Flatten only solid body layers (excluding outlines, top FX, and drop shadows)."""
        exclude_tokens = tuple(t.lower() for t in outline_exclude)
        merged = IndexedLayer(
            name="__solid__",
            width=self.width,
            height=self.height,
            palette_size=self.palette_size,
            toroidal=self.toroidal,
        )
        for lyr in self.ordered_layers():
            if not lyr.visible:
                continue
            low = lyr.name.lower()
            if "outline" in low or any(tok in low for tok in exclude_tokens):
                continue
            merged.blit(lyr)
        return merged


@dataclass
class AnimationTag:
    name: str
    from_frame: int
    to_frame: int
    direction: str = "forward"  # forward | reverse | pingpong
    loop: bool = True


@dataclass
class SliceDef:
    name: str
    x: int
    y: int
    w: int
    h: int
    pivot: tuple[int, int] | None = None
    center_9slice: tuple[int, int, int, int] | None = None  # (cx, cy, cw, ch)


class PixelProject:
    """Top-level locked-dimension pixel art asset container."""

    def __init__(
        self,
        name: str,
        width: int,
        height: int,
        spec: StyleSpec,
        category: str = "icons",
        toroidal: bool = False,
        default_duration_ms: int = 150,
    ) -> None:
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category {category!r}; must be one of {VALID_CATEGORIES}"
            )
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise ValueError(f"Canvas size must be positive integers, got {width!r}x{height!r}")

        self.name = name
        self.category = category
        self._width = width
        self._height = height
        self.spec = spec
        self.toroidal = bool(toroidal or category == "tilesets")
        self.frames: list[Frame] = [
            Frame(
                width=self._width,
                height=self._height,
                palette_size=len(spec.palette),
                duration_ms=default_duration_ms,
                toroidal=self.toroidal,
            )
        ]
        self.tags: list[AnimationTag] = []
        self.slices: list[SliceDef] = []
        self.nine_slice: tuple[int, int, int, int] | None = None  # (left, top, right, bottom)
        self.sheet_columns: int | None = None
        self.split_rows_by_tag: bool = False
        self.metadata: dict[str, object] = {}

        # Sensible default pivot based on asset category
        pivot_mode = spec.defaults_by_type.get(category, {}).get("pivot_mode", "center")
        if pivot_mode == "bottom_center":
            self.pivot: tuple[int, int] = (self._width // 2, self._height - 1)
        elif pivot_mode == "top_left":
            self.pivot = (0, 0)
        else:
            self.pivot = (self._width // 2, self._height // 2)

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def frame(self, idx: int = 0) -> Frame:
        return self.frames[idx]

    def layer(
        self,
        name: str,
        frame_idx: int = 0,
        z_index: int | None = None,
    ) -> IndexedLayer:
        return self.frames[frame_idx].layer(name, z_index=z_index)

    def add_frame(
        self,
        duration_ms: int = 150,
        clone_from: int | None = None,
    ) -> Frame:
        if clone_from is not None:
            fr = self.frames[clone_from].copy(duration_ms=duration_ms)
        else:
            fr = Frame(
                width=self._width,
                height=self._height,
                palette_size=len(self.spec.palette),
                duration_ms=duration_ms,
                toroidal=self.toroidal,
            )
        self.frames.append(fr)
        return fr

    def add_tag(
        self,
        name: str,
        from_frame: int,
        to_frame: int,
        direction: str = "forward",
        loop: bool = True,
    ) -> None:
        if direction not in ("forward", "reverse", "pingpong"):
            raise ValueError(f"Invalid tag direction: {direction!r}")
        if from_frame < 0 or to_frame < from_frame or to_frame >= len(self.frames):
            raise ValueError(
                f"Tag {name!r} frame range [{from_frame}, {to_frame}] invalid for {len(self.frames)} frames."
            )
        self.tags.append(
            AnimationTag(
                name=name,
                from_frame=from_frame,
                to_frame=to_frame,
                direction=direction,
                loop=loop,
            )
        )

    def set_pivot(self, x: int, y: int) -> None:
        self.pivot = (int(x), int(y))

    def set_nine_slice(self, left: int, top: int, right: int, bottom: int) -> None:
        if left < 0 or top < 0 or right < 0 or bottom < 0:
            raise ValueError("9-slice margins must be non-negative.")
        if left + right >= self._width or top + bottom >= self._height:
            raise ValueError(
                f"9-slice margins ({left},{top},{right},{bottom}) exceed canvas {self._width}x{self._height}."
            )
        self.nine_slice = (int(left), int(top), int(right), int(bottom))

    def set_sheet_layout(
        self,
        columns: int | None = None,
        split_rows_by_tag: bool = False,
    ) -> None:
        """Configure multi-frame sprite sheet packing (grid columns or one row per animation tag)."""
        if columns is not None and int(columns) < 1:
            raise ValueError(f"sheet_columns must be >= 1, got {columns!r}")
        self.sheet_columns = int(columns) if columns is not None else None
        self.split_rows_by_tag = bool(split_rows_by_tag)

    def all_layer_names(self) -> list[str]:
        """Collect canonical bottom-to-top ordered layer names across all frames."""
        first_seen: dict[str, int] = {}
        explicit_z: dict[str, int] = {}
        seq = 0
        for fr in self.frames:
            for name, lyr in fr.layers.items():
                if name not in first_seen:
                    first_seen[name] = seq
                    seq += 1
                if lyr.z_index is not None and name not in explicit_z:
                    explicit_z[name] = lyr.z_index
        return sorted(
            first_seen.keys(),
            key=lambda nm: (explicit_z.get(nm, _default_layer_z(nm)), first_seen[nm]),
        )

    def composite_frame(self, frame_idx: int, include_hidden: bool = False) -> IndexedLayer:
        """Flatten a frame using the project's canonical bottom-to-top layer order."""
        return self.frames[frame_idx].composite(
            include_hidden=include_hidden,
            layer_order=self.all_layer_names(),
        )

    def remap_material(
        self,
        mapping: Mapping[str, str],
        reoutline: bool = True,
        outline_exclude: Iterable[str] = ("fx", "vfx", "glow", "shadow"),
    ) -> int:
        """Palette-swap materials across every frame/layer, optionally regenerating outline layers."""
        from .shading import apply_outline

        exclude_tokens = tuple(t.lower() for t in outline_exclude)
        order = self.all_layer_names()
        total = 0
        for fi, fr in enumerate(self.frames):
            outline_layers: list[IndexedLayer] = []
            for lname, lyr in fr.layers.items():
                if reoutline and "outline" in lname.lower():
                    outline_layers.append(lyr)
                else:
                    total += lyr.remap_material(mapping, self.spec)
            if reoutline and outline_layers:
                for ol in outline_layers:
                    ol.clear()
                solid_order = [
                    ln
                    for ln in order
                    if "outline" not in ln.lower() and not any(tok in ln.lower() for tok in exclude_tokens)
                ]
                solid = IndexedLayer(
                    name="__solid__",
                    width=self._width,
                    height=self._height,
                    palette_size=len(self.spec.palette),
                    toroidal=self.toroidal,
                )
                for ln in solid_order:
                    lyr = fr.layers.get(ln)
                    if lyr is not None and lyr.visible:
                        solid.blit(lyr)
                for ol in outline_layers:
                    apply_outline(ol, solid, self.spec)
        return total

    def used_colors(self) -> set[int]:
        colors: set[int] = set()
        order = self.all_layer_names()
        for fr in self.frames:
            colors.update(fr.composite(layer_order=order).used_colors())
        return colors

    def total_clipped_pixels(self) -> int:
        return sum(lyr.clipped_count for fr in self.frames for lyr in fr.layers.values())
