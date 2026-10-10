This is proposed documentation for source not yet installed.

## Cumulative record consumer

Use `validation/validate_release_record.py` with the immutable V2 archive next
to this checkout and the unchanged owner delta. Start from
`validation/RELEASE_EVIDENCE_TEMPLATE.json`; leave `template=true` and `NOT_RUN`
until actual observations exist. From the product checkout:

```sh
python3 -B validation/validate_release_record.py --record evidence/release.json --target USEFUL
python3 -B tests/test_release_record.py
```

The default USEFUL target requires 47 records covering 46 checks: the retained
V2 requirements, mandatory AC043 and AC053-AC058, with separate AC055 rows for
`worker=Harness` and `worker=A0`. Both worker rows bind the same complete
candidate fingerprint and each references separate evidence files; common
receipts may be shared in addition. DAILY remains cumulative (56 records),
and FOUNDATION remains its nine checks. AC044-AC046 remain selectable through
`--require-optional`; inherited reviewed exceptions use
`--allow-not-applicable`, but mandatory web/admin checks cannot be excepted.

The record must bind the exact base/delta bytes in `acceptance_definition`.
Candidate fingerprints, times, actions, observations, evidence hashes and
containment are checked using the pinned V2 predicates and contained file
reads. Changed definitions, stale candidate receipts, duplicate/unknown worker
rows, symlinks and escaping evidence fail. Explicit `--base-root` and
`--product-root` locate the same pinned definitions; they cannot weaken them.

Exit 0 means only declared record completeness and byte/candidate consistency;
exit 1 means unresolved or malformed records, and exit 2 means invalid inputs.
`attests_runtime_truth=false` and `review_required=true` always remain visible.
Synthetic file-fixture success is offline consumer verification. Independent
review of the source and actual installed candidate observations is still
required for release, including all seven installed and four web journeys.
