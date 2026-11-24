"""Automated unit & binary-spec round-trip tests for pixel_forge."""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from pixel_forge import (
    BLOB47_MASKS,
    CARDINAL16_MASKS,
    CORE_MATERIALS,
    TRANSPARENT,
    CharacterRig,
    PartTransform,
    PixelProject,
    apply_inner_outline,
    apply_layer_ao,
    apply_outline,
    apply_pixel_aa,
    attack_swing_poses,
    auto_shade_layer,
    build_autotile_set,
    build_button_states,
    build_custom_palette_spec,
    check_nine_slice_consistency,
    check_tile_seams,
    circle,
    cutout_mask,
    despeckle,
    draw_health_bar,
    draw_iso_block,
    draw_iso_diamond,
    draw_item_slot,
    draw_nine_slice_panel,
    erase_circle,
    erase_polygon,
    erase_rect,
    fill_stone_brick_tile,
    fill_transition_tile,
    find_orphan_pixels,
    find_outline_doubles,
    generate_hue_shifted_ramp,
    idle_cycle_poses,
    infer_material_profile,
    list_palettes,
    list_spec_presets,
    load_palette,
    load_spec,
    paint_ascii_canvas,
    rect,
    remove_doubles,
    resolution_budget,
    shaded_cylinder,
    shaded_sphere,
    validate_project,
    walk_cycle_poses,
)
from pixel_forge.exporters import export_all
import cli as pixel_cli


def parse_aseprite_binary(path: Path) -> dict:
    """Minimal strict Aseprite (.ase) binary parser to verify spec compliance."""
    data = path.read_bytes()
    assert len(data) >= 128, "File shorter than 128-byte Aseprite header"
    (
        file_size,
        magic,
        n_frames,
        width,
        height,
        color_depth,
        flags,
        speed,
        _z0,
        _z1,
        trans_idx,
        _ign,
        num_colors,
        px_w,
        px_h,
        gx,
        gy,
        gw,
        gh,
        _res,
    ) = struct.unpack_from("<IHHHHHIHII B 3s H BB hh HH 84s", data, 0)

    assert file_size == len(data), f"Header file_size {file_size} != actual {len(data)}"
    assert magic == 0xA5E0, f"Bad Aseprite magic: {hex(magic)}"
    assert color_depth == 8

    offset = 128
    frames_parsed = []
    chunk_types_seen: list[int] = []
    layer_names: list[str] = []
    cel_count = 0

    for _ in range(n_frames):
        f_bytes, f_magic, old_c, duration, _fut, new_c = struct.unpack_from("<IHHH2sI", data, offset)
        assert f_magic == 0xF1FA, f"Bad frame magic: {hex(f_magic)}"
        f_end = offset + f_bytes
        c_off = offset + 16
        c_count = new_c if new_c > 0 else old_c
        for _ in range(c_count):
            c_size, c_type = struct.unpack_from("<IH", data, c_off)
            c_payload = data[c_off + 6 : c_off + c_size]
            chunk_types_seen.append(c_type)
            if c_type == 0x2004:
                # Layer name starts at byte 16
                slen = struct.unpack_from("<H", c_payload, 16)[0]
                layer_names.append(c_payload[18 : 18 + slen].decode("utf-8"))
            elif c_type == 0x2005:
                # Compressed cel: decompress and check pixel byte length == cw * ch
                _, _, _, _, cel_type, _, _, cw, ch = struct.unpack_from("<HhhBHh5sHH", c_payload, 0)
                assert cel_type == 2
                raw = zlib.decompress(c_payload[20:])
                assert len(raw) == cw * ch
                cel_count += 1
            c_off += c_size
        assert c_off == f_end, f"Chunk parsing ended at {c_off} != frame end {f_end}"
        frames_parsed.append({"duration": duration, "chunks": c_count})
        offset = f_end

    assert offset == len(data), f"Trailing bytes after frames: {offset} != {len(data)}"
    return {
        "width": width,
        "height": height,
        "frames": n_frames,
        "num_colors": num_colors,
        "chunk_types": chunk_types_seen,
        "layer_names": layer_names,
        "cel_count": cel_count,
    }


