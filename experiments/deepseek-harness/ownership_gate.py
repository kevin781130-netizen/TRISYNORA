#!/usr/bin/env python3
"""Fail-closed, stdlib-only bridge capability ownership/overlap acceptance gate.

This audits TRISYNORA policy and its actually configured MCP plugin surface,
NOT the built-in DSH shell/FS tools or any mounted native product runtime.
OS sandbox isolation remains mandatory for launching Harness.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
POLICY = HERE / "capability_ownership.json"
PATCH = HERE / "dsh.patch.yml"

# Independent, explicitly reviewed owner-of-truth baseline. Changing the JSON
# alone cannot silently transfer authority; this code and its tests must also
# be reviewed (and the native product owner must separately authorize changes).
EXPECTED_OWNERS = {
    "vera": (
        "agent-run-control", "agent-run-history-and-progress",
        "code-verification-and-repair", "patch-apply-approval",
        "code-model-routing", "code-session-checkpoints",
    ),
    "minimax-h3": (
        "director-and-storyboard-workflow", "comfyui-workflow-control",
        "video-generation-and-take-review", "director-override-and-retake",
        "h3-asset-export-approval",
    ),
    "pointflux": (
        "scene-ir-and-patches", "scene-validation-and-compilation",
        "particle-and-motion-runtime", "deterministic-render-and-composition",
        "visual-judge-and-optimization", "pointflux-import-approval",
    ),
    "deepseek-harness": (
        "optional-external-chat-ui", "harness-only-model-selection",
        "harness-only-session-history", "read-only-mcp-client",
        "harness-internal-jobs-only",
    ),
    "trisynora": (
        "declared-capability-catalog", "not-connected-lookup",
        "isolated-package-reference-inspection",
    ),
}

EXPECTED_CAPABILITIES = {
    "vera": ("governance-evidence", "validate-handoff"),
    "minimax-h3": ("video-export", "approved-take-reference"),
    "pointflux": ("particle-render", "video-layer-import"),
}
EXPECTED_TOOL_NAMES = (
    "trisynora_list_capabilities",
    "trisynora_check_capability",
    "trisynora_inspect_package",
)
EXPECTED_HARNESS_NATIVE_DENIALS = (
    "nativeJobMirror", "nativeJobCancel", "nativeJobSchedule",
    "nativeCommandExecution", "nativeWrite", "nativeApprovalSubstitution",
    "nativeCredentialsOrWorktreeMount", "nativeRuntimeConnection",
)
EXPECTED_BRIDGE_FLAGS = (
    "nativeProductsConnected", "nativeWriteToolsExposed",
    "productOwnedStatusAdapterConnected", "packageImportAuthorized",
)

# Pin the *entire* actual DSH Cordis plugin insert rather than trust a
# superficial "read-only" flag. The shipped DSH Web may still expose powerful
# default tools, hence this does NOT itself enforce OS-level isolation.
PINNED_PATCH = """- insert:
    - id: trisynora-readonly-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: trisynora
        transport: stdio
        command: python3
        args: ['-B', '/opt/trisynora/readonly_mcp.py']
        env:
          TRISYNORA_EXCHANGE_ROOT: /exchange
          PYTHONDONTWRITEBYTECODE: '1'
        failOnStartupError: true
        toolCallTimeoutMs: 15000
        maxInstructionBytes: 1024
        reconnect:
          enabled: false
