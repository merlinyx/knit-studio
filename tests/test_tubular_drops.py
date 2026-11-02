import unittest
from spacer_pipeline.plated_helper import PlatedShapingHelper
from spacer_pipeline.tubular import Hole, with_holes
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan


def initial_live(gauge,width):
    return {f'{bed}{gauge*n+(bed=="b")}':1 for bed in ('f','b') for n in range(1,width+1)}


def check_cleanup(test,lines,gauge,width):
    live=initial_live(gauge,width)
    rack=0
    for line in lines:
        words=line.split()
        if not words:
            continue
        if words[0]=='rack':
            rack=float(words[1])
        elif words[0]=='xfer':
            source,target=words[1:]
            f,b=(source,target) if source[0]=='f' else (target,source)
            test.assertEqual(int(f[1:])-int(b[1:]),rack)
            if source in live:  # a successful first sweep leaves an empty retry source
                live[target]=live.get(target,0)+live.pop(source)
        elif words[0]=='drop':
            test.assertNotIn(words[1],live,f'cleanup would drop a live stitch: {line}')
        elif words[0]=='knit':
            live[words[2]]=1
        elif words[0]=='tuck':
            live[words[2]]=live.get(words[2],0)+1
    return live


def check_sweeps(test,lines,repeats):
    locations=[line.split()[1] for line in lines if line.startswith('drop ')]
    test.assertTrue(locations)
    width=len(locations)//repeats
    test.assertEqual(len(locations),width*repeats)
    sweep=locations[:width]
    test.assertEqual(sweep,sorted(set(sweep),key=lambda loc:(int(loc[1:]),loc[0])))
    test.assertEqual(locations,sweep*repeats)
    return sweep


class TubularDropTests(unittest.TestCase):
    def test_decrease_cleanup_only_empty_slots_and_ordered_sweeps(self):
        for gauge in (2,3,4):
            for double in (False,True):
                sh=PlatedShapingHelper(16,gauge=gauge,double_transfers=double,drop_repeats=4)
                sh.decrease_both()
                live=check_cleanup(self,sh.instructions,gauge,16)
                self.assertEqual(set(live),{f'{bed}{gauge*n+(bed=="b")}' for bed in ('f','b') for n in range(2,16)})
                sweep=check_sweeps(self,sh.instructions,4)
                self.assertEqual(len(sweep),8)  # two vacated slots, both beds + temporary needles

    def test_repeat_count_and_default_compatibility(self):
        for repeats in (None,1,2,4):
            sh=PlatedShapingHelper(12,drop_repeats=repeats)
            sh.decrease(3,lean='left')
            drops=[x for x in sh.instructions if x.startswith('drop ')]
            self.assertEqual(len(drops),0 if repeats is None else 4*repeats)
        sh=PlatedShapingHelper(12,drop_repeats=3)
        sh.drop_pass(iter(('f10','b3','f2','f10')))
        self.assertEqual(check_sweeps(self,sh.instructions,3),['f2','b3','f10'])
        for value in (0,-1,True,1.5):
            with self.assertRaises(ValueError):
                PlatedShapingHelper(12,drop_repeats=value)

    def test_hole_and_flap_cleanup_do_not_touch_surviving_loops(self):
        for gauge in (2,3):
            plan=dict(format='tubular-design-plan-v3',bed_width=16,holes=[],sections=[],
                      courses=[dict(course=i,section='body',front_stitches=16,stitches=32,
                          bed_runs={'f':[1,16],'b':[1,16]}) for i in range(1,9)])
            plan=with_holes(plan,[Hole(3,((8,9),(7,10),(8,9)))])
            result=compile_tubular_plan(plan,TubularConfig(gauge=gauge,cast_on='none',
                drop_repeats=3,double_transfers=True,finish='flap_bind_off',
                flap=dict(n=12,flap_width=8,flap_rows=8)))
            # Stop before final chain/tag, testing all hole operations and flap joining.
            lines=result.knitout.splitlines()
            end=next(i for i,line in enumerate(lines) if line.startswith(';flap stage 6:'))
            check_cleanup(self,lines[:end],gauge,16)
            join=next(i for i,line in enumerate(lines) if line.startswith(';flap stage 4:'))
            secure=next(i for i,line in enumerate(lines) if line.startswith(';flap stage 5:'))
            self.assertEqual(check_sweeps(self,lines[join:secure],3),[f'f{gauge*n}' for n in range(5,13)])
            with self.assertRaisesRegex(ValueError,'positive integer'):
                compile_tubular_plan(plan,TubularConfig(drop_repeats=0))

    def test_finish_drop_is_one_ordered_sweep_per_repeat(self):
        for double in (False,True):
            sh=PlatedShapingHelper(12,gauge=3,double_transfers=double,drop_repeats=3)
            sh.inhook(5)
            sh.drop_all_tubular(5)
            sweep=check_sweeps(self,sh.instructions,3)
            self.assertEqual(len(sweep),24)
            self.assertEqual(sh.instructions[1],'outhook 5')
