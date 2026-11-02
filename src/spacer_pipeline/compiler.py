"""Compile :class:`PanelPlan` geometry into spacer-fabric knitout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .engine import SpacerHelper
from .model import PanelPlan, RowPlan, Run


CarrierSpec = int | tuple[int, ...]


@dataclass(frozen=True)
class CompileConfig:
    front_carrier: CarrierSpec = (2, 4)
    back_carrier: CarrierSpec = (8, 10)
    filler_carrier: CarrierSpec = 7
    filler_pass_pairs: int = 3
    tuck_spacing: int = 4
    waste_rows: int = 6
    cast_off_rows: int = 4
    drop_repeats: int = 2
    multi_run_policy: str = "short-rows"

    def __post_init__(self) -> None:
        if self.filler_pass_pairs < 0:
            raise ValueError("filler_pass_pairs must be nonnegative")
        if not 1 <= self.tuck_spacing <= 5:
            raise ValueError("tuck_spacing must be in 1..5")
        if self.waste_rows < 5:
            raise ValueError("waste_rows must be at least 5")
        if self.cast_off_rows < 0:
            raise ValueError("cast_off_rows must be nonnegative")
        if self.drop_repeats < 1:
            raise ValueError("drop_repeats must be at least 1")
        if self.multi_run_policy not in {"short-rows", "error"}:
            raise ValueError("multi_run_policy must be 'short-rows' or 'error'")


@dataclass(frozen=True)
class CompileResult:
    output_path: Path
    knitout_lines: int
    ordinary_blocks: int
    short_row_groups: int
    short_row_levels: int
    step_changes: int
    coordinate_offset: int


def parse_carrier_spec(value: str) -> CarrierSpec:
    carriers = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not carriers:
        raise ValueError("carrier specification cannot be empty")
    if len(set(carriers)) != len(carriers):
        raise ValueError(f"duplicate carrier in {value!r}")
    return carriers[0] if len(carriers) == 1 else carriers


def _shift_row(row: RowPlan, offset: int) -> RowPlan:
    return RowPlan(tuple(Run(run.start + offset, run.end + offset) for run in row.runs))


def _split_continuing_run(
    rows: Sequence[RowPlan],
    start: int,
) -> tuple[list[RowPlan], list[Run] | None, int]:
    """Collect a split episode and infer its uniquely continuing run.

    A semantic region name is deliberately unnecessary. Starting with the
    first single run above the split, walk downward by overlap. If exactly one
    run in every split row overlaps that continuation, that run is the main
    fabric and the remaining runs are terminal short-row branches. Multiple
    matches mean there is no unique continuing run.
    """
    episode: list[RowPlan] = []
    index = start
    while index < len(rows) and len(rows[index].runs) > 1:
        episode.append(rows[index])
        index += 1

    if index >= len(rows) or len(rows[index].runs) != 1:
        return episode, None, index

    target = rows[index].runs[0]
    continuing_reversed: list[Run] = []
    for row in reversed(episode):
        matches = [run for run in row.runs if run.overlaps(target)]
        if len(matches) != 1:
            return episode, None, index
        target = matches[0]
        continuing_reversed.append(target)
    return episode, list(reversed(continuing_reversed)), index


def _knit_shaped_block(
    spacer: SpacerHelper,
    target: Run,
    config: CompileConfig,
    *,
    filler_pass_pairs: int | None = None,
) -> bool:
    """Move to ``target`` and knit one block; return whether it stepped."""
    if filler_pass_pairs is None:
        filler_pass_pairs = config.filler_pass_pairs
    left_delta = target.start - spacer.min_n
    right_delta = target.end - spacer.max_n
    gradual = abs(left_delta) <= 1 and abs(right_delta) <= 1

    if not gradual:
        spacer.comment(
            f"panel compiler: abrupt range {spacer.min_n}-{spacer.max_n} "
            f"-> {target.start}-{target.end}"
        )
        spacer.step_range(
            target.start,
            target.end,
            cast_off_rows=config.cast_off_rows,
        )
        spacer.knit_spacer_block(
            filler_pass_pairs=filler_pass_pairs,
            tuck_spacing=config.tuck_spacing,
        )
        return True

    increases: list[str] = []
    decreases: list[str] = []
    if left_delta == -1:
        increases.append("left")
    elif left_delta == 1:
        decreases.append("left")
    if right_delta == 1:
        increases.append("right")
    elif right_delta == -1:
        decreases.append("right")

    # Increases must precede face rows. Calling them here permits a block to
    # increase one edge and decrease the other, which translates an asymmetric
    # image row without weakening the spacer sequencing rules.
    for side in increases:
        spacer.increase_edge(side)
    spacer.knit_spacer_block(
        filler_pass_pairs=filler_pass_pairs,
        tuck_spacing=config.tuck_spacing,
        decrease_sides=tuple(decreases),
    )
    return False


def _next_abrupt_transition_casts_off(current: Run, target: Run) -> bool:
    """Return whether ``current -> target`` steps and loses live needles."""
    left_delta = target.start - current.start
    right_delta = target.end - current.end
    abrupt = abs(left_delta) > 1 or abs(right_delta) > 1
    loses_needles = target.start > current.start or target.end < current.end
    return abrupt and loses_needles


def _trailing_filler_pairs(
    spacer: SpacerHelper,
    current: Run,
    next_row: RowPlan | None,
    config: CompileConfig,
) -> int:
    """Suppress filler tucks immediately before an abrupt cast-off.

    The following step transfers outgoing back-bed loops onto the front bed.
    Ending the outgoing width with face rows ensures those transfers see
    knitted face loops rather than fresh, unknitted filler tucks.
    """
    if (
        config.cast_off_rows > 0
        and next_row is not None
        and len(next_row.runs) == 1
        and _next_abrupt_transition_casts_off(current, next_row.runs[0])
    ):
        target = next_row.runs[0]
        spacer.comment(
            "panel compiler: omit trailing filler before abrupt cast-off "
            f"{current.start}-{current.end} -> {target.start}-{target.end}; "
            "end outgoing width on face rows"
        )
        return 0
    return config.filler_pass_pairs


def compile_panel_plan(
    plan: PanelPlan,
    output_path: str | Path,
    config: CompileConfig | None = None,
) -> CompileResult:
    """Compile a gauge-resolved panel plan to a knitout ``.k`` file.

    Single-run rows are ordinary spacer blocks. Edge movement of at most one
    logical stitch per side is shaped gradually; larger changes use an exact
    range step with the engine's cast-on/cast-off treatment.

    Consecutive multi-run rows are interpreted as nested short-row levels over
    the current connected base. They do not replace or split the active base
    range. This is intentionally distinct from independent-island knitting.
    """
    config = config or CompileConfig()
    if not plan.rows or len(plan.rows[0].runs) != 1:
        raise ValueError("the first plan row must contain exactly one connected run")

    # Normalize the plan's leftmost coordinate to logical needle 1 while
    # preserving all relative placement information.
    coordinate_offset = 1 - plan.min_needle
    rows = tuple(_shift_row(row, coordinate_offset) for row in plan.rows)
    first_run = rows[0].runs[0]
    if first_run.width < 4:
        raise ValueError("initial spacer width must be at least four stitches")

    spacer = SpacerHelper(
        width=first_run.width,
        front_carrier=config.front_carrier,
        back_carrier=config.back_carrier,
        filler_carrier=config.filler_carrier,
        drop_repeats=config.drop_repeats,
    )
    spacer.min_n = first_run.start
    spacer.max_n = first_run.end
    spacer.standard_headers()
    spacer.comment(
        f"panel plan: {len(rows)} row specification(s), coordinate offset "
        f"{coordinate_offset:+d}"
    )
    spacer.cast_on_spacer(waste_rows=config.waste_rows)

    ordinary_blocks = 0
    short_row_groups = 0
    short_row_levels = 0
    step_changes = 0

    spacer.knit_spacer_block(
        filler_pass_pairs=_trailing_filler_pairs(
            spacer,
            first_run,
            rows[1] if len(rows) > 1 else None,
            config,
        ),
        tuck_spacing=config.tuck_spacing,
    )
    ordinary_blocks += 1

    index = 1
    while index < len(rows):
        row = rows[index]
        if not row.runs:
            raise ValueError(f"row {index} has no active runs")

        if len(row.runs) == 1:
            if _knit_shaped_block(
                spacer,
                row.runs[0],
                config,
                filler_pass_pairs=_trailing_filler_pairs(
                    spacer,
                    row.runs[0],
                    rows[index + 1] if index + 1 < len(rows) else None,
                    config,
                ),
            ):
                step_changes += 1
            ordinary_blocks += 1
            index += 1
            continue

        if config.multi_run_policy == "error":
            raise ValueError(
                f"row {index} has {len(row.runs)} runs; "
                "enable the short-rows policy to compile it"
            )

        episode, continuing, next_index = _split_continuing_run(rows, index)
        short_levels: list[RowPlan] = []
        for relative_index, level in enumerate(episode):
            main_run = None if continuing is None else continuing[relative_index]
            short_runs = tuple(run for run in level.runs if run != main_run)
            short_levels.append(RowPlan(short_runs))
            for run in short_runs:
                if run.start < spacer.min_n or run.end > spacer.max_n:
                    raise ValueError(
                        f"row {index + relative_index} short-row run "
                        f"{run.start}-{run.end} "
                        f"extends outside connected base {spacer.min_n}-{spacer.max_n}"
                    )

        if continuing is not None:
            spacer.comment(
                "panel compiler: inferred anonymous continuing component "
                f"through {len(continuing)} split row(s): "
                + ", ".join(f"{run.start}-{run.end}" for run in continuing)
            )

        spacer.knit_spacer_short_rows(
            [[(run.start, run.end) for run in level.runs] for level in short_levels],
            filler_pass_pairs=config.filler_pass_pairs,
            tuck_spacing=config.tuck_spacing,
            continuation=(continuing[0].start, continuing[0].end)
            if continuing is not None
            else None,
        )
        short_row_groups += 1
        short_row_levels += len(episode)

        if continuing is not None:
            spacer.comment(
                f"panel compiler: continue main component at "
                f"{continuing[0].start}-{continuing[0].end}; "
                "drop terminal short-row loops without finish treatment"
            )
            spacer.step_range(
                continuing[0].start,
                continuing[0].end,
                cast_off_rows=0,
            )
            for relative_index, main_run in enumerate(continuing):
                if relative_index + 1 < len(continuing):
                    next_row = RowPlan((continuing[relative_index + 1],))
                else:
                    next_row = rows[next_index] if next_index < len(rows) else None
                if _knit_shaped_block(
                    spacer,
                    main_run,
                    config,
                    filler_pass_pairs=_trailing_filler_pairs(
                        spacer, main_run, next_row, config
                    ),
                ):
                    step_changes += 1
                ordinary_blocks += 1
        index = next_index

    spacer.finish_spacer(waste_rows=config.waste_rows)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output = spacer.write(destination)
    return CompileResult(
        output_path=destination,
        knitout_lines=len(output.splitlines()),
        ordinary_blocks=ordinary_blocks,
        short_row_groups=short_row_groups,
        short_row_levels=short_row_levels,
        step_changes=step_changes,
        coordinate_offset=coordinate_offset,
    )
