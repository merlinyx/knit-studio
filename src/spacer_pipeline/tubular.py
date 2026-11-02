"""Swept-profile design sampling, hole specifications and indexed HTML preview."""
from __future__ import annotations

import base64
import html
import json
import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .image import load_mask, resize_mask


@dataclass(frozen=True)
class Hole:
    """Inclusive one-based logical needles on one bed; courses start at 1."""
    start_course: int
    gaps: tuple[tuple[int, int], ...]
    bed: str = "f"


def with_holes(plan, holes):
    """Return a validated copy with the supplied hole overlays."""
    if plan.get("format") != "tubular-design-plan-v3":
        raise ValueError("expected tubular-design-plan-v3; regenerate older plans")
    result = deepcopy(plan)
    courses = result["courses"]
    normalized_holes = []
    occupied = set()
    for hole in holes:
        if isinstance(hole, Hole):
            hole = dict(start_course=hole.start_course, gaps=hole.gaps, bed=hole.bed)
        bed = hole.get("bed", "f")
        if bed not in ("f", "b"):
            raise ValueError("hole bed must be f or b")
        start = hole["start_course"]
        gaps = hole["gaps"]
        if type(start) is not int or not gaps or start < 2 or start + len(gaps) > len(courses):
            raise ValueError("hole needs complete courses below and above it")
        for offset, gap in enumerate(gaps):
            if len(gap) != 2 or any(type(v) is not int for v in gap):
                raise ValueError("hole intervals require two integer endpoints")
            a, b = gap
            row = courses[start + offset - 1]
            lo, hi = row["bed_runs"][bed]
            if not lo < a <= b < hi:
                raise ValueError("hole must leave live stitches on both sides within one bed")
            cells = {(start + offset, bed, n) for n in range(a, b + 1)}
            if cells & occupied:
                raise ValueError("holes overlap")
            occupied |= cells
        normalized_holes.append(dict(start_course=start, bed=bed, gaps=[list(g) for g in gaps]))
    result["holes"] = normalized_holes
    return result


