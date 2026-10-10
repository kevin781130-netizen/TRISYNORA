"""Regression: duplicate Jobs and native authority cannot creep into Harness.

All negative cases mutate only ephemeral dictionaries/strings in memory.
No native Vera / H3 / PointFlux checkout or API is ever opened.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def _load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


g = _load("ownership_gate.py", "trisynora_ownership_gate")
m = _load("readonly_mcp.py", "trisynora_mcp_ownership_fixture")


class CapabilityOwnershipGateTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(g.POLICY.read_text(encoding="utf-8"))
        self.products = copy.deepcopy(m.PRODUCTS)
        self.tools = copy.deepcopy(m.TOOLS)
        self.patch = g.PATCH.read_text(encoding="utf-8")
        self.catalog = copy.deepcopy(m.dispatch(
            "trisynora_list_capabilities", {},
        ))

    def accept(self):
        g.verify(self.policy, self.products, self.tools,
                 self.patch, self.catalog)

    def deny(self):
        with self.assertRaises(g.OwnershipViolation):
            self.accept()

    def test_real_files_satisfy_exact_owner_of_truth_contract(self):
        g.check_files()
        self.accept()

    def test_jobs_controller_mirroring_cannot_be_enabled(self):
        self.policy["harnessToNative"]["nativeJobMirror"] = True
        self.deny()

    def test_jobs_cancel_cannot_cross_into_native_vera(self):
        self.policy["harnessToNative"]["nativeJobCancel"] = True
        self.deny()

    def test_native_job_schedule_must_remain_owner_only(self):
        self.policy["harnessToNative"]["nativeJobSchedule"] = True
        self.deny()

    def test_owner_reassignment_cannot_make_harness_run_vera(self):
        self.policy["ownership"]["deepseek-harness"].append("agent-run-control")
        self.deny()

    def test_native_approval_must_not_be_delegated(self):
        self.policy["harnessToNative"]["nativeApprovalSubstitution"] = True
        self.deny()

    def test_product_status_must_not_be_exaggerated(self):
        self.policy["bridge"]["productOwnedStatusAdapterConnected"] = True
        self.deny()

    def test_new_write_or_run_mcp_tool_is_rejected(self):
        template = copy.deepcopy(self.tools[0])
        template["name"] = "trisynora_kill_vera_run"
        self.tools.append(template)
        self.deny()

    def test_mutation_relabelled_readonly_is_rejected(self):
        self.tools[1]["name"] = "trisynora_execute_pointflux"
        self.deny()

    def test_tool_annotation_downgrade_is_rejected(self):
        self.tools[2]["annotations"]["readOnlyHint"] = False
        self.deny()

    def test_mcp_catalog_cannot_claim_native_product_connected(self):
        self.catalog["products"][0]["connected"] = True
        self.deny()

    def test_mcp_catalog_cannot_claim_native_write_exposed(self):
        self.catalog["nativeWriteToolsExposed"] = True
        self.deny()

    def test_native_product_registration_change_requires_review(self):
        self.products["vera"] = ("governance-evidence", "run-agent")
        self.deny()

    def test_dsh_patch_must_not_mount_shadow_jobs_controller(self):
        self.patch += "\n  - insert:\n      id: shadow-native-jobs\n"
        self.deny()

    def test_dsh_patch_must_not_change_execution_command(self):
        self.patch = self.patch.replace(
            "command: python3", "command: bash",
        )
        self.deny()

    def test_unknown_policy_field_requires_review(self):
        self.policy["harnessToNative"]["executeNow"] = False
        self.deny()

    def test_source_scope_cannot_claim_native_runtime_tested(self):
        self.policy["validationScope"] = "native projects fully audited"
        self.deny()


if __name__ == "__main__":
    unittest.main()
