import tempfile
import unittest
from pathlib import Path

from spacer_pipeline.recipe import run_job
from spacer_pipeline.settings_schema import build_schema, default_recipe
from test_recipe import panel_image, vase_image


class SettingsSchemaTests(unittest.TestCase):
    def test_every_config_field_is_exposed(self) -> None:
        import dataclasses
        from spacer_pipeline.compiler import CompileConfig
        from spacer_pipeline.tubular_compiler import TubularConfig

        schema = build_schema()["pipelines"]
        spacer = {f["name"] for f in schema["spacer"] if f["target"] == "compile"}
        tube = {f["name"] for f in schema["tube"] if f["target"] == "compile"}
        self.assertEqual(spacer, {f.name for f in dataclasses.fields(CompileConfig)})
        # Sections and flap have their own editors.
        self.assertEqual(tube | {"section_carriers", "flap"},
                         {f.name for f in dataclasses.fields(TubularConfig)})

    def test_input_mode_leads_the_image_group(self) -> None:
        for fields in build_schema()["pipelines"].values():
            self.assertEqual(fields[0]["key"], "image.input_mode")

    def test_default_recipes_compile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            spacer = dict(default_recipe("spacer"), image_path=str(panel_image(out / "p.png")))
            self.assertIsNone(run_job(spacer, out / "spacer").error)
            tube = default_recipe("tube")
            tube.update(image_path=str(vase_image(out / "v.png")))
            tube["image"].update(stitch_gauge=4, course_gauge=8, diameter_inches=3)
            self.assertIsNone(run_job(tube, out / "tube").error)


if __name__ == "__main__":
    unittest.main()
