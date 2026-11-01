from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media_rights import MediaRightsError, validate_media_permission  # noqa: E402


class MediaRightsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.asset = self.root / "assets" / "audio" / "test.mp3"
        self.asset.parent.mkdir(parents=True)
        self.asset.write_bytes(b"placeholder audio")
        self.manifest_path = self.asset.parent / "audio-rights.json"

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self, **changes):
        manifest = {
            "asset_file": "assets/audio/test.mp3",
            "rights_holder": "Rights holder example",
            "license_name": "Written permission for YouTube reuse",
            "license_url": "",
            "permission_evidence_file": "assets/audio/permission.txt",
            "youtube_upload_allowed": True,
            "attribution": "",
        }
        manifest.update(changes)
        (self.asset.parent / "permission.txt").write_text("Evidence placeholder", encoding="utf-8")
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def validate(self):
        return validate_media_permission(
            root=self.root,
            asset_path=self.asset,
            manifest_path=self.manifest_path,
            media_kind="audio",
        )

    def test_accepts_explicit_written_permission_evidence(self):
        self.write_manifest()
        self.assertTrue(self.validate()["youtube_upload_allowed"])

    def test_rejects_missing_manifest(self):
        with self.assertRaisesRegex(MediaRightsError, "Missing"):
            self.validate()

    def test_rejects_permission_not_explicitly_granted(self):
        self.write_manifest(youtube_upload_allowed=False)
        with self.assertRaisesRegex(MediaRightsError, "not explicitly approved"):
            self.validate()

    def test_rejects_mismatched_asset_path(self):
        self.write_manifest(asset_file="assets/audio/other.mp3")
        with self.assertRaisesRegex(MediaRightsError, "must match"):
            self.validate()

    def test_license_url_requires_attribution(self):
        self.write_manifest(license_url="https://example.org/license", permission_evidence_file="", attribution="")
        with self.assertRaisesRegex(MediaRightsError, "attribution"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
