"""Palette management, OKLab perceptual color distance, and Hue-Shifting ramp generation."""

from __future__ import annotations

import colorsys
import json
import math
from pathlib import Path
from typing import Iterable, Sequence

RGB = tuple[int, int, int]

PACKAGE_DIR = Path(__file__).resolve().parent
SKILL_ROOT = PACKAGE_DIR.parent.parent
PALETTES_DIR = SKILL_ROOT / "assets" / "palettes"


def hex_to_rgb(hex_str: str) -> RGB:
    """Parse '#RRGGBB' or 'RRGGBB' into an (R, G, B) tuple."""
    s = hex_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"Invalid hex color: {hex_str!r}")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def rgb_to_hex(rgb: RGB) -> str:
    """Convert an (R, G, B) tuple to lowercase '#rrggbb'."""
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_oklab(rgb: RGB) -> tuple[float, float, float]:
    """Convert 8-bit sRGB to perceptual OKLab (L, a, b)."""
    r = _srgb_to_linear(rgb[0] / 255.0)
    g = _srgb_to_linear(rgb[1] / 255.0)
    b = _srgb_to_linear(rgb[2] / 255.0)

    l_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m_ = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l_c = math.copysign(abs(l_) ** (1.0 / 3.0), l_)
    m_c = math.copysign(abs(m_) ** (1.0 / 3.0), m_)
    s_c = math.copysign(abs(s_) ** (1.0 / 3.0), s_)

    L = 0.2104542553 * l_c + 0.7936177850 * m_c - 0.0040720468 * s_c
    a = 1.9779984951 * l_c - 2.4285922050 * m_c + 0.4505937099 * s_c
    b_val = 0.0259040371 * l_c + 0.7827717662 * m_c - 0.8086757660 * s_c
    return (L, a, b_val)


