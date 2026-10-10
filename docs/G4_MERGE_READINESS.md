# G4 — Merge-readiness review (no automatic merge)

**最高憲法：三個產品絕對不互相污染。**

G4 is an **independent local evidence checker for TRISYNORA's seven stacked draft PRs**, not an authorization to merge, a native product integration or a publication. Its sole purpose is to make accidental scope changes and lost history visible *before* human approval.

## Findings from live GitHub inspection on 2026-10-11

All seven GitHub PRs were open, Draft, unmerged, and reported `mergeable=true`, `mergeable_state=clean` at the time of inspection. GitHub PR state may change later; G4 itself **does not query GitHub**, and it cannot prove current mergeability, owner consent or branch protection settings.

Incremental changed-file counts (as checked against each PR's actual stacked base/head):

| PR | Head | Files | Scope |
| --- | --- | --- | --- |
| [#1](https://github.com/kevin781130-netizen/TRISYNORA/pull/1) | `206bb613` | 30 | Constitution, five schemas, P0 tests/docs |
| [#2](https://github.com/kevin781130-netizen/TRISYNORA/pull/2) | `3f2a9b94` | 3 | H3-origin package |
| [#3](https://github.com/kevin781130-netizen/TRISYNORA/pull/3) | `f0032e17` | 3 | PointFlux read-only receiver |
| [#4](https://github.com/kevin781130-netizen/TRISYNORA/pull/4) | `1d6b8145` | 4 | True MP4 decoder |
| [#5](https://github.com/kevin781130-netizen/TRISYNORA/pull/5) | `7081e78b` | 3 | Three-product synthetic Git SHA gate |
| [#6](https://github.com/kevin781130-netizen/TRISYNORA/pull/6) | `237e1278` | 4 | Complete synthetic bridge rehearsal |
| [#7](https://github.com/kevin781130-netizen/TRISYNORA/pull/7) | current branch | 10 | G3/G4 governance, CI, README |

`governance/g4-review-scope.json` pins the exact added/modified file list for the first six heads, plus the allowed PR #7 file paths. It does **not** replace human code review. The exact-file lists help identify a new file outside an approved scope; the user must review any lock update, because a lock file can itself be changed by a PR author.

## Run the G4 check

Requires the complete Git history:

```bash
git fetch --all
python tools/g3_release_gate.py
python tools/g4_merge_review.py
python -m unittest discover -s tests -v
```

In GitHub Actions, checkout uses `fetch-depth: 0`. The G4 checker uses Git history and exact `git diff --name-status --no-renames -z` only; no network, GitHub tokens, native repositories, mutable DB or other product code.

Expected G4 output is `status=review-scope-consistent`, `prHumanReviewApproved=false`, `mergesExecuted=false`, `nativeRuntimeE2EVerified=false`, `productionReleaseAllowed=false`. It verifies historic PR file scopes, not whether the current GitHub UI still reports `clean`.

## Critical: how to merge WITHOUT invalidating the G3 freeze

**Do not use Squash and merge or Rebase and merge while the current G3 freeze expects the original seven stacked commits to remain ancestors of the final branch.** Either would rewrite/discard the original commits and invalidate the pinned ancestry gate.

Upon **explicit human owner approval** of each PR, use this sequence:

1. Review `CONSTITUTION.md` and PR #1's exact diff, source/repo firewall, license/public disclosure implications; require a successful current CI on that head. Only then take PR #1 out of Draft and merge it into `main` using a **merge commit** (preserving original history).
2. **Retarget PR #2 base to `main`**, without rebasing/rewriting its feature branch; compare exact file diff and confirm a fresh CI at the resulting merge candidate, then merge by **merge commit** if separately approved.
3. Repeat with #3, #4, #5 and #6, retargeting each to `main` only **after** its parent is merged. Continue to inspect the exact incremental diff and independent CI at each step.
4. Retarget PR #7 to `main` after #6; run G3 and G4 with full history again, review this PR, then merge by merge commit only after explicit approval. Retain a record of merge SHAs and review evidence.
5. **If GitHub settings do not allow merge commits**, STOP. Decide a new approved history strategy, regenerate the frozen ancestry evidence and rerun the relevant tests instead of silently choosing squash/rebase.
6. If a PR is amended after its head was pinned, pause all mergers and **refresh both G3/G4 locks** with the new diff, current run evidence and independent review.

The above sequence is a *manual checklist*, **not a script**. This repository deliberately provides no button or automation that changes PR bases, marks PRs ready, merges branches, creates tags or publishes versions.

## Required red lines before any PUBLIC release

**Unresolved:** no approved distribution `LICENSE` in the tracked files. Public source visibility does not itself grant an MIT, Apache or other reuse license. The owner must choose the text and review any upstream redistribution obligations. We do **not** set a license automatically.

**Unresolved:** the actual native three-product E2E. Only a native H3-approved real video export, separately authorized PointFlux-owned Video Layer/receiver adapter, independent PointFlux composite playback/render, opt-in Vera final verification, bridge-OFF standalone regression and actual native source SHA can support such a claim.

**Unresolved:** complete native file coverage. G1's SHA tool measures Git-indexed paths plus explicit watchlisted untracked files; it does not certify hidden native caches, databases, process state or cloud writes.

G4 is finished when the scope checker passes on a pinned head, **not** when release has been authorized. Human approval and safe merge sequence remain separate future actions.
