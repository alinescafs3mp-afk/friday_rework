# Canonical bounded-maintenance reader: source-only delta

Status: **NOT INSTALLED**. This checkpoint publishes one reviewed canonical-source compatibility patch. It grants no installation, service, worker or user-task acceptance. Publication is independent of the product integration path.

Isolated predicate controls showed the original canonical raised-maintenance branch rejecting the current registration fingerprint, which was absent from its exact allowlist. Its source refusal is `ordinary_source92_maintenance_original_phase_budget_changed`; this is not an actual canonical updater run. The patch adds that single fingerprint to `_source92_maintenance_budget_checked` in `scripts/friday_ordinary_install.py`: 68 inserted bytes; all other source bytes are unchanged. All seven historical canonical fingerprints remain, including the existing difference from the private reader family.

Exact full-file SHA-256 before:
`edcded4947cb638da95b8a8d7417f1f652e23238f5d618b170d5766e037037b5`

Exact full-file SHA-256 after:
`b629b61729f102c6fad481d57ca1565fd428d61cb4ea2779b6fd4b5af884779a`

The 181–600 second integer bounds, original unclipped clock, deadline, reserve and all other guards remain unchanged. The legacy branch at or below 180 seconds retains its existing behavior, including its early return for `True`. No new installer, stamp, manifest, authority or history policy is introduced into the product.

Verification reuses the completed source review: 64 isolated predicate cases passed and independent static delta review found zero HIGH/MEDIUM issues. These are controlled source checks, not full module, native updater, installed-state or user-task executions. The original reader refusal is preserved; an initial incorrect checker comparison between the two historical allowlists was corrected on the same candidate, with its failed observation retained privately. It was not a product failure.

The corresponding private maintenance path had already succeeded separately. That success does not establish installation or execution of this canonical candidate. Existing package bindings still require deliberate reconciliation before any future integration; this publication creates no additional product gate. Live policy, services and user acceptance are outside this checkpoint.

The packaging check applies this patch and its inverse to owned disposable copies of the exact baseline, with zero fuzz, and compares the complete resulting files with the recorded hashes. It reuses the unchanged source tests without rerunning them. The patch changes only repository-relative header paths; its hunk is identical to the reviewed source patch.

Root publishes only `README.md`, `MANIFEST.json` and `canonical-maintenance-reader.patch` under `docs/checkpoints/2026-10-25-canonical-maintenance-reader-source-only/`. The patch is a review artifact: publishing it does not apply it to the product. To reproduce, use a disposable tree containing the exact baseline at `scripts/friday_ordinary_install.py`, then run `patch --batch --fuzz=0 -p1` with this patch on standard input. Verify the after hash, reverse with `patch --batch --fuzz=0 -R -p1`, and verify the before hash. Stop on any mismatch; do not adapt another baseline silently.

No private paths, operation or process identifiers, network addresses, raw receipts, histories, handoffs, credentials or test oracles are included. Detailed working evidence remains private.
