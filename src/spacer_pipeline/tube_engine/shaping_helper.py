"""

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

import warnings

from .knitting_helper import KnittingHelper


class ShapingHelper(KnittingHelper):
    """
    (deprecated documentation pertaining gauge)
    A knitting helper that adds half-gauge tubular knitting and support
    for shaping operations.

    Supports both flat (sheet) and tubular (tube) knitting modes.
    For tubular knitting, half-gauge is used by default:
      - Front needles are at even positions (2*n)
      - Back needles are at odd positions (2*n+1)
    This follows the J-30.js convention: loc('f', n) = f{2*n}, loc('b', n) = b{2*n+1}.

    Inherits min_n/max_n tracking from KnittingHelper. Adds:
        is_tubular:    whether this is a tube (half gauge)

    Caveats students should keep in mind:
      * Tubular pieces assume the front and back beds stay balanced, which
        is why a single (min_n, max_n) range describes the whole tube. An
        increase/decrease applies symmetrically to both beds.
      * Physical machines have a limited racking range. MAX_RACK records the
        largest |rack| we expect to be safe. Shaping operations that would
        exceed it still emit valid knitout, but warn — see _increase_by_positions.
        On a half-gauge tube each unit of logical shift costs TWO racking
        steps, so shifting a needle by 2 (e.g. two same-side increases that
        stack onto one needle) already reaches rack 4.
    """

    # Largest racking magnitude assumed safe on the target machine.
    # Override per-instance (sh.MAX_RACK = 8) if your hardware allows more.
    MAX_RACK = 8

    def __init__(self, width, is_tubular=True, gauge = 2, side_slack=False, double_transfers=False, drop_repeats=None):
        """
        Initialize the ShapingHelper.

        Parameters:
            width:      number of logical stitches for this piece
            is_tubular: whether this is a tube; if True, uses n-gauge layout
            gauge:      the gauge of knitting
            side_slack: whether to include additional tucks on both ends to add more slack
            double_transfers: repeat selected whole transfer sweeps
            drop_repeats: None for legacy output; positive count for ordered drop cleanup
        """
        if type(double_transfers) is not bool:
            raise ValueError("double_transfers must be boolean")
        super().__init__(width=width)
        self.double_transfers = double_transfers
        if drop_repeats is not None and (type(drop_repeats) is not int or drop_repeats < 1):
            raise ValueError("drop_repeats must be None or a positive integer")
        self.drop_repeats = drop_repeats
        assert gauge <= 4, "gauge must be less than or equal to 4"
        self.gauge = gauge
        assert (not is_tubular) or width >= 4, \
            "width must be at least 4 stitches for tubular knitting"

        self.is_tubular = is_tubular
        self.side_slack = side_slack

    def xfer_pass(self, transfers):
        """Run a full ordered transfer sweep, optionally repeat before racking.

        Materialize generators so the second sweep uses the same needles.
        Ordinary xfer() and chain bind-off remain single.
        """
        transfers = tuple(transfers)
        for _ in range(2 if self.double_transfers else 1):
            for source, target in transfers:
                self.xfer(source, target)

    def drop_pass(self, locations):
        """Repeat complete physically ordered sweeps, independently of xfer_pass.

        None preserves existing explicit-drop order/count. When enabled, both
        beds are interleaved by physical needle number so each sweep is monotone.
        Low-level drop() itself always emits one instruction.
        """
        locations = tuple(locations)
        if self.drop_repeats is not None:
            locations = tuple(sorted(set(locations), key=lambda loc: (int(loc[1:]), loc[0])))
        for _ in range(self.drop_repeats or 1):
            for location in locations:
                self.drop(location)

    def drop_vacated(self, locations):
        """Optional cleanup after completed transfers; never drop live targets."""
        if self.drop_repeats is not None:
            self.drop_pass(locations)

    def _drop_decreased_edges(self, old_min, old_max):
        outgoing = list(range(old_min, self.min_n)) + list(range(self.max_n+1, old_max+1))
        if self.is_tubular:
            # Original needles and opposite-bed temporary needles in the
            # vacated logical slots should all be empty after the decrease.
            locations = [f'{bed}{self.gauge*n+offset}' for n in outgoing
                         for offset in (0, 1) for bed in ('f', 'b')]
        else:
            locations = [f'{bed}{n}' for n in outgoing for bed in ('f', 'b')]
        self.drop_vacated(locations)

    def drop_all(self, bed="f"):
        self.drop_pass(f'{bed}{n}' for n in range(self.min_n, self.max_n+1))

    def drop_all_both(self, margin=0):
        self.drop_pass(f'{bed}{n}' for bed in ('f', 'b')
                       for n in range(self.min_n-margin, self.max_n+margin+1))

    def __repr__(self):
        return f"ShapingHelper(range=[{self.min_n}, {self.max_n}], direction={self.direction}, is_tubular={self.is_tubular}, gauge={self.gauge}, side_slack={self.side_slack})"

    # ----------------------------------------------------------------
    # Needle addressing helpers (n-gauge)
    # ----------------------------------------------------------------

    def _loc(self, bed, n, gauge):
        """
        Translate logical needle index n to physical bed+needle string.
        For tubular (n-gauge): front -> f{gauge*n}, back -> b{gauge*n+1}.
        For flat: front/back -> {bed}{n}.
        Matches J-30.js: loc('f', n) = f(2*n), loc('b', n) = b(2*n+1).
        """
        if self.is_tubular:
            return f"f{self.gauge * n}" if bed == "f" else f"b{self.gauge * n + 1}"
            if gauge == 2:
                return f"f{2 * n}" if bed == "f" else f"b{2 * n + 1}"
            elif gauge == 3:
                return f"f{3 * n}" if bed == "f" else f"b{3 * n + 1}"
            elif gauge == 4:
                return f"f{4 * n}" if bed == "f" else f"b{4 * n + 2}"
        else:
            return f"{bed}{n}"

    # ----------------------------------------------------------------
    # Cast-on
    # ----------------------------------------------------------------

    def cast_on_tubular(self, carrier, settling_rows=4):
        """
        Alternating front/back cast-on for n-gauge tube.
        Translated from J-30.js closed cast-on.

        Tucks right-to-left on alternating front and back needles at rack -2,
        then knits left-to-right at rack 0 to close the bottom.

        Contributor: Xander Lord (@xlord@wesleyan.edu)
        """
        assert self.is_tubular, "cast_on_tubular requires tubular mode"

        self.inhook(carrier)

        # All front tucks right-to-left
        self.rack(-2)
        for n in range(self.max_n, self.min_n - 1, -1):
            self.tuck("-", self._loc("f", n, self.gauge), carrier)

        # All back tucks right-to-left
        for n in range(self.max_n, self.min_n - 1, -1):
            self.tuck("-", self._loc("b", n, self.gauge), carrier)

        self.releasehook(carrier)

        # Miss past the edge to position carrier
        self.miss("-", f"f{2 * self.min_n - 2}", carrier)

        # All front knits left-to-right to close
        self.rack(0)
        for n in range(self.min_n, self.max_n + 1):
            self.knit("+", self._loc("f", n, self.gauge), carrier)

        # All back knits left-to-right to close
        for n in range(self.min_n, self.max_n + 1):
            self.knit("+", self._loc("b", n, self.gauge), carrier)

        # Step 3: Settling rows as tubular
        self.direction[carrier] = "-"
        for _ in range(settling_rows):
            self.knit_tubular_row(carrier)

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
        assert self.gauge == 2, \
            "this cast-on assumes half-gauge"
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

    def cast_on_tubular_twisted_tuck(self, carrier, settling_rows=4):
        """
        Twisted tuck cast-on for n-gauge tube. Using the same twisted
        tuck as the increase method. (Not tested)

        Parameters:
            carrier:        the yarn carrier to use
            settling_rows:  tubular settling rows after cast-on
                            (default 4, forced even for consistency)
        """
        assert self.is_tubular, \
            "cast_on_tubular_twisted_tuck requires tubular mode"
        if settling_rows % 2 != 0:
            settling_rows += 1

        self.inhook(carrier)

        # Step 1: Cast on right-to-left on the front bed
        for n in range(self.max_n, self.min_n - 1, -1):
            needle = self._loc("f", n, self.gauge)
            self.miss("-", needle, carrier)
            self.tuck("+", needle, carrier)
            self.miss("-", needle, carrier)

        self.releasehook(carrier)

        # Step 2: Cast on left-to-right on the back bed
        for n in range(self.min_n, self.max_n + 1):
            needle = self._loc("b", n, self.gauge)
            self.miss("+", needle, carrier)
            self.tuck("-", needle, carrier)
            self.miss("+", needle, carrier)

        # Step 3: Settling rows as tubular
        self.direction[carrier] = "-"
        for _ in range(settling_rows):
            self.knit_tubular_row(carrier)

    def cast_on_tubular_knit(self, carrier, nknit = 5, settling_rows=4):
        """
        Cast on by knitting a few stitches for n-gauge tube.
        Translated from image-tj.js band(A, B)'s cast on.  (Tested)

        Parameters:
            carrier:        the yarn carrier to use
            nknit:          number of stitches to knit for cast-on
            settling_rows:  tubular settling rows after cast-on
                            (default 4, forced even for consistency)
        """
        assert self.is_tubular, "cast_on_tubular_knit requires tubular mode"
        if settling_rows % 2 != 0:
            settling_rows += 1

        self.inhook(carrier)

        # A few stitches on the front bed to the right of the piece
        max_n = self.max_n * self.gauge
        for n in range(max_n + nknit, max_n, -1):
            if n % 2 == 1:
                self.tuck("-", f"f{n}", carrier)
        for n in range(max_n + nknit, max_n, -1):
            if n % 2 == 0:
                self.tuck("+", f"f{n}", carrier)
        for n in range(max_n + nknit, max_n, -1):
            self.knit("-", f"f{n}", carrier)

        self.releasehook(carrier)

        # Settling rows as tubular
        self.direction[carrier] = "-"
        for _ in range(settling_rows):
            self.knit_tubular_row(carrier)

        # Drop the initial knit patch for casting on
        self.drop_pass(f"f{n}" for n in range(max_n + nknit, max_n, -1))

    def cast_on_tubular_alt_tuck(self, carrier, settling_rows=4):
        """
        Alternating-tuck cast-on for n-gauge tube.
        """
        assert self.is_tubular, "cast_on_tubular_alt_tuck requires tubular mode"
        self.inhook(carrier)
        for n in range(self.max_n, self.min_n - 1, -1):
            self.tuck("-", self._loc("f", n, self.gauge), carrier)
        for n in range(self.min_n, self.max_n + 1):
            self.tuck("+", self._loc("b", n, self.gauge), carrier)
        self.direction[carrier] = "-"
        for _ in range(settling_rows):
            self.knit_tubular_row(carrier)
        self.releasehook(carrier)

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

        Currently adding two tucks on both sides if the side_slack is on.
        """
        assert self.is_tubular, "knit_tubular_row requires tubular mode"

        min_needle, max_needle = None, None
        if self.direction[carrier] == "-":
            for n in range(self.max_n, self.min_n - 1, -1):
                self.knit("-", self._loc("f", n, self.gauge), carrier)
            if self.side_slack:
                min_needle = int(self._loc("f", n, self.gauge)[1:])
                self.drop(f"f{min_needle - 2}")
                self.tuck("-", f"f{min_needle - 2}", carrier)
                self.drop(f"b{min_needle - 1}")
                self.tuck("+", f"b{min_needle - 1}", carrier)
            for n in range(self.min_n, self.max_n + 1):
                self.knit("+", self._loc("b", n, self.gauge), carrier)
            if self.side_slack:
                max_needle = int(self._loc("b", n, self.gauge)[1:])
                self.drop(f"b{max_needle + 2}")
                self.tuck("+", f"b{max_needle + 2}", carrier)
                self.drop(f"f{max_needle + 1}")
                self.tuck("-", f"f{max_needle + 1}", carrier)
        else:
            for n in range(self.min_n, self.max_n + 1):
                self.knit("+", self._loc("f", n, self.gauge), carrier)
            if self.side_slack:
                max_needle = int(self._loc("f", n, self.gauge)[1:])
                self.drop(f"f{max_needle + 2}")
                self.tuck("+", f"f{max_needle + 2}", carrier)
                self.drop(f"b{max_needle + 1}")
                self.tuck("-", f"b{max_needle + 1}", carrier)
            for n in range(self.max_n, self.min_n - 1, -1):
                self.knit("-", self._loc("b", n, self.gauge), carrier)
            if self.side_slack:
                min_needle = int(self._loc("b", n, self.gauge)[1:])
                self.drop(f"b{min_needle - 2}")
                self.tuck("-", f"b{min_needle - 2}", carrier)
                self.drop(f"f{min_needle - 1}")
                self.tuck("+", f"f{min_needle - 1}", carrier)
    
    # def knit_partial_row(self, carrier, step, offset=0):
    #     '''
    #     Knit one row of tubular fabric on specific needles (NOT TESTED)
    #     Respects the carrier's current direction
    #     '''
    #     if self.direction[carrier] == "-":
    #         leftover = (self.max_n - self.min_n) % step
    #         for n in range(self.max_n- offset, self.min_n - 1, -step):
    #             self.knit("-", self._loc("f", n), carrier)
    #         for n in range(self.min_n + leftover, self.max_n + 1, step):
    #             self.knit("+", self._loc("b", n), carrier)
    #     else:
    #         for n in range(self.min_n+ offset, self.max_n + 1, step):
    #             self.knit("+", self._loc("f", n), carrier)
    #         for n in range(self.max_n - leftover, self.min_n - 1, -step):
    #             self.knit("-", self._loc("b", n), carrier)


    def knit_partial_row(self, carrier, step):
        '''
        Knit one row of tubular fabric on specific needles (NOT TESTED)
        Respects the carrier's current direction
        '''
        if self.direction[carrier] == "-":
            for n in range(self.max_n, self.min_n - 1, -step):
                self.knit("-", self._loc("f", n, self.gauge), carrier)
            if ((self.max_n - self.min_n) % step) != 0:
                self.knit("-", self._loc("f", self.min_n, self.gauge), carrier)
            for n in range(self.min_n, self.max_n + 1, step):
                self.knit("+", self._loc("b", n, self.gauge), carrier)
            if ((self.max_n - self.min_n) % step) != 0:
                self.knit("-", self._loc("b", self.max_n, self.gauge), carrier)
        else:
            for n in range(self.min_n, self.max_n + 1, step):
                self.knit("+", self._loc("f", n, self.gauge), carrier)
            if ((self.max_n - self.min_n) % step) != 0:
                self.knit("-", self._loc("f", self.max_n, self.gauge), carrier)
            for n in range(self.max_n, self.min_n - 1, -step):
                self.knit("-", self._loc("b", n, self.gauge), carrier)
            if ((self.max_n - self.min_n) % step) != 0:
                self.knit("-", self._loc("b", self.min_n, self.gauge), carrier)

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
            self.knit(d, self._loc(b, n, self.gauge), carrier)
            step()

        def tuck_and_turn():
            nonlocal n, b, d
            self.tuck(d, self._loc(b, n, self.gauge), carrier)
            d = "-" if d == "+" else "+"
            step()

        for turn in turns:
            while n != turn["n"] or b != turn["b"]:
                do_knit()
            tuck_and_turn()
        self.comment("before finishing")
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
                self.xfer(f"f{n * self.gauge}", f"b{n * self.gauge}")
            self.rack(self.gauge)
            for n in range(self.min_n, position):
                self.xfer(f"b{n * self.gauge + 1}", f"f{(n + 1) * self.gauge + 1}")
                self.xfer(f"b{n * self.gauge}", f"f{(n + 1) * self.gauge}")
            self.rack(0)
            for n in range(self.min_n, position):
                self.xfer(f"f{(n + 1) * self.gauge + 1}", f"b{(n + 1) * self.gauge + 1}")
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
                self.xfer(f"f{n * self.gauge}", f"b{n * self.gauge}")
            self.rack(-self.gauge)
            for n in range(self.max_n, position, -1):
                self.xfer(f"b{n * self.gauge}", f"f{(n - 1) * self.gauge}")
                self.xfer(f"b{n * self.gauge + 1}", f"f{(n - 1) * self.gauge + 1}")
            self.rack(0)
            for n in range(self.max_n, position, -1):
                self.xfer(f"f{(n - 1) * self.gauge + 1}", f"b{(n - 1) * self.gauge + 1}")
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
        old_min, old_max = self.min_n, self.max_n
        if lean == "left":
            self._do_decrease_left(position)
        else:
            self._do_decrease_right(position)
        self._drop_decreased_edges(old_min, old_max)

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

        old_min, old_max = self.min_n, self.max_n
        self._do_decrease_left(left_position)
        self._do_decrease_right(right_position)
        self._drop_decreased_edges(old_min, old_max)

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

        Input forms accepted:

          * A plain list of needle indices (or a single int), combined
            with the `lean` argument, applies the SAME lean to every
            increase:
                increase([3, 5], carrier=1, lean="right")

          * A list of (position, lean) pairs gives EACH increase its own
            lean, so increases in one row need not mirror:
                increase([(3, "right"), (10, "left")], carrier=1)

          * (Tubular only) a list of (bed, position, lean) triples places
            increases on the front and back beds INDEPENDENTLY, e.g. a new
            front stitch at 4 and a new back stitch at 9:
                increase([("f", 4, "right"), ("b", 9, "left")], carrier=1)
            The first two forms are symmetric shorthand: they apply the
            same increases to both beds (f{p} and b{p} together).

        For the int / pair forms the `lean` argument supplies the default
        lean; it is ignored once explicit leans are given.

        Balance requirement (tubular): the front and back beds must stay
        the same width, so the per-bed triples must contain the SAME number
        of left-lean and the SAME number of right-lean increases on each
        bed. Otherwise the single (min_n, max_n) range can no longer
        describe both beds and an assertion fires (see
        _increase_by_positions).

        lean="right":
          The new stitch is inserted to the LEFT of `position`; stitches
          at and above `position` shift rightward, so max_n grows.

        lean="left":
          The new stitch is inserted to the RIGHT of `position`; stitches
          at and below `position` shift leftward, so min_n shrinks.

        Parameters:
            positions: one of
                       - int (single position),
                       - list of ints (uniform `lean`),
                       - list of (int, "left"|"right") pairs, or
                       - list of ("f"|"b", int, "left"|"right") triples
                         (tubular, per-bed)
            carrier:   the carrier to use
            lean:      default lean for the int / list-of-ints forms
        """
        assert lean in ("left", "right"), f"lean must be 'left' or 'right', got '{lean}'"

        # Normalize every accepted form to front_pairs / back_pairs, each a
        # list of (position, lean). back_pairs=None means "same as front"
        # (the symmetric default; for flat the back list is unused).
        if isinstance(positions, int):
            front_pairs = [(positions, lean)]
            back_pairs = None
        else:
            positions = list(positions)
            assert len(positions) > 0, "positions must not be empty"
            first = positions[0]
            if isinstance(first, int):
                front_pairs = [(p, lean) for p in positions]
                back_pairs = None
            elif len(first) == 2:
                front_pairs = [(p, ln) for (p, ln) in positions]
                back_pairs = None
            else:
                # per-bed (bed, position, lean) triples
                assert self.is_tubular, (
                    "per-bed (f/b) increases are only meaningful for tubular "
                    "knitting; use (position, lean) pairs for flat fabric"
                )
                front_pairs = []
                back_pairs = []
                for bed, p, ln in positions:
                    assert bed in ("f", "b"), \
                        f"bed must be 'f' or 'b', got '{bed}'"
                    (front_pairs if bed == "f" else back_pairs).append((p, ln))

        self._increase_by_positions(front_pairs, carrier, back_pairs=back_pairs)

    def _compute_increase_layout(self, position_lean_pairs):
        """
        Compute the needle remapping for a set of per-position increases.

        Each (position, lean) pair inserts exactly one new stitch:
          - lean="right": the new stitch sits just LEFT of `position`,
            pushing `position` and everything above it one step right.
          - lean="left":  the new stitch sits just RIGHT of `position`,
            pushing `position` and everything below it one step left.

        Building an ordered token stream (right-lean inserts before their
        anchor, the old needle, then left-lean inserts after their anchor)
        and re-indexing left-to-right yields an order-preserving map that
        handles arbitrarily mixed leans in one pass.

        Returns:
            old_to_new: dict mapping each current logical needle to its
                        new logical needle index
            empty_set:  set of new logical needle indices that are the
                        freshly-created (empty) needles
            new_min:    new minimum logical needle index
            new_max:    new maximum logical needle index
        """
        right_inserts = {}   # anchor position -> count of right-lean inserts
        left_inserts = {}    # anchor position -> count of left-lean inserts
        num_left = 0
        num_right = 0
        for position, lean in position_lean_pairs:
            assert lean in ("left", "right"), \
                f"lean must be 'left' or 'right', got '{lean}'"
            self._validate_position(position)
            if lean == "right":
                right_inserts[position] = right_inserts.get(position, 0) + 1
                num_right += 1
            else:
                left_inserts[position] = left_inserts.get(position, 0) + 1
                num_left += 1

        # Each left-lean insert grows the min_n side; each right-lean
        # insert grows the max_n side (matches the single-lean behavior).
        new_min = self.min_n - num_left
        new_max = self.max_n + num_right

        # Ordered token stream over [min_n, max_n].
        # None marks a new (empty) needle.
        tokens = []
        for n in range(self.min_n, self.max_n + 1):
            for _ in range(right_inserts.get(n, 0)):
                tokens.append(None)   # right-lean insert sits left of n
            tokens.append(n)
            for _ in range(left_inserts.get(n, 0)):
                tokens.append(None)   # left-lean insert sits right of n

        old_to_new = {}
        empty_set = set()
        idx = new_min
        for tok in tokens:
            if tok is None:
                empty_set.add(idx)
            else:
                old_to_new[tok] = idx
            idx += 1

        return old_to_new, empty_set, new_min, new_max

    def _shift_groups(self, old_to_new):
        """
        Group current logical needles by how far they shift (new - old).

        Since each per-bed map is order-preserving, deltas may differ
        across needles (and even differ in sign for mixed leans) without
        any crossings. Returns {delta: [needles...]}.
        """
        by_delta = {}
        for n in range(self.min_n, self.max_n + 1):
            delta = old_to_new[n] - n
            by_delta.setdefault(delta, []).append(n)
        return by_delta

    def _warn_if_over_rack(self, *by_deltas, num_inc):
        """
        Warn (but do not block) if an increase needs more racking than the
        machine is assumed to handle. On an n-gauge tube each unit of
        logical shift costs two racking steps, so the cost is doubled.
        """
        max_shift = max(
            (abs(d) for by_delta in by_deltas for d in by_delta),
            default=0,
        )
        rack_needed = max_shift * (self.gauge if self.is_tubular else 1)
        if rack_needed > self.MAX_RACK:
            warnings.warn(
                f"increase needs racking ±{rack_needed}, which exceeds "
                f"MAX_RACK (±{self.MAX_RACK}) for "
                f"{'tubular' if self.is_tubular else 'flat'} knitting. "
                f"Knitout is still emitted, but the machine may not be able "
                f"to rack this far. Consider spreading these {num_inc} "
                f"increase(s) across more rows, or using positions that "
                f"don't stack {max_shift} shifts onto a single needle.",
                stacklevel=3,
            )

    def _increase_by_positions(self, front_pairs, carrier, back_pairs=None):
        """
        Unified increase for both flat and tubular fabric.

        (deprecated documentation pertaining gauge)
        This single helper replaces the old `_increase_flat` and
        `_increase_tubular`: the only real difference between them was
        full gauge (f{n}, rack by delta) versus half gauge (f{2n}/b{2n+1},
        rack by 2*delta, plus a second pass for the back-bed needles), so
        both are handled here by branching on `self.is_tubular`.

        The front and back beds are remapped INDEPENDENTLY (each from its
        own (position, lean) list), which is what lets a front increase and
        a back increase sit at different positions. For the standard
        symmetric increase, pass `back_pairs=None` and the back bed reuses
        the front's positions.

        Strategy (lace.js-style transfers):
          1. Clear the front bed by transferring every stitch to the back.
          2. Re-deliver each stitch to its new front position, grouped by
             how far it shifts (delta) to minimize rack changes.
          3. (Tubular only) repeat for the back-bed (odd) needles, staged
             through the front bed, using the back map.
          4. Knit a "-" front pass, doing a twisted tuck at each new
             (empty) front needle instead of a knit. For tubular, also knit
             a "+" back pass with twisted tucks at the empty back needles.

        For flat:    direction flips "-" -> "+".
        For tubular:  direction stays "-".

        Parameters:
            front_pairs: list of (position, lean) for the front bed
            carrier:     the carrier to use
            back_pairs:  list of (position, lean) for the back bed, or None
                         to mirror front_pairs (symmetric). Tubular only;
                         ignored for flat fabric.
        """
        assert len(front_pairs) > 0, "front_pairs must not be empty"
        assert self.direction[carrier] == "-", (
            f"increase requires carrier direction '-', "
            f"got '{self.direction[carrier]}'"
        )

        # Front-bed remap.
        f_to_new, f_empty, new_min, new_max = \
            self._compute_increase_layout(front_pairs)
        f_by_delta = self._shift_groups(f_to_new)

        if self.is_tubular:
            # Back-bed remap (defaults to mirroring the front).
            if back_pairs is None:
                back_pairs = front_pairs
            assert len(back_pairs) > 0, "back_pairs must not be empty"
            b_to_new, b_empty, b_min, b_max = \
                self._compute_increase_layout(back_pairs)

            # Balance check: both beds must end on the SAME range so a single
            # (min_n, max_n) still describes the tube. This holds exactly when
            # each bed has the same number of left-lean and right-lean inserts.
            assert (new_min, new_max) == (b_min, b_max), (
                "front and back increases are unbalanced: front grows the "
                f"range to [{new_min}, {new_max}] but back to [{b_min}, "
                f"{b_max}]. A tube needs equal numbers of left-lean and "
                "right-lean increases on each bed so both stay the same "
                "width."
            )
            b_by_delta = self._shift_groups(b_to_new)

            self._warn_if_over_rack(f_by_delta, b_by_delta,
                                    num_inc=len(front_pairs))

            # -- Move front (even) needles: f{2n} -> b{2n} -> f{2*new} --
            self.xfer_pass([(f"f{n * self.gauge}", f"b{n * self.gauge}") for n in range(self.min_n, self.max_n + 1)])
            # delta==0 (unchanged) first, then by increasing shift magnitude
            for delta in sorted(f_by_delta, key=abs):
                if delta == 0:
                    self.xfer_pass([(f"b{n * self.gauge}", f"f{n * self.gauge}") for n in f_by_delta[0]])
                else:
                    # back->front xfer: rack = front_idx - back_idx = 2*delta
                    self.rack(delta * self.gauge)
                    self.xfer_pass([(f"b{n * self.gauge}", f"f{(n + delta) * self.gauge}") for n in f_by_delta[delta]])
                    self.rack(0)

            # -- Move back (odd) needles: stage on front, then to b{2*new+1} --
            self.xfer_pass([(f"b{n * self.gauge + 1}", f"f{n * self.gauge + 1}") for n in range(self.min_n, self.max_n + 1)])
            for delta in sorted(b_by_delta, key=abs):
                if delta == 0:
                    self.xfer_pass([(f"f{n * self.gauge + 1}", f"b{n * self.gauge + 1}") for n in b_by_delta[0]])
                else:
                    # front->back xfer: rack = front_idx - back_idx = -2*delta
                    self.rack(-(delta * self.gauge))
                    self.xfer_pass([(f"f{n * self.gauge + 1}", f"b{(n + delta) * self.gauge + 1}") for n in b_by_delta[delta]])
                    self.rack(0)
        else:
            self._warn_if_over_rack(f_by_delta, num_inc=len(front_pairs))

            # -- Move front needles: f{n} -> b{n} -> f{new} --
            self.xfer_pass([(f"f{n}", f"b{n}") for n in range(self.min_n, self.max_n + 1)])
            for delta in sorted(f_by_delta, key=abs):
                if delta == 0:
                    self.xfer_pass([(f"b{n}", f"f{n}") for n in f_by_delta[0]])
                else:
                    # back->front xfer: rack = front_idx - back_idx = delta
                    self.rack(delta)
                    self.xfer_pass([(f"b{n}", f"f{n + delta}") for n in f_by_delta[delta]])
                    self.rack(0)

        self.min_n = new_min
        self.max_n = new_max

        # -- Front "-" pass with twisted tucks at empty front positions --
        for n in range(self.max_n, self.min_n - 1, -1):
            loc = self._loc("f", n, self.gauge)
            if n in f_empty:
                self.miss("-", loc, carrier)
                self.tuck("+", loc, carrier)
                self.miss("-", loc, carrier)
            else:
                self.knit("-", loc, carrier)

        if self.is_tubular:
            # -- Back "+" pass with twisted tucks at empty back positions --
            for n in range(self.min_n, self.max_n + 1):
                loc = self._loc("b", n, self.gauge)
                if n in b_empty:
                    self.miss("+", loc, carrier)
                    self.tuck("-", loc, carrier)
                    self.miss("+", loc, carrier)
                else:
                    self.knit("+", loc, carrier)
            # Direction stays "-" for tubular
        else:
            self._flip_direction(carrier)  # "-" -> "+"

    # ----------------------------------------------------------------
    # Bind-off
    # ----------------------------------------------------------------

    def bind_off_tubular(self, carrier, has_tag = True):
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
            self.knit("-", self._loc("f", n, self.gauge), carrier)
            self.miss("-", self._loc("f", n - 1, self.gauge), carrier)
            self.xfer(self._loc("f", n, self.gauge), f"b{n * self.gauge}")
            self.rack(-self.gauge)
            self.xfer(f"b{n * self.gauge}", self._loc("f", n - 1, self.gauge))
            self.rack(0)

        # Leftmost front stitch: chain onto back bed
        self.knit("-", self._loc("f", self.min_n, self.gauge), carrier)
        self.tuck("-", self._loc("f", self.min_n - 1, self.gauge), carrier)
        self.rack(-1)
        self.xfer(self._loc("f", self.min_n, self.gauge), self._loc("b", self.min_n, self.gauge))
        self.rack(0)

        # Bind-off (back): left-to-right
        for n in range(self.min_n, self.max_n):
            self.knit("+", self._loc("b", n, self.gauge), carrier)
            self.miss("+", self._loc("b", n + 1, self.gauge), carrier)
            self.xfer(self._loc("b", n, self.gauge), f"f{n * self.gauge + 1}")
            self.rack(-self.gauge)
            self.xfer(f"f{n * self.gauge + 1}", self._loc("b", n + 1, self.gauge))
            self.rack(0)
        self._finish_tubular_bind_off(carrier, has_tag)

    def _finish_tubular_bind_off(self, carrier, has_tag=True):
        """Shared tag and carrier removal after the chain reaches back max_n."""
        if has_tag:
            # Tag (on back)
            loc_max_b = self._loc("b", self.max_n, self.gauge)
            self.knit("+", loc_max_b, carrier)
            self.knit("-", loc_max_b, carrier)
            self.knit("+", loc_max_b, carrier)
            self.knit("-", loc_max_b, carrier)
            self.tuck("-", self._loc("b", self.max_n - 1, self.gauge), carrier)
            self.tuck("+", self._loc("b", self.max_n - 2, self.gauge), carrier)
            self.knit("+", self._loc("b", self.max_n - 1, self.gauge), carrier)
            self.knit("+", loc_max_b, carrier)
            for _ in range(4):
                for n in range(self.max_n, self.max_n - 3, -1):
                    self.knit("-", self._loc("b", n, self.gauge), carrier)
                for n in range(self.max_n - 2, self.max_n + 1):
                    self.knit("+", self._loc("b", n, self.gauge), carrier)

        self.outhook(carrier)

    def bind_off_flap(self, carrier, *, n=None, flap_width=None, flap_rows=None,
                      stitch_gauge=None, row_gauge=None, has_tag=True):
        """Finish a tube with a front flap transferred onto the back bed.

        Width is inclusive; rows are even individual flat passes. Omitted
        dimensions are calculated using fabric gauges measured at this spacing.
        Returns the resolved layout and fit estimates.
        """
        from ..flap_bind_off import FlapBindOffConfig, bind_off_flap
        return bind_off_flap(self, carrier, FlapBindOffConfig(
            n=n, flap_width=flap_width, flap_rows=flap_rows,
            stitch_gauge=stitch_gauge, row_gauge=row_gauge, has_tag=has_tag))

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
        but adapted for n-gauge tubular knitting.

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
                    loc = self._loc("f", n, self.gauge)
                    if n in front_positions:
                        self.knit("-", loc, car)
                    else:
                        self.miss("-", loc, car)
                # Back pass: left-to-right
                for n in range(self.min_n, self.max_n + 1):
                    loc = self._loc("b", n, self.gauge)
                    if n in back_positions:
                        self.knit("+", loc, car)
                    else:
                        self.miss("+", loc, car)
            else:
                # Front pass: left-to-right
                for n in range(self.min_n, self.max_n + 1):
                    loc = self._loc("f", n, self.gauge)
                    if n in front_positions:
                        self.knit("+", loc, car)
                    else:
                        self.miss("+", loc, car)
                # Back pass: right-to-left
                for n in range(self.max_n, self.min_n - 1, -1):
                    loc = self._loc("b", n, self.gauge)
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
                loc = self._loc("f", n, self.gauge)
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
                loc = self._loc("b", n, self.gauge)
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
                loc = self._loc("f", n, self.gauge)
                if pattern_row[idx] == carrier_a:
                    self.instructions.append(
                        f"knit + {loc} {carrier_a} {carrier_b}")
                else:
                    self.instructions.append(
                        f"knit + {loc} {carrier_b} {carrier_a}")
            # Back pass: right-to-left (reversed carrier order for outside)
            for n in range(self.max_n, self.min_n - 1, -1):
                idx = n - self.min_n
                loc = self._loc("b", n, self.gauge)
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
        assert self.gauge == 2, "knit_tubular_rib_row requires half-gauge"
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
    # Teardown
    # ----------------------------------------------------------------

    def drop_all_tubular(self, carrier):
        """
        Quick teardown for tubular fabric: outhook the carrier, then
        drop every loop on both beds at the n-gauge positions.
        Useful for fast iteration when you don't need a proper bind-off.
        """
        assert self.is_tubular, "drop_all_tubular requires tubular mode"
        self.outhook(carrier)
        locations = []
        if self.side_slack:
            locations.extend((f'f{self.gauge*self.min_n-2}', f'b{self.gauge*self.min_n-2}',
                              f'f{self.gauge*self.min_n-1}', f'b{self.gauge*self.min_n-1}'))
        locations.extend(location for n in range(self.min_n, self.max_n+1)
                         for location in (self._loc('f', n, self.gauge), self._loc('b', n, self.gauge)))
        if self.side_slack:
            locations.extend((f'f{self.gauge*self.max_n+1}', f'b{self.gauge*self.max_n+2}',
                              f'f{self.gauge*self.max_n+2}', f'b{self.gauge*self.max_n+3}'))
        self.drop_pass(locations)
