import unittest
from copy import deepcopy
from spacer_pipeline.flap_bind_off import FlapBindOffConfig, resolve_flap
from spacer_pipeline.plated_helper import PlatedShapingHelper
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan


class FlapSizingTests(unittest.TestCase):
    def test_automatic_square_and_offset_range(self):
        layout = resolve_flap(1,40,FlapBindOffConfig(stitch_gauge=4,row_gauge=6))
        self.assertEqual((layout['flap_start'],layout['n'],layout['flap_width'],layout['flap_rows']), (11,30,20,30))
        self.assertEqual(layout['width_inches'], layout['height_inches'])
        self.assertEqual(layout['left_fit_error_inches'], 0)
        self.assertEqual(layout['right_fit_error_inches'], 0)
        shifted = resolve_flap(6,45,FlapBindOffConfig(stitch_gauge=4,row_gauge=6))
        self.assertEqual((shifted['flap_start'],shifted['n']), (16,35))

    def test_overrides_even_rounding_and_rectangular_fit(self):
        layout = resolve_flap(1,40,FlapBindOffConfig(n=25,flap_width=10,stitch_gauge=4,row_gauge=6))
        self.assertEqual((layout['flap_start'],layout['flap_rows']), (16,46))  # 45 rounds up to even
        self.assertAlmostEqual(layout['left_fit_error_inches'], 46/6-30/4)
        layout = resolve_flap(1,40,FlapBindOffConfig(flap_rows=30,stitch_gauge=4,row_gauge=6))
        self.assertEqual(layout['flap_width'],20)
        manual = resolve_flap(1,40,FlapBindOffConfig(n=25,flap_width=10,flap_rows=12))
        self.assertEqual(manual['flap_rows'],12)
        self.assertNotIn('height_inches',manual)
        rounded = resolve_flap(1,30,FlapBindOffConfig(stitch_gauge=4,row_gauge=8))
        self.assertEqual(rounded['left_stitches'],rounded['right_stitches'])
        self.assertEqual(rounded['flap_rows']%2,0)

    def test_invalid_inputs(self):
        for config in (FlapBindOffConfig(), FlapBindOffConfig(n=40),
                       FlapBindOffConfig(n=10,flap_width=12,flap_rows=12),
                       FlapBindOffConfig(flap_width=1,flap_rows=12),
                       FlapBindOffConfig(flap_width=10,flap_rows=11),
                       FlapBindOffConfig(flap_width=True,flap_rows=12),
                       FlapBindOffConfig(stitch_gauge=0,row_gauge=6)):
            with self.subTest(config=config), self.assertRaises(ValueError):
                resolve_flap(1,40,config)


