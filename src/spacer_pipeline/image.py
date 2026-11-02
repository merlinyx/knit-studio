"""Convert filled silhouettes or closed outline images into panel plans."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import math

from PIL import Image

from .model import PanelPlan, RowPlan, Run


Mask = list[list[bool]]


def _is_gradual_increase(previous: RowPlan, current: RowPlan) -> bool:
    """Match the one-stitch edge increases used by the knit compiler."""
    if len(previous.runs) != 1 or len(current.runs) != 1:
        return False
    old, new = previous.runs[0], current.runs[0]
    left_delta = new.start - old.start
    right_delta = new.end - old.end
    return (
        abs(left_delta) <= 1
        and abs(right_delta) <= 1
        and (left_delta == -1 or right_delta == 1)
    )


def align_gradual_increase_rows(
    rows: tuple[RowPlan, ...],
) -> tuple[tuple[RowPlan, ...], list[dict[str, int | str]]]:
    """Move gradual increases onto even, front-face-first rows.

    An increase on an odd row is advanced one row when a holding row exists.
    Adjacent events are handled in the opposite direction: the old width is
    held for one extra row and the increase is delayed. Rasterization normally
    supplies a repeated row that can absorb this shift, so total height is
    preserved. If it does not, one holding row is inserted as a safe fallback.
    """
    adjusted = list(rows)
    changes: list[dict[str, int | str]] = []
    index = 1

    while index < len(adjusted):
        if not _is_gradual_increase(adjusted[index - 1], adjusted[index]):
            index += 1
            continue

        event_index = index
        if event_index % 2 == 1:
            if (
                event_index >= 2
                and adjusted[event_index - 1] == adjusted[event_index - 2]
            ):
                adjusted[event_index - 1] = adjusted[event_index]
                changes.append(
                    {
                        "from_row": event_index,
                        "to_row": event_index - 1,
                        "placement": "before",
                    }
                )
                event_index -= 1
            elif (
                event_index + 1 < len(adjusted)
                and adjusted[event_index + 1] == adjusted[event_index]
            ):
                adjusted[event_index] = adjusted[event_index - 1]
                changes.append(
                    {
                        "from_row": event_index,
                        "to_row": event_index + 1,
                        "placement": "after",
                    }
                )
                event_index += 1
            else:
                adjusted.insert(event_index, adjusted[event_index - 1])
                changes.append(
                    {
                        "from_row": event_index,
                        "to_row": event_index + 1,
                        "placement": "after_inserted_hold",
                    }
                )
                event_index += 1

        index = event_index + 1

    return tuple(adjusted), changes


def _crop(mask: Mask) -> Mask:
    active = [
        (x, y)
        for y, row in enumerate(mask)
        for x, value in enumerate(row)
        if value
    ]
    if not active:
        raise ValueError("image contains no material pixels after thresholding")
    xs, ys = zip(*active)
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    return [row[left : right + 1] for row in mask[top : bottom + 1]]


def _fill_closed_outline(boundary: Mask) -> Mask:
    """Fill all pixels not reachable from the image border."""

    height = len(boundary)
    width = len(boundary[0])
    exterior = [[False] * width for _ in range(height)]
    queue: deque[tuple[int, int]] = deque()

    def add(x: int, y: int) -> None:
        if 0 <= x < width and 0 <= y < height and not boundary[y][x] and not exterior[y][x]:
            exterior[y][x] = True
            queue.append((x, y))

    for x in range(width):
        add(x, 0)
        add(x, height - 1)
    for y in range(height):
        add(0, y)
        add(width - 1, y)

    while queue:
        x, y = queue.popleft()
        add(x - 1, y)
        add(x + 1, y)
        add(x, y - 1)
        add(x, y + 1)

    return [
        [boundary[y][x] or not exterior[y][x] for x in range(width)]
        for y in range(height)
    ]


def load_mask(
    path: str | Path,
    *,
    threshold: int = 128,
    invert: bool = False,
    fill_outline: bool = False,
    crop: bool = True,
) -> Mask:
    image = Image.open(path).convert("L")
    pixels = list(image.tobytes())
    material = [value < threshold for value in pixels]
    if invert:
        material = [not value for value in material]
    mask = [
        material[y * image.width : (y + 1) * image.width]
        for y in range(image.height)
    ]
    if fill_outline:
        mask = _fill_closed_outline(mask)
    return _crop(mask) if crop else mask


def resize_mask(mask: Mask, columns: int, rows: int, coverage: float = 0.5) -> Mask:
    if columns < 1 or rows < 1:
        raise ValueError("target grid dimensions must be positive")
    if not 0 < coverage <= 1:
        raise ValueError("coverage must be in (0, 1]")

    height = len(mask)
    width = len(mask[0])
    image = Image.new("L", (width, height))
    image.putdata([255 if value else 0 for row in mask for value in row])
    resized = image.resize((columns, rows), resample=Image.Resampling.BOX)
    cutoff = round(255 * coverage)
    values = list(resized.tobytes())
    return [
        [values[y * columns + x] >= cutoff for x in range(columns)]
        for y in range(rows)
    ]


def _runs_from_mask_row(row: list[bool], needle_offset: int = 0) -> RowPlan:
    runs: list[Run] = []
    start: int | None = None
    for x, value in enumerate(row + [False]):
        if value and start is None:
            start = x
        elif not value and start is not None:
            runs.append(Run(start + needle_offset, x - 1 + needle_offset))
            start = None
    return RowPlan(tuple(runs))


def mask_to_plan(
    mask: Mask,
    *,
    stitch_gauge: float = 9.5,
    row_gauge: float = 13.0,
    needle_offset: int = 0,
    bottom_up: bool = True,
    align_increase_rows: bool = True,
    metadata: dict | None = None,
) -> PanelPlan:
    source_rows = reversed(mask) if bottom_up else iter(mask)
    rows = tuple(_runs_from_mask_row(row, needle_offset) for row in source_rows)
    plan_metadata = dict(metadata or {})
    if align_increase_rows:
        rows, adjustments = align_gradual_increase_rows(rows)
        plan_metadata["increase_row_parity"] = {
            "enabled": True,
            "rule": "gradual increases use even, front-face-first row indices",
            "row_indexing": "zero-based, bottom-to-top",
            "adjustments": adjustments,
        }
    return PanelPlan(
        rows,
        stitch_gauge=stitch_gauge,
        row_gauge=row_gauge,
        metadata=plan_metadata,
    )


def image_to_plan(
    path: str | Path,
    *,
    width_inches: float | None = None,
    height_inches: float | None = None,
    stitch_gauge: float = 9.5,
    row_gauge: float = 13.0,
    threshold: int = 128,
    invert: bool = False,
    fill_outline: bool = False,
    coverage: float = 0.5,
    needle_offset: int = 0,
    align_increase_rows: bool | None = None,
    input_mode: str = "dimensions",
) -> PanelPlan:
    if input_mode not in ("dimensions", "stitch-pixels"):
        raise ValueError("input_mode must be dimensions or stitch-pixels")
    pixels = input_mode == "stitch-pixels"
    if pixels and (width_inches is not None or height_inches is not None):
        raise ValueError("stitch-pixels mode does not accept physical dimensions")
    if pixels and align_increase_rows:
        raise ValueError("stitch-pixels mode preserves rows; increase-row alignment must be disabled")
    if not pixels and any(v is None or not math.isfinite(v) or v <= 0 for v in (width_inches, height_inches)):
        raise ValueError("dimensions mode requires positive width_inches and height_inches")
    if align_increase_rows is None:
        align_increase_rows = not pixels
    mask = load_mask(
        path,
        threshold=threshold,
        invert=invert,
        fill_outline=fill_outline,
        crop=not pixels,
    )
    if not any(any(row) for row in mask):
        raise ValueError("image contains no material pixels after thresholding")
    columns = len(mask[0]) if pixels else max(1, round(width_inches * stitch_gauge))
    rows = len(mask) if pixels else max(1, round(height_inches * row_gauge))
    resized = mask if pixels else resize_mask(mask, columns, rows, coverage=coverage)
    return mask_to_plan(
        resized,
        stitch_gauge=stitch_gauge,
        row_gauge=row_gauge,
        needle_offset=needle_offset,
        align_increase_rows=align_increase_rows,
        metadata={
            "source": str(path),
            "source_type": "image",
            "input_mode": input_mode,
            "source_grid": {"columns": len(mask[0]), "rows": len(mask)},
            "pixel_row_unit": "spacer block" if pixels else None,
            "requested_width_inches": width_inches,
            "requested_height_inches": height_inches,
            "threshold": threshold,
            "fill_outline": fill_outline,
            "coverage": coverage,
        },
    )
