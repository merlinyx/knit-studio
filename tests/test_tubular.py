import tempfile
import unittest
from pathlib import Path
from PIL import Image
from spacer_pipeline.tubular import tubular_plan, save_tubular_preview


class TubularTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.image = Path(self.tmp.name) / 'profile.png'
        Image.new('RGB', (20, 20), 'black').save(self.image)

    def plan(self, **kwargs):
        return tubular_plan(self.image, diameter_inches=2, height_inches=1,
                            stitch_gauge=5, course_gauge=6, **kwargs)

    def test_circumference_and_course_order(self):
        plan = self.plan()
        self.assertEqual([r['course'] for r in plan['courses']], list(range(1, 7)))
        self.assertEqual(plan['courses'][0]['stitches'], 32)
        self.assertEqual(plan['courses'][0]['front_stitches'], 16)

    def test_overlay_preserves_base_stitches_and_exports(self):
        plan = self.plan(holes=[dict(start_course=2, gaps=[[4, 5], [3, 6]])],
                         sections=[dict(name='elastic', start_course=1, end_course=3)])
        self.assertEqual(plan['courses'][1]['stitches'], 32)
        output = save_tubular_preview(plan, Path(self.tmp.name) / 'preview.html')
        self.assertIn('Course 2, needle 4, front, elastic, HOLE', output.read_text())

    def test_rejects_boundary_crossing_and_overlapping_sections(self):
        with self.assertRaises(ValueError):
            self.plan(holes=[dict(start_course=2, gaps=[[16, 17]])])
        with self.assertRaises(ValueError):
            self.plan(sections=[dict(name='a', start_course=1, end_course=3),
                                dict(name='b', start_course=2, end_course=3)])

    def test_rejects_disconnected_profile(self):
        image = Image.new('RGB', (20, 20), 'black')
        for y in range(20):
            image.putpixel((10, y), (255, 255, 255))
        image.save(self.image)
        with self.assertRaises(ValueError):
            self.plan()

    def test_centered_bed_slots_and_python_hole_api(self):
        from PIL import ImageDraw
        from spacer_pipeline.tubular import Hole, with_holes
        image = Image.new('RGB', (20, 20), 'white')
        ImageDraw.Draw(image).polygon([(6, 0), (13, 0), (19, 19), (0, 19)], fill='black')
        image.save(self.image)
        plan = self.plan()
        width = plan['bed_width']
        for row in plan['courses']:
            a, b = row['bed_runs']['f']
            c, d = row['bed_runs']['b']
            self.assertEqual(c, a)
            self.assertEqual(d, b)
            self.assertLessEqual(abs((a - 1) - (width - b)), 1)
        a, b = plan['courses'][2]['bed_runs']['f']
        changed = with_holes(plan, [Hole(3, ((a + 1, a + 1),), bed="b")])
        self.assertEqual(plan['holes'], [])
        self.assertEqual(changed['holes'][0]['gaps'], [[a + 1, a + 1]])
        with self.assertRaises(ValueError):
            with_holes(plan, [Hole(3, ((a, a),))])

    def test_one_based_courses_and_mirrored_back_labels(self):
        from spacer_pipeline.tubular import Hole, with_holes
        plan = with_holes(self.plan(), [Hole(2, ((4, 5),), bed="b")])
        output = save_tubular_preview(plan, Path(self.tmp.name) / 'back.html').read_text()
        self.assertIn('Course 2, needle 4, back, body, HOLE', output)
        self.assertNotIn('Course 1, needle 4, back, body, HOLE', output)
        import re
        labels = re.findall(r'y="25" font-size="10">(\d+)</text>', output)
        self.assertEqual([int(n) for n in labels], list(range(1, 17)) + list(range(16, 0, -1)))
        with self.assertRaisesRegex(ValueError, 'below and above'):
            with_holes(plan, [Hole(1, ((4, 5),))])
