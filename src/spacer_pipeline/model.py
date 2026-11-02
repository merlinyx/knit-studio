"""Core row/run representation.

Rows are stored in knitting order: index 0 is the bottom/cast-on row.
Run endpoints are inclusive logical needle indices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, order=True)
class Run:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"run end {self.end} is before start {self.start}")

    @property
    def width(self) -> int:
        return self.end - self.start + 1

    def overlaps(self, other: "Run") -> bool:
        return max(self.start, other.start) <= min(self.end, other.end)

    def intersection_width(self, other: "Run") -> int:
        if not self.overlaps(other):
            return 0
        return min(self.end, other.end) - max(self.start, other.start) + 1

    def to_list(self) -> list[int]:
        return [self.start, self.end]


@dataclass(frozen=True)
class RowPlan:
    runs: tuple[Run, ...]

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.runs))
        if ordered != self.runs:
            raise ValueError("runs must be ordered from left to right")
        for left, right in zip(ordered, ordered[1:]):
            if left.end + 1 >= right.start:
                raise ValueError(
                    "runs must be separated by at least one inactive stitch; "
                    f"merge {left.start}-{left.end} and {right.start}-{right.end}"
                )

    @property
    def stitch_count(self) -> int:
        return sum(run.width for run in self.runs)

    @property
    def span(self) -> Run | None:
        if not self.runs:
            return None
        return Run(self.runs[0].start, self.runs[-1].end)

    def contains(self, needle: int) -> bool:
        return any(run.start <= needle <= run.end for run in self.runs)

    def to_list(self) -> list[list[int]]:
        return [run.to_list() for run in self.runs]


@dataclass(frozen=True)
class PanelPlan:
    rows: tuple[RowPlan, ...]
    stitch_gauge: float = 9.5
    row_gauge: float = 13.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("a panel plan needs at least one row")
        if self.stitch_gauge <= 0 or self.row_gauge <= 0:
            raise ValueError("gauges must be positive")

    @property
    def min_needle(self) -> int:
        starts = [run.start for row in self.rows for run in row.runs]
        if not starts:
            raise ValueError("panel plan contains no active stitches")
        return min(starts)

    @property
    def max_needle(self) -> int:
        ends = [run.end for row in self.rows for run in row.runs]
        if not ends:
            raise ValueError("panel plan contains no active stitches")
        return max(ends)

    @property
    def grid_width(self) -> int:
        return self.max_needle - self.min_needle + 1

    @property
    def nominal_width_inches(self) -> float:
        return self.grid_width / self.stitch_gauge

    @property
    def nominal_height_inches(self) -> float:
        return len(self.rows) / self.row_gauge

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "spacer-panel-plan-v1",
            "row_order": "bottom-to-top",
            "run_endpoints": "inclusive",
            "gauge": {
                "stitches_per_inch": self.stitch_gauge,
                "spacer_blocks_per_inch": self.row_gauge,
            },
            "rows": [row.to_list() for row in self.rows],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PanelPlan":
        gauge = data.get("gauge", {})
        rows = tuple(
            RowPlan(tuple(Run(int(a), int(b)) for a, b in row))
            for row in data["rows"]
        )
        return cls(
            rows=rows,
            stitch_gauge=float(gauge.get("stitches_per_inch", 9.5)),
            row_gauge=float(gauge.get("spacer_blocks_per_inch", 13.0)),
            metadata=dict(data.get("metadata", {})),
        )

    def write_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return destination

    @classmethod
    def read_json(cls, path: str | Path) -> "PanelPlan":
        return cls.from_dict(json.loads(Path(path).read_text()))


def row_from_runs(runs: Iterable[tuple[int, int] | Run]) -> RowPlan:
    normalized = tuple(
        run if isinstance(run, Run) else Run(int(run[0]), int(run[1]))
        for run in runs
    )
    return RowPlan(tuple(sorted(normalized)))

