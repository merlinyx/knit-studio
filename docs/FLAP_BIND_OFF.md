# Flap bind-off

Use this finish to knit a front-bed flap at the top of a tubular piece, transfer
its live end onto occupied back-bed stitches, secure those stacked loops, then
chain-bind-off the rest of the tube. The carrier and yarns already active at
the end of the body continue through the flap. Plated groups are supported.

## Automatic sizing in the compiler

```python
from spacer_pipeline.flap_bind_off import FlapBindOffConfig
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan

config = TubularConfig(
    gauge=3,
    carrier=5,
    finish='flap_bind_off',
    flap=FlapBindOffConfig(stitch_gauge=4, row_gauge=6),
)
result = compile_tubular_plan(plan, config)
result.write('generated/flap.k')
print(result.schedule[-1]['flap'])
```

The numbers 4 and 6 are example **measured fabric gauges**, in stitches/inch and
individual flat rows/inch. Measure them for the final yarn, stitch settings and
selected needle spacing. They are not machine needle spacing. The flap's flat
rows may have a different gauge from the tube; use the measured flap row gauge.

The compiler can inherit `stitch_gauge` and `course_gauge` from the plan if
explicit values are omitted. For stitch-pixel plans these may only be default
nominal values, so provide calibration before relying on physical sizing.

For a final range 1..40 and example gauges S=4, R=6, automatic sizing chooses:

- Flap width: 20 live stitches, inclusive f11..f30 (`n=30`).
- Flap rows: 30 individual flat passes, alternating left/right.
- Estimated width and height: 5 × 5 inches.
- Each side opening: 10 remaining front + 10 back stitches = 20 stitches = 5 in.

The automatic flap is centered, keeps at least one live stitch on each side,
and prefers equal side counts. Integer widths and even row counts can require
a rectangular flap and small fit differences.

## Override any dimensions

```python
config = TubularConfig(
    gauge=3, carrier=5, finish='flap_bind_off',
    flap=FlapBindOffConfig(
        n=25, flap_width=10, flap_rows=12,
        stitch_gauge=4, row_gauge=6,
    ),
)
```

`n` is the rightmost **logical front needle**, not a physical machine needle.
`flap_width` is the number of stitches including both endpoints: this example
uses f16..f25. `flap_rows` must be even and at least 2; each pass counts as one
row. Explicit values are respected even if they produce a non-square or
poorly matched flap; estimated errors are reported instead of silently changing
the request. If width and rows are both explicit, fabric gauges are optional
for the direct helper, although they are needed for dimensional estimates.

- Omit `n`: center the specified/calculated flap in the actual final live range.
- Omit `flap_rows`: calculate an even count to approximately match the average
  length of the left and right side openings.
- Specify rows but omit width: derive a width from the remaining side stitches
  and calibrated row/stitch gauges, respecting available space.
- Specify `n` but omit width: try to balance the two side openings; bounds can
  prevent an exact balance.
- Set `has_tag=False` to omit the final tag; the last chain stack is still knitted.

The schedule's `flap` object reports resolved endpoints, row count, width,
left/right side stitch counts, and (when calibrated) estimated width, height,
square error and side-fit errors in inches. Positive fit error means the flap
height exceeds the corresponding side-opening length.

## Exact path

For final range f1..f40 / b1..b40, `n=25`, width 10:

1. Use the existing front chain steps from f40 down to f25. f25 remains live,
   carrying the chain stack; f26..f40 are no longer live.
2. Knit f25→f16, f16→f25, repeating for the requested even row count.
3. Knit f25→f1, then b1→b40. All back stitches remain live.
4. Rack **-1**, transfer f16..f25 onto b16..b25, then reset rack to 0.
   The intended join stacks front flap loops onto existing back loops.
5. Knit b40→b1, then f1→f15, securing all joined back loops.
6. Resume the front chain from f15→f1, chain across the left edge, bind off the
   whole back bed b1→b40, make the existing optional tag, and remove carriers
   individually.

With needle spacing g, front logical i maps to f(g*i), back to b(g*i+1).
Joining corresponding logical indices therefore uses rack -1 at gauges 2,
3 and 4. Ordinary same-bed chain steps still rack by -g. Do not multiply the
measured stitches/inch by g again when calculating the flap width.

