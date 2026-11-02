"""Local HTTP server behind Knit Studio.

It listens on 127.0.0.1 only. Every ``/api`` request must carry the session
token from the launch URL in an ``X-Studio-Token`` header; browsers cannot
add that header cross-origin without a CORS preflight this server never
grants, so other web pages cannot drive it.
"""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import secrets
import socketserver
import subprocess
import sys
import tempfile
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from .. import __version__
from ..recipe import recipe_name, run_job
from ..settings_schema import build_schema, default_recipe

STATIC = Path(__file__).parent / "static"
SAMPLES = Path(__file__).parent / "samples"
BUILTIN_PRESETS = Path(__file__).parent / "presets.json"
MAX_BODY = 64 * 1024 * 1024


def user_data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "Knit Studio"


def default_output_root() -> Path:
    return Path.home() / "Documents" / "Knit Studio"


def open_in_file_browser(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif os.name == "nt":
        os.startfile(str(path))  # noqa: S606 - local folder the app wrote
    else:
        subprocess.Popen(["xdg-open", str(path)])


def normalize_image(data_url: str) -> tuple[str, int, int]:
    """Flatten transparency onto white and re-encode as PNG.

    Design tools often export transparent backgrounds, which would otherwise
    read as black (all fabric) after grayscale conversion.
    """
    raw = base64.b64decode(data_url.split(",", 1)[-1])
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            flat = Image.new("RGB", rgba.size, "white")
            flat.paste(rgba, mask=rgba.getchannel("A"))
        else:
            flat = image.convert("RGB")
    buffer = io.BytesIO()
    flat.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{encoded}", flat.width, flat.height


class Presets:
    def __init__(self, folder: Path):
        self.folder = folder

    def all(self) -> list[dict]:
        presets = json.loads(BUILTIN_PRESETS.read_text())
        if self.folder.is_dir():
            for path in sorted(self.folder.glob("*.json")):
                try:
                    preset = json.loads(path.read_text())
                except (OSError, ValueError):
                    continue
                preset.update(id=f"user-{path.stem}", builtin=False)
                presets.append(preset)
        return presets

    def save(self, label: str, pipeline: str, settings: dict) -> dict:
        label = label.strip()
        if not label:
            raise ValueError("preset needs a name")
        stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in label.lower()).strip("-") or "preset"
        self.folder.mkdir(parents=True, exist_ok=True)
        preset = dict(label=label, pipeline=pipeline, settings=settings)
        (self.folder / f"{stem}.json").write_text(json.dumps(preset, indent=2) + "\n")
        return dict(preset, id=f"user-{stem}", builtin=False)

    def delete(self, preset_id: str) -> None:
        if not preset_id.startswith("user-"):
            raise ValueError("built-in presets cannot be deleted")
        path = self.folder / f"{preset_id[5:]}.json"
        if path.parent == self.folder and path.exists():
            path.unlink()


