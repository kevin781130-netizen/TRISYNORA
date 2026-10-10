# Eighth knife — owner-of-truth and duplicate-capability gate

**Decision: Do not connect DeepSeek Harness Jobs to Vera, MiniMax-H3 or PointFlux native tasks.**

The only intended reuse of Harness is its separate chat/model/session/MCP interface. It is not a second Vera, second H3 Director or another PointFlux engine.

## Capability ownership

| Capability family | Sole owner | Harness job/control integration |
| --- | --- | --- |
| Coding Agent, run state, progress, cancel, checkpoints, verification, patch apply approval and code model routing | Vera | **DENIED** |
| Director workflows, ComfyUI graph control, take review, retakes and H3 asset publication approval | MiniMax-H3 | **DENIED** |
| Scene IR, render/optimization/validation/temporal judge, particle/audio execution and import approval | PointFlux | **DENIED** |
| External conversation UI, Harness-local model selection, Session history and Harness-internal Jobs | DeepSeek Harness | Allowed only for its own sandbox |
| Catalog-only lookup and inspection of a separate verified package | TRISYNORA | Allowed, strictly read-only |

Relevant source evidence from repository inspection:
- [Vera README](https://github.com/kevin781130-netizen/vera/blob/main/README.md), Vera active_run_status.py and test_agent_run_inspector_browser.py: existing run command center, progress/evidence and explicit run approval. Vera declares its commercial Beta NOT production ready.
- [MiniMax-H3 README](https://github.com/kevin781130-netizen/minimax-H3/blob/main/README.md): native Director owns creative workflow, ComfyUI graph changes and take choices.
- [PointFlux README](https://github.com/kevin781130-netizen/PointFlux/blob/main/README.md): deterministic Scene IR, compile, render and judge are native responsibilities.
- [Official Harness Jobs README](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/client/ui-jobs/README.md): the panel is NOT presentation only; a built-in stop action calls ctx.jobs.kill. Mirroring Vera run IDs would create a competing stop/control authority.

## Actual automated gate

- **capability_ownership.json**: exact single-owner map and explicit NO values for native job mirroring, cancelling, scheduling, command execution, write, approval substitution, worktree mount and runtime connection.
- **ownership_gate.py**: separately pinned owner baseline, three MCP tool names, read-only-only arguments and annotations, product catalog claims, and the complete Cordis plugin insertion. Unauthorized new Jobs plugins, native tools, owner transfers or approval flags make CI fail.
- **test_ownership_gate.py**: adversarial tests deliberately attempt in-memory owner reassignment, native kill, native connection claims, MCP tool additions and plugin insertion, and require refusal.
- **GitHub Actions**: runs the ownership gate before the existing MCP protocol and browser integration checks.

Run locally from TRISYNORA root:

    python -B experiments/deepseek-harness/ownership_gate.py

    python -B -m unittest discover -s experiments/deepseek-harness -p "test_*.py" -v

## Non-claims and hard boundaries

This gate audits only TRISYNORA's declared MCP plugin and bridge capability surface. It does NOT remove or certify stock Harness Shell, filesystem, process or network tools. Launching Harness still requires a disposable OS sandbox/VM with NO native repository, credential or network access to native services. Neither the MCP annotations nor a read-only CLI mode is a host-security boundary.

Vera, H3 and PointFlux are NOT runtime connected by this experiment. All native catalog entries remain uncallable. A future product-owned status receipt needs its own separate review, verified provenance and freshness, and must not be fed into Harness job.list/job.kill as a shadow controller.

**No changes to the three product repositories. No integration into native Jobs. No PR merge.**
