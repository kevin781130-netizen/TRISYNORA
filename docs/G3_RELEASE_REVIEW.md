# G3 — TRISYNORA contract convergence, six-PR freeze and release gates

**最高憲法：Vera、MiniMax-H3、PointFlux 絕對不互相污染。** This is the strongest requirement. No TRISYNORA task may add native product code, a cross-product mutable database, implicit product write permissions, a fourth Agent/Director, or forced installation dependencies.

## 2026-10-11 freeze snapshot

The checked GitHub PR stack has **six draft PRs**, all individually reporting a successful **historic GitHub Actions execution at their frozen head**. The original PRs are **not merged**, and no release has been published.

| Review order | PR | Scope | Frozen CI tests |
| --- | --- | --- | --- |
| 1 | [#1](https://github.com/kevin781130-netizen/TRISYNORA/pull/1) | Highest constitution, ownership, five neutral schemas | 36 |
| 2 | [#2](https://github.com/kevin781130-netizen/TRISYNORA/pull/2) | H3-origin video staging and immutable Asset/Shot package | 49 |
| 3 | [#3](https://github.com/kevin781130-netizen/TRISYNORA/pull/3) | PointFlux dry-run receiver, reference only | 63 |
| 4 | [#4](https://github.com/kevin781130-netizen/TRISYNORA/pull/4) | Genuine 1-second H.264 FFprobe and FFmpeg decode | 78 |
| 5 | [#5](https://github.com/kevin781130-netizen/TRISYNORA/pull/5) | G1 SHA-256 and Git HEAD on three synthetic product repositories | 100 |
| 6 | [#6](https://github.com/kevin781130-netizen/TRISYNORA/pull/6) | G2 isolated end-to-end **synthetic** bridge rehearsal | 113 |

The authoritative machine-readable historic evidence is `governance/g3-freeze.json`. Its GitHub run IDs and commit SHA were checked through the GitHub API at the time of authoring; **the lock does not claim to query current GitHub API statuses**. Any PR amendment or rebasing after freezing must be re-reviewed and the lock regenerated with matching new evidence. Do not relabel a stale historic Success as a new/current PASS.

## Offline freeze verifier

```powershell
python tools/g3_release_gate.py
```

In GitHub Actions, checkout uses full Git history (`fetch-depth: 0`) to support a real `git merge-base --is-ancestor` check for each frozen PR pair. The gate rejects incorrect locked commits, altered branch ancestry, missing five schemas or constitutional files, foreign repository implementation directories, Git submodules, symlinks in the tracked tree, invented native E2E claims, and unapproved release flags. It uses only local Git inspection; it does not ask for GitHub secrets or visit native repositories.

Expected result is `status=g3-foundation-freeze-verified` with **`productionReleaseAllowed=false`**. This is success for the **G3 documentation, contract and pre-merge audit gate** — not a release authorization.

## Required human-review / actual merge order

The following remains **manual only**:

1. Review the full `CONSTITUTION.md` and source scope of PR #1. After explicit owner approval, mark ready, merge PR #1 into `main` and record actual merge SHA.
2. Rebase or retarget PR #2 onto the new main without losing its change isolation. Re-run its CI on the new head. Approve and merge #2 only after checking the diff.
3. Repeat for #3, #4, #5 and #6 in order, always checking branch base, file diff, CI success at the *new* merge candidate, and source repository non-contamination.
4. G3 (this seventh PR) is independently reviewed and merged only after the first six. Stacked draft branches should not be automatically deleted or merged by unrelated actions.
5. Before **any public release**: owner explicitly selects a distribution license and reviews copyright/third-party obligations. **This repository currently has no distribution LICENSE** in its tracked tree; being Public does not automatically authorize code reuse under MIT.
6. Version/tag/publish must be separately and explicitly authorized. Do not create `v0.1.0` or `v0.1.0-rc1` merely because G3 checks pass.

### Prerequisites for genuine cross-product production readiness

- Running H3 natively produces a reviewed/approved real Take and producer-owned export with verifiable provenance, not metadata invented by TRISYNORA.
- PointFlux implements an independently approved native Video Layer and permission-checked receiving adapter **in a separate PointFlux-owned PR**. Source H3 project and Take hashes are preserved. No native editor state is overwritten without PointFlux user approval.
- PointFlux imports a **copy** of approved media, validates streams, renders a real composite, and proves editable standalone workflows still operate with bridge OFF.
- Vera coordinates only when explicitly enabled and performs its own independent final verification; H3↔PointFlux continues working when Vera is missing.
- Each native product passes its own standalone regression. Before/after native project/Takes/output hash evidence is recorded with explicit watched untracked paths and traceable versions.
- No shared mutable database, no copied native engines, no always-running central runtime, no circular product install dependency, no automatically assumed consent.

## What the current green suite does NOT prove

The last frozen PR (#6) ran **113 tests, 0 skipped**, including a real FFmpeg H.264 media sample and a successful synthetic full-chain rehearsal. These tests use temporary mock Git repositories, *not* the three real products.

The G3 verifier does not certify actual PointFlux MP4 import, 3-app source isolation during a real exchange, ComfyUI/GPU/browser, native visual quality, rights/consent, or all untracked files. It also does not continuously monitor later GitHub PR changes.

**Release labels** must distinguish:

- `g3-foundation-freeze-verified`: contract/stack evidence consistent, six historic CI records pinned.
- `productionReleaseAllowed=false`: until real integrations, licensing and owner approvals are all independently satisfied.
- `not-verified`: any claim outside measured scope or if pinned evidence goes stale.

## Escalation rules

A new adapter must be requested as a **new explicit product-specific task and its own PR**. TRISYNORA cannot edit Vera, H3 or PointFlux as a side effect of an interoperability PR. If any future implementation proposes shared native state, implicit project edits, cross-product imports, or automatic merging, stop and reject it.
