# Using image plans for spacer, tubular and ordinary flat knitting

Run the commands below from the `spacer-image-pipeline` repository. With the
existing development environment, Python scripts run as:

```bash
PYTHONPATH=src .venv/bin/python path/to/script.py
```

## Choose the fabric construction

| Goal | Geometry | Knitout construction |
| --- | --- | --- |
| Flat spacer fabric | `PanelPlan` from `image_to_plan` | `compile_panel_plan`: front/back faces and filler passes |
| Ordinary tube | `tubular_plan` | `compile_tubular_plan`: courses around front/back beds |
| Ordinary flat fabric | Panel geometry or selected tube geometry | Flat `ShapingHelper`: one front-bed pass per design row |

A flat outline does not automatically mean ordinary single-bed knitting.
The CLI `compile` command produces **spacer fabric**. `tube-compile` produces
**tubular fabric**. Neither currently provides a plain-flat switch.
The runnable adapters below use the existing helper's flat mode directly.

## Image input: dimensions or exact stitch pixels

### Physical dimensions

For a panel:

```python
from spacer_pipeline.image import image_to_plan

panel = image_to_plan(
    'panel.png', width_inches=4, height_inches=2,
    stitch_gauge=8, row_gauge=12,
)
```

Width uses stitches/inch; height uses rows/inch. When compiling spacer fabric,
that row unit is a spacer block. If using the ordinary-flat adapter, supply
ordinary flat courses/inch instead. Default dimensional panel sampling aligns
gradual increases for spacer compilation; set `align_increase_rows=False` when
planning ordinary flat geometry.

For a tube, supply a filled **full side profile**:

```python
from spacer_pipeline.tubular import tubular_plan

tube = tubular_plan(
    'profile.png', diameter_inches=4, height_inches=3,
    stitch_gauge=8, course_gauge=12,
)
```

Here `stitch_gauge` measures stitches/inch around the circumference. The pipeline
converts sampled diameter to circumference, then divides stitches across the
beds. This conversion is separate from machine needle spacing.

### Exact stitch pixels

```python
panel = image_to_plan('panel-pixels.png', input_mode='stitch-pixels', needle_offset=1)
tube = tubular_plan('tube-pixels.png', input_mode='stitch-pixels')
```

Do not provide physical dimensions in this mode.

- Panel: one filled pixel = one logical stitch; one image row = one plan row.
  Source positions, separated runs and blank rows are retained. The default
  column offset is 0; `needle_offset=1` makes the first column needle 1.
- Tube: one filled pixel = one stitch **per bed**; one image row = one design
  course. A 12-pixel run gives 12 front + 12 back stitches. Each row must have
  one filled run; remove blank top/bottom padding. Widths are centered.

Both read image rows bottom-to-top. Pixel mode does not resize or automatically
align rows. Fabric gauges annotate nominal sizes without changing stitch counts.

## Compile a flat spacer panel

```python
from spacer_pipeline.compiler import CompileConfig, compile_panel_plan
from spacer_pipeline.preview import save_preview

save_preview(panel, 'generated/panel-preview.png')
panel.write_json('generated/panel.json')
compile_panel_plan(panel, 'generated/panel-spacer.k', CompileConfig())
```

Each plan row becomes a spacer block with face and filler operations. Existing
carrier settings, shaping policies and nested short-row behavior apply; see the
main README for their configuration. Multiple runs do not automatically mean
independent plain-flat panels or an open hole.

## Compile a tube, sections and a hole

```python
from spacer_pipeline.tubular import Hole, tubular_plan, with_holes, save_tubular_preview
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan

# This example image is 12 pixels wide and 10 rows tall.
tube = tubular_plan('examples/stitch-pixels/tube.png', input_mode='stitch-pixels', sections=[
    dict(name='elastic', start_course=1, end_course=7, color='#e8b86d'),
    dict(name='wire', start_course=8, end_course=10, color='#87b6c8'),
])
save_tubular_preview(tube, 'generated/tube-base.html')
tube = with_holes(tube, [Hole(
    start_course=3, gaps=((6, 7), (5, 8), (5, 8), (6, 7)), bed='f',
)])
save_tubular_preview(tube, 'generated/tube-hole.html')
result = compile_tubular_plan(tube, TubularConfig(
    gauge=3, carrier=6, section_carriers={'elastic': 1, 'wire': 6},
))
result.write('generated/tube.k')
```

