"""Compatibility checks use the original wire helper, not the packaged snapshot."""
import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from spacer_pipeline.tubular import Hole, with_holes
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan


def instructions(text):
    """Ignore comments/headers/whitespace, retain every machine operation."""
    return [' '.join(line.split(';', 1)[0].split()) for line in text.splitlines()
            if line.split(';', 1)[0].strip()]


def plan_from_ranges(ranges):
    return dict(format='tubular-design-plan-v3', bed_width=max(b for a, b in ranges),
                holes=[], sections=[], courses=[dict(course=i, bed_runs={'f': [a, b], 'b': [a, b]},
                front_stitches=b-a+1, stitches=2*(b-a+1), section='body')
                for i, (a, b) in enumerate(ranges, 1)])


def original_modules():
    root = Path(__file__).resolve().parents[2] / 'wire_knitting/wire_knitting_code'
    loaded = {}
    for name in ('knitout_writer', 'knitting_helper', 'shaping_helper', 'example_patterns'):
        spec = importlib.util.spec_from_file_location(name, root / f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, loaded):
            spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


class CompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (Path(__file__).resolve().parents[2] / 'wire_knitting/wire_knitting_code').is_dir():
            raise unittest.SkipTest('original wire_knitting checkout is not next to this repository')
        cls.original = original_modules()

    def test_original_plain_tube_example_all_gauges(self):
        # Execute the actual example function, intercepting only file writing.
        original = self.original['shaping_helper'].ShapingHelper
        write = original.write
        for gauge in (2, 3, 4):
            with self.subTest(gauge=gauge):
                captured = []
                def capture(helper, filename=None):
                    text = write(helper)
                    captured.append(text)
                    return text
                with patch.object(original, 'write', capture), contextlib.redirect_stdout(io.StringIO()):
                    self.original['example_patterns'].test_tube(gauge)
                result = compile_tubular_plan(plan_from_ranges([(1, 30)]*30),
                    TubularConfig(gauge=gauge, carrier=6, side_slack=True, finish='drop'))
                self.assertEqual(instructions(result.knitout), instructions(captured[0]))

    def test_original_nonwire_caston_example(self):
        original = self.original['shaping_helper'].ShapingHelper
        write = original.write
        captured = []
        def capture(helper, filename=None):
            text = write(helper)
            captured.append(text)
            return text
        with patch.object(original, 'write', capture), contextlib.redirect_stdout(io.StringIO()):
            self.original['example_patterns'].test_tube(3, main_carrier=6, nonwire_caston=1)
        result = compile_tubular_plan(plan_from_ranges([(1, 30)]*30),
            TubularConfig(gauge=3, carrier=6, cast_on='knit', nonwire_caston=1,
                          side_slack=True, finish='drop'))
        self.assertEqual(instructions(result.knitout), instructions(captured[0]))
        self.assertEqual(sum(e['kind']=='nonwire_caston_transition_extra_courses' for e in result.schedule), 1)

    def run_example(self, name):
        original = self.original['shaping_helper'].ShapingHelper
        write = original.write
        captured = []
        def capture(helper, filename=None):
            text = write(helper)
            captured.append(text)
            return text
        with patch.object(original, 'write', capture), contextlib.redirect_stdout(io.StringIO()):
            getattr(self.original['example_patterns'], name)()
        return captured[0]

    def test_original_short_row_tube_example(self):
        turns = [dict(b='b', n=n) for n in (14, 7, 13, 8, 20, 2)]
        turns += [dict(b='f', n=n) for n in (13, 8)]
        result = compile_tubular_plan(plan_from_ranges([(1, 20)]*20),
            TubularConfig(carrier=6, finish='drop', short_rows_after={10: turns}))
        self.assertEqual(instructions(result.knitout), instructions(self.run_example('test_tube_shortrows')))

    def test_original_sock_example(self):
        ranges = [(1, 20)]*20
        short_rows = {}
        for lo, hi in ((2, 19), (3, 18), (4, 17)):
            ranges.extend([(lo, hi)]*2)
            short_rows[len(ranges)-1] = [dict(b='b', n=n) for n in
                (round(.7*(hi-lo)+lo), round(.3*(hi-lo)+lo), hi, lo+1)]
        ranges.extend([(4, 17)]*20)
        result = compile_tubular_plan(plan_from_ranges(ranges),
            TubularConfig(cast_on='all_needle_transition', finish='drop', short_rows_after=short_rows))
        self.assertEqual(instructions(result.knitout), instructions(self.run_example('test_sock')))

    def test_centered_decrease_and_increase_matches_original_operations(self):
        original = self.original['shaping_helper'].ShapingHelper
        sh = original(12, gauge=2)
        sh.standard_headers()
        sh.cast_on_all_needle_transition(3, settling_rows=4)
        for _ in range(3):
            sh.knit_tubular_row(3)
        sh.decrease_both()
        sh.knit_tubular_row(3)
        sh.knit_tubular_row(3)
        sh.increase([(sh.min_n, 'left'), (sh.max_n, 'right')], 3)
        sh.knit_tubular_row(3)
        sh.bind_off_tubular(3)
        plan = plan_from_ranges([(1, 12)]*3 + [(2, 11)]*2 + [(1, 12)]*2)
        result = compile_tubular_plan(plan, TubularConfig(cast_on='all_needle_transition'))
        self.assertEqual(instructions(result.knitout), instructions(sh.write()))


