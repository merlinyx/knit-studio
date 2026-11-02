# ShapingHelper & KnittingHelper API Reference

This document covers the public methods available in `shaping_helper.py` and `knitting_helper.py` for your final project. All shaping operations (tubular knitting, increases, decreases, short rows) live in `ShapingHelper`, which inherits flat-knitting utilities from `KnittingHelper`, which in turn inherits low-level knitout instruction methods from `KnitoutWriter`.

---

## Quick Start

```python
from shaping_helper import ShapingHelper

# Tubular (half-gauge tube):
sh = ShapingHelper(width=20, is_tubular=True)
sh.standard_headers()
sh.cast_on_all_needle_transition(carrier=3, settling_rows=4)
for _ in range(30):
    sh.knit_tubular_row(carrier=3)
sh.bind_off_tubular(carrier=3)
sh.write("my_tube.k")

# Flat:
sh = ShapingHelper(width=20, is_tubular=False)
sh.standard_headers()
sh.cast_on_flat(carrier=1)
for _ in range(20):
    sh.knit_flat_row(carrier=1)
sh.simple_bind_off("f", 1)
sh.write("my_flat.k")
```

---

## Construction

### `ShapingHelper(width, is_tubular=True)`

Creates a new shaping helper instance.

| Parameter | Type | Description |
|-----------|------|-------------|
| `width` | int | Number of logical stitches (minimum 4 for tubular, 2 for flat) |
| `is_tubular` | bool | `True` for half-gauge tubular knitting, `False` for flat |

**Key state tracked automatically:**

- `self.min_n` / `self.max_n` — current leftmost/rightmost logical needle indices (start at 1 and `width`)
- `self.width` — current stitch count (`max_n - min_n + 1`), updates as you increase/decrease
- `self.direction[carrier]` — current knitting direction for each carrier (`"+"` or `"-"`)

---

## Cast-On Methods

### `cast_on_all_needle_transition(carrier, settling_rows=4)`

**Mode:** Tubular only

Recommended tubular cast-on. Casts on at full gauge on the front bed, knits settling rows, then transfers odd-position stitches to the back bed at rack 0 to reach half-gauge layout. Avoids racking during the cast-on stage.

After this call, the carrier direction is `"-"` and the fabric is ready for `knit_tubular_row()`.

| Parameter | Type | Description |
|-----------|------|-------------|
| `carrier` | int | Yarn carrier number |
| `settling_rows` | int | Rows before transitioning (default 4, forced even) |

### `cast_on_flat(carrier)`

**Mode:** Flat only

Alternating-tuck cast-on on the front bed. Handles `inhook`/`releasehook` automatically. After this call, the carrier direction is `"-"`.

---

## Row Knitting

### `knit_tubular_row(carrier)`

**Mode:** Tubular only

Knits one full tubular row (front pass + back pass). Automatically respects and maintains the carrier's current direction.

**Direction behavior:** The direction does NOT flip after a tubular row. If direction is `"-"`, it knits front right-to-left then back left-to-right, and direction stays `"-"` for the next call. This is by design (follows J-30.js convention).

### `knit_flat_row(carrier)`

**Mode:** Flat only

Knits one flat row on the front bed. Direction flips after each call (`"-"` becomes `"+"` and vice versa).

### `knit_body_row(carrier)`

Convenience method: calls `knit_tubular_row` or `knit_flat_row` depending on mode.

---

## Shaping: Increase

### `increase(positions, carrier, lean="right")`

Increases by one or more stitches in a single row. **This method knits a row with the increases embedded** — do NOT call `knit_tubular_row` or `knit_flat_row` separately for this row.

| Parameter | Type | Description |
|-----------|------|-------------|
| `positions` | int or list of ints | Logical needle index(es) where new stitches appear |
| `carrier` | int | Yarn carrier to use |
| `lean` | `"right"` or `"left"` | Direction stitches shift to make room |

**Direction requirement:** Carrier direction MUST be `"-"` when calling this method.

**After the call:**

- **Flat:** direction becomes `"+"`. Call `knit_flat_row(carrier)` to get back to `"-"` for the next increase.
- **Tubular:** direction stays `"-"`. You can call another increase immediately, or knit a settling row.

**How lean works:**

- `lean="right"`: Stitches from `p..max_n` shift rightward, opening a gap at each position. `max_n` grows by the number of positions.
- `lean="left"`: Stitches from `min_n..p` shift leftward, opening a gap at each position. `min_n` shrinks by the number of positions.

