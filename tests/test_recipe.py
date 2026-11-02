import base64
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from spacer_pipeline.cli import main
from spacer_pipeline.dat import convert_with_node, node_executable
from spacer_pipeline.recipe import read_recipe, run_job

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "src" / "spacer_pipeline" / "studio" / "static" / "dat-shim.js"
CONVERTER = ROOT / "src" / "spacer_pipeline" / "studio" / "static" / "vendor" / "knitout-to-dat.js"

# The October panels from run_spacer.sh; drawings/ is local-only (gitignored).
LOCAL_PANELS = [
    ("1009/ws2.png", dict(width_inches=4.75, height_inches=3.75, stitch_gauge=10, row_gauge=10),
     dict(front_carrier=[2, 4], back_carrier=[6, 7], filler_carrier=5, filler_pass_pairs=4)),
    ("1009/bm2.png", dict(width_inches=2.5, height_inches=6.25, stitch_gauge=10, row_gauge=10),
     dict(front_carrier=[2, 4], back_carrier=[6, 7], filler_carrier=5, filler_pass_pairs=4)),
    ("1009/wbl2.png", dict(width_inches=3.5, height_inches=7.5, row_gauge=12),
     dict(front_carrier=[2, 4], back_carrier=[8, 9], filler_carrier=7, filler_pass_pairs=4)),
]

TUBE_IMAGE = dict(diameter_inches=3, height_inches=3, stitch_gauge=4, course_gauge=8)
TUBE_COMPILE = dict(gauge=2, carrier=6, section_carriers={"base": [1, 3]}, finish="bind_off")
TUBE_SECTIONS = [dict(name="base", start_course=1, end_course=6, color="#e8b86d")]


def panel_image(path: Path) -> Path:
    image = Image.new("RGB", (240, 200), "white")
    ImageDraw.Draw(image).polygon([(60, 10), (180, 10), (230, 190), (10, 190)], fill="black")
    image.save(path)
    return path


def vase_image(path: Path) -> Path:
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    for y in range(300):
        half = 50 + 40 * (1 - abs(y - 150) / 150)
        draw.line([(100 - half, y), (100 + half, y)], fill="black")
    image.save(path)
    return path


def flags(arguments: dict) -> list[str]:
    names = dict(width_inches="--width-in", height_inches="--height-in",
                 diameter_inches="--diameter-in")
    result = []
    for key, value in arguments.items():
        result += [names.get(key, "--" + key.replace("_", "-")), str(value)]
    return result


def carriers(value) -> str:
    return ",".join(map(str, value)) if isinstance(value, list) else str(value)


