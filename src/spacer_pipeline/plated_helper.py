"""Carrier-group adapter over the existing wire ShapingHelper.

Keep carrier order exactly as supplied, on both beds. This emits combined-yarn
stitches; it does not promise which yarn appears outside on a given machine.
"""
from .tube_engine import ShapingHelper


def carrier_group(value):
    if type(value) is int:
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = tuple(value)
    else:
        raise ValueError('carrier must be an integer or a list/tuple of carrier integers')
    if not values or any(type(v) is not int or not 1 <= v <= 10 for v in values):
        raise ValueError('carriers must be integers 1..10')
    if len(set(values)) != len(values):
        raise ValueError('carrier groups must not contain duplicates')
    return values[0] if len(values) == 1 else values


def members(value):
    value = carrier_group(value)
    return (value,) if type(value) is int else value


class PlatedShapingHelper(ShapingHelper):
    """Original helper API, accepting int or ordered carrier groups.

    For example: cast_on_tubular_alt_tuck((2, 4)), knit_tubular_row((2, 4)).
    Singleton behavior is identical to ShapingHelper. The adapter also works
    with increase/decrease, flat mode and bind-off because they call the
    overridden knit/tuck/miss and carrier lifecycle methods.
    """
    def _group_text(self, carrier):
        return ' '.join(str(c) for c in members(carrier))

    def _validate_active_carrier(self, carrier):
        for c in members(carrier):
            if c not in self.active_carriers:
                raise ValueError(f'inactive carrier {c}')

    def inhook(self, carrier):
        group = carrier_group(carrier)
        carriers = members(group)
        if any(c in self.active_carriers for c in carriers):
            raise ValueError('cannot inhook an already active carrier')
        self.active_carriers.update(carriers)
        self.direction.setdefault(group, '-')
        self.instructions.append(f'inhook {self._group_text(group)}')

    def releasehook(self, carrier):
        self._validate_active_carrier(carrier)
        self.instructions.append(f'releasehook {self._group_text(carrier)}')

    def outhook(self, carrier):
        self._validate_active_carrier(carrier)
        for c in members(carrier):
            self.instructions.append(f'outhook {c}')
            self.active_carriers.remove(c)

    def _yarn_operation(self, op, direction, needle, carrier):
        self._validate_direction(direction)
        self._validate_active_carrier(carrier)
        self.instructions.append(f'{op} {direction} {needle} {self._group_text(carrier)}')

    def knit(self, direction, bed_needle, carrier):
        self._yarn_operation('knit', direction, bed_needle, carrier)

    def tuck(self, direction, bed_needle, carrier):
        self._yarn_operation('tuck', direction, bed_needle, carrier)

    def miss(self, direction, bed_needle, carrier):
        self._yarn_operation('miss', direction, bed_needle, carrier)

    plating_setup_courses = 2

    def start_tubular_carriers(self, carrier, courses_per_carrier=2):
        """Introduce each new carrier in order, knitting solo before plating.

        This can be called on empty needles for a direct-knit startup, or on
        existing fabric. A course is a full front/back round (two passes).
        Each hook is released before the next carrier is introduced.
        """
        if type(courses_per_carrier) is not int or courses_per_carrier < 1:
            raise ValueError('courses_per_carrier must be a positive integer')
        group = carrier_group(carrier)
        self.direction.setdefault(group, '-')
        extra = 0
        for c in members(group):
            if c not in self.active_carriers:
                self.inhook(c)
                for _ in range(courses_per_carrier):
                    self.knit_tubular_row(c)
                self.releasehook(c)
                extra += courses_per_carrier
        return extra

    def prep_tubular_colorwork(self, carriers):
        """Sequential solo setup for groups; preserve legacy singleton setup."""
        extra = 0
        for carrier in carriers:
            group = carrier_group(carrier)
            courses = self.plating_setup_courses if len(members(group)) > 1 else 1
            extra += self.start_tubular_carriers(group, courses_per_carrier=courses)
        return extra

    def retire_carriers(self, old, keep):
        """Remove only old members absent from the incoming carrier group."""
        departing = tuple(c for c in members(old) if c not in members(keep))
        if departing:
            self.outhook(departing)
