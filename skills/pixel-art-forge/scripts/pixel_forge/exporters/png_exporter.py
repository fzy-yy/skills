"""1x native PNG, ordered horizontal or grid Sprite Sheet, and per-frame PNG exporter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from ..canvas import PixelProject
from ..qa import layer_to_pil


def _compute_sheet_layout(
    project: PixelProject,
    columns: int | None = None,
    split_rows_by_tag: bool | None = None,
) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Compute (sheet_width, sheet_height, frame_rects) for single, strip, grid, or tag-row sheets."""
    w, h = project.width, project.height
    n_frames = len(project.frames)
    if n_frames <= 1:
        return (w, h, [(0, 0, w, h)])

    use_cols = columns if columns is not None else project.sheet_columns
    use_tag_rows = project.split_rows_by_tag if split_rows_by_tag is None else bool(split_rows_by_tag)

    # Mode A: One row per animation tag (e.g. 4-direction walk/idle RPG sheets)
    if use_tag_rows and project.tags:
        rows: list[list[int]] = []
        covered: set[int] = set()
        for tag in project.tags:
            row_indices = list(range(tag.from_frame, tag.to_frame + 1))
            if row_indices:
                if use_cols is not None and use_cols > 0:
                    for start in range(0, len(row_indices), use_cols):
                        rows.append(row_indices[start : start + use_cols])
                else:
                    rows.append(row_indices)
                covered.update(row_indices)
        untagged = [i for i in range(n_frames) if i not in covered]
        if untagged:
            if use_cols is not None and use_cols > 0:
                for start in range(0, len(untagged), use_cols):
                    rows.append(untagged[start : start + use_cols])
            else:
                rows.append(untagged)

        pos_by_frame: dict[int, tuple[int, int, int, int]] = {}
        max_cols = max(len(r) for r in rows)
        for r_idx, row in enumerate(rows):
            for c_idx, f_idx in enumerate(row):
                if f_idx not in pos_by_frame:
                    pos_by_frame[f_idx] = (c_idx * w, r_idx * h, w, h)
        rects = [pos_by_frame[i] for i in range(n_frames)]
        return (max_cols * w, len(rows) * h, rects)

    # Mode B: Fixed-column grid atlas (e.g. 8-column Blob47 autotile sheet)
    if use_cols is not None and use_cols > 0 and use_cols < n_frames:
        cols = int(use_cols)
        n_rows = (n_frames + cols - 1) // cols
        rects = [((i % cols) * w, (i // cols) * h, w, h) for i in range(n_frames)]
        return (cols * w, n_rows * h, rects)

    # Mode C: Default ordered horizontal strip
    rects = [(i * w, 0, w, h) for i in range(n_frames)]
    return (w * n_frames, h, rects)


def export_png(
    project: PixelProject,
    out_dir: str | Path,
    columns: int | None = None,
    split_rows_by_tag: bool | None = None,
) -> dict[str, Any]:
    """Export 1x native PNG (single sprite, horizontal strip, or multi-row grid sprite sheet).

    Returns layout metadata used by JSON exporter.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pal = project.spec.palette
    n_frames = len(project.frames)

    if n_frames == 1:
        filename = f"{project.name}.png"
        img = layer_to_pil(project.composite_frame(0), pal)
        img.save(out / filename, format="PNG")
        return {
            "filename": filename,
            "path": out / filename,
            "sheet_width": project.width,
            "sheet_height": project.height,
            "frame_rects": [(0, 0, project.width, project.height)],
        }

    filename = f"{project.name}_sheet.png"
    sheet_w, sheet_h, rects = _compute_sheet_layout(
        project,
        columns=columns,
        split_rows_by_tag=split_rows_by_tag,
    )
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    for idx, (ox, oy, _, _) in enumerate(rects):
        f_img = layer_to_pil(project.composite_frame(idx), pal)
        sheet.paste(f_img, (ox, oy))

    sheet.save(out / filename, format="PNG")
    return {
        "filename": filename,
        "path": out / filename,
        "sheet_width": sheet_w,
        "sheet_height": sheet_h,
        "frame_rects": rects,
    }


def export_frame_pngs(project: PixelProject, out_dir: str | Path) -> list[Path]:
    """Export every animation frame as an individual 1x native PNG under `frames/`."""
    frames_dir = Path(out_dir) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    # Remove stale frame PNGs left behind when frame count decreases
    for stale in frames_dir.glob(f"{project.name}_*.png"):
        stale.unlink(missing_ok=True)
    pal = project.spec.palette

    written: list[Path] = []
    for idx in range(len(project.frames)):
        f_img = layer_to_pil(project.composite_frame(idx), pal)
        f_path = frames_dir / f"{project.name}_{idx:03d}.png"
        f_img.save(f_path, format="PNG")
        written.append(f_path)
    return written
