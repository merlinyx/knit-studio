"""Rectangular plain-flat examples; run from the repository with PYTHONPATH=src.

These adapters reuse geometry only. They do not compile spacer constructions,
internal holes, shaped outlines, sections or material transitions.
"""
from pathlib import Path

from spacer_pipeline.image import image_to_plan
from spacer_pipeline.tubular import tubular_plan
from spacer_pipeline.tube_engine import ShapingHelper


def knit_plain_flat(ranges, output, carrier=3):
    """One single-bed plain pass per input range; rectangular geometry only."""
    ranges = list(ranges)
    if not ranges or any(tuple(r) != tuple(ranges[0]) for r in ranges):
        raise ValueError('this example requires a constant needle range')
    lo, hi = ranges[0]
    if hi-lo+1 < 3:
        raise ValueError('the stack-bind-off tag needs at least three needles')
    sh = ShapingHelper(width=hi-lo+1, is_tubular=False)
    sh.min_n, sh.max_n = lo, hi
    sh.standard_headers()
    sh.cast_on_flat(carrier)
    for _ in ranges:
        sh.knit_flat_row(carrier)
    sh.bind_off_flat(carrier)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sh.write(str(output))
    return output


def panel_to_plain_flat(plan, output, carrier=3):
    if any(len(row.runs) != 1 for row in plan.rows):
        raise ValueError('plain-flat example requires one continuous run per row')
    return knit_plain_flat([(row.runs[0].start, row.runs[0].end) for row in plan.rows], output, carrier)


def tube_to_plain_flat(plan, output, carrier=3, surface='front'):
    if plan.get('format') != 'tubular-design-plan-v3':
        raise ValueError('expected a v3 tubular plan')
    if plan.get('holes'):
        raise ValueError('tubular hole routing cannot be reused for flat knitting')
    if surface == 'front':
        ranges = [tuple(row['bed_runs']['f']) for row in plan['courses']]
    elif surface == 'circumference':
        ranges = [(1, row['stitches']) for row in plan['courses']]
    else:
        raise ValueError('surface must be front or circumference')
    return knit_plain_flat(ranges, output, carrier)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    output = root/'generated/plain-flat'
    panel = image_to_plan(root/'examples/stitch-pixels/flat.png',
                          input_mode='stitch-pixels', needle_offset=1)
    panel_to_plain_flat(panel, output/'panel-plain.k')
    tube = tubular_plan(root/'examples/stitch-pixels/tube.png', input_mode='stitch-pixels')
    tube_to_plain_flat(tube, output/'tube-front-plain.k')
    tube_to_plain_flat(tube, output/'tube-unwrapped-plain.k', surface='circumference')
    print(f'Wrote three ordinary flat knitout examples to {output}')