def quietly(argv: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return main(argv)


class RecipeMatchesCliTests(unittest.TestCase):
    """run_job must produce exactly what the existing commands produce."""

    def assert_spacer_matches_cli(self, image: Path, image_args: dict, compile_args: dict) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            quietly(["image", str(image), *flags(image_args), "--fill-outline",
                     "--json", str(out / "cli.json")])
            quietly(["compile", str(out / "cli.json"), "--output", str(out / "cli.k"),
                     "--front-carriers", carriers(compile_args["front_carrier"]),
                     "--back-carriers", carriers(compile_args["back_carrier"]),
                     "--filler-carriers", carriers(compile_args["filler_carrier"]),
                     "--filler-pass-pairs", str(compile_args["filler_pass_pairs"])])
            result = run_job(dict(pipeline="spacer", name="studio", image_path=str(image),
                                  image=dict(image_args, fill_outline=True),
                                  compile=compile_args), out / "studio")
            self.assertIsNone(result.error)
            self.assertEqual((out / "cli.k").read_text(), result.files["knitout"].read_text())
            self.assertEqual(json.loads((out / "cli.json").read_text()),
                             json.loads(result.files["plan"].read_text()))

    def test_spacer_synthetic_panel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = panel_image(Path(directory) / "panel.png")
            self.assert_spacer_matches_cli(
                image, dict(width_inches=4, height_inches=3),
                dict(front_carrier=[2, 4], back_carrier=[8, 10], filler_carrier=7, filler_pass_pairs=3))

    def test_spacer_local_october_panels(self) -> None:
        for name, image_args, compile_args in LOCAL_PANELS:
            image = ROOT / "drawings" / name
            if not image.exists():
                self.skipTest("local drawings/ folder not present")
            with self.subTest(name):
                self.assert_spacer_matches_cli(image, image_args, compile_args)

    def test_tube_matches_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            image = vase_image(out / "vase.png")
            (out / "spec.json").write_text(json.dumps(dict(sections=TUBE_SECTIONS)))
            (out / "config.json").write_text(json.dumps(TUBE_COMPILE))
            quietly(["tube-preview", str(image), *flags(TUBE_IMAGE), "--spec", str(out / "spec.json"),
                     "--html", str(out / "cli.html"), "--json", str(out / "cli.json")])
            quietly(["tube-compile", str(out / "cli.json"), "--config", str(out / "config.json"),
                     "--output", str(out / "cli.k")])
            sections = [dict(TUBE_SECTIONS[0], carriers=[1, 3])]
            compile_args = {k: v for k, v in TUBE_COMPILE.items() if k != "section_carriers"}
            result = run_job(dict(pipeline="tube", name="studio", image_path=str(image),
                                  image=TUBE_IMAGE, sections=sections, compile=compile_args),
                             out / "studio")
            self.assertIsNone(result.error)
            self.assertEqual((out / "cli.k").read_text(), result.files["knitout"].read_text())


class RecipeFileTests(unittest.TestCase):
    def test_saved_recipe_embeds_image_and_reproduces_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            image = panel_image(out / "panel.png")
            first = run_job(dict(pipeline="spacer", name="p", image_path=str(image),
                                 image=dict(width_inches=4, height_inches=3)), out / "first")
            saved = json.loads(first.files["recipe"].read_text())
            self.assertNotIn("image_path", saved)
            self.assertEqual(base64.b64decode(saved["image_data"]), image.read_bytes())
            image.unlink()
            second = run_job(read_recipe(first.files["recipe"]), out / "second")
            self.assertEqual(first.files["knitout"].read_text(), second.files["knitout"].read_text())

    def test_pixel_mode_ignores_leftover_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "pixels.png"
            Image.new("RGB", (8, 6), "black").save(image)
            result = run_job(dict(pipeline="spacer", name="p", image_path=str(image),
                                  image=dict(input_mode="stitch-pixels", width_inches=4,
                                             height_inches=3, align_increase_rows=True)),
                             Path(directory) / "out", preview_only=True)
            self.assertIsNone(result.error)
            self.assertEqual(result.course_count, 6)
            self.assertNotIn("recipe", result.files)

    def test_compiler_error_is_reported_with_preview_kept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            result = run_job(dict(pipeline="tube", name="t", image_path=str(vase_image(out / "v.png")),
                                  image=TUBE_IMAGE, compile=dict(gauge=5)), out / "job")
            self.assertIn("gauge", result.error)
            self.assertTrue(result.files["preview"].exists())
            self.assertNotIn("knitout", result.files)
            self.assertNotIn("recipe", result.files)

    def test_cli_run_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            panel_image(out / "panel.png")
            (out / "r.json").write_text(json.dumps(dict(
                pipeline="spacer", name="cli", image_path="panel.png",
                image=dict(width_inches=4, height_inches=3))))
            self.assertEqual(quietly(["run", str(out / "r.json"), "--output-dir", str(out / "o")]), 0)
            self.assertTrue((out / "o" / "cli.k").exists())


@unittest.skipUnless(node_executable(), "Node.js not installed")
class DatShimTests(unittest.TestCase):
    def test_in_window_conversion_matches_node(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            result = run_job(dict(pipeline="spacer", name="d",
                                  image_path=str(panel_image(out / "panel.png")),
                                  image=dict(width_inches=4, height_inches=3)), out / "job")
            convert_with_node(result.files["knitout"], out / "node.dat")
            script = (
                "const fs = require('fs');"
                f"const {{ createDatConverter }} = require({json.dumps(str(SHIM))});"
                f"const convert = createDatConverter(fs.readFileSync({json.dumps(str(CONVERTER))}, 'utf8'));"
                f"const out = convert(fs.readFileSync({json.dumps(str(result.files['knitout']))}, 'utf8'));"
                f"fs.writeFileSync({json.dumps(str(out / 'shim.dat'))}, out.bytes);"
            )
            subprocess.run([node_executable(), "-e", script], check=True)
            self.assertEqual((out / "node.dat").read_bytes(), (out / "shim.dat").read_bytes())


if __name__ == "__main__":
    unittest.main()
