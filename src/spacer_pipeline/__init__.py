"""Gauge-aware panel plans for spacer-fabric knitting."""

__version__ = "0.2.0"

from .analysis import PlanEvent, analyze_plan
from .compiler import CompileConfig, CompileResult, compile_panel_plan
from .model import PanelPlan, RowPlan, Run
from .parser import parse_run_file, parse_run_text

__all__ = [
    "PanelPlan",
    "PlanEvent",
    "RowPlan",
    "Run",
    "CompileConfig",
    "CompileResult",
    "analyze_plan",
    "compile_panel_plan",
    "parse_run_file",
    "parse_run_text",
]
