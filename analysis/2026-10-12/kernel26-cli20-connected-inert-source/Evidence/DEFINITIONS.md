# Original and current unexecuted definitions

All rows below describe complete assertion/fixture Source retained in this archive. They are NOT_RUN for these selected bytes. Labels are intended outcomes, not observed PASS.

## Original32: exact 10 positive, 18 negative, four uncertainty definitions

| Definition | Case | Kind | Intended cause | Actual execution |
| --- | --- | --- | --- | --- |
| test_k120_first_birth_reservation | K120_FIRST_BIRTH_RESERVATION | positive | actual_atomic_clone3_into_group_and_private_pidns_before_bootstrap | NOT_RUN |
| test_k120_bootstrap_fork_thread | K120_BOOTSTRAP_FORK_THREAD | positive | actual_real_fork_and_thread_before_probe_GO | NOT_RUN |
| test_k120_opaque_import_fork_thread | K120_OPAQUE_IMPORT_FORK_THREAD | positive | actual_captured_qualification_top_level_fork_and_thread | NOT_RUN |
| test_k120_tasks128_real_limit | K120_TASKS128_REAL_LIMIT | positive | actual_kernel_tasks128_and_pids_events_max_delta | NOT_RUN |
| test_k120_controller_write_refusal | K120_CONTROLLER_WRITE_REFUSAL | positive | actual_write_open_errno13or30_without_write | NOT_RUN |
| test_k120_output_byte_inode_limit | K120_OUTPUT_BYTE_INODE_LIMIT | positive | actual_ENOSPC_bytes_and_inodes_with_bounded_lifetime_write | NOT_RUN |
| test_k120_zombie_adopted_wait | K120_ZOMBIE_ADOPTED_WAIT | positive | actual_Z_then_direct_wait_and_adopted_setsid_wait_fresh | NOT_RUN |
| test_k120_root_wait_kernel_zero | K120_ROOT_WAIT_KERNEL_ZERO | positive | actual_Root_stock_wait_then_fresh_retained_group_kernel0 | NOT_RUN |
| test_k120_root_normal_umount | K120_ROOT_NORMAL_UMOUNT | positive | actual_known_output_FD_close_before_normal_umount_fresh_absence | NOT_RUN |
| test_k120_protected_writers_unchanged | K120_PROTECTED_WRITERS_UNCHANGED | positive | actual_same_four_births_groups_and_controller_values | NOT_RUN |
| test_k120_foreign_group_fd | K120_FOREIGN_GROUP_FD | negative | Root_private_alternate_group_fd_inode | NOT_RUN |
| test_k120_unbounded_memory | K120_UNBOUNDED_MEMORY | negative | Root_private_actual_memory_max_max | NOT_RUN |
| test_k120_nonzero_swap | K120_NONZERO_SWAP | negative | Root_private_actual_swap_nonzero | NOT_RUN |
| test_k120_unbounded_tasks | K120_UNBOUNDED_TASKS | negative | Root_private_actual_pids_max_max | NOT_RUN |
| test_k120_unbounded_cpu | K120_UNBOUNDED_CPU | negative | Root_private_actual_cpu_max_max | NOT_RUN |
| test_k120_shared_writer_scope | K120_SHARED_WRITER_SCOPE | negative | actual_protected_or_outside_actor_scope_rejected_before_clone | NOT_RUN |
| test_k120_foreign_slot_fd | K120_FOREIGN_SLOT_FD | negative | Root_private_alternate_regular_slot_inode | NOT_RUN |
| test_k120_unheld_slot | K120_UNHELD_SLOT | negative | actual_FD_without_exclusive_FLOCK | NOT_RUN |
| test_k120_clock_renewal | K120_CLOCK_RENEWAL | negative | Root_expected_original_clock_pin_mismatch_no_launch | NOT_RUN |
| test_k120_final_reserve_short | K120_FINAL_RESERVE_SHORT | negative | valid_original_dual_clock_actual_remaining_insufficient | NOT_RUN |
| test_k120_useful_reserve_short | K120_USEFUL_RESERVE_SHORT | negative | valid_original_dual_clock_actual_useful_less45 | NOT_RUN |
| test_k120_already_elapsed_guardian | K120_ALREADY_ELAPSED_GUARDIAN | negative | actual_guardian_kernel_birth_expiry_not_now_plus_timer | NOT_RUN |
| test_k120_relative1800_guard | K120_RELATIVE1800_GUARD | negative | actual_original120_vs_forced1800_refuse_before_clone | NOT_RUN |
| test_k120_no_current_source_acceptance | K120_NO_CURRENT_SOURCE_ACCEPTANCE | negative | Root_refuses_entry_without_independent_exact_source_acceptance | NOT_RUN |
| test_k120_no_actual_root_admission | K120_NO_ACTUAL_ROOT_ADMISSION | negative | Root_refuses_entry_without_actual_specific_action_admission | NOT_RUN |
| test_k120_role_hard_cap_missing | K120_ROLE_HARD_CAP_MISSING | negative | actual_getrlimit_or_affinity_mismatch_before_first_birth | NOT_RUN |
| test_k120_output_not_bounded | K120_OUTPUT_NOT_BOUNDED | negative | actual_foreign_or_unbounded_mount_vfs_refusal | NOT_RUN |
| test_k120_pidfd_or_namespace_unsupported | K120_PIDFD_OR_NAMESPACE_UNSUPPORTED | negative | actual_clone3_failure_errno_no_fallback_no_retry | NOT_RUN |
| test_k120_pidfd_fstat | K120_PIDFD_FSTAT | unknown | AFTER_REAL_PIDFD_FSTAT | NOT_RUN |
| test_k120_map_go | K120_MAP_GO | unknown | AFTER_REAL_MAP_GO | NOT_RUN |
| test_k120_init_wait | K120_INIT_WAIT | unknown | AFTER_REAL_INIT_WAIT | NOT_RUN |
| test_k120_pipe_close | K120_PIPE_CLOSE | unknown | AFTER_REAL_PIPE_CLOSE | NOT_RUN |

