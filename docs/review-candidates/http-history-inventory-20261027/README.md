# HTTP history inventory correction — 27 October 2026

Source-only analysis material for the accepted S408 correction. The patch names
an omitted private historical receipt reader; that target is absent from this
public repository. It is not a public runtime port, an installation package or
an instruction to apply the patch to an installed service.

## Defect and correction

The historical reader included `a0_web.py` for the earlier `web_probe` transition
but omitted it from the expected publication inventory for `web_http`. A valid
HTTP-transition receipt therefore failed with
`ordinary_a0_source_successor_publication_inventory_changed`.

[final.patch](final.patch) includes the web adapter for either exact transition
and moves the complete inventory check ahead of the authenticated ancestry walk.
It checks the complete `before`, `after`, committed-after and intent-before
key sets, including the marker relationship and committed-after digest joins.
The intent and its before-map must be dictionaries. An impossible publication
is rejected before the more expensive history traversal.

The original `service_publication_sources` call still receives the full maps;
there is no projected subset or replacement with the newer public helper.
Exact source pins, identity/mode checks, inactive-state requirements and the
other 38 guard predicates are preserved. The private historical validator and
the public service declaration module have different contracts; their source
hashes and inventories cannot be substituted.

## Reused evidence and status

The accepted source package recorded 34 bounded inventory checks, including
missing/extra entries, changed digests, path aliases, source tuples and inactive
flags. The actual full maps contained 11 before-entries and 10 after-entries.
The final delta had an independent PASS review and Root source-only acceptance.
This export reuses that evidence; it did not rerun tests, traverse historical
receipts, import the runtime or perform live effects.

At this export's preparation checkpoint, the prior source installation (R472)
and native update (R474) remained accepted. The R475 derivative was in progress
and had not been accepted. Service restoration, worker qualification and the
new DSH/A0 Telegram file tasks were not established by this source acceptance.
The original refusal and its verified unchanged inputs remain recorded in the
[operational observations](../../worker-web-service-source.md#operational-observations-27-october-2026).
No runtime or end-to-end success is claimed here.

## SHA-256 provenance

The evidence records remain private; only their digests are published. The
patch is byte-identical to the accepted sanitized delta.

| Material | SHA-256 |
| --- | --- |
| Exported `final.patch` | `34219c94d49a718067f0dc870afc235cd7f464383a8d0de9bbb295fa497df18e` |
| Accepted final private reader | `1ee69d5647c972626937a8a8fee6cdada435047f29ff9eda671c2870bf17c69f` |
| S408 source result | `1ef21c99aa284eaf4181dcd5e7061a890b7a82eac86a1d4a967a93e437518a61` |
| Independent final-delta review | `42dd9595b3230a40d4403fb4bf76e02e76563e6345524b831cf7298331b141b2` |
| Root source-only acceptance | `67a94fb5b6b320ccf1fb005a2d73384b11a93fac911f7fef57999a1f298235c5` |
