# Final CLI5 blocking sites

- R1: Physical operation guard retires before actual native caller and its cleanup return. Sites: hermes/hermes_cli/friday_cli_finite_owner.py:373-386, hermes/hermes_cli/friday_cli_finite.py:190-208, hermes/hermes_cli/friday_cli_finite.py:474-504, hermes/agent/tool_executor.py:629-648, hermes/agent/tool_executor.py:754-757, hermes/agent/tool_executor.py:1153-1172.

- R2: Sequence changes scope but does not prevent renewing one native operation. Sites: hermes/hermes_cli/friday_cli_finite_owner.py:311-331, hermes/hermes_cli/friday_cli_finite_owner.py:373-386, hermes/hermes_cli/friday_cli_finite.py:266-280, hermes/hermes_cli/friday_cli_work.py:236-255, hermes/agent/tool_executor.py:781-801.

- R3: Observer acquisition failures and adverse shutdown drop unreaped native custody. Sites: hermes/hermes_cli/friday_cli_finite_owner.py:220-245, hermes/hermes_cli/friday_cli_finite_owner.py:396-410, hermes/hermes_cli/friday_cli_finite_owner.py:412-463, hermes/hermes_cli/friday_cli_finite_owner.py:528-544.

- R4: Actual AppSession identity is not retained or checked. Sites: hermes/hermes_cli/friday_cli_output.py:102-140, hermes/hermes_cli/friday_cli_output.py:521-535, hermes/hermes_cli/friday_cli_output.py:570-687, hermes/hermes_cli/friday_cli_work.py:136-156, hermes/hermes_cli/friday_cli_finite.py:289-321, hermes/hermes_cli/friday_cli_finite.py:547-568.

- R5: Observer durable state witness does not close named-inode replacement during fsync. Sites: hermes/hermes_cli/friday_cli_finite_owner.py:54-78, hermes/hermes_cli/friday_cli_finite_owner.py:80-118.

Full source facts, counterexamples, required changes, dependency sites and meaningful controls are preserved in CLI22-FINAL5-FINDINGS.json. All corresponding complete bodies are under CLI/. No counterexample executed.
