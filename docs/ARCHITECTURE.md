# TRISYNORA Architecture: independent islands, optional bridges

```text
              optional Vera orchestration
                  [ VERA ]
         capability discovery / tasks
              /                 \
             v                   v
     [ MINI MAX H3 ]       [ POINTFLUX ]
      native Director        native Studio
      AI video takes         motion / FX / QA
             \                   /
              \  opt-in exchange /
               [ TRISYNORA v1 ]
                neutral schemas
               no shared runtime
```

A direct **H3 ↔ PointFlux** interchange works with Vera OFF. A standalone **Vera**, **H3**, or **PointFlux** installation works with every bridge OFF. TRISYNORA itself never runs a persistent service.

## Five contract families

1. **Capability** — advertised features, versions, availability; discovery is not a grant of permission.
2. **Asset** — immutable provenance and digest for an asset *inside a controlled exchange package*. The location is a validated **package-relative** path; never an arbitrary URL or remote path.
3. **Shot** — neutral source identity, native format, digest, rational frame rate, referenced artifact IDs, read-only vs explicitly approved handoff. No native prompt, camera transform, take, or renderer-specific Scene IR is embedded.
4. **Job** — a bounded *description* of a requested optional operation with separate target/product, idempotency, scope, and approved output area; a Job JSON **never** grants OS or application authority.
5. **Evidence** — domain check, source digest, observed proof, and explicitly limited domain authority. Vera can independently ingest it under its own verification runtime.

Native formats are authoritative: PointFlux Scene IR and `pointflux-h3-shot-exchange/v1`; Vera Fabric and EvidenceReceipt; H3 Production Core and verified local ComfyUI template bindings. The new schemas are **external envelopes**, not drop-in schema replacements. Their mapping to native formats must be implemented and tested by **product-owned adapters**.

## Adapter interface (proposed, not implemented)

```text
product CLI / localhost API
    capabilities()         -> neutral Capability
    export_reference(...)  -> neutral Shot + Asset manifests
    import_reference(...)  -> receiver validation + explicit bind
    submit_job(...)        -> receiver-local authorization + job id
    job_status(...)        -> state + immutable output manifest
    export_evidence(...)   -> neutral Evidence
```

An adapter should expose only these operations it actually supports. Unsupported or unverified operations are explicitly unavailable. No generic remote shell, path-based writes, arbitrary ComfyUI node execution, or secrets export.

## Data flow examples

- **H3 → PointFlux:** H3 exports an operator-approved, hashed video asset; PointFlux imports a **copy** into its workspace after validation, adds GPU/Remotion effects, exports a new MP4 and a domain QA receipt. H3 native Take stays unchanged.
- **PointFlux → H3:** PointFlux exports a versioned shot/preview reference; H3 validates and *optionally* links it to an H3 director shot, without modifying the AI prompt or existing approved Take. Changed source SHA makes the reference stale and triggers review.
- **Vera → either:** Vera inspects capabilities and requests an operation through a product-owned adapter with bounded permission. Vera accepts domain evidence but runs independent verification before a cross-product PASS.

## Explicitly deferred

- Actual media transfer / ComfyUI streaming / GPU hardware coordination / cross-editor 3D camera transformations.
- Multi-track interchange via optional OpenTimelineIO (only when a real editable timeline use case exists).
- Auto asset factory / speech/music generation / visual semantic scoring; future capabilities attached via adapters.
- Browser UI, fourth Director, shared queue or database.

All deferred items need separate PRs and real environment acceptance, with Article 1 standalone proof.
