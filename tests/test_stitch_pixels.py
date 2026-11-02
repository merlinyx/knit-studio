import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

from spacer_pipeline.cli import main
from spacer_pipeline.image import image_to_plan
from spacer_pipeline.tubular import tubular_plan
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan


class StitchPixelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.path = self.folder / 'pixels.png'

    def test_flat_preserves_canvas_runs_and_odd_row_increase(self):
        image = Image.new('RGB', (8, 3), 'white')
        draw = ImageDraw.Draw(image)
        draw.line((2, 2, 5, 2), fill='black')
        draw.line((1, 1, 6, 1), fill='black')
        draw.line((1, 0, 2, 0), fill='black')
        draw.line((5, 0, 6, 0), fill='black')
        image.save(self.path)
        plan = image_to_plan(self.path, input_mode='stitch-pixels', needle_offset=1)
        self.assertEqual([row.to_list() for row in plan.rows],
                         [[[3, 6]], [[2, 7]], [[2, 3], [6, 7]]])
        self.assertEqual(plan.metadata['source_grid'], {'columns': 8, 'rows': 3})
        self.assertNotIn('increase_row_parity', plan.metadata)
        different_gauge = image_to_plan(self.path, input_mode='stitch-pixels', stitch_gauge=2, row_gauge=5, needle_offset=1)
        self.assertEqual(plan.rows, different_gauge.rows)

    def test_tube_one_pixel_is_one_stitch_per_bed_without_rounding(self):
        image = Image.new('RGB', (9, 3), 'white')
        draw = ImageDraw.Draw(image)
        for y, count in enumerate((5, 6, 7)):
            draw.line((1, y, count, y), fill='black')
        image.save(self.path)
        plan = tubular_plan(self.path, input_mode='stitch-pixels')
        self.assertEqual([row['front_stitches'] for row in plan['courses']], [7, 6, 5])
        self.assertEqual([row['stitches'] for row in plan['courses']], [14, 12, 10])
        result = compile_tubular_plan(plan, TubularConfig(gauge=3))
        self.assertIn('knit - f21 3', result.knitout)
        different_gauge = tubular_plan(self.path, input_mode='stitch-pixels', stitch_gauge=2, course_gauge=5)
        self.assertEqual([r['bed_runs'] for r in plan['courses']],
                         [r['bed_runs'] for r in different_gauge['courses']])

    def test_rejects_dimensions_and_row_alignment_in_pixel_mode(self):
        Image.new('RGB', (8, 8), 'black').save(self.path)
        with self.assertRaisesRegex(ValueError, 'physical dimensions'):
            image_to_plan(self.path, input_mode='stitch-pixels', width_inches=1)
        with self.assertRaisesRegex(ValueError, 'physical dimensions'):
            tubular_plan(self.path, input_mode='stitch-pixels', diameter_inches=1)
        with self.assertRaisesRegex(ValueError, 'preserves rows'):
            image_to_plan(self.path, input_mode='stitch-pixels', align_increase_rows=True)
        with self.assertRaisesRegex(ValueError, 'positive'):
            image_to_plan(self.path)

    def test_cli_both_pixel_modes_without_dimensions(self):
        Image.new('RGB', (8, 8), 'black').save(self.path)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['image', str(self.path), '--input-mode', 'stitch-pixels',
                                  '--json', str(self.folder/'flat.json')]), 0)
            self.assertEqual(main(['tube-preview', str(self.path), '--input-mode', 'stitch-pixels',
                                  '--html', str(self.folder/'tube.html'),
                                  '--json', str(self.folder/'tube.json')]), 0)
        flat = json.loads((self.folder/'flat.json').read_text())
        tube = json.loads((self.folder/'tube.json').read_text())
        self.assertEqual(len(flat['rows']), 8)
        self.assertEqual(tube['courses'][0]['stitches'], 16)
        self.assertIn('Stitch-pixel mode', (self.folder/'tube.html').read_text())
