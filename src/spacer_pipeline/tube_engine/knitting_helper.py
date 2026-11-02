"""
COMP116 Final Project - KnittingHelper

This module provides the KnittingHelper class, which wraps the procedural
helper functions from HW2/3/4 as methods on a class that inherits from
KnitoutWriter. It covers flat knitting, knit/purl texture patterns,
color stripes, stranded colorwork, and birdseye jacquard.

Hierarchy:
    KnitoutWriter         (HW5)  -- individual knitout instructions + validation
      -> KnittingHelper   (this) -- plain flat knitting operations
           -> ShapingHelper      -- adds shaping state and operations
"""

from .knitout_writer import KnitoutWriter


class KnittingHelper(KnitoutWriter):
    """
    A helper class that groups low-level knitout instructions into
    higher-level functionalities: cast-on, rows, waste sections,
    colorwork, and bind-off.

    This is the OOP version of the procedural knitout_helpers.py files
    from HW2, HW3, and HW4. The key difference: instead of threading
    state (direction, width, knitout_lines) through every function call,
    the state lives on the object.

    Attributes on top of what KnitoutWriter provides:
        min_n:     leftmost active needle index (default 1)
        max_n:     rightmost active needle index (default width)
        direction: dict mapping each carrier to its current direction
                   ("+" = left-to-right, "-" = right-to-left)
    """

    def __init__(self, width):
        """
        Initialize the KnittingHelper.

        Parameters:
            width:    number of stitches (needles) for this piece
        """
        super().__init__(carriers=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert width >= 2, "width must be at least 2"
        self.min_n = 1
        self.max_n = width
        # Each carrier starts with no assigned direction (set during cast-on
        # or first use). We initialize as "-" by convention.
        self.direction = {c: "-" for c in self.carriers}

    @property
    def width(self):
        """Current number of active needles."""
        return self.max_n - self.min_n + 1

    def _flip_direction(self, carrier):
        """Flip a carrier's direction after a pass."""
        self.direction[carrier] = "+" if self.direction[carrier] == "-" else "-"

    # ----------------------------------------------------------------
    # Flat knitting
    # ----------------------------------------------------------------

    def standard_headers(self):
        """
        Add standard knitout file headers, excluding carriers.
        """
        self.add_header("Position", "Center")
        self.add_header("Width", "450")

    def set_subroller(self, setting):
        """
        Assign subroller settings
        """
        assert type(setting) == int, f"Invalid subroller setting, must be an integer. (got: {setting})"
        self.instructions.append(f"x-sub-roller-number {setting}")


    def cast_on(self, carrier):
        """
        Alternating-tuck cast-on on the front bed.

        Equivalent to the procedural cast_on() from HW2/HW3.
        Lays down alternating tucks using the carrier (assuming active)
        right-to-left then left-to-right, so every needle gets one tuck.

        After this call the carrier is active and direction is "-".
        """
        for s in range(self.max_n, self.min_n - 1, -1):
            if (self.max_n - s) % 2 == 0:
                self.tuck("-", f"f{s}", carrier)
        for s in range(self.min_n, self.max_n + 1):
            if (self.max_n - s) % 2 == 1:
                self.tuck("+", f"f{s}", carrier)
        self.direction[carrier] = "-"

    def knit_row(self, bed, carrier, op_indices=None):
        """
        Knit one full-width pass on the given bed, respecting the
        carrier's current direction, then flip the direction.

        Parameters:
            bed:        the bed to knit on ("f" or "b")
            carrier:    the carrier to use
            op_indices: if provided, only knit on these indices
                        (overrides min_n/max_n range)
        """
        if op_indices is None:
            op_indices = range(self.min_n, self.max_n + 1)
        if self.direction[carrier] == "-":
            for s in reversed(list(op_indices)):
                self.knit("-", f"{bed}{s}", carrier)
        else:
            for s in op_indices:
                self.knit("+", f"{bed}{s}", carrier)
        self._flip_direction(carrier)

    def knit_waste(self, bed, carrier, waste_rows=10):
        """
        Knit waste rows to stabilize the fabric.

        Parameters:
            bed:         the bed to knit on ("f" or "b")
            carrier:     the carrier to use
            waste_rows:  number of waste rows (default 10, always rounded
                         up to an even number so the carrier ends on the
                         same side it started)
        """
        if waste_rows % 2 == 1:
            waste_rows += 1
        for _ in range(waste_rows):
            self.knit_row(bed, carrier)

    def drop_all(self, bed="f"):
        """
        Drop all stitches on the specified bed (min_n through max_n).
        """
        for s in range(self.min_n, self.max_n + 1):
            self.drop(f"{bed}{s}")

    def drop_all_both(self, margin=0):
        """
        Drop all stitches on both beds, optionally with an overhang margin.
        """
        for s in range(self.min_n - margin, self.max_n + 1 + margin):
            self.drop(f"f{s}")
        for s in range(self.min_n - margin, self.max_n + 1 + margin):
            self.drop(f"b{s}")

    def simple_bind_off(self, bed, carrier):
        """
        Simple bind-off: knit several settling rows, outhook, drop.
        """
        self.knit_waste(bed, carrier)
        self.outhook(carrier)
        self.drop_all(bed)

    def stack_bind_off(self, carrier, min_n=None, max_n=None):
        """
        Stack bind-off on the front bed (left-to-right).

        Translated from rectangle-bindoff.js. The carrier must be
        approaching from the left (direction == "+") or an extra row
        is knitted to achieve that.

        Parameters:
            carrier: the carrier to use
            min_n:   leftmost needle (default self.min_n)
            max_n:   rightmost needle (default self.max_n)
        """
        self._validate_active_carrier(carrier)
        if min_n is None:
            min_n = self.min_n
        if max_n is None:
            max_n = self.max_n

        # Ensure carrier is going left-to-right
        if self.direction[carrier] == "-":
            self.knit_row("f", carrier)  # extra row to flip direction

        # Chain bind-off left-to-right
        for n in range(min_n, max_n):
            self.xfer(f"f{n}", f"b{n}")
            self.rack(1)
            self.xfer(f"b{n}", f"f{n + 1}")
            self.rack(0.25)
            if (n - min_n) % 2 == 1:
                self.tuck("+", f"b{n}", carrier)
            self.knit("+", f"f{n + 1}", carrier)
            if n + 2 <= max_n:
                self.miss("+", f"f{n + 2}", carrier)
            self.rack(0)

        # Settling triangle at the end
        self.knit("-", f"f{max_n}", carrier)
        self.knit("+", f"f{max_n}", carrier)
        self.knit("-", f"f{max_n}", carrier)
        self.knit("+", f"f{max_n - 1}", carrier)
        self.knit("+", f"f{max_n}", carrier)
        self.knit("-", f"f{max_n}", carrier)
        self.knit("-", f"f{max_n - 1}", carrier)
        self.knit("+", f"f{max_n - 2}", carrier)
        self.knit("+", f"f{max_n - 1}", carrier)
        self.knit("+", f"f{max_n}", carrier)
        self.knit("-", f"f{max_n}", carrier)
        self.knit("-", f"f{max_n - 1}", carrier)
        self.knit("-", f"f{max_n - 2}", carrier)
        self.knit("+", f"f{max_n - 3}", carrier)
        self.knit("+", f"f{max_n - 2}", carrier)
        self.knit("+", f"f{max_n - 1}", carrier)
        self.knit("+", f"f{max_n}", carrier)

        for _ in range(4):
            for n in range(max_n, max_n - 4, -1):
                self.knit("-", f"f{n}", carrier)
            for n in range(max_n - 3, max_n + 1):
                self.knit("+", f"f{n}", carrier)

        self.outhook(carrier)
        # Drop remaining loops
        self.rack(0.25)
        for n in range(min_n, max_n + 1):
            self.drop(f"b{n}")
            self.drop(f"f{n}")
        self.rack(0)

    # ----------------------------------------------------------------
    # HW2 Variations: Knit/Purl patterns and Color Stripes
    # ----------------------------------------------------------------

    def knit_kp_rows(self, rand_array, carrier):
        """
        Variation 1 from HW2: Knit/Purl rows pattern.
        0 = all-knit row (front bed), 1 = all-purl row (back bed).
        Transfers stitches between beds as needed.

        Parameters:
            rand_array: list of 0s and 1s
            carrier:    the carrier to use (must be active)
        """
        current_bed = "f"

        for value in rand_array:
            target_bed = "b" if value == 1 else "f"

            # Transfer if we need to switch beds
            if target_bed != current_bed:
                other_bed = "f" if current_bed == "b" else "b"
                for s in range(self.max_n, self.min_n - 1, -1):
                    self.xfer(f"{current_bed}{s}", f"{other_bed}{s}")
                # Double up xfers for reliability (matches HW2)
                for s in range(self.min_n, self.max_n + 1):
                    self.xfer(f"{current_bed}{s}", f"{other_bed}{s}")
                current_bed = target_bed

            # Knit the row on current bed
            self.knit_row(current_bed, carrier)

        # Transfer back to front bed if we ended on back bed
        if current_bed == "b":
            for s in range(self.min_n, self.max_n + 1):
                self.xfer(f"b{s}", f"f{s}")

    def knit_kp_cols(self, rand_array, carrier, height=20):
        """
        Variation 2 from HW2: Knit/Purl columns pattern.
        0 = all-knit column (front bed), 1 = all-purl column (back bed).

        Parameters:
            rand_array: list of 0s and 1s, length == self.width
            carrier:    the carrier to use (must be active)
            height:     number of pattern rows to knit
        """
        # Transfer purl columns to back bed
        for s in range(self.min_n, self.max_n + 1):
            if rand_array[s - self.min_n] == 1:
                self.xfer(f"f{s}", f"b{s}")

        # Knit pattern rows
        for _ in range(height):
            if self.direction[carrier] == "-":
                for s in range(self.max_n, self.min_n - 1, -1):
                    bed = "b" if rand_array[s - self.min_n] == 1 else "f"
                    self.knit("-", f"{bed}{s}", carrier)
            else:
                for s in range(self.min_n, self.max_n + 1):
                    bed = "b" if rand_array[s - self.min_n] == 1 else "f"
                    self.knit("+", f"{bed}{s}", carrier)
            self._flip_direction(carrier)

        # Transfer back to front bed
        for s in range(self.min_n, self.max_n + 1):
            if rand_array[s - self.min_n] == 1:
                self.xfer(f"b{s}", f"f{s}")

    def knit_color_stripes(self, rand_array, carrier_a, carrier_b):
        """
        Variation 3 from HW2: Color stripe rows.
        0 = use carrier_a, 1 = use carrier_b.
        Both carriers must already be active.

        Parameters:
            rand_array: list of 0s and 1s
            carrier_a:  first carrier (for 0 values)
            carrier_b:  second carrier (for 1 values)
        """
        for value in rand_array:
            chosen = carrier_a if value == 0 else carrier_b
            self.knit_row("f", chosen)

    # ----------------------------------------------------------------
    # Stranded Colorwork (from HW3)
    # ----------------------------------------------------------------

    def _get_unique_carriers(self, pattern):
        """Helper to iterate over the 2D array pattern to get unique
        carriers (assuming each cell is a carrier number)."""
        unique_carriers = set()
        for row in pattern:
            for carrier in row:
                unique_carriers.add(carrier)
        return unique_carriers

    def prep_stranded_colorwork(self, pattern):
        """
        Prepare before knitting the colorwork section. This inhooks all
        the carriers used in the pattern and knits some waste with the
        first carrier.
        """
        sorted_carriers = sorted(list(self._get_unique_carriers(pattern)))
        for i, carrier in enumerate(sorted_carriers):
            if i == 0:
                self.inhook(carrier)
                self.cast_on(carrier)
                self.knit_waste("f", carrier)
                self.releasehook(carrier)
            else:
                self.inhook(carrier)
                self.knit_row("f", carrier)
                self.releasehook(carrier)

    def knit_stranded_colorwork(self, pattern):
        """
        Knit a colorwork section on the front bed only.

        Each row of pattern specifies which carrier knits each stitch.
        Unused carriers float on the back. This is single-bed colorwork
        similar to HW3's image_to_colorwork, but as a method.

        Parameters:
            pattern:  2D list of carrier numbers, shape (rows, width).
                      All values must be carriers declared at init.
                      The array is knitted bottom-to-top (last row first).

        Prerequisites:
            All carriers referenced in pattern must already be active
            (brought in via inhook + releasehook).
        """
        for row in pattern[::-1]:
            # Group stitches by carrier
            carrier_indices = {}
            for col, carrier in enumerate(row):
                if carrier not in carrier_indices:
                    carrier_indices[carrier] = []
                carrier_indices[carrier].append(col + self.min_n)

            for carrier in sorted(carrier_indices.keys()):
                indices = carrier_indices[carrier]
                self.knit_row("f", carrier, op_indices=indices)

    def end_stranded_colorwork(self, pattern):
        """
        End a stranded colorwork section: outhook non-primary carriers,
        knit waste with primary, outhook, drop.
        """
        sorted_carriers = sorted(list(self._get_unique_carriers(pattern)))
        # Outhook non-primary carriers
        for carrier in sorted_carriers[1:]:
            self.outhook(carrier)
        # Waste and drop with primary carrier
        self.knit_waste("f", sorted_carriers[0])
        self.outhook(sorted_carriers[0])
        self.drop_all("f")

    # ----------------------------------------------------------------
    # Birdseye Jacquard (from HW4)
    # ----------------------------------------------------------------

    def doubleknit_cast_on(self, carriers):
        """
        Double-knit cast-on for all carriers, translated from knit-jacquard.js.

        Parameters:
            carriers:      sorted list of carrier numbers (ints)
        """
        f_parity = (self.max_n - 1) % 2

        self.instructions.append("x-stitch-number 104")
        start_dir = "-"
        first = True

        for car in carriers:
            self.inhook(car)

            # Pass 1: alternating all-needle knit, right-to-left
            for n in range(self.max_n, self.min_n - 1, -1):
                if (n - 1) % 2 == f_parity:
                    self.knit("-", f"f{n}", car)
                else:
                    self.knit("-", f"b{n}", car)

            # Pass 2: alternating all-needle knit, left-to-right (front/back swapped)
            for n in range(self.min_n, self.max_n + 1):
                if (n - 1) % 2 == f_parity:
                    self.knit("+", f"b{n}", car)
                else:
                    self.knit("+", f"f{n}", car)

            if first:
                first = False
                self.instructions.append("x-stitch-number 105")

            # Tubular passes to stabilize the yarn
            if start_dir == "-":
                self.direction[car] = "-"
                for n in range(self.max_n, self.min_n - 1, -1):
                    self.knit("-", f"f{n}", car)
                for n in range(self.min_n, self.max_n + 1):
                    self.knit("+", f"b{n}", car)
                start_dir = "+"
            else:
                self.direction[car] = "+"
                for n in range(self.max_n, self.min_n - 1, -1):
                    if (n - 1) % 2 == f_parity:
                        self.knit("-", f"f{n}", car)
                for n in range(self.min_n, self.max_n + 1):
                    self.knit("+", f"b{n}", car)
                for n in range(self.max_n, self.min_n - 1, -1):
                    if (n - 1) % 2 != f_parity:
                        self.knit("-", f"f{n}", car)
                start_dir = "-"

            self.releasehook(car)

    def doubleknit_bind_off(self, carriers):
        """
        Bind-off for birdseye/double-knit fabric, translated from HW4
        knitout_helpers.py bind_off().

        Parameters:
            carriers: sorted list of carrier numbers (ints)
        """
        cars_desc = sorted(carriers, reverse=True)
        last_car = cars_desc[-1]

        self.rack(0)

        # Outhook all carriers except the last (two tubular passes, then outhook)
        for car in cars_desc[:-1]:
            if self.direction[car] == "-":
                for _ in range(2):
                    for n in range(self.max_n, self.min_n - 1, -1):
                        self.knit("-", f"f{n}", car)
                    for n in range(self.min_n, self.max_n + 1):
                        self.knit("+", f"b{n}", car)
            else:
                for _ in range(2):
                    for n in range(self.min_n, self.max_n + 1):
                        self.knit("+", f"f{n}", car)
                    for n in range(self.max_n, self.min_n - 1, -1):
                        self.knit("-", f"b{n}", car)
            self.outhook(car)

        # Transfer all back-bed loops to front bed
        for n in range(self.min_n, self.max_n + 1):
            self.xfer(f"b{n}", f"f{n}")

        # Knit 4 rows on the front bed
        for _ in range(4):
            self.knit_row("f", last_car)

        # Transfer all front-bed loops to back bed
        for n in range(self.min_n, self.max_n + 1):
            self.xfer(f"f{n}", f"b{n}")

        # Knit 4 rows on the back bed
        for _ in range(4):
            self.knit_row("b", last_car)

        # Outhook and drop all
        self.outhook(last_car)
        self.drop_all_both(margin=4)

    def _knit_carrier_row(self, direction, carrier, front_set, back_set):
        """
        Knit one carrier's stitches for a single birdseye row,
        interleaving front and back needle-by-needle.

        Returns True if any stitches were knitted.
        """
        did_knit = False
        needle_range = (range(self.min_n, self.max_n + 1) if direction == "+"
                        else range(self.max_n, self.min_n - 1, -1))
        last_needle = self.max_n if direction == "+" else self.min_n

        for n in needle_range:
            knitted_here = False
            if direction == "+":
                if n in front_set:
                    self.knit("+", f"f{n}", carrier)
                    did_knit = knitted_here = True
                if n in back_set:
                    self.knit("+", f"b{n}", carrier)
                    did_knit = knitted_here = True
            else:
                if n in back_set:
                    self.knit("-", f"b{n}", carrier)
                    did_knit = knitted_here = True
                if n in front_set:
                    self.knit("-", f"f{n}", carrier)
                    did_knit = knitted_here = True

            # Miss at boundary if carrier is done but hasn't reached the edge
            if did_knit and n == last_needle and not knitted_here:
                if direction == "+":
                    self.miss("+", f"b{self.max_n + 1}", carrier)
                else:
                    self.miss("-", f"b{self.min_n - 1}", carrier)

        return did_knit

    def knit_birdseye(self, pattern):
        """
        Knit a birdseye colorwork section using front + back beds.

        Parameters:
            pattern: 2D list of carrier numbers, shape (rows, width).
                     All values must be among self.carriers.
                     Requires at least 2 carriers.

        Prerequisites:
            All carriers must already be active. Racking will be set
            to 0.25 during this section and restored to 0 after.
        """
        carriers = sorted(list(self._get_unique_carriers(pattern)))
        n_carriers = len(carriers)
        assert n_carriers >= 2, "Birdseye requires at least 2 carriers"

        self.rack(0.25)

        for row_idx, row in enumerate(pattern[::-1]):
            # Front-bed design stitches per carrier
            front_sets = {car: set() for car in carriers}
            for col, val in enumerate(row):
                front_sets[val].add(col + self.min_n)

            # Back-bed birdseye: rotating sequence shifted by row index
            back_sets = {car: set() for car in carriers}
            for col in range(self.width):
                phase = (col + row_idx) % n_carriers
                back_sets[carriers[phase]].add(col + self.min_n)

            # Knit non-primary carriers first, then primary last
            knit_order = carriers[1:] + [carriers[0]]
            for car in knit_order:
                did_knit = self._knit_carrier_row(
                    self.direction[car], car,
                    front_sets[car], back_sets[car])
                if did_knit:
                    self._flip_direction(car)

        self.rack(0)


# ================================================================
# Example Usage / Tests
# ================================================================
if __name__ == "__main__":
    import random
    random.seed(116)

    # ----------------------------------------------------------
    # Test 1: Flat knitting with knit/purl rows (HW2 Variation 1)
    # Uses xfers to switch between front and back beds
    # ----------------------------------------------------------
    print("--- Test 1: Knit/Purl Rows (HW2 Variation 1) ---")
    kh1 = KnittingHelper(width=20)
    kh1.standard_headers()
    kh1.inhook(1)
    kh1.cast_on(1)
    kh1.knit_waste("f", 1)
    kh1.releasehook(1)

    # Random pattern of knit/purl rows
    rand_array = [random.randint(0, 1) for _ in range(20)]
    print(f"  Pattern: {rand_array}")
    kh1.knit_kp_rows(rand_array, 1)

    # End waste and finish
    kh1.knit_waste("f", 1)
    kh1.outhook(1)
    kh1.drop_all("f")

    output1 = kh1.write()
    print(f"  Generated {len(output1.splitlines())} knitout lines")

    # ----------------------------------------------------------
    # Test 2: Knit/Purl Columns (HW2 Variation 2)
    # ----------------------------------------------------------
    print("\n--- Test 2: Knit/Purl Columns (HW2 Variation 2) ---")
    kh2 = KnittingHelper(width=20)
    kh2.standard_headers()
    kh2.inhook(1)
    kh2.cast_on(1)
    kh2.knit_waste("f", 1)
    kh2.releasehook(1)

    rand_array2 = [random.randint(0, 1) for _ in range(20)]
    print(f"  Pattern: {rand_array2}")
    kh2.knit_kp_cols(rand_array2, 1, height=20)

    kh2.knit_waste("f", 1)
    kh2.outhook(1)
    kh2.drop_all("f")

    output2 = kh2.write()
    print(f"  Generated {len(output2.splitlines())} knitout lines")

    # ----------------------------------------------------------
    # Test 3: Color Stripes (HW2 Variation 3)
    # ----------------------------------------------------------
    print("\n--- Test 3: Color Stripes (HW2 Variation 3) ---")
    kh3 = KnittingHelper(width=20)
    kh3.standard_headers()

    # Bring in carrier A, cast on, waste
    kh3.inhook(1)
    kh3.cast_on(1)
    kh3.knit_waste("f", 1)
    kh3.releasehook(1)

    # Bring in carrier B
    kh3.inhook(2)
    kh3.knit_row("f", 2)
    kh3.releasehook(2)

    rand_array3 = [random.randint(0, 1) for _ in range(20)]
    print(f"  Pattern: {rand_array3}")
    kh3.knit_color_stripes(rand_array3, 1, 2)

    kh3.outhook(2)
    kh3.knit_waste("f", 1)
    kh3.outhook(1)
    kh3.drop_all("f")

    output3 = kh3.write()
    print(f"  Generated {len(output3.splitlines())} knitout lines")

    # ----------------------------------------------------------
    # Test 4: Stranded Colorwork (HW3)
    # ----------------------------------------------------------
    print("\n--- Test 4: Stranded Colorwork (HW3) ---")
    kh4 = KnittingHelper(width=20)
    kh4.standard_headers()

    # Generate a random 3-color pattern
    stranded_pattern = []
    carrier_choices = [1, 2, 3]
    for r in range(10):
        row = [random.choice(carrier_choices) for _ in range(20)]
        stranded_pattern.append(row)
    print(f"  Pattern ({len(stranded_pattern)} rows x {len(stranded_pattern[0])} cols)")

    kh4.prep_stranded_colorwork(stranded_pattern)
    kh4.knit_stranded_colorwork(stranded_pattern)
    kh4.end_stranded_colorwork(stranded_pattern)

    output4 = kh4.write()
    print(f"  Generated {len(output4.splitlines())} knitout lines")

    # ----------------------------------------------------------
    # Test 5: Birdseye Jacquard (HW4)
    # ----------------------------------------------------------
    print("\n--- Test 5: Birdseye Jacquard (HW4) ---")
    kh5 = KnittingHelper(width=20)
    kh5.standard_headers()
    kh5.instructions.append("x-sub-roller-number 3")

    # Checkerboard pattern: 2 carriers
    birdseye_pattern = []
    for r in range(6):
        row = []
        for c in range(20):
            row.append(1 if (r + c) % 2 == 0 else 2)
        birdseye_pattern.append(row)
    print(f"  Checkerboard pattern ({len(birdseye_pattern)} rows x {len(birdseye_pattern[0])} cols)")

    kh5.doubleknit_cast_on([1, 2])
    kh5.knit_birdseye(birdseye_pattern)

    kh5.instructions.append("x-sub-roller-number 0")
    kh5.doubleknit_bind_off([1, 2])

    output5 = kh5.write()
    print(f"  Generated {len(output5.splitlines())} knitout lines")

    # ----------------------------------------------------------
    # Write all test outputs to files
    # ----------------------------------------------------------
    kh1.write("test_kp_rows.k")
    kh2.write("test_kp_cols.k")
    kh3.write("test_color_stripes.k")
    kh4.write("test_stranded.k")
    kh5.write("test_birdseye.k")
    print("\nAll test knitout files written successfully.")
