#!/usr/bin/env python3.14
"""Serve a packaged Degrees of Lewdity web app and selected ModLoader mods."""

from __future__ import annotations

import argparse
import functools
import json
import mimetypes
import shutil
import socket
import sys
import threading
import webbrowser
import zipfile
from dataclasses import dataclass
from email.utils import formatdate
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence
from urllib.parse import quote, urlsplit

DEFAULT_PORT = 8000
DEFAULT_BIND = "127.0.0.1"
SUPPORTED_PROTOCOLS = ("HTTP/1.0", "HTTP/1.1")
OFFICIAL_MOD_FILES = {
    "i18n": "official-i18n.mod.zip",
    "images": "official-images.mod.zip",
}
ALLOWED_COMPRESSIONS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}


class UserInputError(ValueError):
    """An actionable command-line input error."""


@dataclass(frozen=True)
class ModSpec:
    kind: str
    value: str | None = None


@dataclass(frozen=True)
class ServedMod:
    path: Path
    route: str
    name: str
    version: str


class AppendModSpec(argparse.Action):
    """Preserve the relative order of official and custom mod flags."""

    def __init__(self, option_strings, dest, *, mod_kind: str, **kwargs):
        self.mod_kind = mod_kind
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        specs = list(getattr(namespace, self.dest) or [])
        value = values if self.mod_kind == "custom" else None
        specs.append(ModSpec(self.mod_kind, value))
        setattr(namespace, self.dest, specs)


def executable_mode(program_name: str) -> str:
    return "fixed" if Path(program_name).name == "dol-chs" else "selectable"


def default_app_directory(program_name: str) -> Path:
    prefix = Path(__file__).resolve().parent.parent
    return prefix / "share" / Path(program_name).name


def read_version(app_directory: Path) -> str:
    try:
        return (app_directory / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "development"


def valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 0 and 65535")
    return port


def build_parser(program_name: str, app_directory: Path | None = None) -> argparse.ArgumentParser:
    default_directory = app_directory or default_app_directory(program_name)
    version = read_version(default_directory)
    parser = argparse.ArgumentParser(
        prog=program_name,
        description="Serve Degrees of Lewdity as a local browser application.",
    )
    parser.add_argument("port", nargs="?", type=valid_port, default=DEFAULT_PORT,
                        help=f"port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("-b", "--bind", default=DEFAULT_BIND, metavar="ADDRESS",
                        help=f"address to bind to (default: {DEFAULT_BIND})")
    parser.add_argument("-d", "--directory", type=Path, default=default_directory,
                        help="web application directory (default: packaged application)")
    parser.add_argument("-p", "--protocol", choices=SUPPORTED_PROTOCOLS, default="HTTP/1.0",
                        help="HTTP protocol version (default: HTTP/1.0)")
    parser.add_argument("--open", action=argparse.BooleanOptionalAction, default=True,
                        help="open the application in a browser (default: enabled)")
    parser.add_argument("--quiet", action="store_true", help="suppress request logs")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version}")

    if executable_mode(program_name) == "selectable":
        parser.set_defaults(mod_specs=[])
        parser.add_argument(
            "--no-mods",
            action="store_true",
            help="load no mods (default; cannot be combined with mod selectors)",
        )
        parser.add_argument(
            "--i18n",
            dest="mod_specs",
            action=AppendModSpec,
            mod_kind="i18n",
            nargs=0,
            help="load the bundled official Chinese localization at this position",
        )
        parser.add_argument(
            "--images",
            dest="mod_specs",
            action=AppendModSpec,
            mod_kind="images",
            nargs=0,
            help="load the bundled official image pack at this position",
        )
        parser.add_argument(
            "-m",
            "--mod",
            dest="mod_specs",
            action=AppendModSpec,
            mod_kind="custom",
            metavar="PATH",
            help="load a .mod.zip file at this position; may be repeated",
        )
    return parser


def validate_app_directory(path: Path) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as error:
        raise UserInputError(f"application directory does not exist: {path}") from error
    if not resolved.is_dir():
        raise UserInputError(f"application directory is not a directory: {path}")
    if not (resolved / "index.html").is_file():
        raise UserInputError(f"application directory has no index.html: {resolved}")
    return resolved


def validate_mod_archive(path: Path) -> tuple[Path, str, str]:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as error:
        raise UserInputError(f"mod does not exist: {path}") from error
    if not resolved.is_file():
        raise UserInputError(f"mod is not a file: {path}")
    if not zipfile.is_zipfile(resolved):
        raise UserInputError(f"mod is not a valid ZIP archive: {resolved}")

    try:
        with zipfile.ZipFile(resolved) as archive:
            infos = archive.infolist()
            names = {entry.filename for entry in infos}
            if "boot.json" not in names:
                raise UserInputError(f"mod has no boot.json at its root: {resolved}")
            if any(entry.flag_bits & 0x1 for entry in infos):
                raise UserInputError(f"encrypted mod archives are not supported: {resolved}")
            if any(entry.compress_type not in ALLOWED_COMPRESSIONS for entry in infos):
                raise UserInputError(f"mod must use only Store or Deflate compression: {resolved}")
            try:
                manifest = json.loads(archive.read("boot.json"))
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
                raise UserInputError(f"mod has an invalid boot.json: {resolved}") from error
    except zipfile.BadZipFile as error:
        raise UserInputError(f"mod is not a valid ZIP archive: {resolved}") from error

    if not isinstance(manifest, dict) or not isinstance(manifest.get("name"), str):
        raise UserInputError(f"mod boot.json has no string name: {resolved}")
    name = manifest["name"].strip()
    if not name:
        raise UserInputError(f"mod boot.json has an empty name: {resolved}")
    version = manifest.get("version", "unknown")
    if not isinstance(version, str):
        version = str(version)
    return resolved, name, version


