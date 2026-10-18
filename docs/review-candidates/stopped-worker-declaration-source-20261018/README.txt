Stopped worker declaration writer Source — 18 October 2026

The stopped operator could archive stale worker state and prepare typed changes,
but did not yet have a native writer that applied those approved changes and
resealed configuration/user proof. This candidate adds that missing maintenance
phase. It preserves current source, role, installation, PM/build, identity and
consumer-lock checks, original budgets and one-shot consumption. Publication is
atomic with exact owned rollback; uncertainty never authorizes a blind retry.

SOURCE.patch contains16 project files against the exact layered Source94 hashes
in STATUS.json. It is not a patch against plain upstream or unmodified main.
The small native patch adds PairingStore(initialize=False) to avoid constructor
migration during an authenticated read. Default initialization and normal grant
matching remain unchanged. The patch and its exact manifest also occur within
the project patch; the separate copies support review of the native layer.

Independent Source review approved this snapshot with zero open findings.
Exact patch reconstruction and git apply --check --no-index passed. The three
test modules define350 literal Source cases; pytest collection, execution and
installed behavior have NOT run for this writer. Earlier152-test startup and
63-control producer results cover their earlier tuples only. They are not
acceptance for this candidate. The combined Source95 tuple, narrow large-file
fixture limits, actual regressions, supported promotion and live user journeys
remain pending. This archive is inert and the installer does not reference it.

Native code derives from NousResearch/hermes-agent revision
781334eea4b9225a3e194faf0c241d9afe218634; the MIT LICENSE retains attribution.
Private handoffs, acceptance checklists/oracles, user data, credentials and raw
runtime observations are excluded. No runtime configuration is published.