def oklab_distance(c1: RGB, c2: RGB) -> float:
    """Perceptual Euclidean distance in OKLab color space."""
    l1, a1, b1 = rgb_to_oklab(c1)
    l2, a2, b2 = rgb_to_oklab(c2)
    return math.sqrt((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2)


def luminance(rgb: RGB) -> float:
    """Perceptual lightness L in OKLab (0.0 .. 1.0)."""
    return rgb_to_oklab(rgb)[0]


def generate_hue_shifted_ramp(
    base_hex: str,
    steps: int = 4,
    shadow_hue_target: float = 250.0,
    highlight_hue_target: float = 52.0,
    hue_shift_strength: float = 0.35,
) -> list[str]:
    """Generate a pixel-art material ramp with natural Hue-Shifting.

    Shadows shift slightly cooler (toward deep blue/purple) and slightly higher saturation;
    highlights shift slightly warmer (toward sunlit yellow) and lighter.
    Returns hex strings ordered from darkest (index 0) to brightest (index -1).
    """
    if steps < 2:
        return [rgb_to_hex(hex_to_rgb(base_hex))]

    r, g, b = hex_to_rgb(base_hex)
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    h_deg = h * 360.0

    def _lerp_hue(src: float, dst: float, t: float) -> float:
        diff = ((dst - src + 540.0) % 360.0) - 180.0
        return (src + diff * t) % 360.0

    # Place base color slightly above middle so shadows have rich depth
    base_pos = max(1, (steps - 1) // 2)
    ramp: list[str] = []

    for i in range(steps):
        if i == base_pos:
            ramp.append(rgb_to_hex((r, g, b)))
            continue

        if i < base_pos:
            # Darkening toward shadow
            t = (base_pos - i) / max(1, base_pos)
            new_l = max(0.08, l * (1.0 - 0.68 * t))
            new_s = min(0.95, s + 0.14 * t * (1.0 - s * 0.5)) if s > 0.04 else min(0.28, s + 0.18 * t)
            new_h = _lerp_hue(h_deg, shadow_hue_target, hue_shift_strength * t)
        else:
            # Brightening toward highlight
            t = (i - base_pos) / max(1, (steps - 1 - base_pos))
            new_l = min(0.93, l + (0.93 - l) * (0.68 * t))
            new_s = max(0.08, s * (1.0 - 0.22 * t)) if s > 0.05 else s
            new_h = _lerp_hue(h_deg, highlight_hue_target, hue_shift_strength * t)

        nr, ng, nb = colorsys.hls_to_rgb(new_h / 360.0, new_l, new_s)
        ramp.append(rgb_to_hex((round(nr * 255), round(ng * 255), round(nb * 255))))

    return ramp


class Palette:
    """Strictly indexed opaque color palette (indices 0..N-1; max 255 colors)."""

    MAX_COLORS = 255  # Reserve slot 0 in indexed .aseprite for transparency

    def __init__(self, colors: Sequence[str | RGB], name: str = "custom") -> None:
        self.name = name
        self._colors: list[RGB] = []
        self._oklab_cache: list[tuple[float, float, float]] = []
        for c in colors:
            rgb = hex_to_rgb(c) if isinstance(c, str) else (int(c[0]), int(c[1]), int(c[2]))
            self.add_color(rgb)
        if not self._colors:
            raise ValueError("Palette must contain at least one color.")

    def __len__(self) -> int:
        return len(self._colors)

    @property
    def colors(self) -> list[RGB]:
        return list(self._colors)

    @property
    def hex_colors(self) -> list[str]:
        return [rgb_to_hex(c) for c in self._colors]

    def rgb_at(self, idx: int) -> RGB:
        if not (0 <= idx < len(self._colors)):
            raise IndexError(f"Palette index {idx} out of range [0, {len(self._colors) - 1}]")
        return self._colors[idx]

    def hex_at(self, idx: int) -> str:
        return rgb_to_hex(self.rgb_at(idx))

    def add_color(self, color: str | RGB) -> int:
        rgb = hex_to_rgb(color) if isinstance(color, str) else (int(color[0]), int(color[1]), int(color[2]))
        if rgb in self._colors:
            return self._colors.index(rgb)
        if len(self._colors) >= self.MAX_COLORS:
            raise ValueError(f"Palette cannot exceed {self.MAX_COLORS} opaque colors.")
        self._colors.append(rgb)
        self._oklab_cache.append(rgb_to_oklab(rgb))
        return len(self._colors) - 1

    def nearest(self, color: str | RGB) -> int:
        """Find nearest palette index using OKLab perceptual distance."""
        rgb = hex_to_rgb(color) if isinstance(color, str) else color
        l1, a1, b1 = rgb_to_oklab(rgb)
        best_idx = 0
        best_dist = float("inf")
        for idx, (l2, a2, b2) in enumerate(self._oklab_cache):
            d = (l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2
            if d < best_dist:
                best_dist = d
                best_idx = idx
        return best_idx

    def darkest_index(self) -> int:
        """Return index of the perceptually darkest color in the palette."""
        return min(range(len(self._colors)), key=lambda i: self._oklab_cache[i][0])

    def brightest_index(self) -> int:
        """Return index of the perceptually brightest color in the palette."""
        return max(range(len(self._colors)), key=lambda i: self._oklab_cache[i][0])

    def match_ramp(self, hex_ramp: Iterable[str]) -> list[int]:
        """Map a sequence of hex colors onto the nearest indices in this palette."""
        return [self.nearest(h) for h in hex_ramp]

    def match_ramp_distinct(
        self,
        colors: Sequence[str | RGB],
        min_steps: int = 2,
        max_fallback_dist: float = 0.28,
    ) -> list[int]:
        """Map a color ramp onto distinct, luminance-sorted palette indices without shade collapse."""
        if not colors:
            return []
        targets = [hex_to_rgb(c) if isinstance(c, str) else c for c in colors]
        target_labs = [rgb_to_oklab(rgb) for rgb in targets]
        desired = min(len(targets), len(self._colors))

        chosen: list[int] = []
        chosen_set: set[int] = set()

        # Pass 1: pick the nearest unique color for each target shade
        for lab in target_labs:
            idx = min(
                range(len(self._oklab_cache)),
                key=lambda i: (
                    (lab[0] - self._oklab_cache[i][0]) ** 2
                    + (lab[1] - self._oklab_cache[i][1]) ** 2
                    + (lab[2] - self._oklab_cache[i][2]) ** 2
                ),
            )
            if idx not in chosen_set:
                chosen.append(idx)
                chosen_set.add(idx)

        # Pass 2: if duplicates collapsed the ramp, greedily fill remaining slots with closest unused colors
        min_needed = min(max(1, min_steps), len(self._colors))
        if len(chosen) < desired:
            for lab in target_labs:
                if len(chosen) >= desired:
                    break
                best_idx = -1
                best_dist = float("inf")
                for i, plab in enumerate(self._oklab_cache):
                    if i in chosen_set:
                        continue
                    d = math.sqrt(
                        (lab[0] - plab[0]) ** 2
                        + (lab[1] - plab[1]) ** 2
                        + (lab[2] - plab[2]) ** 2
                    )
                    if d < best_dist:
                        best_dist = d
                        best_idx = i
                if best_idx != -1 and (best_dist <= max_fallback_dist or len(chosen) < min_needed):
                    chosen.append(best_idx)
                    chosen_set.add(best_idx)

        # Sort strictly darkest -> brightest by OKLab perceptual lightness L
        chosen.sort(key=lambda i: self._oklab_cache[i][0])
        return chosen

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "colors": self.hex_colors,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Palette":
        return cls(colors=data["colors"], name=data.get("name", "custom"))


def list_palettes() -> list[str]:
    """List available built-in palette preset names."""
    if not PALETTES_DIR.exists():
        return []
    return sorted(p.stem for p in PALETTES_DIR.glob("*.json"))


def load_palette(name_or_path: str | Path) -> Palette:
    """Load a built-in palette by name or from a JSON file path."""
    p = Path(name_or_path)
    if not p.exists():
        p = PALETTES_DIR / f"{name_or_path}.json"
    if not p.exists():
        available = ", ".join(list_palettes())
        raise FileNotFoundError(
            f"Palette {name_or_path!r} not found. Available presets: {available}"
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    return Palette.from_dict(data)
