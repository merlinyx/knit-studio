"""Knitout-to-DAT conversion with the bundled knitout-backend-swg script.

Knit Studio runs the script inside its own window (see
``studio/static/dat-shim.js``), so designers never need Node. The command line
uses Node directly when it is installed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

CONVERTER = Path(__file__).parent / "studio" / "static" / "vendor" / "knitout-to-dat.js"


def node_executable() -> str | None:
    return shutil.which("node") or shutil.which("nodejs")


def convert_with_node(knitout_path: str | Path, dat_path: str | Path) -> str:
    """Write ``dat_path``; return the converter's warnings. Raises if Node is missing."""
    node = node_executable()
    if node is None:
        raise RuntimeError("Node.js is not installed; use Knit Studio or install Node to write .dat files")
    completed = subprocess.run(
        [node, str(CONVERTER), str(knitout_path), str(dat_path)],
        capture_output=True, text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "knitout-to-dat failed")
    return completed.stderr.strip()
