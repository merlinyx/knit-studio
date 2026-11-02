"""Recipes: one JSON document holding every setting for an image-to-knitout job.

A recipe is what Knit Studio saves and what ``spacer-plan run`` accepts. It
names a pipeline and passes its two settings groups straight through:

``image``
    keyword arguments for :func:`image_to_plan` (spacer) or
    :func:`tubular_plan` (tube).
``compile``
    fields of :class:`CompileConfig` (spacer) or :class:`TubularConfig`
    (tube). Carrier groups are JSON lists, e.g. ``[2, 4]`` for plating.

Tube recipes also carry ``sections`` (each may name its own ``carriers``) and
``holes``. The source image is either a path (``image_path``, relative to
the recipe file) or embedded as base64 PNG (``image_data``) so a recipe can
be shared as a single file.
"""

from __future__ import annotations

import base64
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analysis import analyze_plan
from .compiler import CompileConfig, compile_panel_plan
from .image import image_to_plan
from .preview import save_preview

RECIPE_FORMAT = "knit-studio-recipe-v1"
PIPELINES = ("spacer", "tube")

# Physical-size arguments that stitch-pixel mode rejects.
_DIMENSION_KEYS = {
    "spacer": ("width_inches", "height_inches"),
    "tube": ("diameter_inches", "height_inches"),
}


@dataclass
class JobResult:
    pipeline: str
    name: str
    files: dict[str, Path] = field(default_factory=dict)
    summary: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    course_count: int = 0
    error: str | None = None


def _carrier(value):
    if isinstance(value, list):
        return tuple(int(v) for v in value) if len(value) > 1 else int(value[0])
    return value


def read_recipe(path: str | Path) -> dict[str, Any]:
    recipe = json.loads(Path(path).read_text())
    recipe.setdefault("_base_dir", str(Path(path).resolve().parent))
    return recipe


def recipe_name(recipe: dict[str, Any]) -> str:
    name = str(recipe.get("name") or "design").strip()
    safe = "".join(c if c.isalnum() or c in "-_ ." else "_" for c in name).strip(" .")
    return safe or "design"


def _validate(recipe: dict[str, Any]) -> str:
    if recipe.get("format", RECIPE_FORMAT) != RECIPE_FORMAT:
        raise ValueError(f"unsupported recipe format {recipe.get('format')!r}")
    pipeline = recipe.get("pipeline")
    if pipeline not in PIPELINES:
        raise ValueError("recipe pipeline must be 'spacer' or 'tube'")
    return pipeline


def resolve_image(recipe: dict[str, Any], scratch: Path) -> Path:
    """Return a readable image path, writing embedded image data if needed."""
    data = recipe.get("image_data")
    if data:
        if "," in data[:100]:
            data = data.split(",", 1)[1]  # strip a data: URL prefix
        destination = scratch / f"{recipe_name(recipe)}-source.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(base64.b64decode(data))
        return destination
    if not recipe.get("image_path"):
        raise ValueError("recipe needs an image_path or embedded image_data")
    path = Path(recipe["image_path"]).expanduser()
    if not path.is_absolute():
        path = Path(recipe.get("_base_dir", ".")) / path
    if not path.is_file():
        raise ValueError(f"image not found: {path}")
    return path


def image_arguments(recipe: dict[str, Any], pipeline: str) -> dict[str, Any]:
    arguments = dict(recipe.get("image", {}))
    if arguments.get("input_mode") == "stitch-pixels":
        for key in _DIMENSION_KEYS[pipeline]:
            arguments.pop(key, None)
        if pipeline == "spacer":
            arguments.pop("align_increase_rows", None)
    return arguments


def spacer_config(settings: dict[str, Any]) -> CompileConfig:
    fields = dict(settings)
    for key in ("front_carrier", "back_carrier", "filler_carrier"):
        if key in fields:
            fields[key] = _carrier(fields[key])
    return CompileConfig(**fields)


def tube_config(settings: dict[str, Any], sections=()):
    from .tubular_compiler import TubularConfig

    fields = dict(settings)
    for key in ("carrier", "nonwire_caston"):
        if fields.get(key) is not None:
            fields[key] = _carrier(fields[key])
    carriers = {name: _carrier(value) for name, value in fields.get("section_carriers", {}).items()}
    for section in sections:
        if section.get("carriers") not in (None, []):
            carriers[section["name"]] = _carrier(section["carriers"])
    fields["section_carriers"] = carriers
    if "short_rows_after" in fields:
        fields["short_rows_after"] = {int(k): v for k, v in fields["short_rows_after"].items()}
    if fields.get("finish") != "flap_bind_off":
        fields.pop("flap", None)
    return TubularConfig(**fields)


