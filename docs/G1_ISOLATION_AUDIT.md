# G1 Source Isolation Audit — Vera / MiniMax-H3 / PointFlux

**Highest constitution:** Native products remain independently installable, executable, editable, testable, and releasable. TRISYNORA cannot own or write any product's project, source, secrets, output, or shared database.

## What this gate actually proves

`tools/isolation_audit.py` is a *read-only source integrity observer*. It captures a pinned SHA-256 baseline of the files **currently indexed by Git** in each of three independent repositories, plus **explicitly watched native files** (for example a native project file or an H3 approved Take that is not Git-tracked).

Running the tool before and after an experimental exchange lets the operator detect:

- Any changed/added/deleted Git-indexed file or content under Vera, MiniMax-H3, or PointFlux;
- Any changed, removed, or replaced native file explicitly listed for watch;
- A change to the checked-out Git `HEAD`, including commit changes with identical working files;
- A changed/tampered baseline itself, when its SHA-256 was pinned **outside** the watched repositories.

Git-indexed + explicitly watched is an **intentionally limited scope**. This tool does **NOT** claim that every untracked, Git-ignored, transient, in-memory, database, remote, or model-generated file is unchanged. Nor does it establish that any native product can start with integration disabled. Those are separate native-regression gates.

## No-contamination technical restrictions

- All three source roots must be **distinct top-level Git repositories**, outside the TRISYNORA working tree, with no nested roots.
- It **never** does `git checkout`, `git add`, `git commit`, installs a dependency, starts a renderer, or writes to a native source directory. Git inspection sets `GIT_OPTIONAL_LOCKS=0`.
- Symlinks and nonregular paths are **rejected**, not followed.
- Only a **new baseline JSON** is written to an operator-controlled directory **outside** all three repositories and TRISYNORA. Existing files are never overwritten.
- Each baseline is capped at 32 MiB; the scan is bounded to 20,000 named files and 2 GiB of source bytes per product, maximum 256 MiB per individual file. Out-of-budget coverage is `NOT VERIFIED`, never PASS.
- The baseline records relative source filenames, Git HEAD, hashes, sizes and the explicit watchlist. **It must remain private and must not be committed**: filenames can reveal private structure. Outputs from `verify` report counts only, not source paths, file contents or secret values.
- Baseline SHA itself is not a digital signature. Keep its value in a separate trusted local record; a malicious operator with control of both baseline and the SHA record cannot be detected by this tool.

## Windows operator instructions

Create a JSON watchlist **outside all three products and TRISYNORA**, e.g. `C:\audits\watch.json`:

```json
{
  "vera": [],
  "minimax-h3": ["exports/approved-take.mp4", "projects/production.json"],
  "pointflux": ["projects/scene.json"]
}
```

These relative paths are examples, **not known native file locations**. Replace them with paths that actually exist *under your own checked-out repository roots* and refer to native assets you want to protect. The tool refuses missing watched paths at capture time. An empty watchlist `[]` is allowed, but **untracked files then remain unverified**.

1. Record the initial Git HEAD and source file contents (read-only), before you run a bridge experiment:

```powershell
python tools/isolation_audit.py capture --vera-root C:\projects\Vera --h3-root C:\projects\minimax-H3 --pointflux-root C:\projects\PointFlux --watch-list C:\audits\watch.json --out C:\audits\g1-before.json
```

The output prints `baselineSha256`. Copy the **64-character** digest to a trusted operator note distinct from the JSON baseline. Do not treat `baseline-created` as proof of independent product operation.

2. Perform your separately approved test on *isolated exchange-package copies*. No code in this audit invokes the three products.

3. Verify all scoped files against the preserved baseline and original SHA:

```powershell
python tools/isolation_audit.py verify --vera-root C:\projects\Vera --h3-root C:\projects\minimax-H3 --pointflux-root C:\projects\PointFlux --baseline C:\audits\g1-before.json --expected-baseline-sha256 YOUR_RECORDED_64_CHARACTER_SHA
```

Exit codes:

| Exit | Outcome | Meaning |
| --- | --- | --- |
| `0` | `unchanged-within-scope` | Git-indexed files, selected watch files, Git HEAD unchanged; explicitly limited coverage |
| `3` | `changed-within-scope` | One or more products have Git SHA/head, path set or content changes |
| `2` | `not-verified` | Invalid snapshot, untrusted/symlink path, lack of Git, missing files or exceeded bounds |

Only `unchanged-within-scope` is a clean *G1 scoped file integrity observation*. **Full native isolation remains NOT VERIFIED** until independent applications are exercised (bridge OFF), private/untracked outputs are included, and the receiving product approves all native changes.

## CI and test assurance

```bash
python -m unittest discover -s tests -v
```

`tests/test_isolation_audit.py` creates **three temporary Git repositories** as synthetic stand-ins, including untracked protected Take and PointFlux project fixtures. Tests verify modified files, same-size tampering, deletion, new indexed files, empty commits, changed baseline checksum, symlinks, path traversal, overlapping roots, no overwrites and read-only verification. **It does not clone, read or write your actual Vera, H3, or PointFlux repositories.**

This gate must be used **alongside** the P1 MP4 media/codec check. A passing 78+ unit suite or CI only certifies tooling on test fixtures; it does not mean H3 → PointFlux native E2E is complete.

## Dependency / review

Draft stacked PR sequence: **#1 Constitution → #2 H3 package → #3 PointFlux dry-run → #4 MP4 decode → G1 audit**. None may bypass the native product owners' separate approval. This repository remains an optional interoperable contract/tooling project, not a central executive, a shared-state store, or a fourth Director.
