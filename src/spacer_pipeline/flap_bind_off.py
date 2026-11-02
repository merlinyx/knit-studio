"""Sizing and construction of a front-bed flap joined onto a tube's back bed."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class FlapBindOffConfig:
    n: int | None = None
    flap_width: int | None = None
    flap_rows: int | None = None
    stitch_gauge: float | None = None
    row_gauge: float | None = None
    has_tag: bool = True


def resolve_flap(min_n, max_n, config):
    """Resolve logical inclusive endpoints; physical gauge is already in S.

    S = measured stitches/inch at the actual needle spacing, R = flat flap
    rows/inch. Each side opening contains both front and back live stitches.
    """
    if not isinstance(config, FlapBindOffConfig):
        config = FlapBindOffConfig(**config)
    size = max_n-min_n+1
    if size < 4:
        raise ValueError('flap bind-off requires at least four needles per bed')
    for name in ('n', 'flap_width', 'flap_rows'):
        value = getattr(config, name)
        if value is not None and type(value) is not int:
            raise ValueError(f'{name} must be an integer')
    if type(config.has_tag) is not bool:
        raise ValueError('has_tag must be boolean')
    s, r = config.stitch_gauge, config.row_gauge
    for name, value in (('stitch_gauge', s), ('row_gauge', r)):
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError(f'{name} must be finite and positive')
    calibrated = s is not None and r is not None
    width, rows, n = config.flap_width, config.flap_rows, config.n
    if rows is not None and (rows < 2 or rows % 2):
        raise ValueError('flap_rows must be a positive even number (at least 2)')
    if n is not None and not min_n+2 <= n < max_n:
        raise ValueError('n must leave room for a two-stitch flap and a live stitch on both sides')
    if width is None:
        if rows is not None:
            if not calibrated:
                raise ValueError('automatic width from rows requires stitch_gauge and row_gauge')
            target_side = rows*s/(2*r)
            target_width = size-2*target_side if n is None else n-min_n-target_side+1
        elif n is not None:
            target_width = n-min_n-(max_n-n)+1
        else:
            target_width = size/2  # square + matching side openings => W = N/2
        upper = size-2 if n is None else n-min_n
        candidates = list(range(2, upper+1))
        if n is None:
            balanced = [w for w in candidates if (size-w)%2 == 0]
            candidates = balanced or candidates
        width = min(candidates, key=lambda w: (abs(w-target_width), -w))
    if not 2 <= width <= size-2:
        raise ValueError('flap_width must be 2..(needles per bed - 2)')
    if n is None:
        low = min_n + (size-width)//2
        n = low+width-1
    else:
        low = n-width+1
    if low <= min_n or n >= max_n:
        raise ValueError('flap must leave at least one live needle on each side')
    left, right = low-min_n, max_n-n
    if rows is None:
        if not calibrated:
            raise ValueError('automatic flap rows require stitch_gauge and row_gauge')
        target = (left+right)*r/s
        # Nearest positive even row count, with deterministic upward ties.
        rows = max(2, 2*math.floor(target/2+0.5))
    result = dict(n=n, flap_start=low, flap_width=width, flap_rows=rows,
                  left_stitches=2*left, right_stitches=2*right, has_tag=config.has_tag)
    if calibrated:
        height = rows/r
        result.update(width_inches=width/s, height_inches=height,
                      left_opening_inches=2*left/s, right_opening_inches=2*right/s,
                      left_fit_error_inches=height-2*left/s,
                      right_fit_error_inches=height-2*right/s,
                      square_error_inches=height-width/s)
    return result


def _front_chain(sh, carrier, high, low):
    for n in range(high, low, -1):
        sh.knit('-', sh._loc('f', n, sh.gauge), carrier)
        sh.miss('-', sh._loc('f', n-1, sh.gauge), carrier)
        sh.xfer(sh._loc('f', n, sh.gauge), f'b{n*sh.gauge}')
        sh.rack(-sh.gauge)
        sh.xfer(f'b{n*sh.gauge}', sh._loc('f', n-1, sh.gauge))
        sh.rack(0)


def bind_off_flap(sh, carrier, config):
    """Partial chain, even flat passes, back-bed join, securing row, chain."""
    if not sh.is_tubular:
        raise ValueError('flap bind-off requires tubular mode')
    if sh.side_slack:
        raise ValueError('flap bind-off currently requires side_slack=False')
    layout = resolve_flap(sh.min_n, sh.max_n, config)
    sh._validate_active_carrier(carrier)
    if sh.direction[carrier] != '-':
        raise ValueError("flap bind-off requires next tubular direction '-' (carrier on right)")
    if sh.racking != 0:
        raise ValueError('flap bind-off must start at rack 0')
    if sh.gauge not in (2, 3, 4) or sh.MAX_RACK < sh.gauge:
        raise ValueError('unsupported needle spacing or rack limit')
    lo, hi, n, start = sh.min_n, sh.max_n, layout['n'], layout['flap_start']
    sh.comment(f'flap bind-off: f{start}..f{n} logical; {layout["flap_rows"]} flat passes')
    sh.comment('flap stage 1: partial front chain to n')
    _front_chain(sh, carrier, hi, n)
    sh.comment('flap stage 2: even back-and-forth front passes')
    for row in range(layout['flap_rows']):
        direction = '-' if row % 2 == 0 else '+'
        needles = range(n, start-1, -1) if direction == '-' else range(start, n+1)
        for needle in needles:
            sh.knit(direction, sh._loc('f', needle, sh.gauge), carrier)
    sh.comment('flap stage 3: front to left edge, back to right edge')
    for needle in range(n, lo-1, -1):
        sh.knit('-', sh._loc('f', needle, sh.gauge), carrier)
    for needle in range(lo, start): # this should be before the patch
        sh.knit('+', sh._loc('b', needle, sh.gauge), carrier)
    sh.comment('flap stage 4: join front flap edge onto occupied back needles')
    sh.rack(-1)  # f(g*n) aligns with b(g*n+1), for any supported gauge
    sh.xfer_pass([(sh._loc('f', needle, sh.gauge), sh._loc('b', needle, sh.gauge))
                  for needle in range(start, n+1)])
    sh.rack(0)
    sh.drop_vacated(sh._loc('f', needle, sh.gauge) for needle in range(start, n+1))
    sh.comment('flap stage 5: securing back pass and remaining front pass')
    for needle in range(start, hi+1):
        sh.knit('+', sh._loc('b', needle, sh.gauge), carrier)
    for needle in range(hi, lo-1, -1):
        sh.knit('-', sh._loc('b', needle, sh.gauge), carrier)
    for needle in range(lo, start):
        sh.knit('+', sh._loc('f', needle, sh.gauge), carrier)
    sh.comment('flap stage 6: resume chain on remaining front, then entire back')
    _front_chain(sh, carrier, start-1, lo)
    sh.knit('-', sh._loc('f', lo, sh.gauge), carrier)
    sh.tuck('-', sh._loc('f', lo-1, sh.gauge), carrier)
    sh.rack(-1)
    sh.xfer(sh._loc('f', lo, sh.gauge), sh._loc('b', lo, sh.gauge))
    sh.rack(0)
    for needle in range(lo, hi):
        sh.knit('+', sh._loc('b', needle, sh.gauge), carrier)
        sh.miss('+', sh._loc('b', needle+1, sh.gauge), carrier)
        sh.xfer(sh._loc('b', needle, sh.gauge), f'f{needle*sh.gauge+1}')
        sh.rack(-sh.gauge)
        sh.xfer(f'f{needle*sh.gauge+1}', sh._loc('b', needle+1, sh.gauge))
        sh.rack(0)
    if not layout['has_tag']:
        sh.knit('+', sh._loc('b', hi, sh.gauge), carrier)
    sh._finish_tubular_bind_off(carrier, layout['has_tag'])
    return layout