The flap's start edge is knitted into the front of the tube and its live end
is joined to the back. This path does **not** attach the flap's side edges to
the remaining side-opening stitches while knitting; those side stitches receive
the chain bind-off. Sizing matches their lengths geometrically.

## Direct helper API

```python
from spacer_pipeline.plated_helper import PlatedShapingHelper

sh = PlatedShapingHelper(width=40, gauge=3)
sh.standard_headers()
sh.start_tubular_carriers(5, courses_per_carrier=2)
for _ in range(12):
    sh.knit_tubular_row(5)
layout = sh.bind_off_flap(
    5, n=25, flap_width=10, flap_rows=12,
    stitch_gauge=4, row_gauge=6,
)
sh.write('generated/manual-flap.k')
```

`bind_off_flap` is also available on the packaged `tube_engine.ShapingHelper`.
Use `PlatedShapingHelper` for a tuple carrier such as `(2,4)`.

## CLI configuration

`flap` can be an ordinary dictionary in Python or an object in the JSON passed
to `tube-compile --config`:

```json
{
  "gauge": 3,
  "carrier": 5,
  "finish": "flap_bind_off",
  "flap": {"stitch_gauge": 4, "row_gauge": 6}
}
```

## Limits and example

The method requires a tube at rack 0, the normal right-side seam position
(next tubular direction `-`), at least four needles per bed, and
`side_slack=False`. The flap is at least two stitches wide and leaves at least
one live needle on each side. Automatic sizing uses the **last** course's
range, including any previous shaping. Existing holes must have closed before
finishing, as required by the tubular plan validator.

Flap passes, traversal, securing and chain/tag steps are finishing instructions,
not extra design courses or part of the body preview. They are mapped by the
final `flap_bind_off` schedule entry; the current image preview shows the body
only. This is an experimental construction: swatch the turns and transfer join,
and check the measured fit before using it on a full piece.

Run from the repository root:

```bash
PYTHONPATH=src .venv/bin/python docs/flap_bind_off_example.py
```

This produces automatic and explicit rectangular flap knitout samples and a
schedule under `generated/flap-bind-off/`. Tests replay live-loop occupancy and
transfer alignment at gauges 2, 3 and 4, for singleton and plated carriers.

## Optional double transfers

Set `TubularConfig(double_transfers=True, finish='flap_bind_off', ...)` to repeat
each selected transfer sweep as a whole before changing the rack position. The default is `False`.
For example, the flap join emits:

```text
rack -1
xfer f30 b31
xfer f33 b34
xfer f30 b31
xfer f33 b34
rack 0
```

The entire ordered loop runs once, then runs again; individual instructions
are not paired. This is a repeated sweep, not a transfer back. If the first succeeds, the second source is empty. Compiler mode
applies only to increases, hole-shaping transfers and the flap’s front-to-back
join. Chain bind-off steps, ordinary outer decreases and cast-on transfers remain
unchanged. No knitting or racking operations are duplicated, and schedule offsets
include the repeated instructions. Existing cast-on transfer repetitions are retained without further duplication.

For direct helper programs, use
`PlatedShapingHelper(width=40, gauge=3, double_transfers=True)` (also supported by
the packaged `ShapingHelper`). To enable retries only for the finishing step,
set `sh.double_transfers = True` immediately before `sh.bind_off_flap(...)`.
The flag changes emitted instructions; machine/backend behavior still needs to
be checked at the intended speed.

Transfer loops for increases repeat separately for each staging/delivery group
at its required rack. Hole decreases stage both edges together, repeat that
staging sweep, then deliver each displacement group at its own rack and repeat
that group. A delivery group containing only one needle necessarily has two
identical adjacent instructions. The flap join repeats its whole needle range
before resetting rack to zero. Regenerate knitout after changing this option.

## Optional drop cleanup after the join

`TubularConfig(drop_repeats=4, ...)` (or the helper constructor's same option)
adds four ordered drop sweeps over the front flap needles immediately after
transfer at rack 0. They should be empty by then; the back join stacks are
preserved and secured by the following back pass. This is independent of
`double_transfers`, and does not add drops to the chain bind-off. The default
`None` preserves prior behavior. Each whole sweep completes before it repeats.
