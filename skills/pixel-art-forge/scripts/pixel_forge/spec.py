"""StyleSpec management, material ramps, and resolution detail budgets."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .palette import (
    SKILL_ROOT,
    Palette,
    generate_hue_shifted_ramp,
    load_palette,
)

SPECS_DIR = SKILL_ROOT / "assets" / "specs"
CORE_MATERIALS: tuple[str, ...] = (
    "dark_ink",
    "steel",
    "stone",
    "gold",
    "wood",
    "leather",
    "skin",
    "cloth_red",
    "cloth_blue",
    "fire",
    "grass",
    "water",
    "magic",
)

VALID_SHADING_PROFILES = ("matte", "metallic", "gem", "emissive")


def infer_material_profile(material_name: str) -> str:
    """Infer default pixel-art reflectance profile ('matte', 'metallic', 'gem', 'emissive') from material name."""
    m = material_name.lower()
    if any(tok in m for tok in ("steel", "gold", "silver", "bronze", "iron", "metal", "brass", "copper", "chrome")):
        return "metallic"
    if any(tok in m for tok in ("fire", "flame", "lava", "plasma", "ember", "glow")):
        return "emissive"
    if any(tok in m for tok in ("gem", "magic", "water", "ice", "crystal", "glass", "ruby", "emerald", "sapphire", "amethyst")):
        return "gem"
    return "matte"


@dataclass(frozen=True)
class ResolutionBudget:
    """Art-direction guidance tied to the target logical canvas size."""

    tier: str
    width: int
    height: int
    shades_per_material: tuple[int, int]
    safe_margin: int
    outline_recommended: str
    dither_allowed: bool
    guidance: str


def resolution_budget(width: int, height: int) -> ResolutionBudget:
    """Return pixel-art detail budget tailored to the exact target dimensions."""
    dim = max(width, height)
    if dim <= 16:
        return ResolutionBudget(
            tier="micro_8_16",
            width=width,
            height=height,
            shades_per_material=(2, 3),
            safe_margin=1 if dim >= 12 else 0,
            outline_recommended="sel_out or none (avoid thick inner lines)",
            dither_allowed=False,
            guidance="Prioritize bold iconic silhouette; 2-3 shades max per material; omit tiny ornaments.",
        )
    if dim <= 36:
        return ResolutionBudget(
            tier="classic_24_32",
            width=width,
            height=height,
            shades_per_material=(3, 4),
            safe_margin=1,
            outline_recommended="sel_out (1px)",
            dither_allowed=False,
            guidance="Classic 16-bit clarity; clear major parts, 3-4 shades per ramp, clean 1px Sel-Out.",
        )
    if dim <= 72:
        return ResolutionBudget(
            tier="hibit_48_64",
            width=width,
            height=height,
            shades_per_material=(4, 5),
            safe_margin=2,
            outline_recommended="sel_out (1px with lit-side brightening)",
            dither_allowed=True,
            guidance="Hi-bit detail; 4-5 shades, secondary details (buckles/gems/texture), selective Bayer dithering.",
        )
    return ResolutionBudget(
        tier="large_72_plus",
        width=width,
        height=height,
        shades_per_material=(4, 6),
        safe_margin=2,
        outline_recommended="sel_out (1px)",
        dither_allowed=True,
        guidance="Large sprite/portrait; group shading into large clean color clusters and avoid pixel noise.",
    )


DEFAULT_BY_TYPE: dict[str, dict[str, Any]] = {
    "icons": {"size": [32, 32], "padding": 1, "pivot_mode": "center"},
    "characters": {"size": [32, 32], "padding": 1, "pivot_mode": "bottom_center"},
    "tilesets": {"size": [16, 16], "padding": 0, "pivot_mode": "top_left"},
    "ui": {"size": [48, 48], "padding": 0, "pivot_mode": "top_left"},
}


@dataclass
class StyleSpec:
    """Locked project-level visual contract enforcing style and palette consistency."""

    project_name: str
    palette: Palette
    materials: dict[str, list[int]]
    light_dir: tuple[float, float] = (-1.0, -1.0)
    outline: dict[str, Any] = field(
        default_factory=lambda: {
            "mode": "sel_out",
            "color_index": 0,
            "lit_boost": True,
            "corners": "round",
        }
    )
    perspective: str = "topdown_3_4"
    dither: str = "none"
    pixels_per_unit: int = 32
    max_colors: int | None = None
    material_profiles: dict[str, str] = field(default_factory=dict)
    defaults_by_type: dict[str, dict[str, Any]] = field(
        default_factory=lambda: json.loads(json.dumps(DEFAULT_BY_TYPE))
    )

    def __post_init__(self) -> None:
        # Normalize light direction
        lx, ly = float(self.light_dir[0]), float(self.light_dir[1])
        mag = math.hypot(lx, ly)
        self.light_dir = (lx / mag, ly / mag) if mag > 1e-6 else (-0.7071, -0.7071)

        # Validate every material ramp points strictly to valid palette indices
        n = len(self.palette)
        for mat_name, ramp in self.materials.items():
            if not ramp:
                raise ValueError(f"Material ramp {mat_name!r} cannot be empty.")
            for idx in ramp:
                if not isinstance(idx, int) or not (0 <= idx < n):
                    raise ValueError(
                        f"Material {mat_name!r} contains invalid palette index {idx} "
                        f"(palette size is {n})."
                    )

        # Validate outline color index
        oc = int(self.outline.get("color_index", self.palette.darkest_index()))
        if not (0 <= oc < n):
            oc = self.palette.darkest_index()
        self.outline["color_index"] = oc
        self.outline.setdefault("mode", "sel_out")
        self.outline.setdefault("lit_boost", True)
        self.outline.setdefault("corners", "round")

        for m_name, prof in list(self.material_profiles.items()):
            if prof not in VALID_SHADING_PROFILES:
                raise ValueError(
                    f"Invalid shading profile {prof!r} for material {m_name!r}; "
                    f"expected one of {VALID_SHADING_PROFILES}."
                )

    def material_profile(self, material: str) -> str:
        """Return configured or inferred reflectance profile for `material`."""
        return self.material_profiles.get(material, infer_material_profile(material))

    def ramp(self, material: str) -> list[int]:
        """Return palette index ramp (darkest -> brightest) for a material."""
        if material not in self.materials:
            avail = ", ".join(sorted(self.materials.keys()))
            raise KeyError(
                f"Unknown material {material!r}. Available materials: {avail}"
            )
        return list(self.materials[material])

    def color(self, material: str, shade: int = 2) -> int:
        """Get a clamped palette index from a material ramp (0=darkest, -1=brightest)."""
        r = self.ramp(material)
        if shade < 0:
            idx = max(0, len(r) + shade)
        else:
            idx = min(len(r) - 1, shade)
        return r[idx]

    def register_material_from_hex(
        self,
        name: str,
        base_hex: str,
        steps: int = 4,
        lock_to_palette: bool = True,
    ) -> list[int]:
        """Create a hue-shifted material ramp, either snapped to palette or appended."""
        hex_ramp = generate_hue_shifted_ramp(base_hex, steps=steps)
        if lock_to_palette:
            indices = self.palette.match_ramp_distinct(hex_ramp, min_steps=min(2, steps))
        else:
            indices = [self.palette.add_color(h) for h in hex_ramp]
        self.materials[name] = indices
        return list(indices)

    def remap_to_palette(self, new_palette: Palette) -> None:
        """Remap all material ramps onto `new_palette` while preserving distinct shade ordering."""
        old_pal = self.palette
        remapped: dict[str, list[int]] = {}
        for mat, ramp in self.materials.items():
            old_rgbs = [old_pal.rgb_at(i) for i in ramp]
            remapped[mat] = new_palette.match_ramp_distinct(old_rgbs, min_steps=min(2, len(ramp)))
        self.palette = new_palette
        self.materials = remapped
        self.outline["color_index"] = new_palette.darkest_index()

    def to_dict(self) -> dict[str, Any]:
        out = {
            "project_name": self.project_name,
            "palette": self.palette.to_dict(),
            "materials": self.materials,
            "light_dir": [round(self.light_dir[0], 4), round(self.light_dir[1], 4)],
            "outline": self.outline,
            "perspective": self.perspective,
            "dither": self.dither,
            "pixels_per_unit": self.pixels_per_unit,
            "max_colors": self.max_colors,
            "defaults_by_type": self.defaults_by_type,
        }
        if self.material_profiles:
            out["material_profiles"] = dict(self.material_profiles)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyleSpec":
        pal_data = data["palette"]
        if isinstance(pal_data, str):
            palette = load_palette(pal_data)
        else:
            palette = Palette.from_dict(pal_data)

        raw_max = data.get("max_colors")
        return cls(
            project_name=data.get("project_name", "pixel_project"),
            palette=palette,
            materials=data["materials"],
            light_dir=tuple(data.get("light_dir", (-1.0, -1.0))),
            outline=dict(data.get("outline", {})),
            perspective=data.get("perspective", "topdown_3_4"),
            dither=data.get("dither", "none"),
            pixels_per_unit=int(data.get("pixels_per_unit", 32)),
            max_colors=int(raw_max) if raw_max is not None else None,
            material_profiles=dict(data.get("material_profiles", {})),
            defaults_by_type=data.get(
                "defaults_by_type", json.loads(json.dumps(DEFAULT_BY_TYPE))
            ),
        )


def list_spec_presets() -> list[str]:
    """List built-in StyleSpec preset names."""
    if not SPECS_DIR.exists():
        return []
    return sorted(p.stem for p in SPECS_DIR.glob("*.json"))


def load_spec(path: str | Path) -> StyleSpec:
    """Load a StyleSpec from a JSON file path or built-in preset name."""
    p = Path(path)
    if not p.exists():
        p = SPECS_DIR / f"{path}.json"
    if not p.exists():
        avail = ", ".join(list_spec_presets())
        raise FileNotFoundError(
            f"StyleSpec {path!r} not found. Built-in presets: {avail}"
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    return StyleSpec.from_dict(data)


def build_custom_palette_spec(
    base_spec: StyleSpec,
    color_entries: list[str],
    palette_name: str = "custom_theme",
    steps_per_color: int = 4,
) -> StyleSpec:
    """Build a custom hue-shifted palette from user base colors and remap `base_spec` onto it.

    Each entry in `color_entries` may be `'#rrggbb'` or `'material_name:#rrggbb'`.
    """
    if not color_entries:
        raise ValueError("color_entries cannot be empty.")

    # Always include a deep cool ink shadow and a crisp neutral highlight anchor
    seed_colors: list[str] = ["#151321", "#f2f4f8"]
    custom_ramps: dict[str, list[str]] = {}

    # Respect max_colors budget if already set on base_spec
    steps = max(2, int(steps_per_color))
    if base_spec.max_colors is not None:
        avail = max(2, base_spec.max_colors - 2)
        steps = max(2, min(steps, avail // max(1, len(color_entries))))

    for idx, raw in enumerate(color_entries):
        item = raw.strip()
        if not item:
            continue
        if ":" in item:
            mat_name, hex_val = item.split(":", 1)
            mat_name = mat_name.strip()
            hex_val = hex_val.strip()
        else:
            mat_name = f"theme_{idx + 1}"
            hex_val = item
        ramp_hex = generate_hue_shifted_ramp(hex_val, steps=steps)
        custom_ramps[mat_name] = ramp_hex
        seed_colors.extend(ramp_hex)

    new_pal = Palette(seed_colors, name=palette_name)
    base_spec.remap_to_palette(new_pal)
    for mat_name, ramp_hex in custom_ramps.items():
        base_spec.materials[mat_name] = new_pal.match_ramp_distinct(ramp_hex, min_steps=min(2, steps))
    return base_spec


def save_spec(spec: StyleSpec, path: str | Path) -> Path:
    """Write a StyleSpec JSON file to disk."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(spec.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p
