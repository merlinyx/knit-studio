# Tubular pipeline: design and implementation status

## Implemented

- Full side-profile image to explicit tubular design courses.
- Centered, numbered front/back preview, named course sections and hole overlay.
- One-based bed-local needle and course coordinates (`tubular-design-plan-v3`).
- Ordinary tube cast-on, knitting, outer increases/decreases, optional short
  rows and finishing through a snapshot of the wire ShapingHelper.
- Named sections mapped to yarn carriers.
- Experimental local openings on either bed, one opening at a time, within
  a constant-width band. Outward transfers secure removed loops; shrinking
  gaps receive twisted-tuck increases. Traversal reverses around the remaining
  circumference instead of floating across the opening.
- Preflight geometry checks, internal loop-stack occupancy checks for opening
  operations, and a design-course/instruction schedule.

## Coordinates

The input is a filled **full side profile**, not a radius/half-profile image.
Supply maximum diameter, height, circumference stitches/inch and courses/inch.
Each sampled row must contain one contiguous silhouette run. Its width gives
local diameter; circumference = pi × diameter. Round to an even stitch count
and split it equally across the beds. This image geometry layer was written
independently of the original wire image conversion code.

Courses and needles start at **1**. Courses increase bottom-to-top. Let W be
maximum needles per bed. Front headers read 1..W left-to-right; back headers
read W..1. Both beds' JSON `bed_runs` contain the same inclusive logical needle
range. Each range is centered within 1..W; an odd spare needle goes to the
high-numbered end (visually right on front and left on back).

Physical knitout addressing follows the wire helper: front n → f(gauge*n),
back n → b(gauge*n+1). Preview numbers are logical needles, not physical
machine numbers. Old v1/v2 plans are rejected; regenerate them from the image.

`Hole(start_course=3, gaps=((9,10), (8,11), (9,10)), bed="f")` removes the
specified inclusive needle intervals on courses 3, 4 and 5. Course 6 closes
the opening. A default bed of `f` is provided; use `b` for a back-bed opening.
Sections also use one-based inclusive course ranges. Unnamed courses use `body`.

## Compilation scope

Use `compile_tubular_plan(plan, TubularConfig(...))`. Compilation checks the
whole supported episode before returning output; writing is explicit via
`result.write(path)`. It does not mutate the plan. Defaults are gauge 2,
carrier 3, twisted-tuck cast-on with four settling courses, and chain bind-off.
`finish="drop"` is available for matching existing development samples.

Outer edges may change by at most one needle per side per design course.
Both-sided decreases use ShapingHelper's default inset positions; single-sided
decreases merge near the edge. Increases use its left/right edge anchors.
Thus a silhouette does not reproduce every arbitrary shaping placement from
an older procedural pattern. Explicit extra short rows can be requested with
`short_rows_after={course: [{"b": "b", "n": needle}, ...]}`. These are extra
passes, separate from design courses, and cannot overlap an opening episode.

For an opening:

- Keep the outer range and carrier constant from its preceding course through
  its closing course. Outer shaping and material changes can occur elsewhere.
- Leave at least one live needle between the hole and each edge of its bed.
- First and last gaps must be one or two needles wide; wider middle gaps grow
  gradually. Each edge may move at most one needle per course; consecutive
  gaps must overlap. Separate openings may be knitted sequentially.
- Side-slack tucks are not supported during openings.
- A reserved empty opposite-bed needle stages each local transfer; adjacent
  surviving loops receive the removed stitch and are knitted through.

Opening setup positions the carrier with connected partial passes. Closing
seeds the upper bridge and adds a connected recovery pass to restore the normal
seam. Those passes introduce local extra knitting and can affect dimensions.
A carrier change uses the helper's stabilizing round, also extra to the design
courses. These events are explicit in `result.schedule`; image height describes
design courses, not a guarantee of the final knitted height.

Schedule `instruction_start/end` use zero-based instruction offsets with an
exclusive end; `knitout_line_start/end` use one-based inclusive file lines.
Cast-on/settling, every design course, short-row episodes, material transitions,
opening setup/recovery and finishing are separately identifiable.

This is experimental construction code. Tests establish instruction and
occupancy invariants, not material-specific physical stability; swatch opening
joins and elastic/wire transitions before a full lampshade.

## Provenance and regression tests

