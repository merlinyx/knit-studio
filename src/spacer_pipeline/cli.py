"""Command-line interface for producing and inspecting panel plans."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import analyze_plan
from .compiler import CompileConfig, compile_panel_plan, parse_carrier_spec
from .image import image_to_plan
from .model import PanelPlan
from .parser import parse_run_file
from .preview import ascii_preview, save_preview


def _add_gauge_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stitch-gauge", type=float, default=9.5)
    parser.add_argument("--row-gauge", type=float, default=13.0)


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", type=Path, help="write the normalized plan as JSON")
    parser.add_argument("--preview", type=Path, help="write a color PNG stitch-grid preview")
    parser.add_argument("--ascii", action="store_true", help="print an ASCII preview")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spacer-plan")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run a Knit Studio recipe (image → plan → knitout)")
    run.add_argument("recipe", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--dat", action="store_true", help="also write .dat (requires Node.js)")

    tube = subparsers.add_parser("tube-preview", help="preview a full swept profile; no knitout")
    tube.add_argument("input", type=Path)
    tube.add_argument("--diameter-in", type=float)
    tube.add_argument("--height-in", type=float)
    tube.add_argument("--stitch-gauge", type=float, default=9.5)
    tube.add_argument("--course-gauge", type=float, default=13.0)
    tube.add_argument("--input-mode", choices=("dimensions", "stitch-pixels"), default="dimensions")
    tube.add_argument("--spec", type=Path, help="JSON with named sections and holes")
    tube.add_argument("--html", type=Path, required=True)
    tube.add_argument("--json", type=Path)

    tube_compile = subparsers.add_parser("tube-compile", help="compile a v3 tubular plan to knitout")
    tube_compile.add_argument("input", type=Path)
    tube_compile.add_argument("--output", type=Path, required=True)
    tube_compile.add_argument("--config", type=Path, help="TubularConfig fields as JSON")
    tube_compile.add_argument("--schedule", type=Path, help="write design-course/instruction mapping")

    runs = subparsers.add_parser("runs", help="parse run-per-row text notation")
    runs.add_argument("input", type=Path)
    _add_gauge_arguments(runs)
    _add_output_arguments(runs)

    image = subparsers.add_parser("image", help="rasterize a silhouette or closed outline")
    image.add_argument("input", type=Path)
    image.add_argument("--width-in", type=float)
    image.add_argument("--height-in", type=float)
    image.add_argument("--input-mode", choices=("dimensions", "stitch-pixels"), default="dimensions")
    image.add_argument("--threshold", type=int, default=128)
    image.add_argument("--coverage", type=float, default=0.5)
    image.add_argument("--invert", action="store_true")
    image.add_argument("--fill-outline", action="store_true")
    image.add_argument("--needle-offset", type=int, default=0)
    image.add_argument(
        "--no-align-increase-rows",
        action="store_false",
        dest="align_increase_rows",
        default=None,
        help="keep rasterized increase rows unchanged instead of aligning parity",
    )
    _add_gauge_arguments(image)
    _add_output_arguments(image)

    inspect = subparsers.add_parser("inspect", help="inspect an existing JSON plan")
    inspect.add_argument("input", type=Path)
    _add_output_arguments(inspect)

    compile_command = subparsers.add_parser(
        "compile", help="compile a JSON panel plan to spacer knitout"
    )
    compile_command.add_argument("input", type=Path)
    compile_command.add_argument("--output", type=Path, required=True)
    compile_command.add_argument("--front-carriers", default="2,4")
    compile_command.add_argument("--back-carriers", default="8,10")
    compile_command.add_argument("--filler-carriers", default="7")
    compile_command.add_argument("--filler-pass-pairs", type=int, default=3)
    compile_command.add_argument("--tuck-spacing", type=int, default=4)
    compile_command.add_argument("--waste-rows", type=int, default=6)
    compile_command.add_argument("--cast-off-rows", type=int, default=4)
    compile_command.add_argument(
        "--drop-repeats",
        type=int,
        default=2,
        help="repeat each shaping/width-step drop this many times (default: 2)",
    )
    compile_command.add_argument(
        "--multi-run-policy",
        choices=("short-rows", "error"),
        default="short-rows",
    )
    return parser


def _report(plan: PanelPlan, *, show_ascii: bool) -> None:
    print(
        f"{len(plan.rows)} block rows, needles {plan.min_needle}..{plan.max_needle} "
        f"({plan.grid_width} columns), nominal "
        f"{plan.nominal_width_inches:.2f} x {plan.nominal_height_inches:.2f} in"
    )
    events = analyze_plan(plan)
    for event in events:
        if event.kind != "cast_on":
            print(f"[{event.severity}] row {event.row}: {event.message}")
    if show_ascii:
        print(ascii_preview(plan))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        from .recipe import read_recipe, run_job
        result = run_job(read_recipe(args.recipe), args.output_dir)
        for item in result.diagnostics:
            print(f"[{item['severity']}] row {item['row']}: {item['message']}")
        if result.error:
            print(f"error: {result.error}")
            return 1
        print(result.summary)
        if args.dat:
            from .dat import convert_with_node
            dat_path = result.files["knitout"].with_suffix(".dat")
            warnings = convert_with_node(result.files["knitout"], dat_path)
            if warnings:
                print(warnings)
            result.files["dat"] = dat_path
        for label, path in result.files.items():
            print(f"  {label}: {path}")
        return 0
    if args.command == "tube-compile":
        from .tubular_compiler import TubularConfig, compile_tubular_plan
        fields = json.loads(args.config.read_text()) if args.config else {}
        if "short_rows_after" in fields:
            fields["short_rows_after"] = {int(k): v for k, v in fields["short_rows_after"].items()}
        config = TubularConfig(**fields)
        result = compile_tubular_plan(json.loads(args.input.read_text()), config)
        result.write(args.output)
        if args.schedule:
            args.schedule.parent.mkdir(parents=True, exist_ok=True)
            args.schedule.write_text(json.dumps(result.schedule, indent=2) + "\n")
        print(f"Wrote {args.output}; {len(result.schedule)} scheduled episodes")
        return 0
    if args.command == "tube-preview":
        from .tubular import tubular_plan, save_tubular_preview
        spec = json.loads(args.spec.read_text()) if args.spec else {}
        plan = tubular_plan(args.input, diameter_inches=args.diameter_in,
                            height_inches=args.height_in, stitch_gauge=args.stitch_gauge,
                            course_gauge=args.course_gauge,
                            sections=spec.get("sections", ()), holes=spec.get("holes", ()),
                            input_mode=args.input_mode)
        save_tubular_preview(plan, args.html)
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(plan, indent=2) + "\n")
        print(f"Wrote {len(plan['courses'])} design courses to {args.html}")
        return 0
    if args.command == "compile":
        plan = PanelPlan.read_json(args.input)
        config = CompileConfig(
            front_carrier=parse_carrier_spec(args.front_carriers),
            back_carrier=parse_carrier_spec(args.back_carriers),
            filler_carrier=parse_carrier_spec(args.filler_carriers),
            filler_pass_pairs=args.filler_pass_pairs,
            tuck_spacing=args.tuck_spacing,
            waste_rows=args.waste_rows,
            cast_off_rows=args.cast_off_rows,
            drop_repeats=args.drop_repeats,
            multi_run_policy=args.multi_run_policy,
        )
        result = compile_panel_plan(plan, args.output, config)
        print(
            f"wrote {result.output_path} ({result.knitout_lines} lines): "
            f"{result.ordinary_blocks} ordinary block(s), "
            f"{result.short_row_groups} short-row group(s) / "
            f"{result.short_row_levels} level(s), "
            f"{result.step_changes} abrupt range step(s)"
        )
        return 0

    if args.command == "runs":
        plan = parse_run_file(
            args.input,
            stitch_gauge=args.stitch_gauge,
            row_gauge=args.row_gauge,
        )
    elif args.command == "image":
        plan = image_to_plan(
            args.input,
            width_inches=args.width_in,
            height_inches=args.height_in,
            stitch_gauge=args.stitch_gauge,
            row_gauge=args.row_gauge,
            threshold=args.threshold,
            coverage=args.coverage,
            invert=args.invert,
            fill_outline=args.fill_outline,
            needle_offset=args.needle_offset,
            align_increase_rows=args.align_increase_rows,
            input_mode=args.input_mode,
        )
    else:
        plan = PanelPlan.read_json(args.input)

    if args.json:
        plan.write_json(args.json)
    if args.preview:
        save_preview(plan, args.preview)
    _report(plan, show_ascii=args.ascii)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
