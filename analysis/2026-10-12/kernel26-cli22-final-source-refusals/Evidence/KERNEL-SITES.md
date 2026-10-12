# Final kernel3 blocking sites

- C55-CHILD-FD-SNAPSHOT-TRANSIENT-EBADF: Both fixed child hygiene loops close the already-closed proc enumeration descriptor and abort the normal connected path. Sites: Source/stock_install_owner.py:1058-1074, Source/stock_install_owner.py:1105-1117, Source/stock_install_owner.py:1197-1237, Source/root_fd_custody.py:591-603, Source/stock_install_host.py:1532-1537.

- C55-AUXILIARY-OWNERSHIP-ROLE-LAST-ROW-PREFIX: Whole auxiliary preflight ignores ownership role/identity declarations that are rejected only after caller and Root prefix effects. Sites: Source/root_fd_custody.py:368-438, Source/existing_root_adapter.py:193-259, Source/root_fd_custody.py:120-142, Source/stock_install_owner.py:1579-1603, Source/qualification_batch.py:137-195, Source/stock_install_owner.py:1666-1683, Source/stock_install_owner.py:1705-1739.

- C55-AUXILIARY-PHASE-WITHOUT-CLEANUP-CONSUMER: The whole plan accepts auxiliary phase lifetimes for normal/uncertainty phases that have no cleanup consumer. Sites: Source/root_fd_custody.py:368-438, Source/qualification_batch.py:180-188, Source/qualification_batch.py:425-454, Source/qualification_batch.py:393-405, Source/stock_install_owner.py:1521-1557, Source/kernel120_control_inputs.py:131-134, Source/stock_install_owner.py:855-901, Source/root_fd_custody.py:543-566.

Full causal paths, counterexamples, required behavior and meaningful controls are preserved in KERNEL26-FINAL3-FINDINGS.json. All corresponding complete bodies are under Kernel/. No counterexample executed.
