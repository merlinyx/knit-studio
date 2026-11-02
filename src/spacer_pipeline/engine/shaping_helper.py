"""
COMP116 Final Project - ShapingHelper

This module provides the ShapingHelper class for projects that involve
tubular knitting and shaping (increases, decreases, short rows).

Reference implementations from knitout-examples repo:
  - Tubular short rows + decrease: J-30.js
  - Stack bind-off (flat): rectangle-bindoff.js
  - Chain bind-off (birdseye): image-tj.js, rainbow-tj.js
  - Decrease patterns: decrease.js

Hierarchy:
    KnitoutWriter           (HW5)  -- individual knitout instructions + validation
      -> KnittingHelper            -- plain flat knitting operations
           -> ShapingHelper (this) -- adds shaping state and operations
"""

from .knitting_helper import KnittingHelper


class ShapingHelper(KnittingHelper):
    """
    A knitting helper that adds half-gauge tubular knitting and support
    for shaping operations.

    Supports both flat (sheet) and tubular (tube) knitting modes.
    For tubular knitting, half-gauge is used by default:
      - Front needles are at even positions (2*n)
      - Back needles are at odd positions (2*n+1)
    This follows the J-30.js convention: loc('f', n) = f{2*n}, loc('b', n) = b{2*n+1}.

    Inherits min_n/max_n tracking from KnittingHelper. Adds:
        is_tubular:    whether this is a tube (half gauge)
    """

    def __init__(self, width, is_tubular=True):
        """
        Initialize the ShapingHelper.

        Parameters:
            width:      number of logical stitches for this piece
            is_tubular: whether this is a tube; if True, uses half-gauge layout
        """
        super().__init__(width=width)
        assert (not is_tubular) or width >= 4, \
            "width must be at least 4 stitches for tubular knitting"

        self.is_tubular = is_tubular

    def __repr__(self):
        return f"ShapingHelper(range=[{self.min_n}, {self.max_n}], is_tubular={self.is_tubular}, direction={self.direction})"

    # ----------------------------------------------------------------
    # Needle addressing helpers (half-gauge)
    # ----------------------------------------------------------------

    def _loc(self, bed, n):
        """
        Translate logical needle index n to physical bed+needle string.
        For tubular (half-gauge): front -> f{2*n}, back -> b{2*n+1}.
        For flat: front/back -> {bed}{n}.
        Matches J-30.js: loc('f', n) = f(2*n), loc('b', n) = b(2*n+1).
        """
        if self.is_tubular:
            return f"f{2 * n}" if bed == "f" else f"b{2 * n + 1}"
        else:
            return f"{bed}{n}"

    # ----------------------------------------------------------------
    # Cast-on
    # ----------------------------------------------------------------

    def cast_on_tubular(self, carrier):
        """
        Alternating front/back cast-on for half-gauge tube.
        Translated from J-30.js closed cast-on.

        Tucks right-to-left on alternating front and back needles at rack -2,
        then knits left-to-right at rack 0 to close the bottom.
        """
        assert self.is_tubular, "cast_on_tubular requires tubular mode"

        self.inhook(carrier)

        # Right-to-left tucks at rack -2 (alternating front/back)
        self.rack(-2)
        for n in range(self.max_n, self.min_n - 1, -1):
            self.tuck("-", self._loc("f", n), carrier)
            self.tuck("-", self._loc("b", n), carrier)
        # Miss past the edge to position carrier
        self.miss("-", f"f{2 * self.min_n - 2}", carrier)

        # Left-to-right knit at rack 0 to close
        self.rack(0)
        for n in range(self.min_n, self.max_n + 1):
            self.knit("+", self._loc("f", n), carrier)
            self.knit("+", self._loc("b", n), carrier)

        self.releasehook(carrier)
        self.direction[carrier] = "-"

    def cast_on_all_needle_transition(self, carrier, settling_rows=4):
        """
        All-needle cast-on on the front bed, followed by a rack-0
        transition to half-gauge tubular layout.

        Inspired by the mitten_tag.k approach: cast on at full gauge
        (every needle), knit a few settling rows, then transfer
        odd-position stitches to the back bed to reach the standard
        half-gauge layout (front = f{2n}, back = b{2n+1}).

        This avoids any racking during the cast-on stage.

        Steps:
          1. Alternating-tuck cast-on across physical needles
             [2*min_n .. 2*max_n+1] on the front bed.
          2. Knit `settling_rows` rows on the front bed (all needles)
             so the fabric is stable enough to transfer.
          3. Transfer every odd-position stitch (f{2n+1}) to the
             back bed (b{2n+1}) at rack 0.

        After this call, the fabric is in the standard half-gauge
        layout and ready for knit_tubular_row().

        Parameters:
            carrier:        the yarn carrier to use
            settling_rows:  number of full-gauge front-bed rows to
                            knit before transitioning (default 4;
                            must be even so the carrier ends on the
                            right side, matching tubular row start)
        """
        assert self.is_tubular, \
            "cast_on_all_needle_transition requires tubular mode"
        assert settling_rows >= 2, \
            "need at least 2 settling rows for stable transfer"
        # Force even so we always end with direction "-" after settling
        if settling_rows % 2 != 0:
            settling_rows += 1

        # Physical needle range that spans the full half-gauge layout
        phys_min = 2 * self.min_n        # leftmost front needle
        phys_max = 2 * self.max_n + 1    # rightmost back-bed position

        self.inhook(carrier)

        # --- Step 1: alternating-tuck cast-on (full gauge, front bed) ---
        # Right-to-left pass: tuck on every other needle
        for s in range(phys_max, phys_min - 1, -1):
            if (phys_max - s) % 2 == 0:
                self.tuck("-", f"f{s}", carrier)
        # Left-to-right pass: fill in the gaps
        for s in range(phys_min, phys_max + 1):
            if (phys_max - s) % 2 == 1:
                self.tuck("+", f"f{s}", carrier)

        self.releasehook(carrier)

        # --- Step 2: settling rows (full gauge, front bed) ---
        d = "-"
        for _ in range(settling_rows):
            if d == "-":
                for s in range(phys_max, phys_min - 1, -1):
                    self.knit("-", f"f{s}", carrier)
            else:
                for s in range(phys_min, phys_max + 1):
                    self.knit("+", f"f{s}", carrier)
            d = "+" if d == "-" else "-"

        # After an even number of rows starting from "-", we end
        # having just done a "+" pass, so d is now "-" for next.

        # --- Step 3: transfer odd positions to back bed (rack 0) ---
        # Double each transfer to ensure loops actually move on the
        # machine (some machines skip single transfers reliably —
        # see HW2 Variation 1 for prior instance of this issue).
        for n in range(self.min_n, self.max_n + 1):
            odd_pos = 2 * n + 1
            self.xfer(f"f{odd_pos}", f"b{odd_pos}")
        for n in range(self.min_n, self.max_n + 1):
            odd_pos = 2 * n + 1
            self.xfer(f"f{odd_pos}", f"b{odd_pos}")

        self.direction[carrier] = "-"

    def cast_on_flat(self, carrier):
        """
        Alternating-tuck cast-on on the front bed for flat knitting.
        Just delegates to the parent cast_on().
        """
        assert not self.is_tubular, "cast_on_flat requires flat mode"
        self.inhook(carrier)
        self.cast_on(carrier)
        self.releasehook(carrier)

    # ----------------------------------------------------------------
    # Row knitting
    # ----------------------------------------------------------------

    def knit_tubular_row(self, carrier):
        """
        Knit one row of plain tubular fabric (two passes: front + back).
        Respects the carrier's current direction.
        Follows J-30.js knitRow() convention.
        """
        assert self.is_tubular, "knit_tubular_row requires tubular mode"

        if self.direction[carrier] == "-":
            for n in range(self.max_n, self.min_n - 1, -1):
                self.knit("-", self._loc("f", n), carrier)
            for n in range(self.min_n, self.max_n + 1):
                self.knit("+", self._loc("b", n), carrier)
        else:
            for n in range(self.min_n, self.max_n + 1):
                self.knit("+", self._loc("f", n), carrier)
            for n in range(self.max_n, self.min_n - 1, -1):
                self.knit("-", self._loc("b", n), carrier)

    def knit_flat_row(self, carrier):
        """
        Knit one row of flat fabric on the front bed.
        Delegates to the parent knit_row.
        """
        assert not self.is_tubular, "knit_flat_row requires flat mode"
        self.knit_row("f", carrier)

    def knit_body_row(self, carrier):
        """
        Knit one row in the appropriate mode (tubular or flat).
        """
        if self.is_tubular:
            self.knit_tubular_row(carrier)
        else:
            self.knit_flat_row(carrier)

    # ----------------------------------------------------------------
    # Short rows (translated from J-30.js shortRows)
    # ----------------------------------------------------------------

    def short_rows(self, turns, carrier):
        """
        Perform a series of short-row turns on a tubular piece.

        Translated from J-30.js shortRows(). A short row walks around
        the tube knitting each stitch until reaching a designated turn
        point, where it tucks and reverses.

        Parameters:
            turns:   list of dicts with keys 'b' (bed: 'f' or 'b') and
                     'n' (logical needle index) — the point to turn at.
                     Example: [{'b': 'b', 'n': 8}, {'b': 'f', 'n': 3}]
            carrier: the yarn carrier to use
        """
        assert self.is_tubular, "short_rows requires tubular mode"

        # State: next stitch to make
        n = self.max_n
        b = "f"
        d = "-"

        def step():
            nonlocal n, b, d
            if d == "-":
                if n == self.min_n:
                    d = "+"
                    b = "b" if b == "f" else "f"
                else:
                    n -= 1
            else:
                if n == self.max_n:
                    d = "-"
                    b = "b" if b == "f" else "f"
                else:
                    n += 1

        def do_knit():
            nonlocal n, b, d
            self.knit(d, self._loc(b, n), carrier)
            step()

        def tuck_and_turn():
            nonlocal n, b, d
            self.tuck(d, self._loc(b, n), carrier)
            d = "-" if d == "+" else "+"
            step()

        for turn in turns:
            while n != turn["n"] or b != turn["b"]:
                do_knit()
            tuck_and_turn()

        # Finish last row; knit until we're back at (max_n, 'f')
        while not (n == self.max_n and b == "f"):
            do_knit()

    def short_row_flat(self, work_min, work_max, carrier):
        """
        Perform a short-row turn on a flat piece. Knits only needles
        in [work_min, work_max], tucks at the boundary to close the gap,
        then reverses direction.

        All positions are absolute needle indices.

        Parameters:
            work_min: absolute needle index of the leftmost working needle
            work_max: absolute needle index of the rightmost working needle
            carrier:  the yarn carrier to use
        """
        assert not self.is_tubular, "short_row_flat requires flat mode"
        assert self.min_n <= work_min <= work_max <= self.max_n, (
            f"Working range [{work_min}, {work_max}] must be within "
            f"active range [{self.min_n}, {self.max_n}]"
        )

        direction = self.direction[carrier]
        if direction == "-":
            for n in range(work_max, work_min - 1, -1):
                self.knit("-", f"f{n}", carrier)
            if work_min > self.min_n:
                self.tuck("-", f"f{work_min - 1}", carrier)
        else:
            for n in range(work_min, work_max + 1):
                self.knit("+", f"f{n}", carrier)
            if work_max < self.max_n:
                self.tuck("+", f"f{work_max + 1}", carrier)

        self._flip_direction(carrier)

    # ----------------------------------------------------------------
    # Decrease (translated from J-30.js decrease + decrease.js)
    #
    # Both decrease methods take an absolute needle position where
    # the stacking/merge happens.
    # ----------------------------------------------------------------

    def _validate_position(self, position):
        """Check that a logical needle position is in the active range."""
        assert self.min_n <= position <= self.max_n, (
            f"Position {position} is outside the active range "
            f"[{self.min_n}, {self.max_n}]"
        )

    def _do_decrease_left(self, position):
        """
        Internal: left-leaning decrease at `position`.

        Shifts all stitches from min_n to position-1 one position
        rightward. The stitch at min_n stacks onto min_n+1. min_n
        advances by 1.

        For flat (from decrease.js):
          xfer f{min_n..position-1} -> back, rack 1,
          xfer back -> front (shifted right by 1), rack 0.

        For tubular (from J-30.js):
          Same idea but with rack ±2 and both even/odd physical needles.
        """
        self._validate_position(position)
        assert position > self.min_n, (
            f"decrease_left position ({position}) must be > min_n ({self.min_n})"
        )

        if self.is_tubular:
            for n in range(self.min_n, position):
                self.xfer(f"f{n * 2}", f"b{n * 2}")
            self.rack(2)
            for n in range(self.min_n, position):
                self.xfer(f"b{n * 2 + 1}", f"f{(n + 1) * 2 + 1}")
                self.xfer(f"b{n * 2}", f"f{(n + 1) * 2}")
            self.rack(0)
            for n in range(self.min_n, position):
                self.xfer(f"f{(n + 1) * 2 + 1}", f"b{(n + 1) * 2 + 1}")
        else:
            for n in range(self.min_n, position):
                self.xfer(f"f{n}", f"b{n}")
            self.rack(1)
            for n in range(self.min_n, position):
                self.xfer(f"b{n}", f"f{n + 1}")
            self.rack(0)

        self.min_n += 1

    def _do_decrease_right(self, position):
        """
        Internal: right-leaning decrease at `position`.

        Shifts all stitches from position+1 to max_n one position
        leftward. The stitch at max_n stacks onto max_n-1. max_n
        decreases by 1.

        For flat (from decrease.js):
          xfer f{position+1..max_n} -> back, rack -1,
          xfer back -> front (shifted left by 1), rack 0.

        For tubular (from J-30.js):
          Same idea but with rack ±2 and both even/odd physical needles.
        """
        self._validate_position(position)
        assert position < self.max_n, (
            f"decrease_right position ({position}) must be < max_n ({self.max_n})"
        )

        if self.is_tubular:
            for n in range(self.max_n, position, -1):
                self.xfer(f"f{n * 2}", f"b{n * 2}")
            self.rack(-2)
            for n in range(self.max_n, position, -1):
                self.xfer(f"b{n * 2}", f"f{(n - 1) * 2}")
                self.xfer(f"b{n * 2 + 1}", f"f{(n - 1) * 2 + 1}")
            self.rack(0)
            for n in range(self.max_n, position, -1):
                self.xfer(f"f{(n - 1) * 2 + 1}", f"b{(n - 1) * 2 + 1}")
        else:
            for n in range(self.max_n, position, -1):
                self.xfer(f"f{n}", f"b{n}")
            self.rack(-1)
            for n in range(self.max_n, position, -1):
                self.xfer(f"b{n}", f"f{n - 1}")
            self.rack(0)

        self.max_n -= 1

    def decrease(self, position, lean="left"):
        """
        Decrease by one stitch at absolute needle `position`.

        This is a pure transfer operation (no carrier needed).
        The caller is responsible for knitting a settling row afterward.

        lean="left" (default):
          Shifts min_n..position-1 rightward by 1, stacking onto position.
          min_n advances by 1.

        lean="right":
          Shifts position+1..max_n leftward by 1, stacking onto position.
          max_n decreases by 1.

        Parameters:
            position: absolute needle index where stitches merge
            lean:     "left" (shift left side right) or
                      "right" (shift right side left)
        """
        assert lean in ("left", "right"), f"lean must be 'left' or 'right', got '{lean}'"
        if lean == "left":
            self._do_decrease_left(position)
        else:
            self._do_decrease_right(position)

    def decrease_both(self, left_position=None, right_position=None):
        """
        Decrease on both edges simultaneously, as in J-30.js decrease().

        This is a pure transfer operation (no carrier needed).
        The caller is responsible for knitting a settling row afterward.

        If positions are not provided, defaults to ~25% inset from each
        edge (matching J-30.js).

        Parameters:
            left_position:  absolute position for left decrease (default: auto)
            right_position: absolute position for right decrease (default: auto)
        """
        if left_position is None or right_position is None:
            inset = round(self.width * 0.25)
            if inset < 1:
                inset = 1
            if left_position is None:
                left_position = self.min_n + inset
            if right_position is None:
                right_position = self.max_n - inset

        self._do_decrease_left(left_position)
        self._do_decrease_right(right_position)

    # ----------------------------------------------------------------
    # Increase
    #
    # Accepts one or more absolute positions where new stitches appear.
    # Strategy: transfer-to-open-gaps, then knit a row with twisted
    # tucks at the empty needles. No splits used.
    #
    # Twisted tuck on an empty needle during a "-" pass:
    #   miss - f{n}   (move past the needle)
    #   tuck + f{n}   (reverse to catch the needle)
    #   miss - f{n}   (continue the "-" pass)
    # This anchors a new loop on the empty needle.
    # ----------------------------------------------------------------

    def increase(self, positions, carrier, lean="right"):
        """
        Increase by one or more stitches in a single row using
        twisted tucks (no splits).

        **Important:** this method knits a row with the increases
        embedded, so the caller should NOT knit a separate row.
        The carrier direction MUST be "-" when this is called.

        Procedure:
          1. Cascading transfers to shift stitches and open gaps.
          2. Knit a "-" row; at each gap, do a twisted tuck
             (miss -, tuck +, miss -) instead of a normal knit.

        For flat:  direction flips to "+" afterward.
        For tubular: knits front "-" with twisted tucks at front gaps,
                     then back "+" with twisted tucks at back gaps.
                     Direction stays "-" afterward.

        lean="right" (default):
          Shifts stitches from position..max_n rightward by 1.
          max_n grows by len(positions).

        lean="left":
          Shifts stitches from min_n..position leftward by 1.
          min_n shrinks by len(positions).

        Parameters:
            positions: int or list of ints — absolute needle indices
            carrier:   the carrier to use
            lean:      "right" or "left"
        """
        # Normalize to list
        if isinstance(positions, int):
            positions = [positions]
        assert len(positions) > 0, "positions must not be empty"
        assert lean in ("left", "right"), f"lean must be 'left' or 'right', got '{lean}'"
        assert self.direction[carrier] == "-", (
            f"increase requires carrier direction '-', "
            f"got '{self.direction[carrier]}'"
        )

        # Validate all positions
        for p in positions:
            self._validate_position(p)

        if self.is_tubular:
            self._increase_tubular(positions, carrier, lean)
        else:
            self._increase_flat(positions, carrier, lean)

    def _increase_flat(self, positions, carrier, lean):
        """
        Flat increase with twisted tucks, using lace.js-style transfers.

        Strategy (inspired by lace.js):
          1. Transfer ALL front stitches to back bed (clears front bed).
          2. At rack +1 or -1, transfer the shifting needles to their
             new front positions (shifted by 1).
          3. At rack 0, transfer the unchanged needles back to front.
          4. Knit a "-" row with twisted tucks at the gaps.

        This avoids the issue where partial transfers fail on the machine.
        All positions are handled in a single transfer pass.
        Direction flips "-" → "+".
        """
        num_inc = len(positions)

        if lean == "right":
            positions_sorted = sorted(positions)
            # Build a mapping: old front needle -> new front needle
            # Every needle >= a position gets shifted right by the number
            # of positions at or below it.
            shift_amount = {}
            for n in range(self.min_n, self.max_n + 1):
                shift = sum(1 for p in positions_sorted if p <= n)
                shift_amount[n] = shift

            new_max = self.max_n + num_inc
            # Figure out which new positions will be empty
            occupied_new = set()
            for n in range(self.min_n, self.max_n + 1):
                occupied_new.add(n + shift_amount[n])
            empty_set = set()
            for n in range(self.min_n, new_max + 1):
                if n not in occupied_new:
                    empty_set.add(n)

            # Step 1: all front to back
            for n in range(self.min_n, self.max_n + 1):
                self.xfer(f"f{n}", f"b{n}")

            # Step 2: transfer shifted needles from back to new front pos
            # Group by shift amount to minimize rack changes
            by_shift = {}
            for n in range(self.min_n, self.max_n + 1):
                s = shift_amount[n]
                if s not in by_shift:
                    by_shift[s] = []
                by_shift[s].append(n)

            for s in sorted(by_shift.keys()):
                if s == 0:
                    # No shift, return straight to front at rack 0
                    for n in by_shift[0]:
                        self.xfer(f"b{n}", f"f{n}")
                else:
                    self.rack(s)
                    for n in by_shift[s]:
                        self.xfer(f"b{n}", f"f{n + s}")
                    self.rack(0)

            self.max_n = new_max

        else:  # lean == "left"
            positions_sorted = sorted(positions, reverse=True)
            # Every needle <= a position gets shifted left
            shift_amount = {}
            for n in range(self.min_n, self.max_n + 1):
                shift = sum(1 for p in positions_sorted if p >= n)
                shift_amount[n] = shift

            new_min = self.min_n - num_inc
            occupied_new = set()
            for n in range(self.min_n, self.max_n + 1):
                occupied_new.add(n - shift_amount[n])
            empty_set = set()
            for n in range(new_min, self.max_n + 1):
                if n not in occupied_new:
                    empty_set.add(n)

            # Step 1: all front to back
            for n in range(self.min_n, self.max_n + 1):
                self.xfer(f"f{n}", f"b{n}")

            # Step 2: transfer back to new positions
            by_shift = {}
            for n in range(self.min_n, self.max_n + 1):
                s = shift_amount[n]
                if s not in by_shift:
                    by_shift[s] = []
                by_shift[s].append(n)

            for s in sorted(by_shift.keys()):
                if s == 0:
                    for n in by_shift[0]:
                        self.xfer(f"b{n}", f"f{n}")
                else:
                    self.rack(-s)
                    for n in by_shift[s]:
                        self.xfer(f"b{n}", f"f{n - s}")
                    self.rack(0)

            self.min_n = new_min

        # -- Knit "-" row with twisted tucks at gaps --
        for n in range(self.max_n, self.min_n - 1, -1):
            if n in empty_set:
                self.miss("-", f"f{n}", carrier)
                self.tuck("+", f"f{n}", carrier)
                self.miss("-", f"f{n}", carrier)
            else:
                self.knit("-", f"f{n}", carrier)

        self._flip_direction(carrier)  # "-" → "+"

    def _increase_tubular(self, positions, carrier, lean):
        """
        Tubular increase with twisted tucks, lace.js-style transfers.

        Strategy:
          1. Transfer ALL front (even) needles to back bed.
          2. At rack ±2, transfer shifting needles to new positions.
             At rack 0, return unchanged needles.
          3. Move the back (odd) needles similarly (via front as staging).
          4. Knit front "-" pass with twisted tucks at empty fronts.
          5. Knit back "+" pass with twisted tucks at empty backs.
        Direction stays "-".
        """
        num_inc = len(positions)

        if lean == "right":
            positions_sorted = sorted(positions)
            # Build shift map: how much each logical position shifts right
            shift_amount = {}
            for n in range(self.min_n, self.max_n + 1):
                shift_amount[n] = sum(1 for p in positions_sorted if p <= n)

            new_max = self.max_n + num_inc
            occupied_new = set()
            for n in range(self.min_n, self.max_n + 1):
                occupied_new.add(n + shift_amount[n])
            empty_set = set()
            for n in range(self.min_n, new_max + 1):
                if n not in occupied_new:
                    empty_set.add(n)

            # -- Move front (even) needles --
            # Step 1a: all front to back
            for n in range(self.min_n, self.max_n + 1):
                self.xfer(f"f{n * 2}", f"b{n * 2}")

            # Step 1b: transfer to new front positions by shift amount
            by_shift = {}
            for n in range(self.min_n, self.max_n + 1):
                s = shift_amount[n]
                if s not in by_shift:
                    by_shift[s] = []
                by_shift[s].append(n)

            for s in sorted(by_shift.keys()):
                if s == 0:
                    for n in by_shift[0]:
                        self.xfer(f"b{n * 2}", f"f{n * 2}")
                else:
                    self.rack(s * 2)
                    for n in by_shift[s]:
                        self.xfer(f"b{n * 2}", f"f{(n + s) * 2}")
                    self.rack(0)

            # -- Move back (odd) needles --
            # Step 2a: all back to front (staging)
            for n in range(self.min_n, self.max_n + 1):
                self.xfer(f"b{n * 2 + 1}", f"f{n * 2 + 1}")

            # Step 2b: transfer to new back positions via staging
            # For f->b: racking = front_idx - back_idx = (n*2+1) - ((n+s)*2+1) = -2s
            for s in sorted(by_shift.keys()):
                if s == 0:
                    for n in by_shift[0]:
                        self.xfer(f"f{n * 2 + 1}", f"b{n * 2 + 1}")
                else:
                    self.rack(-(s * 2))
                    for n in by_shift[s]:
                        self.xfer(f"f{n * 2 + 1}", f"b{(n + s) * 2 + 1}")
                    self.rack(0)

            self.max_n = new_max

        else:  # lean == "left"
            positions_sorted = sorted(positions, reverse=True)
            shift_amount = {}
            for n in range(self.min_n, self.max_n + 1):
                shift_amount[n] = sum(1 for p in positions_sorted if p >= n)

            new_min = self.min_n - num_inc
            occupied_new = set()
            for n in range(self.min_n, self.max_n + 1):
                occupied_new.add(n - shift_amount[n])
            empty_set = set()
            for n in range(new_min, self.max_n + 1):
                if n not in occupied_new:
                    empty_set.add(n)

            # -- Move front (even) needles --
            for n in range(self.min_n, self.max_n + 1):
                self.xfer(f"f{n * 2}", f"b{n * 2}")

            by_shift = {}
            for n in range(self.min_n, self.max_n + 1):
                s = shift_amount[n]
                if s not in by_shift:
                    by_shift[s] = []
                by_shift[s].append(n)

            for s in sorted(by_shift.keys()):
                if s == 0:
                    for n in by_shift[0]:
                        self.xfer(f"b{n * 2}", f"f{n * 2}")
                else:
                    self.rack(-(s * 2))
                    for n in by_shift[s]:
                        self.xfer(f"b{n * 2}", f"f{(n - s) * 2}")
                    self.rack(0)

            # -- Move back (odd) needles --
            for n in range(self.min_n, self.max_n + 1):
                self.xfer(f"b{n * 2 + 1}", f"f{n * 2 + 1}")

            # For f->b: racking = front_idx - back_idx = (n*2+1) - ((n-s)*2+1) = 2s
            for s in sorted(by_shift.keys()):
                if s == 0:
                    for n in by_shift[0]:
                        self.xfer(f"f{n * 2 + 1}", f"b{n * 2 + 1}")
                else:
                    self.rack(s * 2)
                    for n in by_shift[s]:
                        self.xfer(f"f{n * 2 + 1}", f"b{(n - s) * 2 + 1}")
                    self.rack(0)

            self.min_n = new_min

        # -- Front "-" pass with twisted tucks at empty positions --
        for n in range(self.max_n, self.min_n - 1, -1):
            loc = self._loc("f", n)
            if n in empty_set:
                self.miss("-", loc, carrier)
                self.tuck("+", loc, carrier)
                self.miss("-", loc, carrier)
            else:
                self.knit("-", loc, carrier)

        # -- Back "+" pass with twisted tucks at empty positions --
        for n in range(self.min_n, self.max_n + 1):
            loc = self._loc("b", n)
            if n in empty_set:
                self.miss("+", loc, carrier)
                self.tuck("-", loc, carrier)
                self.miss("+", loc, carrier)
            else:
                self.knit("+", loc, carrier)
        # Direction stays "-" for tubular

    # ----------------------------------------------------------------
    # Bind-off
    # ----------------------------------------------------------------

    def bind_off_tubular(self, carrier):
        """
        Chain bind-off for tubular fabric, translated from J-30.js.

        Binds off the front bed right-to-left:
          knit stitch, miss past neighbor, xfer to back, rack, xfer back to next front.
        Then binds off the back bed left-to-right similarly.
        Finishes with a small tag for security.
        """
        assert self.is_tubular, "bind_off_tubular requires tubular mode"

        # Bind-off (front): right-to-left
        for n in range(self.max_n, self.min_n, -1):
            self.knit("-", self._loc("f", n), carrier)
            self.miss("-", self._loc("f", n - 1), carrier)
            self.xfer(self._loc("f", n), f"b{n * 2}")
            self.rack(-2)
            self.xfer(f"b{n * 2}", self._loc("f", n - 1))
            self.rack(0)

        # Leftmost front stitch: chain onto back bed
        self.knit("-", self._loc("f", self.min_n), carrier)
        self.tuck("-", self._loc("f", self.min_n - 1), carrier)
        self.rack(-1)
        self.xfer(self._loc("f", self.min_n), self._loc("b", self.min_n))
        self.rack(0)

        # Bind-off (back): left-to-right
        for n in range(self.min_n, self.max_n):
            self.knit("+", self._loc("b", n), carrier)
            self.miss("+", self._loc("b", n + 1), carrier)
            self.xfer(self._loc("b", n), f"f{n * 2 + 1}")
            self.rack(-2)
            self.xfer(f"f{n * 2 + 1}", self._loc("b", n + 1))
            self.rack(0)

        # Tag (on back)
        loc_max_b = self._loc("b", self.max_n)
        self.knit("+", loc_max_b, carrier)
        self.knit("-", loc_max_b, carrier)
        self.knit("+", loc_max_b, carrier)
        self.knit("-", loc_max_b, carrier)
        self.tuck("-", self._loc("b", self.max_n - 1), carrier)
        self.tuck("+", self._loc("b", self.max_n - 2), carrier)
        self.knit("+", self._loc("b", self.max_n - 1), carrier)
        self.knit("+", loc_max_b, carrier)
        for _ in range(4):
            for n in range(self.max_n, self.max_n - 3, -1):
                self.knit("-", self._loc("b", n), carrier)
            for n in range(self.max_n - 2, self.max_n + 1):
                self.knit("+", self._loc("b", n), carrier)

        self.outhook(carrier)

    def bind_off_flat(self, carrier):
        """
        Stack bind-off for flat fabric (delegates to KnittingHelper.stack_bind_off).
        """
        assert not self.is_tubular, "bind_off_flat requires flat mode"
        self.stack_bind_off(carrier, min_n=self.min_n, max_n=self.max_n)

    def bind_off_chain_birdseye(self, carrier):
        """
        Chain bind-off from image-tj.js / rainbow-tj.js.
        Works at rack 0.25, chaining each stitch onto the next.
        """
        direction = self.direction[carrier]

        self.rack(0.25)
        if direction == "+":
            for n in range(self.min_n, self.max_n + 1):
                self.knit("+", f"f{n}", carrier)
                self.rack(0)
                self.xfer(f"f{n}", f"b{n}")
                self.knit("-", f"b{n}", carrier)
                if n != self.max_n:
                    self.rack(1)
                    self.xfer(f"b{n}", f"f{n + 1}")
                else:
                    self.xfer(f"b{n}", f"f{n}")
        else:
            for n in range(self.max_n, self.min_n - 1, -1):
                self.knit("-", f"b{n}", carrier)
                self.rack(0)
                self.xfer(f"b{n}", f"f{n}")
                self.knit("+", f"f{n}", carrier)
                if n != self.min_n:
                    self.rack(1)
                    self.xfer(f"f{n}", f"b{n - 1}")

        self.rack(0)

    def bind_off_body(self, carrier):
        """Bind off in the appropriate mode (tubular or flat)."""
        if self.is_tubular:
            self.bind_off_tubular(carrier)
        else:
            self.bind_off_flat(carrier)

    # ----------------------------------------------------------------
    # Tubular Colorwork (Stranded & Plating)
    # ----------------------------------------------------------------

    def prep_tubular_colorwork(self, carriers):
        """
        Bring in additional carriers for tubular colorwork.

        Call this before knit_tubular_colorwork_row() or
        knit_tubular_plating_row(). The main carrier (used for cast-on)
        should already be active. Additional carriers are inhook'd and
        stabilized with one tubular round each.

        Parameters:
            carriers: list of all carrier numbers used in the colorwork
                      pattern (including the already-active main carrier)
        """
        assert self.is_tubular, "prep_tubular_colorwork requires tubular mode"
        for car in sorted(carriers):
            if car not in self.active_carriers:
                self.inhook(car)
                self.knit_tubular_row(car)
                self.releasehook(car)

    def knit_tubular_colorwork_row(self, front_pattern, back_pattern=None):
        """
        Knit one tubular colorwork row using stranded technique.

        Each carrier traverses the full tube (front + back), knitting
        at positions assigned to it and missing at other positions.
        Floats form inside the tube. Similar to HW3's stranded colorwork
        but adapted for half-gauge tubular knitting.

        Front and back can have independent patterns, allowing different
        designs on each side of the tube.

        Parameters:
            front_pattern: list of carrier numbers, length == self.width.
                           Each element specifies which carrier knits that
                           front-bed stitch position.
            back_pattern:  list of carrier numbers, length == self.width.
                           Each element specifies which carrier knits that
                           back-bed stitch position. If None, uses
                           front_pattern for both sides (same pattern
                           on front and back).

        All carriers must already be active (see prep_tubular_colorwork).
        Direction stays unchanged after this call.
        """
        assert self.is_tubular, "knit_tubular_colorwork_row requires tubular mode"
        assert len(front_pattern) == self.width, \
            f"front_pattern length ({len(front_pattern)}) must match width ({self.width})"

        if back_pattern is None:
            back_pattern = front_pattern
        else:
            assert len(back_pattern) == self.width, \
                f"back_pattern length ({len(back_pattern)}) must match width ({self.width})"

        # Group positions by carrier for each bed independently
        front_carrier_positions = {}
        for col, car in enumerate(front_pattern):
            front_carrier_positions.setdefault(car, set()).add(col + self.min_n)

        back_carrier_positions = {}
        for col, car in enumerate(back_pattern):
            back_carrier_positions.setdefault(car, set()).add(col + self.min_n)

        # All carriers that appear in either pattern
        all_carriers = sorted(
            set(front_carrier_positions.keys()) | set(back_carrier_positions.keys())
        )

        # Each carrier does a complete round with knit/miss
        for car in all_carriers:
            front_positions = front_carrier_positions.get(car, set())
            back_positions = back_carrier_positions.get(car, set())

            if self.direction[car] == "-":
                # Front pass: right-to-left
                for n in range(self.max_n, self.min_n - 1, -1):
                    loc = self._loc("f", n)
                    if n in front_positions:
                        self.knit("-", loc, car)
                    else:
                        self.miss("-", loc, car)
                # Back pass: left-to-right
                for n in range(self.min_n, self.max_n + 1):
                    loc = self._loc("b", n)
                    if n in back_positions:
                        self.knit("+", loc, car)
                    else:
                        self.miss("+", loc, car)
            else:
                # Front pass: left-to-right
                for n in range(self.min_n, self.max_n + 1):
                    loc = self._loc("f", n)
                    if n in front_positions:
                        self.knit("+", loc, car)
                    else:
                        self.miss("+", loc, car)
                # Back pass: right-to-left
                for n in range(self.max_n, self.min_n - 1, -1):
                    loc = self._loc("b", n)
                    if n in back_positions:
                        self.knit("-", loc, car)
                    else:
                        self.miss("-", loc, car)
            # Direction stays unchanged for tubular

    def knit_tubular_plating_row(self, pattern_row, carrier_a, carrier_b):
        """
        Knit one tubular colorwork row using plating technique.

        Both carriers travel together in every stitch. The carrier order
        in the knitout instruction determines which color shows on the
        face of the fabric:
          - Front bed: first carrier listed shows on the face (outside)
          - Back bed: carrier order is reversed so the same color appears
            on the outside of the tube

        Parameters:
            pattern_row: list of carrier numbers (each must be carrier_a
                         or carrier_b), length == self.width.
                         Specifies which carrier shows on the outside
                         of the tube at each position.
            carrier_a:   first carrier number
            carrier_b:   second carrier number

        Both carriers must be active. Direction stays unchanged.
        """
        assert self.is_tubular, "knit_tubular_plating_row requires tubular mode"
        assert len(pattern_row) == self.width, \
            f"pattern_row length ({len(pattern_row)}) must match width ({self.width})"
        self._validate_active_carrier(carrier_a)
        self._validate_active_carrier(carrier_b)

        if self.direction[carrier_a] == "-":
            # Front pass: right-to-left
            for n in range(self.max_n, self.min_n - 1, -1):
                idx = n - self.min_n
                loc = self._loc("f", n)
                if pattern_row[idx] == carrier_a:
                    # carrier_a on outside: list first on front bed
                    self.instructions.append(
                        f"knit - {loc} {carrier_a} {carrier_b}")
                else:
                    self.instructions.append(
                        f"knit - {loc} {carrier_b} {carrier_a}")
            # Back pass: left-to-right (reversed carrier order for outside)
            for n in range(self.min_n, self.max_n + 1):
                idx = n - self.min_n
                loc = self._loc("b", n)
                if pattern_row[idx] == carrier_a:
                    # carrier_a on outside: list SECOND on back bed
                    self.instructions.append(
                        f"knit + {loc} {carrier_b} {carrier_a}")
                else:
                    self.instructions.append(
                        f"knit + {loc} {carrier_a} {carrier_b}")
        else:
            # Front pass: left-to-right
            for n in range(self.min_n, self.max_n + 1):
                idx = n - self.min_n
                loc = self._loc("f", n)
                if pattern_row[idx] == carrier_a:
                    self.instructions.append(
                        f"knit + {loc} {carrier_a} {carrier_b}")
                else:
                    self.instructions.append(
                        f"knit + {loc} {carrier_b} {carrier_a}")
            # Back pass: right-to-left (reversed carrier order for outside)
            for n in range(self.max_n, self.min_n - 1, -1):
                idx = n - self.min_n
                loc = self._loc("b", n)
                if pattern_row[idx] == carrier_a:
                    self.instructions.append(
                        f"knit - {loc} {carrier_b} {carrier_a}")
                else:
                    self.instructions.append(
                        f"knit - {loc} {carrier_a} {carrier_b}")

    def end_tubular_colorwork(self, carriers, main_carrier):
        """
        End a tubular colorwork section.

        Outhooks all carriers except the main carrier, which continues
        for the rest of the piece.

        Parameters:
            carriers:      list of all carrier numbers used in the pattern
            main_carrier:  the carrier to keep active
        """
        for car in sorted(carriers):
            if car != main_carrier and car in self.active_carriers:
                self.outhook(car)

    # ----------------------------------------------------------------
    # Tubular Ribbing
    # ----------------------------------------------------------------

    def knit_tubular_rib_row(self, kp_pattern, carrier):
        """
        Knit one tubular row with a knit/purl ribbing pattern.

        Similar to HW2's array_to_kp_cols() but for half-gauge tubes.
        Each column is either knit (0) or purl (1) as seen from the
        outside of the tube. The pattern applies consistently around
        the entire tube.

        Each rib row is self-contained: it transfers stitches to the
        appropriate bed before each pass and restores the standard
        half-gauge layout afterward. No racking is needed because
        the half-gauge layout leaves even/odd positions available.

        For the front pass:
          - Knit positions (0): stay on front bed f{2n}, knit normally
          - Purl positions (1): transfer to b{2n}, knit on back bed

        For the back pass:
          - Knit positions (0): transfer from b{2n+1} to f{2n+1},
            knit on front bed (V shows on outside)
          - Purl positions (1): stay on back bed b{2n+1}, knit normally
            (purl bump shows on outside)

        After the row, all stitches are restored to standard half-gauge
        positions (front = f{2n}, back = b{2n+1}).

        Parameters:
            kp_pattern: list of 0s and 1s, length == self.width.
                        0 = knit stitch (V shows on outside)
                        1 = purl stitch (bump shows on outside)
            carrier:    the yarn carrier to use

        Direction stays unchanged after this call.
        """
        assert self.is_tubular, "knit_tubular_rib_row requires tubular mode"
        assert len(kp_pattern) == self.width, \
            f"kp_pattern length ({len(kp_pattern)}) must match width ({self.width})"

        purl_set = set()
        knit_set = set()
        for i, v in enumerate(kp_pattern):
            n = i + self.min_n
            if v == 1:
                purl_set.add(n)
            else:
                knit_set.add(n)

        if self.direction[carrier] == "-":
            # === Front pass (right-to-left) ===

            # Step 1: Transfer front purl stitches to back bed
            # At half gauge, b{2n} is empty so xfer f{2n} -> b{2n} is safe
            for n in purl_set:
                self.xfer(f"f{2*n}", f"b{2*n}")

            # Step 2: Knit front pass
            for n in range(self.max_n, self.min_n - 1, -1):
                if n in knit_set:
                    self.knit("-", f"f{2*n}", carrier)
                else:
                    self.knit("-", f"b{2*n}", carrier)

            # Step 3: Restore front purls + move back knits to front
            for n in purl_set:
                self.xfer(f"b{2*n}", f"f{2*n}")
            for n in knit_set:
                self.xfer(f"b{2*n+1}", f"f{2*n+1}")

            # === Back pass (left-to-right) ===

            # Step 4: Knit back pass
            for n in range(self.min_n, self.max_n + 1):
                if n in knit_set:
                    self.knit("+", f"f{2*n+1}", carrier)
                else:
                    self.knit("+", f"b{2*n+1}", carrier)

            # Step 5: Restore back knits to back bed
            for n in knit_set:
                self.xfer(f"f{2*n+1}", f"b{2*n+1}")

        else:  # direction "+"
            # === Front pass (left-to-right) ===
            for n in purl_set:
                self.xfer(f"f{2*n}", f"b{2*n}")

            for n in range(self.min_n, self.max_n + 1):
                if n in knit_set:
                    self.knit("+", f"f{2*n}", carrier)
                else:
                    self.knit("+", f"b{2*n}", carrier)

            for n in purl_set:
                self.xfer(f"b{2*n}", f"f{2*n}")
            for n in knit_set:
                self.xfer(f"b{2*n+1}", f"f{2*n+1}")

            # === Back pass (right-to-left) ===
            for n in range(self.max_n, self.min_n - 1, -1):
                if n in knit_set:
                    self.knit("-", f"f{2*n+1}", carrier)
                else:
                    self.knit("-", f"b{2*n+1}", carrier)

            for n in knit_set:
                self.xfer(f"f{2*n+1}", f"b{2*n+1}")

    # ----------------------------------------------------------------
    # Experimental Cast-On (Non-Crossing Tuck)
    # ----------------------------------------------------------------

    def cast_on_tubular_tuck_experimental(self, carrier, settling_rows=4):
        """
        Experimental all-needle knit cast-on for half-gauge tube.

        Based on the rainbow-tj.js / image-tj.js approach: knit (not tuck)
        on all needles, alternating between front and back beds each needle.
        This places stitches on both beds immediately without needing a
        transfer step to separate them, and avoids connecting front and
        back beds the way an alternating-tuck cast-on can.

        WARNING: This is experimental. Use for experimentation only.

        Steps:
          1. Knit right-to-left ("-") alternating f/b on each needle
             (even-offset from max → front, odd-offset → back)
          2. Knit left-to-right ("+") alternating b/f on each needle
             (reverses the bed assignment so each needle gets both passes)
          3. Now stitches are on both beds at full gauge (every needle).
             Transfer to half-gauge: keep f{2n} and b{2n+1}, drop the rest.
          4. Settling rows as standard half-gauge tubular

        After this call, the fabric is in standard half-gauge layout
        and ready for knit_tubular_row().

        Parameters:
            carrier:        the yarn carrier to use
            settling_rows:  tubular settling rows after cast-on
                            (default 4, forced even for consistency)
        """
        assert self.is_tubular, \
            "cast_on_tubular_tuck_experimental requires tubular mode"
        if settling_rows % 2 != 0:
            settling_rows += 1

        # Physical needle range spanning the half-gauge layout
        phys_min = 2 * self.min_n        # leftmost front needle
        phys_max = 2 * self.max_n + 1    # rightmost back-bed position

        self.inhook(carrier)

        # Step 1: Knit right-to-left, alternating f/b
        # Following rainbow-tj: (max-n)%2==0 → front, else → back
        for n in range(phys_max, phys_min - 1, -1):
            if (phys_max - n) % 2 == 0:
                self.knit("-", f"f{n}", carrier)
            else:
                self.knit("-", f"b{n}", carrier)

        # Step 2: Knit left-to-right, alternating b/f (reversed beds)
        for n in range(phys_min, phys_max + 1):
            if (phys_max - n) % 2 == 0:
                self.knit("+", f"b{n}", carrier)
            else:
                self.knit("+", f"f{n}", carrier)

        self.releasehook(carrier)

        # Step 3: Transition to half-gauge
        # After the two passes, every physical needle has a loop on both
        # front and back. We want to keep only f{2n} and b{2n+1}.
        # Transfer unwanted positions: f{2n+1} → drop, b{2n} → drop
        # Actually: xfer f{odd} to b{odd} (stacking), then drop b{even}
        # Simpler: just drop the needles we don't want.
        for n in range(self.min_n, self.max_n + 1):
            # Drop f{2n+1} (odd front positions — not part of half-gauge front)
            self.drop(f"f{2*n+1}")
            # Drop b{2n} (even back positions — not part of half-gauge back)
            self.drop(f"b{2*n}")

        # Step 4: Settling rows as tubular (standard half-gauge)
        self.direction[carrier] = "-"
        for _ in range(settling_rows):
            self.knit_tubular_row(carrier)

    # ----------------------------------------------------------------
    # Teardown
    # ----------------------------------------------------------------

    def drop_all_tubular(self, carrier):
        """
        Quick teardown for tubular fabric: outhook the carrier, then
        drop every loop on both beds at the half-gauge positions.
        Useful for fast iteration when you don't need a proper bind-off.
        """
        assert self.is_tubular, "drop_all_tubular requires tubular mode"
        self.outhook(carrier)
        for n in range(self.min_n, self.max_n + 1):
            self.drop(f"f{2 * n}")       # front even
            self.drop(f"b{2 * n + 1}")   # back odd