class OpeningCompilerTests(unittest.TestCase):
    def test_front_and_back_openings_transfer_alignment_and_no_crossing_floats(self):
        for bed in ('f', 'b'):
            for gauge in (2, 3, 4):
                with self.subTest(bed=bed, gauge=gauge):
                    plan = with_holes(plan_from_ranges([(1, 16)]*10),
                        [Hole(3, ((8, 9), (7, 10), (7, 10), (8, 9)), bed)])
                    result = compile_tubular_plan(plan, TubularConfig(gauge=gauge))
                    self.assertEqual(len([e for e in result.schedule if e['kind']=='open_course']), 4)
                    self.assertEqual(len([e for e in result.schedule if e['kind']=='closing_course_and_recovery']), 1)
                    # Every transfer must use aligned front/back needles.
                    rack = 0
                    for line in instructions(result.knitout):
                        words = line.split()
                        if words[0] == 'rack':
                            rack = float(words[1])
                            self.assertLessEqual(abs(rack), 8)
                        if words[0] == 'xfer':
                            a, b = words[1:]
                            self.assertNotEqual(a[0], b[0])
                            f, back = (a, b) if a[0]=='f' else (b, a)
                            self.assertEqual(int(f[1:])-int(back[1:]), rack)
                    emitted = result.knitout.splitlines()
                    for event in result.schedule:
                        if event['kind'] != 'open_course':
                            continue
                        a, b = event['gap']
                        previous = None
                        for line in emitted[event['knitout_line_start']-1:event['knitout_line_end']]:
                            words = line.split()
                            if not words or words[0] not in ('knit', 'tuck', 'miss'):
                                continue
                            needle = words[2]
                            if needle[0] == bed:
                                logical = (int(needle[1:])-(bed=='b'))//gauge
                                self.assertFalse(a <= logical <= b, line)
                                if previous and previous[0] == bed:
                                    low, high = sorted((previous[1], logical))
                                    self.assertFalse(low < a and high > b, line)
                                previous = (bed, logical)
                            else:
                                previous = (needle[0], 0)

    def test_asymmetric_and_single_needle_openings(self):
        for bed in ('f', 'b'):
            for gaps in (((8, 8), (7, 8), (7, 9), (8, 9), (9, 9)),
                         ((8, 9), (9, 10), (8, 9), (8, 8))):
                plan = with_holes(plan_from_ranges([(1, 16)]*10), [Hole(3, gaps, bed)])
                result = compile_tubular_plan(plan)
                self.assertIn('closing_course_and_recovery', [e['kind'] for e in result.schedule])
                # Check direction continuity within every opening course,
                # including the approach to newly seeded starting edges.
                lines = result.knitout.splitlines()
                for event in result.schedule:
                    if event['kind'] != 'open_course':
                        continue
                    previous = None
                    for line in lines[event['knitout_line_start']-1:event['knitout_line_end']]:
                        words = line.split()
                        if not words or words[0] not in ('knit', 'tuck', 'miss'):
                            continue
                        direction, needle = words[1:3]
                        current = (needle[0], int(needle[1:]), direction)
                        if previous and previous[0] == current[0]:
                            delta = current[1]-previous[1]
                            self.assertGreaterEqual(delta if direction=='+' else -delta, 0)
                        previous = current

    def test_nonwire_caston_honors_first_section_and_same_carrier(self):
        plan = plan_from_ranges([(1, 12)]*4)
        plan['courses'][0]['section']='elastic'
        result = compile_tubular_plan(plan, TubularConfig(carrier=6,
            nonwire_caston=2, section_carriers={'elastic': 1}))
        ops = instructions(result.knitout)
        self.assertLess(ops.index('inhook 2'), ops.index('inhook 1'))
        self.assertLess(ops.index('outhook 2'), ops.index('inhook 6'))
        unchanged = compile_tubular_plan(plan, TubularConfig(carrier=6, section_carriers={'elastic': 1}))
        same = compile_tubular_plan(plan, TubularConfig(carrier=6,
            nonwire_caston=1, section_carriers={'elastic': 1}))
        self.assertEqual(instructions(unchanged.knitout), instructions(same.knitout))
        for invalid in (0, 11, True):
            with self.assertRaises(ValueError):
                compile_tubular_plan(plan, TubularConfig(nonwire_caston=invalid))

    def test_material_sections_and_schedule(self):
        plan = plan_from_ranges([(1, 12)]*8)
        for row in plan['courses'][:3]:
            row['section']='elastic'
        result = compile_tubular_plan(plan, TubularConfig(section_carriers={'elastic': 1}, finish='drop'))
        self.assertIn('inhook 1', result.knitout)
        self.assertIn('inhook 3', result.knitout)
        self.assertEqual(sum(e['kind']=='carrier_transition_extra_course' for e in result.schedule), 1)

    def test_rejects_shaping_or_carrier_change_during_opening(self):
        hole = Hole(3, ((6, 7), (6, 7)))
        plan = with_holes(plan_from_ranges([(1, 16)]*3+[(2, 15)]*4), [hole])
        with self.assertRaisesRegex(ValueError, 'constant'):
            compile_tubular_plan(plan)
        plan = with_holes(plan_from_ranges([(1, 16)]*7), [hole])
        plan['courses'][3]['section']='wire'
        with self.assertRaisesRegex(ValueError, 'material/carrier'):
            compile_tubular_plan(plan, TubularConfig(section_carriers={'wire': 6}))

    def test_rejects_large_initial_gap_and_abrupt_outer_change(self):
        plan = with_holes(plan_from_ranges([(1, 16)]*7), [Hole(3, ((6, 9),))])
        with self.assertRaisesRegex(ValueError, 'one or two'):
            compile_tubular_plan(plan)
        with self.assertRaisesRegex(ValueError, 'edge changes'):
            compile_tubular_plan(plan_from_ranges([(1, 16), (4, 13)]))
