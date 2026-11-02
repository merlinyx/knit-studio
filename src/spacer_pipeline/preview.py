"""ASCII and PNG previews for panel plans."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .model import PanelPlan


def ascii_preview(plan: PanelPlan, active: str = "█", inactive: str = "·") -> str:
    lines: list[str] = []
    for row in reversed(plan.rows):
        lines.append(
            "".join(
                active if row.contains(needle) else inactive
                for needle in range(plan.min_needle, plan.max_needle + 1)
            )
        )
    return "\n".join(lines)


def save_preview(plan: PanelPlan, path: str | Path, cell_size: int = 12) -> Path:
    if cell_size < 2:
        raise ValueError("cell_size must be at least 2")
    margin = 28
    width = plan.grid_width * cell_size + 2 * margin
    height = len(plan.rows) * cell_size + 2 * margin
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    for display_y, row_index in enumerate(reversed(range(len(plan.rows)))):
        row = plan.rows[row_index]
        previous = plan.rows[row_index - 1] if row_index > 0 else None
        for needle in range(plan.min_needle, plan.max_needle + 1):
            x0 = margin + (needle - plan.min_needle) * cell_size
            y0 = margin + display_y * cell_size
            box = (x0, y0, x0 + cell_size - 1, y0 + cell_size - 1)
            if row.contains(needle):
                newly_active = previous is not None and not previous.contains(needle)
                color = "#e58a2b" if newly_active else "#264653"
                draw.rectangle(box, fill=color, outline="#ffffff")
            else:
                draw.rectangle(box, fill="#f5f5f2", outline="#ddddda")

    draw.text((margin, 7), "top", fill="#333333")
    draw.text((margin, height - 20), "cast-on / bottom", fill="#333333")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination)
    return destination