**Mechanics (both flat and tubular):** Uses a lace.js-style transfer strategy — all stitches move to the back bed first, then return to the front at their new (shifted) positions. A twisted tuck (`miss -`, `tuck +`, `miss -`) anchors a new loop at each empty needle during the knit row. No splits are used.

**Practical notes:** For tubular, avoid more than 1 increase per side per row — large racking values needed for multi-position half-gauge transfers can cause dropped stitches. Single increases per row are reliable. For flat, multi-position increases (2 at a time) work well.

**Example — increase 2 at a time:**

```python
# Flat: increase 2 stitches on the right side
sh.increase(positions=[sh.max_n - 2, sh.max_n], carrier=1, lean="right")
sh.knit_flat_row(carrier=1)  # settling row, direction back to "-"

# Tubular: increase 1 stitch
sh.increase(positions=3, carrier=3, lean="right")
sh.knit_tubular_row(carrier=3)  # optional settling row
```

---

## Shaping: Decrease

### `decrease(position, lean="left")`

Decreases by one stitch at the given position. **This is a pure transfer operation — no carrier is needed.** The caller must knit a settling row afterward.

| Parameter | Type | Description |
|-----------|------|-------------|
| `position` | int | Logical needle index where stitches merge |
| `lean` | `"left"` or `"right"` | Which side's stitches shift inward |

**No direction requirement.** Decrease is purely mechanical (transfers only).

- `lean="left"`: Shifts `min_n..position-1` rightward, stacking onto `position`. `min_n` increases by 1.
- `lean="right"`: Shifts `position+1..max_n` leftward, stacking onto `position`. `max_n` decreases by 1.

```python
# Decrease on the left edge
sh.decrease(position=sh.min_n + 2, lean="left")
sh.knit_tubular_row(carrier=3)  # settling row

# Decrease on the right edge
sh.decrease(position=sh.max_n - 2, lean="right")
sh.knit_tubular_row(carrier=3)  # settling row
```

### `decrease_both(left_position=None, right_position=None)`

Decreases on both edges in one call. If positions are omitted, defaults to ~25% inset from each edge. Also a pure transfer operation.

```python
sh.decrease_both()  # auto positions
sh.knit_tubular_row(carrier=3)
```

---

## Shaping: Short Rows

### `short_rows(turns, carrier)`

**Mode:** Tubular only

Performs a series of short-row turns on a tube. The carrier walks around the tube knitting each stitch until reaching a turn point, where it tucks and reverses.

| Parameter | Type | Description |
|-----------|------|-------------|
| `turns` | list of dicts | Each dict has `"b"` (bed: `"f"` or `"b"`) and `"n"` (logical needle index) |
| `carrier` | int | Yarn carrier to use |

The method automatically finishes the last row and returns the carrier to the starting position `(max_n, "f")`.

```python
sh.short_rows([
    {"b": "b", "n": 8},   # turn on back bed at needle 8
    {"b": "b", "n": 3},   # turn on back bed at needle 3
    {"b": "b", "n": sh.max_n},  # turn at right edge
    {"b": "b", "n": sh.min_n + 1},  # turn near left edge
], carrier=3)
```

### `short_row_flat(work_min, work_max, carrier)`

**Mode:** Flat only

Knits only needles in `[work_min, work_max]`, tucks at the boundary to prevent a hole, then flips direction.

| Parameter | Type | Description |
|-----------|------|-------------|
| `work_min` | int | Leftmost working needle (absolute index) |
| `work_max` | int | Rightmost working needle (absolute index) |
| `carrier` | int | Yarn carrier to use |

```python
# Progressive short rows to create a wedge
for inset in range(1, 4):
    sh.short_row_flat(sh.min_n + inset, sh.max_n - inset, carrier=1)
    sh.short_row_flat(sh.min_n + inset, sh.max_n - inset, carrier=1)
```

---

## Bind-Off & Teardown

### `bind_off_tubular(carrier)`

**Mode:** Tubular only

Chain bind-off for tubular fabric (translated from J-30.js). Binds off front bed right-to-left, then back bed left-to-right, with a small security tag. Takes some time to knit.

### `bind_off_flat(carrier)`

**Mode:** Flat only

Stack bind-off on the front bed (delegates to `stack_bind_off`).

### `simple_bind_off(bed, carrier)`

Quick bind-off: knits waste rows, outhooks carrier, drops all stitches.

