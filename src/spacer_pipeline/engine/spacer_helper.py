"""
COMP116 Final Project / Research - SpacerHelper (half gauge)

Weft-knit spacer fabric construction, following:

    Albaugh, McCann, Yao, Hudson. "Engineering Multifunctional Spacer
    Fabrics Through Machine Knitting." CHI 2021.
    https://doi.org/10.1145/3411764.3445564

A spacer fabric consists of two knit face layers connected by a
monofilament filler yarn tucked in a shallow zig-zag between the beds.
This module produces the *open* ("cut open generalized cylinder")
variant: the two faces are knit as separate flat sheets on the front
and back beds, connected only by the shared cast-on region at the
bottom and by the filler yarn -- so the finished sheet can be wrapped
around a robot arm section rather than knit as a closed tube.

Layout: HALF GAUGE, 1-BASED (front face -> f{2n-1}, back face ->
b{2n}), so logical stitch 1 sits on physical needle 1 and the overall
needle range is [1 .. 2*width]. NOTE: this overrides the inherited
ShapingHelper/J-30 convention (f{2n}, b{2n+1}, which starts the range
at physical needle 2); all spacer code goes through the overridden
_loc()/_phys() helpers and SpacerHelper owns its own cast-on and
decrease transfers, so nothing here depends on the old physical
numbering. Half gauge promotes the elastic draw-in that produces
loft, and leaves empty opposite needles for transfer-based shaping.

Carriers and PLATING: each of front_carrier / back_carrier /
filler_carrier may be a single carrier number OR a tuple of carrier
numbers knit together as a carrier set (plating). Example:

    SpacerHelper(width=100, front_carrier=3,
                 back_carrier=(7, 10),   # conductive 7 plated with
                 filler_carrier=4)       # elastic 10

Every operation of that face then lists the whole set (e.g.
"knit - f8 7 10"), and the set is inhooked/released/outhooked
together. Plating order matters: on the front bed the FIRST carrier
in the tuple shows on the fabric's public side. This is how the paper
combines a non-elastic (e.g. conductive) face yarn with its hair-thin
latex elastic. The front and back sets must not share carriers.

Yarn plan:
  * Face yarns: any knittable yarn plated with elastic (without
    elastic there is no draw-in and the spacer stays flat). For a
    conductive shielding face, plate a conductive yarn with the
    elastic on that face's carrier set.
  * Filler: semi-stiff nylon monofilament. Nylon mono fishing line
    is exactly what the paper used (KastKing / Hi-Seas "Grand Slam
    Mono", 6 lb test, 0.22-0.25 mm diameter).

Waste regions: the cast-on and finish both include generous waste
(>= 5 rows at each stage) intended to be sewn through (e.g. zipper
attachment) or unraveled after seaming; edges are NOT self-secured.

Geometric (programmable) parameters from the paper, and where they
live in this API:

    tuck spacing        -> `tuck_spacing`   (logical stitches between
                           successive filler tucks; paper: <6 and >1
                           for clean formation; default 5)
    tuck pattern offset -> `tuck_offset`    (needle shift of the tuck
                           grid between successive filler passes)
    filler row density  -> `filler_pass_pairs` vs `face_row_pairs`
                           (default 5/1 for a dense, load-bearing
                           cushion; the paper's default fabric was
                           2/1)
    face knitting order -> `face_order` ("front_first", "back_first",
                           "alternate"). The face knit first after a
                           set of filler rows shears downward;
                           "alternate" minimizes shear bias.

Additional mode: EYELETS. enable_eyelets() skips (misses) bands of
needles during face rows on a regular grid -- the held loops stretch
over the skipped row and open small holes. Defaults assume the
measured gauge of 13 rows and 13 wales per inch (~5 rows and ~5
stitches per cm): one skipped row every 5 face rows, eyelets 3
stitches wide with 5 solid stitches between them, on both faces or
either one.

Shaping caveat from the paper (sec. 8): "transferring monofilament
tucks was prone to errors, making increase/decrease shaping
difficult." Therefore knit_spacer_block() applies edge decreases
AFTER the face rows (when the filler tucks of the previous block
have been knit through and needles hold only face loops) and edge
increases BEFORE the face rows (so the new needles are anchored by
direction-consistent tucks before any filler pass can reach them).

Hierarchy:
    KnitoutWriter -> KnittingHelper -> ShapingHelper -> SpacerHelper
"""

import math

from .shaping_helper import ShapingHelper


