# Bounded web regression source

This adds the exact 118-line synthetic regression source for the existing [five-file bounded-web component](../ordinary-web-bounded-result-20261020/README.md). The `.py.txt` suffix keeps this archive outside automatic test collection and runtime imports.

All 14 isolated offline cases passed against the component afterimages pinned in `SOURCE.json`. They exercise the actual AST-selected response reader and original-caller publication environment: the 15,000-character inline ceiling, bounded handler results, response size and encoding limits, timeout refusal, and failed/stopped/foreign callers that must not reacquire native cache. Transport and caller fixtures are synthetic. This run covers selected functions, not full module integration or network behavior.

The candidate remains uninstalled. Live provider/Telegram execution, database durability, the complete baseline and release acceptance are open. The earlier component archive retains its separate qualification limits.

Preflight refused an older source preimage before tests, then found no pytest in the runtime environment. The recorded passing run used the existing test environment and the exact current component; no package was installed.

No model assets, operational provenance, private evidence, owner data or acceptance oracles are included. Existing license notices are retained. See `SOURCE.json` for exact content hashes and scope.