def tubular_plan(path, *, diameter_inches=None, height_inches=None, stitch_gauge=9.5,
                 course_gauge=13.0, sections=(), holes=(), input_mode="dimensions"):
    if input_mode not in ("dimensions", "stitch-pixels"):
        raise ValueError("input_mode must be dimensions or stitch-pixels")
    pixels = input_mode == "stitch-pixels"
    if pixels and (diameter_inches is not None or height_inches is not None):
        raise ValueError("stitch-pixels mode does not accept physical dimensions")
    values = (stitch_gauge, course_gauge) if pixels else (diameter_inches, height_inches, stitch_gauge, course_gauge)
    if any(v is None or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("dimensions and gauges must be finite and positive")
    mask = load_mask(path, crop=not pixels)
    samples = mask if pixels else resize_mask(mask, len(mask[0]), max(1, round(height_inches * course_gauge)))
    courses = []
    for index, row in enumerate(reversed(samples)):
        active = [i for i, value in enumerate(row) if value]
        if not active or active != list(range(active[0], active[-1] + 1)):
            raise ValueError(f"course {index + 1}: expected one filled profile run")
        if pixels:
            count = 2 * len(active)
            diameter = count / (math.pi * stitch_gauge)
        else:
            diameter = len(active) / len(row) * diameter_inches
            count = max(4, 2 * round(math.pi * diameter * stitch_gauge / 2))
        courses.append(dict(course=index + 1, stitches=count, front_stitches=count // 2,
                            diameter_inches=diameter, section="body"))
    if pixels:
        diameter_inches = max(row["diameter_inches"] for row in courses)
        height_inches = len(courses) / course_gauge
    used = set()
    normalized_sections = []
    for section in sections:
        name, start, end = section["name"], section["start_course"], section["end_course"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("section names must be nonempty strings")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(courses):
            raise ValueError("section course range is invalid")
        indices = set(range(start, end + 1))
        if used & indices:
            raise ValueError("sections overlap")
        used |= indices
        color = section.get("color", "#70a9a1")
        if not isinstance(color, str) or len(color) != 7 or color[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in color[1:]):
            raise ValueError("section color must be #RRGGBB")
        normalized_sections.append(dict(name=name, start_course=start, end_course=end, color=color))
        for i in indices:
            courses[i - 1]["section"] = name
            courses[i - 1]["color"] = color
    bed_width = max(row["front_stitches"] for row in courses)
    for row in courses:
        count = row["front_stitches"]
        start = 1 + (bed_width - count) // 2
        row["bed_runs"] = {"f": [start, start + count - 1],
                           "b": [start, start + count - 1]}
    plan = dict(format="tubular-design-plan-v3", source=str(path), input_mode=input_mode,
                coordinates="one-based courses and bed-local needles; mirrored back chart",
                bed_width=bed_width,
                diameter_inches=diameter_inches, height_inches=height_inches,
                stitch_gauge=stitch_gauge, course_gauge=course_gauge,
                courses=courses, sections=normalized_sections, holes=[])
    return with_holes(plan, holes)



def save_tubular_preview(plan, path):
    """Write a self-contained, scrollable SVG chart with per-cell hover labels."""
    plan = with_holes(plan, plan.get("holes", ()))
    courses = plan["courses"]
    cell, left, top = 18, 80, 48
    maximum = 2 * plan["bed_width"]
    width, height = left + maximum * cell + 30, top + len(courses) * cell + 40
    holes = {(h["start_course"] + i, h["bed"], n) for h in plan["holes"]
             for i, (a, b) in enumerate(h["gaps"]) for n in range(a, b + 1)}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">']
    for n in range(maximum):
        parts.append(f'<text x="{left+n*cell+3}" y="25" font-size="10">{n + 1 if n < plan["bed_width"] else maximum - n}</text>')
    for label, slot in (("FRONT", 0), ("BACK", plan["bed_width"])):
        parts.append(f'<text x="{left+slot*cell}" y="42" font-size="11">{label}</text>')
    for row in reversed(courses):
        r = row["course"]
        y = top + (len(courses)-r)*cell
        parts.append(f'<text x="5" y="{y+13}" font-size="11">C{r}</text>')
        for n in range(maximum):
            bed = "f" if n < plan["bed_width"] else "b"
            needle = n + 1 if bed == "f" else maximum - n
            a, b = row["bed_runs"][bed]
            active = a <= needle <= b
            hole = (r, bed, needle) in holes
            color = "#f1f3f4" if not active else ("#fff0ef" if hole else row.get("color", "#b7cedb"))
            title = html.escape(f'Course {r}, needle {needle}, {"front" if n < plan["bed_width"] else "back"}, {row["section"]}{", inactive" if not active else (", HOLE" if hole else "")}')
            x = left+n*cell
            parts.append(f'<rect x="{x}" y="{y}" width="18" height="18" fill="{color}" stroke="#fff"><title>{title}</title></rect>')
            if hole:
                parts.append(f'<path d="M{x+4},{y+4} l10,10 m0,-10 l-10,10" stroke="#ba4336"/>')
        boundary = left + plan["bed_width"]*cell
        parts.append(f'<path d="M{boundary},{y} v18" stroke="#253b48" stroke-width="2"/>')
    parts.append('</svg>')
    # A schematic full-profile view uses the exact same sampled courses.
    profile = ['<svg xmlns="http://www.w3.org/2000/svg" width="300" height="%d">' % height]
    for row in reversed(courses):
        y = top + (len(courses)-row["course"])*cell
        span = 200 * row["diameter_inches"] / plan["diameter_inches"]
        profile.append(f'<rect x="{160-span/2}" y="{y}" width="{span}" height="18" fill="{row.get("color", "#b7cedb")}" stroke="white"/><text x="5" y="{y+13}" font-size="11">C{row["course"]}</text>')
    profile.append('<path d="M160,40 V%d" stroke="#333" stroke-dasharray="4 4"/></svg>' % (height-35))
    source = Path(plan["source"])
    mime = "image/png"  # normalize input for reliable self-contained display
    from PIL import Image
    import io
    buffer = io.BytesIO()
    with Image.open(source) as image:
        image.convert("RGB").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    payload = html.escape(json.dumps(plan, indent=2))
    sampling_note = (
        "Stitch-pixel mode: each filled pixel is one stitch per bed; each image row is one design course. Gauges only estimate dimensions."
        if plan.get("input_mode") == "stitch-pixels" else
        "Dimension mode: sampled diameters are converted using circumference = π × diameter."
    )
    document = f'''<!doctype html><meta charset="utf-8"><title>Tubular design preview</title>
<style>body{{font:15px system-ui;margin:30px;color:#253b48}}.views{{display:flex;gap:24px}}.chart{{overflow:auto;max-height:70vh;border:1px solid #ddd}}img{{max-width:220px;max-height:240px}}summary{{cursor:pointer}}svg{{display:block}}p{{max-width:950px}}</style>
<h1>Tubular design preview</h1><p>Design courses only — no cast-on, settling courses or machine scheduling. Courses and needles start at 1; courses grow upward. Front occupies the left fixed slot range and back the right. Each bed’s live stitches are centered independently; gray cells are inactive. Front needles increase left to right; back needles decrease left to right. Hole intervals use bed-local needle numbers. An odd spare needle goes at the high-numbered end on each bed. Dark line: front/back boundary. Red crosses: proposed hole. Hover a cell for coordinates and section.</p>
<div class="views"><div><h2>Source</h2><img alt="Input full side profile" src="data:{mime};base64,{encoded}"><h2>Sampled profile</h2><div class="chart">{''.join(profile)}</div></div><div style="min-width:0;flex:1"><h2>Unwrapped circumference</h2><div class="chart">{''.join(parts)}</div></div></div>
<p>Section colors are named course ranges from the specification. {sampling_note} This overlay does not validate knitting feasibility.</p><details><summary>Plan JSON</summary><pre>{payload}</pre></details>'''
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document)
    return destination
