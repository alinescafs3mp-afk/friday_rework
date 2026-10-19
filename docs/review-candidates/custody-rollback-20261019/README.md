# Preserve detected reference loss through rollback

After a configuration write, a retained reference could be replaced and later regain its previous inode identity during rollback. The installer could then certify the rollback even though it had already detected that the reference changed.

`CUSTODY.patch` records that detected loss for the transaction. Owned restoration still runs; later equality cannot clear the recorded failure or produce `rolled-back.json`. The original error remains the cause of `StopUnconfirmed`. Refusal before publication and ordinary failure/cancellation rollback retain their existing behavior.

This is an inert review copy, applied on top of the installer afterimage from `../compact65536-migration-20261019/`. It does not change the repository installer, installed configuration, model or service. Exact baseline and afterimage hashes are in `FACTS.json`.

Independent static review passed. On the coherent private candidate, all original 163 cases and five additional custody cases passed: 504 complete phase reports, no skips, one 300-second operation, verified source equality and namespace cleanup. The five new cases cover one-shot external and retained-reference replacement, physical ABA, renderer proof loss and refusal before publication. They use synthetic transaction fixtures and do not establish installed-state or live acceptance.

The new regression source is byte-identical to the executed source and imports the capacity candidate's fixtures. The separately published anonymized fixture variant has not been rerun with this patch. Earlier failures and the incomplete focused attempt remain recorded separately in `FACTS.json`.

Compression context 65,536 / input ceiling 65,530 remains a pending configuration migration. Main inference stays 262,144. Coherent qualification, supported installation, current renderer issuance/parity, the two maintenance transactions and runtime acceptance remain separate requirements.
