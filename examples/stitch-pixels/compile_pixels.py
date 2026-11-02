"""Run from the repo with PYTHONPATH=src .venv/bin/python examples/stitch-pixels/compile_pixels.py."""
from pathlib import Path
from spacer_pipeline.image import image_to_plan
from spacer_pipeline.preview import save_preview
from spacer_pipeline.compiler import compile_panel_plan
from spacer_pipeline.tubular import Hole, tubular_plan, with_holes, save_tubular_preview
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan

folder = Path(__file__).resolve().parent
# 12 pixels wide -> exactly 12 needles on EACH bed; 10 rows -> 10 design courses.
plan = tubular_plan(folder/'tube.png', input_mode='stitch-pixels', sections=[
    dict(name='elastic', start_course=1, end_course=7, color='#e8b86d'),
    dict(name='wire', start_course=8, end_course=10, color='#87b6c8'),
])
save_tubular_preview(plan, folder/'tube-base.html')
plan = with_holes(plan, [Hole(3, ((6, 7), (5, 8), (5, 8), (6, 7)), bed='f')])
save_tubular_preview(plan, folder/'tube-hole.html')
# Use the same machine spacing for both materials. Change 3 to 2 or 4 to swatch.
compile_tubular_plan(plan, TubularConfig(gauge=3, carrier=6,
    section_carriers={'elastic': 1, 'wire': 6})).write(folder/'tube.k')

# 8 pixels wide -> exactly 8 logical stitches; 8 rows -> 8 spacer BLOCKS.
flat = image_to_plan(folder/'flat.png', input_mode='stitch-pixels', needle_offset=1)
flat.write_json(folder/'flat-plan.json')
save_preview(flat, folder/'flat-preview.png')
compile_panel_plan(flat, folder/'flat.k')
