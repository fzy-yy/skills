"""Exact-palette pixel-art animated GIF exporter (zero color drift, clean transparent disposal)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..canvas import TRANSPARENT, PixelProject


def _build_gif_palette_bytes(project: PixelProject) -> list[int]:
    """Build 768-byte RGB palette table with slot 0 reserved for transparency."""
    table: list[int] = [0, 0, 0]  # slot 0 = transparent placeholder
    for r, g, b in project.spec.palette.colors:
        table.extend((r, g, b))
    # Pad to 256 entries (768 ints)
    remaining = 256 - (len(table) // 3)
    if remaining > 0:
        table.extend([0, 0, 0] * remaining)
    return table[:768]


def export_gif(project: PixelProject, out_dir: str | Path) -> Path:
    """Export an animated GIF using the exact locked project palette and per-frame durations."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    out_path = out / f"{project.name}.gif"

    w, h = project.width, project.height
    pal_bytes = _build_gif_palette_bytes(project)

    pil_frames: list[Image.Image] = []
    durations: list[int] = []
    for idx, fr in enumerate(project.frames):
        comp = project.composite_frame(idx)
        im = Image.new("P", (w, h), 0)
        im.putpalette(pal_bytes)
        raw = bytearray(w * h)
        pos = 0
        for y in range(h):
            row = comp.grid[y]
            for x in range(w):
                c = row[x]
                raw[pos] = 0 if c == TRANSPARENT else (c + 1)
                pos += 1
        im.frombytes(bytes(raw))
        pil_frames.append(im)
        durations.append(max(20, int(fr.duration_ms)))

    pil_frames[0].save(
        out_path,
        format="GIF",
        save_all=True,
        append_images=pil_frames[1:],
        duration=durations,
        loop=0,
        transparency=0,
        disposal=2,  # Restore to background (transparent) between frames — zero ghosting!
        optimize=False,
    )
    return out_path
