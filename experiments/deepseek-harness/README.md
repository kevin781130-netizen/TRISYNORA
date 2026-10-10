# DeepSeek Harness optional console bridge — isolated spike v0.1

**This experiment is an independent side branch based on TRISYNORA `main`, not on draft PR #1–#7.** It is not a fourth Director, a production integration, or a native Vera/H3/PointFlux adapter.

## Scope: reuse the useful DeepSeek Harness features without importing its Agent core

| Actual DeepSeek module | Reuse strategy | Stage |
| --- | --- | --- |
| Web and conversation UI (`dsh-web-app`, `client/ui-chat`) | Run unmodified in a separate DSH installation | **VERIFIED** real Chromium chat → Agent → MCP → rendered response, keyless mock provider |
| Provider-neutral LLM/model switching (`llm/*`) | Keep inside external DSH process, never embed into Vera | **VERIFIED** official Web picker selects `deepseek-v4-pro`, actual request wire confirms ID; third-party routes untested |
| MCP client (`@deepseek-ai/dsh-mcp-client`) | External DSH connects to the tiny read-only MCP server in this folder | **VERIFIED** official DSH Agent Loop and Web Browser route via actual stdio MCP |
| User approval UI (`client/ui-approval`) | Use only for UI presentation; **cannot authorize native writes** | Conceptual, native binding deliberately absent |
| Background job panel (`client/ui-jobs`) | Keep **Harness-internal only**. Never mirror native Vera/H3/PointFlux tasks into `job.list` or delegate `job.kill` | **DO NOT CONNECT** to native jobs; overlapping owner/control risk |
| Harness Session persistence, browser reconnect and Host cold restart | Keep native DSH session log in isolated DSH_HOME; select historic Session from official Web sidebar | **VERIFIED** full Chromium restart and separate Host process termination/restart with original MCP result on model request wire |
| Cordis Agent Loop, workflow/subagents, bash/FS/process | **Do not transplant into TRISYNORA**; native project ownership remains separate | Forbidden native access |

DeepSeek Harness is MIT licensed, but its included packages and dependencies have separate notices. **This spike copies no third-party source code**, only provides an integration configuration for its published runtime. DeepSeek Harness is still an **experimental developer preview, not security-audited**. Treating its approval UI or read-only setting as sufficient security is unsafe.