def selected_specs(program_name: str, parsed_specs: Sequence[ModSpec] | None,
                   no_mods: bool = False) -> list[ModSpec]:
    if executable_mode(program_name) == "fixed":
        return [ModSpec("i18n"), ModSpec("images")]
    if no_mods and parsed_specs:
        raise UserInputError("--no-mods cannot be combined with --i18n, --images or --mod")
    return list(parsed_specs or [])


def resolve_mods(program_name: str, app_directory: Path,
                 parsed_specs: Sequence[ModSpec] | None, no_mods: bool = False) -> list[ServedMod]:
    mods: list[ServedMod] = []
    for index, spec in enumerate(selected_specs(program_name, parsed_specs, no_mods)):
        if spec.kind in OFFICIAL_MOD_FILES:
            path = app_directory / "mods" / OFFICIAL_MOD_FILES[spec.kind]
        elif spec.kind == "custom" and spec.value is not None:
            path = Path(spec.value)
        else:
            raise UserInputError(f"unsupported mod selection: {spec.kind}")

        resolved, name, version = validate_mod_archive(path)
        route = f"/__dol_mods__/{index}/{quote(resolved.name)}"
        mods.append(ServedMod(resolved, route, name, version))
    return mods


def make_handler(app_directory: Path, mods: Sequence[ServedMod], protocol: str,
                 quiet: bool) -> type[SimpleHTTPRequestHandler]:
    route_map = {mod.route: mod.path for mod in mods}
    mod_list = json.dumps([mod.route for mod in mods], ensure_ascii=False).encode("utf-8")

    class DolRequestHandler(SimpleHTTPRequestHandler):
        protocol_version = protocol

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(app_directory), **kwargs)

        def log_message(self, format_string, *args):
            if not quiet:
                super().log_message(format_string, *args)

        def do_GET(self):
            self._serve(head_only=False)

        def do_HEAD(self):
            self._serve(head_only=True)

        def _serve(self, *, head_only: bool):
            request_path = urlsplit(self.path).path
            if request_path == "/modList.json":
                self._send_bytes(mod_list, "application/json; charset=utf-8", head_only=head_only)
                return
            if request_path in route_map:
                self._send_file(route_map[request_path], head_only=head_only)
                return
            if head_only:
                super().do_HEAD()
            else:
                super().do_GET()

        def _send_bytes(self, content: bytes, content_type: str, *, head_only: bool):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head_only:
                self.wfile.write(content)

        def _send_file(self, path: Path, *, head_only: bool):
            try:
                stat = path.stat()
                source = path.open("rb")
            except OSError:
                self.send_error(404, "Mod file is no longer available")
                return
            with source:
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/zip")
                self.send_header("Content-Length", str(stat.st_size))
                self.send_header("Last-Modified", formatdate(stat.st_mtime, usegmt=True))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if not head_only:
                    shutil.copyfileobj(source, self.wfile)

    return DolRequestHandler


def make_server(bind: str, port: int, handler: type[SimpleHTTPRequestHandler]) -> ThreadingHTTPServer:
    try:
        family = socket.getaddrinfo(
            bind,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            flags=socket.AI_PASSIVE,
        )[0][0]
    except socket.gaierror as error:
        raise UserInputError(f"cannot resolve bind address {bind!r}: {error}") from error

    class DolHTTPServer(ThreadingHTTPServer):
        address_family = family
        daemon_threads = True

    try:
        return DolHTTPServer((bind, port), handler)
    except OSError as error:
        raise UserInputError(f"cannot listen on {bind}:{port}: {error}") from error


def browser_url(bind: str, port: int) -> str:
    if bind in {"0.0.0.0", ""}:
        host = "127.0.0.1"
    elif bind == "::":
        host = "::1"
    else:
        host = bind
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}/"


def main(argv: Sequence[str] | None = None, *, program_name: str | None = None) -> int:
    invoked_as = program_name or Path(sys.argv[0]).name
    if invoked_as not in {"dol-chs", "dol-chs-mod"}:
        invoked_as = "dol-chs-mod"
    parser = build_parser(invoked_as)
    args = parser.parse_args(argv)

    try:
        app_directory = validate_app_directory(args.directory)
        mods = resolve_mods(
            invoked_as,
            app_directory,
            getattr(args, "mod_specs", None),
            getattr(args, "no_mods", False),
        )
        handler = make_handler(app_directory, mods, args.protocol, args.quiet)
        server = make_server(args.bind, args.port, handler)
    except UserInputError as error:
        parser.error(str(error))

    actual_port = server.server_address[1]
    url = browser_url(args.bind, actual_port)
    print(f"Serving {invoked_as} at {url}", flush=True)
    if mods:
        print("Mods:", flush=True)
        for mod in mods:
            print(f"  {mod.name} {mod.version}", flush=True)
    else:
        print("Mods: none", flush=True)

    if args.open:
        opener = threading.Timer(0.15, functools.partial(webbrowser.open, url))
        opener.daemon = True
        opener.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
