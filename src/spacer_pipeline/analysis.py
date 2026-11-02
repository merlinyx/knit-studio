"""Topology and manufacturability diagnostics for row/run plans."""

from __future__ import annotations

from dataclasses import dataclass

from .model import PanelPlan, RowPlan, Run


@dataclass(frozen=True)
class PlanEvent:
    row: int
    kind: str
    message: str
    severity: str = "info"


def _covered_width(run: Run, row: RowPlan) -> int:
    return sum(run.intersection_width(previous) for previous in row.runs)


def _needles(row: RowPlan) -> set[int]:
    return {
        needle
        for run in row.runs
        for needle in range(run.start, run.end + 1)
    }


def analyze_plan(plan: PanelPlan) -> list[PlanEvent]:
    """Describe splits, merges, new islands, and abrupt edge additions.

    This intentionally does not decide how to knit the events. In particular,
    disconnected runs are reported as requiring an independent cast-on rather
    than being silently interpreted as short rows.
    """

    events: list[PlanEvent] = []
    first = plan.rows[0]
    if not first.runs:
        events.append(PlanEvent(0, "empty", "cast-on row is empty", "error"))
    else:
        events.append(
            PlanEvent(
                0,
                "cast_on",
                f"initial cast-on for {len(first.runs)} run(s), "
                f"{first.stitch_count} stitches total",
            )
        )

    ever_active = _needles(first)
    for index in range(1, len(plan.rows)):
        previous = plan.rows[index - 1]
        current = plan.rows[index]
        previous_needles = _needles(previous)
        current_needles = _needles(current)
        newly_worked = current_needles - previous_needles
        returning = newly_worked & ever_active
        never_active = newly_worked - ever_active

        if not current.runs:
            events.append(PlanEvent(index, "empty", "row has no active runs", "warning"))
            continue

        connected_pairs = [
            (old, new)
            for old in previous.runs
            for new in current.runs
            if old.overlaps(new)
        ]
        if previous.runs and not connected_pairs and never_active:
            events.append(
                PlanEvent(
                    index,
                    "disconnected_row",
                    "no run overlaps the preceding row; independent cast-on required",
                    "warning",
                )
            )

        for run in current.runs:
            overlap = _covered_width(run, previous)
            run_needles = set(range(run.start, run.end + 1))
            run_new = run_needles & never_active
            run_returning = run_needles & returning
            if overlap == 0 and run_new:
                events.append(
                    PlanEvent(
                        index,
                        "new_island",
                        f"run {run.start}-{run.end} starts without vertical connection; "
                        "independent cast-on required",
                        "warning",
                    )
                )
            elif overlap == 0 and run_returning:
                events.append(
                    PlanEvent(
                        index,
                        "resumed_island",
                        f"run {run.start}-{run.end} resumes previously active needles; "
                        "the loop-holding policy remains to be chosen",
                    )
                )
            if len(run_new) > 2:
                events.append(
                    PlanEvent(
                        index,
                        "abrupt_addition",
                        f"run {run.start}-{run.end} introduces {len(run_new)} "
                        "new stitches beyond the preceding row; use an explicit "
                        "edge cast-on/step",
                    )
                )

        if returning:
            events.append(
                PlanEvent(
                    index,
                    "resume_held",
                    f"{len(returning)} previously active stitch(es) resume after a gap; "
                    "the pipeline preserves this without assigning short rows",
                )
            )

        for run in previous.runs:
            if _covered_width(run, current) == 0:
                events.append(
                    PlanEvent(
                        index,
                        "ended_island",
                        f"preceding run {run.start}-{run.end} ends before this row",
                    )
                )

        if len(current.runs) > len(previous.runs) and connected_pairs:
            events.append(
                PlanEvent(index, "split", "one connected region splits into multiple runs")
            )
        elif len(current.runs) < len(previous.runs) and connected_pairs:
            events.append(
                PlanEvent(index, "merge", "multiple runs reconnect into fewer regions")
            )

        ever_active.update(current_needles)

    return events