`src/spacer_pipeline/tube_engine/` is copied from
`../wire_knitting/wire_knitting_code/`, with only imports made package-relative.
The existing spacer engine remains separate and unchanged.

Tests load the original source independently and execute these actual examples,
intercepting their output writes to avoid creating files in the source folder:

- `test_tube` at gauges 2, 3 and 4, including side-slack behavior;
- `test_tube_shortrows`;
- `test_sock`, including outer decreases and short rows.

Comparison strips comments, headers and whitespace but retains all machine
instructions. A further centered decrease/increase and bind-off sequence is
compared with the original helper. These checks test compiler emission, not
image-to-width equivalence. Arbitrary asymmetric increase placement, stranded
colorwork and plating examples are not yet representable by this plan API.
The source-comparison tests require the sibling wire_knitting checkout.

## Next steps

1. Swatch and adjust opening startup, upper-bridge anchoring and recovery.
2. Add a compiler-aware preview of extra partial courses and transitions.
3. Add explicit shaping placement policies, then simultaneous outer shaping
   and openings using a shared live-loop/transfer planner.
4. Add a supplied color-to-name palette for image sections and preserve source
   sampling provenance.
5. Extend to simultaneous openings and flat-component routing. Keep flat and
   tubular traversal planners separate while sharing geometry and primitives.

## Stitch-pixel input mode

`input_mode="stitch-pixels"` bypasses dimensional scaling. Each occupied
source pixel contributes one stitch per bed, and every source row contributes
one design course in bottom-to-top order. Widths are centered into the same
one-based, mirrored needle chart. There is no image downsize limit, per-bed
parity rounding or automatic row insertion. Blank rows and disconnected runs
are rejected for tubular profiles rather than silently discarded. White side
margins do not add stitches. Do not supply diameter/height in this mode.

The plan records `input_mode`. Its diameter and height fields are nominal
estimates from the supplied/default fabric gauges, not a resampling instruction.
Changing those gauges leaves needle ranges and course counts unchanged.
`TubularConfig.gauge` continues to control physical needle spacing separately.

The flat image adapter also supports this mode, retaining the entire canvas,
multiple runs, and unmodified rows. Its row unit remains a spacer block. The
spacer engine's physical addressing is unchanged by selecting pixel input.

## Dedicated cast-on carrier

`TubularConfig.nonwire_caston` is an optional carrier number (1..10). It
performs the selected cast-on method and settling courses independently of
section annotations. Before design course 1, the first section's carrier is
introduced with the helper's stabilization round plus one further tubular round,
then the cast-on carrier is removed. For singleton first-section carriers, the two extra rounds are reported as
`nonwire_caston_transition_extra_courses`. No transition is needed when the
carriers match. `None` preserves the prior behavior. With `cast_on="knit"`,
this prelude matches the original `test_tube(..., nonwire_caston=...)` example;
a regression test compares its machine instructions at gauge 3.

## Plated carrier groups

`PlatedShapingHelper` adapts the packaged helper's knit/tuck/miss and carrier
lifecycle operations to ordered groups, leaving the snapshot's row and transfer
algorithms in place. `TubularConfig` accepts groups for default, section and
cast-on carriers. Lists from JSON are normalized to tuples before planning.
Carrier order is preserved on both beds, and transitions retain shared members.
Internal-hole knitting uses the whole active group, including newly seeded
edge loops. Single-carrier operations retain their original emitted commands.
This does not add a full-gauge-to-sparse loop-remapping transition.


## Sequential plated startup

`plating_setup_courses` (default 2) controls solo rounds per newly introduced
plated-group member. Each carrier is inhooked, knitted solo, and released before
the next is introduced; grouped inhook is no longer used by compiler setup.
With a conventional cast-on on a plated group, the first member casts on and
remaining members receive sequential solo setup. `cast_on="none"` bypasses all
cast-on operations and starts every first-section carrier sequentially with
these solo knit rounds, even on initially empty needles. It disallows a separate
`nonwire_caston`. Startup rounds are extra to the design plan and recorded in
`direct_carrier_setup`. Transition schedule entries report actual `extra_courses`
counts, which can be larger for plating than for singleton transitions.

Grouped carrier removal emits separate `outhook` commands in the supplied order
(e.g. `outhook 2` then `outhook 4`), including transitions and finishing.