Courses, section boundaries and hole needles are one-based. Front preview
numbers increase left-to-right; back numbers decrease left-to-right. A hole
names its bed and inclusive logical needle intervals. The example opens on
course 3 and closes on course 7, before changing to wire on course 8.

`gauge=2` (default), 3 or 4 controls machine spacing throughout the tube.
It is independent of measured fabric gauge and pixel counts. Openings currently
require constant outer width and carrier from the preceding through closing
course, gradual hole edges and one opening at a time. Extra settling,
material-transition and opening setup/recovery passes appear in `result.schedule`.
See [the tubular design document](TUBULAR_PLAN.md) for construction limits.

## Ordinary flat knitting from a panel plan

The executable example is [examples/plain-flat/from_plans.py](../examples/plain-flat/from_plans.py).
Run it to generate three ordinary-flat knitout files:

```bash
PYTHONPATH=src .venv/bin/python examples/plain-flat/from_plans.py
```

To use its adapter in your own script, add the example folder to the import path
(or copy the small adapter into your script):

```python
import sys
sys.path.insert(0, 'examples/plain-flat')  # relative to repository root
from from_plans import panel_to_plain_flat, tube_to_plain_flat

panel = image_to_plan(
    'examples/stitch-pixels/flat.png', input_mode='stitch-pixels', needle_offset=1,
)
panel_to_plain_flat(panel, 'generated/panel-plain.k', carrier=3)
```

This example is an 8-stitch × 8-row rectangle. The adapter interprets each plan
row as **one ordinary front-bed knitting pass**, rather than a spacer block.
It casts on with alternating tucks and finishes with the helper's stack bind-off.
The bind-off may add a positioning row and a small tag.

The adapter explicitly requires a constant single run of at least three
needles. It rejects shaped ranges, split/empty rows and narrow rectangles; it
uses one carrier and does not apply section or material-transition annotations.

## Ordinary flat knitting from tubular geometry

Use a tube **without holes** for either of these conversions:

```python
tube = tubular_plan('examples/stitch-pixels/tube.png', input_mode='stitch-pixels')

# One face: 12 stitches wide, 10 ordinary flat rows.
tube_to_plain_flat(tube, 'generated/front-flat.k', surface='front')

# Both faces opened into one sheet: 24 stitches wide, 10 ordinary flat rows.
tube_to_plain_flat(tube, 'generated/circumference-flat.k', surface='circumference')
```

`front` uses the front bed's logical range and produces one face's width.
`circumference` concatenates the stitch counts of both faces into one front-bed
range starting at 1. It gives the full unwrapped width, but does not preserve
two separate bed identities. Both are flat sheets; neither closes a tube seam.

These rectangular adapters use geometry only. A tubular hole's one-carrier
route around the remaining circumference cannot be used for a flat sheet:
a flat internal hole separates the row into two regions. The adapter rejects
such holes. General shaped flat-plan compilation and flat-hole routing are
future work.

## Direct flat helper: rows and controlled shaping

For flat patterns needing increases, decreases or short rows, use the helper
explicitly instead of the rectangular adapters:

```python
from pathlib import Path
from spacer_pipeline.tube_engine import ShapingHelper

sh = ShapingHelper(width=12, is_tubular=False)
sh.standard_headers()
sh.cast_on_flat(carrier=3)
for _ in range(6):
    sh.knit_flat_row(3)

# Transfer-only decrease; knit afterward to secure the stacked loops.
sh.decrease(position=sh.min_n + 2, lean='left')
for _ in range(2):
    sh.knit_flat_row(3)

# increase() includes its own row and requires next direction '-'.
assert sh.direction[3] == '-'
sh.increase(positions=sh.min_n, carrier=3, lean='left')
sh.knit_flat_row(3)  # '+' pass, restoring next direction '-'

sh.bind_off_flat(3)
Path('generated').mkdir(exist_ok=True)
sh.write('generated/shaped-flat.k')
```

Flat mode knits adjacent physical front needles `f1`, `f2`, etc.; its addressing
ignores the tubular `gauge` setting. `is_tubular=False` therefore does not create
a flat sheet at three-needle spacing. Bind-off and shaping use the back bed
for transfers, even though the body is single-bed fabric.

`simple_bind_off('f', carrier)` is a different finish: waste/settling rows,
carrier removal and dropping all loops. Use `bind_off_flat` for the stack
bind-off shown here. Machine-swatch new material settings and hole joins.

## Separate non-wire cast-on yarn