def test_stranded_colorwork_tube():
    """Stranded colorwork on a tube — different patterns on front and back."""
    print("--- Test: Stranded Colorwork Tube (Front/Back Independent) ---")
    width = 10
    sh = ShapingHelper(width=width, is_tubular=True)
    sh.standard_headers()

    main_carrier = 3
    sh.cast_on_all_needle_transition(carrier=main_carrier, settling_rows=4)

    # Plain rows before colorwork
    for _ in range(5):
        sh.knit_tubular_row(carrier=main_carrier)

    # Bring in second carrier for colorwork
    carriers = [3, 4]
    sh.prep_tubular_colorwork(carriers)

    # Front: checkerboard, Back: vertical stripes
    for row_idx in range(10):
        front_row = []
        back_row = []
        for col in range(width):
            # Front: checkerboard
            front_row.append(3 if (row_idx + col) % 2 == 0 else 4)
            # Back: vertical stripes (5 wide each)
            back_row.append(3 if col < width // 2 else 4)
        sh.knit_tubular_colorwork_row(front_row, back_row)

    sh.end_tubular_colorwork(carriers, main_carrier)

    # Plain rows after colorwork
    for _ in range(5):
        sh.knit_tubular_row(carrier=main_carrier)

    sh.drop_all_tubular(carrier=main_carrier)
    output = sh.write("test_stranded_tube.k")
    print(f"  Generated {len(output.splitlines())} knitout lines")


def test_stranded_three_color():
    """Stranded colorwork with three carriers."""
    print("\n--- Test: Stranded Colorwork Tube (3-Color Stripes) ---")
    width = 12
    sh = ShapingHelper(width=width, is_tubular=True)
    sh.standard_headers()

    main_carrier = 1
    sh.cast_on_all_needle_transition(carrier=main_carrier, settling_rows=4)

    for _ in range(5):
        sh.knit_tubular_row(carrier=main_carrier)

    # Three carriers: horizontal color stripes (4 stitches each)
    carriers = [1, 2, 3]
    sh.prep_tubular_colorwork(carriers)

    for row_idx in range(8):
        pattern_row = []
        for col in range(width):
            if col < 4:
                pattern_row.append(1)
            elif col < 8:
                pattern_row.append(2)
            else:
                pattern_row.append(3)
        # knit the same checkboard on front and back
        sh.knit_tubular_colorwork_row(pattern_row)

    sh.end_tubular_colorwork(carriers, main_carrier)

    for _ in range(5):
        sh.knit_tubular_row(carrier=main_carrier)

    sh.drop_all_tubular(carrier=main_carrier)
    output = sh.write("test_stranded_3color_tube.k")
    print(f"  Generated {len(output.splitlines())} knitout lines")


def test_plating_colorwork_tube():
    """Plating colorwork on a tube using two carriers."""
    print("\n--- Test: Plating Colorwork Tube (Vertical Stripes) ---")
    width = 10
    sh = ShapingHelper(width=width, is_tubular=True)
    sh.standard_headers()

    main_carrier = 3
    sh.cast_on_all_needle_transition(carrier=main_carrier, settling_rows=4)

    for _ in range(5):
        sh.knit_tubular_row(carrier=main_carrier)

    # Bring in second carrier for plating
    carrier_a = 3
    carrier_b = 4
    sh.prep_tubular_colorwork([carrier_a, carrier_b])

    # Vertical stripe pattern: alternating bands
    for row_idx in range(12):
        pattern_row = []
        for col in range(width):
            # 3-stitch wide vertical stripes
            if (col % 6) < 3:
                pattern_row.append(carrier_a)
            else:
                pattern_row.append(carrier_b)
        sh.knit_tubular_plating_row(pattern_row, carrier_a, carrier_b)

    sh.end_tubular_colorwork([carrier_a, carrier_b], main_carrier)

    for _ in range(5):
        sh.knit_tubular_row(carrier=main_carrier)

    sh.drop_all_tubular(carrier=main_carrier)
    output = sh.write("test_plating_tube.k")
    print(f"  Generated {len(output.splitlines())} knitout lines")


if __name__ == "__main__":
    test_stranded_colorwork_tube()
    test_stranded_three_color()
    test_plating_colorwork_tube()
    print("\nAll colorwork tube tests completed.")
