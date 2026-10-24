# Scoped worker credentials and inactive A0 primary selection

R257 and R258 close two observed input failures in the existing normal worker path. Worker preparation now retains the validated separately scoped compressor credential **name**. A protected Dashboard action can update an admitted, inactive user's A0 chat and utility declarations to that user's already configured primary model. It preserves embeddings, compressor settings, grants, user data and runtime limits.

The action checks operator authority, current user generation, root/target/binding CAS and existing worker custody. It refuses active, revoked, foreign or previously attempted worker state. The planner rejects a utility route that would borrow the primary model credential for another service. The launcher adds exactly the already approved primary-plus-embedding endpoint pair; existing accepted policy outputs are unchanged.

Apply `01-scoped-worker-credential-names.patch` and then `02-inactive-a0-current-primary.patch` to the accepted R252 source composition, using a unified-diff tool that accepts zero-context hunks. The exact six resulting source hashes are in FACTS.json. Both patches were applied in that order to isolated copies of the six base files and compared with the reviewed overlay.

R257 has 51 passing offline controls; R258 has 23, including the real native configuration transition on an isolated fixture constructed from private nonsecret deployment metadata and subsequent planning for both workers. Both source packages passed independent review with no findings. These are source and offline results. **They are not installed, live worker execution, inference, or product readiness.**

The current installed version remains the separately accepted R253 package. Its later finite worker-prepare request returned HTTP 400 and was closed without a retry or worker qualification. Its actual server handler trace was not retained; isolated planning reproduced input refusals, which must not be presented as that missing trace. R259 is preparing coherent existing project and inactive-service maintenance joins for these new sources. The new launcher needs a legitimate new service-maintenance successor; historical effects and clocks stay closed.

No user records, fixture contents, credentials, endpoint addresses, private handoffs or session histories are published here. Native layers, full data protection and the original service limits remain unchanged.