### `drop_all_tubular(carrier)`

**Mode:** Tubular only

Fast teardown: outhooks the carrier and drops every loop on both beds. Use this during development/testing when you don't need a proper bind-off.

### `bind_off_body(carrier)`

Convenience: calls `bind_off_tubular` or `bind_off_flat` depending on mode.

---

## Tubular Colorwork (Stranded & Plating)

These methods add colorwork capability to tubular (half-gauge) knitting. Two techniques are supported: stranded (with floats) and plating (two carriers per stitch).

### `prep_tubular_colorwork(carriers)`

**Mode:** Tubular only

Brings in additional carriers for colorwork. The main carrier (used for cast-on) should already be active. Each new carrier is inhook'd and stabilized with one tubular round.

| Parameter | Type | Description |
|-----------|------|-------------|
| `carriers` | list of ints | All carrier numbers used in the pattern (including the already-active main carrier) |

```python
carriers = [3, 4]  # carrier 3 is already active from cast-on
sh.prep_tubular_colorwork(carriers)  # brings in carrier 4
```

### `knit_tubular_colorwork_row(front_pattern, back_pattern=None)`

**Mode:** Tubular only

Knits one tubular colorwork row using the stranded technique. Each carrier traverses the full tube (front + back), knitting at positions assigned to it and missing at other positions. Floats form inside the tube. Similar to HW3's `knit_stranded_colorwork` but for half-gauge tubes.

Front and back beds can have independent patterns, allowing different designs on each side of the tube.

| Parameter | Type | Description |
|-----------|------|-------------|
| `front_pattern` | list of ints | Carrier number per front-bed stitch position, length == `width`. All carriers must be active. |
| `back_pattern` | list of ints or None | Carrier number per back-bed stitch position, length == `width`. If `None`, uses `front_pattern` for both sides. |

Direction stays unchanged after this call.

```python
# Same pattern on front and back (backward compatible):
for row_idx in range(10):
    pattern_row = [3 if (row_idx + col) % 2 == 0 else 4 for col in range(sh.width)]
    sh.knit_tubular_colorwork_row(pattern_row)

# Different patterns on front and back:
for row_idx in range(10):
    front_row = [3 if (row_idx + col) % 2 == 0 else 4 for col in range(sh.width)]
    back_row = [3 if col < sh.width // 2 else 4 for col in range(sh.width)]
    sh.knit_tubular_colorwork_row(front_row, back_row)
```

### `knit_tubular_plating_row(pattern_row, carrier_a, carrier_b)`

**Mode:** Tubular only

Knits one tubular colorwork row using the plating technique. Both carriers travel together in every stitch. The carrier order in the knitout instruction determines which color shows on the face:

- **Front bed:** first carrier listed shows on the face (outside of tube)
- **Back bed:** carrier order is automatically reversed so the same color appears on the outside

| Parameter | Type | Description |
|-----------|------|-------------|
| `pattern_row` | list of ints | Which carrier shows on the outside at each position (each must be `carrier_a` or `carrier_b`), length == `width` |
| `carrier_a` | int | First carrier number |
| `carrier_b` | int | Second carrier number |

Both carriers must be active. Direction stays unchanged.

```python
# Vertical stripes: carrier 3 for first half, carrier 4 for second half
pattern_row = [3 if col < sh.width // 2 else 4 for col in range(sh.width)]
sh.knit_tubular_plating_row(pattern_row, carrier_a=3, carrier_b=4)
```

### `end_tubular_colorwork(carriers, main_carrier)`

Ends a colorwork section by outhooking all carriers except the main carrier.

| Parameter | Type | Description |
|-----------|------|-------------|
| `carriers` | list of ints | All carrier numbers used in the pattern |
| `main_carrier` | int | The carrier to keep active |

**Complete colorwork example:**

```python
sh.cast_on_all_needle_transition(carrier=3, settling_rows=4)
for _ in range(10):
    sh.knit_tubular_row(carrier=3)

# Colorwork section
carriers = [3, 4]
sh.prep_tubular_colorwork(carriers)
for row_idx in range(10):
    pattern_row = [3 if (row_idx + col) % 2 == 0 else 4 for col in range(sh.width)]
    sh.knit_tubular_colorwork_row(pattern_row)
sh.end_tubular_colorwork(carriers, main_carrier=3)

for _ in range(10):
    sh.knit_tubular_row(carrier=3)
```

---

## Tubular Ribbing