class Studio:
    """State shared by request handlers."""

    def __init__(self, *, desktop: bool = False, data_dir: Path | None = None,
                 output_root: Path | None = None):
        self.token = secrets.token_urlsafe(24)
        self.desktop = desktop
        self.data_dir = data_dir or user_data_dir()
        self.presets = Presets(self.data_dir / "presets")
        self.output_root = output_root or default_output_root()
        self.written: set[Path] = set()  # folders and .k files this session produced
        self.lock = threading.Lock()

    # Each handler takes the decoded JSON body and returns a JSON-able value.
    def state(self, _body):
        samples = {}
        for pipeline, filename in (("spacer", "spacer-arch.png"), ("tube", "tube-vase.png")):
            encoded = base64.b64encode((SAMPLES / filename).read_bytes()).decode()
            samples[pipeline] = dict(name=filename, data=f"data:image/png;base64,{encoded}")
        try:
            last_session = json.loads((self.data_dir / "last-session.json").read_text())
        except (OSError, ValueError):
            last_session = {}
        return dict(version=__version__, desktop=self.desktop, schema=build_schema(),
                    defaults={p: default_recipe(p) for p in ("spacer", "tube")},
                    presets=self.presets.all(), output_root=str(self.output_root), samples=samples,
                    last_session=last_session)

    def remember(self, body):
        """Keep the working settings so the next launch starts where this one ended."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "last-session.json").write_text(json.dumps(body))
        return {}

    def image(self, body):
        data, width, height = normalize_image(body["data"])
        return dict(data=data, width=width, height=height)

    def preview(self, body):
        recipe = body["recipe"]
        with tempfile.TemporaryDirectory() as scratch:
            try:
                result = run_job(recipe, scratch, preview_only=True)
            except (ValueError, KeyError, TypeError) as error:
                return dict(ok=False, fatal=str(error))
            preview = result.files["preview"]
            if preview.suffix == ".png":
                shown = dict(kind="png", data="data:image/png;base64,"
                             + base64.b64encode(preview.read_bytes()).decode())
            else:
                shown = dict(kind="html", html=preview.read_text())
        return dict(ok=result.error is None, error=result.error, summary=result.summary,
                    diagnostics=result.diagnostics, course_count=result.course_count, preview=shown)

    def generate(self, body):
        recipe = body["recipe"]
        root = Path(body.get("output_root") or self.output_root).expanduser()
        folder = root / recipe_name(recipe)
        name = recipe_name(recipe)
        clashes = sorted(p.name for p in folder.glob(f"{name}*")) if folder.is_dir() else []
        if clashes and not body.get("overwrite"):
            return dict(ok=False, exists=True, folder=str(folder), clashes=clashes)
        try:
            result = run_job(recipe, folder)
        except (ValueError, KeyError, TypeError) as error:
            return dict(ok=False, fatal=str(error))
        if result.error:
            return dict(ok=False, error=result.error)
        knitout = result.files["knitout"]
        with self.lock:
            self.written |= {folder.resolve(), knitout.resolve()}
        return dict(ok=True, folder=str(folder), summary=result.summary,
                    files={k: str(v) for k, v in result.files.items()},
                    knitout_path=str(knitout), knitout=knitout.read_text())

    def save_dat(self, body):
        knitout = Path(body["knitout_path"]).resolve()
        if knitout not in self.written:
            raise PermissionError("can only write .dat next to a file this session generated")
        destination = knitout.with_suffix(".dat")
        destination.write_bytes(base64.b64decode(body["data"]))
        return dict(path=str(destination))

    def open_folder(self, body):
        folder = Path(body["path"]).resolve()
        if folder not in self.written:
            raise PermissionError("can only open folders this session generated")
        open_in_file_browser(folder)
        return {}

    def save_preset(self, body):
        return self.presets.save(body["label"], body["pipeline"], body["settings"])

    def delete_preset(self, body):
        self.presets.delete(body["id"])
        return {}


ROUTES = {
    ("GET", "/api/state"): Studio.state,
    ("POST", "/api/image"): Studio.image,
    ("POST", "/api/preview"): Studio.preview,
    ("POST", "/api/generate"): Studio.generate,
    ("POST", "/api/save-dat"): Studio.save_dat,
    ("POST", "/api/open-folder"): Studio.open_folder,
    ("POST", "/api/presets"): Studio.save_preset,
    ("POST", "/api/presets/delete"): Studio.delete_preset,
    ("POST", "/api/remember"): Studio.remember,
}


def make_handler(studio: Studio):
    class Handler(BaseHTTPRequestHandler):
        server_version = "KnitStudio"

        def log_message(self, format, *args):
            if os.environ.get("KNIT_STUDIO_DEBUG"):  # otherwise keep the terminal quiet
                sys.stderr.write(f"{self.address_string()} {format % args}\n")

        def _send(self, status, payload: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, status, value):
            self._send(status, json.dumps(value).encode(), "application/json")

        def _handle(self, method):
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                return self._static(path) if method == "GET" else self._json(HTTPStatus.NOT_FOUND, {})
            route = ROUTES.get((method, path))
            if route is None:
                return self._json(HTTPStatus.NOT_FOUND, dict(message="unknown endpoint"))
            if not secrets.compare_digest(self.headers.get("X-Studio-Token", ""), studio.token):
                return self._json(HTTPStatus.FORBIDDEN, dict(message="bad session token"))
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, dict(message="request too large"))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                return self._json(HTTPStatus.OK, route(studio, body))
            except PermissionError as error:
                return self._json(HTTPStatus.FORBIDDEN, dict(message=str(error)))
            except Exception as error:  # report, don't crash the server
                traceback.print_exc()
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                                  dict(message=f"{type(error).__name__}: {error}"))

        def _static(self, path):
            relative = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (STATIC / relative).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                return self._json(HTTPStatus.NOT_FOUND, {})
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type.endswith("javascript"):
                content_type += "; charset=utf-8"
            self._send(HTTPStatus.OK, target.read_bytes(), content_type)

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return Handler


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind calls socket.getfqdn(), a reverse-DNS lookup
        # that can hang for many seconds on some networks. It only names the
        # server, which a 127.0.0.1-only app does not need.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def start_server(studio: Studio, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start serving in a daemon thread; return the server and the launch URL."""
    server = LocalServer(("127.0.0.1", port), make_handler(studio))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/#token={studio.token}"
    return server, url
