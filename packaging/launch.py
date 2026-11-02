"""Entry point for the packaged Knit Studio app (PyInstaller)."""

import logging
import os
import sys

from spacer_pipeline.studio.app import main
from spacer_pipeline.studio.server import user_data_dir

if getattr(sys, "frozen", False):
    # A windowed app has no terminal; keep messages in a log people can send in.
    log_dir = user_data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "knit-studio.log", "w", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = log
    logging.basicConfig(stream=log, level=logging.DEBUG if os.environ.get("KNIT_STUDIO_DEBUG") else logging.INFO)
    if os.environ.get("KNIT_STUDIO_DEBUG"):
        import faulthandler
        faulthandler.dump_traceback_later(8, file=log)

raise SystemExit(main())