`nonwire_caston` selects a dedicated cast-on carrier without adding a design row:

```python
config = TubularConfig(
    gauge=3,
    carrier=6,
    nonwire_caston=2,             # carrier 2 holds the separate cast-on yarn
    cast_on='knit',              # cast_on_tubular_knit, as in the old wire example
    section_carriers={'elastic': 1, 'wire': 6},
)
result = compile_tubular_plan(tube, config)
```

Carrier 2 knits the cast-on and settling courses using the selected `cast_on`
method. The compiler then brings in the first section's carrier (1 here),
knits two stabilization courses with that carrier, and removes carrier 2.
Design course 1 starts afterward with carrier 1. The later wire section still
switches to carrier 6. Cast-on and transition courses are listed in the schedule
and do not change section or hole row numbers.

`nonwire_caston=None` retains the original default: cast on with the first
section's carrier. If the separate cast-on carrier equals that carrier, the
compiler skips the redundant transition. This option selects a carrier number,
not a yarn material; thread the intended yarn into that carrier yourself.

## Plated elastic sections

An ordered carrier tuple/list knits both yarns into the same stitch:

```python
config = TubularConfig(
    gauge=3, carrier=5, nonwire_caston=1, cast_on='alt_tuck',
    section_carriers={'elastic': (2, 4), 'wire': 5},
)
result = compile_tubular_plan(tube, config)
```

The elastic section emits commands like `knit - f30 2 4`, while wire emits
`knit - f30 5`. The same groups are used for tucks, misses, hole increases and
bind-off when needed. JSON uses `[2, 4]` instead of `(2, 4)`. A default carrier
or non-wire cast-on carrier can also be a group. Carrier groups must be nonempty
and contain distinct numbers from 1 through 10. The compiler introduces new
members sequentially with two solo rounds each and retires only departing members; changing `(2,4)` to `4`
keeps carrier 4 active. New members of a plated group each get the configured solo setup rounds before
plating begins. A singleton section retains the helper’s one-round introduction. The plan's geometry and hole numbering remain unchanged.

Order is preserved as supplied on both beds. This combines yarns but does not
promise face-specific plating order on a particular machine. The original
helper's `knit_tubular_plating_row(pattern, a, b)` has separate front/back order
logic if that behavior is needed. Adding a companion yarn changes the fabric;
it does not automatically increase stitch size or loosen the elastic.

Runnable examples (from the repository root):

```bash
PYTHONPATH=src .venv/bin/python examples/plated-elastic/helper_style.py
PYTHONPATH=src .venv/bin/python examples/plated-elastic/image_with_hole.py
```

The first uses the original procedural helper style through a small carrier-group
adapter. By default it introduces 2 and 4 sequentially without a separate cast-on,
knits a plated `(2,4)` elastic band, then
switches to wire on 5, all at gauge 3. The second compiles an image plan with a
hole in the plated band. Outputs go in `generated/`.

For your own direct program:

```python
from spacer_pipeline.plated_helper import PlatedShapingHelper
sh = PlatedShapingHelper(width=30, gauge=3)
sh.standard_headers()
sh.cast_on_tubular_alt_tuck(1, settling_rows=6)
sh.prep_tubular_colorwork([(2, 4)])
sh.retire_carriers(1, (2, 4))
for _ in range(30):
    sh.knit_tubular_row((2, 4))
sh.prep_tubular_colorwork([5])
sh.retire_carriers((2, 4), 5)
for _ in range(30):
    sh.knit_tubular_row(5)
sh.bind_off_tubular(5)
```

Use tuples for carrier groups passed to high-level helper methods, because the
helper's direction state uses the group as a dictionary key. Low-level writer
operations and compiler configuration also accept lists.

### Why dropping the unused full-gauge loops is a different construction

Knitting with no yarn on a live needle is a drop: it releases its loop, allowing
that stitch column to ladder down. It does not merge the loop into a retained
wire needle. A full-gauge `f1..30, b1..30` tube also has a different bed layout
from the helper's `f(g*n), b(g*n+1)` mapping; setting `gauge=1` would not produce
that exact layout. The compiler currently supports gauge 2, 3 and 4 only.

A secured dense-to-sparse transition would need an explicit loop consolidation
or bind-off/remapping strategy. Full-gauge occupied opposite-bed needles leave
less temporary transfer space than the current sparse layout. The present
compiler does not plan that transition. The plated examples retain the same
needle layout throughout so they can be swatched independently of that work.


