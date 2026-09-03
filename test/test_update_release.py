from __future__ import annotations

import importlib.util
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "update-release"
LOADER = SourceFileLoader("update_release", str(MODULE_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC and SPEC.loader
UPDATER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = UPDATER
LOADER.exec_module(UPDATER)


def asset(name: str, digest_character: str) -> dict:
    return {
        "name": name,
        "browser_download_url": f"https://example.invalid/{name}",
        "digest": f"sha256:{digest_character * 64}",
    }


class UpdateReleaseTest(unittest.TestCase):
    def test_parse_release_selects_non_polyfill_assets(self):
        payload = {
            "tag_name": "v1.2.3.4-chs-5.6.7a",
            "assets": [
                asset("DoL-ModLoader-1.2.3.4-v8.9.0.zip", "a"),
                asset("DoL-ModLoader-1.2.3.4-v8.9.0-polyfill.zip", "b"),
                asset("ModI18N-1.2.3.4-chs-5.6.7a.mod.zip", "c"),
                asset("GameOriginalImagePack-1.2.3.4.mod.zip", "d"),
            ],
        }

        release = UPDATER.parse_release(payload)

        self.assertEqual("1.2.3.4-chs-5.6.7a", release.version)
        self.assertEqual("DoL-ModLoader-1.2.3.4-v8.9.0.zip", release.game.name)
        self.assertEqual("c" * 64, release.i18n.sha256)
        self.assertEqual("d" * 64, release.images.sha256)

    def test_formula_update_is_complete_and_idempotent(self):
        release = UPDATER.Release(
            tag="v9.8.7.6-chs-5.4.3b",
            version="9.8.7.6-chs-5.4.3b",
            game=UPDATER.Asset(
                "DoL-ModLoader-9.8.7.6-v2.0.0.zip",
                "https://example.invalid/DoL-ModLoader-9.8.7.6-v2.0.0.zip",
                "a" * 64,
            ),
            i18n=UPDATER.Asset(
                "ModI18N-9.8.7.6-chs-5.4.3b.mod.zip",
                "https://example.invalid/ModI18N-9.8.7.6-chs-5.4.3b.mod.zip",
                "b" * 64,
            ),
            images=UPDATER.Asset(
                "GameOriginalImagePack-9.8.7.6.mod.zip",
                "https://example.invalid/GameOriginalImagePack-9.8.7.6.mod.zip",
                "c" * 64,
            ),
        )
        content = (ROOT / "Formula" / "dol-chs.rb").read_text(encoding="utf-8")
        updated = UPDATER.update_formula(content, release)

        self.assertIn('version "9.8.7.6-chs-5.4.3b"', updated)
        self.assertIn(release.game.url, updated)
        self.assertIn(release.game.sha256, updated)
        self.assertIn(release.i18n.url, updated)
        self.assertIn(release.i18n.sha256, updated)
        self.assertIn(release.images.url, updated)
        self.assertIn(release.images.sha256, updated)
        self.assertEqual(updated, UPDATER.update_formula(updated, release))


if __name__ == "__main__":
    unittest.main()
