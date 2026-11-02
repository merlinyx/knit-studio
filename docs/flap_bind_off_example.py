"""Run from repo: PYTHONPATH=src .venv/bin/python docs/flap_bind_off_example.py"""
import json
from pathlib import Path
from PIL import Image
from spacer_pipeline.tubular import tubular_plan, save_tubular_preview
from spacer_pipeline.tubular_compiler import TubularConfig
from spacer_pipeline.flap_bind_off import FlapBindOffConfig
from spacer_pipeline.tubular_compiler import compile_tubular_plan
from spacer_pipeline.plated_helper import PlatedShapingHelper

output=Path(__file__).resolve().parents[1]/'generated/flap-bind-off'
output.mkdir(parents=True,exist_ok=True)
Image.new('RGB',(40,12),'black').save(output/'tube-pixels.png')
plan=tubular_plan(output/'tube-pixels.png',input_mode='stitch-pixels')
save_tubular_preview(plan,output/'body-preview.html')
# Example calibration only: substitute measurements at your yarn/stitch size/gauge.
config=TubularConfig(gauge=3,carrier=5,cast_on='none',finish='flap_bind_off',
                    flap=FlapBindOffConfig(stitch_gauge=4,row_gauge=6))
result=compile_tubular_plan(plan,config)
result.write(output/'automatic-flap.k')
(output/'schedule.json').write_text(json.dumps(result.schedule,indent=2)+'\n')
print('Automatic flap:',result.schedule[-1]['flap'])

# Direct helper style with an explicit 10-stitch, 12-pass rectangular flap.
sh=PlatedShapingHelper(width=40,gauge=3)
sh.standard_headers()
sh.start_tubular_carriers(5,courses_per_carrier=2)
for _ in range(12):
    sh.knit_tubular_row(5)
layout=sh.bind_off_flap(5,n=25,flap_width=10,flap_rows=12,
                      stitch_gauge=4,row_gauge=6)
sh.write(str(output/'manual-flap.k'))
print('Explicit flap:',layout)
print('Outputs:',output)
