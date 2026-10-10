"""Offline JSON Schema and isolation conformance for synthetic v1 fixtures.

No Vera, H3, PointFlux, browser, ComfyUI, models or network access is required.
Fixture hashes are synthetic and do NOT constitute real render evidence.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("capability", "asset", "shot", "job", "evidence")


def load(kind: str, folder: str) -> dict:
    if folder == "schemas":
        file = ROOT / "schemas" / "v1" / f"{kind}.schema.json"
    else:
        file = ROOT / "examples" / "v1" / f"{kind}.json"
    return json.loads(file.read_text(encoding="utf-8"))


class ContractConformance(unittest.TestCase):
    def test_schemas_are_valid_draft_2020_12(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind):
                Draft202012Validator.check_schema(load(kind, "schemas"))

    def test_all_synthetic_fixtures_validate(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind):
                schema, fixture = load(kind, "schemas"), load(kind, "examples")
                Draft202012Validator(schema).validate(fixture)
                self.assertEqual(fixture["contract"], f"trisynora.{kind}/v1")

    def test_unknown_versions_and_undeclared_fields_fail_closed(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind):
                schema, fixture = load(kind, "schemas"), load(kind, "examples")
                invalid_version = copy.deepcopy(fixture)
                invalid_version["contract"] = f"trisynora.{kind}/v2"
                self.assertFalse(Draft202012Validator(schema).is_valid(invalid_version))
                unknown = copy.deepcopy(fixture)
                unknown["undocumentedAuthority"] = "allow"
                self.assertFalse(Draft202012Validator(schema).is_valid(unknown))

    def test_asset_path_cannot_escape_package(self) -> None:
        schema, fixture = load("asset", "schemas"), load("asset", "examples")
        for invalid in ("../secret", "/tmp/file.mp4", "C:/secret.mp4", "https://x.test/a.mp4", "assets/../../secret", "assets\\file.mp4", "assets//file.mp4"):
            with self.subTest(path=invalid):
                value = copy.deepcopy(fixture)
                value["media"]["path"] = invalid
                self.assertFalse(Draft202012Validator(schema).is_valid(value))

    def test_shot_cannot_implicitly_bind_and_asset_requires_approval(self) -> None:
        for kind, keys in (("shot", ("handoff", "requiresExplicitBind")), ("asset", ("publication", "requiresReceiverApproval"))):
            schema, fixture = load(kind, "schemas"), load(kind, "examples")
            invalid = copy.deepcopy(fixture)
            invalid[keys[0]][keys[1]] = False
            self.assertFalse(Draft202012Validator(schema).is_valid(invalid))

    def test_evidence_cannot_claim_vera_success(self) -> None:
        schema, fixture = load("evidence", "schemas"), load("evidence", "examples")
        bad = copy.deepcopy(fixture)
        bad["veraVerified"] = True
        self.assertFalse(Draft202012Validator(schema).is_valid(bad))
        bad = copy.deepcopy(fixture)
        bad["authority"] = "cross-product-final"
        self.assertFalse(Draft202012Validator(schema).is_valid(bad))
        bad = copy.deepcopy(fixture)
        bad["observation"]["verdict"] = "pass"
        bad["observation"]["executed"] = False
        self.assertFalse(Draft202012Validator(schema).is_valid(bad))

    def test_job_cannot_supply_arbitrary_commands_or_output_overwrites(self) -> None:
        schema, fixture = load("job", "schemas"), load("job", "examples")
        bad = copy.deepcopy(fixture)
        bad["operation"] = "shell-execute"
        self.assertFalse(Draft202012Validator(schema).is_valid(bad))
        bad = copy.deepcopy(fixture)
        bad["outputPolicy"]["mode"] = "overwrite-source"
        self.assertFalse(Draft202012Validator(schema).is_valid(bad))


if __name__ == "__main__":
    unittest.main()
