"""Plated elastic, local hole, then wire; same gauge 3 throughout."""
from pathlib import Path
from spacer_pipeline.tubular import Hole, tubular_plan, with_holes, save_tubular_preview
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan

root = Path(__file__).resolve().parents[2]
plan = tubular_plan(root/'examples/stitch-pixels/tube.png', input_mode='stitch-pixels', sections=[
    dict(name='elastic', start_course=1, end_course=7, color='#e8b86d'),
    dict(name='wire', start_course=8, end_course=10, color='#87b6c8'),
])
plan = with_holes(plan, [Hole(3, ((6,7), (5,8), (5,8), (6,7)))])
config = TubularConfig(gauge=3, carrier=5, cast_on='none', plating_setup_courses=2,
                       section_carriers={'elastic': (2,4), 'wire': 5})
output = root/'generated/plated-elastic'
save_tubular_preview(plan, output/'preview.html')
compile_tubular_plan(plan, config).write(output/'tube.k')
print(output)
