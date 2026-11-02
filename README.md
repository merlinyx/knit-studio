# Knit Studio

Turn a black-and-white pattern image into knitting-machine files (`.k` knitout
and Shima Seiki `.dat`) for **spacer fabric panels** or **tubes / generalized
cylinders** (wire knitting). Most people use the **Knit Studio** app described
first. The command-line pipeline underneath it is documented after that.

> **About this repository.** The Knit Studio app, its packaging, its release
> builds and most of this README were written by **Claude** (Anthropic's AI
> model, Claude Opus 5.5) working in Claude Code with Yuxuan Mei. They are built
> on Yuxuan Mei's spacer and tube knitting pipelines (`src/spacer_pipeline/`,
> apart from `recipe.py`, `settings_schema.py`, `dat.py` and `studio/`).

- [Knit Studio for designers](#knit-studio-for-designers): download and use the app
- [Knit Studio for developers](#knit-studio-for-developers): install from source, recipes, building releases
- [Pipeline reference](#pipeline-reference): how the pipeline works, and its command-line tools

## Knit Studio for designers

### Install

Download the file for your computer from the
[latest release](../../releases/latest):

| Computer | File |
| --- | --- |
| Mac with an Apple chip (M1 or newer) | `Knit-Studio-mac-apple-silicon.dmg` |
| Older Intel Mac | `Knit-Studio-mac-intel.dmg` |
| Windows 10 or 11 | `Knit-Studio-windows.exe` |

**Mac:** open the `.dmg` and drag **Knit Studio** into **Applications**. The
app is not signed with an Apple developer certificate, so the first time you
open it macOS says it "cannot be opened" or "cannot verify the developer":

1. Click **Done** (or **Cancel**).
2. Open **System Settings → Privacy & Security**, scroll down, and click
   **Open Anyway** next to the Knit Studio message. Confirm with your password.

After that it opens normally. If macOS instead says the app "is damaged", open
**Terminal**, run `xattr -cr "/Applications/Knit Studio.app"`, and open the
app again.

**Windows:** double-click `Knit-Studio-windows.exe`. If a blue "Windows
protected your PC" box appears, click **More info → Run anyway**. Windows 11
already has everything the app needs. If no window appears on Windows 10,
install Microsoft's free
[WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).
Without it, Knit Studio opens in your web browser instead.

### Make a pattern

1. Choose **Spacer panel** or **Tube** at the top.
2. **Drop your image** into the *Pattern image* box, or click **Use a sample
   image** to try it out first.
   - Spacer panel: the panel shape in black on white. Tick *Drawing is an
     outline* if you drew only the outline.
   - Tube: the tube's full side profile, filled black on white.
   - Transparent backgrounds count as white.
3. Set **What the image means**:
   - *A drawing to scale*: enter the finished size in inches. The app
     resizes the image to match the gauges.
   - *Exact stitch chart*: every filled pixel is one stitch and every pixel
     row is one row. No size is needed.
4. Check the **gauges** and **yarns**. A yarn setting is a carrier number from
   1 to 10. Tick **Plate** to knit that part with two yarns together, then
   choose the second carrier.
5. **Tubes only:** use **Sections** to give a course range its own yarn (for
   example an elastic base), and **Holes** to add openings. Courses count
   from 1 at the bottom. Hover over the preview to read course and needle
   numbers.
6. The preview updates as you change settings. Warnings are listed above it.
   A red message means the compiler cannot use these settings yet, and
   **Generate files** stays disabled until you fix them.
7. Choose where to **save files**, then click **Generate files**. You get a
   folder named after your design containing:
   - `name.dat`: the file for the knitting machine
   - `name.k`: knitout, the readable form of the same instructions
   - `name-preview.png` or `.html`: the preview
   - `name-recipe.json`: every setting plus the image. Use **Open
     settings…** to bring the design back later, or send this one file to
     someone who needs to reproduce or debug it.

**Presets** (top bar) store yarn, gauge and machine settings for a particular
machine setup. Choose one to apply it. **Save as preset…** saves your current
settings, without the image or its size. **Show advanced settings** (bottom of
the left panel) shows the rarely changed machine options.

Knit Studio remembers your last settings between launches. If something goes
wrong, the log is at `~/Library/Application Support/Knit Studio/knit-studio.log`
(Mac) or `%APPDATA%\Knit Studio\knit-studio.log` (Windows).

## Knit Studio for developers

Requires Python 3.10+.

```bash
pipx install "knit-studio[desktop] @ git+https://github.com/merlinyx/knit-studio.git"
knit-studio            # opens in its own window
knit-studio --browser  # or in your web browser
```

Or work from a clone:

```bash
git clone https://github.com/merlinyx/knit-studio.git
cd knit-studio
python -m venv .venv
.venv/bin/pip install -e ".[desktop]"
.venv/bin/knit-studio
```

Without the `desktop` extra, `knit-studio` opens in the browser. The Python
package is `spacer_pipeline`, and the pipeline's command-line tool is
`spacer-plan`.

### Recipes

The app saves every job as a recipe: one JSON file with the pipeline
(`spacer` or `tube`), the image settings (`image`: keyword arguments of
`image_to_plan` / `tubular_plan`), the compiler settings (`compile`: fields of
`CompileConfig` / `TubularConfig`, with carrier groups as lists such as
`[2, 4]` for plating), tube `sections` and `holes`, and the image itself,
embedded as `image_data`, or given as an `image_path` relative to the recipe.
To run one without the app:

```bash
spacer-plan run my-design-recipe.json --output-dir out/ --dat   # --dat needs Node.js
```

`spacer_pipeline.recipe.run_job()` is the shared entry point for the app and
the command line. `tests/test_recipe.py` checks that it produces exactly the
same `.k` files as the original `image` / `compile` / `tube-preview` /
`tube-compile` commands.

### Adding settings

The app builds its forms from the code. Any new keyword argument of
`image_to_plan` / `tubular_plan`, or new field of `CompileConfig` /
`TubularConfig` / `FlapBindOffConfig`, appears automatically under *More
settings*. To give it a label, help text, group or widget, add an entry in
`HINTS` in `src/spacer_pipeline/settings_schema.py`. Built-in presets live in
`src/spacer_pipeline/studio/presets.json`.

### .dat conversion

`src/spacer_pipeline/studio/static/vendor/knitout-to-dat.js` is an unmodified
copy of the upstream knitout-backend-swg converter (see `THIRD_PARTY/`). The
app runs it inside its own window, so designers do not need Node. The command
line runs it with Node.

### Releasing

Pushing a version tag builds the Mac (Apple Silicon and Intel) and Windows
apps on GitHub Actions and attaches them to a GitHub release:

```bash
git tag v0.2.0 && git push origin v0.2.0
```

To build locally, run `pip install -e ".[build]"` and then
`pyinstaller packaging/knit-studio.spec --noconfirm`. The output goes to
`dist/`. To debug a packaged app, set `KNIT_STUDIO_DEBUG=1`. Requests and a
stack dump then go to the log.

## Pipeline reference

The pipeline converts hand-drawn or CAD panel outlines into a gauge-aware
spacer-fabric row plan, and full side profiles into tubular plans.

The pipeline can compile connected panel outlines to spacer knitout. It also
supports nested, separated runs as explicit spacer short-row episodes instead
of silently flattening them into one centered width.

## Coordinate model

- Rows are listed **bottom-to-top**, matching knitting order.
- A run is an inclusive logical-needle interval such as `1-7`.
- Multiple runs are comma-separated: `0-1, 7-8`.
- The defaults are 9.5 stitches/inch and 13 spacer block rows/inch.
- A spacer block is the unit used as the second value in the existing
  `(width, blocks)` patterns. Internally it contains a face-row pair.

The example in `examples/partial_rows.txt` is:

```text
1-7
0-1, 7-8
0-8
2-6
1-7
0-8
```

## Install for development

```bash
python -m venv .venv
.venv/bin/pip install -e .
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

## Convert run notation

```bash
spacer-plan runs examples/partial_rows.txt \
  --json generated/partial_rows.json \
  --preview generated/partial_rows.png \
  --ascii
```

Orange preview cells are stitches that were inactive on the preceding block
row. They may be ordinary gradual increases or may require an explicit edge
cast-on, depending on how many appear at once.

## Convert an image

For a filled black silhouette on a white background:

```bash
spacer-plan image panel.png \
  --width-in 7.75 --height-in 7 \
  --json generated/panel.json \
  --preview generated/panel-preview.png
```

For a closed black outline with a white interior, add `--fill-outline`.
Use `--invert` for a light shape on a dark background. Input is cropped to the
detected material and then rasterized anisotropically: width uses the stitch
gauge, while height uses the spacer-block gauge.

## Compile a JSON plan to spacer knitout

The defaults match the current acrylic/elastic/conductive setup:

- front carriers: `2,4`
- back carriers: `8,10`
- filler carrier: `7`
- filler pass pairs: `3`
- tuck spacing: `4`
- repeated drops: `2`

```bash
spacer-plan compile generated/wm1.json \
  --output generated/wm1.k \
  --drop-repeats 2
```

Override the threading when needed:

```bash
spacer-plan compile generated/wm1.json \
  --output generated/wm1.k \
  --front-carriers 1,4 \
  --back-carriers 9,10 \
  --filler-carriers 6
```

For ordinary one-run rows, each JSON row becomes one spacer block. An edge can
move by one logical stitch per block using normal increases/decreases. Larger
changes use an exact-range step: overlapping stitches remain live, new edge
stitches are tuck-cast-on, and outgoing stitches receive cast-off waste.

### Separated runs as short rows

Consecutive multi-run rows are interpreted as nested short-row levels over the
current connected base. For example:

```text
1-20
3-6, 15-18
4-5, 16-17
1-20
```

produces right-to-left turns at:

```text
15, 18, 16, 17, 3, 6, 4, 5
```

on both spacer faces. The pass between `17` and `3` keeps the base connected.
This is not interpreted as two independently cast-on islands. Runs within a
group must stay inside the current connected base and nest from outer to inner.

Short-row spacer construction is experimental machine behavior. Knit a small
swatch before running a full panel, especially when plated or conductive yarns
have changed tension. To prohibit multi-run compilation, use
`--multi-run-policy error`.

For a split row, the compiler follows overlap upward to infer an anonymous
continuing component; no semantic region name is required. Terminal nested
runs are knitted as local spacer short-row blocks (front face, back face, then
filler), while the uniquely continuing run remains ordinary spacer fabric.
Carrier travel between terminal runs is knitted as transition stitches to
avoid long floats. Narrow tips automatically reduce the filler tuck spacing so
at least two alternating-bed anchors fit; the tuck-grid offset remains at
least one needle. Short-row runs may be as narrow as two stitches, but their
filler-pair count is reduced automatically before the local tuck pattern would
repeat on the same physical needles. After the bumps finish, their remaining
front- and back-bed loops are dropped immediately so they cannot tether or
distort the continuing component; they do not receive `finish_spacer` or extra
cast-off rows. Filler tucks that have not been knitted through are changed to
misses before these shape drops, avoiding loose tuck-and-drop loops.
Shape-change drops default to two repetitions for reliability with elastic and
plated yarns, including vacated needles after gradual decreases; change this
with `--drop-repeats`.

Image rasterization aligns every gradual increase to an even zero-based row,
where the spacer engine knits the front face first. An odd-row increase is
normally moved one row before its rasterized position. Adjacent increases are
separated by holding the old width for one extra row and moving the odd-row
increase after its original position. These shifts preserve total height
whenever a repeated raster row is available and are recorded in JSON metadata. Use
`--no-align-increase-rows` to retain the raw rasterization.

Pure abrupt expansions merge their alternating-tuck cast-on into the face-row
path instead of making separate tuck-only passes that miss the old center. The
face carriers preserve their existing flow: after finishing on the right, the
next pass knits left through the old width and seeds the new left edge; the
rightward return completes that edge, knits the old width, and seeds the new
right edge; a third leftward pass completes the right cast-on. The filler is
temporarily secured beyond the expanded right edge with a tuck (not a miss),
and that parking tuck is dropped after the next filler pass anchors the yarn
inside the fabric. One transition filler pass follows the face carriers to
their new side, keeping all carrier sets aligned for later ordinary or
short-row blocks. The sequence is mirrored automatically when the carriers
begin on the left. This keeps the old and new widths mechanically connected.
Abrupt shrinks and mixed shift/resize steps retain the existing step behavior.

## What the diagnostics mean

- **split/merge:** connected fabric becomes multiple runs or reconnects.
- **abrupt addition:** the new row overlaps the old row but adds more than two
  stitches; this is a candidate for an explicit edge cast-on or step.
- **resume held:** needles used in an earlier row become active again after a
  gap. The plan preserves this fact without yet choosing a short-row or other
  loop-holding implementation.
- **new island/disconnected row:** there is no vertical overlap. The pipeline
  does not pretend this is a short row; it records that an independent cast-on
  or a separate construction decision is required.

## Repository layout

- `src/spacer_pipeline/model.py` — run, row, and panel data structures
- `src/spacer_pipeline/parser.py` — compact text notation
- `src/spacer_pipeline/image.py` — threshold, outline fill, gauge scaling
- `src/spacer_pipeline/analysis.py` — connectivity and cast-on diagnostics
- `src/spacer_pipeline/preview.py` — ASCII and PNG grid previews
- `src/spacer_pipeline/engine/` — standalone snapshot of the existing spacer
  knitout engine, with imports made package-relative
- `src/spacer_pipeline/tubular.py`, `tubular_compiler.py`, `tube_engine/` —
  tube sampling, holes and the tubular knitout compiler
- `src/spacer_pipeline/recipe.py` — recipes and `run_job()`, shared by the app
  and `spacer-plan run`
- `src/spacer_pipeline/settings_schema.py` — the app's settings forms
- `src/spacer_pipeline/studio/` — the Knit Studio app (local server and web UI)
- `packaging/` — PyInstaller build of the desktop app
- `docs/API_REFERENCE.md` — copied helper API reference

The compiler intentionally does not treat a never-connected run as an
independent fabric island. Such geometry still needs a separate construction
policy and carrier/cast-on decision.

## Experimental tubular design preview

This separate preview path accepts a **filled full side profile** on white.
It converts sampled diameter to circumference; it does not treat image width
as stitch count. The separate `tube-compile` command emits tubular knitout. Gauges here mean circumference stitches/inch
and design courses/inch, not spacer blocks. Existing spacer commands are unchanged.

```bash
spacer-plan tube-preview examples/tubular/lampshade-profile.png \
  --diameter-in 4 --height-in 3 --stitch-gauge 4 --course-gauge 8 \
  --spec examples/lampshade-sections.json \
  --html examples/tubular/lampshade-preview.html \
  --json examples/tubular/lampshade-plan.json
```

Open the HTML in a browser. Scroll the chart horizontally as needed and hover
cells for course, stitch, bed and section. The specification names inclusive
course ranges and supplies display colors; source image colors are not yet
interpreted as sections. Hole intervals are inclusive, one per consecutive
course. Courses and needles start at 1. Front headers increase left-to-right; back headers decrease left-to-right. Each bed’s live interval is centered within its fixed range. The hole
is a design overlay, not a mechanically validated knitting construction.
See [the implementation plan](docs/TUBULAR_PLAN.md) for coordinate conventions,
limitations and subsequent milestones.

### Preview first, then specify holes in Python

Run `PYTHONPATH=src .venv/bin/python examples/tubular/preview_lampshade.py`.
The example saves a base preview, then uses `Hole(start_course=3, gaps=..., bed="f")`
and `with_holes(plan, holes)` to save a separate overlay preview. `with_holes`
returns a copy and checks gaps against each course’s centered live intervals.
Sections remain named course ranges. The flat image workflow remains the
existing `image` command; the tubular workflow uses a full side profile.

### Compile a tubular plan

```python
from spacer_pipeline.tubular import Hole, with_holes
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan

plan = with_holes(plan, [Hole(
    start_course=3, gaps=((9, 10), (8, 11), (8, 11), (9, 10)), bed="f",
)])
result = compile_tubular_plan(plan, TubularConfig(
    carrier=6, section_carriers={"elastic base": 1, "wire body": 6},
))
result.write("lampshade.k")
```

The Python example now also writes `lampshade.k` and `lampshade-schedule.json`.
Its bottom band is constant-width so the opening finishes before outer shaping
and the wire transition begin.

For JSON plans/configuration:

```bash
spacer-plan tube-compile examples/tubular/lampshade-plan.json \
  --config examples/tubular/compile-config.json \
  --output generated/lampshade.k --schedule generated/lampshade-schedule.json
```

Hole knitting is experimental. The first compiler requires constant outer
width/carrier during an opening, one opening at a time, and gradual hole edges.
Outer shaping is supported elsewhere. The schedule identifies extra opening
setup/recovery passes, settling courses and carrier stabilization rounds;
these are not included in the design-course height. See the implementation
plan for exact limits and compatibility-test coverage.

## Exact stitch-pixel input

Select `--input-mode stitch-pixels` or `input_mode="stitch-pixels"` in Python.
Omit physical dimensions in this mode. No cropping, image resizing, stitch-count
rounding or automatic increase-row alignment is applied.

- **Tubular:** each filled pixel is one logical stitch **on each bed**. An
  N-pixel run gives N front + N back stitches. Each source row is one design
  course; rows are read bottom-to-top, and widths are centered as before.
  Every source row must have one contiguous filled run; omit blank top/bottom
  padding. Compilation still requires at least four stitches per bed.
- **Flat/spacer:** each filled pixel is one logical stitch in the panel plan;
  separated runs and blank pixels retain their source positions. Each image
  row is one **spacer block**, not an individual machine pass. Blank rows and
  margins are preserved. Use `--needle-offset 1` to label source column zero
  as logical needle 1; the existing flat default remains zero.

Thresholding, inversion and outline filling are still available on the flat
image command. In pixel mode the physical fabric gauges annotate nominal
sizes only; they do not change stitch counts. Machine spacing remains separate:
`TubularConfig(gauge=3)` uses three-needle spacing throughout the tube.

```bash
spacer-plan tube-preview examples/stitch-pixels/tube.png \
  --input-mode stitch-pixels --html generated/pixel-tube.html \
  --json generated/pixel-tube.json

spacer-plan image examples/stitch-pixels/flat.png \
  --input-mode stitch-pixels --needle-offset 1 \
  --json generated/pixel-flat.json --preview generated/pixel-flat.png
```

Run `PYTHONPATH=src .venv/bin/python examples/stitch-pixels/compile_pixels.py`
for a complete Python example: preview the tube, add its hole, compile with
elastic/wire carriers at gauge 3, and also preview/compile a flat spacer swatch.
The dimensional input mode remains the default and retains its existing
scaling/alignment behavior. Exact pixel geometry still has to satisfy each
compiler's shaping and connectivity constraints.

## Flat, spacer and tubular usage guide

See [Using image plans for spacer, tubular and ordinary flat knitting](docs/USAGE_FLAT_AND_TUBULAR.md)
for a construction comparison, pixel/dimensional inputs, carrier sections,
tubular holes, and runnable ordinary-flat examples from both kinds of plan.

For an additional cast-on yarn independent of the first section, use
`TubularConfig(nonwire_caston=2, cast_on="knit", ...)`. The cast-on and two
transition courses precede design row 1; hole/section numbering stays unchanged.
See the usage guide's dedicated cast-on-carrier example.

Tubular carrier settings also accept ordered groups for plating, for example
`section_carriers={"elastic": (2, 4), "wire": 5}` (JSON: `[2, 4]`). See the
usage guide and `examples/plated-elastic/` for compiler and direct-helper
examples that combine two yarns in the elastic section.

For direct sequential plated startup, use `cast_on="none", plating_setup_courses=2`.
The first section's carriers enter one at a time, each knitting two solo tubular
rounds and releasing its hook before plating begins. No cast-on waste is emitted.
See the usage guide and updated `examples/plated-elastic/` scripts.

Grouped carrier removal emits separate `outhook` commands in the supplied order
(e.g. `outhook 2` then `outhook 4`), including transitions and finishing.

For a flap joined across the top of a tube, use `finish="flap_bind_off"` with
`FlapBindOffConfig`. See [Flap bind-off](docs/FLAP_BIND_OFF.md) for automatic
square/rectangular sizing, explicit overrides, the exact path, and runnable
compiler/helper examples.

Optional transfer retries: `TubularConfig(double_transfers=True, ...)` repeats
whole transfer sweeps for increases, hole shaping and the flap join. Each loop
completes before it is repeated at the same rack. Chain
bind-off, outer decreases and cast-on transfers remain unchanged. Direct helpers
accept the same constructor option. Single transfer remains the default; see
[Flap bind-off](docs/FLAP_BIND_OFF.md#optional-double-transfers).

Tubular drop cleanup is independently configurable:
`TubularConfig(drop_repeats=4, double_transfers=True, ...)`.
After decreases, hole shaping and flap joining it drops only vacated source/
staging needles. Drops are sorted by physical needle position across both beds
and the entire sweep is repeated, rather than repeating each needle in place.
`drop_repeats=None` (default) preserves prior output; a positive integer enables
cleanup. Explicit cast-on patch and final drop sweeps also use the count.