See original sources:
- [Harness repo](https://github.com/deepseek-ai/deepseek-harness)
- [Architecture](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.zh.md)
- [MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)
- [Safety statement](https://github.com/deepseek-ai/deepseek-harness/blob/master/SAFETY.zh.md)
- [MIT and third-party notices](https://github.com/deepseek-ai/deepseek-harness/blob/master/LICENSE)

## Eighth knife — owner-of-truth is now a CI gate

Vera already owns Agent run state, terminal approval, verification and code
model routing. MiniMax-H3 owns Director workflows and Take approval; PointFlux
owns deterministic Scene IR, rendering and judgment. The shipped Harness
Jobs UI has its own stop button and job-kill Remote, so it must **not** control
native runs or pretend to be a second Vera command center.

See [OWNERSHIP_BOUNDARY.md](OWNERSHIP_BOUNDARY.md) and the exact
[capability_ownership.json](capability_ownership.json) mapping. CI invokes
[ownership_gate.py](ownership_gate.py) before ordinary protocol/E2E tests
and rejects native job mirroring, stop/retry, write/apply approval, extra
MCP commands and DSH patch expansions. The positive and tampered-policy
regressions are in [test_ownership_gate.py](test_ownership_gate.py).

The gate is **limited to bridge/patch/tool declarations**; it does not
disable the upstream DSH stock Shell/FS/Process tools. Running the DSH
Web profile still requires a disposable sandbox with no native source
mounts or credentials. The three native products remain NOT CONNECTED.

## Ninth knife — product-owned read-only status receipt contract (not connected)

Vera retains verification Run/approval authority; H3 owns Director/Take
execution; PointFlux owns its deterministic render/optimization. We have
added a **separate, bounded, read-only *snapshot format*** for their future
product-approved exporters, not another Agent or Harness Jobs controller.

- [STATUS_RECEIPT_CONTRACT.md](STATUS_RECEIPT_CONTRACT.md) defines the exact
  v1 subject mapping, constrained progress/outcome, expiration, SHA-256,
  strict JSON and source-provenance requirements.
- [status_receipt.py](status_receipt.py) is a pure Python, standard-library
  validator. It does **no network, disk or native product I/O**. Results
  always state `producerAuthenticityVerified=false` and
  `usableAsAuthoritativeNativeStatus=false`: a self-contained SHA-256
  digest cannot authenticate the asserted product author.
- [test_status_receipt.py](test_status_receipt.py) exercises all three
  fake producer formats and rejects malformed, stale, replayed, tampered,
  overprivileged or mismatched input.
- This does **not** add a fourth MCP tool, a real producer connector,
  signing credentials, a Jobs mirror or any native workflow changes.
  Publisher-side authentication and trusted status display remain separate,
  product-owner-approved follow-up work.

## The executable deliverable

`readonly_mcp.py` is a **standalone Python-standard-library** stdio MCP server. Its *entire* callable surface is:

1. `trisynora_list_capabilities`: declares Vera, MiniMax-H3, PointFlux capabilities, **all unconnected and uncallable**.
2. `trisynora_check_capability`: checks whether a known capability can be called; currently always `not-connected`.
3. `trisynora_inspect_package`: **reads only** operator-selected `TRISYNORA_EXCHANGE_ROOT/<packageId>`, checks a completion receipt, both digest-locked manifests, safe local media path, declared 128 MiB cap and actual SHA-256. Reports `verified-reference-only` — *not* playable media, native source authorization or completed import.

There are **no** native command, filesystem edit, network, approval-grant, shell or repo-writer MCP tools.

This experiment references P1 `trisynora.asset/v1` and `trisynora.shot/v1` **envelope conventions**; since the constitutional PR and H3 handoff PR remain unmerged, actual compatibility must be retested against approved future main. It does not claim to enforce every field of their complete JSON Schema.

## Required isolated local filesystem layout

Do **not** run DSH with Vera, H3 or PointFlux source repositories mounted/visible. For a first prototype use a **disposable container/VM**, separate from those projects, with only these two read-only mounts:

```text
/opt/trisynora/readonly_mcp.py          # optional MCP script (read-only)
/opt/trisynora/dsh.patch.yml            # optional Harness profile patch
/exchange/.trisynora-exchange-root.json # operator-controlled trust marker
/exchange/take_001/ready.json
/exchange/take_001/manifests/asset.json
/exchange/take_001/manifests/shot.json
/exchange/take_001/assets/<artifactId>.mp4
```

`/exchange` **must not be under any Git checkout** (Vera/H3/PointFlux/TRISYNORA). The .json marker must contain:

```json
{"format":"trisynora.external-exchange-root/v1","kind":"read-only-staging"}
```

The operator should generate exchange packages with the separately reviewed P1 tool (after it passes its open security findings), then copy packages into this directory. The marker is **not authentication**, merely a defense against accidentally reading a random directory. The MCP adapter rejects symlinks, paths with traversal, missing or inconsistent receipts, fake write approvals and damaged media. A true hostile local user or concurrent filesystem writer requires stronger OS-level sandbox and verified file-descriptor pinning.

### Harness patch integration

The adjacent `dsh.patch.yml` uses the official published **Cordis** `- insert:` syntax to add `@deepseek-ai/dsh-mcp-client` over stdio. The two absolute paths are **examples**; set them to the mounted paths in your *separate* Harness sandbox.

Example shell **inside that isolated VM/container only**:

```sh
export DSH_PERMISSION_MODE=read-only
export DSH_TELEMETRY_DISABLED=1
# Install a pinned and independently reviewed published dsh version first.
dsh web --no-open --patch /opt/trisynora/dsh.patch.yml
```

Refer to Harness's [profile and patch guide](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.zh.md). Do **not** assume the `read-only` setting disables every default built-in terminal, filesystem, browser or subprocess path. A standard DSH Web profile may still register its own tools. **The hard boundary is the operating-system sandbox with no native-product mounts/credentials/network reachability**, not this YAML or an LLM's compliance.

The only authenticated native capability grants must be issued by **each actual product's own adapter and human permissions** in a future, separately reviewed product-specific PR. Merely clicking Approve in Harness **must never** grant permission to write a Vera, H3 or PointFlux workspace.

## Verified integration boundary and pinned upstream packages

- DSH Web launcher: **`@deepseek-ai/dsh@0.2.0-rc.2`**, installed from npm in a clean GitHub Actions temporary directory; the independent test checks that the official `--dump-config` includes our MCP plugin and the launched Web profile actually answers HTTP. No model is invoked.
- Real MCP Client: **`@modelcontextprotocol/client@2.2.0`**, exactly the dependency used by upstream `dsh-mcp-client` in the inspected source. It launches `readonly_mcp.py` with stdio, lists three tools, calls the declared capability lookup, checks an actual digest-locked synthetic exchange package, and proves tampered media and write requests are rejected.
- **Actual DSH Agent Loop (headless):** a temporary loopback-only mock Messages provider asks for `mcp__trisynora__trisynora_list_capabilities` and receives the genuine MCP result. The CI verifier requires a later model request to contain the model-facing `tool_result`, exact MCP tool name, and `catalog-only` payload. No paid model key, outbound inference, or native product call. This is separate from the official Web startup check and will be credited only after the head's actual CI passes.
- **Browser verified:** the real Chromium UI opens an authenticated DSH Web session, sends through the shipped composer, invokes the actual MCP client and renders the real catalog-only receipt. Separate regression checks the official model picker changes the *actual wire model* to `deepseek-v4-pro`. A third check kills Chromium, reconnects with a fresh browser process, selects the old Session in the official sidebar, observes the original MCP transcript, and confirms the follow-up model request contains both historic user turn and MCP result. All three checks use a keyless local mock provider. A **fourth cold-restart gate** runs the original browser/MCP session, terminates its owning DSH Host and confirms its loopback port is released, starts a brand-new DSH Host process with the SAME isolated HOME/DSH_HOME/work directory, opens an entirely fresh Chromium instance on the newly authenticated URL, selects the original Session, and continues it. The new Host model request MUST contain both historical and new user prompts plus historical MCP tool response and still use `deepseek-v4-pro`. The original DSH Host stays stopped for the entire recovery phase.
- The contract is intended to be compatible with P1 envelope structure, with strict optional pilot limits. Source provenance is user-declared: **not native H3 signature/consent**.

## Developer and CI tests

```sh
python3 -B -m unittest discover -s experiments/deepseek-harness -p 'test_*.py' -v
```

The CI tests run independent Python protocol/contract checks, genuine MCP SDK stdio, official DSH Web startup, actual DSH Headless Agent Loop, and **four separate Playwright Chromium Web-session gates**: browser→MCP, browser model-picker→correct model ID→MCP, and full browser-process termination→old Session restoration→continued message with historic MCP context on the wire. The fourth gate covers actual Host process restart and requires old Session persistence across it. No native product, actual movie decoding, external model API provider, or real model key is used.

**Acceptance status (limited):**
- MCP unit and direct stdio contract: **VERIFIED** after checking CI at the current head.
- Official MCP Client SDK discovers and invokes tools: **VERIFIED** after checking CI at the current head.
- Official DSH Web startup and patch inclusion: **VERIFIED** after checking CI at the current head.
- Official DSH Headless Agent Loop → MCP real tool response → second/subsequent mock model request: **VERIFIED ONLY IF** the standalone headless gate passes on the exact current CI head.
- Web browser Agent session invoking MCP: **VERIFIED** with keyless scripted provider and real Chromium.
- Official Web UI model switching: **VERIFIED** exact `deepseek-v4-pro` ID in actual local provider requests.
- Independent Chromium process restores historical Session, prior MCP result and model selection, then continues old Session with running Host: **VERIFIED**.
- Full DSH Host termination and restart, distinct PID/port, same isolated durable profile and Session storage, fresh Chromium old-session recovery, historical MCP content on the new Host's model wire: **VERIFIED** against keyless local mock provider. CI evidence: [Push #38085407717](https://github.com/kevin781130-netizen/TRISYNORA/actions/runs/38085407717) and [PR #38085412395](https://github.com/kevin781130-netizen/TRISYNORA/actions/runs/38085412395) at `eee4f6fb`.
- Real model-provider credentials/external API, OS crash/power failure recovery, production session durability and concurrent Host ownership: **NOT VERIFIED**.
- Real H3/PointFlux/Vera adapters, approvals, and video import: **NOT IMPLEMENTED**.
- Native product standalone regressions and actual three-project isolation: **NOT VERIFIED**.
- All seven constitutional PRs: untouched, unmerged, and remain review-blocked where documented.

**Next separate authorization gate:** producer-owned signed export and independent trust anchors for the status-receipt format. Until signature/channel verification and actual product approvals pass, the current snapshots remain **untrusted and disconnected**; do not add an MCP status tool or Job mirror. Never delegate cancel/retry/apply/approve powers or native code mounts to Harness.