## Sequential setup without cast-on waste

```python
config = TubularConfig(
    gauge=3,
    carrier=5,
    cast_on="none",
    plating_setup_courses=2,
    section_carriers={"elastic": (2, 4), "wire": 5},
)
```

No separate cast-on yarn, tuck cast-on, cast-on patch or settling courses are
emitted. Instead startup is exactly:

1. `inhook 2`, knit two complete tubular rounds with 2, `releasehook 2`.
2. `inhook 4`, knit two complete tubular rounds with 4, `releasehook 4`.
3. Begin design course 1 with `(2,4)` plated knitting.

Here a round/course is a front pass plus a back pass, so "two rounds" means
four machine passes per carrier. The four solo startup rounds are recorded as
`direct_carrier_setup` before design course 1, preserving hole/section indexing.
`settling_courses` is ignored in this mode. `nonwire_caston` must be `None`.
Starting with knit operations on empty needles is a direct-knit startup whose
loop capture should be checked on the machine with the intended yarns.

For manual sequencing in helper style:

```python
sh = PlatedShapingHelper(width=30, gauge=3)
sh.standard_headers()
sh.start_tubular_carriers((2, 4), courses_per_carrier=2)
for _ in range(30):
    sh.knit_tubular_row((2, 4))
```

The equivalent explicit sequence is `inhook(2)`, two `knit_tubular_row(2)`
calls, `releasehook(2)`, followed by those calls for 4. Both finish at the normal
right-side seam. `start_tubular_carriers` leaves already active members alone.
`prep_tubular_colorwork` also introduces new plated members sequentially;
`sh.plating_setup_courses` controls its solo rounds (default 2). When a plated
section itself performs a conventional cast-on, the first member casts on,
and subsequent members enter through this sequential setup.

Grouped carrier removal emits separate `outhook` commands in the supplied order
(e.g. `outhook 2` then `outhook 4`), including transitions and finishing.

## Finish a tube with a flap

`finish="flap_bind_off"` adds a front-bed flap and joins its live end onto the
back bed before completing the chain bind-off. It supports calibrated automatic
sizing and manual `n`, inclusive `flap_width`, and even `flap_rows` overrides.
See [Flap bind-off](FLAP_BIND_OFF.md) for the path, sizing rules and examples.

### Double-transfer option

Use `TubularConfig(double_transfers=True, ...)` or construct the packaged
`ShapingHelper` / `PlatedShapingHelper` with `double_transfers=True` to repeat each
selected transfer loop as a complete sweep at the same rack setting: increases, hole shaping
and the flap front-to-back join. Chain bind-off, outer decreases and cast-on
transfers remain single (apart from any pre-existing explicit repetitions). The
separate spacer compiler/engine is unchanged. See the flap guide for examples.

### Tubular drop repetitions

```python
config = TubularConfig(
    gauge=3,
    carrier=5,
    drop_repeats=4,
    double_transfers=True,  # independent; may also be False
)
```

`drop_repeats` can be `None` (default, legacy behavior) or a positive integer.
An integer enables post-transfer cleanup on vacated decrease slots, hole source/
staging needles, and the front flap edge after it is transferred onto the back.
Surviving stitches and back-bed flap join stacks are not dropped. Cleanup occurs
at rack 0 after the relevant transfers, before knitting resumes. Outer decreases
clean original and temporary needles in the vacated logical slots.

Each sweep deduplicates locations and sorts by physical needle number across
both beds. It completes the whole sweep before repeating it. For example,
with two locations and count 2, output is `drop f3`, `drop b4`, `drop f3`,
`drop b4`. This avoids per-needle repetitions interrupting a sweep and allows
monotone drop sequences; the backend still determines actual carriage passes.
Both edges of a two-sided decrease are collected into a single cleanup sweep.

The setting also applies to cast-on patch cleanup and `finish="drop"` teardown.
Existing side-slack drop/tuck operations remain unchanged. The low-level
`drop(location)` method emits one instruction; for an explicit repeated batch,
use `sh.drop_pass(locations)`.

Direct helpers support the same constructor option:

```python
sh = PlatedShapingHelper(width=40, gauge=3, drop_repeats=4)
```

Single and double transfer modes use the same drop count. Setting 1 enables
one cleanup sweep; `None` adds no new shape cleanup and retains legacy explicit
drop ordering/count. JSON configuration uses `null` for `None`. This option
adds instruction-level retries; test the release behavior with the actual yarn
and machine speed.
