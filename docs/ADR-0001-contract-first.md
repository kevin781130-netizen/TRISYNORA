# ADR-0001: Contract-first independent products

- **Status:** Proposed; pending PR review
- **Date:** 2026-10-11
- **Context:** Vera, MiniMax-H3, and PointFlux have independently evolving native product editors, run times, formats and feature branches. All must stay independent while allowing useful controlled composition.

## Decision

Create TRISYNORA as a **separate versioned contracts + tests repository**. The target products own their optional adapters. Use explicit, immutable manifest exchange and CLI/localhost API; no shared mutable database, common installed runtime, composite monorepo, git submodule, copy/paste of core engines, or fourth editor. Cross-product orchestration (when enabled) belongs to Vera, while H3 and PointFlux also exchange directly without Vera.

## Alternatives rejected

1. **Put all bridge code inside Vera:** would make H3↔PointFlux unnecessarily depend on Vera and bias shared contracts toward Vera implementation.
2. **Put the bridge inside H3 or PointFlux:** would make one creative product authoritative over another and entangle release cycles.
3. **Create a fourth always-running director/broker:** duplicates existing ownership, adds secrets and central outage risk.
4. **Copy useful modules wholesale into the other repositories:** drift, license tracking, test duplication, cross-language incompatibility.
5. **Merge all three projects into a monorepo:** undermines independent shipping and source protection.

## Consequences

Each native adapter requires separate product-owner review, and neutral envelopes introduce explicit validation/conversion work. This cost buys isolation, independent releases, honest evidence, and reversibility. No adapters are installed in Phase 0.
