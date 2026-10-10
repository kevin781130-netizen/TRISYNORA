"""Repo-local non-contamination guard.

This guard inspects only TRISYNORA's own working tree. It cannot prove the
standalone/runtime state of the three *other* repositories; that needs real E2E.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_ROOTS = {
    "vera", "minimax-h3", "pointflux", "backend", "frontend", "src",
    "node_modules", "vendor", "upstream", "third_party", "third-party",
}


class ConstitutionalBoundary(unittest.TestCase):
    def test_constitution_present_and_highest_authority(self):
        constitution = (ROOT / "CONSTITUTION.md").read_text(encoding="utf-8")
        self.assertIn("Zero Cross-Project Contamination", constitution)
        self.assertIn("No TRISYNORA task", constitution)
        self.assertIn("Standalone", constitution)

    def test_no_embedded_product_or_runtime_roots(self):
        existing = {p.name.casefold() for p in ROOT.iterdir() if p.is_dir()}
        self.assertEqual(existing & FORBIDDEN_ROOTS, set())

    def test_no_git_submodules_or_mutable_shared_store(self):
        self.assertFalse((ROOT / ".gitmodules").exists())
        self.assertFalse((ROOT / "database.sqlite").exists())
        self.assertFalse((ROOT / "runtime.db").exists())
        self.assertFalse((ROOT / "secrets.env").exists())


if __name__ == "__main__":
    unittest.main()