### `knit_tubular_rib_row(kp_pattern, carrier)`

**Mode:** Tubular only

Knits one tubular row with a knit/purl ribbing pattern. Similar to HW2's `array_to_kp_cols()` but for half-gauge tubes.

Each column is either knit (0) or purl (1) as seen from the outside of the tube. The pattern applies consistently around the entire tube.

| Parameter | Type | Description |
|-----------|------|-------------|
| `kp_pattern` | list of 0/1 | One entry per column, length == `width`. 0 = knit (V shows), 1 = purl (bump shows) |
| `carrier` | int | Yarn carrier to use |

Direction stays unchanged after this call.

**How it works (for direction `"-"`):**

1. Transfer front purl stitches: `f{2n}` → `b{2n}` (empty in half gauge, no racking needed)
2. Knit front pass: knit stitches on `f{2n}`, purl stitches on `b{2n}`
3. Restore front purls (`b{2n}` → `f{2n}`), transfer back knits to front (`b{2n+1}` → `f{2n+1}`)
4. Knit back pass: knit stitches on `f{2n+1}`, purl stitches on `b{2n+1}`
5. Restore back knits to back bed (`f{2n+1}` → `b{2n+1}`)

After the row, all stitches return to standard half-gauge positions.

```python
# 1x1 rib
kp_1x1 = [i % 2 for i in range(sh.width)]  # [0, 1, 0, 1, ...]
for _ in range(20):
    sh.knit_tubular_rib_row(kp_1x1, carrier=3)

# 2x2 rib
kp_2x2 = [0 if (i // 2) % 2 == 0 else 1 for i in range(sh.width)]
for _ in range(20):
    sh.knit_tubular_rib_row(kp_2x2, carrier=3)
```

**Mixing rib and plain rows:**

```python
# Ribbed cuff, then plain body
kp_pattern = [i % 2 for i in range(sh.width)]
for _ in range(15):
    sh.knit_tubular_rib_row(kp_pattern, carrier=3)
for _ in range(30):
    sh.knit_tubular_row(carrier=3)
```

---

## Experimental Cast-On

### `cast_on_tubular_tuck_experimental(carrier, settling_rows=4)`

**Mode:** Tubular only

**WARNING:** This is experimental.

An alternative cast-on based on the rainbow-tj.js / image-tj.js approach. Instead of tucking, it **knits** on all needles alternating between front and back beds in two passes. This places loops on both beds immediately without the criss-cross yarn path of an alternating-tuck cast-on. Then it transitions to half-gauge by dropping the unwanted positions.

| Parameter | Type | Description |
|-----------|------|-------------|
| `carrier` | int | Yarn carrier to use |
| `settling_rows` | int | Tubular settling rows after cast-on (default 4, forced even) |

**Steps:**

1. Knit right-to-left (`"-"`), alternating front and back beds each needle (full gauge, all needles on both beds)
2. Knit left-to-right (`"+"`), alternating back and front (reversed beds from pass 1)
3. Drop unwanted positions to reach half-gauge: drop `f{2n+1}` and `b{2n}`, keeping only `f{2n}` and `b{2n+1}`
4. Knit tubular settling rows in standard half-gauge layout

After this call, the fabric is in standard half-gauge layout and ready for `knit_tubular_row()`. Direction is `"-"`.

```python
sh = ShapingHelper(width=10, is_tubular=True)
sh.standard_headers()
sh.cast_on_tubular_tuck_experimental(carrier=3, settling_rows=4)
for _ in range(20):
    sh.knit_tubular_row(carrier=3)
```

---

## Direction Management Summary

Understanding carrier direction is critical for authoring patterns with these helpers.

| Method | Direction requirement | Direction after |
|--------|----------------------|-----------------|
| `knit_tubular_row` | Any | Unchanged |
| `knit_flat_row` | Any | Flipped |
| `increase` | Must be `"-"` | Flat: `"+"` / Tubular: `"-"` |
| `decrease` | None (no carrier) | Unchanged |
| `short_rows` | Any | Returns to start state |
| `short_row_flat` | Any | Flipped |
| `knit_tubular_colorwork_row` | Any | Unchanged |
| `knit_tubular_plating_row` | Any | Unchanged |
| `knit_tubular_rib_row` | Any | Unchanged |

**Common pattern for repeated flat increases:**

