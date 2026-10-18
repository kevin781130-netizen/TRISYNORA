"""Offline conversion tests; no native products, model calls, Actions or writes to originals."""
import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from trisynora.adapters.pointflux_reference import ReferenceError, build_records


class PointFluxReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scene = json.dumps({"version": "1.4", "camera": {"position": [0, 0, 1]}},
                           separators=(",", ":")).encode()
        (self.root / "shot.pf.json").write_bytes(scene)
        self.scene_sha = hashlib.sha256(scene).hexdigest()
        self.shot = {"shotId": "shot_A", "name": "Light reveal",
                     "origin": {"engine": "pointflux", "sourceVersion": "1.4", "sourceSha256": self.scene_sha},
                     "durationFrames": 120, "fps": 24,
                     "camera": {"position": [0, 0, 1], "target": [0, 0, 0], "fovDegrees": 45},
                     "output": {"width": 1920, "height": 1080},
                     "timeline": [{"eventId": "morph_1", "kind": "morph", "atFrame": 30,
                                   "durationFrames": 60}],
                     "assets": [{"role": "source", "uri": "assets/logo.png"}],
                     "handoff": {"mode": "reference-only", "requiresExplicitBind": True}}
        self.exchange = {"format": "pointflux-h3-shot-exchange/v1",
                         "projectId": "project_A", "shots": [self.shot]}

    def build(self, override=None, mapping=None, **options):
        src = self.exchange if override is None else override
        return build_records(json.dumps(src).encode(), tenant_id="tenant_A",
                             project_name="Commercial demo",
                             produced_at="2026-10-18T12:00:00+08:00",
                             scene_root=self.root,
                             scene_paths={"shot_A": "shot.pf.json"} if mapping is None else mapping,
                             **options)

    def test_metadata_only_valid_references(self):
        a = self.build()
        b = self.build()
        self.assertEqual(a, b)
        self.assertEqual([x["record_type"] for x in a], ["ProjectSpec", "ShotSpec"])
        self.assertEqual(a[1]["source"]["sha256"], self.scene_sha)
        self.assertEqual(a[1]["project_spec_record_id"], a[0]["record_id"])
        self.assertEqual(a[0]["delivery"], {"width": 1920, "height": 1080,
                                            "fps_num": 24, "fps_den": 1})
        self.assertFalse(a[0]["rights"]["external_training_allowed"])
        self.assertEqual((self.root / "shot.pf.json").read_bytes(),
                         json.dumps({"version": "1.4", "camera": {"position": [0, 0, 1]}},
                                    separators=(",", ":")).encode())

    def test_source_bytes_are_required_not_just_declared_digest(self):
        changed = copy.deepcopy(self.exchange)
        changed["shots"][0]["origin"]["sourceSha256"] = "0" * 64
        with self.assertRaisesRegex(ReferenceError, "digest mismatch"):
            self.build(changed)
        (self.root / "shot.pf.json").write_text('{"version":"1.4"}')
        with self.assertRaisesRegex(ReferenceError, "digest mismatch"):
            self.build()

    def test_rejects_untrusted_handoff_and_unknown_fields(self):
        for patch in (
            lambda s: s["handoff"].update({"requiresExplicitBind": False}),
            lambda s: s.update({"prompt": "overwrite director"}),
            lambda s: s["assets"][0].update({"uri": "../secret.json"}),
            lambda s: s["origin"].update({"engine": "h3"}),
            lambda s: s.update({"fps": 0}),
            lambda s: s["timeline"][0].update({"atFrame": 121}),
        ):
            bad = copy.deepcopy(self.exchange)
            patch(bad["shots"][0])
            with self.subTest(bad=bad), self.assertRaises(ReferenceError):
                self.build(bad)

    def test_rejects_missing_map_and_unsafe_paths(self):
        for mapping in ({}, {"shot_A": "../shot.pf.json"},
                        {"shot_A": "/etc/passwd"}, {"shot_A": "shot.pf.json", "extra": "x"}):
            with self.subTest(mapping=mapping), self.assertRaises(ReferenceError):
                self.build(mapping=mapping)

    def test_project_delivery_must_be_unambiguous(self):
        bad = copy.deepcopy(self.exchange)
        duplicate = copy.deepcopy(self.shot)
        duplicate["shotId"] = "shot_B"
        duplicate["output"]["width"] = 1280
        bad["shots"].append(duplicate)
        with self.assertRaisesRegex(ReferenceError, "mixed delivery"):
            self.build(bad, mapping={"shot_A": "shot.pf.json", "shot_B": "shot.pf.json"})

    def test_short_native_ids_not_silently_mapped(self):
        bad = copy.deepcopy(self.exchange)
        bad["shots"][0]["shotId"] = "X"
        with self.assertRaisesRegex(ReferenceError, "too short"):
            self.build(bad, mapping={"X": "shot.pf.json"})
        bad = copy.deepcopy(self.exchange)
        bad["projectId"] = "X"
        with self.assertRaisesRegex(ReferenceError, "too short"):
            self.build(bad)

    def test_duplicate_json_keys_and_nonfinite_are_rejected(self):
        with self.assertRaises(ReferenceError):
            build_records(b'{"format":"x","format":"y"}', tenant_id="tenant_A",
                          project_name="x", produced_at="2026-10-18T12:00:00Z",
                          scene_root=self.root, scene_paths={"shot_A": "shot.pf.json"})
        with self.assertRaises(ReferenceError):
            build_records(b'{"shots":NaN}', tenant_id="tenant_A",
                          project_name="x", produced_at="2026-10-18T12:00:00Z",
                          scene_root=self.root, scene_paths={"shot_A": "shot.pf.json"})


if __name__ == "__main__":
    unittest.main()