class FlapConstructionTests(unittest.TestCase):
    def simulate(self, instructions, gauge, lo, hi):
        live = {f'{bed}{gauge*n+(bed=="b")}':1 for bed in ('f','b') for n in range(lo,hi+1)}
        rack=0
        snapshots={}
        for line in instructions:
            words=line.split()
            if not words:
                continue
            if line.startswith(';flap stage'):
                snapshots[int(words[2].rstrip(':'))]=dict(live)
            if words[0]=='rack':
                rack=float(words[1])
                self.assertLessEqual(abs(rack),gauge)
            elif words[0]=='xfer':
                source,target=words[1:]
                self.assertIn(source,live,line)
                f,b=(source,target) if source[0]=='f' else (target,source)
                self.assertEqual(int(f[1:])-int(b[1:]),rack,line)
                live[target]=live.get(target,0)+live.pop(source)
            elif words[0]=='knit':
                self.assertIn(words[2],live,line)
                live[words[2]]=1
            elif words[0]=='tuck':
                live[words[2]]=live.get(words[2],0)+1
        return live,snapshots

    def test_confirmed_path_live_loops_and_alignment_all_gauges(self):
        for gauge in (2,3,4):
            for carrier in (5,(2,4)):
                with self.subTest(gauge=gauge,carrier=carrier):
                    sh=PlatedShapingHelper(40,gauge=gauge)
                    sh.inhook(carrier)
                    layout=sh.bind_off_flap(carrier,n=25,flap_width=10,flap_rows=12)
                    live,stages=self.simulate(sh.instructions,gauge,1,40)
                    # Initial partial chain leaves f1..f25 and all back loops.
                    self.assertEqual({x for x in stages[2] if x.startswith('f')}, {f'f{gauge*n}' for n in range(1,26)})
                    # Join: front f16..f25 vacated; their corresponding back loops stacked.
                    self.assertTrue(all(f'f{gauge*n}' not in stages[5] for n in range(16,26)))
                    self.assertTrue(all(stages[5][f'b{gauge*n+1}']==2 for n in range(16,26)))
                    self.assertTrue(all(count==1 for count in stages[6].values()))
                    # All original body stitches have been bound off, leaving only the tag.
                    self.assertEqual(set(live), {f'f{gauge*0}', *(f'b{gauge*n+1}' for n in (38,39,40))})
                    body=sh.instructions
                    a=next(i for i,x in enumerate(body) if x.startswith(';flap stage 2'))
                    b=next(i for i,x in enumerate(body) if x.startswith(';flap stage 3'))
                    passes=[x for x in body[a+1:b] if x.startswith('knit ')]
                    self.assertEqual(len(passes),12*10)
                    self.assertEqual(passes[0].split()[1:3],['-',f'f{25*gauge}'])
                    self.assertEqual(passes[-1].split()[1:3],['+',f'f{25*gauge}'])
                    self.assertFalse(sh.active_carriers)
                    self.assertEqual(layout['flap_start'],16)

    def test_compiler_config_dict_and_schedule_does_not_mutate_plan(self):
        plan=dict(format='tubular-design-plan-v3',bed_width=40,holes=[],sections=[],stitch_gauge=4,course_gauge=6,
                  courses=[dict(course=i,section='body',front_stitches=40,stitches=80,
                  bed_runs={'f':[1,40],'b':[1,40]}) for i in range(1,4)])
        before=deepcopy(plan)
        result=compile_tubular_plan(plan,TubularConfig(gauge=3,cast_on='none',finish='flap_bind_off'))
        self.assertEqual(result.schedule[-1]['flap']['flap_rows'],30)
        self.assertEqual(result.schedule[-1]['flap']['flap_width'],20)
        self.assertEqual(plan,before)
        custom=compile_tubular_plan(plan,TubularConfig(finish='flap_bind_off',
            flap={'n':25,'flap_width':10,'flap_rows':12,'has_tag':False}))
        self.assertEqual(custom.schedule[-1]['flap']['n'],25)

    def test_validation_before_emission_and_side_slack_rejected(self):
        sh=PlatedShapingHelper(40)
        sh.inhook(3)
        before=list(sh.instructions)
        with self.assertRaises(ValueError):
            sh.bind_off_flap(3,n=25,flap_width=10,flap_rows=11)
        self.assertEqual(sh.instructions,before)

        sh.side_slack=True
        with self.assertRaisesRegex(ValueError, 'side_slack'):
            sh.bind_off_flap(3,n=25,flap_width=10,flap_rows=12)
        self.assertEqual(sh.instructions,before)


    def test_compiler_sizes_from_last_shaped_course(self):
        ranges=[(1,40),(2,39),(3,38)]
        plan=dict(format='tubular-design-plan-v3',bed_width=40,holes=[],sections=[],stitch_gauge=4,course_gauge=6,
                  courses=[dict(course=i,section='body',front_stitches=b-a+1,stitches=2*(b-a+1),
                  bed_runs={'f':[a,b],'b':[a,b]}) for i,(a,b) in enumerate(ranges,1)])
        result=compile_tubular_plan(plan,TubularConfig(finish='flap_bind_off'))
        layout=result.schedule[-1]['flap']
        self.assertEqual((layout['flap_start'],layout['n'],layout['flap_width']), (12,29,18))
        self.assertEqual(layout['left_stitches'],18)
        self.assertEqual(layout['right_stitches'],18)

    def test_smallest_flap_and_no_tag_finish(self):
        sh=PlatedShapingHelper(4,gauge=3)
        sh.inhook(5)
        layout=sh.bind_off_flap(5,flap_width=2,flap_rows=2,has_tag=False)
        self.assertEqual((layout['flap_start'],layout['n']), (2,3))
        live,_=self.simulate(sh.instructions,3,1,4)
        self.assertEqual(live,{'f0':1,'b13':1})
        self.assertEqual(sh.instructions[-2:],['knit + b13 5','outhook 5'])