```python
# After cast-on + even number of rows, direction is "-"
for i in range(3):
    sh.increase(positions=sh.max_n, carrier=1, lean="right")
    # direction is now "+", need to flip back to "-"
    sh.knit_flat_row(carrier=1)  # settling row, direction -> "-"
```

**Common pattern for tubular increases:**

```python
# Direction is "-" (standard for tubular)
sh.increase(positions=5, carrier=3, lean="right")
# direction is still "-", can increase again or knit
sh.knit_tubular_row(carrier=3)  # optional settling
```

---

## Half-Gauge Needle Addressing

For tubular mode, the helper automatically translates logical needle indices to physical positions:

- Front bed: logical needle `n` -> physical `f{2*n}` (even positions)
- Back bed: logical needle `n` -> physical `b{2*n+1}` (odd positions)

You never need to think about this translation when using the high-level methods. It only matters if you're writing custom low-level knitout instructions alongside the helper. In that case, you'd want to use the private method `_loc(bed, n)` to obtain the physical position of that needle.

---

## KnittingHelper Reference (Flat Knitting)

If your project is primarily flat knitting (single bed, no shaping), you can use `KnittingHelper` directly. It provides all the building blocks for flat fabric, texture patterns, and colorwork.

### `KnittingHelper(width)`

Creates a flat knitting helper.

| Parameter | Type | Description |
|-----------|------|-------------|
| `width` | int | Number of stitches (minimum 2) |

State tracked: `self.min_n` (starts at 1), `self.max_n` (starts at `width`), `self.direction[carrier]` (starts at `"-"` for all carriers).

**Quick start (flat knitting with KnittingHelper directly):**

```python
from knitting_helper import KnittingHelper

kh = KnittingHelper(width=20)
kh.standard_headers()
kh.inhook(1)
kh.cast_on(1)
kh.knit_waste("f", 1)
kh.releasehook(1)

for _ in range(20):
    kh.knit_row("f", 1)

kh.outhook(1)
kh.drop_all("f")
kh.write("my_flat.k")
```

---

### Setup & Headers

#### `standard_headers()`

Adds standard knitout file headers (Position: Center, Width: 450). Call this before any knitting operations.

---

### Cast-On

#### `cast_on(carrier)`

Alternating-tuck cast-on on the front bed. The carrier must already be active (call `self.inhook(carrier)` first). After this call, direction is `"-"`.

**Note:** Unlike `ShapingHelper.cast_on_flat()`, this does NOT handle `inhook`/`releasehook` for you. You manage carrier activation yourself.

```python
kh.inhook(1)
kh.cast_on(1)
kh.knit_waste("f", 1)  # stabilize before releasing
kh.releasehook(1)
```

---

### Row Knitting

#### `knit_row(bed, carrier, op_indices=None)`

Knits one full-width pass on the specified bed, respecting the carrier's current direction, then flips direction.

| Parameter | Type | Description |
|-----------|------|-------------|
| `bed` | `"f"` or `"b"` | Which bed to knit on |
| `carrier` | int | Yarn carrier to use |
| `op_indices` | iterable or None | If provided, only knit on these needle indices (default: all needles `min_n..max_n`) |

Direction flips after every call. If direction is `"-"`, knits right-to-left; if `"+"`, knits left-to-right.

```python
kh.knit_row("f", 1)           # full row on front bed
kh.knit_row("b", 1)           # full row on back bed
kh.knit_row("f", 1, op_indices=range(5, 15))  # partial row
```

#### `knit_waste(bed, carrier, waste_rows=10)`

Knits waste/stabilization rows. Always rounds up to an even number so the carrier ends on the same side it started.

| Parameter | Type | Description |
|-----------|------|-------------|
| `bed` | `"f"` or `"b"` | Which bed to knit on |
| `carrier` | int | Yarn carrier to use |
| `waste_rows` | int | Number of rows (default 10, forced even) |

---

### Drop & Bind-Off

#### `drop_all(bed="f")`

Drops all stitches on the specified bed from `min_n` through `max_n`.

#### `drop_all_both(margin=0)`

Drops all stitches on both front and back beds. The `margin` parameter extends the drop range beyond `min_n`/`max_n` by that many needles on each side (useful after birdseye which may leave loops on extended needles).

#### `simple_bind_off(bed, carrier)`

Quick bind-off: knits waste rows to push fabric down, outhooks the carrier, then drops all stitches.

```python
kh.simple_bind_off("f", 1)
```

#### `stack_bind_off(carrier, min_n=None, max_n=None)`

