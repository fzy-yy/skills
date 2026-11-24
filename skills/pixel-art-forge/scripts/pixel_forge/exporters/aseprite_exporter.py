"""Pure-Python native Aseprite (.aseprite / .ase) binary encoder.

Implements the official Aseprite binary specification using Python stdlib (`struct` + `zlib`):
  - Indexed 8-bit color depth (slot 0 = transparent, slots 1..N = locked project palette)
  - Palette chunk (0x2019) + Old Palette chunk (0x0004)
  - Layer chunks (0x2004) preserving semantic layers bottom-to-top
  - Compressed Image Cel chunks (0x2005) per layer per frame with exact durations
  - Tags chunk (0x2018) for animation loops & directions
  - Slice chunks (0x2022) for Pivot and UI 9-Slice center rects
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from ..canvas import TRANSPARENT, IndexedLayer, PixelProject

CHUNK_OLD_PALETTE = 0x0004
CHUNK_LAYER = 0x2004
CHUNK_CEL = 0x2005
CHUNK_TAGS = 0x2018
CHUNK_PALETTE = 0x2019
CHUNK_SLICE = 0x2022


def _ase_string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


def _wrap_chunk(chunk_type: int, payload: bytes) -> bytes:
    return struct.pack("<IH", 6 + len(payload), chunk_type) + payload


def _build_palette_chunk(project: PixelProject) -> bytes:
    """Build Palette Chunk (0x2019). Slot 0 is transparent, slots 1..N are palette colors."""
    colors = project.spec.palette.colors
    total = len(colors) + 1  # max 256
    parts = [struct.pack("<III8s", total, 0, total - 1, b"\x00" * 8)]
    # Slot 0: transparent
    parts.append(struct.pack("<HBBBB", 0, 0, 0, 0, 0))
    for r, g, b in colors:
        parts.append(struct.pack("<HBBBB", 0, r, g, b, 255))
    return _wrap_chunk(CHUNK_PALETTE, b"".join(parts))


def _build_old_palette_chunk(project: PixelProject) -> bytes:
    """Build legacy Old Palette Chunk (0x0004) for maximal backwards compatibility."""
    colors = [(0, 0, 0)] + project.spec.palette.colors
    count_byte = 0 if len(colors) == 256 else len(colors)
    parts = [struct.pack("<HBB", 1, 0, count_byte)]
    for r, g, b in colors:
        parts.append(struct.pack("<BBB", r, g, b))
    return _wrap_chunk(CHUNK_OLD_PALETTE, b"".join(parts))


def _build_layer_chunk(name: str, visible: bool = True, opacity: int = 255) -> bytes:
    flags = (1 if visible else 0) | 2  # visible + editable
    payload = struct.pack(
        "<HHHHHHB3s",
        flags,
        0,  # layer type: Normal (Image)
        0,  # child level
        0,  # default width (ignored)
        0,  # default height (ignored)
        0,  # blend mode: Normal
        max(0, min(255, int(opacity))),
        b"\x00\x00\x00",
    ) + _ase_string(name)
    return _wrap_chunk(CHUNK_LAYER, payload)


def _build_cel_chunk(layer_index: int, layer: IndexedLayer) -> bytes | None:
    """Build Compressed Image Cel Chunk (0x2005) cropped cleanly to the layer bbox."""
    bb = layer.bbox()
    if bb is None:
        return None
    min_x, min_y, max_x, max_y = bb
    cw = max_x - min_x + 1
    ch = max_y - min_y + 1

    raw = bytearray(cw * ch)
    pos = 0
    for y in range(min_y, max_y + 1):
        row = layer.grid[y]
        for x in range(min_x, max_x + 1):
            c = row[x]
            raw[pos] = 0 if c == TRANSPARENT else (c + 1)
            pos += 1

    compressed = zlib.compress(bytes(raw), level=6)
    header = struct.pack(
        "<HhhBHh5sHH",
        layer_index,
        min_x,
        min_y,
        layer.opacity,
        2,  # cel_type: Compressed Image
        0,  # z_index
        b"\x00" * 5,
        cw,
        ch,
    )
    return _wrap_chunk(CHUNK_CEL, header + compressed)


def _build_tags_chunk(project: PixelProject) -> bytes | None:
    if not project.tags:
        return None
    dir_map = {"forward": 0, "reverse": 1, "pingpong": 2}
    tag_colors = [
        (80, 190, 255),
        (120, 225, 140),
        (255, 165, 90),
        (235, 110, 175),
    ]
    parts = [struct.pack("<H8s", len(project.tags), b"\x00" * 8)]
    for idx, tag in enumerate(project.tags):
        tc = tag_colors[idx % len(tag_colors)]
        repeat = 0 if tag.loop else 1
        parts.append(
            struct.pack(
                "<HHBH6sBBBB",
                tag.from_frame,
                tag.to_frame,
                dir_map.get(tag.direction, 0),
                repeat,
                b"\x00" * 6,
                tc[0],
                tc[1],
                tc[2],
                0,
            )
            + _ase_string(tag.name)
        )
    return _wrap_chunk(CHUNK_TAGS, b"".join(parts))


def _build_slice_chunk(
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    pivot: tuple[int, int] | None = None,
    center_9slice: tuple[int, int, int, int] | None = None,
) -> bytes:
    flags = (1 if center_9slice is not None else 0) | (2 if pivot is not None else 0)
    parts = [
        struct.pack("<III", 1, flags, 0),
        _ase_string(name),
        struct.pack("<IiiII", 0, x, y, w, h),
    ]
    if center_9slice is not None:
        cx, cy, cw, ch = center_9slice
        parts.append(struct.pack("<iiII", cx, cy, cw, ch))
    if pivot is not None:
        parts.append(struct.pack("<ii", pivot[0], pivot[1]))
    return _wrap_chunk(CHUNK_SLICE, b"".join(parts))


def export_aseprite(project: PixelProject, out_dir: str | Path) -> Path:
    """Encode PixelProject into a spec-compliant native `.aseprite` binary file."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    out_path = out / f"{project.name}.aseprite"

    layer_names = project.all_layer_names()
    if not layer_names:
        layer_names = ["layer_0"]

    frame_blobs: list[bytes] = []
    for fi, fr in enumerate(project.frames):
        chunks: list[bytes] = []
        if fi == 0:
            chunks.append(_build_old_palette_chunk(project))
            chunks.append(_build_palette_chunk(project))
            for lname in layer_names:
                lyr_ref = next(
                    (f.layers[lname] for f in project.frames if lname in f.layers),
                    None,
                )
                vis = lyr_ref.visible if lyr_ref is not None else True
                op = lyr_ref.opacity if lyr_ref is not None else 255
                chunks.append(_build_layer_chunk(lname, visible=vis, opacity=op))

            tags_chunk = _build_tags_chunk(project)
            if tags_chunk is not None:
                chunks.append(tags_chunk)

            # Primary slice with pivot and optional 9-slice
            center_9 = None
            if project.nine_slice is not None:
                sl, st, sr, sb = project.nine_slice
                center_9 = (sl, st, project.width - sl - sr, project.height - st - sb)
            chunks.append(
                _build_slice_chunk(
                    name="nine_slice" if center_9 is not None else "bounds",
                    x=0,
                    y=0,
                    w=project.width,
                    h=project.height,
                    pivot=project.pivot,
                    center_9slice=center_9,
                )
            )
            for s in project.slices:
                chunks.append(
                    _build_slice_chunk(
                        name=s.name,
                        x=s.x,
                        y=s.y,
                        w=s.w,
                        h=s.h,
                        pivot=s.pivot,
                        center_9slice=s.center_9slice,
                    )
                )

        # Write one Cel chunk per non-empty layer in this frame
        for l_idx, lname in enumerate(layer_names):
            lyr = fr.layers.get(lname)
            if lyr is not None:
                cel = _build_cel_chunk(l_idx, lyr)
                if cel is not None:
                    chunks.append(cel)

        chunk_data = b"".join(chunks)
        n_chunks = len(chunks)
        old_n = n_chunks if n_chunks < 0xFFFF else 0xFFFF
        frame_bytes = 16 + len(chunk_data)
        frame_hdr = struct.pack(
            "<IHHH2sI",
            frame_bytes,
            0xF1FA,
            old_n,
            fr.duration_ms,
            b"\x00\x00",
            n_chunks,
        )
        frame_blobs.append(frame_hdr + chunk_data)

    all_frames = b"".join(frame_blobs)
    total_size = 128 + len(all_frames)
    num_colors = len(project.spec.palette) + 1
    header = struct.pack(
        "<IHHHHHIHII B 3s H BB hh HH 84s",
        total_size,
        0xA5E0,  # magic
        len(project.frames),
        project.width,
        project.height,
        8,  # 8-bit indexed
        1,  # flags: valid layer opacity
        project.frames[0].duration_ms,
        0,
        0,
        0,  # transparent palette index = 0
        b"\x00\x00\x00",
        num_colors,
        1,  # pixel width ratio
        1,  # pixel height ratio
        0,  # grid X
        0,  # grid Y
        project.width,  # grid W
        project.height,  # grid H
        b"\x00" * 84,
    )
    assert len(header) == 128, f"Aseprite header must be 128 bytes, got {len(header)}"
    out_path.write_bytes(header + all_frames)
    return out_path
