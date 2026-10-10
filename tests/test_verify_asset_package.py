"""Read-only asset manifest, digest and containment tests; no product runtime."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_asset_package import PackageVerificationError, verify_package  # noqa: E402


def example(media: bytes) -> dict:
    return {
        "contract": "trisynora.asset/v1",
        "artifactId": "asset_demo01",
        "origin": {"product": "minimax-h3", "projectId": "H3demo", "revision": "fixture-r1"},
        "media": {"kind": "video", "mimeType": "video/mp4", "sizeBytes": len(media),
                  "sha256": hashlib.sha256(media).hexdigest(), "path": "assets/take.mp4"},
        "publication": {"mode": "approved-copy", "requiresReceiverApproval": True},
    }


class TestPackageVerifier(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets").mkdir()
        self.media = b"synthetic-media-fixture-not-real-mp4"
        (self.root / "assets" / "take.mp4").write_bytes(self.media)
        self.manifest = example(self.media)
        self.save()

    def save(self) -> None:
        (self.root / "asset.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_positive_file_bytes_verified_without_authorization(self) -> None:
        result = verify_package(self.root)
        self.assertEqual(result["status"], "asset-bytes-verified")
        self.assertFalse(result["receiverAuthorized"])
        self.assertFalse(result["mediaSemanticsVerified"])
        self.assertFalse(result["crossProductE2EVerified"])

    def test_tampered_media_fails(self) -> None:
        (self.root / "assets" / "take.mp4").write_bytes(b"unapproved")
        with self.assertRaises(PackageVerificationError):
            verify_package(self.root)

    def test_same_size_digest_change_fails(self) -> None:
        (self.root / "assets" / "take.mp4").write_bytes(self.media[::-1])
        with self.assertRaisesRegex(PackageVerificationError, "SHA-256"):
            verify_package(self.root)

    def test_bad_manifest_contract_fails(self) -> None:
        self.manifest["contract"] = "trisynora.asset/v2"
        self.save()
        with self.assertRaisesRegex(PackageVerificationError, "schema invalid"):
            verify_package(self.root)

    def test_manifest_extra_authorization_field_fails(self) -> None:
        self.manifest["authorized"] = True
        self.save()
        with self.assertRaisesRegex(PackageVerificationError, "schema invalid"):
            verify_package(self.root)

    def test_parent_traversal_and_absolute_paths_fail(self) -> None:
        for path in ("../outside.mp4", "/etc/passwd", "C:/Windows/file", "https://invalid.test/p.mp4", "assets//take.mp4"):
            with self.subTest(path=path):
                self.manifest["media"]["path"] = path
                self.save()
                with self.assertRaises(PackageVerificationError):
                    verify_package(self.root)

    def test_symlink_media_fails_if_supported(self) -> None:
        source = self.root / "assets" / "take.mp4"
        dest = self.root / "assets" / "link.mp4"
        try:
            dest.symlink_to(source)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable on this OS")
        self.manifest["media"]["path"] = "assets/link.mp4"
        self.save()
        with self.assertRaisesRegex(PackageVerificationError, "symlink"):
            verify_package(self.root)

    def test_symlink_parent_fails_if_supported(self) -> None:
        link = self.root / "foreign"
        try:
            link.symlink_to(self.root / "assets", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable on this OS")
        self.manifest["media"]["path"] = "foreign/take.mp4"
        self.save()
        with self.assertRaisesRegex(PackageVerificationError, "symlink"):
            verify_package(self.root)

    def test_duplicate_json_keys_fail(self) -> None:
        (self.root / "asset.json").write_text('{"contract":"x","contract":"y"}', encoding="utf-8")
        with self.assertRaisesRegex(PackageVerificationError, "duplicate JSON key"):
            verify_package(self.root)

    def test_bound_on_bytes(self) -> None:
        with self.assertRaisesRegex(PackageVerificationError, "size mismatch or ceiling"):
            verify_package(self.root, max_bytes=2)


if __name__ == "__main__":
    unittest.main()