class TestPixelForge(unittest.TestCase):
    def test_presets_load(self) -> None:
        pals = list_palettes()
        specs = list_spec_presets()
        self.assertGreaterEqual(len(pals), 6)
        self.assertGreaterEqual(len(specs), 4)
        for p in pals:
            pal = load_palette(p)
            self.assertGreaterEqual(len(pal), 4)
        for s in specs:
            spec = load_spec(s)
            self.assertGreater(len(spec.materials), 3)
            for mat in CORE_MATERIALS:
                self.assertIn(mat, spec.materials, f"Preset {s!r} missing core material {mat!r}")

    def test_palette_remap_and_cli_custom_spec(self) -> None:
        spec = load_spec("topdown_rpg")
        spec.remap_to_palette(load_palette("sweetie16"))
        for mat in CORE_MATERIALS:
            ramp = spec.ramp(mat)
            self.assertEqual(len(ramp), len(set(ramp)), f"Collapsed duplicate shade in {mat}: {ramp}")
            self.assertGreaterEqual(len(ramp), 2)

        # CLI init-spec with custom colors, light-dir, ppu, max-colors
        with tempfile.TemporaryDirectory() as td:
            out_spec = Path(td) / "pixel_spec.json"
            rc = pixel_cli.main(
                [
                    "init-spec",
                    "--preset",
                    "topdown_rpg",
                    "--custom-colors",
                    "hero_blue:#3a6ea5,ruby:#c93b4b",
                    "--light-dir",
                    "1,-1",
                    "--ppu",
                    "16",
                    "--max-colors",
                    "12",
                    "--out",
                    str(out_spec),
                ]
            )
            self.assertEqual(rc, 0)
            loaded = load_spec(out_spec)
            self.assertIn("hero_blue", loaded.materials)
            self.assertIn("ruby", loaded.materials)
            self.assertLessEqual(len(loaded.palette), 12)
            self.assertEqual(loaded.pixels_per_unit, 16)
            self.assertGreater(loaded.light_dir[0], 0.5)
            self.assertLess(loaded.light_dir[1], -0.5)

    def test_ao_horizontal_light_and_nineslice_light_dir(self) -> None:
        spec = load_spec("topdown_rpg")
        # Pure horizontal light from the left (-1, 0): shadow casts strictly right (+1, 0), not down!
        spec.light_dir = (-1.0, 0.0)
        spec.__post_init__()
        proj = PixelProject("ao_h", 12, 12, spec, category="icons")
        bg = proj.layer("bg")
        occ = proj.layer("occ")
        rect(bg, 2, 2, 8, 8, spec.color("stone", 3), fill=True, material="stone")
        rect(occ, 4, 4, 2, 2, spec.color("steel", 3), fill=True, material="steel")
        apply_layer_ao(bg, occ, spec, step=1)
        # Pixel to the right of occluder (6, 4) should be darkened; pixel directly below (4, 6) untouched
        self.assertEqual(bg.get_px(6, 4), spec.color("stone", 2))
        self.assertEqual(bg.get_px(4, 6), spec.color("stone", 3))

        # Top-right light (+1, -1): 9-slice right bevel should be brighter than left bevel
        spec_tr = load_spec("topdown_rpg")
        spec_tr.light_dir = (1.0, -1.0)
        spec_tr.__post_init__()
        ui = PixelProject("panel_tr", 24, 24, spec_tr, category="ui")
        draw_nine_slice_panel(ui.layer("panel"), spec_tr, border=5)
        w_ramp = spec_tr.ramp("wood")
        self.assertEqual(ui.layer("panel").get_px(22, 12), w_ramp[-1])
        self.assertEqual(ui.layer("panel").get_px(1, 12), w_ramp[1])

    def test_stone_brick_non_divisible_width_seamless(self) -> None:
        spec = load_spec("topdown_rpg")
        for w, cols in ((16, 2), (22, 3), (24, 5)):
            tile = PixelProject(f"brick_{w}_{cols}", w, 16, spec, category="tilesets")
            fill_stone_brick_tile(tile.layer("stone"), spec, rows=4, cols=cols, seed=17)
            seam = check_tile_seams(tile.layer("stone"), spec.palette)
            self.assertTrue(seam["seamless_ok"], f"Seam failed for {w}x16 cols={cols}: {seam}")

    def test_qa_multiframe_tileset_doubles_and_stale_frames(self) -> None:
        spec = load_spec("topdown_rpg")
        # 1. Multi-frame tileset catches seam break on Frame 1
        tile = PixelProject("multi_tile", 16, 16, spec, category="tilesets")
        fill_stone_brick_tile(tile.layer("stone"), spec, seed=1)
        f1 = tile.add_frame()
        # Deliberate non-wrapping horizontal gradient (small interior steps, harsh LR wrap seam)
        s_ramp = spec.ramp("steel")
        for x in range(16):
            c_idx = s_ramp[min(len(s_ramp) - 1, (x * len(s_ramp)) // 16)]
            for y in range(16):
                f1.layer("stone").set_px(x, y, c_idx, "steel")
        rep = validate_project(tile)
        self.assertEqual(len(rep["seam_reports"]), 2)
        self.assertTrue(rep["seam_reports"][0]["seamless_ok"])
        self.assertFalse(rep["seam_reports"][1]["seamless_ok"])
        self.assertFalse(rep["seam_report"]["seamless_ok"])

        # 2. L-double detection on thin outline layer
        icon = PixelProject("dbl_test", 16, 16, spec, category="icons")
        ol = icon.layer("outline")
        for pt in ((4, 4), (5, 4), (5, 5), (6, 5)):
            ol.set_px(pt[0], pt[1], 0)
        self.assertIn((5, 4), find_outline_doubles(ol))
        self.assertIn((5, 5), find_outline_doubles(ol))

        # 3. Stale frame cleanup + category-prefixed QA sheet + canonical layer order
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pixel_assets"
            anim4 = PixelProject("hero", 16, 16, spec, category="characters")
            for fi in range(4):
                fr = anim4.frame(0) if fi == 0 else anim4.add_frame(duration_ms=120)
                rect(fr.layer("body"), 5, 5, 6, 8, spec.color("steel", 2), fill=True, material="steel")
            anim4.add_tag("idle", 0, 3)
            res4 = export_all(anim4, assets_root=root)
            self.assertTrue(Path(res4["inspection_sheet"]).name == "characters_hero_qa.png")
            self.assertEqual(len(list((root / "exports/characters/hero/frames").glob("*.png"))), 4)

            # Re-export same asset with only 2 frames: stale frames 002 & 003 must be cleaned up
            anim2 = PixelProject("hero", 16, 16, spec, category="characters")
            for fi in range(2):
                fr = anim2.frame(0) if fi == 0 else anim2.add_frame(duration_ms=120)
                rect(fr.layer("body"), 5, 5, 6, 8, spec.color("steel", 2), fill=True, material="steel")
            anim2.add_tag("idle", 0, 1)
            export_all(anim2, assets_root=root)
            remaining = sorted(p.name for p in (root / "exports/characters/hero/frames").glob("*.png"))
            self.assertEqual(remaining, ["hero_000.png", "hero_001.png"])

    def test_strict_palette_and_dimensions(self) -> None:
        spec = load_spec("topdown_rpg")
        with self.assertRaises(ValueError):
            PixelProject("bad", 0, 16, spec)
        proj = PixelProject("test_box", 16, 16, spec, category="icons")
        lyr = proj.layer("main")
        with self.assertRaises(ValueError):
            lyr.set_px(2, 2, 999)
        # Out of bounds write increments clipped_count without crashing
        ok = lyr.set_px(20, 20, 1)
        self.assertFalse(ok)
        self.assertEqual(lyr.clipped_count, 1)

    def test_max_colors_cap_enforced_by_qa(self) -> None:
        spec = load_spec("topdown_rpg")
        spec.max_colors = 2
        proj = PixelProject("cap_test", 8, 8, spec, category="icons")
        lyr = proj.layer("main")
        lyr.set_px(1, 1, 0)
        lyr.set_px(2, 2, 1)
        self.assertTrue(validate_project(proj)["passed"])
        lyr.set_px(3, 3, 2)  # 3rd color exceeds max_colors=2
        report = validate_project(proj)
        self.assertFalse(report["passed"])
        self.assertTrue(any("max_colors" in e for e in report["errors"]))

    def test_hue_shifted_ramp(self) -> None:
        ramp = generate_hue_shifted_ramp("#4488cc", steps=4)
        self.assertEqual(len(ramp), 4)
        self.assertEqual(len(set(ramp)), 4)

    def test_remove_doubles(self) -> None:
        # Path with an L-double at (1, 0): (0,0) -> (1,0) -> (1,1) -> (2,1)
        pts = [(0, 0), (1, 0), (1, 1), (2, 1)]
        cleaned = remove_doubles(pts)
        self.assertNotIn((1, 0), cleaned)
        self.assertEqual(cleaned[0], (0, 0))
        self.assertEqual(cleaned[-1], (2, 1))

    def test_directional_shading_and_despeckle(self) -> None:
        spec = load_spec("topdown_rpg")
        proj = PixelProject("orb", 24, 24, spec, category="icons")
        lyr = proj.layer("orb")
        circle(lyr, 12, 12, 7, spec.color("steel", 2), fill=True, material="steel")
        auto_shade_layer(lyr, spec, material="steel")
        # Top-left quadrant should average brighter than bottom-right quadrant (no pillow shading!)
        ramp = spec.ramp("steel")
        tl = ramp.index(lyr.get_px(8, 8))
        br = ramp.index(lyr.get_px(16, 16))
        self.assertGreater(tl, br, f"Expected top-left ({tl}) brighter than bottom-right ({br})")

        # Inject a single orphan interior noise pixel and verify despeckle removes it
        lyr.set_px(12, 12, spec.color("fire", 1), material="fire")
        self.assertIn((12, 12), find_orphan_pixels(lyr))
        fixed = despeckle(lyr)
        self.assertGreaterEqual(fixed, 1)
        self.assertNotIn((12, 12), find_orphan_pixels(lyr))

    def test_all_four_categories_export_and_aseprite_roundtrip(self) -> None:
        spec = load_spec("topdown_rpg")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pixel_assets"

            # 1. Static Icon
            icon = PixelProject("gem", 16, 16, spec, category="icons")
            body = icon.layer("gem")
            circle(body, 8, 8, 5, spec.color("magic", 2), fill=True, material="magic")
            auto_shade_layer(body, spec)
            apply_outline(icon.layer("outline"), body, spec)
            res_icon = export_all(icon, assets_root=root)
            self.assertTrue(res_icon["qa"]["passed"])
            self.assertNotIn("tres", res_icon["exports"])
            self.assertNotIn("gif", res_icon["exports"])
            # Check 1x PNG exact size & 1-bit alpha
            with Image.open(res_icon["exports"]["png"]) as raw_im:
                im = raw_im.convert("RGBA")
                self.assertEqual(im.size, (16, 16))
                alphas = {im.getpixel((x, y))[3] for y in range(16) for x in range(16)}
                self.assertTrue(alphas.issubset({0, 255}))
            ase_i = parse_aseprite_binary(Path(res_icon["exports"]["aseprite"]))
            self.assertEqual((ase_i["width"], ase_i["height"], ase_i["frames"]), (16, 16, 1))
            self.assertIn("gem", ase_i["layer_names"])
            self.assertIn("outline", ase_i["layer_names"])

            # 2. Animated Character (Ordered Sheet + Per-Frame PNGs + GIF + JSON + Aseprite)
            char = PixelProject("slime", 24, 24, spec, category="characters")
            rig = CharacterRig(24, 24, len(spec.palette))
            b_part = rig.add_part("body", z_order=10)
            circle(b_part, 12, 14, 6, spec.color("grass", 2), fill=True, material="grass")
            auto_shade_layer(b_part, spec)
            rig.render_to_frame(char.frame(0), pose={"body": (0, 0)})
            apply_outline(char.frame(0).layer("outline"), char.frame(0).composite(), spec)
            f1 = char.add_frame(duration_ms=180)
            rig.render_to_frame(f1, pose={"body": (0, 1)})
            apply_outline(f1.layer("outline"), f1.composite(), spec)
            char.add_tag("idle", 0, 1, loop=True)
            res_char = export_all(char, assets_root=root)
            self.assertTrue(res_char["qa"]["passed"])
            self.assertNotIn("tres", res_char["exports"])
            with Image.open(res_char["exports"]["png"]) as char_im:
                self.assertEqual(char_im.size, (48, 24))
            # Verify individual per-frame PNGs
            frame_paths = res_char["exports"]["frames"]
            self.assertEqual(len(frame_paths), 2)
            for fp in frame_paths:
                with Image.open(fp) as fim:
                    self.assertEqual(fim.size, (24, 24))
            # Verify animated GIF
            gif_path = Path(res_char["exports"]["gif"])
            self.assertTrue(gif_path.exists())
            with Image.open(gif_path) as gim:
                self.assertEqual(gim.size, (24, 24))
                self.assertEqual(getattr(gim, "n_frames", 1), 2)
                self.assertEqual(gim.info.get("transparency"), 0)
            meta_c = json.loads(Path(res_char["exports"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual(meta_c["meta"]["frameTags"][0]["name"], "idle")
            self.assertEqual(meta_c["meta"]["gif"], "slime.gif")
            self.assertEqual(len(meta_c["meta"]["frameImages"]), 2)
            self.assertIn("unity", meta_c["meta"]["engine_hints"])
            self.assertIn("godot", meta_c["meta"]["engine_hints"])
            ase_c = parse_aseprite_binary(Path(res_char["exports"]["aseprite"]))
            self.assertEqual(ase_c["frames"], 2)
            self.assertIn(0x2018, ase_c["chunk_types"])  # Tags chunk present
            self.assertIn(0x2022, ase_c["chunk_types"])  # Slice/Pivot chunk present

            # 3. Static Seamless Tile
            tile = PixelProject("brick", 16, 16, spec, category="tilesets")
            fill_stone_brick_tile(tile.layer("stone"), spec, seed=7)
            seam = check_tile_seams(tile.layer("stone"), spec.palette)
            self.assertTrue(seam["seamless_ok"])
            res_tile = export_all(tile, assets_root=root)
            self.assertTrue(res_tile["qa"]["passed"])
            self.assertNotIn("tres", res_tile["exports"])

            # 4. 9-Slice UI Panel
            ui = PixelProject("panel", 32, 32, spec, category="ui")
            margins = draw_nine_slice_panel(ui.layer("panel"), spec, border=5)
            ui.set_nine_slice(*margins)
            res_ui = export_all(ui, assets_root=root)
            self.assertTrue(res_ui["qa"]["passed"])
            self.assertNotIn("tres", res_ui["exports"])
            meta_ui = json.loads(Path(res_ui["exports"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual(meta_ui["meta"]["engine_hints"]["godot"]["nineSliceLTRB"], [6, 6, 6, 6])

            # Ensure zero .tres files anywhere under exports/
            self.assertEqual(list(root.rglob("*.tres")), [])

            # Verify catalog.json and project_contact_sheet.png were maintained
            catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(len(catalog["assets"]), 4)
            self.assertTrue((root / "_inspect" / "project_contact_sheet.png").exists())

    def test_alpha_lock_remap_rotate_and_squash(self) -> None:
        spec = load_spec("topdown_rpg")
        proj = PixelProject("sword_swap", 24, 24, spec, category="icons")
        body = proj.layer("body")
        rect(body, 8, 6, 8, 12, spec.color("steel", 3), fill=True, material="steel")
        orig_count = body.non_empty_count()

        # Alpha lock prevents painting outside opaque silhouette and keeps original material when material=None
        with body.lock_alpha():
            rect(body, 0, 0, 24, 24, spec.color("steel", 4), fill=True)
        self.assertEqual(body.non_empty_count(), orig_count)
        self.assertEqual(body.get_px(2, 2), TRANSPARENT)
        self.assertEqual(body.get_px(10, 10), spec.color("steel", 4))
        self.assertEqual(body.get_material(10, 10), "steel")

        # Exact 90-degree rotation preserves pixel count and swaps aspect
        rot90 = body.rotate(90.0, pivot=(11.5, 11.5))
        self.assertEqual(rot90.non_empty_count(), orig_count)
        bb90 = rot90.bbox()
        self.assertIsNotNone(bb90)
        self.assertGreater(bb90[2] - bb90[0], bb90[3] - bb90[1])

        # Arbitrary 45-degree RotSprite rotation preserves valid palette indices & material_map
        rot45 = body.rotate(45.0)
        self.assertGreater(rot45.non_empty_count(), orig_count // 2)
        for x, y, c in rot45.iter_opaque():
            self.assertEqual(rot45.get_material(x, y), "steel")
            self.assertIn(c, spec.ramp("steel"))

        # Squash & stretch keeps 1x grid and adjusts bbox height
        sq = body.squash_stretch(sx=1.25, sy=0.75)
        bb_orig = body.bbox()
        bb_sq = sq.bbox()
        self.assertIsNotNone(bb_orig)
        self.assertIsNotNone(bb_sq)
        self.assertLess(bb_sq[3] - bb_sq[1], bb_orig[3] - bb_orig[1])

        # Project-level material palette swap + automatic outline regeneration
        apply_outline(proj.layer("outline"), body, spec)
        changed = proj.remap_material({"steel": "gold"}, reoutline=True)
        self.assertEqual(changed, orig_count)
        self.assertEqual(body.get_material(10, 10), "gold")
        self.assertIn(body.get_px(10, 10), spec.ramp("gold"))
        # Outline adjacent to bottom-right shadow side should now match gold[0]
        self.assertEqual(proj.layer("outline").get_px(16, 12), spec.color("gold", 0))

    def test_large_canvas_distance_field_3d_primitives_and_aa(self) -> None:
        spec = load_spec("topdown_rpg")
        # 64x64 large orb verifies full distance field (beyond old 3px cap) produces smooth directional shading
        proj = PixelProject("large_orb", 64, 64, spec, category="icons")
        lyr = proj.layer("orb")
        circle(lyr, 32, 32, 22, spec.color("steel", 2), fill=True, material="steel")
        auto_shade_layer(lyr, spec, material="steel")
        ramp = spec.ramp("steel")
        self.assertGreater(ramp.index(lyr.get_px(20, 20)), ramp.index(lyr.get_px(44, 44)))

        # 3D shaded sphere & cylinder honor light_dir
        sp_proj = PixelProject("sphere_cyl", 32, 32, spec, category="icons")
        sp_lyr = sp_proj.layer("sphere")
        shaded_sphere(sp_lyr, 15.5, 15.5, 10, spec, material="magic")
        m_ramp = spec.ramp("magic")
        self.assertGreater(m_ramp.index(sp_lyr.get_px(11, 11)), m_ramp.index(sp_lyr.get_px(21, 21)))

        cyl_lyr = sp_proj.layer("cyl")
        shaded_cylinder(cyl_lyr, 4, 4, 8, 20, spec, material="wood", axis="vertical")
        w_ramp = spec.ramp("wood")
        self.assertGreater(w_ramp.index(cyl_lyr.get_px(5, 10)), w_ramp.index(cyl_lyr.get_px(11, 10)))

        # Inner outline darkens shaded side of adjacent distinct materials
        seam_lyr = sp_proj.layer("seam")
        rect(seam_lyr, 4, 4, 6, 6, spec.color("steel", 4), fill=True, material="steel")
        rect(seam_lyr, 10, 4, 6, 6, spec.color("gold", 3), fill=True, material="gold")
        darkened = apply_inner_outline(seam_lyr, spec, step=1)
        self.assertGreater(darkened, 0)
        self.assertEqual(seam_lyr.get_px(10, 6), spec.color("gold", 2))

        # Pixel AA stays strictly within opaque pixels & palette
        aa_lyr = sp_proj.layer("aa")
        rect(aa_lyr, 4, 4, 10, 10, spec.color("steel", 5), fill=True, material="steel")
        rect(aa_lyr, 4, 4, 5, 5, spec.color("steel", 1), fill=True, material="steel")
        before_opaque = aa_lyr.non_empty_count()
        aa_changed = apply_pixel_aa(aa_lyr, spec, material="steel", min_run=2)
        self.assertGreaterEqual(aa_changed, 1)
        self.assertEqual(aa_lyr.non_empty_count(), before_opaque)

    def test_hierarchical_rig_transforms_and_presets(self) -> None:
        spec = load_spec("topdown_rpg")
        rig = CharacterRig(32, 32, len(spec.palette))
        torso = rig.add_part("torso", z_order=20)
        head = rig.add_part("head", z_order=30, parent="torso")
        weapon = rig.add_part("weapon", z_order=40, parent="torso", pivot=(22.0, 18.0))

        rect(torso, 12, 14, 8, 8, spec.color("steel", 2), fill=True, material="steel")
        rect(head, 13, 6, 6, 6, spec.color("skin", 2), fill=True, material="skin")
        rect(weapon, 22, 10, 2, 10, spec.color("gold", 2), fill=True, material="gold")

        proj = PixelProject("rig_test", 32, 32, spec, category="characters")
        # Moving torso by (0, 2) must carry head to y=8 and rotate weapon cleanly
        rig.render_to_frame(
            proj.frame(0),
            pose={
                "torso": (0, 2),
                "weapon": PartTransform(dx=1, dy=0, rotate_deg=45.0),
            },
        )
        self.assertEqual(proj.frame(0).layer("head").bbox(), (13, 8, 18, 13))
        self.assertIsNotNone(proj.frame(0).layer("weapon").bbox())

        # Cyclic parent detection raises ValueError
        bad_rig = CharacterRig(16, 16, len(spec.palette))
        bad_rig.add_part("a", parent="b")
        bad_rig.add_part("b", parent="a")
        with self.assertRaises(ValueError):
            bad_rig.render_to_frame(proj.add_frame())

        # Verify built-in presets for idle, all 4 walk directions, and attack swing
        self.assertEqual(len(idle_cycle_poses(4)), 4)
        for direction in ("down", "up", "left", "right"):
            w_poses = walk_cycle_poses(direction=direction, frames=4)
            self.assertEqual(len(w_poses), 4)
        atk = attack_swing_poses(direction="right", frames=4)
        self.assertEqual(len(atk), 4)
        self.assertIsInstance(atk[1][0]["weapon"], PartTransform)

    def test_cli_scaffold_run_recolor_and_preview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pixel_assets"
            # 1. Scaffold all 4 categories and run each via `cli.py run`
            for cat, name, w, h in (
                ("icons", "orb_item", 24, 24),
                ("characters", "mini_hero", 32, 32),
                ("tilesets", "wall_tile", 16, 16),
                ("ui", "box_ui", 32, 32),
            ):
                rc_s = pixel_cli.main(
                    [
                        "scaffold",
                        "--category", cat,
                        "--name", name,
                        "--width", str(w),
                        "--height", str(h),
                        "--root", str(root),
                    ]
                )
                self.assertEqual(rc_s, 0)
                script_p = root / "src" / cat / f"{name}_{w}x{h}.py"
                self.assertTrue(script_p.exists())

                rc_r = pixel_cli.main(["run", str(script_p), "--", "--out", str(root)])
                self.assertEqual(rc_r, 0)
                self.assertTrue((root / "_inspect" / f"{cat}_{name}_qa.png").exists())

            # 2. Recolor the generated orb_item (magic -> fire) into fire_orb
            orb_script = root / "src" / "icons" / "orb_item_24x24.py"
            rc_rec = pixel_cli.main(
                [
                    "recolor",
                    "--script", str(orb_script),
                    "--map", "magic=fire",
                    "--name", "fire_orb",
                    "--root", str(root),
                ]
            )
            self.assertEqual(rc_rec, 0)
            recolored_png = root / "exports" / "icons" / "fire_orb" / "fire_orb.png"
            self.assertTrue(recolored_png.exists())

            # 3. Export 8x lossless nearest preview
            prev_out = root / "_inspect" / "fire_orb_8x.png"
            rc_p = pixel_cli.main(
                ["preview", "--png", str(recolored_png), "--scale", "8", "--out", str(prev_out)]
            )
            self.assertEqual(rc_p, 0)
            with Image.open(prev_out) as pim:
                self.assertEqual(pim.size, (192, 192))

    def test_autotile_16_and_47_blob_and_transitions(self) -> None:
        self.assertEqual(len(CARDINAL16_MASKS), 16)
        self.assertEqual(len(BLOB47_MASKS), 47)
        spec = load_spec("topdown_rpg")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pixel_assets"
            proj16 = build_autotile_set("grass_16", 16, spec, fill_material="grass", bg_material="wood", mode="cardinal16")
            self.assertEqual(len(proj16.frames), 16)
            res16 = export_all(proj16, assets_root=root)
            self.assertTrue(res16["qa"]["passed"])
            self.assertNotIn("gif", res16["exports"])

            proj47 = build_autotile_set("grass_47", 16, spec, fill_material="grass", bg_material="wood", mode="blob47")
            self.assertEqual(len(proj47.frames), 47)
            res47 = export_all(proj47, assets_root=root)
            self.assertTrue(res47["qa"]["passed"])
            self.assertTrue(Path(res47["inspection_sheet"]).exists())
            meta47 = json.loads(Path(res47["exports"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual(meta47["meta"]["autotile"]["tile_count"], 47)
            self.assertEqual(meta47["meta"]["engine_hints"]["godot"]["autotile"]["mode"], "blob47")
            self.assertEqual(meta47["meta"]["engine_hints"]["unity"]["ruleTile"]["tileCount"], 47)
            ase47 = parse_aseprite_binary(Path(res47["exports"]["aseprite"]))
            self.assertEqual(ase47["frames"], 47)

        # Terrain transitions on all 4 edges
        for edge in ("top", "bottom", "left", "right"):
            tp = PixelProject(f"tr_{edge}", 16, 16, spec, category="tilesets")
            fill_transition_tile(tp.layer("ground"), spec, top_material="grass", bottom_material="stone", edge=edge)
            self.assertEqual(tp.layer("ground").non_empty_count(), 256)

    def test_isometric_diamond_and_block_export(self) -> None:
        spec = load_spec("topdown_rpg")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pixel_assets"
            iso_proj = PixelProject("iso_tile", 32, 32, spec, category="tilesets", toroidal=False)
            info = draw_iso_block(iso_proj.layer("block"), spec, top_material="grass", side_material="wood", height_px=8)
            iso_proj.metadata["isometric"] = info
            self.assertEqual(info["diamond_w"] // 2, info["diamond_h"])
            res = export_all(iso_proj, assets_root=root)
            self.assertTrue(res["qa"]["passed"])
            self.assertTrue(Path(res["inspection_sheet"]).exists())
            meta = json.loads(Path(res["exports"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual(meta["meta"]["engine_hints"]["godot"]["tileShape"], "TILE_SHAPE_ISOMETRIC")
            self.assertEqual(meta["meta"]["engine_hints"]["unity"]["gridCellLayout"], "Isometric")

        # Pure diamond primitive check
        dp = PixelProject("iso_flat", 32, 16, spec, category="tilesets", toroidal=False)
        dw, dh = draw_iso_diamond(dp.layer("top"), spec, material="stone")
        self.assertEqual((dw, dh), (32, 16))
        self.assertGreater(dp.layer("top").non_empty_count(), 200)

    def test_ui_button_states_health_bar_and_item_slot(self) -> None:
        spec = load_spec("topdown_rpg")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pixel_assets"
            btn = build_button_states("play_btn", 48, 18, spec)
            self.assertEqual(len(btn.frames), 4)
            self.assertIsNotNone(btn.nine_slice)
            res_btn = export_all(btn, assets_root=root)
            self.assertTrue(res_btn["qa"]["passed"])
            # Static UI state sheet should NOT emit animated GIF
            self.assertNotIn("gif", res_btn["exports"])
            meta_btn = json.loads(Path(res_btn["exports"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual(meta_btn["meta"]["ui_states"]["pressed"], 2)
            # Ensure normal and pressed states differ visually
            self.assertNotEqual(btn.frame(0).composite().grid, btn.frame(2).composite().grid)

            # Segmented health bar
            hp = PixelProject("hp_bar", 48, 10, spec, category="ui")
            draw_health_bar(hp.layer("bar"), spec, ratio=0.6, segmented=4)
            res_hp = export_all(hp, assets_root=root)
            self.assertTrue(res_hp["qa"]["passed"])

            # Selected item slot with rarity rim
            slot = PixelProject("slot_sel", 24, 24, spec, category="ui")
            margins = draw_item_slot(slot.layer("slot"), spec, selected=True, rarity_material="magic")
            slot.set_nine_slice(*margins)
            res_slot = export_all(slot, assets_root=root)
            self.assertTrue(res_slot["qa"]["passed"])

    def test_layer_canonical_z_order_and_composite_solid(self) -> None:
        spec = load_spec("topdown_rpg")
        proj = PixelProject("z_order_check", 24, 24, spec, category="icons")
        f0 = proj.frame(0)
        # Deliberately create 'fx' first and 'outline' last: canonical Z-buckets must still order
        # outline (-100) -> body (0) -> fx (+100) so outline never slices over FX!
        fx = f0.layer("fx")
        body = f0.layer("body")
        outline = f0.layer("outline")
        rect(body, 8, 8, 8, 8, spec.color("steel", 3), fill=True, material="steel")
        # FX spark overlaps top edge of body where outline will sit
        rect(fx, 11, 6, 2, 3, spec.color("fire", -1), fill=True, material="fire")
        solid = f0.composite_solid()
        self.assertEqual(solid.get_px(11, 6), TRANSPARENT)
        apply_outline(outline, solid, spec)
        self.assertEqual(proj.all_layer_names(), ["outline", "body", "fx"])
        comp = proj.composite_frame(0)
        # FX pixel at (11, 7) must remain bright fire (not overwritten by outline!)
        self.assertEqual(comp.get_px(11, 7), spec.color("fire", -1))

    def test_rig_parent_rotation_and_flip_propagation(self) -> None:
        spec = load_spec("topdown_rpg")
        rig = CharacterRig(32, 32, len(spec.palette))
        arm = rig.add_part("front_arm", z_order=20, pivot=(16.0, 15.0))
        wpn = rig.add_part("weapon", z_order=30, parent="front_arm", pivot=(22.0, 15.0))
        rect(arm, 16, 15, 6, 2, spec.color("steel", 2), fill=True, material="steel")
        # Upright blade at x=22, y=9..15
        rect(wpn, 22, 9, 1, 7, spec.color("gold", 3), fill=True, material="gold")

        proj = PixelProject("fk_rot", 32, 32, spec, category="characters")
        # Rotate parent arm +90 deg around shoulder (16, 15): grip (22, 15) must orbit to (16, 21)
        # and blade tip (22, 9) must rotate horizontally to (22, 21)!
        rig.render_to_frame(proj.frame(0), pose={"front_arm": PartTransform(rotate_deg=90.0)})
        wpn_f0 = proj.frame(0).layer("weapon")
        self.assertNotEqual(wpn_f0.get_px(16, 21), TRANSPARENT)
        self.assertNotEqual(wpn_f0.get_px(22, 21), TRANSPARENT)

        # Flip parent horizontally: child weapon must mirror across canvas to x = 31 - 22 = 9
        f1 = proj.add_frame()
        rig.render_to_frame(f1, pose={"front_arm": PartTransform(flip_x=True)})
        wpn_f1 = f1.layer("weapon")
        self.assertNotEqual(wpn_f1.get_px(9, 12), TRANSPARENT)
        self.assertEqual(wpn_f1.get_px(22, 12), TRANSPARENT)

    def test_nine_slice_consistency_and_multiframe_alert_qa(self) -> None:
        spec = load_spec("topdown_rpg")
        ui = PixelProject("bad_9slice", 32, 32, spec, category="ui")
        margins = draw_nine_slice_panel(ui.layer("panel"), spec, border=5)
        ui.set_nine_slice(*margins)
        self.assertTrue(check_nine_slice_consistency(ui.layer("panel"), margins)["consistent"])
        # Inject an ornament dot inside the stretchable top edge band (x=15, y=2)
        ui.layer("panel").set_px(15, 2, spec.color("cloth_red", 3), "cloth_red")
        rep = validate_project(ui)
        self.assertFalse(rep["nine_slice_report"]["consistent"])
        self.assertIn(15, rep["nine_slice_report"]["frames"][0]["mismatch_columns"])
        self.assertTrue(any("9-slice stretch band mismatch" in w for w in rep["warnings"]))

        # Multi-frame non-zero border alert triggers secondary zoomed ruler panel without crashing
        with tempfile.TemporaryDirectory() as td:
            anim = PixelProject("alert_anim", 16, 16, spec, category="characters")
            rect(anim.frame(0).layer("body"), 5, 5, 6, 8, spec.color("steel", 2), fill=True, material="steel")
            f1 = anim.add_frame()
            rect(f1.layer("body"), 5, 0, 6, 8, spec.color("steel", 2), fill=True, material="steel")
            anim.add_tag("idle", 0, 1)
            res = export_all(anim, assets_root=Path(td) / "pixel_assets")
            self.assertEqual(res["qa"]["alert_frame"], 1)
            self.assertTrue(Path(res["inspection_sheet"]).exists())

    def test_sprite_sheet_grid_columns_and_tag_rows(self) -> None:
        spec = load_spec("topdown_rpg")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "pixel_assets"
            # 1. Fixed 8-column grid sheet for 47-tile Blob autotile -> 8x6 tiles = 128x96 PNG
            auto47 = build_autotile_set("grid_auto", 16, spec, mode="blob47", sheet_columns=8)
            res_auto = export_all(auto47, assets_root=root)
            with Image.open(res_auto["exports"]["png"]) as im_a:
                self.assertEqual(im_a.size, (16 * 8, 16 * 6))
            meta_a = json.loads(Path(res_auto["exports"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual(meta_a["frames"][8]["frame"], {"x": 0, "y": 16, "w": 16, "h": 16})

            # 2. Tag-row packing: 2 tags x 3 frames each -> 3x2 = 48x32 PNG
            char = PixelProject("tag_grid", 16, 16, spec, category="characters")
            char.set_sheet_layout(split_rows_by_tag=True)
            for fi in range(6):
                fr = char.frame(0) if fi == 0 else char.add_frame()
                rect(fr.layer("body"), 4, 4, 8, 8, spec.color("cloth_blue", 2), fill=True, material="cloth_blue")
            char.add_tag("down", 0, 2)
            char.add_tag("up", 3, 5)
            res_c = export_all(char, assets_root=root)
            with Image.open(res_c["exports"]["png"]) as im_c:
                self.assertEqual(im_c.size, (16 * 3, 16 * 2))
            meta_c = json.loads(Path(res_c["exports"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual(meta_c["frames"][3]["frame"], {"x": 0, "y": 16, "w": 16, "h": 16})

    def test_ascii_canvas_boolean_cutouts_and_material_profiles(self) -> None:
        spec = load_spec("topdown_rpg")
        self.assertEqual(infer_material_profile("steel"), "metallic")
        self.assertEqual(infer_material_profile("magic"), "gem")
        self.assertEqual(infer_material_profile("fire"), "emissive")
        self.assertEqual(infer_material_profile("wood"), "matte")

        proj = PixelProject("cutout_ascii", 16, 16, spec, category="icons")
        lyr = proj.layer("helm")
        paint_ascii_canvas(
            lyr,
            spec,
            """
..SSSS..
.SSSSSS.
SSSSSSSS
SSx..xSS
""",
            legend={"S": "steel:3", "x": "erase"},
            ox=0,
            oy=2,
            mirror=True,
        )
        # Left side (2, 2) mirrored to (13, 2)
        self.assertEqual(lyr.get_px(2, 2), spec.color("steel", 3))
        self.assertEqual(lyr.get_px(13, 2), spec.color("steel", 3))

        erase_rect(lyr, 6, 4, 4, 1)
        self.assertEqual(lyr.get_px(7, 4), TRANSPARENT)
        erase_circle(lyr, 8, 3, 1.0)
        self.assertEqual(lyr.get_px(8, 3), TRANSPARENT)
        erase_polygon(lyr, [(0, 4), (2, 4), (1, 5)])
        self.assertEqual(lyr.get_px(1, 4), TRANSPARENT)

        mask = proj.layer("mask")
        rect(mask, 12, 2, 4, 4, 1)
        removed = cutout_mask(lyr, mask)
        self.assertGreater(removed, 0)
        self.assertEqual(lyr.get_px(13, 2), TRANSPARENT)

        # Verify all 4 explicit material shading profiles run cleanly & CLI perspective alias works
        for prof in ("matte", "metallic", "gem", "emissive"):
            p_lyr = proj.layer(f"p_{prof}")
            circle(p_lyr, 8, 8, 5, spec.color("gold", 2), fill=True, material="gold")
            auto_shade_layer(p_lyr, spec, material="gold", profile=prof)
            self.assertGreater(p_lyr.non_empty_count(), 20)

        with tempfile.TemporaryDirectory() as td:
            sp_out = Path(td) / "spec.json"
            rc = pixel_cli.main(["init-spec", "--perspective", "side_platformer", "--out", str(sp_out)])
            self.assertEqual(rc, 0)
            self.assertEqual(load_spec(sp_out).perspective, "side_view")


if __name__ == "__main__":
    unittest.main(verbosity=2)
