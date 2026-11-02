import unittest
from spacer_pipeline.plated_helper import PlatedShapingHelper, carrier_group
from spacer_pipeline.tubular import Hole, with_holes
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan


def rectangle(width=16, courses=10):
    return dict(format='tubular-design-plan-v3', bed_width=width, sections=[], holes=[],
                courses=[dict(course=i, section='elastic' if i<=7 else 'wire',
                    bed_runs={'f': [1, width], 'b': [1, width]},
                    front_stitches=width, stitches=2*width) for i in range(1,courses+1)])


class PlatingTests(unittest.TestCase):
    def test_plated_opening_and_single_wire_transition(self):
        plan = with_holes(rectangle(), [Hole(3, ((8,9),(7,10),(7,10),(8,9)))])
        result = compile_tubular_plan(plan, TubularConfig(gauge=3, carrier=5,
            nonwire_caston=1, cast_on='alt_tuck', section_carriers={'elastic': [2,4], 'wire': 5}))
        self.assertIn('inhook 2\n', result.knitout)
        self.assertIn('inhook 4\n', result.knitout)
        self.assertNotIn('inhook 2 4', result.knitout)
        self.assertIn('releasehook 2\n', result.knitout)
        self.assertIn('releasehook 4\n', result.knitout)
        self.assertIn('knit - f48 2 4', result.knitout)
        self.assertIn('outhook 2\nouthook 4', result.knitout)
        lines = result.knitout.splitlines()
        for event in result.schedule:
            if event['kind']=='open_course':
                for line in lines[event['knitout_line_start']-1:event['knitout_line_end']]:
                    words = line.split()
                    if words and words[0] in ('knit','tuck','miss'):
                        self.assertEqual(words[3:], ['2','4'])
            if event['kind']=='tubular_course' and event['course']>=8:
                for line in lines[event['knitout_line_start']-1:event['knitout_line_end']]:
                    if line.startswith('knit '):
                        self.assertEqual(line.split()[3:], ['5'])

    def test_shared_carrier_is_retained(self):
        result = compile_tubular_plan(rectangle(), TubularConfig(
            carrier=4, section_carriers={'elastic': (2,4), 'wire': 4}))
        self.assertIn('outhook 2\n', result.knitout)
        self.assertNotIn('outhook 2 4', result.knitout)
        self.assertEqual(result.knitout.count('inhook 4\n'), 1)
        self.assertEqual(result.knitout.count('outhook 4'), 1)  # final bind-off only

    def test_shared_member_can_acquire_new_plating_yarn(self):
        plan = rectangle()
        result = compile_tubular_plan(plan, TubularConfig(carrier=4,
            section_carriers={'elastic': 4, 'wire': (2,4)}))
        self.assertIn('inhook 2\n', result.knitout)
        self.assertIn('releasehook 2\n', result.knitout)
        self.assertNotIn('outhook 4\n', result.knitout)

    def test_helper_style_and_carrier_validation(self):
        sh = PlatedShapingHelper(12, gauge=3)
        sh.cast_on_tubular_alt_tuck((2,4), settling_rows=4)
        sh.knit_tubular_row((2,4))
        sh.increase([(4,'left'), (9,'right')], (2,4))
        sh.bind_off_tubular((2,4))
        self.assertFalse(sh.active_carriers)
        self.assertIn('tuck +', sh.write())
        for value in ([], [2,2], [2,11], [2,True], '2 4'):
            with self.assertRaises(ValueError):
                carrier_group(value)
        sh = PlatedShapingHelper(12)
        sh.inhook(2)
        with self.assertRaisesRegex(ValueError, 'inactive carrier 4'):
            sh.knit('-', 'f10', (2,4))

    def test_direct_startup_exact_order_and_no_cast_on_operations(self):
        result = compile_tubular_plan(rectangle(), TubularConfig(gauge=3,
            cast_on='none', settling_courses=0, carrier=5,
            section_carriers={'elastic': [2,4], 'wire': 5}))
        lines = result.knitout.splitlines()
        setup = result.schedule[0]
        self.assertEqual(setup['kind'], 'direct_carrier_setup')
        self.assertEqual(setup['extra_courses'], 4)
        ops = lines[setup['knitout_line_start']-1:setup['knitout_line_end']]
        self.assertEqual(ops[0], 'inhook 2')
        index4 = ops.index('inhook 4')
        self.assertEqual(ops[index4-1], 'releasehook 2')
        self.assertEqual(ops[-1], 'releasehook 4')
        self.assertEqual(sum(line.startswith('knit ') and line.endswith(' 2') for line in ops), 2*2*16)
        self.assertEqual(sum(line.startswith('knit ') and line.endswith(' 4') for line in ops), 2*2*16)
        self.assertFalse(any(line.startswith(('tuck ', 'drop ', 'xfer ')) for line in ops))
        first = next(e for e in result.schedule if e.get('course')==1)
        body = lines[first['knitout_line_start']-1:first['knitout_line_end']]
        self.assertTrue(all(line.endswith(' 2 4') for line in body if line.startswith('knit ')))

    def test_configurable_solo_setup_and_invalid_combination(self):
        result = compile_tubular_plan(rectangle(), TubularConfig(cast_on='none',
            plating_setup_courses=3, section_carriers={'elastic': (4,2)}))
        self.assertEqual(result.schedule[0]['extra_courses'], 6)
        self.assertLess(result.knitout.index('inhook 4'), result.knitout.index('inhook 2'))
        with self.assertRaisesRegex(ValueError, 'separate nonwire'):
            compile_tubular_plan(rectangle(), TubularConfig(cast_on='none', nonwire_caston=1))
        with self.assertRaisesRegex(ValueError, 'positive integer'):
            compile_tubular_plan(rectangle(), TubularConfig(plating_setup_courses=0))

    def test_group_outhook_is_sequential_and_validates_before_removal(self):
        sh = PlatedShapingHelper(12)
        sh.start_tubular_carriers((4,2))
        sh.outhook((4,2))
        self.assertEqual(sh.instructions[-2:], ['outhook 4', 'outhook 2'])
        self.assertFalse(sh.active_carriers)
        sh.inhook(2)
        before = list(sh.instructions)
        with self.assertRaisesRegex(ValueError, 'inactive carrier 4'):
            sh.outhook((2,4))
        self.assertEqual(sh.instructions, before)
        self.assertEqual(sh.active_carriers, {2})

    def test_plated_finish_emits_single_carrier_outhooks(self):
        for finish in ('bind_off', 'drop'):
            with self.subTest(finish=finish):
                result = compile_tubular_plan(rectangle(), TubularConfig(
                    cast_on='none', carrier=(2,4), finish=finish))
                hooks = [line for line in result.knitout.splitlines() if line.startswith('outhook ')]
                self.assertEqual(hooks, ['outhook 2', 'outhook 4'])
