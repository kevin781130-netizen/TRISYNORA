## Summary

Describe only the TRISYNORA contract, documentation or test changes.

## Zero-contamination constitutional checklist

- [ ] I read `CONSTITUTION.md` and `AGENTS.md` and the change complies with every article.
- [ ] Vera, MiniMax-H3 and PointFlux source repositories are **unchanged** by this PR.
- [ ] All three products remain individually installable, runnable, testable and releasable without TRISYNORA.
- [ ] No third-party core copied/vendored; no git submodule, shared mutable DB, secrets, global Agent, or fourth Director.
- [ ] Any cross-project operation is opt-in, versioned, bounded, receiver-authorized, and reversible when possible.
- [ ] Native projects / approved takes remain unchanged; receiver creates derived artifacts under its own workspace.
- [ ] New schema revisions do not break consumers silently; unknown versions fail closed.
- [ ] Evidence names executed and unverified tests separately; no synthetic fixture is presented as a real PASS.
- [ ] All changes are limited to this repository. External product PRs, if required, are separately authorized and reviewed.

## Actual verification (do not fill from assumptions)

Commands executed:

```text
[record commands here]
```

Executed PASS / FAIL / SKIP:

```text
[record observed results here]
```

## Constitutional amendment?

- [ ] No
- [ ] Yes: this is a dedicated `constitutional-change` PR, with written cross-product impact, isolation evidence, and human owner review.

## Known gaps and next phase

List missing hardware, CI, browser, model, and media evidence explicitly.