"""


class OwnershipViolation(ValueError):
    """Policy or MCP tool expansion requires a separate human review."""


def _ensure(ok: bool, reason: str) -> None:
    if not ok:
        raise OwnershipViolation(reason)


def _exact_keys(value: Any, keys: set[str], where: str) -> None:
    _ensure(isinstance(value, dict) and set(value) == keys,
            where + " has unexpected or missing fields")


def verify(policy: Any, products: Any, tools: Any, patch_text: str,
           catalog: Any) -> None:
    _exact_keys(policy, {
        "schema", "status", "ownership", "harnessToNative", "bridge",
        "sources", "validationScope",
    }, "policy")
    _ensure(policy["schema"] == "trisynora.capability-ownership/v1",
            "wrong policy schema")
    _ensure(policy["status"] == "experiment-only-no-native-connections",
            "native product connections require a separate review")

    owners = policy["ownership"]
    _exact_keys(owners, set(EXPECTED_OWNERS), "owner registry")
    _ensure(all(
        isinstance(owners[p], list)
        and tuple(owners[p]) == EXPECTED_OWNERS[p]
        for p in EXPECTED_OWNERS
    ), "authority owner reassignment or duplication")
    flat = [cap for caps in owners.values() for cap in caps]
    _ensure(len(flat) == len(set(flat)),
            "one capability may not have multiple execution owners")

    native_flags = policy["harnessToNative"]
    _exact_keys(native_flags, set(EXPECTED_HARNESS_NATIVE_DENIALS),
                "external Harness native authority")
    _ensure(all(native_flags[k] is False for k in native_flags),
            "Harness cannot mirror, stop, schedule, approve or write native jobs")

    bridge = policy["bridge"]
    _exact_keys(bridge, set(EXPECTED_BRIDGE_FLAGS), "bridge native status")
    _ensure(all(bridge[k] is False for k in bridge),
            "bridge must not claim a native connection, approval or write")

    _ensure(
        policy["validationScope"] ==
        "TRISYNORA bridge policy and configured MCP surface only; "
        "no runtime audit of native repositories or of stock DSH built-in tools",
        "OS/native runtime scope may not be misrepresented",
    )
    _exact_keys(policy["sources"], {
        "vera", "minimax-h3", "pointflux", "harness-jobs",
    }, "source references")
    _ensure(all(
        isinstance(v, str) and v.startswith("https://github.com/")
        for v in policy["sources"].values()
    ), "source references must be public git URLs")

    _ensure(isinstance(products, dict) and {
        k: tuple(v) for k, v in products.items()
    } == EXPECTED_CAPABILITIES, "MCP product catalog silently changed")
    _ensure(isinstance(tools, list) and len(tools) == len(EXPECTED_TOOL_NAMES),
            "extra MCP tools exposed")
    _ensure(tuple(t.get("name") for t in tools) == EXPECTED_TOOL_NAMES,
            "MCP tool registry changed or added a native action")
    for t in tools:
        a = t.get("annotations")
        _ensure(
            isinstance(a, dict)
            and a.get("readOnlyHint") is True
            and a.get("destructiveHint") is False
            and a.get("openWorldHint") is False,
            "MCP tool permission annotation changed",
        )
        schema = t.get("inputSchema")
        _ensure(
            isinstance(schema, dict)
            and schema.get("type") == "object"
            and schema.get("additionalProperties") is False,
            "MCP tool input becomes extensible/unsafe",
        )
    _ensure(
        isinstance(catalog, dict)
        and catalog.get("status") == "catalog-only"
        and catalog.get("mcpReadOnly") is True
        and catalog.get("nativeWriteToolsExposed") is False
        and catalog.get("operatorApprovalSubstituted") is False,
        "MCP response overstates native authority",
    )
    _ensure(
        len(catalog.get("products", [])) == 3
        and {item.get("id") for item in catalog["products"]}
        == set(EXPECTED_CAPABILITIES)
        and all(
            item.get("connected") is False
            and all(
                sub.get("callable") is False
                and sub.get("nativePermissionGranted") is False
                for sub in item.get("declaredCapabilities", [])
            )
            for item in catalog["products"]
        ),
        "product capability state claims execution or connection",
    )

    # Remove only comment/empty header lines; retain every executable plugin
    # line. A new Cordis job-controller, privileged MCP server, mount, etc.,
    # fails this exact-match gate even if its name looks innocuous.
    lines = patch_text.splitlines()
    while lines and (not lines[0].strip()
                     or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    _ensure("\n".join(lines).strip() == PINNED_PATCH.strip(),
            "DSH patch modified: extra plugin/job/controller capability")


def check_files() -> None:
    from readonly_mcp import PRODUCTS, TOOLS, dispatch
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    verify(policy, PRODUCTS, TOOLS, PATCH.read_text(encoding="utf-8"),
           dispatch("trisynora_list_capabilities", {}))


def main() -> int:
    try:
        check_files()
    except (OwnershipViolation, OSError, ValueError, KeyError, TypeError,
            ImportError) as error:
        print(json.dumps({
            "status": "ownership-gate-fail",
            "reason": type(error).__name__,
            "nativeAuthorityGranted": False,
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "status": "ownership-gate-pass",
        "capabilityOwners": len(EXPECTED_OWNERS),
        "mcpTools": len(EXPECTED_TOOL_NAMES),
        "harnessNativeJobControl": False,
        "harnessNativeWriteAuthorized": False,
        "nativeProductsConnected": False,
        "stockHarnessToolsAudited": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