Each definition remains in [the complete original32 Source](../Kernel/Source/test_kernel120_qualification.py.txt).

## C45 regression definitions

The current batch file contains 19 definitions; the author's repair describes 18 affected C45 memory definitions migrated to the current API. Those are static provenance counts, not execution results. The retained-FD file contains eight definitions.

### Source/test_c45_root_batch.py

- test_c45_missing_actual_root_provider — NOT_RUN
- test_c45_wrong_original_source_budget — NOT_RUN
- test_c45_dualclock_drift — NOT_RUN
- test_c45_renewed_final — NOT_RUN
- test_c45_nonfinite_bool_clock — NOT_RUN
- test_c45_complete_original_clock_positive — NOT_RUN
- test_c45_wait_after_firstbirth — NOT_RUN
- test_c45_candidate_json_is_not_wait_proof — NOT_RUN
- test_c45_case_mapping_unbound_before_provider — NOT_RUN
- test_c45_plan_mapping_unbound — NOT_RUN
- test_c45_missing_provider_after_synthetic_mapping — NOT_RUN
- test_c45_candidate_mapping_cannot_replace_original — NOT_RUN
- test_c45_unmeasured_whole32_fit — NOT_RUN
- test_c45_missing_or_repeated_original_case — NOT_RUN
- test_c45_phase_clock_reset — NOT_RUN
- test_c45_original_cut_window_not_common_batch_assumption — NOT_RUN
- test_c45_conditional_serial_reservations_conflict — NOT_RUN
- test_c45_no_invented_parallel_topology — NOT_RUN
- test_c45_trace_driver_full32_not_partial — NOT_RUN

[Complete inert definition file](../Kernel/Source/test_c45_root_batch.py.txt).

### Source/test_c45_root_fd_custody.py

- test_root_fd_normal_capture — NOT_RUN
- test_root_fd_fstat_failure_registered — NOT_RUN
- test_root_fd_identity_failure_registered — NOT_RUN
- test_root_fd_open_failure_no_lost_handle — NOT_RUN
- test_root_fd_dup_failure_retains_exterior — NOT_RUN
- test_root_fd_close_ambiguity_no_retry — NOT_RUN
- test_root_fd_partial_target_failure_retained — NOT_RUN
- test_root_fd_full_finalizer_order_static — NOT_RUN

[Complete inert definition file](../Kernel/Source/test_c45_root_fd_custody.py.txt).

## CLI28 original-owner contract scenarios

One parametrized function describes all 28 scenarios. The fixture is unbound and every scenario is NOT_RUN.

| Scenario | Intended state | Actual execution |
| --- | --- | --- |
| direct_positive | DELIVERED | NOT_RUN |
| wrapped_positive | DELIVERED | NOT_RUN |
| whole_set_multiple_artifacts | DELIVERED | NOT_RUN |
| caller_shorter_original_budget | UNKNOWN | NOT_RUN |
| slow_metadata_before_reservation | NO_SEND | NOT_RUN |
| slow_metadata_terminal_publication | UNKNOWN | NOT_RUN |
| slow_native_renderer_cpu | UNKNOWN | NOT_RUN |
| slow_input_detach | UNKNOWN | NOT_RUN |
| slow_input_cooked_exit | UNKNOWN | NOT_RUN |
| slow_native_redraw | UNKNOWN | NOT_RUN |
| stop_before_write | NO_SEND | NOT_RUN |
| stop_during_partial_write | UNKNOWN | NOT_RUN |
| revoke_before_dispatch | NO_SEND | NOT_RUN |
| revoke_after_partial_output | UNKNOWN | NOT_RUN |
| generation_change_before_terminal_save | UNKNOWN | NOT_RUN |
| cancel_during_owned_read | NO_SEND | NOT_RUN |
| cancel_during_renderer_write | UNKNOWN | NOT_RUN |
| cancel_during_native_join | UNKNOWN | NOT_RUN |
| late_native_done_callback | UNKNOWN | NOT_RUN |
| output_close_ambiguous | UNKNOWN | NOT_RUN |
| input_close_ambiguous | NO_SEND | NOT_RUN |
| primary_with_output_cleanup_failure | UNKNOWN | NOT_RUN |
| primary_with_input_cleanup_failure | NO_SEND | NOT_RUN |
| primary_with_metadata_cleanup_failure | NO_SEND | NOT_RUN |
| explicit_retry_unknown_forbidden | NO_SEND | NOT_RUN |
| automatic_replay_unknown_forbidden | NO_SEND | NOT_RUN |
| late_atomic_replace | UNKNOWN | NOT_RUN |
| late_directory_fsync | UNKNOWN | NOT_RUN |

[Complete CLI scenario Source](../CLI/Tests/test_c52_actual_contract.py.txt). Original106 consists of 66+37+3 definitions in historical programs; six exact prior programs/renderer controls plus this new program are retained. Their historical paths need current rebinding before any actual use.
