"""Compile v3 tubular design plans, with experimental single-opening traversal."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from .tubular import with_holes
from .flap_bind_off import FlapBindOffConfig, resolve_flap
from .plated_helper import PlatedShapingHelper, carrier_group, members


@dataclass(frozen=True)
class TubularConfig:
    gauge: int = 2
    carrier: int | tuple[int, ...] = 3
    section_carriers: dict[str, int | tuple[int, ...]] = field(default_factory=dict)
    cast_on: str = "twisted_tuck"
    settling_courses: int = 4
    plating_setup_courses: int = 2
    finish: str = "bind_off"
    flap: FlapBindOffConfig | dict | None = None
    side_slack: bool = False
    max_rack: int = 8
    double_transfers: bool = False
    drop_repeats: int | None = None
    short_rows_after: dict[int, list[dict]] = field(default_factory=dict)
    nonwire_caston: int | tuple[int, ...] | None = None


@dataclass(frozen=True)
class TubularResult:
    knitout: str
    schedule: tuple[dict, ...]

    def write(self, path):
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.knitout + "\n")
        return destination


def _preflight(plan, config):
    plan = with_holes(plan, plan.get("holes", ()))
    if config.drop_repeats is not None and (type(config.drop_repeats) is not int or config.drop_repeats < 1):
        raise ValueError("drop_repeats must be None or a positive integer")
    if type(config.double_transfers) is not bool:
        raise ValueError("double_transfers must be boolean")
    if type(config.gauge) is not int or config.gauge not in (2, 3, 4):
        raise ValueError("tubular gauge must be 2, 3 or 4")
    if type(config.max_rack) is not int or config.max_rack < config.gauge:
        raise ValueError("max_rack must accommodate a one-needle transfer")
    if config.cast_on not in ("twisted_tuck", "alt_tuck", "knit", "all_needle_transition", "none"):
        raise ValueError("unknown tubular cast-on")
    if config.cast_on == "all_needle_transition" and config.gauge != 2:
        raise ValueError("all-needle transition requires gauge 2")
    if type(config.plating_setup_courses) is not int or config.plating_setup_courses < 1:
        raise ValueError("plating_setup_courses must be a positive integer")
    if config.cast_on == "none" and config.nonwire_caston is not None:
        raise ValueError("cast_on=none cannot use a separate nonwire_caston carrier")
    if config.cast_on != "none" and (type(config.settling_courses) is not int or config.settling_courses < 2):
        raise ValueError("at least two settling courses are required")
    if config.finish not in ("bind_off", "drop", "flap_bind_off"):
        raise ValueError("finish must be bind_off, drop or flap_bind_off")
    courses = plan['courses']
    if not courses:
        raise ValueError("plan needs courses")
    for i, row in enumerate(courses, 1):
        if row['course'] != i:
            raise ValueError("courses must be consecutive starting at 1")
        lo, hi = row['bed_runs']['f']
        if (type(lo) is not int or type(hi) is not int or lo < 1 or hi > plan['bed_width']
                or hi - lo + 1 < 4 or row['bed_runs']['b'] != [lo, hi]
                or row['front_stitches'] != hi-lo+1 or row['stitches'] != 2*(hi-lo+1)):
            raise ValueError(f"course {i}: expected balanced beds with at least four stitches each")
        if i > 1:
            old_lo, old_hi = courses[i-2]['bed_runs']['f']
            if abs(lo-old_lo) > 1 or abs(hi-old_hi) > 1:
                raise ValueError(f"course {i}: outer edge changes exceed one needle per side; resample more courses")
            if (lo-old_lo) * (hi-old_hi) > 0:
                raise ValueError(f"course {i}: lateral relocation is not supported")
    if config.finish == 'flap_bind_off':
        if config.side_slack:
            raise ValueError('flap bind-off currently requires side_slack=False')
        resolve_flap(*courses[-1]['bed_runs']['f'], config.flap)
    elif config.flap is not None:
        raise ValueError('flap configuration requires finish=flap_bind_off')
    for course, turns in config.short_rows_after.items():
        if type(course) is not int or not 1 <= course <= len(courses):
            raise ValueError("short-row course keys must be one-based integers")
        lo, hi = courses[course-1]['bed_runs']['f']
        for turn in turns:
            if turn.get('b') not in ('f', 'b') or type(turn.get('n')) is not int or not lo <= turn['n'] <= hi:
                raise ValueError("short-row turns must name a live bed-local needle")
    holes = sorted(plan['holes'], key=lambda h: h['start_course'])
    previous_end = 0
    for hole in holes:
        start, gaps = hole['start_course'], hole['gaps']
        end = start + len(gaps)  # includes the closing course
        if start <= previous_end:
            raise ValueError("only one opening at a time; leave a complete course between holes")
        previous_end = end
        if config.side_slack:
            raise ValueError("side_slack is not supported with openings")
        if gaps[0][1] - gaps[0][0] > 1 or gaps[-1][1] - gaps[-1][0] > 1:
            raise ValueError("opening and closing gaps must be one or two needles wide")
        if any(start-1 <= course <= end for course in config.short_rows_after):
            raise ValueError("extra short rows must be outside opening episodes")
        region = courses[start-2:end]
        if len({tuple(row['bed_runs']['f']) for row in region}) != 1:
            raise ValueError(f"hole at course {start}: keep outer width constant from preceding through closing course")
        carriers = {config.section_carriers.get(row['section'], config.carrier) for row in region}
        if len(carriers) != 1:
            raise ValueError("material/carrier changes must occur outside the opening episode")
        for old, new in zip(gaps, gaps[1:]):
            if any(abs(a-b) > 1 for a, b in zip(old, new)) or max(old[0], new[0]) > min(old[1], new[1]):
                raise ValueError("hole edges may move at most one needle per course and must overlap")
    return plan


class _Opening:
    def __init__(self, helper, carrier, bed):
        self.sh, self.carrier, self.bed = helper, carrier, bed
        self.other = 'b' if bed == 'f' else 'f'
        self.gap = None
        self.at_left = False
        self.live = {self.needle(bed, n): 1 for bed in ("f", "b")
                     for n in range(helper.min_n, helper.max_n+1)}

    def needle(self, bed, n):
        return self.sh._loc(bed, n, self.sh.gauge)

    def pass_(self, bed, start, end, direction, seeds=()):
        step = 1 if direction == '+' else -1
        if (end-start)*step < 0:
            return
        for n in range(start, end+step, step):
            target = self.needle(bed, n)
            if n in seeds and bed == self.bed:
                if target in self.live:
                    raise ValueError(f"increase target {target} is occupied")
                self.live[target] = 1
                opposite = '-' if direction == '+' else '+'
                self.sh.miss(direction, target, self.carrier)
                self.sh.tuck(opposite, target, self.carrier)
                self.sh.miss(direction, target, self.carrier)
            else:
                if target not in self.live:
                    raise ValueError(f"cannot knit empty opening needle {target}")
                self.live[target] = 1
                self.sh.knit(direction, target, self.carrier)

    def move_outward_many(self, moves):
        """Stage the complete edge sweep, then deliver groups at each rack."""
        staging = []
        delivery = {}
        for source, target in moves:
            gauge = self.sh.gauge
            physical = gauge*source + (1 if self.bed == 'b' else 0)
            temporary = f'{self.other}{physical}'
            source_loc = self.needle(self.bed, source)
            target_loc = self.needle(self.bed, target)
            if source_loc not in self.live or temporary in self.live or target_loc not in self.live:
                raise ValueError('local decrease needs live source/target and empty staging needle')
            self.live[target_loc] += self.live.pop(source_loc)
            staging.append((source_loc, temporary))
            rack = gauge*(target-source)*(1 if self.bed == 'f' else -1)
            delivery.setdefault(rack, []).append((temporary, target_loc))
        self.sh.xfer_pass(staging)
        for rack, transfers in delivery.items():
            self.sh.rack(rack)
            self.sh.xfer_pass(transfers)
            self.sh.rack(0)
        self.sh.drop_vacated(location for pair in staging for location in pair)

    def start(self, gap):
        a, b = gap
        # Position the carrier at an opening edge by a connected partial pass.
        # This is explicitly reported as an extra setup pass, outside design courses.
        if self.bed == 'f':
            self.pass_('f', self.sh.max_n, b+1, '-')
            self.at_left = False
        else:
            self.pass_('f', self.sh.max_n, self.sh.min_n, '-')
            self.pass_('b', self.sh.min_n, a-1, '+')
            self.at_left = True
        moves = [(a, a-1)]
        if b != a:
            moves.append((b, b+1))
        self.move_outward_many(moves)
        self.gap = (a, b)

    def course(self, gap):
        a, b = gap
        old_a, old_b = self.gap
        moves = []
        if a < old_a:
            moves.append((a, a-1))
        if b > old_b:
            moves.append((b, b+1))
        self.move_outward_many(moves)
        seeds = set(range(old_a, a)) | set(range(b+1, old_b+1))
        lo, hi = self.sh.min_n, self.sh.max_n
        # When a shrinking gap creates a new stitch at the starting edge,
        # approach it from the old edge before reversing into the open course.
        # Otherwise the first miss would request travel in the wrong direction.
        if self.at_left and a > old_a:
            self.sh.comment('seed new left edge before reversing')
            self.pass_(self.bed, a-1, a-1, '+', {a-1})
            seeds.remove(a-1)
        elif not self.at_left and b < old_b:
            self.sh.comment('seed new right edge before reversing')
            self.pass_(self.bed, b+1, b+1, '-', {b+1})
            seeds.remove(b+1)
        if self.at_left:
            self.pass_(self.bed, a-1, lo, '-', seeds)
            self.pass_(self.other, lo, hi, '+')
            self.pass_(self.bed, hi, b+1, '-', seeds)
        else:
            self.pass_(self.bed, b+1, hi, '+', seeds)
            self.pass_(self.other, hi, lo, '-')
            self.pass_(self.bed, lo, a-1, '+', seeds)
        self.at_left = not self.at_left
        self.gap = (a, b)
        expected = {self.needle(bed, n) for bed in ('f', 'b')
                    for n in range(lo, hi+1) if bed != self.bed or not a <= n <= b}
        if set(self.live) != expected or any(count != 1 for count in self.live.values()):
            raise ValueError("opening course did not secure all surviving loops")

    def close(self):
        a, b = self.gap
        lo, hi = self.sh.min_n, self.sh.max_n
        seeds = set(range(a, b+1))
        # Seed the short upper bridge only when the opening ends. Continue once
        # around the now closed tube, securing the bridge on subsequent courses.
        if self.at_left:
            self.pass_(self.bed, a, hi, '+', seeds)
            self.pass_(self.other, hi, lo, '-')
            self.pass_(self.bed, lo, a-1, '+')
            endpoint = a
        else:
            self.pass_(self.bed, b, lo, '-', seeds)
            self.pass_(self.other, lo, hi, '+')
            self.pass_(self.bed, hi, b+1, '-')
            endpoint = b+1
        # Return to the ordinary tubular seam on a connected partial pass.
        self.sh.comment('opening recovery partial pass (extra to design course)')
        self.pass_(self.bed, endpoint, hi, '+')
        expected = {self.needle(bed, n) for bed in ('f', 'b') for n in range(lo, hi+1)}
        if set(self.live) != expected or any(count != 1 for count in self.live.values()):
            raise ValueError("closing course did not restore the full live tube")
        self.sh.direction[self.carrier] = '-'


def compile_tubular_plan(plan, config=None):
    """Return knitout and an instruction-range schedule; write only after success.

    Outer shaping delegates to the wire helper. Internal openings use local
    transfers and reverse along the remaining circumference. Machine swatching
    is required; instruction checks do not establish physical loop stability.
    """
    config = config or TubularConfig()
    config = replace(config, carrier=carrier_group(config.carrier),
                     section_carriers={name: carrier_group(value) for name, value in config.section_carriers.items()},
                     nonwire_caston=None if config.nonwire_caston is None else carrier_group(config.nonwire_caston))
    if config.finish == 'flap_bind_off':
        flap = config.flap or FlapBindOffConfig()
        if isinstance(flap, dict):
            flap = FlapBindOffConfig(**flap)
        flap = replace(flap,
                       stitch_gauge=flap.stitch_gauge if flap.stitch_gauge is not None else plan.get('stitch_gauge'),
                       row_gauge=flap.row_gauge if flap.row_gauge is not None else plan.get('course_gauge'))
        config = replace(config, flap=flap)
    plan = _preflight(plan, config)
    rows = plan['courses']
    first = rows[0]
    lo, hi = first['bed_runs']['f']
    sh = PlatedShapingHelper(hi-lo+1, gauge=config.gauge, side_slack=config.side_slack,
                             double_transfers=config.double_transfers, drop_repeats=config.drop_repeats)
    sh.min_n, sh.max_n = lo, hi
    sh.MAX_RACK = config.max_rack
    sh.plating_setup_courses = config.plating_setup_courses
    sh.standard_headers()
    schedule = []

    def record(kind, start, course=None, **extra):
        schedule.append(dict(kind=kind, course=course,
                             instruction_start=start, instruction_end=len(sh.instructions),
                             knitout_line_start=start+len(sh.headers)+3,
                             knitout_line_end=len(sh.instructions)+len(sh.headers)+2, **extra))

    carrier = config.section_carriers.get(first['section'], config.carrier)
    if config.cast_on == 'none':
        extra = sh.start_tubular_carriers(carrier, config.plating_setup_courses)
        record('direct_carrier_setup', 0, carrier=carrier, extra_courses=extra)
    else:
        cast = dict(twisted_tuck=sh.cast_on_tubular_twisted_tuck,
                    alt_tuck=sh.cast_on_tubular_alt_tuck,
                    knit=sh.cast_on_tubular_knit,
                    all_needle_transition=sh.cast_on_all_needle_transition)[config.cast_on]
        requested_cast = carrier if config.nonwire_caston is None else config.nonwire_caston
        # Establish loops with the first yarn; introduce companion yarns solo.
        cast_carrier = members(requested_cast)[0]
        cast(cast_carrier, settling_rows=config.settling_courses)
        record('cast_on_and_settling', 0, carrier=cast_carrier)
        if len(members(requested_cast)) > 1:
            start = len(sh.instructions)
            extra = sh.prep_tubular_colorwork([requested_cast])
            record('plating_carrier_setup', start, carrier=requested_cast, extra_courses=extra)
        if requested_cast != carrier:
            start = len(sh.instructions)
            sh.comment('transition from nonwire cast-on yarn to first section yarn')
            extra = sh.prep_tubular_colorwork([carrier])
            sh.knit_tubular_row(carrier)
            sh.retire_carriers(requested_cast, carrier)
            record('nonwire_caston_transition_extra_courses', start, carrier=carrier,
                   cast_on_carrier=requested_cast, extra_courses=extra+1)
    hole_starts = {h['start_course']: h for h in plan['holes']}
    opening = None
    current_hole = None
    for row in rows:
        number = row['course']
        next_carrier = config.section_carriers.get(row['section'], config.carrier)
        if next_carrier != carrier:
            start = len(sh.instructions)
            extra = sh.prep_tubular_colorwork([next_carrier])
            sh.retire_carriers(carrier, next_carrier)
            carrier = next_carrier
            record('carrier_transition_extra_course', start, number, extra_courses=extra)
        if number in hole_starts:
            current_hole = hole_starts[number]
            opening = _Opening(sh, carrier, current_hole['bed'])
            start = len(sh.instructions)
            sh.comment('opening setup partial passes and local decreases')
            opening.start(current_hole['gaps'][0])
            record('opening_setup', start, number)
        start = len(sh.instructions)
        sh.comment(f'design course {number}; section {row["section"]}')
        if opening:
            offset = number-current_hole['start_course']
            if offset < len(current_hole['gaps']):
                opening.course(current_hole['gaps'][offset])
                record('open_course', start, number, bed=current_hole['bed'],
                       gap=current_hole['gaps'][offset])
                continue
            opening.close()
            record('closing_course_and_recovery', start, number)
            opening = None
            continue
        new_lo, new_hi = row['bed_runs']['f']
        increase = []
        both_decrease = new_lo > sh.min_n and new_hi < sh.max_n
        if both_decrease:
            sh.decrease_both()
        elif new_lo > sh.min_n:
            sh.decrease(sh.min_n+1, lean='left')
        elif new_lo < sh.min_n:
            increase.append((sh.min_n, 'left'))
        if new_hi < sh.max_n and not both_decrease:
            sh.decrease(sh.max_n-1, lean='right')
        elif new_hi > sh.max_n:
            increase.append((sh.max_n, 'right'))
        if increase:
            sh.increase(increase, carrier)
        else:
            sh.knit_tubular_row(carrier)
        if (sh.min_n, sh.max_n) != (new_lo, new_hi):
            raise ValueError(f'course {number}: shaping did not reach planned range')
        record('tubular_course', start, number)
        if number in config.short_rows_after:
            start = len(sh.instructions)
            sh.short_rows(config.short_rows_after[number], carrier)
            record('short_rows', start, number)
    start = len(sh.instructions)
    if config.finish == 'drop':
        sh.drop_all_tubular(carrier)
    elif config.finish == 'flap_bind_off':
        layout = sh.bind_off_flap(carrier, **vars(config.flap))
        record(config.finish, start, flap=layout)
    else:
        sh.bind_off_tubular(carrier)
    if config.finish != 'flap_bind_off':
        record(config.finish, start)
    return TubularResult(sh.write(), tuple(schedule))
