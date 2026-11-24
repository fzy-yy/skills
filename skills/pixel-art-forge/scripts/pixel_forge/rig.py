"""Modular hierarchical character Anchor Rig, PartTransform, and 4-direction animation presets."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from .canvas import Frame, IndexedLayer


@dataclass
class PartTransform:
    """Per-frame transform for a rig part (translation, flip, RotSprite rotation, squash/stretch)."""

    dx: int = 0
    dy: int = 0
    flip_x: bool = False
    flip_y: bool = False
    rotate_deg: float = 0.0
    pivot: tuple[float, float] | None = None
    squash_x: float = 1.0
    squash_y: float = 1.0


PoseValue = tuple[int, int] | PartTransform


@dataclass
class RigPart:
    """One semantic body/equipment part with optional parent binding and rotation pivot."""

    name: str
    layer: IndexedLayer
    base_offset: tuple[int, int] = (0, 0)
    z_order: int = 0
    parent: str | None = None
    pivot: tuple[float, float] | None = None


def _as_transform(val: PoseValue | None) -> PartTransform:
    if val is None:
        return PartTransform()
    if isinstance(val, PartTransform):
        return val
    return PartTransform(dx=int(val[0]), dy=int(val[1]))


def _default_pivot(layer: IndexedLayer) -> tuple[float, float]:
    bb = layer.bbox()
    if bb is not None:
        return ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
    return ((layer.width - 1) / 2.0, (layer.height - 1) / 2.0)


def _transform_point_2d(
    pt: tuple[float, float],
    rp: RigPart,
    tf: PartTransform,
    width: int,
    height: int,
) -> tuple[float, float]:
    """Forward-map a 2D canvas point through one rig node's local flip, squash, rotation, and offset."""
    x, y = float(pt[0]), float(pt[1])
    piv = tf.pivot or rp.pivot or _default_pivot(rp.layer)
    px, py = float(piv[0]), float(piv[1])

    if tf.flip_x:
        x = (width - 1) - x
        px = (width - 1) - px
    if tf.flip_y:
        y = (height - 1) - y
        py = (height - 1) - py

    if abs(tf.squash_x - 1.0) > 1e-4 or abs(tf.squash_y - 1.0) > 1e-4:
        x = px + (x - px) * tf.squash_x
        y = py + (y - py) * tf.squash_y

    if abs(tf.rotate_deg) > 1e-4:
        rad = math.radians(tf.rotate_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        rx = x - px
        ry = y - py
        x = px + rx * cos_a - ry * sin_a
        y = py + rx * sin_a + ry * cos_a

    x += rp.base_offset[0] + tf.dx
    y += rp.base_offset[1] + tf.dy
    return (x, y)


class CharacterRig:
    """Modular hierarchical anchor rig keeping character proportions & pivot 100% locked across frames."""

    def __init__(self, width: int, height: int, palette_size: int) -> None:
        self.width = width
        self.height = height
        self.palette_size = palette_size
        self.parts: dict[str, RigPart] = {}

    def add_part(
        self,
        name: str,
        z_order: int = 0,
        base_offset: tuple[int, int] = (0, 0),
        layer: IndexedLayer | None = None,
        parent: str | None = None,
        pivot: tuple[float, float] | None = None,
    ) -> IndexedLayer:
        if parent == name:
            raise ValueError(f"Rig part {name!r} cannot be its own parent.")
        lyr = layer if layer is not None else IndexedLayer(name, self.width, self.height, self.palette_size)
        self.parts[name] = RigPart(
            name=name,
            layer=lyr,
            base_offset=base_offset,
            z_order=z_order,
            parent=parent,
            pivot=pivot,
        )
        return lyr

    def part(self, name: str) -> IndexedLayer:
        return self.parts[name].layer

    def _ancestor_chain(self, name: str) -> list[RigPart]:
        """Return [self_part, parent_part, ..., root_part], validating parent existence & cycles."""
        chain: list[RigPart] = []
        visiting: set[str] = set()
        curr: str | None = name
        while curr is not None:
            if curr in visiting:
                raise ValueError(f"Cyclic parent chain detected in CharacterRig involving {curr!r}.")
            if curr not in self.parts:
                raise KeyError(f"Rig part {name!r} references unknown parent {curr!r}.")
            visiting.add(curr)
            rp = self.parts[curr]
            chain.append(rp)
            curr = rp.parent
        return chain

    def render_to_frame(
        self,
        frame: Frame,
        pose: Mapping[str, PoseValue] | None = None,
        overrides: Mapping[str, IndexedLayer] | None = None,
        hidden: Sequence[str] = (),
        global_offset: tuple[int, int] = (0, 0),
    ) -> None:
        """Render all rig parts into semantic layers on `frame` with full hierarchical FK transforms.

        Parent translations, flips, squash/stretch, and joint rotations propagate cleanly to child parts
        while compositing into at most one squash + one RotSprite pass per part (zero double-resampling).
        """
        pose = pose or {}
        overrides = overrides or {}
        hidden_set = set(hidden)
        gx, gy = global_offset

        ordered = sorted(self.parts.values(), key=lambda p: p.z_order)
        for rp in ordered:
            if rp.name in hidden_set:
                continue
            src = overrides.get(rp.name, rp.layer)
            chain = self._ancestor_chain(rp.name)
            tfs = [_as_transform(pose.get(node.name)) for node in chain]

            # Fast exact integer path when no node in the chain flips, squashes, or rotates
            pure_translation = all(
                not tf.flip_x
                and not tf.flip_y
                and abs(tf.squash_x - 1.0) <= 1e-4
                and abs(tf.squash_y - 1.0) <= 1e-4
                and abs(tf.rotate_deg) <= 1e-4
                for tf in tfs
            )
            target = frame.layer(rp.name)
            if pure_translation:
                ox = sum(node.base_offset[0] + tf.dx for node, tf in zip(chain, tfs))
                oy = sum(node.base_offset[1] + tf.dy for node, tf in zip(chain, tfs))
                target.blit(src, ox=ox + gx, oy=oy + gy)
                continue

            # Full hierarchical forward kinematics: map child rest pivot through self -> ... -> root
            tf_self = tfs[0]
            rest_piv = tf_self.pivot or rp.pivot or _default_pivot(src)
            world_piv = rest_piv
            eff_flip_x = False
            eff_flip_y = False
            eff_sx = 1.0
            eff_sy = 1.0
            eff_rot = 0.0

            for node, tf in zip(chain, tfs):
                world_piv = _transform_point_2d(world_piv, node, tf, self.width, self.height)
                if tf.flip_x:
                    eff_flip_x = not eff_flip_x
                    eff_rot = -eff_rot
                if tf.flip_y:
                    eff_flip_y = not eff_flip_y
                    eff_rot = -eff_rot
                eff_sx *= tf.squash_x
                eff_sy *= tf.squash_y
                eff_rot += tf.rotate_deg

            transformed = src
            piv_after_flip = [float(rest_piv[0]), float(rest_piv[1])]
            if eff_flip_x:
                transformed = transformed.flip_x()
                piv_after_flip[0] = (self.width - 1) - piv_after_flip[0]
            if eff_flip_y:
                transformed = transformed.flip_y()
                piv_after_flip[1] = (self.height - 1) - piv_after_flip[1]

            piv_tuple = (piv_after_flip[0], piv_after_flip[1])
            if abs(eff_sx - 1.0) > 1e-4 or abs(eff_sy - 1.0) > 1e-4:
                transformed = transformed.squash_stretch(eff_sx, eff_sy, anchor=piv_tuple)
            if abs(eff_rot) > 1e-4:
                transformed = transformed.rotate(eff_rot, pivot=piv_tuple)

            ox = round(world_piv[0] - piv_tuple[0])
            oy = round(world_piv[1] - piv_tuple[1])
            target.blit(transformed, ox=ox + gx, oy=oy + gy)


def idle_cycle_poses(
    frames: int = 4,
    duration_ms: int = 190,
    hierarchical: bool = True,
) -> list[tuple[dict[str, PoseValue], int]]:
    """Generate a subtle breathing idle animation preset.

    When `hierarchical=True`, assumes head/arms/weapon/cape are parented to `torso`,
    so moving `torso` smoothly carries the upper body while legs stay anchored.
    """
    if frames <= 2:
        raw = [
            {"torso": (0, 0)},
            {"torso": (0, 1)},
        ]
    else:
        raw = [
            {"torso": (0, 0), "cape": (0, 0)},
            {"torso": (0, 1), "cape": (0, 0)},
            {"torso": (0, 1), "cape": (1, 0)},
            {"torso": (0, 0), "cape": (0, 0)},
        ]
    if not hierarchical:
        expanded: list[dict[str, PoseValue]] = []
        for p in raw:
            ty = p["torso"][1] if isinstance(p["torso"], tuple) else p["torso"].dy
            cx = p.get("cape", (0, 0))
            cdx = cx[0] if isinstance(cx, tuple) else cx.dx
            expanded.append(
                {
                    "torso": (0, ty),
                    "head": (0, ty),
                    "front_arm": (0, ty),
                    "back_arm": (0, ty),
                    "shield": (0, ty),
                    "weapon": (0, ty),
                    "cape": (cdx, ty),
                }
            )
        raw = expanded
    return [(p, duration_ms) for p in raw[: max(1, frames)]]


def walk_cycle_poses(
    direction: str = "down",
    frames: int = 4,
    duration_ms: int = 130,
) -> list[tuple[dict[str, PoseValue], int]]:
    """Generate 4-direction RPG / side-scroller walk cycle pose presets ('down', 'up', 'left', 'right').

    Designed for hierarchical rigs where head/arms/weapon/cape follow `torso`, while legs stay
    independent of `torso` so grounded feet never drift vertically.
    """
    d = direction.lower()
    if d not in ("down", "up", "left", "right"):
        raise ValueError(f"Unsupported walk direction {direction!r}; use 'down', 'up', 'left', or 'right'.")

    if d in ("down", "up"):
        cape_sway = 1 if d == "down" else -1
        poses: list[dict[str, PoseValue]] = [
            {
                "left_leg": (0, -1), "right_leg": (0, 0),
                "front_leg": (0, -1), "back_leg": (0, 0),
                "torso": (0, 0), "front_arm": (0, 1), "back_arm": (0, -1),
                "cape": (-cape_sway, 0),
            },
            {
                "left_leg": (0, 0), "right_leg": (0, -1),
                "front_leg": (0, 0), "back_leg": (0, -1),
                "torso": (0, -1), "front_arm": (0, 0), "back_arm": (0, 0),
                "cape": (0, 0),
            },
            {
                "left_leg": (0, 0), "right_leg": (0, -1),
                "front_leg": (0, 0), "back_leg": (0, -1),
                "torso": (0, 0), "front_arm": (0, -1), "back_arm": (0, 1),
                "cape": (cape_sway, 0),
            },
            {
                "left_leg": (0, -1), "right_leg": (0, 0),
                "front_leg": (0, -1), "back_leg": (0, 0),
                "torso": (0, -1), "front_arm": (0, 0), "back_arm": (0, 0),
                "cape": (0, 0),
            },
        ]
    else:
        facing = 1 if d == "right" else -1
        poses = [
            {
                "front_leg": (2 * facing, 0), "back_leg": (-2 * facing, 0),
                "left_leg": (-2 * facing, 0), "right_leg": (2 * facing, 0),
                "torso": (0, 0),
                "front_arm": (-1 * facing, 0), "back_arm": (1 * facing, 0),
                "cape": (-1 * facing, 0),
            },
            {
                "front_leg": (0, -1), "back_leg": (0, 0),
                "left_leg": (0, 0), "right_leg": (0, -1),
                "torso": (0, -1),
                "front_arm": (0, 0), "back_arm": (0, 0),
                "cape": (-1 * facing, 0),
            },
            {
                "front_leg": (-2 * facing, 0), "back_leg": (2 * facing, 0),
                "left_leg": (2 * facing, 0), "right_leg": (-2 * facing, 0),
                "torso": (0, 0),
                "front_arm": (1 * facing, 0), "back_arm": (-1 * facing, 0),
                "cape": (0, 0),
            },
            {
                "front_leg": (0, 0), "back_leg": (0, -1),
                "left_leg": (0, -1), "right_leg": (0, 0),
                "torso": (0, -1),
                "front_arm": (0, 0), "back_arm": (0, 0),
                "cape": (-1 * facing, 0),
            },
        ]

    if frames == 2:
        poses = [poses[0], poses[2]]
    return [(p, duration_ms) for p in poses[: max(1, frames)]]


def attack_swing_poses(
    direction: str = "right",
    frames: int = 4,
    hierarchical: bool = True,
) -> list[tuple[dict[str, PoseValue], int]]:
    """Generate an anticipation -> slash -> follow-through -> recovery attack pose sequence.

    When `hierarchical=True` (default), offsets & rotations are calibrated for `torso -> front_arm -> weapon`
    parenting so weapon grip stays tightly coupled to the hand without triple-accumulating translation.
    """
    facing = -1 if direction.lower() == "left" else 1
    if hierarchical:
        seq: list[tuple[dict[str, PoseValue], int]] = [
            # 0: Anticipation wind-up
            (
                {
                    "torso": (-1 * facing, 0),
                    "front_arm": PartTransform(dx=0, dy=-1, rotate_deg=-15.0 * facing),
                    "weapon": PartTransform(dx=0, dy=0, rotate_deg=-25.0 * facing),
                },
                120,
            ),
            # 1: Active impact slash
            (
                {
                    "torso": (1 * facing, 1),
                    "front_arm": PartTransform(dx=1 * facing, dy=0, rotate_deg=25.0 * facing),
                    "weapon": PartTransform(dx=0, dy=0, rotate_deg=45.0 * facing),
                },
                75,
            ),
            # 2: Follow-through settle
            (
                {
                    "torso": (1 * facing, 0),
                    "front_arm": PartTransform(dx=1 * facing, dy=1, rotate_deg=15.0 * facing),
                    "weapon": PartTransform(dx=0, dy=0, rotate_deg=30.0 * facing),
                },
                95,
            ),
            # 3: Recovery to neutral
            (
                {
                    "torso": (0, 0),
                    "front_arm": PartTransform(dx=0, dy=0, rotate_deg=0.0),
                    "weapon": PartTransform(dx=0, dy=0, rotate_deg=0.0),
                },
                110,
            ),
        ]
    else:
        seq = [
            (
                {
                    "torso": (-1 * facing, 0),
                    "front_arm": (-1 * facing, -1),
                    "weapon": PartTransform(dx=-1 * facing, dy=-1, rotate_deg=-35.0 * facing),
                },
                120,
            ),
            (
                {
                    "torso": (1 * facing, 1),
                    "front_arm": (2 * facing, 0),
                    "weapon": PartTransform(dx=2 * facing, dy=1, rotate_deg=65.0 * facing),
                },
                75,
            ),
            (
                {
                    "torso": (1 * facing, 0),
                    "front_arm": (1 * facing, 1),
                    "weapon": PartTransform(dx=1 * facing, dy=1, rotate_deg=45.0 * facing),
                },
                95,
            ),
            (
                {
                    "torso": (0, 0),
                    "front_arm": (0, 0),
                    "weapon": PartTransform(dx=0, dy=0, rotate_deg=0.0),
                },
                110,
            ),
        ]
    return seq[: max(1, min(frames, len(seq)))]


def draw_smear_arc(
    layer: IndexedLayer,
    cx: float,
    cy: float,
    r_inner: float,
    r_outer: float,
    start_deg: float,
    end_deg: float,
    ramp: Sequence[int],
    material: str | None = None,
) -> None:
    """Draw a pixel-art motion smear arc (e.g. sword slash trail) shaded along the sweep."""
    if not ramp:
        return
    min_x = max(0, math.floor(cx - r_outer - 1))
    max_x = min(layer.width - 1, math.ceil(cx + r_outer + 1))
    min_y = max(0, math.floor(cy - r_outer - 1))
    max_y = min(layer.height - 1, math.ceil(cy + r_outer + 1))

    span = end_deg - start_deg
    if abs(span) < 1e-3:
        return

    for py in range(min_y, max_y + 1):
        for px in range(min_x, max_x + 1):
            dx = px - cx
            dy = py - cy
            r = math.hypot(dx, dy)
            if not (r_inner <= r <= r_outer):
                continue
            ang = math.degrees(math.atan2(dy, dx))
            rel = (ang - start_deg) % 360.0
            if span > 0:
                if rel > span:
                    continue
                t = rel / span
            else:
                rel_neg = rel - 360.0 if rel > 0 else rel
                if rel_neg < span:
                    continue
                t = rel_neg / span
            idx = max(0, min(len(ramp) - 1, round(t * (len(ramp) - 1))))
            layer.set_px(px, py, ramp[idx], material)
