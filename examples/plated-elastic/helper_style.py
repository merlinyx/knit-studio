"""Direct helper style: independent knobs for cast-on, elastic and wire.

Run: PYTHONPATH=src .venv/bin/python examples/plated-elastic/helper_style.py
Carrier numbers identify yarn feeders, not material properties.
"""
from pathlib import Path
from spacer_pipeline.plated_helper import PlatedShapingHelper

WIDTH = 30                   # logical stitches per bed
GAUGE = 3                    # same physical spacing throughout
CAST_ON = None               # set to 1 to use separate cast-on yarn
ELASTIC = (2, 4)              # elastic + companion yarn, ordered group
WIRE = 5
ELASTIC_COURSES = 30
WIRE_COURSES = 30

sh = PlatedShapingHelper(width=WIDTH, gauge=GAUGE)
sh.standard_headers()
if CAST_ON is None:
    # inhook 2 -> two solo rounds -> releasehook 2, then the same for 4.
    sh.start_tubular_carriers(ELASTIC, courses_per_carrier=2)
else:
    sh.cast_on_tubular_alt_tuck(CAST_ON, settling_rows=6)
    sh.prep_tubular_colorwork([ELASTIC])
    sh.knit_tubular_row(ELASTIC)
    sh.retire_carriers(CAST_ON, ELASTIC)
for _ in range(ELASTIC_COURSES):
    sh.knit_tubular_row(ELASTIC)

sh.prep_tubular_colorwork([WIRE])
sh.retire_carriers(ELASTIC, WIRE)
for _ in range(WIRE_COURSES):
    sh.knit_tubular_row(WIRE)
sh.bind_off_tubular(WIRE)
output = Path(__file__).resolve().parents[2]/'generated/plated-elastic-helper.k'
output.parent.mkdir(parents=True, exist_ok=True)
sh.write(str(output))
print(output)
