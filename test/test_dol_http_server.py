from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "libexec" / "dol_http_server.py"
SPEC = importlib.util.spec_from_file_location("dol_http_server", MODULE_PATH)
assert SPEC and SPEC.loader
SERVER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SERVER
SPEC.loader.exec_module(SERVER)


def write_mod(path: Path, name: str, version: str = "1.0.0") -> bytes:
    manifest = {
        "name": name,
        "version": version,
        "styleFileList": [],
        "scriptFileList": [],
        "tweeFileList": [],
        "imgFileList": [],
        "additionFile": [],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("boot.json", json.dumps(manifest))
    return path.read_bytes()


class DolHTTPServerTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = Path(self.temporary_directory.name)
        (self.app / "index.html").write_text("<title>DoL test</title>", encoding="utf-8")
        (self.app / "VERSION").write_text("9.8.7-test", encoding="utf-8")
        (self.app / "mods").mkdir()
        write_mod(self.app / "mods" / "official-i18n.mod.zip", "ModI18N")
        write_mod(self.app / "mods" / "official-images.mod.zip", "GameOriginalImagePack")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_mod_formula_default_matches_no_mods(self):
        parser = SERVER.build_parser("dol-chs-mod", self.app)
        default_args = parser.parse_args(["--no-open", "0"])
        explicit_args = parser.parse_args(["--no-mods", "--no-open", "0"])

        default_mods = SERVER.resolve_mods(
            "dol-chs-mod", self.app, default_args.mod_specs, default_args.no_mods
        )
        explicit_mods = SERVER.resolve_mods(
            "dol-chs-mod", self.app, explicit_args.mod_specs, explicit_args.no_mods
        )

        self.assertEqual([], default_mods)
        self.assertEqual(default_mods, explicit_mods)

    def test_no_mods_cannot_be_combined_with_selectors(self):
        parser = SERVER.build_parser("dol-chs-mod", self.app)
        args = parser.parse_args(["--no-mods", "--i18n", "--no-open", "0"])

        with self.assertRaisesRegex(SERVER.UserInputError, "cannot be combined"):
            SERVER.resolve_mods("dol-chs-mod", self.app, args.mod_specs, args.no_mods)

    def test_fixed_formula_always_loads_official_mods(self):
        mods = SERVER.resolve_mods("dol-chs", self.app, None)

        self.assertEqual(["ModI18N", "GameOriginalImagePack"], [mod.name for mod in mods])

    def test_selection_order_is_preserved(self):
        custom = self.app / "custom.mod.zip"
        write_mod(custom, "CustomMod")
        parser = SERVER.build_parser("dol-chs-mod", self.app)
        args = parser.parse_args([
            "--images",
            "--mod",
            str(custom),
            "--i18n",
            "--no-open",
            "0",
        ])

        mods = SERVER.resolve_mods("dol-chs-mod", self.app, args.mod_specs)

        self.assertEqual(["GameOriginalImagePack", "CustomMod", "ModI18N"], [mod.name for mod in mods])

    def test_invalid_mod_is_rejected(self):
        invalid = self.app / "invalid.mod.zip"
        with zipfile.ZipFile(invalid, "w") as archive:
            archive.writestr("not-boot.json", "{}")

        with self.assertRaisesRegex(SERVER.UserInputError, "no boot.json"):
            SERVER.validate_mod_archive(invalid)

    def test_dynamic_routes_serve_only_selected_mods(self):
        custom = self.app / "a custom.mod.zip"
        expected = write_mod(custom, "CustomMod")
        parser = SERVER.build_parser("dol-chs-mod", self.app)
        args = parser.parse_args(["--mod", str(custom), "--no-open", "0"])
        mods = SERVER.resolve_mods("dol-chs-mod", self.app, args.mod_specs)
        handler = SERVER.make_handler(self.app, mods, "HTTP/1.0", True)
        server = SERVER.make_server("127.0.0.1", 0, handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(f"{base_url}/modList.json") as response:
                mod_list = json.load(response)
            self.assertEqual(["/__dol_mods__/0/a%20custom.mod.zip"], mod_list)

            with urllib.request.urlopen(f"{base_url}{mod_list[0]}") as response:
                self.assertEqual(expected, response.read())

            with self.assertRaises(urllib.error.HTTPError) as context:
                urllib.request.urlopen(f"{base_url}/__dol_mods__/1/a%20custom.mod.zip")
            self.assertEqual(404, context.exception.code)
            context.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_browser_url_handles_wildcard_and_ipv6_addresses(self):
        self.assertEqual("http://127.0.0.1:8000/", SERVER.browser_url("0.0.0.0", 8000))
        self.assertEqual("http://[::1]:8000/", SERVER.browser_url("::", 8000))


if __name__ == "__main__":
    unittest.main()