Chain-style stack bind-off on the front bed (translated from `rectangle-bindoff.js`). Produces a clean bound edge. The carrier direction will be adjusted automatically if needed.

| Parameter | Type | Description |
|-----------|------|-------------|
| `carrier` | int | Yarn carrier to use (must be active) |
| `min_n` | int or None | Leftmost needle (default: `self.min_n`) |
| `max_n` | int or None | Rightmost needle (default: `self.max_n`) |

---

### Texture Patterns (HW2)

#### `knit_kp_rows(rand_array, carrier)`

Knit/purl rows pattern. Each element in the array controls one row: `0` = knit row (front bed), `1` = purl row (back bed). Transfers stitches between beds as needed.

| Parameter | Type | Description |
|-----------|------|-------------|
| `rand_array` | list of 0/1 | One entry per row |
| `carrier` | int | Yarn carrier (must be active) |

```python
import random
pattern = [random.randint(0, 1) for _ in range(20)]
kh.knit_kp_rows(pattern, 1)
```

#### `knit_kp_cols(rand_array, carrier, height=20)`

Knit/purl columns pattern. Each element controls one column: `0` = knit (front), `1` = purl (back). The pattern repeats for `height` rows.

| Parameter | Type | Description |
|-----------|------|-------------|
| `rand_array` | list of 0/1 | One entry per column (length must equal `width`) |
| `carrier` | int | Yarn carrier (must be active) |
| `height` | int | Number of pattern rows (default 20) |

```python
cols = [random.randint(0, 1) for _ in range(20)]
kh.knit_kp_cols(cols, 1, height=30)
```

#### `knit_color_stripes(rand_array, carrier_a, carrier_b)`

Color stripe rows. Each element controls which carrier knits that row: `0` = `carrier_a`, `1` = `carrier_b`. Both carriers must already be active.

| Parameter | Type | Description |
|-----------|------|-------------|
| `rand_array` | list of 0/1 | One entry per row |
| `carrier_a` | int | First carrier (for 0 values) |
| `carrier_b` | int | Second carrier (for 1 values) |

```python
kh.inhook(2)
kh.knit_row("f", 2)
kh.releasehook(2)
stripes = [random.randint(0, 1) for _ in range(20)]
kh.knit_color_stripes(stripes, 1, 2)
```

---

### Stranded Colorwork (HW3)

#### `prep_stranded_colorwork(pattern)`

Prepares for colorwork: inhooks all carriers found in the pattern, casts on with the first carrier, and knits waste. Call this instead of doing manual cast-on when using colorwork.

#### `knit_stranded_colorwork(pattern)`

Knits a colorwork section on the front bed. Each cell in the 2D pattern array specifies which carrier knits that stitch. Unused carriers float on the back. The pattern is knitted bottom-to-top (last row in the array = first row knitted).

| Parameter | Type | Description |
|-----------|------|-------------|
| `pattern` | 2D list of ints | Shape `(rows, width)`, each value is a carrier number |

All carriers referenced must already be active.

```python
# 3-color pattern, 10 rows x 20 columns
pattern = [[random.choice([1, 2, 3]) for _ in range(20)] for _ in range(10)]
kh.prep_stranded_colorwork(pattern)
kh.knit_stranded_colorwork(pattern)
kh.end_stranded_colorwork(pattern)
```

#### `end_stranded_colorwork(pattern)`

Finishes colorwork: outhooks non-primary carriers, knits waste with the primary carrier, outhooks, drops.

---

### Birdseye Jacquard (HW4)

#### `doubleknit_cast_on(carriers)`

Double-knit cast-on for birdseye jacquard. Inhooks all carriers and performs the interlocking front/back cast-on.

| Parameter | Type | Description |
|-----------|------|-------------|
| `carriers` | list of ints | Sorted list of carrier numbers (e.g., `[1, 2]`) |

#### `knit_birdseye(pattern)`

Knits a birdseye colorwork section using both front and back beds. The front bed shows the design (each cell = which carrier), and the back bed gets a rotating birdseye interlocking pattern automatically.

| Parameter | Type | Description |
|-----------|------|-------------|
| `pattern` | 2D list of ints | Shape `(rows, width)`, each value is a carrier number. Requires at least 2 distinct carriers. |

All carriers must already be active. Sets rack to 0.25 during the section.

```python
# Checkerboard with 2 carriers
pattern = [[(1 if (r + c) % 2 == 0 else 2) for c in range(20)] for r in range(10)]
kh.doubleknit_cast_on([1, 2])
kh.knit_birdseye(pattern)
kh.doubleknit_bind_off([1, 2])
```

