# A0 cold observation: preserve progress before cleanup

Status: reviewed source change; installation and user acceptance are pending.

A real cold A0 observation completed its body and then failed during cleanup.
The complete observation existed only in memory, so the failed attempt cannot
serve as an accepted qualification. Its recorded failure and original clock
remain unchanged. The temporary container, route and introduced credentials
have since been cleaned up through separate bounded maintenance. Gateway and
Dashboard remain running. The original cleanup cause is still unproven.

This patch saves an explicit `UNSETTLED` / `NOT_READY` observation before cleanup.
It records bounded cleanup stage, exception class and static source locations,
including the already loaded native supervisor/control cause chain. It excludes
messages, arguments, locals and dynamic exception names. Existing final custody,
readiness and failed-proof rejection checks remain in force. Diagnostic write
failure cannot suppress required cleanup or mask its original failure.

The patch applies to the installed-source snapshot identified in
`PROVENANCE.json`. Two private installation path literals are replaced with
`<INSTALL_HOME>` in this publication; substitute the exact installation root
when evaluating those fixed canonical path checks. The private reviewed source
hashes and the redacted publication hashes are recorded separately.

Validation reused nine affected source controls, then three supervisor metadata
and two native-control metadata controls. These are isolated source checks;
they do not establish a real A0 qualification or a Telegram engineering result.
Patch applicability and Python syntax were checked against the actual source
preimages. No completed worker or user request was repeated for this patch.
