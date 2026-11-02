"""Run from the repository: PYTHONPATH=src .venv/bin/python examples/tubular/preview_lampshade.py"""
from pathlib import Path
from spacer_pipeline.tubular_compiler import TubularConfig, compile_tubular_plan
from spacer_pipeline.tubular import Hole, tubular_plan, with_holes, save_tubular_preview

folder = Path(__file__).resolve().parent
plan = tubular_plan(
    folder / "lampshade-profile.png",
    diameter_inches=4, height_inches=3, stitch_gauge=4, course_gauge=8,
    sections=[
        dict(name="elastic base", start_course=1, end_course=8, color="#e8b86d"),
        dict(name="wire body", start_course=9, end_course=24, color="#87b6c8"),
    ],
)
# Inspect this first to choose fixed chart positions for the hole.
save_tubular_preview(plan, folder / "lampshade-base-preview.html")
plan = with_holes(plan, [Hole(start_course=3, gaps=((9, 10), (8, 11), (8, 11), (9, 10)), bed="f")])
save_tubular_preview(plan, folder / "lampshade-preview.html")
import json
(folder / "lampshade-plan.json").write_text(json.dumps(plan, indent=2) + "\n")

# The bottom eight courses have constant width, so the opening is wholly
# inside the elastic band. Outer shaping begins after the hole has closed.
result = compile_tubular_plan(plan, TubularConfig(
    gauge=2, carrier=6, section_carriers={"elastic base": 1, "wire body": 6},
))
result.write(folder / "lampshade.k")
(folder / "lampshade-schedule.json").write_text(json.dumps(result.schedule, indent=2) + "\n")
