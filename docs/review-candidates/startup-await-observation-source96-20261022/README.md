# Source96: installed acceptance passed; first actual native startup failed

Source96 installation is independently accepted. The subsequent D2 check exited 0
in 38.7903 seconds, was reaped and did not time out. It verified current installed
custody across 17710 native files, 265 project files and 96 layers. This acceptance
covers the installed state; it grants no runtime or release acceptance.

The first actual Source96 native startup failed with exit 3 after the unchanged
full 90-second service window. The terminal operation, including stop, took
136.28849 seconds. The outer wrapper returned 0 for cleanup transport only.
Exact owned cleanup passed: the gateway and all three role records were absent,
no manager jobs remained, and the protected backend was unchanged. No deadline
was reset, extended or clipped. The consumed installation and first startup must
not be replayed. READY is false and the contextual Jarvis request remains unsent.

Telegram polling connected at unit +86.178101 seconds. Eleven bounded async
samples were captured; the last three, at unit +87.288516, +89.289954 and
+91.291183 seconds, showed the startup coroutine suspended in the secondary
profile stage on this exact await chain:

```text
gateway/run_startup.py:1956 await self._start_impl()
gateway/run_startup.py:2025 await _start_secondary_profiles
gateway/run_startup.py:1584 await _start_secondary_profile_adapters
gateway/run_adapters.py:1013 await _start_one_profile_adapters
gateway/run_adapters.py:1270 await _load_secondary_profile_config
gateway/run_adapters.py:1088 await asyncio.to_thread(admission.onboarded_gateway_profile, profile_home)
```

Received samples demonstrate event-loop dispatch at those instants. The executing
inner thread step and its cost were not directly observed; responsiveness after
the last sample is unknown. Missing loop-tick responses are unknown, and absent
records alone do not prove nonentry. The abort's final `STARTUP_AWAIT_END`,
`impl=TRUE` and `flush=RETURNED` describe abort completion, not READY, durable
persistence or delivery. Direct source identifies the full root ordinary check at
`hermes_cli/friday_credential_admission.py:3428` as a connected hypothesis before
auth/policy and inert-profile validation. Existing same-invocation source-guard records also show two worker spans of
2.759 and 2.689 seconds overlapping this stage; both passed and the second ended
after the native CLI timeout. Their caller tags are `UNKNOWN`, so a concrete
onboarding caller or profile identity is not established. The third secondary
sample was captured during cleanup after native failure. A deeper live cause or
causal repair is not proven. Admission, integrity, authorization, isolation and custody checks must
remain intact before hydration or effects.

The first independent installed check, D1, remains a failure: exit 1 at
`foreign_matching_consumer` after 15.19 seconds. Its refusal recorded no matching
PID, so historical process identity is unknown. A literal own-shell matching
mechanism was demonstrated separately; it does not establish D1's historical
identity. No consumer-guard exemption or bypass was used. D2 acceptance does not
erase D1. The earlier Source95 startup failure after its full 90-second service
window also remains preserved; polling connected at +85.305913 seconds and its
remaining async stage was not captured.

This candidate adds fixed-field, bounded startup-task observations and six suffix
boundary markers to the supported startup path. It preserves the Source95 flush
repair, authorization, integrity, isolation, recovery, startup order and deadlines,
and creates no new task, thread, signal, runtime or orchestration service. The
unchanged 27 callback controls were reused; 22 affected suffix, exception,
cancellation, abort and logging-failure controls passed. Independent source review
has no high or medium findings. The pure journal parser passed 33 grammar,
bounds, timing and privacy controls; bounded journal capture remains intact.

One unchanged stock-composer run passed in 15.83 seconds and was reaped. The
canonical receipt matched its prediction; the genuine installed-ancestry receipt
is recorded separately. The supported update command was consumed once: exit 0
in 43.36 seconds, no timeout, child reaped, with five afterimages and the expected
genuine installed receipt. Those successful steps remain distinct from the
failed first native startup.

`STATUS.json` records the separate outcomes. `OBSERVATIONS.json` publishes only
sanitized fixed labels, code locations, counts and relative timings, with evidence
digests. Source patch and source manifest remain byte exact. The separate accepted
web/document/caption package remains a follow-on, outside this exact candidate.
Existing genuine partial user evidence and every earlier failure remain preserved.
This candidate earns no full B00, user-journey or release acceptance.