#### `doubleknit_bind_off(carriers)`

Bind-off for birdseye/double-knit fabric. Outhooks all carriers except the last, transfers back to front, knits settling rows, then drops.

| Parameter | Type | Description |
|-----------|------|-------------|
| `carriers` | list of ints | Sorted list of carrier numbers |

---

### Carrier Lifecycle (Inherited from KnitoutWriter)

These low-level methods manage yarn carriers. When using `KnittingHelper` directly (not `ShapingHelper`), you're responsible for calling these yourself.

| Method | What it does |
|--------|-------------|
| `inhook(carrier)` | Bring carrier into action using the inserting hook |
| `releasehook(carrier)` | Release the inserting hook (call after a few rows stabilize the yarn) |
| `outhook(carrier)` | Take carrier out of action |

**Typical carrier lifecycle:**

```python
kh.inhook(1)          # bring yarn in
kh.cast_on(1)         # cast on (yarn gets anchored)
kh.knit_waste("f", 1) # knit a few rows to stabilize
kh.releasehook(1)     # safe to release the hook now
# ... knit your pattern ...
kh.outhook(1)         # done with this carrier
kh.drop_all("f")      # drop the loops
```

---

## Spacer Fabric (SpacerHelper)

`spacer_helper.py` provides `SpacerHelper(ShapingHelper)` for weft-knit spacer fabric (Albaugh et al., CHI 2021): two face layers on the front and back beds connected by a monofilament filler tucked in a zig-zag between them. It produces the **open sheet** variant — faces share only the cast-on region (plus the filler), so a shaped sheet can be wrapped around an object such as a robot arm segment. Fabric is knit at **half gauge** like the paper, but **1-based**: front face on `f{2n-1}`, back face on `b{2n}`, so logical stitch 1 sits on physical needle 1 and the used range is exactly `[1 .. 2*width]` (park misses extend it one needle each side). This overrides the inherited ShapingHelper/J-30 convention (`f{2n}`, `b{2n+1}`, which starts at needle 2), so `SpacerHelper` overrides `_loc`/`_phys`, adds `_phys_min()`/`_phys_max()` span helpers, and owns its own cast-on, `decrease`, finish, and teardown transfers; `increase` raises — use `increase_edge`. Half gauge promotes the elastic draw-in that produces loft and leaves empty opposite needles for transfer-based shaping. Face yarns must be **plated with elastic** (no elastic → no draw-in → flat fabric); for a conductive shielding face, plate a conductive yarn with the elastic on that carrier. The filler is nylon monofilament — nylon mono fishing line, 6 lb test / 0.22–0.25 mm, is what the paper used.

### `SpacerHelper(width, front_carrier=3, back_carrier=4, filler_carrier=5, tuck_spacing=5, tuck_offset=1, face_row_pairs=1, filler_pass_pairs=5, face_order="alternate", drop_repeats=2)`

