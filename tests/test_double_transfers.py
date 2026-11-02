import unittest
from spacer_pipeline.plated_helper import PlatedShapingHelper
from spacer_pipeline.tube_engine import ShapingHelper
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan


def collapse_retries(test, text):
    lines=text.splitlines()
    result=[]
    index=0
    while index<len(lines):
        line=lines[index]
        result.append(line)
        if line.startswith('xfer '):
            end=index
            while end<len(lines) and lines[end].startswith('xfer '):
                end+=1
            for length in range(1,(end-index)//2+1):
                block=lines[index:index+length]
                if block==lines[index+length:index+2*length]:
                    result.extend(block[1:])
                    index+=2*length-1
                    break
        index+=1
    return '\n'.join(result)


class DoubleTransferTests(unittest.TestCase):
    def test_direct_helper_repeats_in_place(self):
        for helper in (ShapingHelper, PlatedShapingHelper):
            sh=helper(12,gauge=3,double_transfers=True)
            sh.rack(-1)
            sh.xfer_pass((('f30','b31'),('f33','b34')))
            sh.rack(0)
            self.assertEqual(sh.instructions,['rack -1','xfer f30 b31','xfer f33 b34','xfer f30 b31','xfer f33 b34','rack 0'])
            single=helper(12,double_transfers=True)
            single.xfer('f30','b30')
            self.assertEqual(single.instructions,['xfer f30 b30'])
            with self.assertRaisesRegex(ValueError,'boolean'):
                helper(12,double_transfers=2)

    def test_compiler_flap_and_shaping_match_after_collapsing_retries(self):
        ranges=[(1,20),(2,19),(1,20)]
        plan=dict(format='tubular-design-plan-v3',bed_width=20,holes=[],sections=[],
                  courses=[dict(course=i,section='body',front_stitches=b-a+1,stitches=2*(b-a+1),
                      bed_runs={'f':[a,b],'b':[a,b]}) for i,(a,b) in enumerate(ranges,1)])
        for gauge in (2,3):
            for finish in ('bind_off','flap_bind_off'):
                with self.subTest(gauge=gauge,finish=finish):
                    fields=dict(gauge=gauge,carrier=(2,4),cast_on='none',finish=finish)
                    if finish=='flap_bind_off':
                        fields['flap']=dict(n=14,flap_width=8,flap_rows=12)
                    single=compile_tubular_plan(plan,TubularConfig(**fields))
                    double=compile_tubular_plan(plan,TubularConfig(**fields,double_transfers=True))
                    self.assertEqual(collapse_retries(self,double.knitout),single.knitout)
                    def operations(result, kind, course=None):
                        event=next(e for e in result.schedule if e['kind']==kind and (course is None or e['course']==course))
                        return result.knitout.splitlines()[event['knitout_line_start']-1:event['knitout_line_end']]
                    # Ordinary outer decrease and chain bind-off stay single.
                    self.assertEqual(operations(single,'tubular_course',2),operations(double,'tubular_course',2))
                    inc1=operations(single,'tubular_course',3)
                    inc2=operations(double,'tubular_course',3)
                    self.assertEqual(sum(x.startswith('xfer ') for x in inc2),2*sum(x.startswith('xfer ') for x in inc1))
                    prefix=[f'xfer f{gauge*n} b{gauge*n}' for n in range(2,20)]
                    start=inc2.index(prefix[0])
                    self.assertEqual(inc2[start:start+2*len(prefix)],prefix+prefix)
                    finish1=operations(single,finish)
                    finish2=operations(double,finish)
                    if finish=='bind_off':
                        self.assertEqual(finish1,finish2)
                    else:
                        for stage in (1,2,3,5,6):
                            def segment(lines):
                                a=next(i for i,x in enumerate(lines) if x.startswith(f';flap stage {stage}:'))
                                b=next((i for i in range(a+1,len(lines)) if lines[i].startswith(';flap stage ')),len(lines))
                                return lines[a:b]
                            self.assertEqual(segment(finish1),segment(finish2))
                        self.assertEqual(sum(x.startswith('xfer ') for x in finish2)-sum(x.startswith('xfer ') for x in finish1),8)
                        join=[f'xfer f{gauge*n} b{gauge*n+1}' for n in range(7,15)]
                        start=finish2.index(join[0])
                        self.assertEqual(finish2[start:start+16],join+join)
                    self.assertEqual(double.schedule[-1]['knitout_line_end'],len(double.knitout.splitlines()))
        with self.assertRaisesRegex(ValueError,'boolean'):
            compile_tubular_plan(plan,TubularConfig(double_transfers=1))

    def test_hole_decrease_transfers_retry_in_place(self):
        from spacer_pipeline.tubular import Hole, with_holes
        plan=dict(format='tubular-design-plan-v3',bed_width=16,holes=[],sections=[],
                  courses=[dict(course=i,section='body',front_stitches=16,stitches=32,
                      bed_runs={'f':[1,16],'b':[1,16]}) for i in range(1,9)])
        plan=with_holes(plan,[Hole(3,((8,9),(7,10),(8,9)))])
        single=compile_tubular_plan(plan,TubularConfig(cast_on='none'))
        double=compile_tubular_plan(plan,TubularConfig(cast_on='none',double_transfers=True))
        self.assertEqual(collapse_retries(self,double.knitout),single.knitout)
        for event in double.schedule:
            if event['kind'] in ('opening_setup','open_course'):
                lines=double.knitout.splitlines()[event['knitout_line_start']-1:event['knitout_line_end']]
                first=next((i for i,line in enumerate(lines) if line.startswith('xfer ')),None)
                if first is not None:
                    self.assertNotEqual(lines[first],lines[first+1])
                    self.assertEqual(lines[first:first+2],lines[first+2:first+4])
