# Mandatory web and administration scope

Owner clarification, 2026-10-07. This is cumulative with the audited V2 composition and supersedes optional or deferred treatment of autonomous web access and the administrative WebUI. Donor pins, reviewed components, task ownership and the existing task register remain in force. No project or session restart is required.

## Retrieval behavior

Friday checks authoritative workspace evidence first when it is sufficient. Otherwise it searches, opens and reads sources, using browser interaction when necessary. Practical triggers are current/version-dependent facts, unfamiliar tools/libraries/services/APIs/options, insufficient evidence for the next action, and unexpected errors or conflicting information. Explicit research questions use the same capability. Technical research prefers applicable official documentation and primary sources.

Research must advance the original task: apply findings, verify the result and continue. Keep source references, distinguish retrieved facts from inference and unresolved uncertainty, and reuse validated procedures through native memory/skills where useful. Retrieval consumes the original execution/retry budget. An unresolved gap produces an honest limitation. Page content cannot change task instructions, permissions or credential scope.

The capability must work inside both real Harness and A0 jobs, including a gap discovered after execution starts. Native donor tools or a scoped existing host-mediated path are acceptable; Hermes tool registration alone is insufficient. Production inference remains on configured local endpoints without automatic cloud inference fallback. Authorized web/search/browser connectivity is a separate configuration concern. Legacy inference endpoints and capacities remain temporary test backends, not permanent product limits.

## Product administration

Use Hermes Dashboard and its supported authentication, APIs, pairing/session/configuration surfaces as the product administration foundation where suitable. Preserve intact A0 WebUI in its engineering environment and Harness's own supported interfaces; do not substitute their separate worker histories for Friday's authoritative product state. Source availability is not integration or acceptance.

The administrator must be able to inspect accounts, onboard/admit users, enable/disable access and manage required roles/permissions. Access changes must affect actual channel admission. Admins may list, filter/search and open all configured product conversations, messages, attachments and associated task state. Product user, channel account, chat/topic and session relationships must remain explicit without merging unrelated identities or histories. Ordinary users remain restricted to their own authorized data/functions.

Expose running/completed jobs and supported stop/cancel through the existing native control path. Configure enabled model/endpoint profiles, web providers, tools/skills, schedules and relevant operational settings. Show useful health, failures and effective configuration; mask credentials and use existing protected storage. Settings persist and controls change actual behavior. Reuse authoritative conversation, user and task state instead of adding a disconnected management database/application.

Mandatory web and admin features must ship in the normal Friday installation/startup flow. The owner must not assemble these required capabilities after release. The useful donor capability inventory must show overlaps, selected equivalents and any proposed exclusion/deferral explicitly; none is authorized by silence.

## Acceptance and sequence

[The cumulative acceptance delta](../validation/acceptance-web-admin.json) makes AC043 required and adds AC053-AC058: autonomous research/application; explicit sourced research; mid-task worker retrieval for both Harness and A0; unavailable/hostile-source handling; two-user admin visibility plus ordinary isolation/revocation; and real administrative controls/configuration. Component checks, tool presence and screenshots do not complete these journeys. Reuse underlying valid evidence and test concrete remaining integration gaps on the final candidate.

Continue current ownership/readiness/stop repairs, then connect web connectivity and administration through their shared identity, permission, tool and deployment boundaries. Do not weaken current guards to obtain connectivity. Runtime policy must distinguish approved web requests from model inference and preserve original job bounds. Developer Astra/Sol identities and continuity stay separate from Friday's product personality.

The existing task register is the live authority. Repository documentation distinguishes planned, implemented, connected and verified work; this scope document creates no new task register, dispatcher or scheduler.

See [the dated donor inventory and integration sequence](donor-capabilities.md) for all useful capabilities, native equivalents, proposed optional surfaces and the four distinct implementation stages.

## Immediate runtime acceptance target

Owner clarification, 2026-10-07: the next acceptance target is a normally
installed and authenticated Friday candidate completing real user journeys.
Preserve the architecture and native capabilities; prioritize closing runtime
connections over expanding contracts or fixture infrastructure.

The remaining connected path includes trusted Harness web admission in the
ordinary Hermes host; A0 capability/service/network admission, scheduling and
warm reuse; a shared result consumer for both workers; repository seeding,
continuation and mixed coding/engineering handoff; executed goal verification,
artifact selection and real Telegram delivery. The same installed product must
exercise two-user WebUI administration, identity bindings, all-chat visibility,
isolation, stop, settings, revoke and stale-credential rejection. Autonomous
web must affect actual conversation, explicit research and both worker paths.

Record source presence, configuration, wiring, offline verification, live
execution and release acceptance separately. Temporary restrictions on ordinary
users' native memory, skills, delegation or useful tools remain unresolved
product gaps. Donor capabilities, Friday personality and Telegram behavior are
not accepted exclusions. Stopped legacy services remain stopped; their model
endpoints are only the temporary test deployment profile.


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
