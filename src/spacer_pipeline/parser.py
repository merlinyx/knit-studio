"""Parser for compact run-per-row notation such as ``0-1, 7-8``."""

from __future__ import annotations

from pathlib import Path
import re

from .model import PanelPlan, RowPlan, Run


RUN_RE = re.compile(r"^(-?\d+)\s*(?:-\s*(-?\d+))?$")


def parse_run_line(line: str, line_number: int | None = None) -> RowPlan:
    content = line.split("#", 1)[0].strip()
    if not content:
        return RowPlan(())

    runs: list[Run] = []
    for token in content.split(","):
        token = token.strip()
        match = RUN_RE.match(token)
        if not match:
            location = f" on line {line_number}" if line_number else ""
            raise ValueError(f"invalid run {token!r}{location}")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) is not None else start
        runs.append(Run(start, end))
    return RowPlan(tuple(sorted(runs)))


def parse_run_text(
    text: str,
    *,
    stitch_gauge: float = 9.5,
    row_gauge: float = 13.0,
    metadata: dict | None = None,
) -> PanelPlan:
    rows: list[RowPlan] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        rows.append(parse_run_line(line, line_number))
    return PanelPlan(
        tuple(rows),
        stitch_gauge=stitch_gauge,
        row_gauge=row_gauge,
        metadata=metadata or {},
    )


def parse_run_file(
    path: str | Path,
    *,
    stitch_gauge: float = 9.5,
    row_gauge: float = 13.0,
) -> PanelPlan:
    source = Path(path)
    return parse_run_text(
        source.read_text(),
        stitch_gauge=stitch_gauge,
        row_gauge=row_gauge,
        metadata={"source": str(source), "source_type": "run-text"},
    )

