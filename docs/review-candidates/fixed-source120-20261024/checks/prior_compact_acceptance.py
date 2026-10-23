"""Exact reviewed readonly verifier predicate; caller supplies its existing need()."""

def prior_acceptance_view(acceptance, prior, prior_ref):
    """Read the exact compact R161 receipt; do not rewrite historical documents."""
    if acceptance.get('schema') != 'frw.Root.R161.actual-installed-acceptance.v1':
        return acceptance  # Existing strict historical schema checks remain below.
    history = prior.get('installed_transaction_history')
    need(type(history) is dict and bool(history)
         and acceptance.get('state') == 'ACCEPTED_INSTALLED_FIXED119_GATEWAY_STOPPED'
         and acceptance.get('accepted') is True
         and type(acceptance.get('open_HIGH_MEDIUM')) is int and acceptance['open_HIGH_MEDIUM'] == 0
         and acceptance.get('actual_readonly_verification') == prior_ref
         and acceptance.get('actual_native_once_exit0') == prior.get('actual_execution')
         and acceptance.get('original_clock') == prior.get('original_clock_unchanged')
         and acceptance.get('accepted_under_original_useful_clock') is True
         and acceptance.get('source_layers') == prior.get('source_layers') == 119
         and acceptance.get('native_files') == prior.get('native_files_full_digest_matched') == 17717
         and acceptance.get('project_files') == prior.get('project_files') == 313
         and acceptance.get('installed_plugin_files') == prior.get('installed_plugin_files_full_digest_matched') == 46
         and acceptance.get('source_receipt_sha256') == prior.get('source_receipt_sha256') == '04a9d2a802635930db7fb7c8c72cc38e0b54a1e4f1c6fba9a185107b8d924b13'
         and acceptance.get('input_sha256') == prior.get('input_sha256')
         and type(acceptance.get('installed_history_files')) is int
         and acceptance['installed_history_files'] == len(history) == prior.get('installed_history_files')
         and prior.get('installed_history_union_authenticated') is True
         and acceptance.get('retained_data_files_unchanged') == prior.get('retained_data_files_unchanged')
         and acceptance.get('retained_directories_unchanged') == prior.get('retained_directories_identity_mode_unchanged'),
         'actual_R161_compact_acceptance_exact_pinned_verifier_and_history_required')
    # The receipt cryptographically pins the complete verifier body. Its exact
    # history is still freshly authenticated below, including q==history.
    return dict(acceptance, Root_actual_verifier_result=acceptance['actual_readonly_verification'],
                installed_transaction_history=history)