def _describe(error: Exception) -> str:
    return str(error) or type(error).__name__


def _plan_sections(sections):
    return [{k: v for k, v in s.items() if k in ("name", "start_course", "end_course", "color")}
            for s in sections]


def build_plan(recipe: dict[str, Any], image_path: Path):
    """Sample the image into a spacer PanelPlan or a tubular design-plan dict."""
    pipeline = _validate(recipe)
    arguments = image_arguments(recipe, pipeline)
    if pipeline == "spacer":
        return image_to_plan(image_path, **arguments)
    from .tubular import tubular_plan

    return tubular_plan(image_path, sections=_plan_sections(recipe.get("sections", ())),
                        holes=recipe.get("holes", ()), **arguments)


def run_job(recipe: dict[str, Any], output_dir: str | Path, *, preview_only: bool = False) -> JobResult:
    """Sample, preview and compile one recipe into ``output_dir``.

    Image-sampling errors raise ``ValueError``. Compiler errors are stored in
    ``JobResult.error`` so the plan and preview are still available. With
    ``preview_only`` the compiler still runs (so its errors surface early) but
    no recipe copy is saved.
    """
    pipeline = _validate(recipe)
    name = recipe_name(recipe)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = JobResult(pipeline=pipeline, name=name)
    with tempfile.TemporaryDirectory() as scratch:
        image_path = resolve_image(recipe, Path(scratch))
        plan = build_plan(recipe, image_path)
        if pipeline == "spacer":
            _spacer_outputs(recipe, plan, out, name, result)
        else:
            _tube_outputs(recipe, plan, out, name, result)
        if not preview_only and result.error is None:
            saved = {k: v for k, v in recipe.items() if not k.startswith("_")}
            saved["format"] = RECIPE_FORMAT
            saved.pop("image_path", None)
            saved["image_data"] = base64.b64encode(image_path.read_bytes()).decode()
            result.files["recipe"] = out / f"{name}-recipe.json"
            result.files["recipe"].write_text(json.dumps(saved, indent=2) + "\n")
    return result


def _spacer_outputs(recipe, plan, out, name, result):
    result.files["plan"] = plan.write_json(out / f"{name}.json")
    result.files["preview"] = save_preview(plan, out / f"{name}-preview.png")
    result.course_count = len(plan.rows)
    result.diagnostics = [
        dict(row=e.row, kind=e.kind, message=e.message, severity=e.severity)
        for e in analyze_plan(plan) if e.kind != "cast_on"
    ]
    result.summary = (
        f"{len(plan.rows)} spacer block rows, {plan.grid_width} needles wide "
        f"(about {plan.nominal_width_inches:.2f} × {plan.nominal_height_inches:.2f} in)."
    )
    try:
        compiled = compile_panel_plan(plan, out / f"{name}.k", spacer_config(recipe.get("compile", {})))
    except Exception as error:  # engine assertions are user-facing here
        result.error = _describe(error)
        return
    result.files["knitout"] = compiled.output_path
    result.summary += (
        f" {compiled.ordinary_blocks} ordinary block(s), {compiled.short_row_groups} short-row "
        f"group(s), {compiled.step_changes} abrupt width step(s); {compiled.knitout_lines} knitout lines."
    )


def _tube_outputs(recipe, plan, out, name, result):
    from .tubular import save_tubular_preview
    from .tubular_compiler import compile_tubular_plan

    result.files["plan"] = out / f"{name}.json"
    result.files["plan"].write_text(json.dumps(plan, indent=2) + "\n")
    result.files["preview"] = save_tubular_preview(plan, out / f"{name}-preview.html")
    result.course_count = len(plan["courses"])
    widths = [row["front_stitches"] for row in plan["courses"]]
    result.summary = (
        f"{len(widths)} design courses, {min(widths)}–{max(widths)} stitches per bed "
        f"(about {plan['diameter_inches']:.2f} in max diameter × {plan['height_inches']:.2f} in)."
    )
    try:
        config = tube_config(recipe.get("compile", {}), recipe.get("sections", ()))
        compiled = compile_tubular_plan(plan, config)
    except Exception as error:  # engine assertions are user-facing here
        result.error = _describe(error)
        return
    result.files["knitout"] = compiled.write(out / f"{name}.k")
    result.files["schedule"] = out / f"{name}-schedule.json"
    result.files["schedule"].write_text(json.dumps(compiled.schedule, indent=2) + "\n")
    result.summary += (
        f" {len(compiled.schedule)} scheduled episodes; {len(compiled.knitout.splitlines())} knitout lines."
    )