Each carrier parameter accepts an int **or a tuple for plating** — e.g. `back_carrier=(7, 10)` knits conductive yarn 7 plated with elastic 10 in every back-face stitch (`knit - b9 7 10`); the first carrier listed shows on the fabric face, and the set is inhooked/released/outhooked together. Front and back sets may be equal (one yarn for both faces) but must not partially overlap; the filler must be disjoint from both. `tuck_spacing` is 1–5 logical stitches (paper: 2–5 for clean loft; default 5 = maximum loft), `tuck_offset` shifts the tuck grid per pass, `face_row_pairs`/`filler_pass_pairs` set the default filler density per block (default 5:1, dense load-bearing cushion; the paper's default fabric was 2:1), and `face_order` controls shear bias: the face knit first after filler shears downward; `"alternate"` minimizes bias.

### Quick start

```python
from spacer_helper import SpacerHelper

sp = SpacerHelper(width=40, front_carrier=3, back_carrier=4, filler_carrier=5)
sp.standard_headers()
sp.cast_on_spacer(waste_rows=8)   # extra waste for zipper sewing
sp.knit_spacer_trapezoid([
    (40, 8),    # (width, blocks), bottom to top
    (34, 8),    # tapers over the section's first blocks
    {"width": 30, "blocks": 6, "filler_pass_pairs": 6},  # per-section overrides
])
sp.finish_spacer(waste_rows=8)
sp.write("arm_wrap.k")
```

### Methods

| Method | Description |
|--------|-------------|
| `cast_on_spacer(waste_rows=6)` | Three-stage cast-on with ≥5 waste rows per stage: (1) all-needle tuck cast-on + full-gauge waste + transfer to half gauge (front carrier); (2) back carrier introduced **on the front bed** (back-bed introductions often fail to catch), then per-face waste with both carriers; (3) filler monofilament introduced with a **knit** row pair on the front bed inside the waste — a firm catch, so the loose monofilament start doesn't get grabbed by the face yarns. Every carrier, including each member of a plating set, is inhooked **separately** with its own waste rows (plated inhooks are unreliable), and each is parked past the right edge afterward so no pass has to backtrack |
| `knit_face_row_pair(bed)` | One leftward+rightward face row pair on `"f"` or `"b"`, staying on that bed |
| `knit_filler_pass(tuck_spacing=None, tuck_offset=None)` | One filler pass: tucks alternating beds every `tuck_spacing` stitches; call in pairs |
| `knit_spacer_block(face_row_pairs=None, filler_pass_pairs=None, ..., increase_sides=(), decrease_sides=())` | One unit, sequenced as: increases → face rows → decreases → filler. Decreases sit after the face rows because transferring needles that hold monofilament tucks is error-prone (paper sec. 8); increases sit before so twisted tucks anchor new needles before any filler pass. Defaults fall back to instance settings. `filler_pass_pairs=0` gives an unconnected hinge |
| `enable_eyelets(faces="both", eyelet_width=3, eyelet_gap=5, pitch_rows=None, rows_per_inch=13, eyelet_rows=1, phase=0)` | Eyelet grid mode: every `pitch_rows` face rows (default ≈1 cm at 13 rpi → 5 rows), one row misses the stitches in each eyelet column (default 3 wide, 5 solid between). Columns anchor to absolute needles so they stay vertically aligned through shaping; 2 selvedge stitches always knit. `faces` = `"front"`, `"back"`, or `"both"` |
| `disable_eyelets()` | Back to solid fabric |
| `knit_spacer_trapezoid(sections, ..., step_threshold=None)` | Shaped sheet from `(width, blocks)` sections. Small changes are **shaped** (≤2 st per block, balanced across edges); changes too big for the blocks available — or bigger than `step_threshold` — are **stepped** instead of raising. Per-section `"step": True/False` and `"align": "center"/"left"/"right"` override. First section width must equal current width |
| `step_width(target_width, align="center", cast_off_rows=4)` | Abrupt width change. Needles entering the range are tuck-cast-on. Outgoing stitches are **cast off**: their back-face loops transfer to the front bed and the front face rows keep knitting them for `cast_off_rows` rows before dropping. `cast_off_rows=0` drops them immediately. Drops repeat `drop_repeats` times; unresolved filler tucks on immediately discarded needles are converted to misses. Returns `(dropped, added)` |
| `SpacerHelper.stitches_for(inches, wales_per_inch=13)` | Inches → stitch count, for writing sections in measured units |
| `increase_edge(side)` / `decrease_edge(side)` | One-stitch edge shaping on both faces (`"left"`/`"right"`); prefer the `knit_spacer_block` args so the timing rules above hold |
| `finish_spacer(waste_rows=6)` | Mirrors the cast-on: outhook filler → per-face waste → outhook **back** carrier → transfer back bed onto front bed → merged waste rows with the **front** carrier → drop. The back set (which may be conductive) leaves first, so no conductive fibre runs across the full width of the merged region. Edge intentionally unsecured; the waste is for sewing (zippers) and unravels after seaming |
| `drop_all_spacer()` | Quick teardown for test swatches (no waste region) |
| `SpacerHelper.estimate_thickness(tuck_spacing, ...)` | Finished-thickness estimate (mm) from the paper's triangle model, eq. 1 (13 wpi pitch; paper's fitted bed gap/shrink — re-fit from your swatches) |

See `test_spacer_fabric.py` for a uniform swatch at the 5/5:1 defaults, a filler-density gradient with a hinge, a shear-biased swatch, eyelet grids (both faces and front-only), and a tapered arm wrap.

---

## Writing Output

### `write(filename=None)`

Generates the knitout string. If `filename` is provided, also writes to that file. Always returns the knitout string. This is common to both helpers.

```python
output = kh.write("my_pattern.k")
print(f"Generated {len(output.splitlines())} lines")
```