class SpacerHelper(ShapingHelper):
    """
    Spacer fabric helper for open (sheet) double-bed spacer fabric at
    half gauge, with carrier-set (plating) support.

    The two faces are knit with independent carrier sets; each face's
    carriers always stay on their own bed, so the side edges remain
    open.

    Attributes added on top of ShapingHelper:
        front_carrier, back_carrier, filler_carrier (as passed in;
            int or tuple)
        tuck_spacing, tuck_offset, face_order,
        face_row_pairs, filler_pass_pairs (defaults; overridable
            per call), drop_repeats
    """

    def __init__(self, width, front_carrier=3, back_carrier=4,
                 filler_carrier=5, tuck_spacing=5, tuck_offset=1,
                 face_row_pairs=1, filler_pass_pairs=5,
                 face_order="alternate", drop_repeats=2):
        """
        Parameters:
            width:             number of logical stitches (>= 4)
            front_carrier:     carrier (int) or plating carrier set
                               (tuple) for the front face
            back_carrier:      carrier or plating set for the back
                               face, e.g. (7, 10) = yarn on 7 plated
                               with elastic on 10. Must not share
                               carriers with the front set.
            filler_carrier:    carrier (or set) for the filler
                               monofilament; must not overlap the
                               face sets
            tuck_spacing:      default logical stitches between filler
                               tucks (1..5; paper: 2..5 for clean
                               loft). Default 5 = maximum loft.
            tuck_offset:       default tuck-grid shift per filler pass
            face_row_pairs:    default face row pairs per block
            filler_pass_pairs: default filler pass pairs per block
                               (default 5 -> 5:1 density)
            face_order:        default face knitting order per block:
                               "front_first", "back_first", or
                               "alternate"
            drop_repeats:      redundant drop commands for elastic/plated
                               loops after shaping (default 2)
        """
        super().__init__(width=width, is_tubular=True)

        self.front_carrier = front_carrier
        self.back_carrier = back_carrier
        self.filler_carrier = filler_carrier
        self._front_cs = self._carrier_set(front_carrier)
        self._back_cs = self._carrier_set(back_carrier)
        self._filler_cs = self._carrier_set(filler_carrier)
        for cs in (self._front_cs, self._back_cs, self._filler_cs):
            for c in cs:
                assert c in self.carriers, f"unknown carrier {c}"
        assert not set(self._filler_cs) & (set(self._front_cs)
                                           | set(self._back_cs)), \
            "filler carrier(s) must be distinct from the face carriers"
        if self._front_cs != self._back_cs:
            assert not set(self._front_cs) & set(self._back_cs), (
                "front and back carrier sets must be identical or "
                "fully disjoint (a shared member would break "
                "direction tracking)"
            )

        self._validate_tuck_spacing(tuck_spacing)
        assert face_row_pairs >= 1 and filler_pass_pairs >= 0
        assert drop_repeats >= 1
        assert face_order in ("front_first", "back_first", "alternate")

        self.tuck_spacing = tuck_spacing
        self.tuck_offset = tuck_offset
        self.face_row_pairs = face_row_pairs
        self.filler_pass_pairs = filler_pass_pairs
        self.face_order = face_order
        self.drop_repeats = drop_repeats

        # Filler tucks that have not subsequently been knitted through.
        # Store their instruction positions so an imminent shape drop can
        # turn a now-useless tuck into a miss instead of creating a loose
        # monofilament loop immediately before releasing the needle.
        self._unresolved_filler_tucks = {}

        # Count of filler passes emitted so far (drives the tuck
        # pattern offset and front/back tuck parity between passes).
        self._filler_pass_count = 0
        # Toggles which face goes first when face_order == "alternate".
        self._alternate_front_first = True
        # Edge needles added by increase_edge() that do not hold a loop
        # yet; the next face pass on that bed anchors them with a
        # directional tuck instead of a knit.
        self._pending_new_needles = {"f": set(), "b": set()}
        # Face rows knit so far on each bed (drives the eyelet grid).
        self._face_rows = {"f": 0, "b": 0}
        # Eyelet mode configuration (None = off).
        self._eyelet_cfg = None
        # Physical front-bed needles holding stitches on their way out
        # of the fabric at a step change: they keep being knit by the
        # front face rows for a few rows, then drop. See step_width().
        self._cast_off_needles = set()
        self._cast_off_rows_left = 0
        # Pure abrupt expansions can merge their cast-on into the previous
        # face yarn path instead of emitting separate full-width miss passes.
        # The next spacer block consumes and clears this descriptor.
        self._prepared_step_expansion = None
        # A filler carrier parked beyond a newly expanded edge needs a real
        # yarn anchor, not a miss.  Keep track of that temporary tuck so it
        # can be dropped as soon as the next filler pass has anchored the
        # yarn inside the fabric.
        self._temporary_filler_park_tucks = set()
        # Last physical needle visited by each carrier. Direction tells us
        # which way it should travel next, but shaping transfers can move the
        # active edge without moving the carrier itself. Remembering the last
        # operation prevents transition parking from accidentally stepping
        # inward past a carrier that remains on a just-vacated edge needle.
        self._carrier_positions = {}

    @staticmethod
    def _validate_tuck_spacing(spacing):
        assert 1 <= spacing <= 5, (
            f"tuck_spacing must be in 1..5 logical stitches (got "
            f"{spacing}); the paper reports tucks must be >1 and <6 "
            "stitches apart to form cleanly on a 15g machine "
            "(spacing 1 = dense, minimal loft)"
        )

    # ----------------------------------------------------------------
    # Needle addressing (1-based half gauge)
    #
    #     front face -> f{2n-1}  (odd),  back face -> b{2n}  (even)
    #
    # so logical stitch 1 sits on physical needle 1 and the overall
    # range is [1 .. 2*width]. This overrides the inherited
    # ShapingHelper/J-30 convention (f{2n}, b{2n+1}, range starting at
    # needle 2), so SpacerHelper owns its own cast-on and decrease
    # transfers.
    #
    # All spacer code addresses needles ONLY through _loc()/_phys()
    # and the _phys_min()/_phys_max() span helpers -- never by
    # assuming which bed owns an extreme.
    # ----------------------------------------------------------------

    def _loc(self, bed, n):
        """Logical needle n -> physical bed+needle string (1-based)."""
        return f"f{2 * n - 1}" if bed == "f" else f"b{2 * n}"

    def _phys(self, bed, n):
        """Logical needle n -> physical needle index (int)."""
        return 2 * n - 1 if bed == "f" else 2 * n

    def _phys_min(self):
        """Leftmost physical needle in use (either bed)."""
        return min(self._phys("f", self.min_n), self._phys("b", self.min_n))

    def _phys_max(self):
        """Rightmost physical needle in use (either bed)."""
        return max(self._phys("f", self.max_n), self._phys("b", self.max_n))

    # ----------------------------------------------------------------
    # Carrier-set (plating) primitives
    #
    # Knitout operations take carrier SETS: "knit - f8 7 10" knits
    # both carriers into the stitch (plating; first listed shows on
    # the public side of front-bed fabric). The KnitoutWriter methods
    # accept a single carrier, so these wrappers emit multi-carrier
    # instructions directly and keep active_carriers / direction in
    # sync for every member of the set.
    # ----------------------------------------------------------------

    @staticmethod
    def _carrier_set(carrier):
        """Normalize an int or tuple/list of ints to a tuple."""
        if isinstance(carrier, (tuple, list)):
            assert len(carrier) >= 1, "carrier set must not be empty"
            assert len(set(carrier)) == len(carrier), \
                f"duplicate carriers in set {carrier}"
            return tuple(carrier)
        return (carrier,)

    def _face_cs(self, bed):
        return self._front_cs if bed == "f" else self._back_cs

    def _cs_str(self, cs):
        return " ".join(str(c) for c in cs)

    def _cs_dir(self, cs):
        return self.direction[cs[0]]

    def _cs_flip(self, cs):
        for c in cs:
            self._flip_direction(c)

    def _cs_set_dir(self, cs, d):
        for c in cs:
            self.direction[c] = d

    def _cs_op(self, op, d, loc, cs):
        self._validate_direction(d)
        for c in cs:
            self._validate_active_carrier(c)
        instruction_index = len(self.instructions)
        self.instructions.append(f"{op} {d} {loc} {self._cs_str(cs)}")
        physical_needle = int(loc[1:])
        for c in cs:
            self._carrier_positions[c] = physical_needle
        if op == "knit":
            self._unresolved_filler_tucks.pop(loc, None)
        elif op == "tuck" and tuple(cs) == self._filler_cs:
            self._unresolved_filler_tucks.setdefault(loc, []).append(
                instruction_index
            )

    def knit_cs(self, d, loc, cs):
        self._cs_op("knit", d, loc, cs)

    def tuck_cs(self, d, loc, cs):
        self._cs_op("tuck", d, loc, cs)

    def miss_cs(self, d, loc, cs):
        self._cs_op("miss", d, loc, cs)

    # Carrier LIFECYCLE is always one carrier at a time, even for a
    # plating set: the yarn inserting hook holds a single yarn, so
    # "inhook 7 10" / "outhook 7 10" are not valid operations. Only
    # the knit/tuck/miss operations take the whole set.

    def inhook_cs(self, cs):
        """Inhook each member of the set on its own line."""
        for c in cs:
            self.inhook(c)

    def releasehook_cs(self, cs):
        """Releasehook each member of the set on its own line."""
        for c in cs:
            self.releasehook(c)

    def outhook_cs(self, cs):
        """Outhook each member of the set on its own line."""
        for c in cs:
            self.outhook(c)

    # ----------------------------------------------------------------
    # Eyelet mode
    # ----------------------------------------------------------------

    def enable_eyelets(self, faces="both", eyelet_width=3, eyelet_gap=5,
                       pitch_rows=None, rows_per_inch=13.0,
                       eyelet_rows=1, phase=0):
        """
        Turn on the eyelet grid for subsequent face rows.

        Every `pitch_rows` face rows (per face), one row skips
        (misses) the needles inside each eyelet column instead of
        knitting them. The held loop stretches over the skipped row,
        opening a small hole. Eyelet columns are `eyelet_width`
        logical stitches wide, separated by `eyelet_gap` solid
        stitches, and are anchored to absolute needle numbers so they
        stay vertically aligned (a grid) even while the sheet is
        shaped. The 2 outermost stitches at each edge always knit, to
        keep the selvedges stable.

        Parameters:
            faces:         "front", "back", or "both" ("f"/"b" ok)
            eyelet_width:  stitches skipped per eyelet (default 3)
            eyelet_gap:    solid stitches between eyelets (default 5;
                           3+5 = 8 stitches ~ 1.5 cm at 13 wales/inch
                           -- tune to taste)
            pitch_rows:    face rows between eyelet rows, inclusive of
                           the eyelet row. Default: computed from
                           rows_per_inch as ~1 cm (13 rpi -> 5 rows).
            rows_per_inch: vertical row gauge used when pitch_rows is
                           None (default 13)
            eyelet_rows:   consecutive rows skipped per period
                           (default 1)
            phase:         horizontal shift of the eyelet grid in
                           stitches (for tuning placement)
        """
        faces_map = {"front": ("f",), "f": ("f",),
                     "back": ("b",), "b": ("b",),
                     "both": ("f", "b")}
        assert faces in faces_map, 'faces must be "front", "back", or "both"'
        assert eyelet_width >= 1 and eyelet_gap >= 1
        if pitch_rows is None:
            pitch_rows = max(2, round(rows_per_inch / 2.54))  # ~1 cm
        assert 1 <= eyelet_rows < pitch_rows, \
            "eyelet_rows must be smaller than pitch_rows"

        self._eyelet_cfg = {
            "beds": faces_map[faces],
            "width": eyelet_width,
            "gap": eyelet_gap,
            "pitch_rows": pitch_rows,
            "eyelet_rows": eyelet_rows,
            "phase": phase,
        }
        self.comment(f"eyelets ON: faces={faces}, {eyelet_width} wide / "
                     f"{eyelet_gap} gap, every {pitch_rows} rows")

    def disable_eyelets(self):
        """Turn off the eyelet grid (solid fabric from here on)."""
        self._eyelet_cfg = None
        self.comment("eyelets OFF")

    def _eyelet_columns(self, bed, row_index):
        """
        Logical needles to skip on this face row (empty if none).
        The eyelet row is the LAST `eyelet_rows` rows of each
        `pitch_rows` period, so the first eyelet appears a full period
        above where counting started.
        """
        cfg = self._eyelet_cfg
        if cfg is None or bed not in cfg["beds"]:
            return frozenset()
        pr, er = cfg["pitch_rows"], cfg["eyelet_rows"]
        if row_index % pr < pr - er:
            return frozenset()
        period = cfg["width"] + cfg["gap"]
        cols = set()
        # Keep 2 solid stitches at each selvedge
        for n in range(self.min_n + 2, self.max_n - 1):
            if (n - cfg["phase"]) % period < cfg["width"]:
                cols.add(n)
        return cols

    # ----------------------------------------------------------------
    # Cast-on / carrier setup
    # ----------------------------------------------------------------

    def _park_right(self, cs, offset=1):
        """
        Park a carrier set just past the RIGHT edge and set its
        direction to "-".

        Needed after any carrier introduction that happens on the
        front bed: those passes leave the carrier on the front's
        rightmost needle f{2n-1}, which is one needle LEFT of the
        back face's rightmost needle b{2n}. A following "-" pass that
        starts on the back bed would then have to travel right first,
        and the compiler splits that stitch into a carriage pass of
        its own. Parking past the edge removes the backtrack.

        `offset` staggers parking positions so carriers don't all
        claim the same spot.
        """
        self.miss_cs("+", f"f{self._phys_max() + offset}", cs)
        self._cs_set_dir(cs, "-")

    def _park_outside_span(self, cs, phys_min, phys_max, *, offset=1,
                           anchor=False):
        """Park outside the carrier's current side of a transition span.

        ``_cs_dir(cs)`` is the direction of the carrier set's next knitting
        pass, so ``-`` means it is currently on the right and ``+`` means it
        is currently on the left.  Park farther outward from that side;
        never infer the side from where dropped or newly added needles happen
        to be, because an asymmetric width change can put them on the opposite
        edge.

        Face carriers use a miss because their yarn is already secured in the
        old fabric.  Filler parking uses a temporary tuck so the monofilament
        is genuinely anchored before it reaches newly added needles.
        """
        assert phys_min <= phys_max
        assert offset >= 1
        d = self._cs_dir(cs)
        known_positions = [
            self._carrier_positions[c]
            for c in cs
            if c in self._carrier_positions
        ]
        if d == "-":
            park_direction = "+"
            target = phys_max + offset
            if known_positions:
                target = max(target, max(known_positions) + 1)
            location = f"f{target}"
            side = "right"
        else:
            park_direction = "-"
            target = phys_min - offset
            if known_positions:
                target = min(target, min(known_positions) - 1)
            location = f"f{target}"
            side = "left"
        if anchor:
            self.tuck_cs(park_direction, location, cs)
        else:
            self.miss_cs(park_direction, location, cs)
        return location, side

    def _secure_filler_park_for_expansion(self, phys_min, phys_max,
                                          offset=3):
        """Anchor filler outside its current side of the transition span."""
        self._release_temporary_filler_park_tucks()
        d = self._cs_dir(self._filler_cs)
        edge = "right" if d == "-" else "left"
        self.comment(
            f"secure filler beyond transition {edge} edge with temporary tuck"
        )
        loc, _ = self._park_outside_span(
            self._filler_cs,
            phys_min,
            phys_max,
            offset=offset,
            anchor=True,
        )
        self._temporary_filler_park_tucks.add(loc)
        self._cs_set_dir(self._filler_cs, d)

    def _release_temporary_filler_park_tucks(self):
        """Drop temporary filler anchors after the yarn is secured inside."""
        if not self._temporary_filler_park_tucks:
            return
        self.comment("drop temporary filler parking tuck")
        self._drop_locations_repeatedly(
            sorted(self._temporary_filler_park_tucks),
            prune_unresolved_filler=False,
        )
        self._temporary_filler_park_tucks.clear()

    def cast_on_spacer(self, waste_rows=6):
        """
        Cast on the spacer sheet with generous waste for later sewing
        (e.g. zipper attachment). Sequence:

          1. Alternating-tuck cast-on across ALL physical front-bed
             needles with the FIRST front carrier alone, one waste row,
             releasehook. Every carrier is inhooked SEPARATELY with
             its own waste row -- plated inhooks (two yarns in the
             inserting hook at once) and hookless first rows are
             unreliable. Each additional front-set member then gets
             its own inhook + one full-gauge waste row + releasehook,
             followed by `waste_rows` rows of full-gauge waste with
             the complete (plated) front set, and the transfer of
             back-face positions to the back bed.
          2. Back set members are each introduced ON THE FRONT BED
             (inhook + one row on the front face needles + releasehook;
             back-bed introductions often fail to catch), then
             `waste_rows` rows of per-face waste: front pairs with the
             front set, back pairs with the back set.
          3. Filler members are introduced the same way but with a
             KNIT row pair on the front face needles -- a firm anchor,
             so the loose monofilament start doesn't get caught by the
             other yarns.

        After this call all carrier sets are active and the sheet is
        ready for knit_spacer_block() / knit_spacer_trapezoid().

        Parameters:
            waste_rows: rows of full-set waste per stage (>= 5; forced
                        even, default 6; carrier-introduction rows are
                        in addition to these)
        """
        assert waste_rows >= 5, "need at least 5 waste rows"
        if waste_rows % 2 == 1:
            waste_rows += 1

        fcs = self._front_cs
        # first = fcs[0]

        first = self.filler_carrier

        # --- Stage 1: all-needle cast-on + waste + transfer ---
        #
        # This is ShapingHelper.cast_on_all_needle_transition, step for
        # step, with a SINGLE carrier -- plating members and every
        # other yarn join afterward in stage 2. The only change is
        # addressing: phys_min/phys_max and the transfer targets come
        # from _phys()/_loc(), so it follows this class's 1-based
        # half-gauge layout instead of the J-30 one.
        #
        # With phys_max even, the parity below puts the "-" tucks on
        # the even needles (2n, transferred to the back bed) and the
        # "+" tucks on the odd needles (2n+1, staying on the front).
        self.comment("=== spacer cast-on stage 1: all-needle cast-on, "
                     f"{waste_rows} waste rows, transfer ===")

        phys_min = self._phys_min()   # leftmost needle  (back, odd)
        phys_max = self._phys_max()   # rightmost needle (front, even)

        # Which physical needles end up on which bed after the
        # transfer. The "-" pass tucks the BACK positions (they get
        # transferred away) and the "+" pass tucks the FRONT ones, so
        # the freshest loops are the ones that stay on the front bed
        # and keep knitting.
        back_positions = {self._phys("b", n)
                          for n in range(self.min_n, self.max_n + 1)}

        self.inhook(first)

        # Alternating-tuck cast-on (full gauge, front bed)
        for s in range(phys_max, phys_min - 1, -1):
            if s in back_positions:
                self.tuck("-", f"f{s}", first)
        for s in range(phys_min, phys_max + 1):
            if s not in back_positions:
                self.tuck("+", f"f{s}", first)

        self.releasehook(first)

        # Settling / waste rows (full gauge, front bed)
        d = "-"
        for _ in range(waste_rows):
            if d == "-":
                for s in range(phys_max, phys_min - 1, -1):
                    self.knit("-", f"f{s}", first)
            else:
                for s in range(phys_min, phys_max + 1):
                    self.knit("+", f"f{s}", first)
            d = "+" if d == "-" else "-"

        # Transfer back-face positions to the back bed (rack 0),
        # doubled so the loops actually move on the machine.
        for n in range(self.min_n, self.max_n + 1):
            self.xfer(f"f{self._phys('b', n)}", self._loc("b", n))
        for n in range(self.min_n, self.max_n + 1):
            self.xfer(f"f{self._phys('b', n)}", self._loc("b", n))

        self.direction[first] = "-"
        self._carrier_positions[first] = phys_max

        # self._park_right(self._filler_cs, offset=3)


        # --- Stage 2: introduce every remaining carrier, one at a
        # time, ON THE FRONT BED (back-bed introductions often fail to
        # catch). Each gets its own inhook, one settling row on the
        # front face, releasehook, and a park past the right edge so
        # it begins its real work in phase with the others.
        
        # for c in fcs[1:]:
        for c in fcs:
            self.comment(f"stage 2: introduce front-set member {c}")
            self.inhook(c)
            self.direction[c] = "-"
            # A PAIR of front rows, so the member ends back on the
            # right where the carrier that cast on is already parked.
            # Plated carriers travel together, so an odd number of
            # passes would strand this one at the far end of the bed
            # and the first plated row could not be knit at all.
            # (The back set solves the same problem with its back-bed
            # row; a front-set member must not knit on the back bed,
            # or its yarn ends up in the other face.)
            self._knit_face_pass("f", carrier=c)
            self._knit_face_pass("f", carrier=c)
            self.releasehook(c)
            assert self.direction[c] == "-"
        self._cs_set_dir(fcs, "-")

        self.comment("stage 2: introduce back face carrier(s) on "
                     "front bed, one at a time")
        if self._back_cs != fcs:
            for c in self._back_cs:
                self.comment(f"introduce back-set member {c}")
                self.inhook(c)
                self.direction[c] = "-"
                self._knit_face_pass("f", carrier=c)
                assert self.direction[c] == "+"
                self.direction[c] = "+"
                self._knit_face_pass("b", carrier=c)
                self.releasehook(c)
                assert self.direction[c] == "-"

        self.comment(f"stage 2: {waste_rows} rows per-face waste")
        for _ in range(waste_rows // 2):
            self.knit_face_row_pair("f")
            self.knit_face_row_pair("b")

        # # --- Stage 3: introduce filler on the FRONT bed (knit) ---
        # self.comment("stage 3: introduce filler on front bed "
        #              "(knit pair in waste region for a firm catch)")
        # for c in self._filler_cs:
        #     self.inhook(c)
        #     self._knit_face_pass("f", carrier=c)
        #     self._knit_face_pass("b", carrier=c)
        #     self.releasehook(c)
        # # Park clear of the back face's rightmost needle, so the first
        # # filler pass (which may start with a back-bed tuck) doesn't
        # # have to travel right first.
        # self._park_right(self._filler_cs, offset=3)

    # ----------------------------------------------------------------
    # Face rows
    # ----------------------------------------------------------------

    def _knit_face_pass(self, bed, carrier=None):
        """
        One full-width pass on a single face, staying on that face's
        bed. Respects and then flips the carrier set's direction.

        Needles marked pending by increase_edge() are anchored with a tuck
        in the current pass direction, then knitted on the return pass.
        If eyelet mode is on and this row is an eyelet row for this
        bed, eyelet-column needles are missed instead of knit.

        `carrier` defaults to the bed's face carrier set; pass
        explicitly (int or tuple) for carrier-introduction rows in
        the waste region.
        """
        cs = self._face_cs(bed) if carrier is None \
            else self._carrier_set(carrier)
        d = self._cs_dir(cs)

        pending = self._pending_new_needles[bed]
        skip = self._eyelet_columns(bed, self._face_rows[bed])

        # (physical needle, logical index or None for cast-off waste)
        entries = [(self._phys(bed, n), n)
                   for n in range(self.min_n, self.max_n + 1)]
        casting_off = bed == "f" and self._cast_off_needles
        if casting_off:
            entries += [(p, None) for p in self._cast_off_needles]
        entries.sort(key=lambda e: e[0], reverse=(d == "-"))

        for phys, n in entries:
            loc = f"{bed}{phys}"
            if n is None:
                # Edge stitch on its way out: keep knitting it with
                # this row so the yarn never floats across the middle
                self.knit_cs(d, loc, cs)
            elif n in pending:
                # Direction-consistent edge cast-on.  The former twisted
                # tuck reversed three times at this same needle
                # (miss/tuck/miss), which can trigger dynamic carrier
                # overlap for plated carrier sets.  Tuck on the outgoing
                # pass; the ordinary return pass knits this new loop.
                self.tuck_cs(d, loc, cs)
            elif n in skip:
                self.miss_cs(d, loc, cs)  # eyelet: hold the loop
            else:
                self.knit_cs(d, loc, cs)
        pending.clear()
        self._face_rows[bed] += 1
        self._cs_flip(cs)

        if casting_off:
            self._cast_off_rows_left -= 1
            if self._cast_off_rows_left <= 0:
                self._knit_cast_off_transition_pass()

    def knit_face_row_pair(self, bed):
        """
        Knit one leftward + rightward pair of face rows on one bed
        with that face's carrier set.

        Following the paper, face rows always come in pairs so every
        carrier returns to its starting side and row counts stay even.

        Parameters:
            bed: "f" (front face) or "b" (back face)
        """
        assert bed in ("f", "b")
        self._knit_face_pass(bed)
        self._knit_face_pass(bed)

    # ----------------------------------------------------------------
    # Filler rows
    # ----------------------------------------------------------------

    def knit_filler_pass(self, tuck_spacing=None, tuck_offset=None):
        """
        One filler pass: tuck the filler carrier at every
        `tuck_spacing` logical stitches, alternating between the front
        and back beds tuck-to-tuck, forming the zig-zag of the spacer
        structure. Tucks do not add fabric height, so successive
        passes add filler density to the same face row (paper sec. 4).

        The tuck grid shifts by `tuck_offset` needles on each pass,
        and the front/back parity swaps each pass, so filler anchor
        points distribute over the fabric.

        Direction alternates automatically; call in pairs (or use
        knit_spacer_block) so the filler carrier ends where it started.
        """
        spacing = self.tuck_spacing if tuck_spacing is None else tuck_spacing
        offset = self.tuck_offset if tuck_offset is None else tuck_offset
        self._validate_tuck_spacing(spacing)

        cs = self._filler_cs
        d = self._cs_dir(cs)

        phase = (self._filler_pass_count * offset) % spacing
        bed_flip = self._filler_pass_count % 2

        # Tuck targets in ascending order: (needle, bed)
        targets = []
        j = 0
        n = self.min_n + phase
        while n <= self.max_n:
            bed = "f" if (j + bed_flip) % 2 == 0 else "b"
            targets.append((n, bed))
            n += spacing
            j += 1
        assert len(targets) >= 2, (
            "filler pass has fewer than 2 tucks; widen the piece or "
            "reduce tuck_spacing"
        )

        # Park one needle past the edge so the zig-zag spans the full
        # width and the return pass starts cleanly. While a step
        # change is being cast off, park beyond that waste too --
        # otherwise the filler sits in the middle of the span the
        # front carrier still has to travel.
        left_park = self._phys_min() - 1
        right_park = self._phys_max() + 1
        if self._cast_off_needles:
            left_park = min(left_park, min(self._cast_off_needles) - 1)
            right_park = max(right_park, max(self._cast_off_needles) + 1)

        if d == "-":
            for n, bed in reversed(targets):
                self.tuck_cs("-", self._loc(bed, n), cs)
            self.miss_cs("-", f"f{left_park}", cs)
        else:
            for n, bed in targets:
                self.tuck_cs("+", self._loc(bed, n), cs)
            self.miss_cs("+", f"f{right_park}", cs)

        self._filler_pass_count += 1
        self._cs_flip(cs)
        # The filler yarn now has several real anchors inside the active
        # fabric, so the tuck used to secure its expansion parking position
        # has served its purpose and must not remain on the bed.
        self._release_temporary_filler_park_tucks()

    # ----------------------------------------------------------------
    # Spacer block: the unit cell of the fabric
    # ----------------------------------------------------------------

    def _resolve_face_order(self, face_order):
        order = self.face_order if face_order is None else face_order
        assert order in ("front_first", "back_first", "alternate")
        if order == "front_first":
            return ("f", "b")
        if order == "back_first":
            return ("b", "f")
        # alternate: minimize shear bias by swapping each block
        beds = ("f", "b") if self._alternate_front_first else ("b", "f")
        self._alternate_front_first = not self._alternate_front_first
        return beds

    def knit_spacer_block(self, face_row_pairs=None,
                          filler_pass_pairs=None, tuck_spacing=None,
                          tuck_offset=None, face_order=None,
                          increase_sides=(), decrease_sides=()):
        """
        Knit one spacer "unit": face rows on both faces, then filler.

        The paper expresses filler row density as the ratio of filler
        row pairs to face row pairs; this method IS that ratio:

            filler_pass_pairs / face_row_pairs

        The instance default is 5/1 (dense, load-bearing cushion);
        the paper's default fabric was 2/1. More filler pairs ->
        denser, stiffer fabric; more face pairs -> softer,
        less-connected fabric. filler_pass_pairs=0 gives a section of
        unconnected double cloth (useful for hinge lines).

        Edge shaping is sequenced around the paper's warning that
        transferring monofilament tucks is error-prone:

            increases   (before face rows -- new needles get anchored
                         by directional tucks before any filler pass)
            face rows
            decreases   (after face rows -- previous filler tucks have
                         been knit through, needles hold face loops
                         only)
            filler passes

        Parameters:
            face_row_pairs:    face row pairs on EACH face
                               (default: instance setting)
            filler_pass_pairs: filler pass pairs after the face rows
                               (default: instance setting)
            tuck_spacing:      override the default tuck spacing
            tuck_offset:       override the default tuck offset
            face_order:        override which face is knit first
                               ("front_first" shears the front face
                               downward, "back_first" the back;
                               "alternate" minimizes bias)
            increase_sides:    edge increases this block, e.g.
                               ("left",), ("left", "right")
            decrease_sides:    edge decreases this block
        """
        if face_row_pairs is None:
            face_row_pairs = self.face_row_pairs
        if filler_pass_pairs is None:
            filler_pass_pairs = self.filler_pass_pairs
        assert face_row_pairs >= 1, "need at least one face row pair"
        assert filler_pass_pairs >= 0
        assert not (set(increase_sides) and set(decrease_sides)), \
            "cannot increase and decrease in the same block"

        first, second = self._resolve_face_order(face_order)
        self.comment(f"spacer block: {face_row_pairs} face pair(s) "
                     f"per face ({first} first), "
                     f"{filler_pass_pairs} filler pair(s)")

        for side in increase_sides:
            self.increase_edge(side)

        prepared = self._prepared_step_expansion
        assert not (prepared and increase_sides), \
            "cannot combine gradual and prepared abrupt increases"
        for pair_index in range(face_row_pairs):
            if prepared is not None and pair_index == 0:
                self.comment(
                    "complete merged abrupt-expansion cast-on in the "
                    "first directional face transition"
                )
                self._knit_merged_expansion_face_pair(first, prepared)
                self._knit_merged_expansion_face_pair(second, prepared)
            else:
                self.knit_face_row_pair(first)
                self.knit_face_row_pair(second)
        if prepared is not None:
            self._prepared_step_expansion = None

        for side in decrease_sides:
            self.decrease_edge(side)

        filler_passes = 2 * filler_pass_pairs
        if prepared is not None and filler_pass_pairs > 0:
            # The three-pass expansion moves each face carrier to the
            # opposite edge. One additional filler transition pass does the
            # same for the filler carrier, keeping all carrier sets aligned
            # for subsequent ordinary or short-row blocks.
            self.comment(
                "add one filler transition pass to follow the expanded "
                "face carriers"
            )
            filler_passes += 1
        for _ in range(filler_passes):
            self.knit_filler_pass(tuck_spacing=tuck_spacing,
                                  tuck_offset=tuck_offset)

    # ----------------------------------------------------------------
    # Edge shaping (for trapezoidal sheets)
    # ----------------------------------------------------------------

    def decrease(self, position, lean="left"):
        """
        Decrease by one stitch at logical `position`, on BOTH faces,
        in the 1-based half-gauge layout (front f{2n-1}, back b{2n}).

        Overrides ShapingHelper.decrease, whose transfers are hard
        coded to the J-30 convention (f{2n}, b{2n+1}) and would move
        loops to the wrong needles here. Same strategy as J-30: stage
        the front-face loops on the empty odd back needles, then a
        single racked pass slides BOTH faces one logical stitch over
        onto the front bed, then the back-face loops go home.

        Pure transfer -- no carrier, no direction change. The caller
        knits a settling row afterward.

        lean="left":  min_n..position-1 shift right, stacking onto
                      `position`; min_n += 1.
        lean="right": position+1..max_n shift left, stacking onto
                      `position`; max_n -= 1.
        """
        assert lean in ("left", "right"), "lean must be 'left' or 'right'"
        assert self.min_n <= position <= self.max_n, (
            f"position {position} outside active range "
            f"[{self.min_n}, {self.max_n}]"
        )

        old_min, old_max = self.min_n, self.max_n
        if lean == "left":
            assert position > self.min_n, \
                f"left decrease position ({position}) must be > min_n"
            movers = range(self.min_n, position)
            # Stage front-face loops on the empty odd back needles
            for n in movers:
                self.xfer(f"f{2 * n - 1}", f"b{2 * n - 1}")
            # One racked pass: everything on the back bed lands on the
            # front bed, one logical stitch (2 needles) to the right
            self.rack(2)
            for n in movers:
                self.xfer(f"b{2 * n}", f"f{2 * n + 2}")      # back face
                self.xfer(f"b{2 * n - 1}", f"f{2 * n + 1}")  # front face
            self.rack(0)
            # Back-face loops return to the back bed
            for n in movers:
                self.xfer(f"f{2 * n + 2}", f"b{2 * n + 2}")
            self.min_n += 1
            vacated = old_min
        else:
            assert position < self.max_n, \
                f"right decrease position ({position}) must be < max_n"
            movers = range(self.max_n, position, -1)
            for n in movers:
                self.xfer(f"f{2 * n - 1}", f"b{2 * n - 1}")
            self.rack(-2)
            for n in movers:
                self.xfer(f"b{2 * n}", f"f{2 * n - 2}")      # back face
                self.xfer(f"b{2 * n - 1}", f"f{2 * n - 3}")  # front face
            self.rack(0)
            for n in movers:
                self.xfer(f"f{2 * n - 2}", f"b{2 * n - 2}")
            self.max_n -= 1
            vacated = old_max

        self.comment(
            f"repeat drop vacated decrease needle {vacated} "
            f"x{self.drop_repeats}"
        )
        self._drop_locations_repeatedly(
            (self._loc("f", vacated), self._loc("b", vacated))
        )

    def increase(self, positions, carrier, lean="right"):
        """
        Not supported: ShapingHelper.increase assumes a closed tube in
        the J-30 needle convention and knits its own row. Spacer
        sheets grow with increase_edge(), whose new needles are tucked
        during the next face pass and knitted on its return.
        """
        raise NotImplementedError(
            "use increase_edge(side) / knit_spacer_block("
            "increase_sides=...) for spacer fabric"
        )

    def decrease_edge(self, side):
        """
        Decrease one stitch at an edge, on BOTH faces: the edge stitch
        stacks onto its neighbor one stitch inward. Pure transfer --
        the next face rows settle it.

        Best called via knit_spacer_block(decrease_sides=...), which
        sequences it after the face rows so no monofilament tucks are
        on the transferred needles (paper sec. 8).

        Parameters:
            side: "left" or "right"
        """
        assert side in ("left", "right")
        assert self.width > 4, "cannot decrease below 4 stitches"
        self.comment(f"edge decrease ({side})")
        if side == "left":
            self.decrease(self.min_n + 1, lean="left")
        else:
            self.decrease(self.max_n - 1, lean="right")

    def increase_edge(self, side):
        """
        Increase one stitch at an edge, on BOTH faces. No transfers:
        the active range simply grows and the new edge needle on each
        bed is tucked during the next face pass and knitted on its return
        on that bed. Call immediately before face rows (as
        knit_spacer_block(increase_sides=...) does) so the filler
        never tucks on an empty needle.

        Parameters:
            side: "left" or "right"
        """
        assert side in ("left", "right")
        if side == "left":
            self.min_n -= 1
            new_n = self.min_n
        else:
            self.max_n += 1
            new_n = self.max_n
        self._pending_new_needles["f"].add(new_n)
        self._pending_new_needles["b"].add(new_n)

    # ----------------------------------------------------------------
    # Abrupt width steps (for changes too large to shape gradually)
    # ----------------------------------------------------------------

    @staticmethod
    def stitches_for(inches, wales_per_inch=13.0):
        """Stitch count for a width in inches (default 13 wales/in)."""
        return max(4, int(round(inches * wales_per_inch)))

    def _tuck_new_needles_pass(self, bed, new_needles, parity):
        """
        One full-width pass on `bed` that TUCKS the newly added
        needles whose logical index has the given parity and MISSES
        everything else. Two passes (parity 0 then 1) make an
        alternating-tuck cast-on across the new needles without any
        per-needle direction reversals, and leave the carrier back
        where it started.
        """
        cs = self._face_cs(bed)
        d = self._cs_dir(cs)
        needles = (range(self.max_n, self.min_n - 1, -1) if d == "-"
                   else range(self.min_n, self.max_n + 1))
        for n in needles:
            loc = self._loc(bed, n)
            if n in new_needles and n % 2 == parity:
                self.tuck_cs(d, loc, cs)
            else:
                self.miss_cs(d, loc, cs)
        self._cs_flip(cs)

    def _prepare_merged_step_expansion(self, old_min, old_max,
                                       new_min, new_max):
        """Prepare a wider edge that follows the carriers' natural flow.

        Face row pairs normally finish on the right and leave each face
        carrier ready to travel left.  Do not force another rightward pass.
        Instead, the next spacer block uses three continuous passes: left to
        seed the new left edge, right to complete the left and seed the new
        right edge, then left to complete the right edge.

        Returns ``True`` when the merged path was prepared. Non-standard
        carrier directions fall back to the older standalone tuck passes.
        """
        assert new_min <= old_min <= old_max <= new_max
        face_directions = {
            self._cs_dir(self._front_cs), self._cs_dir(self._back_cs)
        }
        if len(face_directions) != 1:
            return False
        start_direction = next(iter(face_directions))

        self.comment(
            f"prepare merged abrupt expansion {old_min}-{old_max} -> "
            f"{new_min}-{new_max}: preserve next "
            f"{'leftward' if start_direction == '-' else 'rightward'} "
            "face flow"
        )
        self._prepared_step_expansion = {
            "old_min": old_min,
            "old_max": old_max,
            "new_min": new_min,
            "new_max": new_max,
            "start_direction": start_direction,
        }
        return True

    def _knit_merged_expansion_face_pair(self, bed, prepared):
        """Cast on an abrupt expansion in three direction-following passes."""
        assert bed in ("f", "b")
        assert self._eyelet_cfg is None, \
            "eyelets and merged abrupt expansion cannot be combined yet"
        cs = self._face_cs(bed)
        start_direction = prepared["start_direction"]
        assert self._cs_dir(cs) == start_direction

        old_min = prepared["old_min"]
        old_max = prepared["old_max"]
        new_min = prepared["new_min"]
        new_max = prepared["new_max"]
        if start_direction == "-":
            left_added = tuple(range(old_min - 1, new_min - 1, -1))
            left_seeded = frozenset(left_added[::2])
            right_added = tuple(range(old_max + 1, new_max + 1))
            right_seeded = frozenset(right_added[::2])

            # Pass 1 follows the established flow: knit left through the old
            # fabric, then seed the newly added left edge.
            for n in range(old_max, new_min - 1, -1):
                loc = self._loc(bed, n)
                if n >= old_min:
                    self.knit_cs("-", loc, cs)
                elif n in left_seeded:
                    self.tuck_cs("-", loc, cs)
                else:
                    self.miss_cs("-", loc, cs)
            self._cs_flip(cs)

            # Pass 2 completes the left cast-on, knits the old fabric, and
            # seeds the new right edge.
            for n in range(new_min, new_max + 1):
                loc = self._loc(bed, n)
                if n < old_min and n not in left_seeded:
                    self.tuck_cs("+", loc, cs)
                elif n > old_max:
                    if n in right_seeded:
                        self.tuck_cs("+", loc, cs)
                    else:
                        self.miss_cs("+", loc, cs)
                else:
                    self.knit_cs("+", loc, cs)
            self._cs_flip(cs)

            # Pass 3 completes the right cast-on and returns left through
            # live stitches.
            for n in range(new_max, new_min - 1, -1):
                loc = self._loc(bed, n)
                if n > old_max and n not in right_seeded:
                    self.tuck_cs("-", loc, cs)
                else:
                    self.knit_cs("-", loc, cs)
            self._cs_flip(cs)
        else:
            # Mirror the same construction when the carriers begin on the
            # left: right, left, right, with no forced repositioning pass.
            right_added = tuple(range(old_max + 1, new_max + 1))
            right_seeded = frozenset(right_added[::2])
            left_added = tuple(range(old_min - 1, new_min - 1, -1))
            left_seeded = frozenset(left_added[::2])

            for n in range(old_min, new_max + 1):
                loc = self._loc(bed, n)
                if n <= old_max:
                    self.knit_cs("+", loc, cs)
                elif n in right_seeded:
                    self.tuck_cs("+", loc, cs)
                else:
                    self.miss_cs("+", loc, cs)
            self._cs_flip(cs)

            for n in range(new_max, new_min - 1, -1):
                loc = self._loc(bed, n)
                if n > old_max and n not in right_seeded:
                    self.tuck_cs("-", loc, cs)
                elif n < old_min:
                    if n in left_seeded:
                        self.tuck_cs("-", loc, cs)
                    else:
                        self.miss_cs("-", loc, cs)
                else:
                    self.knit_cs("-", loc, cs)
            self._cs_flip(cs)

            for n in range(new_min, new_max + 1):
                loc = self._loc(bed, n)
                if n < old_min and n not in left_seeded:
                    self.tuck_cs("+", loc, cs)
                else:
                    self.knit_cs("+", loc, cs)
            self._cs_flip(cs)
        self._face_rows[bed] += 3

    def _prune_unresolved_filler_tucks(self, locations):
        """Change unknitted filler tucks on doomed needles into misses."""
        pruned = 0
        for location in locations:
            for index in self._unresolved_filler_tucks.pop(location, ()):
                instruction = self.instructions[index]
                if instruction.startswith("tuck "):
                    self.instructions[index] = instruction.replace(
                        "tuck ", "miss ", 1
                    )
                    pruned += 1
        if pruned:
            self.comment(
                f"pruned {pruned} unresolved filler tuck(s) before shape drop"
            )
        return pruned

    def _drop_locations_repeatedly(
        self, locations, *, prune_unresolved_filler=True
    ):
        """Issue configured redundant drops for elastic/plated loops."""
        locations = tuple(locations)
        if prune_unresolved_filler:
            self._prune_unresolved_filler_tucks(locations)
        for _ in range(self.drop_repeats):
            for location in locations:
                self.drop(location)

    def _drop_cast_off_needles(self):
        """Drop the waste stitches left over from a step change."""
        if not self._cast_off_needles:
            return
        self.comment("drop cast-off waste from the step change")
        self._drop_locations_repeatedly(
            f"f{p}" for p in sorted(self._cast_off_needles)
        )
        self._cast_off_needles = set()
        self._cast_off_rows_left = 0

    def _finish_pending_cast_off_rows(self):
        """Complete an earlier step's front waste before another transition."""
        if not self._cast_off_needles:
            return
        self.comment(
            f"complete {self._cast_off_rows_left} pending cast-off front "
            "row(s) before the next width transition"
        )
        while self._cast_off_needles and self._cast_off_rows_left > 0:
            self._knit_face_pass("f")
        # Normally the final full pass triggers the partial transition and
        # drop itself.  Retain this fallback for any legacy state whose row
        # countdown has already reached zero.
        if self._cast_off_needles:
            self._knit_cast_off_transition_pass()

    def _knit_cast_off_transition_pass(self):
        """Return the front carrier to the new edge before dropping waste.

        The ordinary cast-off passes cover the old full width.  With an even
        row count, their final pass leaves the front carrier at the old right
        edge.  Dropping the shoulders there would make the next narrowed pass
        travel in free space before reaching its first live needle; on the
        machine, that yarn can sit too high for the needle to catch.

        Knit one additional, partial front pass through the departure-side
        waste and the entire surviving range, stopping on the nearest waste
        needle beyond the opposite new edge.  The waste can then be dropped
        while the carrier is parked immediately beside the live fabric and
        ready to knit inward on its next pass.
        """
        if not self._cast_off_needles:
            return

        cs = self._front_cs
        d = self._cs_dir(cs)
        active = {self._phys("f", n)
                  for n in range(self.min_n, self.max_n + 1)}
        active_min = min(active)
        active_max = max(active)
        all_positions = active | self._cast_off_needles

        if d == "-":
            opposite_waste = [p for p in self._cast_off_needles
                              if p < active_min]
            stop = max(opposite_waste) if opposite_waste else active_min
            positions = sorted(
                (p for p in all_positions if p >= stop),
                reverse=True,
            )
        else:
            opposite_waste = [p for p in self._cast_off_needles
                              if p > active_max]
            stop = min(opposite_waste) if opposite_waste else active_max
            positions = sorted(p for p in all_positions if p <= stop)

        self.comment(
            "cast-off transition pass: cross surviving front range and "
            "park beside its next edge before dropping waste"
        )
        for phys in positions:
            self.knit_cs(d, f"f{phys}", cs)
        self._face_rows["f"] += 1
        self._cs_flip(cs)
        self._drop_cast_off_needles()

    def step_width(self, target_width, align="center", cast_off_rows=4,
                   _target_min=None):
        """
        Change the width abruptly, WITHOUT transferring any stitches.

        For large jumps (a 7" section down to 4", say) gradual edge
        shaping is neither practical nor wanted: the next row is knit
        as an essentially disconnected row at the new width. So:

          * stitches falling outside the new range are DROPPED off
            both beds -- they are not left hanging on the machine;
          * for a pure expansion, needles entering the range are cast on by
            extending the preceding face-yarn path and completing the cast-on
            inside the following face-row pair; mixed shift/resize changes
            retain the standalone alternating-tuck fallback;
          * min_n / max_n move to the new range. No xfers, no racking.

        Pure expansions remain connected through the continuously knitted old
        center. Shrinks and mixed shift/resize changes can still create a
        visible ledge; filler tucks sitting on dropped needles are released
        while the monofilament stays anchored across the remaining width.

        Parameters:
            target_width: new stitch count (>= 4)
            align:        where the new width sits relative to the old
                          span -- "center" (default), "left", "right"
            cast_off_rows: instead of dropping the outgoing stitches
                          immediately, transfer their back-face loops
                          onto the front bed and keep knitting them
                          with the FRONT face rows for this many rows,
                          then add a partial transition pass through the
                          surviving range before dropping. This parks the
                          front carrier beside the new edge, so its next
                          narrowed pass starts with catchable yarn instead
                          of traversing free space. 0 = drop at once.

        Returns:
            (dropped, added) -- the logical needle indices that left
            and entered the active range.
        """
        assert target_width >= 4, "target_width must be >= 4 stitches"
        assert align in ("center", "left", "right")
        # A second abrupt step can arrive before the preceding step has had
        # enough front rows to secure its outgoing loops. Finish those rows
        # instead of dropping the previous shoulders prematurely.
        self._finish_pending_cast_off_rows()

        old_min, old_max = self.min_n, self.max_n
        delta = target_width - self.width
        if _target_min is not None:
            new_min = _target_min
            new_max = new_min + target_width - 1
        elif align == "center":
            left_add = delta // 2
            new_min = old_min - left_add
            new_max = new_min + target_width - 1
        elif align == "left":
            new_min = old_min
            new_max = old_min + target_width - 1
        else:
            new_max = old_max
            new_min = old_max - target_width + 1

        # Every transition carrier may need to traverse both the old and new
        # ranges.  Use their union for parking so an asymmetric shrink or a
        # mixed shift/resize never sends a carrier backward merely because
        # the changed needles happen to be on its opposite side.
        transition_phys_min = min(
            self._phys("f", old_min), self._phys("b", old_min),
            self._phys("f", new_min), self._phys("b", new_min),
        )
        transition_phys_max = max(
            self._phys("f", old_max), self._phys("b", old_max),
            self._phys("f", new_max), self._phys("b", new_max),
        )

        self.comment(f"=== step width {self.width} -> {target_width} "
                     f"({align}): drop outgoing, tuck incoming ===")

        # Deal with everything that falls outside the new range.
        dropped = [n for n in range(old_min, old_max + 1)
                   if not (new_min <= n <= new_max)]
        front_parked_for_transition = False
        if dropped and cast_off_rows > 0:
            # Bring the back-face loops of the outgoing stitches over
            # to the front bed (b{2n} -> f{2n}; those front needles
            # are empty at half gauge) so a single carrier can knit
            # the whole outgoing edge. Doubled for reliability.
            self.comment(f"cast off {len(dropped)} outgoing stitches "
                         f"over {cast_off_rows} front rows")
            for _ in range(2):
                for n in dropped:
                    self.xfer(self._loc("b", n), f"f{self._phys('b', n)}")
            self._cast_off_needles = set()
            for n in dropped:
                self._cast_off_needles.add(self._phys("f", n))
                self._cast_off_needles.add(self._phys("b", n))
            self._cast_off_rows_left = cast_off_rows
            # Preserve the carrier's actual next direction. Park beyond the
            # union of the old and new spans on the side where it already
            # sits. Basing this on the waste alone is incorrect for a
            # one-sided shrink: that waste can be entirely opposite the
            # carrier.
            front_direction = self._cs_dir(self._front_cs)
            side = "right" if front_direction == "-" else "left"
            self.comment(
                f"cast-off entry: preserve next {front_direction} front "
                f"direction; park just beyond {side} transition edge"
            )
            self._park_outside_span(
                self._front_cs,
                transition_phys_min,
                transition_phys_max,
            )
            front_parked_for_transition = True
        elif dropped:
            self.comment(
                f"repeat immediate outgoing drops x{self.drop_repeats}"
            )
            self._drop_locations_repeatedly(
                location
                for n in dropped
                for location in (self._loc("f", n), self._loc("b", n))
            )

        added = {n for n in range(new_min, new_max + 1)
                 if not (old_min <= n <= old_max)}
        pure_expansion = bool(added) and not dropped \
            and new_min <= old_min and new_max >= old_max

        # Move the active range and secure the filler just beyond the NEW edge
        # opposite its next direction. A miss would only reposition the
        # carrier; the temporary tuck actually anchors the yarn for later
        # tucks in the newly added positions.
        self.min_n, self.max_n = new_min, new_max
        if added and all(c in self.active_carriers
                         for c in self._filler_cs):
            self._secure_filler_park_for_expansion(
                transition_phys_min,
                transition_phys_max,
                offset=3,
            )

        merged_expansion = False
        if pure_expansion:
            merged_expansion = self._prepare_merged_step_expansion(
                old_min, old_max, new_min, new_max
            )

        # Cast on any new needles not handled by the merged pure-expansion
        # path.
        # Any pending edge tucks from a previous increase are moot
        for bed in ("f", "b"):
            self._pending_new_needles[bed] = {
                n for n in self._pending_new_needles[bed]
                if new_min <= n <= new_max
            }

        if added and not merged_expansion:
            # Standalone alternating-tuck passes begin at the new edge in
            # each carrier's tracked direction. Park beyond the complete
            # transition span first, including when the new edge extends
            # beyond the carrier or the opposite edge shrinks inward.
            parked_sets = set()
            if front_parked_for_transition:
                parked_sets.add(self._front_cs)
            for cs in (self._front_cs, self._back_cs):
                if cs in parked_sets:
                    continue
                self._park_outside_span(
                    cs,
                    transition_phys_min,
                    transition_phys_max,
                )
                parked_sets.add(cs)
            for parity in (0, 1):
                if any(n % 2 == parity for n in added):
                    self._tuck_new_needles_pass("f", added, parity)
                    self._tuck_new_needles_pass("b", added, parity)

        return dropped, sorted(added)

    def step_range(self, target_min, target_max, cast_off_rows=4):
        """Abruptly move to an exact logical-needle interval.

        This is the absolute-coordinate counterpart of :meth:`step_width`.
        It is useful for image-derived panels because their left and right
        edges are independent; a new range may grow, shrink, or translate in
        a way that cannot be expressed by center/left/right alignment alone.
        Overlapping stitches stay live, outgoing stitches receive the normal
        step cast-off treatment, and pure expansions use the merged face-row
        cast-on from ``step_width``.
        """
        assert target_max >= target_min
        target_width = target_max - target_min + 1
        return self.step_width(
            target_width,
            cast_off_rows=cast_off_rows,
            _target_min=target_min,
        )

    # ----------------------------------------------------------------
    # Spacer-aware short rows for separated image runs
    # ----------------------------------------------------------------

    @staticmethod
    def _normalize_short_row_levels(levels):
        normalized = []
        for level in levels:
            runs = tuple((int(start), int(end)) for start, end in level)
            assert runs, "each short-row level needs at least one run"
            for start, end in runs:
                assert start <= end, f"invalid run {start}-{end}"
                assert end - start + 1 >= 2, \
                    "short-row runs must be at least two stitches wide"
            for left, right in zip(runs, runs[1:]):
                assert left[1] + 1 < right[0], \
                    "short-row runs must be ordered and separated"
            normalized.append(runs)
        assert normalized, "need at least one short-row level"
        run_count = len(normalized[0])
        assert run_count >= 1
        assert all(len(level) == run_count for level in normalized), \
            "all levels in a short-row group need the same run count"
        for outer, inner in zip(normalized, normalized[1:]):
            for outer_run, inner_run in zip(outer, inner):
                assert outer_run[0] <= inner_run[0] <= inner_run[1] <= outer_run[1], \
                    "short-row runs must nest from outer to inner"
        return tuple(normalized)

    def _knit_local_face_pair(self, bed, start, end, current):
        """Knit to a local run, turn twice, and return its outer boundary.

        Stitches between ``current`` and the run are deliberately knit. These
        transition stitches reposition the carrier without a long float.
        """
        assert bed in ("f", "b")
        assert self._eyelet_cfg is None, \
            "eyelets and image short rows cannot be combined yet"
        cs = self._face_cs(bed)
        direction = self._cs_dir(cs)
        if direction == "-":
            assert current >= end
            for n in range(current, start, -1):
                self.knit_cs("-", self._loc(bed, n), cs)
            self.tuck_cs("-", self._loc(bed, start), cs)
            for n in range(start + 1, end):
                self.knit_cs("+", self._loc(bed, n), cs)
            self.tuck_cs("+", self._loc(bed, end), cs)
            result = end
        else:
            assert current <= start
            for n in range(current, end):
                self.knit_cs("+", self._loc(bed, n), cs)
            self.tuck_cs("+", self._loc(bed, end), cs)
            for n in range(end - 1, start, -1):
                self.knit_cs("-", self._loc(bed, n), cs)
            self.tuck_cs("-", self._loc(bed, start), cs)
            result = start

        self._face_rows[bed] += 2
        return result

    @staticmethod
    def _adaptive_short_row_spacing(start, end, requested):
        """Use the requested spacing when possible, else fit two anchors."""
        width = end - start + 1
        assert width >= 2
        return min(requested, width - 1)

    def _local_filler_targets(self, start, end, spacing, offset,
                              local_pass_index=0):
        """Return at least two alternating-bed anchors inside a local run."""
        effective = self._adaptive_short_row_spacing(start, end, spacing)
        shift = max(1, abs(offset))
        phase = (local_pass_index * shift) % effective
        if effective != spacing:
            # At a tip narrower than the nominal spacing, alternate the same
            # two logical endpoints between beds for one pair. This avoids a
            # third tuck accumulating on either physical needle.
            needles = [start, end]
        else:
            needles = list(range(start + phase, end + 1, effective))
            if len(needles) < 2:
                needles = [start, end]
        bed_flip = self._filler_pass_count % 2
        return [
            (n, "f" if (index + bed_flip) % 2 == 0 else "b")
            for index, n in enumerate(needles)
        ], effective

    def _knit_local_filler_pass(self, start, end, current,
                                tuck_spacing, tuck_offset,
                                local_pass_index=0):
        """Tuck one local filler pass and anchor its transition span."""
        cs = self._filler_cs
        direction = self._cs_dir(cs)
        targets, effective = self._local_filler_targets(
            start, end, tuck_spacing, tuck_offset, local_pass_index
        )
        target_beds = {n: bed for n, bed in targets}
        bed_flip = self._filler_pass_count % 2

        if direction == "-":
            assert current >= end
            transition = list(range(current, end, -tuck_spacing))
            needles = sorted(set(transition + list(target_beds)))
            for index, n in reversed(list(enumerate(needles))):
                bed = target_beds.get(
                    n, "f" if (index + bed_flip) % 2 == 0 else "b"
                )
                self.tuck_cs("-", self._loc(bed, n), cs)
            self.miss_cs("-", f"f{self._phys('f', start) - 1}", cs)
            result = start
        else:
            assert current <= start
            transition = list(range(current, start, tuck_spacing))
            needles = sorted(set(transition + list(target_beds)))
            for index, n in enumerate(needles):
                bed = target_beds.get(
                    n, "f" if (index + bed_flip) % 2 == 0 else "b"
                )
                self.tuck_cs("+", self._loc(bed, n), cs)
            self.miss_cs("+", f"f{self._phys('b', end) + 1}", cs)
            result = end

        if effective != tuck_spacing:
            self.comment(
                f"short-row filler: width {end - start + 1} cannot fit "
                f"spacing {tuck_spacing}; using {effective} with offset >= 1"
            )
        self._filler_pass_count += 1
        self._cs_flip(cs)
        return result

    @classmethod
    def _short_row_filler_pairs(cls, start, end, requested_pairs, spacing):
        """Cap filler pairs before the local tuck pattern repeats.

        Full-width spacer blocks retain their requested density. Short-row
        blocks use only the even number of distinct offset phases that fit
        two natural anchors in the local run. A very narrow tip still gets
        one pair, alternating the endpoints between front and back beds.
        """
        if requested_pairs == 0:
            return 0
        width = end - start + 1
        effective = cls._adaptive_short_row_spacing(start, end, spacing)
        distinct_phases = max(1, min(effective, width - effective))
        nonrepeating_pairs = max(1, distinct_phases // 2)
        return min(requested_pairs, nonrepeating_pairs)

    def _return_short_row_filler_to_edge(self, current, spacing):
        """Reposition filler without re-tucking the just-finished tip."""
        cs = self._filler_cs
        direction = self._cs_dir(cs)
        bed_flip = self._filler_pass_count % 2
        if direction == "-":
            needles = list(range(current - spacing, self.min_n - 1, -spacing))
            for index, n in enumerate(needles):
                bed = "f" if (index + bed_flip) % 2 == 0 else "b"
                self.tuck_cs("-", self._loc(bed, n), cs)
            self.miss_cs("-", f"f{self._phys('f', self.min_n) - 1}", cs)
            result = self.min_n
        else:
            needles = list(range(current + spacing, self.max_n + 1, spacing))
            for index, n in enumerate(needles):
                bed = "f" if (index + bed_flip) % 2 == 0 else "b"
                self.tuck_cs("+", self._loc(bed, n), cs)
            self.miss_cs("+", f"f{self._phys('b', self.max_n) + 1}", cs)
            result = self.max_n
        self._filler_pass_count += 1
        self._cs_flip(cs)
        return result

    def _finish_short_row_face_route(self, bed, current, continuation):
        """Return a face carrier to an edge and toward the main run."""
        cs = self._face_cs(bed)
        direction = self._cs_dir(cs)
        if direction == "-":
            for n in range(current - 1, self.min_n - 1, -1):
                self.knit_cs("-", self._loc(bed, n), cs)
            self._cs_set_dir(cs, "+")
            if continuation is not None:
                for n in range(self.min_n + 1, continuation[0]):
                    self.knit_cs("+", self._loc(bed, n), cs)
        else:
            for n in range(current + 1, self.max_n + 1):
                self.knit_cs("+", self._loc(bed, n), cs)
            self._cs_set_dir(cs, "-")
            if continuation is not None:
                for n in range(self.max_n - 1, continuation[1], -1):
                    self.knit_cs("-", self._loc(bed, n), cs)

    def knit_spacer_short_rows(self, levels, filler_pass_pairs=None,
                               tuck_spacing=None, tuck_offset=None,
                               face_order=None, continuation=None):
        """Knit nested separated runs as one spacer short-row episode.

        ``levels`` is ordered outer-to-inner. Each level is a left-to-right
        list of inclusive ``(start, end)`` logical-needle runs. For example,
        two triangular lobes over a 1..20 base can be expressed as::

            [
                [(3, 6), (15, 18)],
                [(4, 5), (16, 17)],
            ]

        With carriers parked on the right, the right lobe is completed first,
        followed by knitted transition stitches and the left lobe. Every
        local level is a complete spacer block: both faces turn through the
        run and local filler passes follow immediately. ``continuation`` may
        identify the ordinary run that continues above the terminal lobes.
        """
        levels = self._normalize_short_row_levels(levels)
        if filler_pass_pairs is None:
            filler_pass_pairs = self.filler_pass_pairs
        spacing = self.tuck_spacing if tuck_spacing is None else tuck_spacing
        offset = self.tuck_offset if tuck_offset is None else tuck_offset
        assert filler_pass_pairs >= 0
        self._validate_tuck_spacing(spacing)

        directions = {
            self._cs_dir(self._front_cs),
            self._cs_dir(self._back_cs),
            self._cs_dir(self._filler_cs),
        }
        assert len(directions) == 1, \
            "short-row spacer carriers must begin on the same side"
        direction = next(iter(directions))
        lobe_order = (range(len(levels[0]) - 1, -1, -1)
                      if direction == "-" else range(len(levels[0])))
        edge = self.max_n if direction == "-" else self.min_n
        face_positions = {"f": edge, "b": edge}
        filler_position = edge

        self.comment(
            f"=== spacer short rows: {len(levels)} level(s), "
            f"{len(levels[0])} run(s) ==="
        )
        for lobe in lobe_order:
            for level_index, level in enumerate(levels):
                start, end = level[lobe]
                self.comment(
                    f"short-row spacer block: lobe {lobe}, "
                    f"level {level_index}, run {start}-{end}"
                )
                first, second = self._resolve_face_order(face_order)
                for bed in (first, second):
                    face_positions[bed] = self._knit_local_face_pair(
                        bed, start, end, face_positions[bed]
                    )
                local_pairs = self._short_row_filler_pairs(
                    start, end, filler_pass_pairs, spacing
                )
                if local_pairs != filler_pass_pairs:
                    self.comment(
                        f"short-row filler: use {local_pairs} of "
                        f"{filler_pass_pairs} requested pair(s) at width "
                        f"{end - start + 1} to avoid repeated tuck needles"
                    )
                for local_pass_index in range(2 * local_pairs):
                    filler_position = self._knit_local_filler_pass(
                        start, end, filler_position, spacing, offset,
                        local_pass_index,
                    )

        for bed in ("f", "b"):
            self._finish_short_row_face_route(
                bed, face_positions[bed], continuation
            )

        # One sparse transition pass returns the filler to the same side as
        # the face carriers. It starts beyond the just-finished tip so those
        # needles are not tucked again before a face row can clear them.
        filler_position = self._return_short_row_filler_to_edge(
            filler_position, spacing
        )
        if continuation is not None:
            self.comment(
                f"transition carriers toward continuing run "
                f"{continuation[0]}-{continuation[1]}"
            )
            # Continue the filler transition toward the main component with
            # sparse alternating-bed anchors. This remains part of the pass
            # just emitted above, so direction and filler-density accounting
            # do not change a second time.
            bed_flip = (self._filler_pass_count - 1) % 2
            if direction == "-":
                transition_needles = range(
                    self.min_n + 1, continuation[0], spacing
                )
                for index, n in enumerate(transition_needles):
                    bed = "f" if (index + bed_flip) % 2 == 0 else "b"
                    self.tuck_cs("+", self._loc(bed, n), self._filler_cs)
            else:
                transition_needles = range(
                    self.max_n - 1, continuation[1], -spacing
                )
                for index, n in enumerate(transition_needles):
                    bed = "f" if (index + bed_flip) % 2 == 0 else "b"
                    self.tuck_cs("-", self._loc(bed, n), self._filler_cs)

    # ----------------------------------------------------------------
    # Trapezoidal sheet (cut-open generalized cylinder)
    # ----------------------------------------------------------------

    def knit_spacer_trapezoid(self, sections, face_row_pairs=None,
                              filler_pass_pairs=None, tuck_spacing=None,
                              tuck_offset=None, face_order=None,
                              step_threshold=None):
        """
        Knit a shaped spacer sheet from a list of width sections --
        the cut-open surface of a generalized cylinder, sized to wrap
        a (possibly tapered) robot arm segment.

        Parameters:
            sections: list of section specs, bottom to top. Each is
                either a tuple (width, blocks) or a dict
                {"width": int, "blocks": int, ...} where the dict may
                additionally override any of face_row_pairs /
                filler_pass_pairs / tuck_spacing / tuck_offset /
                face_order for that section.

                `width` is the section's stitch count; `blocks` is how
                many spacer blocks to knit in the section. The FIRST
                section's width must equal the width the helper was
                constructed (and cast on) with.

                Small width changes are SHAPED gradually over the
                section's first blocks, at most one stitch per edge
                per block. Larger ones are STEPPED: see step_width()
                -- no transfers, outgoing stitches dropped, incoming
                needles tucked on, all at the section boundary. A
                section steps when |change| > 2 * blocks (i.e. it
                cannot be shaped in the space available) or when it
                exceeds `step_threshold`; a section may also force the
                choice with "step": True / False, and pick where the
                new width sits with "align": "center" (default),
                "left" or "right".
            face_row_pairs, filler_pass_pairs, tuck_spacing,
            tuck_offset, face_order:
                defaults for every section (fall back to the instance
                settings; see knit_spacer_block).
            step_threshold:
                width changes larger than this are stepped even if
                they would fit gradually (None = only step when
                gradual shaping cannot fit).

        Example (big jumps, in inches at 13 wales/inch):
            S = SpacerHelper.stitches_for
            sp.knit_spacer_trapezoid([
                (S(7.0), 10),
                (S(4.0), 10),     # steps down, extra stitches dropped
                (S(7.75), 10),    # steps back up, new needles tucked
                (S(3.0), 10),
            ])

        Example (tapered forearm wrap, 3 sections):
            sp.knit_spacer_trapezoid([
                (40, 8),   # cast-on width, 8 blocks
                (34, 8),   # taper to 34 over the next blocks
                (30, 6),
            ])
        """
        assert len(sections) >= 1
        norm = []
        for sec in sections:
            if isinstance(sec, dict):
                spec = dict(sec)
            else:
                w, blocks = sec
                spec = {"width": w, "blocks": blocks}
            assert spec["width"] >= 4, "sections must be >= 4 stitches"
            assert spec["blocks"] >= 1
            norm.append(spec)

        assert norm[0]["width"] == self.width, (
            f"first section width ({norm[0]['width']}) must match the "
            f"current width ({self.width}); construct/cast on the "
            "helper with the first section's width"
        )

        for i, spec in enumerate(norm):
            target = spec["width"]
            blocks = spec["blocks"]
            delta = target - self.width

            # Gradual shaping can move at most 2 stitches per block
            # (one per edge). Anything larger is a step change unless
            # the section explicitly says otherwise.
            step = spec.get("step")
            if step is None:
                step = abs(delta) > 2 * blocks or (
                    step_threshold is not None
                    and abs(delta) > step_threshold
                )
            if not step:
                assert abs(delta) <= 2 * blocks, (
                    f"section {i}: cannot change width by {delta} in "
                    f"{blocks} blocks (max 2 stitches per block); drop "
                    f'the "step": False override to step instead'
                )

            self.comment(f"=== trapezoid section {i}: width {target}, "
                         f"{blocks} blocks"
                         f"{' (STEP)' if step and delta else ''} ===")

            if step and delta:
                self.step_width(
                    target,
                    align=spec.get("align", "center"),
                    cast_off_rows=spec.get("cast_off_rows", 4),
                )
                delta = 0

            # Balance the shaping between the two edges
            left_todo = abs(delta) // 2
            right_todo = abs(delta) - left_todo
            grow = delta > 0

            for _ in range(blocks):
                sides = []
                if left_todo > 0:
                    sides.append("left")
                    left_todo -= 1
                if right_todo > 0:
                    sides.append("right")
                    right_todo -= 1
                self.knit_spacer_block(
                    face_row_pairs=spec.get("face_row_pairs",
                                            face_row_pairs),
                    filler_pass_pairs=spec.get("filler_pass_pairs",
                                               filler_pass_pairs),
                    tuck_spacing=spec.get("tuck_spacing", tuck_spacing),
                    tuck_offset=spec.get("tuck_offset", tuck_offset),
                    face_order=spec.get("face_order", face_order),
                    increase_sides=tuple(sides) if grow else (),
                    decrease_sides=() if grow else tuple(sides),
                )
            assert self.width == target

    # ----------------------------------------------------------------
    # Finishing
    # ----------------------------------------------------------------

    def finish_spacer(self, waste_rows=6):
        """
        Finish the piece by mirroring the cast-on, leaving a waste
        region for sewing (e.g. zipper attachment) instead of a
        secured bind-off:

          1. Outhook the filler carrier set.
          2. Knit `waste_rows` rows of per-face waste: front pairs
             with the front set, back pairs with the back set.
             Outhook the BACK set.
          3. Transfer the back-bed stitches to the front bed (b{2n} ->
             f{2n}; empty at half gauge), merging everything onto the
             front bed at full gauge.
          4. Knit `waste_rows` more rows across ALL front-bed positions
             with the FRONT set, outhook it, and drop everything.

        The merged waste is knit with the FRONT yarn on purpose: the
        back face is the one that may carry conductive yarn, and
        running it across every needle of the merged region would put
        conductive fibre over the whole width of one side. The back
        set leaves the piece as early as possible.

        The dropped edge is NOT secured -- by design: the waste region
        is for cutting/sewing and can be unraveled after seaming.

        Parameters:
            waste_rows: rows of waste per stage (>= 5; forced even,
                        default 6)
        """
        assert waste_rows >= 5, "need at least 5 waste rows"
        if waste_rows % 2 == 1:
            waste_rows += 1

        self.comment("=== finish (mirrored cast-on, waste for sewing) ===")
        # self.outhook_cs(self._filler_cs)
        self._release_temporary_filler_park_tucks()
        self._finish_pending_cast_off_rows()

        # --- Stage 1: per-face waste ---
        self.comment(f"finish stage 1: {waste_rows} rows per-face waste")
        for _ in range(waste_rows // 2):
            self.knit_face_row_pair("f")
            self.knit_face_row_pair("b")
        # The back set goes out here: it is the one that may be
        # conductive, and it takes no part in the merged waste.
        # if self._front_cs != self._back_cs:
        self.outhook_cs(self._front_cs)
        self.outhook_cs(self._back_cs)

        # --- Stage 2: merge back onto front bed ---
        # Back-face loops sit on b{2n}; the opposite front needles
        # f{2n} are empty at half gauge, so this is a rack-0 xfer.
        # Doubled for machine reliability.
        self.comment("finish stage 2: transfer back bed to front bed")
        for _ in range(2):
            for n in range(self.min_n, self.max_n + 1):
                self.xfer(self._loc("b", n), f"f{self._phys('b', n)}")

        # --- Stage 3: merged waste rows on all front positions ---
        self.comment(f"finish stage 3: {waste_rows} merged rows, drop")
        cs = self._filler_cs
        phys_min = self._phys_min()   # leftmost
        phys_max = self._phys_max()   # rightmost
        # Follow the filler carrier's existing side and direction. Filler
        # passes already park just beyond the corresponding edge, so forcing
        # every finish to begin on the right can create a full-width miss when
        # an earlier odd transition left the carrier on the left.
        self.comment(
            f"finish merged waste follows existing {self._cs_dir(cs)} "
            "filler direction"
        )
        for _ in range(waste_rows):
            if self._cs_dir(cs) == "-":
                for s in range(phys_max, phys_min - 1, -1):
                    self.knit_cs("-", f"f{s}", cs)
            else:
                for s in range(phys_min, phys_max + 1):
                    self.knit_cs("+", f"f{s}", cs)
            self._cs_flip(cs)
        self.outhook_cs(cs)

        for s in range(phys_min, phys_max + 1):
            self.drop(f"f{s}")

    def drop_all_spacer(self):
        """
        Quick teardown for development: outhook all carrier sets and
        drop every loop on both beds. No waste region, nothing
        secured.
        """
        for cs in (self._filler_cs, self._back_cs, self._front_cs):
            if all(c in self.active_carriers for c in cs):
                self.outhook_cs(cs)
        for n in range(self.min_n, self.max_n + 1):
            self.drop(self._loc("f", n))
            self.drop(self._loc("b", n))

    # ----------------------------------------------------------------
    # Design utility: thickness model from the paper (eq. 1)
    # ----------------------------------------------------------------

    @staticmethod
    def estimate_thickness(tuck_spacing, stitch_pitch_mm=25.4 / 13,
                           bed_gap_mm=3.913, shrink=0.653):
        """
        Estimate finished spacer thickness (mm) from the paper's
        right-triangle model (eq. 1):

            t = sqrt(x^2 + b^2 - (s*x)^2)

        where x = tuck spacing in mm (tuck_spacing stitches *
        stitch_pitch_mm), b = bed gap, s = draw-in shrink factor.

        The default stitch pitch uses the measured 13 wales/inch;
        bed_gap_mm and shrink are the paper's fitted values for their
        half-gauge fabric on a Shima SWG091N2 -- re-fit all three from
        your own swatches for trustworthy numbers.
        """
        x = tuck_spacing * stitch_pitch_mm
        return math.sqrt(x * x + bed_gap_mm * bed_gap_mm
                         - (shrink * x) ** 2)
