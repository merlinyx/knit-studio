"""Describe every pipeline setting for Knit Studio's forms.

Fields come from the code itself: the keyword arguments of ``image_to_plan`` /
``tubular_plan`` and the fields of ``CompileConfig`` / ``TubularConfig`` /
``FlapBindOffConfig``. ``HINTS`` only adds labels, help text, widgets and
grouping. A new argument or config field with no hint still appears, under
"More settings", with a widget guessed from its default value.
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import Any

from .compiler import CompileConfig
from .flap_bind_off import FlapBindOffConfig
from .image import image_to_plan
from .tubular import tubular_plan
from .tubular_compiler import TubularConfig

# Arguments the app fills in itself or edits in its own tables.
_SKIPPED = {"path", "sections", "holes", "section_carriers", "flap"}

PIXELS = {"field": "image.input_mode", "equals": "dimensions"}

_INPUT_MODE = dict(
    group="Image", label="What the image means", widget="select",
    options=[["dimensions", "A drawing to scale to a real size"],
             ["stitch-pixels", "Exact stitch chart: one pixel = one stitch"]],
    help="Scaled drawings are resized using the gauges. In a stitch chart every "
         "filled pixel is one stitch and every pixel row is one row.",
)

HINTS: dict[str, dict[str, dict[str, Any]]] = {
    "spacer.image": {
        "input_mode": _INPUT_MODE,
        "width_inches": dict(group="Image", label="Finished width (in)", default=4.0, min=0.1,
                             step=0.05, show_if=PIXELS),
        "height_inches": dict(group="Image", label="Finished height (in)", default=4.0, min=0.1,
                              step=0.05, show_if=PIXELS),
        "fill_outline": dict(group="Image", label="Drawing is an outline (fill it in)",
                             help="Turn on for a closed black outline with a white inside."),
        "invert": dict(group="Image", label="Light shape on dark background"),
        "stitch_gauge": dict(group="Gauge", label="Stitches per inch", min=0.1, step=0.1),
        "row_gauge": dict(group="Gauge", label="Spacer blocks per inch", min=0.1, step=0.1,
                          help="One spacer block is a front + back face-row pair."),
        "threshold": dict(group="Image", label="Dark/light threshold (0–255)", min=0, max=255,
                          advanced=True, help="Pixels darker than this count as fabric."),
        "coverage": dict(group="Image", label="Cell coverage needed", min=0.01, max=1, step=0.05,
                         advanced=True, help="Fraction of a stitch cell that must be filled."),
        "needle_offset": dict(group="Image", label="First needle number", advanced=True),
        "align_increase_rows": dict(
            group="Image", label="Align increases to front-face rows", widget="boolean",
            default=True, advanced=True, show_if=PIXELS,
            help="Moves gradual increases onto even rows where the spacer engine knits the "
                 "front face first. Total height is preserved."),
    },
    "spacer.compile": {
        "front_carrier": dict(group="Yarns", label="Front face", widget="carriers"),
        "back_carrier": dict(group="Yarns", label="Back face", widget="carriers"),
        "filler_carrier": dict(group="Yarns", label="Filler", widget="carriers"),
        "filler_pass_pairs": dict(group="Spacer structure", label="Filler pass pairs per block", min=0),
        "tuck_spacing": dict(group="Spacer structure", label="Filler tuck spacing", min=1, max=5),
        "waste_rows": dict(group="Machine", label="Waste rows", min=5, advanced=True),
        "cast_off_rows": dict(group="Machine", label="Cast-off rows", min=0, advanced=True),
        "drop_repeats": dict(group="Machine", label="Repeat shaping drops", min=1, advanced=True,
                             help="Extra drops help with elastic and plated yarns."),
        "multi_run_policy": dict(
            group="Machine", label="Separated pieces in a row", widget="select", advanced=True,
            options=[["short-rows", "Knit as short rows"], ["error", "Stop with an error"]]),
    },
    "tube.image": {
        "input_mode": _INPUT_MODE,
        "diameter_inches": dict(group="Image", label="Widest diameter (in)", default=4.0, min=0.1,
                                step=0.05, show_if=PIXELS),
        "height_inches": dict(group="Image", label="Height (in)", default=3.0, min=0.1, step=0.05,
                              show_if=PIXELS),
        "stitch_gauge": dict(group="Gauge", label="Stitches per inch (around)", min=0.1, step=0.1),
        "course_gauge": dict(group="Gauge", label="Courses per inch", min=0.1, step=0.1),
    },
    "tube.compile": {
        "carrier": dict(group="Yarns", label="Main yarn (outside sections)", widget="carriers"),
        "nonwire_caston": dict(group="Yarns", label="Separate cast-on yarn", widget="optional_carriers",
                               help="Cast on with a different (non-wire) yarn, then switch."),
        "gauge": dict(group="Machine", label="Needle spacing (gauge)", widget="select",
                      options=[[2, "2 – every other needle"], [3, "3"], [4, "4"]]),
        "cast_on": dict(group="Start and finish", label="Cast-on", widget="select",
                        options=[["twisted_tuck", "Twisted tuck"], ["alt_tuck", "Alternating tuck"],
                                 ["knit", "Knit"], ["all_needle_transition", "All-needle transition (gauge 2)"],
                                 ["none", "None – plated yarns enter one at a time"]]),
        "settling_courses": dict(group="Start and finish", label="Settling courses", min=2,
                                 show_if={"field": "compile.cast_on", "not_equals": "none"}),
        "plating_setup_courses": dict(group="Start and finish", label="Solo rounds per plated yarn",
                                      min=1, help="Used when the first section is plated."),
        "finish": dict(group="Start and finish", label="Finish", widget="select",
                       options=[["bind_off", "Bind off"], ["drop", "Drop"],
                                ["flap_bind_off", "Flap joined across the top"]]),
        "double_transfers": dict(group="Machine", label="Repeat transfer sweeps", advanced=True),
        "drop_repeats": dict(group="Machine", label="Drop cleanup sweeps", widget="optional_integer",
                             min=1, advanced=True, help="Leave off to keep the original output."),
        "side_slack": dict(group="Machine", label="Side slack", advanced=True),
        "max_rack": dict(group="Machine", label="Maximum racking", min=1, advanced=True),
        "short_rows_after": dict(
            group="Machine", label="Extra short rows (JSON)", widget="json", advanced=True,
            help='Course number → list of turns, e.g. {"12": [{"b": "f", "n": 5}]}.'),
    },
    "tube.compile.flap": {
        "n": dict(group="Flap", label="Flap needle", widget="optional_integer",
                  help="Leave the flap sizes blank to size the flap automatically."),
        "flap_width": dict(group="Flap", label="Flap width", widget="optional_integer"),
        "flap_rows": dict(group="Flap", label="Flap rows", widget="optional_integer"),
        "stitch_gauge": dict(group="Flap", label="Flap stitches/in", widget="optional_number",
                             advanced=True, help="Blank uses the tube gauge."),
        "row_gauge": dict(group="Flap", label="Flap rows/in", widget="optional_number",
                          advanced=True, help="Blank uses the tube gauge."),
        "has_tag": dict(group="Flap", label="Knit a tag"),
    },
}

_FLAP_SHOWN = {"field": "compile.finish", "equals": "flap_bind_off"}

GROUP_ORDER = ["Image", "Gauge", "Yarns", "Sections", "Holes", "Spacer structure",
               "Start and finish", "Flap", "Machine", "More settings"]


def _jsonable(value):
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def _guess_widget(default) -> str:
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, int):
        return "integer"
    if isinstance(default, float):
        return "number"
    if isinstance(default, str):
        return "text"
    return "json"


def _sources():
    def signature(function):
        return [(p.name, p.default) for p in inspect.signature(function).parameters.values()
                if p.default is not inspect.Parameter.empty]

    def config(cls):
        result = []
        for f in dataclasses.fields(cls):
            if f.default is not dataclasses.MISSING:
                result.append((f.name, f.default))
            elif f.default_factory is not dataclasses.MISSING:
                result.append((f.name, f.default_factory()))
        return result

    return [("spacer", "image", signature(image_to_plan)),
            ("spacer", "compile", config(CompileConfig)),
            ("tube", "image", signature(tubular_plan)),
            ("tube", "compile", config(TubularConfig)),
            ("tube", "compile.flap", config(FlapBindOffConfig))]


def build_schema() -> dict[str, Any]:
    pipelines: dict[str, list[dict[str, Any]]] = {"spacer": [], "tube": []}
    for pipeline, target, parameters in _sources():
        hints = HINTS.get(f"{pipeline}.{target}", {})
        for name, default in parameters:
            if name in _SKIPPED:
                continue
            hint = dict(hints.get(name, {}))
            default = hint.pop("default", default)
            entry = dict(
                order=list(hints).index(name) if name in hints else len(hints),
                key=f"{target}.{name}", target=target, name=name,
                label=hint.pop("label", name.replace("_", " ").capitalize()),
                group=hint.pop("group", "More settings"),
                widget=hint.pop("widget", _guess_widget(default)),
                default=_jsonable(default),
                advanced=hint.pop("advanced", name not in hints),
                **hint,
            )
            if target == "compile.flap":
                entry["show_if"] = _FLAP_SHOWN
            pipelines[pipeline].append(entry)
    def position(field):
        group = GROUP_ORDER.index(field["group"]) if field["group"] in GROUP_ORDER else 99
        return group, field["target"], field.pop("order")

    for fields in pipelines.values():
        fields.sort(key=position)
    return dict(groups=GROUP_ORDER, pipelines=pipelines)


def default_recipe(pipeline: str) -> dict[str, Any]:
    """A recipe with every schema default filled in (no image yet)."""
    recipe: dict[str, Any] = dict(format="knit-studio-recipe-v1", pipeline=pipeline,
                                  name="design", image={}, compile={})
    if pipeline == "tube":
        recipe.update(sections=[], holes=[])
    for field in build_schema()["pipelines"][pipeline]:
        target = recipe
        for part in field["target"].split("."):
            target = target.setdefault(part, {})
        target[field["name"]] = field["default"]
    return recipe
