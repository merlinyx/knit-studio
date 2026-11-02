"""Launch Knit Studio in its own window (pywebview) or in the web browser."""

from __future__ import annotations

import argparse
import time
import webbrowser
from pathlib import Path

from .server import Studio, start_server


class WindowApi:
    """Native dialogs exposed to the page as ``window.pywebview.api``.

    pywebview exposes public attributes too, so the window stays private.
    """

    def __init__(self):
        self._window = None

    def choose_folder(self, start=""):
        import webview

        chosen = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start or "")
        return chosen[0] if chosen else None

    def save_text(self, filename, text):
        import webview

        chosen = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=filename)
        if not chosen:
            return None
        path = Path(chosen if isinstance(chosen, str) else chosen[0])
        path.write_text(text)
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="knit-studio", description=__doc__)
    parser.add_argument("--browser", action="store_true",
                        help="open in the web browser instead of a separate window")
    parser.add_argument("--port", type=int, default=0, help="port to listen on (default: any free port)")
    parser.add_argument("--no-open", action="store_true", help="print the address without opening it")
    parser.add_argument("--output-root", type=Path, help="default folder for generated files")
    parser.add_argument("--data-dir", type=Path, help="where presets and the last session are kept")
    args = parser.parse_args(argv)

    webview = None
    if not args.browser and not args.no_open:
        try:
            import webview
        except ImportError:
            print("pywebview is not installed; opening in the browser instead.")
    studio = Studio(desktop=webview is not None, data_dir=args.data_dir, output_root=args.output_root)
    server, url = start_server(studio, args.port)

    if webview is not None:
        print(f"Knit Studio is serving {url.split('#')[0]}; opening its window.", flush=True)
        api = WindowApi()
        api._window = webview.create_window("Knit Studio", url, js_api=api, width=1360, height=900,
                                            min_size=(900, 600), text_select=True)
        try:
            webview.start()
        except Exception as error:  # e.g. no WebView2 runtime on an older Windows PC
            print(f"Could not open a window ({error}); opening in the browser instead.")
            studio.desktop = False
        else:
            server.shutdown()
            return 0

    print(f"Knit Studio is running at {url}\nPress Ctrl+C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()
    return 0
