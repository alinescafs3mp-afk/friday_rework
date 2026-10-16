"""Finite ordinary Telegram source activation; native owners retain the receiver.

There is one explicit reviewed deployment transaction. It never resets a CLI
clock, executes a consumed query, enables a worker, approves a user or starts a
consumer. Subsequent service starts use the installed native CLI and unit.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
from pathlib import Path
import stat

MANIFEST = 'patches/hermes/ordinary-telegram-manifest.json'
TRANSACTION = 'preparation/ordinary-gateway'
UPDATE_MANIFEST = 'patches/hermes/ordinary-native-repair-manifest.json'
UPDATE_FILES = {'hermes_cli/friday_dashboard_owner.py', 'hermes_cli/friday_credential_admission.py'}
PRIVATE_STATE_MANIFEST = 'patches/hermes/ordinary-private-state-manifest.json'
PRIVATE_STATE_FILES = {'hermes_cli/plugins_state.py', 'utils.py'}
FILE_CONTINUATION_MANIFEST = 'patches/hermes/ordinary-file-continuation-manifest.json'
FILE_CONTINUATION_FILES = {'hermes_cli/friday_user_scope.py', 'gateway/run_inbound_media.py',
    'gateway/platforms/base.py', 'gateway/run_notifications.py', 'gateway/run_plugin_delivery.py',
    'gateway/run_turn.py', 'plugins/platforms/telegram/adapter.py'}
WORKER_ATTACH_PLUGIN_FILES = {'plugins/friday_rework/onboarding.py',
    'plugins/friday_rework/worker_provision.py', 'plugins/friday_rework/dashboard/api.py',
    'plugins/friday_rework/dashboard/index.js'}

ADMIN_RESTART_MANIFEST = 'patches/hermes/ordinary-admin-restart-manifest.json'
ADMIN_RESTART_FILES = {'hermes_cli/web_server.py', 'hermes_cli/friday_dashboard_owner.py', 'hermes_cli/gateway.py'}

ADMIN_BROADCAST_MANIFEST = 'patches/hermes/ordinary-admin-broadcast-manifest.json'
ADMIN_BROADCAST_FILES = {'hermes_cli/free_tier_bootstrap.py'}

WEB_CONTINUATION_MANIFEST = 'patches/hermes/ordinary-web-continuation-manifest.json'
WEB_CONTINUATION_FILES = {'tools/web_tools_truncate.py', 'tools/web_tools.py', 'model_tools.py'}

WEB_OUTPUT_MANIFEST = 'patches/hermes/ordinary-web-output-manifest.json'
WEB_OUTPUT_FILES = {'agent/bounded_context.py', 'tools/web_tools_truncate.py', 'tools/web_tools.py', 'tools/file_tools.py', 'hermes_cli/friday_user_scope.py'}

SEARCH_RECOVERY_MANIFEST = 'patches/hermes/ordinary-search-recovery-manifest.json'
SEARCH_RECOVERY_FILES = {'tools/web_tools.py', 'tools/web_tools_truncate.py'}

# One reviewed Native78 -> Native79 boundary. Final public native pins must be
# bound after the frozen patch/manifest are independently reviewed; None refuses
# execution, including dry preparation against mutable native afterimages.
SPARK_MULTIPASS_MANIFEST = 'patches/hermes/spark-primary-multipass-manifest.json'
SPARK_MULTIPASS_PATCH = 'patches/hermes/spark-primary-multipass.patch'
SPARK_MULTIPASS_MANIFEST_SHA256 = '37cb4931953833926827f24d9018db667444b34fd3cd3bdb99a71b35a2793919'
SPARK_MULTIPASS_PATCH_SHA256 = 'bc3f5363b2fe33306b5ae66e2dfc1fab5057b1abe0ff44225cdd0d749b1f9fdc'
SPARK_MULTIPASS_PREVIOUS_INPUT = '7aeee4cadb96ce5e4ce392ccbecfb34df691ffae6bf9c1dca46f2d0112782896'
SPARK_MULTIPASS_NEW_FILES = {'agent/context_compressor_multipass.py',
    'tests/agent/test_bounded_multipass.py', 'tests/hermes_cli/test_friday_compression_role.py'}
SPARK_MULTIPASS_FILES = SPARK_MULTIPASS_NEW_FILES | {'agent/auxiliary_client.py',
    'agent/bounded_context.py', 'agent/bounded_summary_output.py', 'agent/context_compressor.py',
    'agent/context_compressor_summary.py', 'agent/conversation_compression.py',
    'agent/usage_anchor.py', 'agent/process_bootstrap.py', 'hermes_state_compression.py', 'hermes_cli/friday_credential_admission.py'}
SPARK_MULTIPASS_PLUGIN_FILES = {'plugins/friday_rework/onboarding.py'}
SPARK_MULTIPASS_NATIVE_FILES = 17683
SPARK_MULTIPASS_PROJECT_BEFORE = {'plugins/friday_rework/onboarding.py': '63f1476661fb4e1dff0a828cd11c298d89661025416836bb115e8ab6abd529b6', 'scripts/friday_ordinary_install.py': '8d8b9cc23f2436ff9903ef29671c97d6147e10d62194cd20e300e9e39a11a1ac', 'tools/configure_local_test.py': '0bc17aa5d2f6e9aa75fad10246205421f49db23e91300fab11900c269bf9666e', 'tools/configure_product.py': '0494489e42f17558893d5372aa988d74ab8a148108836add71eb5a7f440cefdc', 'scripts/friday_install.py': '8b9109adc3b690b47791ff1b9d75073b812e502ac16810361a1692059f0f67dd'}
SPARK_MULTIPASS_PROJECT_AFTER = {'plugins/friday_rework/onboarding.py': '42e262612c464e81568dbcc30266b0c67be365f1cb780fa1700a04ca59ec5c42', 'tools/configure_local_test.py': '0794011d5a06842046746b437ac7beed9eb8da1d18d8b822d701a8f91ca8c523', 'tools/configure_product.py': '7d5ce5209e21c41442e6c44598a85accc011a5c3f6c81c772fe85d9dd2016a82', 'scripts/friday_install.py': '73521e7a4dd09b243d41c9db0869bcfc2bd85e0ecd3eac22537dbe4cbeda8901'}

# Source79/helper-v4 -> Source80: unreviewed native/producer pins refuse execution.
SPARK_REQUEST_BUDGET_MANIFEST = 'patches/hermes/spark-request-budget-manifest.json'
SPARK_REQUEST_BUDGET_PATCH = 'patches/hermes/spark-request-budget.patch'
SPARK_REQUEST_BUDGET_MANIFEST_SHA256 = '0df5366e1f18905c96a8e80df85165fd50a68d8f0e4dfc41178c43165182c16b'
SPARK_REQUEST_BUDGET_PATCH_SHA256 = 'e6840b425e01444036f6f1b8b147bca6b9d2fcf883bdb0e07d3ba09aadfaf708'
SPARK_REQUEST_BUDGET_PREVIOUS_INPUT = '2c0c0ae479145a658ba1b089f82bdfcfdeca1fa14586ac853a9331457f641f7c'
SPARK_REQUEST_BUDGET_NEW_FILES = {'agent/request_budget.py', 'gateway/run_turn_status.py', 'tests/agent/test_named_request_budget.py', 'tests/agent/test_nonstream_request_budget.py', 'tests/agent/test_request_budget_terminal.py', 'tests/gateway/test_telegram_live_turn_status.py', 'tests/hermes_cli/test_named_request_budget.py'}
SPARK_REQUEST_BUDGET_FILES = {'agent/chat_completion_helpers.py', 'agent/chat_completion_nonstream.py', 'agent/chat_completion_stream_monitor.py', 'agent/client_lifecycle.py', 'agent/history_commentary.py', 'agent/request_budget.py', 'agent/turn_api_error.py', 'agent/turn_response_intake.py', 'gateway/platforms/api_server.py', 'gateway/platforms/api_server_openai_routes.py', 'gateway/platforms/base.py', 'gateway/run_turn.py', 'gateway/run_turn_runner.py', 'gateway/run_turn_status.py', 'gateway/turn_context.py', 'hermes_cli/config_providers.py', 'hermes_cli/friday_user_scope.py', 'hermes_cli/timeouts.py', 'hermes_cli/web_routers/sessions.py', 'run_agent.py', 'tests/agent/test_named_request_budget.py', 'tests/agent/test_nonstream_request_budget.py', 'tests/agent/test_privacy_effect_semantics.py', 'tests/agent/test_request_budget_terminal.py', 'tests/gateway/test_telegram_live_turn_status.py', 'tests/hermes_cli/test_named_request_budget.py'}
SPARK_REQUEST_BUDGET_PLUGIN_FILES = {'plugins/friday_rework/user_worker_join.py'}
SPARK_REQUEST_BUDGET_NATIVE_FILES = 17686
SPARK_REQUEST_BUDGET_PROJECT_BEFORE = {
    'scripts/friday_ordinary_install.py':'ea37453fee3a919f196b0cb0a906bcfe6f7b04d21a698cb3f731c31e90a1d907',
    'tools/configure_local_test.py':'0794011d5a06842046746b437ac7beed9eb8da1d18d8b822d701a8f91ca8c523',
    'tools/configure_product.py':'7d5ce5209e21c41442e6c44598a85accc011a5c3f6c81c772fe85d9dd2016a82',
    'plugins/friday_rework/user_worker_join.py':'3bc8de8bff973b2e782cd4157fba97178d0b960d4a7bf88ae978492e845bd9e8',
}
# The updater is pinned by current_input, avoiding a self-referential hash.
SPARK_REQUEST_BUDGET_PROJECT_AFTER = {
    'tools/configure_local_test.py':'6859d082f85620c160b388a9b70077cb8ac59393bdb9af5739315a4f15fb1c19',
    'tools/configure_product.py':'0dc06e69e81f448b9da3627711b28d9433f559915c8db52cf189e7a7a1501216',
    'plugins/friday_rework/user_worker_join.py':'ad10ba044308a0bcdf1697998a37fb33a8d3737025ea2a6e4e244dd3122a9cf2',
}

SOURCE80_HELPER_REQUEST = '85146114e897d29fa2540f026716c018eef2d4700045be941775de8c86462e3a'
SOURCE80_REBIND_REQUEST = 'cdd6438774d0081e5969e6e39c097232b3979f33e2e89d6c406c39d8a379a97b'
SOURCE80_REBIND_INTENT = '059efd03e5323114c9f759d92096e4c9623dadc24d1ed7ebe23b8af10f3d10eb'
SOURCE80_REBIND_COMMITTED = 'ca24f428f0ae4f611a5eaa9c86087db82f11d505799cbc6b9b23d6369c17978f'
SOURCE80_HISTORY_FILES = 566

# One exact Source80 + closed budget-only v2 -> Source81 source transition.
FILE_TOOL_CONTRACT_MANIFEST = 'patches/hermes/ordinary-file-tool-contract-manifest.json'
FILE_TOOL_CONTRACT_PATCH = 'patches/hermes/ordinary-file-tool-contract.patch'
FILE_TOOL_CONTRACT_MANIFEST_SHA256 = 'c0b847d230e4ac03e91c455a2f07282a8b117cfc95f6d207b0c89216a0b12007'
FILE_TOOL_CONTRACT_PATCH_SHA256 = '6c053a31678b7ebbf66167d465a7d54b66ad177082090b5d47f4cf3c8bff1a8a'
FILE_TOOL_CONTRACT_FILES = {'model_tools.py','hermes_cli/friday_prompt_scope.py','agent/system_prompt.py','gateway/run.py'}
FILE_TOOL_CONTRACT_PREVIOUS_INPUT = '7ed481576a38ccc7f99e38f92b25e733dc9b90fa84a613e21aa47d9f97306524'
FILE_TOOL_CONTRACT_NATIVE_FILES = 17693
FILE_TOOL_CONTRACT_PLUGIN_FILES = {'plugins/friday_rework/admin_settings.py'}
FILE_TOOL_CONTRACT_PROJECT_BEFORE = {'scripts/friday_ordinary_install.py': '3576edd1374d5093477aa4412af7dc4382c4c1d8036f3e312a724cbf44408290', 'plugins/friday_rework/admin_settings.py': '8e5642aaa9581448fc3a31f187461a914c26127065194f4c78fc7f92546eea5f'}
FILE_TOOL_CONTRACT_PROJECT_AFTER = {'plugins/friday_rework/admin_settings.py': '1b9f3ef44ab9483ff2ea230ae9d00640510ee8bc35e645feb2b01483ebc3510e'}
SOURCE81_PREDECESSOR_REQUEST = 'a10f7fde0f63ef317dda4eeefeacabf487518362d5af4bc13b28c57e475782f3'
SOURCE81_BUDGET_REQUEST = '5aaebaa33a549fbf5878d25f8b76c1ec4295fea9f18a7083eab46f6479b9459c'
SOURCE81_BUDGET_INTENT = '05ba73d4226f5e1e10e6bd9cfd983b57d0e0a3d3ef3c2062fc2a2dd1f10137c3'
SOURCE81_BUDGET_COMMITTED = '35635275e9b9d84a7b9cf8b44711cb29d381ae28f23eb6c506c32dd86949ed9a'
SOURCE81_HISTORY_FILES = 632
SOURCE81_RETAINED_FILES = 669

# Exact Source81 -> Source82 web credential boundary; no operational rewrite.
WEB_INPUT_MANIFEST = 'patches/hermes/ordinary-web-input-privacy-manifest.json'
WEB_INPUT_PATCH = 'patches/hermes/ordinary-web-input-privacy.patch'
WEB_INPUT_MANIFEST_SHA256 = 'b75fe7b0a44e740c3cdd1258fd7cf4c71720faee3728d468929ecbdd6412cab1'
WEB_INPUT_PATCH_SHA256 = '640ad9dcce0627bdd942df9c29713f5483d7dcfee6a7dceef81332749fdd1567'
WEB_INPUT_FILES = {'tools/web_tools.py','tools/web_tools_extract.py'}
WEB_INPUT_PREVIOUS_INPUT = '58d2f1eeb34b844a5cfd6b59b262f8a820c05614fca9aefe88ceb74b5be93038'
WEB_INPUT_PREDECESSOR_REQUEST = 'bc2fd9911709a89c59748e6946ae78b7c648da9d4d16b3121aac5224d24fb30c'
WEB_INPUT_PREVIOUS_UPDATER = '23fb0ed00ca2cda041ca07115847f232de01061648863b930d16ea55f0f72cca'
WEB_INPUT_NATIVE_FILES = 17693
WEB_INPUT_HISTORY_FILES = 646
WEB_INPUT_SELECTED_CONFIG = 'fe8a6ae2c6998b57f67f75e7affc35d988c30a800baae1daece8569c031af4fd'
WEB_INPUT_PROFILE_FILES = {'profiles/dest_telegram/'+n for n in
    ('config.yaml','.friday-onboarding.json','.friday-user-scope.json','.env')}

# Package Source83: one combined native layer directly on installed Source81.
# Source82/v36 was prepared only; it is never accepted as executed ancestry here.
COMBINED_INPUT_MANIFEST = 'patches/hermes/ordinary-web-delivery-privacy-manifest.json'
COMBINED_INPUT_PATCH = 'patches/hermes/ordinary-web-delivery-privacy.patch'
COMBINED_INPUT_MANIFEST_SHA256 = 'f80b64f11c2a9bdfdd37ef5bdc87a9edd5534f30f19b04c4a8562fd08a6a8d3a'
COMBINED_INPUT_PATCH_SHA256 = '5fc427aeb1298e6137941ad1162524b896b497f4c842f907b9db5dfac4536506'
COMBINED_INPUT_FILES = {'tools/web_tools.py','tools/web_tools_extract.py',
    'gateway/run_plugin_delivery.py','hermes_cli/friday_user_scope.py',
    'hermes_cli/friday_prompt_scope.py'}
COMBINED_INPUT_PREVIOUS_INPUT = '58d2f1eeb34b844a5cfd6b59b262f8a820c05614fca9aefe88ceb74b5be93038'
COMBINED_INPUT_PREDECESSOR_REQUEST = 'bc2fd9911709a89c59748e6946ae78b7c648da9d4d16b3121aac5224d24fb30c'
COMBINED_INPUT_PREVIOUS_UPDATER = '23fb0ed00ca2cda041ca07115847f232de01061648863b930d16ea55f0f72cca'
COMBINED_INPUT_NATIVE_FILES = 17693
COMBINED_INPUT_HISTORY_FILES = 646

# Source84: one reviewed native file presentation layer on committed Source83.
# No mutable afterimages are admitted. Final patch, manifest and exact target set
# are bound together after composition; None fails before reading runtime inputs.
FILE_REPLY_CONTEXT_MANIFEST = 'patches/hermes/ordinary-file-reply-context-caption-manifest.json'
FILE_REPLY_CONTEXT_PATCH = 'patches/hermes/ordinary-file-reply-context-caption.patch'
FILE_REPLY_CONTEXT_MANIFEST_SHA256 = '7c8bbe7894d2c6a85bb75dd3f7ba17e9631a05d47398383d53ab4e0d4bae87e0'
FILE_REPLY_CONTEXT_PATCH_SHA256 = '6be8c37934121f9c8fcabd9d1d4cbdf855785a6cde4673c9825f4f7a2da5295c'
FILE_REPLY_CONTEXT_FILES = {'agent/agent_runtime_helpers.py','agent/chat_completion_helpers.py','agent/context_compressor.py','agent/context_compressor_multipass.py','agent/conversation_compression.py','agent/turn_context.py','gateway/platforms/base.py','gateway/run_plugin_delivery.py','hermes_cli/friday_user_scope.py'}
FILE_REPLY_CONTEXT_PREVIOUS_INPUT = 'f50b97045eaa0a18aa43f99f73701b60fb13c2705058e397b456bc5372172c72'
FILE_REPLY_CONTEXT_PREDECESSOR_REQUEST = 'e03b886b92b37b604b19dbfb19a9bc8d497f76400cf792085b1bc99636137d13'
FILE_REPLY_CONTEXT_PREDECESSOR_COMMITTED = 'f1320cb2d5d800355ab98e72f5fb9bebd12ae50280b52e757b74c31bc3142f92'
FILE_REPLY_CONTEXT_PREVIOUS_UPDATER = '4ce32ffd2e70896f88256e5ab33f63b74223d210599b3941f3e3e660e389909b'
FILE_REPLY_CONTEXT_NATIVE_FILES = 17693
FILE_REPLY_CONTEXT_HISTORY_FILES = 661

# Source85: one reviewed combined web/runtime/history layer on committed Source84.
# No mutable afterimages are admitted. Final patch, manifest and exact target set
# are bound together after composition; None fails before reading runtime inputs.
WEB_RUNTIME_HISTORY_MANIFEST = 'patches/hermes/ordinary-web-runtime-history-manifest.json'
WEB_RUNTIME_HISTORY_PATCH = 'patches/hermes/ordinary-web-runtime-history.patch'
WEB_RUNTIME_HISTORY_MANIFEST_SHA256 = 'b1c7ee3f1df0517a2167c26b2cc5a13b1bdea2c4a32f9a66f301f3e8cb4b6bef'
WEB_RUNTIME_HISTORY_PATCH_SHA256 = 'e8d6651fd3563cb63148289d1ea44b3985dfd9eaf92fec8d1b3fbf572cb3f324'
WEB_RUNTIME_HISTORY_FILES = {'agent/chat_completion_helpers.py','agent/turn_context.py','agent/turn_request_assembly.py','hermes_cli/friday_user_scope.py','tools/browser_process_child.py','tools/web_process.py','tools/web_process_child.py'}
WEB_RUNTIME_HISTORY_PREVIOUS_INPUT = '2b353a5c4aecfcb2cd3f8c401bc83965b0827aa8b54e68fb650ae4dd52a896e0'
WEB_RUNTIME_HISTORY_PREDECESSOR_REQUEST = 'c7b7b3eb267350bccbc46a66b3401f79e8e32afc784376b6b487834a7ba80458'
WEB_RUNTIME_HISTORY_PREDECESSOR_COMMITTED = '39d41a417c2431885aa4d34410ff4a0b091c8e158b0496d7355b4d63e0e4c0a0'
WEB_RUNTIME_HISTORY_PREVIOUS_UPDATER = '439f33677ecf9698e66f98cb9c13f85e301867a928e8c6caa325b47947741b4d'
WEB_RUNTIME_HISTORY_NATIVE_FILES = 17693
WEB_RUNTIME_HISTORY_HISTORY_FILES = 684

PRIVACY_EFFECT_MANIFEST = 'patches/hermes/ordinary-private-refusal-effect-manifest.json'
PRIVACY_EFFECT_NEW_FILES = {'tests/agent/test_privacy_effect_semantics.py'}
PRIVACY_EFFECT_FILES = PRIVACY_EFFECT_NEW_FILES | {'agent/tool_executor.py', 'agent/tool_result_classification.py', 'agent/turn_context.py', 'agent/turn_finalizer.py', 'gateway/run_turn.py', 'gateway/run_turn_runner.py', 'hermes_cli/friday_user_scope.py'}
PRIVACY_EFFECT_PLUGIN_FILES = {'plugins/friday_rework/user_worker_join.py'}
PRIVACY_EFFECT_NATIVE_FILES = 17682
PRIVACY_EFFECT_PLUGIN_BEFORE = 'e0dab0f3a21c3ac3ce841aa6d8176d4fd60ea4c57f6b633cdc0e2091e3e55358'
PRIVACY_EFFECT_PLUGIN_AFTER = '3bc8de8bff973b2e782cd4157fba97178d0b960d4a7bf88ae978492e845bd9e8'

DOCX_CREATION_MANIFEST = 'patches/hermes/ordinary-docx-creation-manifest.json'
DOCX_CREATION_FILES = {'hermes_cli/friday_user_scope.py','tools/file_tools.py','hermes_cli/friday_workspace_docx.py','hermes_cli/friday_plain_docx_template.b64','hermes_cli/friday_plain_docx_template.LICENSE'}
DOCX_CREATION_NEW_FILES = {'hermes_cli/friday_workspace_docx.py','hermes_cli/friday_plain_docx_template.b64','hermes_cli/friday_plain_docx_template.LICENSE'}

DOCUMENT_EXTRACTION_MANIFEST = 'patches/hermes/ordinary-document-extraction-manifest.json'
DOCUMENT_EXTRACTION_FILES = {'hermes_cli/friday_user_scope.py','tools/read_extract.py'}

FILE_REVISION_MANIFEST = 'patches/hermes/ordinary-file-revision-manifest.json'
FILE_REVISION_NEW_FILES = {'hermes_cli/friday_workspace_revision.py'}
FILE_REVISION_FILES = FILE_REVISION_NEW_FILES | {'hermes_cli/friday_user_scope.py','tools/file_tools.py','agent/tool_executor.py','agent/turn_api_call.py','gateway/run_plugin_delivery.py'}

TOOL_RESULT_CONTEXT_MANIFEST = 'patches/hermes/ordinary-tool-result-context-manifest.json'
TOOL_RESULT_CONTEXT_FILES = {'agent/tool_executor.py','agent/web_call_context.py','run_agent.py'}

DSH_SANDBOX_MANIFEST = 'patches/hermes/ordinary-dsh-native-sandbox-profile-manifest.json'
DSH_SANDBOX_FILES = {'tools/render_dsh_local.py','gateway/run_turn_runner.py'}

CURRENT_TURN_MANIFEST = 'patches/hermes/ordinary-current-turn-compaction-privacy-reply-manifest.json'
CURRENT_TURN_FILES = set(['agent/bounded_context.py', 'agent/bounded_summary_output.py', 'agent/context_compressor.py', 'agent/turn_context.py', 'agent/turn_context_compaction.py', 'agent/turn_finalizer.py', 'gateway/run_turn.py', 'hermes_cli/friday_user_scope.py'])
CONTEXT_SELF_MANIFEST = 'patches/hermes/ordinary-context-self-disclosure-manifest.json'
CONTEXT_SELF_PLUGIN_FILES = {'plugins/friday_rework/admin_settings.py'}
CONTEXT_SELF_FILES = {'agent/bounded_context.py', 'agent/conversation_compression.py', 'agent/chat_completion_helpers.py', 'agent/turn_context.py', 'hermes_cli/friday_prompt_scope.py', 'hermes_cli/friday_user_scope.py'}
PRIVATE_REPLY_MANIFEST = 'patches/hermes/ordinary-private-reply-compression-manifest.json'
PRIVATE_REPLY_FILES = {'agent/bounded_context.py', 'agent/chat_completion_helpers.py', 'agent/conversation_compression.py', 'agent/session_persistence.py', 'agent/stream_delivery.py', 'agent/system_prompt.py', 'agent/turn_context.py', 'agent/turn_finalizer.py', 'agent/turn_tool_round.py', 'gateway/platforms/base.py', 'gateway/run_turn.py', 'hermes_cli/friday_prompt_scope.py', 'hermes_cli/friday_user_scope.py', 'tools/registry.py'}
PROMPT_PRIVACY_MANIFEST = 'patches/hermes/ordinary-prompt-privacy-dialogue-manifest.json'
PROMPT_PRIVACY_FILES = {'hermes_cli/friday_prompt_scope.py', 'agent/prompt_builder.py', 'agent/system_prompt.py'}
MEMORY_SCOPE_MANIFEST = 'patches/hermes/ordinary-memory-scope-privacy-manifest.json'
MEMORY_SCOPE_FILES = {'tools/memory_tool_store.py', 'tools/write_approval.py', 'hermes_cli/write_approval_commands.py', 'hermes_cli/friday_user_scope.py', 'tools/memory_tool.py'}
FIRST_CONTACT_COPY_MANIFEST = 'patches/hermes/ordinary-first-contact-copy-manifest.json'
FIRST_CONTACT_COPY_FILES = {'gateway/slash_commands.py', 'agent/onboarding.py', 'gateway/run_turn.py'}
INLINE_PRIVACY_MANIFEST = 'patches/hermes/ordinary-inline-privacy-connected-repair-manifest.json'
INLINE_PRIVACY_FILES = {'gateway/run_turn.py', 'agent/inline_tool_executors.py'}
TOOL_METADATA_MANIFEST = 'patches/hermes/ordinary-tool-metadata-progress-privacy-manifest.json'
TOOL_METADATA_FILES = set(['agent/turn_finalizer.py', 'gateway/platforms/base.py', 'gateway/run_busy.py', 'gateway/run_turn.py', 'hermes_cli/friday_user_scope.py', 'tools/registry.py', 'tools/session_search_tool.py'])
TOOL_METADATA_PLUGIN_FILES = {'plugins/friday_rework/adapters/dsh.py','plugins/friday_rework/artifacts.py','plugins/friday_rework/results.py'}
PUBLIC_SURFACE_MANIFEST = 'patches/hermes/ordinary-public-surface-privacy-manifest.json'
PUBLIC_SURFACE_FILES = {'gateway/slash_commands_status.py', 'hermes_cli/dashboard_auth/middleware.py', 'hermes_cli/friday_product_access.py', 'gateway/slash_commands_session.py', 'gateway/platforms/base.py', 'gateway/slash_commands.py', 'hermes_cli/friday_user_scope.py', 'gateway/run_turn.py', 'tools/registry.py', 'gateway/run_busy.py'}
WORKER_TOOLS_MANIFEST = 'patches/hermes/ordinary-worker-tools-packaging-manifest.json'
WORKER_TOOLS_PLUGIN_FILES = {'plugins/friday_rework/worker_provision.py', 'plugins/friday_rework/onboarding.py', 'plugins/friday_rework/user_worker_join.py'}
WORKER_TOOLS_FILES = {'tools/render_dsh_local.py', 'tools/web_profile.py', 'config/RESEARCH.md'}
DIALOGUE_CONTINUATION_MANIFEST = 'patches/hermes/ordinary-dialogue-continuation-manifest.json'
DIALOGUE_CONTINUATION_FILES = {'hermes_cli/friday_prompt_scope.py', 'agent/system_prompt.py'}

FIRST_CONTACT_STATE_MANIFEST = 'patches/hermes/ordinary-first-contact-state-manifest.json'
FIRST_CONTACT_STATE_FILES = {'agent/onboarding.py'}

TURN_SCOPE_MANIFEST = 'patches/hermes/ordinary-telegram-turn-scope-manifest.json'
TURN_SCOPE_FILES = {'gateway/run_inbound.py'}

ADMIN_STARTUP_MANIFEST = 'patches/hermes/ordinary-admin-startup-manifest.json'
ADMIN_STARTUP_FILES = {'hermes_cli/friday_dashboard_owner.py'}

INTERACTION_SCOPE_MANIFEST = 'patches/hermes/ordinary-interaction-scope-manifest.json'
INTERACTION_SCOPE_FILES = {'gateway/run_inbound_consumer.py',
    'hermes_cli/friday_dashboard_owner.py', 'hermes_cli/web_routers/status.py'}

PROFILE_RUNTIME_MANIFEST = 'patches/hermes/ordinary-profile-runtime-manifest.json'
PROFILE_RUNTIME_FILES = {'hermes_cli/friday_credential_admission.py', 'gateway/config.py',
    'gateway/run_adapters.py', 'hermes_cli/friday_gateway_owner.py',
    'hermes_cli/friday_dashboard_owner.py', 'hermes_cli/friday_product_access.py'}

BROWSER_GATEWAY_MANIFEST = 'patches/hermes/ordinary-browser-gateway-manifest.json'
BROWSER_GATEWAY_FILES = {'hermes_cli/friday_ordinary_gateway.py'}

BROWSER_MANIFEST = 'patches/hermes/ordinary-browser-manifest.json'
BROWSER_NEW_FILES = {'tools/browser_scoped.py', 'tools/browser_process_child.py',
    'tools/browser_public_transport.py', 'tools/browser_native_ipc.py'}
BROWSER_FILES = BROWSER_NEW_FILES | {'hermes_cli/friday_user_scope.py', 'toolsets.py',
    'tools/browser_tool.py', 'tools/browser_tool_lifecycle.py', 'tools/process_registry_web.py'}
BROWSER_PLUGIN_FILES = {'plugins/friday_rework/admin.py', 'plugins/friday_rework/onboarding.py',
    'plugins/friday_rework/dashboard/api.py', 'plugins/friday_rework/dashboard/index.js'}


def api():
    from scripts import friday_install
    return friday_install


def prepare_workers(request, request_path, budget):
    """Continue installation declarations without changing the receiving runtime."""
    from scripts.friday_worker_preparation import prepare
    return prepare(request, request_path, budget)


def write(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def replace(path, data, mode=0o600):
    temporary = path.with_name(path.name + '.ordinary-staged')
    fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        os.fchmod(fd,mode)  # Preserve the exact beforeimage mode under any umask.
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()
    fd = os.open(path.parent, os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def update_file_state(path):
    """Exact bytes and inode custody; absence is never an empty beforeimage."""
    f = api()
    if not os.path.lexists(path): return None
    first = path.lstat()
    data = f.owned_file(path)
    last = path.lstat()
    keys = ('st_dev','st_ino','st_uid','st_nlink','st_mode')
    identity = tuple(getattr(first,k) for k in keys)
    f.require(identity == tuple(getattr(last,k) for k in keys), 'ordinary_update_file_identity_changed')
    return {'data':data,'mode':stat.S_IMODE(first.st_mode),'identity':identity}


def same_update_file(path, expected):
    return update_file_state(path) == expected


def publish_update_file(path, data, mode, before, owned, name):
    """Publish one recorded inode; new files use an exclusive hard-link claim."""
    f = api(); temporary = path.with_name(path.name+'.ordinary-staged')
    try:
        fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    except FileExistsError as exc:
        from scripts.dsh_prepare import StopUnconfirmed
        raise StopUnconfirmed('ordinary update staging path ownership requires reconciliation') from exc
    created = None
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(data);stream.flush();os.fsync(fd)
        st = os.fstat(fd)
        created = {'data':data,'mode':mode,'identity':tuple(getattr(st,k) for k in
            ('st_dev','st_ino','st_uid','st_nlink','st_mode'))}
        f.require(same_update_file(path,before),'ordinary_update_publication_identity_changed')
        f.require(same_update_file(temporary,created),'ordinary_update_staging_identity_changed')
        owned[name] = created
        if before is None:
            os.link(temporary,path,follow_symlinks=False)
            # owned_file intentionally rejects hard links; here both names
            # must still identify exactly our descriptor before unlinking one.
            linked = tuple(2 if i == 3 else value for i,value in enumerate(created['identity']))
            for candidate in (temporary,path):
                info=candidate.lstat()
                f.require(tuple(getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_nlink','st_mode'))
                    == linked,'ordinary_update_link_identity_changed')
            temporary.unlink()
        else:
            os.replace(temporary,path)
        f.require(same_update_file(path,created),'ordinary_update_published_identity_changed')
        sync_directory(path.parent)
    finally:
        os.close(fd)
        if os.path.lexists(temporary):
            # If publication failed, only our own exact staging inode is removed.
            if created is None or not same_update_file(temporary,created):
                from scripts.dsh_prepare import StopUnconfirmed
                raise StopUnconfirmed('ordinary update staging ownership requires reconciliation')
            temporary.unlink()


def restore_update_files(home, saved, owned):
    f = api()
    # Prove the entire affected set before changing any path. Same bytes on a
    # foreign inode or with a changed mode do not confer restoration ownership.
    for name,before in saved.items():
        state = update_file_state(home/name)
        f.require(state == before or (name in owned and state == owned[name]),
            'ordinary_update_restore_ownership_changed')
    restored = {}
    for name,before in reversed(list(saved.items())):
        path = home/name; state = update_file_state(path)
        if state == before: continue
        f.require(name in owned and state == owned[name],'ordinary_update_restore_ownership_changed')
        if before is None:
            path.unlink(); sync_directory(path.parent)
        else:
            publish_update_file(path,before['data'],before['mode'],owned[name],restored,name)
    for name,before in saved.items():
        current = update_file_state(home/name)
        f.require(current == restored.get(name,before),
            'ordinary_update_restore_failed')


def private_parents(root, relative):
    """Create each new private beforeimage directory with its own explicit mode.

    pathlib parents=True uses default permissions for intermediate components;
    no existing historical directory is repaired or relaxed here.
    """
    f = api(); f.directory(root)
    name = Path(relative)
    f.require(not name.is_absolute() and all(p not in ('.','..') for p in name.parts),
        'ordinary_beforeimage_relative_path_required')
    current = root
    for part in name.parent.parts:
        current = current/part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        f.directory(current)
    return current


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def inputs(request, budget):
    f = api()
    f.require(type(request) is dict and set(request) == {'schema','seconds','home','installation_input','previous_input','current_input',
        'marker','source_receipt','configuration','pending_configuration','profile','launcher','tool_search_defer','credential_files'} |
        ({'prior_rolled_back'} if request.get('schema') == 'friday.ordinary-telegram-activation.v2' else set())
        and request['schema'] in ('friday.ordinary-telegram-activation.v1','friday.ordinary-telegram-activation.v2')
        and type(request['seconds']) is int and 30 <= request['seconds'] <= 180, 'ordinary_explicit_request_required')
    home = f.directory(f.canonical(request['home'])); source = home/'hermes-agent'
    paths = {name:budget.call(f.pin, request[name]) for name in request if name not in ('schema','seconds','home','tool_search_defer','credential_files','prior_rolled_back')}
    f.require(paths['marker'] == home/f.MARKER and paths['source_receipt'] == home/'hermes-agent.source.json'
        and paths['configuration'] == home/'config.yaml' and paths['profile'] == home/'FRIDAY-PROFILE.json'
        and paths['launcher'] == source/'.hermes/bin/hermes', 'ordinary_exact_installed_inputs_required')
    credentials=request['credential_files']
    f.require(type(credentials) is dict and set(credentials)=={'.env','auth.json'}, 'ordinary_credential_pins_required')
    for name,ref in credentials.items():
        path=home/name
        if ref is None:
            f.require(not os.path.lexists(path),'ordinary_credential_absence_changed')
        else:
            f.require(f.pin(ref)==path and f.digest(f.owned_file(path,private=True))==ref['sha256'],'ordinary_credential_pin_changed')
    previous = budget.call(f.read_json, paths['previous_input'])
    current = budget.call(f.read_json, paths['current_input'])
    marker = budget.call(f.read_json, paths['marker'])
    f.require(marker.get('completion_stage') == 'CLI_HOST_ONLY' and marker.get('runtime_ready') is False
        and marker.get('gateway_installed') is False and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
        and marker.get('source_receipt_sha256') == request['source_receipt']['sha256']
        and marker.get('input_sha256') == request['installation_input']['sha256']
        and marker.get('postinstall_source_input') == request['previous_input'], 'ordinary_cli_history_required')
    original = budget.call(f.read_json, paths['installation_input'])
    f.require({k:v for k,v in original.items() if k != 'project_files'} ==
        {k:v for k,v in previous.items() if k != 'project_files'}, 'ordinary_original_installation_scope_changed')
    f.require(request['previous_input'] != request['current_input'], 'ordinary_update_new_input_required')
    f.require({k:v for k,v in previous.items() if k != 'project_files'} ==
        {k:v for k,v in current.items() if k != 'project_files'} and current['home'] == str(home),
        'ordinary_deployment_scope_changed')
    f.require(f.cli_historical_scope_closed(marker['original_attempt'],'friday.native-install.v1')
        and (marker.get('cli_segment') is None or f.cli_historical_scope_closed(marker['cli_segment']['clock'],'friday.cli-segment-clock.v1')),
        'ordinary_previous_scope_not_closed')
    f.spec_checked(current, cli_only=True)
    # The current source is an exact ordered prefix; the only new layer is this
    # reviewed manifest. No old layer, consumed intent or historical pin moves.
    receipt = budget.call(f.read_json, paths['source_receipt'])
    donors = {r['id']:r for r in f.read_json(f.pin(current['sources_lock']))['repositories']}
    f.composition_checked(previous, source, receipt, donors['hermes'])
    manifest = f.read_json(f.ROOT/MANIFEST)
    f.require(current['project_files'][MANIFEST] == f.digest(f.owned_file(f.ROOT/MANIFEST))
        and set(current['project_files']) == set(previous['project_files']) | {MANIFEST, manifest['patch'], 'scripts/friday_ordinary_install.py'}
        and all(current['project_files'][name] == pin for name,pin in previous['project_files'].items()
                if name not in ('scripts/friday_install.py','scripts/friday_native.py','scripts/friday_start.py','plugins/friday_rework/onboarding.py')),
        'ordinary_additive_source_required')
    f.require(manifest['base_commit'] == receipt['commit'], 'ordinary_manifest_required')
    f.require(set(manifest['installed_prefix']) == {r['manifest'] for r in receipt['layers']}
        and all(manifest['installed_prefix'][r['manifest']] == r['manifest_sha256'] for r in receipt['layers']),
        'ordinary_exact_prefix_required')
    # Overlay manifests use patch prerequisites for composition. Prefix manifests
    # are pinned separately so old private scopes cannot be silently rewritten.
    for row in manifest['files']:
        p = source/row['path']
        if row['new_file']:
            f.require(not p.exists() and not p.is_symlink(), 'ordinary_new_source_exists')
        else:
            f.require(f.digest(f.owned_file(p)) == row['before_sha256']
                and receipt['files'][row['path']]['sha256'] == row['before_sha256'], 'ordinary_source_changed')
    f.require(f.digest(f.owned_file(f.ROOT/manifest['patch'])) == manifest['patch_sha256'], 'ordinary_patch_changed')
    raw = f.owned_file(paths['pending_configuration'], private=True)
    # Native YAML parser is imported only after the complete old source inventory.
    f.native_packages(source)
    from hermes_cli.friday_dashboard_owner import source_identity
    source_identity(home,source=source)
    f.require(all(f.digest(f.owned_file(home/name,private=True))==pin for name,pin in marker['profile_files'].items()),'ordinary_profile_history_changed')
    from hermes_cli.config_effective import read_user_config_effective_readonly
    cfg = budget.call(read_user_config_effective_readonly, paths['pending_configuration'])
    old_cfg = budget.call(read_user_config_effective_readonly, home/'config.yaml')
    import copy
    changed = copy.deepcopy(old_cfg)
    changed['platforms']['telegram'].setdefault('extra', {})['drop_pending_on_cold_boot'] = False
    changed['platforms']['telegram']['extra']['unauthorized_dm_behavior'] = 'pair'
    changed['gateway']['systemd_watchdog_seconds'] = 30
    deferred = request['tool_search_defer']
    f.require(type(deferred) is list and bool(deferred) and len(deferred) == len(set(deferred))
        and all(isinstance(n,str) and n.isidentifier() for n in deferred)
        and not {'read_file','session_search','clarify'}.intersection(deferred), 'ordinary_progressive_tools_required')
    plans = changed['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']
    f.require(bool(plans), 'ordinary_worker_free_template_required')
    # Keep the full worker template intact. An explicit ordinary template uses
    # the same local model, personality, tools and required scoped credentials.
    ordinary_name = 'friday-ordinary-local'
    f.require('friday-local' in plans and ordinary_name not in plans,
              'ordinary_explicit_template_required')
    template = copy.deepcopy(plans['friday-local'])
    template.pop('worker_inputs', None)
    own = template['config']['plugins']['entries']['friday_rework']['settings']
    f.require(own.get('runtime') == {'enabled':False} and 'worker_requirements' not in own,
              'ordinary_worker_free_template_required')
    template['config'].setdefault('tools',{}).setdefault('tool_search',{})['defer'] = deferred
    plans[ordinary_name] = template
    f.require(cfg == changed, 'ordinary_only_pending_and_progressive_tools_change_required')
    settings = cfg['plugins']['entries']['friday_rework']['settings']
    f.require(settings.get('runtime') == {'enabled':False} and 'worker_requirements' not in settings
        and settings.get('user_isolation') is None and cfg['gateway'].get('profile_routes',[]) == []
        and len(settings['product_access']['accounts']) == 1
        and settings['product_access']['accounts'][0]['platform'] == 'telegram', 'ordinary_worker_free_bootstrap_required')
    if request['schema'] == 'friday.ordinary-telegram-activation.v1':
        f.require(not os.path.lexists(home/TRANSACTION)
            and not os.path.lexists(home/'preparation/ordinary-gateway-archive'), 'ordinary_transaction_already_exists')
    else:
        recovery_checked(request, home, manifest)
    return home, source, paths, previous, current, marker, receipt, manifest, raw, cfg


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def saved_names(manifest):
    return ['FRIDAY-INSTALL.json','hermes-agent.source.json','config.yaml','hermes-agent/install-stamp.json'] + [
        'hermes-agent/'+r['path'] for r in manifest['files'] if not r['new_file']] + ['plugins/friday_rework/onboarding.py']


def no_consumer(home):
    # Same native ownership boundary as explicit source rollback: never stop,
    # uninstall or wake a service to manufacture eligibility for continuation.
    f = api(); f.native_packages(home/'hermes-agent')
    from gateway import host_rendezvous as hr
    from hermes_cli import gateway as gw
    f.require(not gw.get_systemd_unit_path(system=False).exists()
        and not gw.get_systemd_unit_path(system=True).exists()
        and hr.read_record(hr.ROLE_GATEWAY,include_stale=True) is None
        and not gw.find_gateway_pids(), 'ordinary_recovery_no_consumer_required')


def recovery_checked(request, home, manifest):
    """One explicit corrected host candidate after a proven source-only refusal."""
    f=api(); ref=request['prior_rolled_back']; tx=home/TRANSACTION
    f.require(type(ref) is dict and set(ref)=={'request','intent','rollback','archive'},
              'ordinary_recovery_exact_references_required')
    f.directory(tx); before=f.directory(tx/'before')
    f.require({p.name for p in tx.iterdir()} == {'before','intent.json','rolled-back.json'},
              'ordinary_recovery_uncommitted_rollback_required')
    for key,name in [('intent','intent.json'),('rollback','rolled-back.json')]:
        f.require(f.pin(ref[key])==tx/name,'ordinary_recovery_exact_references_required')
    intent=f.read_json(tx/'intent.json'); rollback=f.read_json(tx/'rolled-back.json')
    old=f.read_json(f.pin(ref['request']))
    f.require(intent.get('schema')=='friday.ordinary-telegram-transaction.v1'
        and intent.get('state')=='SOURCE_TRANSACTION_STARTED_NOT_RUNTIME'
        and intent.get('request_sha256')==ref['request']['sha256']
        and rollback=={'state':'ROLLED_BACK_SOURCE_ONLY_NO_RUNTIME_STARTED'},
        'ordinary_recovery_closed_rollback_required')
    f.require(old.get('schema')=='friday.ordinary-telegram-activation.v1'
        and {k:v for k,v in request.items() if k not in ('schema','current_input','prior_rolled_back')} ==
            {k:v for k,v in old.items() if k not in ('schema','current_input')},
        'ordinary_recovery_scope_changed')
    old_input=f.read_json(f.pin(old['current_input']))
    new_input=f.read_json(f.pin(request['current_input']))
    f.require({k:v for k,v in old_input.items() if k!='project_files'} ==
              {k:v for k,v in new_input.items() if k!='project_files'},'ordinary_recovery_scope_changed')
    a=old_input['project_files']; b=new_input['project_files']
    changed={name for name in set(a)|set(b) if a.get(name)!=b.get(name)}
    f.require(changed=={'scripts/friday_ordinary_install.py'} and set(a)==set(b)
        and b['scripts/friday_ordinary_install.py']==f.digest(f.owned_file(f.ROOT/'scripts/friday_ordinary_install.py')),
        'ordinary_recovery_corrected_host_candidate_required')
    f.require(set(intent.get('before',{}))==set(saved_names(manifest))
        and intent.get('new_files')==[r['path'] for r in manifest['files'] if r['new_file']],
        'ordinary_recovery_beforeimage_scope_changed')
    # Validate the complete retained tree, including absence of untracked files.
    expected=set(intent['before'])
    actual=set()
    for path in before.rglob('*'):
        if path.is_dir(): f.directory(path)
        else:
            f.owned_file(path,private=True); actual.add(str(path.relative_to(before)))
    f.require(actual==expected,'ordinary_recovery_beforeimage_scope_changed')
    for name,row in intent['before'].items():
        f.require(type(row) is dict and set(row)=={'sha256','mode'}
            and type(row['mode']) is int and row['mode'] in (0o600,0o644,0o700,0o755),
            'ordinary_recovery_beforeimage_mode_changed')
        f.require(f.digest(f.owned_file(before/name,private=True))==row['sha256']
            and f.digest(f.owned_file(home/name))==row['sha256']
            and stat.S_IMODE((home/name).stat().st_mode)==row['mode'],
            'ordinary_recovery_beforeimage_changed')
    for name in intent['new_files']:
        f.require(not os.path.lexists(home/'hermes-agent'/name),'ordinary_recovery_new_source_present')
    archive=home/'preparation/ordinary-gateway-archive'/ref['request']['sha256']
    f.require(ref['archive']==str(archive) and not os.path.lexists(archive)
        and not os.path.lexists(archive.with_name(archive.name+'.json')),
              'ordinary_recovery_archive_required')
    if os.path.lexists(archive.parent): f.directory(archive.parent)
    no_consumer(home)
    return archive


def archive_rollback(request, home, manifest):
    f=api(); archive=recovery_checked(request,home,manifest); tx=home/TRANSACTION
    if not archive.parent.exists():
        archive.parent.mkdir(mode=0o700); sync_directory(archive.parent.parent)
    # The retained transaction is never edited or deleted. The sibling receipt
    # and directory rename are durable before the new standard-path journal.
    receipt=archive.with_name(archive.name+'.json')
    f.require(not os.path.lexists(receipt),'ordinary_recovery_archive_required')
    os.rename(tx,archive); sync_directory(archive.parent); sync_directory(tx.parent)
    write(receipt,encoded({'schema':'friday.ordinary-telegram-rollback-archive.v1',
        'state':'ROLLED_BACK_TRANSACTION_RETAINED_NOT_REPLAYED',
        'prior_rolled_back':request['prior_rolled_back'],'archive':str(archive)}))
    sync_directory(archive.parent)


def activate(request, request_path, budget):
    """Journal beforeimages, apply exact layer, publish native marker last.

    Exclusive file lock plus exact rechecks protect this transaction. Before any
    consumer starts, exceptions restore its own bytes; the journal is retained
    and never blindly retried. Ambiguous external service effects are outside
    this source-only action and are handled by the native service handoff.
    """
    f = api()
    home = f.directory(f.canonical(request['home']))
    fd = os.open(home, os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        prepared = inputs(request, budget)
        home, source, paths, previous, current, marker, receipt, manifest, config_raw, cfg = prepared
        f.require(f.read_json(request_path) == request, 'ordinary_request_changed')
        # Read and validate every saved owner/mode before creating any journal.
        names = saved_names(manifest)
        saved = {}; history = {}; beforeimages = {}
        for name in names:
            path=home/name
            data=f.owned_file(path,private=name != 'hermes-agent/install-stamp.json' and not name.startswith('hermes-agent/hermes_cli/'))
            mode=stat.S_IMODE(path.stat().st_mode)
            f.require(mode in (0o600,0o644,0o700,0o755),'ordinary_beforeimage_mode_required')
            beforeimages[name]=data; saved[name]={'sha256':f.digest(data),'mode':mode}
        if request.get('schema') == 'friday.ordinary-telegram-activation.v2':
            archive_rollback(request,home,manifest)
        transaction = home/TRANSACTION
        transaction.mkdir(mode=0o700)
        before = transaction/'before'; before.mkdir(mode=0o700)
        for name in names:
            data = beforeimages[name]
            target = before/name; private_parents(before,name)
            write(target,data)
            if name == 'FRIDAY-INSTALL.json': history[str(target.relative_to(home))] = f.digest(data)
        for path in home.glob('FRIDAY-INSTALL.*'):
            if path.name != f.MARKER and path.is_file(): history[path.name] = f.digest(f.owned_file(path,private=True))
        write(transaction/'intent.json',encoded({'schema':'friday.ordinary-telegram-transaction.v1',
            'state':'SOURCE_TRANSACTION_STARTED_NOT_RUNTIME','request_sha256':f.digest(f.owned_file(request_path,private=True)),
            'before':saved,'new_files':[r['path'] for r in manifest['files'] if r['new_file']]}))
        touched = []
        try:
            for name,ref in request['credential_files'].items():
                f.require((not os.path.lexists(home/name)) if ref is None else f.digest(f.owned_file(home/name,private=True))==ref['sha256'],'ordinary_credential_pin_changed')
            from scripts.dsh_prepare import run
            apply_env = f.clean_environment(home)
            apply_env['GIT_CEILING_DIRECTORIES'] = str(source.parent)
            for checking in (True,False):
                command = ['git','--no-optional-locks','apply','--whitespace=nowarn']
                if checking: command.append('--check')
                command.append(str(f.ROOT/manifest['patch']))
                run(command, source, timeout=min(20,budget.check(reserve=1)),env=apply_env,deadline=budget.deadline)
            for row in manifest['files']:
                p = source/row['path']; data = f.owned_file(p)
                f.require(f.digest(data) == row['sha256'] and len(data) == row['bytes'], 'ordinary_patch_output_changed')
                receipt['files'][row['path']] = {k:row[k] for k in ('sha256','bytes','mode')}
            receipt['layers'].append({'manifest':MANIFEST,'manifest_sha256':current['project_files'][MANIFEST],
                'patch_sha256':manifest['patch_sha256']})
            f.composition_checked(current,source,receipt, {r['id']:r for r in f.read_json(f.pin(current['sources_lock']))['repositories']}['hermes'])
            plugin_name = 'plugins/friday_rework/onboarding.py'
            f.require(f.digest(f.owned_file(home/plugin_name,private=True)) == previous['project_files'][plugin_name], 'ordinary_installed_plugin_changed')
            replace(home/plugin_name,f.owned_file(f.ROOT/plugin_name),saved[plugin_name]['mode']); touched.append(plugin_name)
            stamp = f.read_json(source/'install-stamp.json')
            stamp['fridaySource'] = {'baseTree':receipt['base_tree'],'layers':receipt['layers']}
            for name, data in [('hermes-agent.source.json',encoded(receipt)), ('hermes-agent/install-stamp.json',encoded(stamp)), ('config.yaml',config_raw)]:
                budget.check(); replace(home/name,data); touched.append(name)
            # Reload the changed installed modules in a fresh interpreter at
            # normal launch. This installer uses pure binding helpers only.
            import importlib.util
            spec = importlib.util.spec_from_file_location('_friday_ordinary_binding',source/'hermes_cli/friday_ordinary_gateway.py')
            ordinary = importlib.util.module_from_spec(spec); spec.loader.exec_module(ordinary)
            settings = cfg['plugins']['entries']['friday_rework']['settings']
            binding = {'schema':ordinary.SCHEMA,'scope':'TELEGRAM_RECEIVER_AND_AUTHENTICATED_ONBOARDING_ONLY',
                'configuration_sha256':ordinary.normalized_configuration(cfg),
                'credential_files':{n:(ordinary.credential_identity(home)[0] if n == '.env' else f.digest(f.owned_file(home/n,private=True)) if os.path.lexists(home/n) else None) for n in ('.env','auth.json')},
                'profile_sha256':f.digest(f.owned_file(home/'FRIDAY-PROFILE.json',private=True)),
                'source_receipt_sha256':f.digest(encoded(receipt)),
                'baseline':{'runtime_profiles':settings['product_access']['accounts'][0]['runtime_profiles'],
                            'admin_profiles':settings['admin']['profiles'],'telegram_allowed_users':ordinary.credential_identity(home)[1]}, 'history':history,
                'operator_entry':{'script':{'path':str(f.ROOT/'scripts/friday_native.py'),'sha256':current['project_files']['scripts/friday_native.py']},
                    'input':request['current_input']}}
            updated = dict(marker,completion_stage=ordinary.STAGE,input_sha256=request['current_input']['sha256'],
                source_receipt_sha256=binding['source_receipt_sha256'],ordinary_gateway=binding)
            updated['profile_files'] = dict(marker['profile_files'],**{'config.yaml':f.digest(config_raw)})
            updated['plugin_files'] = dict(marker['plugin_files'],**{plugin_name:current['project_files'][plugin_name]})
            budget.check(); replace(home/f.MARKER,encoded(updated)); touched.append(f.MARKER)
            write(transaction/'committed.json', encoded({'state':'SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED','workers_enabled':False,
                'source_receipt_sha256':binding['source_receipt_sha256'],'gateway_started':False}))
            return {'state':'TELEGRAM_ORDINARY_SOURCE_ACTIVATED','ready':False,'workers_enabled':False,'gateway_started':False,
                'ordinary_onboarding':'AUTHENTICATED_NATIVE_API_AND_PAIRING_REQUIRED','full_release_accepted':False}
        except BaseException as original:
            # No service or message effect belongs to this transaction. Restore
            # exact owned beforeimages and only the newly introduced source files.
            try:
                for row in manifest['files']:
                    path = source/row['path']
                    if row['new_file'] and path.exists():
                        f.require(f.digest(f.owned_file(path))==row['sha256'],'ordinary_new_source_ownership_changed')
                        path.unlink()
                for name,row in saved.items():
                    replace(home/name,f.owned_file(before/name,private=True),row['mode'])
                write(transaction/'rolled-back.json',encoded({'state':'ROLLED_BACK_SOURCE_ONLY_NO_RUNTIME_STARTED'}))
            except BaseException as restoration:
                from scripts.dsh_prepare import StopUnconfirmed
                f.remember_secondary(original,restoration)
                raise StopUnconfirmed('ordinary source restoration requires reconciliation') from original
            raise
    finally:
        os.close(fd)


def checked_update_keyless_history(home, reference, predecessor, history):
    """Read the consumed recovery as ancestry; never replay or revalidate setup."""
    import re
    f = api(); recovery = f.read_json(f.pin(reference))
    recovery_id = recovery.get('recovery_id')
    f.require(predecessor.get('schema') == PROJECT_RUNTIME_SCHEMA
        and recovery.get('schema') == 'friday.ordinary-worker-keyless-recovery.v1'
        and isinstance(recovery_id,str) and re.fullmatch('[A-Za-z0-9_-]{1,64}',recovery_id)
        and recovery.get('home') == str(home)
        and recovery.get('installed_input') == predecessor['current_input']
        and recovery.get('transition') == 'NEW_PRODUCT_MAINTENANCE_NO_RUNTIME_AUTHORITY',
        'ordinary_update_exact_keyless_predecessor_required')
    old = f.read_json(f.pin(recovery['installed_input']))
    new = f.read_json(f.pin(recovery['recovery_input']))
    allowed = {'scripts/friday_install.py','scripts/friday_worker_preparation.py'}
    before = old['project_files']; after = new['project_files']
    f.require(len(before) == 227 and set(before) == set(after) and allowed <= set(before)
        and {k:v for k,v in old.items() if k != 'project_files'} ==
            {k:v for k,v in new.items() if k != 'project_files'}
        and all(after[k] == h for k,h in before.items() if k not in allowed)
        and all(after[k] != before[k] for k in allowed),
        'ordinary_update_keyless_input_changed')
    refs = recovery.get('history')
    f.require(type(refs) is list and len(refs) == len(history)
        and all(type(row) is dict and set(row) == {'path','sha256'} for row in refs)
        and {str(home/n):h for n,h in history.items()} == {r['path']:r['sha256'] for r in refs},
        'ordinary_update_keyless_history_changed')
    name = 'preparation/ordinary-keyless-recovery-'+recovery_id
    tx = f.directory(home/name)
    intent = f.read_json(tx/'intent.json'); committed = f.read_json(tx/'committed.json')
    mapping = {str(home/'profiles'/recovery['profile']/'workers/qualification'):str(tx/'failed-qualification')}
    f.require(intent.get('schema') == recovery['schema'] and intent.get('state') == 'CONSUMED_NO_RETRY'
        and intent.get('request_sha256') == reference['sha256']
        and committed.get('request_sha256') == reference['sha256']
        and intent.get('recovery_id') == committed.get('recovery_id') == recovery_id
        and committed.get('state') == 'REPAIRED_CONSUMERS_STOPPED_WORKERS_OFF_NEW_RUNTIME_NOT_AUTHORIZED'
        and intent.get('failure') == recovery['failure']
        and intent.get('archive_mapping') == committed.get('archive_mapping') == mapping
        and intent.get('original_attempt') == committed.get('original_attempt')
        and intent.get('runtime_authority') == committed.get('runtime_acceptance') == committed.get('new_runtime_authority') == 'NOT_GRANTED'
        and all(row.get(k) is False for row in (intent,committed)
            for k in ('consumers_started','workers_enabled','resume_allowed'))
        and committed.get('ready') is False and committed.get('old_attempt_retry_authorized') is False
        and not os.path.lexists(tx/'rolled-back.json'),
        'ordinary_update_committed_keyless_predecessor_required')
    previous_tx = home/'preparation'/('ordinary-source-update-'+predecessor['previous_input']['sha256'])
    f.require(f.read_json(previous_tx/'intent.json').get('project_only') is True
        and f.read_json(previous_tx/'committed.json').get('project_only') is True
        and f.read_json(previous_tx/'committed.json').get('source_receipt_sha256') == recovery['source_receipt']['sha256']
        and f.digest(f.owned_file(tx/'before'/f.MARKER,private=True)) == recovery['root_marker']['sha256'],
        'ordinary_update_keyless_source_binding_changed')
    failed = recovery['qualification_files']
    f.require(set(failed) == {'failure.json','dsh-safety/inputs/bootstrap.py','dsh-safety/inputs/web-ca.pem','dsh-safety/inputs/web-network.mjs'}
        and all(f.digest(f.owned_file(tx/folder/n,private=True)) == h
            for folder in ('failed-before','failed-qualification') for n,h in failed.items()),
        'ordinary_update_keyless_archive_changed')
    return name


def checked_source81_budget_history(home, reference, predecessor):
    """Exact closed Source80 budget-only journal; no operation is dispatched."""
    f=api()
    f.require(type(reference) is dict and reference.get('sha256') == SOURCE81_BUDGET_REQUEST,
        'ordinary_update_exact_budget_history_required')
    request=f.read_json(f.pin(reference))
    f.require(request.get('schema') == REBIND_BUDGET_SCHEMA and request.get('home') == str(home)
        and request.get('profile') == 'dest_telegram' and request.get('seconds') == 180
        and request['previous_input'] == predecessor['current_input']
        and request['current_input']['sha256'] == FILE_TOOL_CONTRACT_PREVIOUS_INPUT,
        'ordinary_update_closed_budget_binding_required')
    f.pin(request['previous_input']);f.pin(request['current_input'])
    tx=f.directory(home/'preparation'/('ordinary-inference-rebind-'+request['previous_input']['sha256']))
    intent=f.read_json(tx/'intent.json');committed=f.read_json(tx/'committed.json')
    names={f.MARKER,'config.yaml','profiles/dest_telegram/config.yaml',
        'profiles/dest_telegram/.friday-onboarding.json','profiles/dest_telegram/.friday-user-scope.json'}
    f.require(intent.get('schema') == REBIND_BUDGET_SCHEMA and intent.get('state') == 'CONSUMED_NO_RETRY'
        and intent.get('request_sha256') == reference['sha256'] and intent.get('seconds') == 180
        and intent.get('previous_input') == request['previous_input']
        and intent.get('current_input') == request['current_input']
        and committed.get('state') == 'EXACT_REQUEST_BUDGET_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED'
        and committed.get('ready') is False
        and all(body.get(field) is False for body in (intent,committed)
            for field in ('consumers_started','workers_enabled','database_changed'))
        and set(request['before']) == set(intent['before']) == set(committed['after']) == names
        and all(intent['before'][n] == {'sha256':request['before'][n]['sha256'],'mode':0o600}
            and request['before'][n]['path'] == str(home/n) for n in names),
        'ordinary_update_closed_budget_semantics_required')
    exact={'intent.json':SOURCE81_BUDGET_INTENT,'committed.json':SOURCE81_BUDGET_COMMITTED,
        **{'before/'+n:intent['before'][n]['sha256'] for n in names},
        **{'stage/'+n:committed['after'][n] for n in names},
        'stage/FRIDAY-PROFILE.json':request['retained']['FRIDAY-PROFILE.json']['sha256'],
        'stage/config.yaml.lock':f.digest(b''),'stage/profiles/dest_telegram/config.yaml.lock':f.digest(b'')}
    actual={}
    for path in tx.rglob('*'):
        f.require(not path.is_symlink(),'ordinary_update_history_link_refused')
        if path.is_dir(): f.directory(path)
        else: actual[str(path.relative_to(tx))]=f.digest(f.owned_file(path,private=True))
    f.require(actual == exact,'ordinary_update_budget_history_changed')
    return {str(tx.relative_to(home))+'/'+n:h for n,h in actual.items()}


def checked_source82_retained(home, request):
    """Retain the current admin-edited profile, never restore closed budget bytes."""
    f=api();refs=request['retained_profile_files']
    f.require(type(refs) is dict and set(refs) == WEB_INPUT_PROFILE_FILES
        and refs['profiles/dest_telegram/config.yaml']['sha256'] == WEB_INPUT_SELECTED_CONFIG,
        'ordinary_update_current_profile_pins_required')
    for name,ref in refs.items():
        f.require(f.pin(ref) == home/name,'ordinary_update_current_profile_changed')
    for name in ('previous_input','current_input','configuration','profile','launcher','native_unit'):
        f.pin(request[name])
    for name,ref in request['credential_files'].items():
        f.require(not os.path.lexists(home/name) if ref is None else f.pin(ref) == home/name,
            'ordinary_update_credential_pin_changed')


def checked_source81_retained(home, request, *, after=False):
    """Preserve all closed budget retained refs except this reviewed source delta."""
    f=api();budget_request=f.read_json(f.pin(request['inference_rebind']))
    retained=budget_request['retained']
    f.require(type(retained) is dict and len(retained) == SOURCE81_RETAINED_FILES,
        'ordinary_update_budget_retained_set_changed')
    allowed={'hermes-agent/'+n for n in FILE_TOOL_CONTRACT_FILES} | FILE_TOOL_CONTRACT_PLUGIN_FILES | {
        'hermes-agent.source.json','hermes-agent/install-stamp.json'}
    for name,ref in retained.items():
        f.require(ref['path'] == str(home/name),'ordinary_update_retained_path_changed')
        if not (after and name in allowed): f.pin(ref)
    tx=home/'preparation'/('ordinary-inference-rebind-'+budget_request['previous_input']['sha256'])
    for name,sha in f.read_json(tx/'committed.json')['after'].items():
        if not (after and name == f.MARKER): f.pin({'path':str(home/name),'sha256':sha})
    for name in ('previous_input','current_input','configuration','profile','launcher','native_unit'):
        f.pin(request[name])
    for name,ref in request['credential_files'].items():
        f.require(not os.path.lexists(home/name) if ref is None else f.pin(ref) == home/name,
            'ordinary_update_credential_pin_changed')


def checked_update_inference_history(home, reference, predecessor):
    """Retain one already committed helper/rebind edge; never replay either."""
    f = api()
    if predecessor.get('schema') == 'friday.ordinary-telegram-source-update.v34':
        return checked_source81_budget_history(home,reference,predecessor)
    f.require(type(reference) is dict and reference.get('sha256') == SOURCE80_REBIND_REQUEST
        and predecessor.get('schema') == PROJECT_INFERENCE_HELPER_SCHEMA,
        'ordinary_update_exact_inference_history_required')
    request = f.read_json(f.pin(reference))
    f.require(request.get('schema') == REBIND_SCHEMA and request.get('home') == str(home)
        and request.get('profile') == 'dest_telegram'
        and request.get('seconds') == 180
        and request['previous_input'] == predecessor['current_input']
        and request['current_input']['sha256'] == SPARK_REQUEST_BUDGET_PREVIOUS_INPUT,
        'ordinary_update_committed_inference_binding_required')
    f.pin(request['previous_input']); f.pin(request['current_input'])
    tx = f.directory(home/'preparation'/('ordinary-inference-rebind-'+request['previous_input']['sha256']))
    intent = f.read_json(tx/'intent.json'); committed = f.read_json(tx/'committed.json')
    names = {'.env','config.yaml',f.MARKER,'FRIDAY-PROFILE.json',
        'profiles/dest_telegram/.env','profiles/dest_telegram/config.yaml',
        'profiles/dest_telegram/.friday-onboarding.json','profiles/dest_telegram/.friday-user-scope.json'}
    f.require(intent.get('schema') == REBIND_SCHEMA and intent.get('state') == 'CONSUMED_NO_RETRY'
        and intent.get('request_sha256') == reference['sha256'] and intent.get('seconds') == 180
        and intent.get('previous_input') == request['previous_input']
        and intent.get('current_input') == request['current_input']
        and committed.get('state') == 'EXACT_INFERENCE_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED'
        and committed.get('ready') is False
        and all(body.get(field) is False for body in (intent,committed)
            for field in ('consumers_started','workers_enabled','database_changed'))
        and set(request['before']) == set(intent['before']) == set(committed['after']) == names
        and all(intent['before'][n] == {'sha256':request['before'][n]['sha256'],'mode':0o600}
            and request['before'][n]['path'] == str(home/n) for n in names),
        'ordinary_update_committed_inference_semantics_required')
    required = {'intent.json':SOURCE80_REBIND_INTENT,
        'committed.json':SOURCE80_REBIND_COMMITTED,
        **{'before/'+n:intent['before'][n]['sha256'] for n in names},
        **{'stage/'+n:committed['after'][n] for n in names},
        'stage/config.yaml.lock':f.digest(b''),
        'stage/profiles/dest_telegram/config.yaml.lock':f.digest(b'')}
    reconciliation = f.directory(home/PROJECT_INFERENCE_RECONCILIATION)
    for name,sha in PROJECT_INFERENCE_RECONCILIATION_PINS.items():
        f.pin({'path':str(home/name),'sha256':sha})
    archived = f.read_json(reconciliation/'intent.json')['tree']['files']
    exact = dict(PROJECT_INFERENCE_RECONCILIATION_PINS)
    for folder in ('failed-before','failed-qualification'):
        for name,row in archived.items():
            path = reconciliation/folder/name
            state = update_file_state(path)
            f.require(state is not None and f.digest(state['data']) == row['sha256']
                and len(state['data']) == row['bytes']
                and state['mode'] == (row['mode'] if folder == 'failed-qualification' else row['mode'] & 0o700)
                and (folder != 'failed-qualification' or list(state['identity']) == row['identity']),
                'ordinary_update_closed_archive_changed')
            exact[str(path.relative_to(home))] = row['sha256']
    exact.update({str(tx.relative_to(home))+'/'+n:h for n,h in required.items()})
    actual = {}
    for root in (reconciliation,tx):
        for path in root.rglob('*'):
            f.require(not path.is_symlink(), 'ordinary_update_history_link_refused')
            if path.is_dir(): f.directory(path)
            else:
                private = not path.is_relative_to(reconciliation/'failed-qualification')
                actual[str(path.relative_to(home))] = f.digest(f.owned_file(path,private=private))
    f.require(actual == exact, 'ordinary_update_inference_history_changed')
    return actual


def update_history(home, expected, predecessor=None, keyless_recovery=None, inference_rebind=None):
    """Pin the complete original activation transaction and rollback archive."""
    f = api(); actual = {}
    roots = [TRANSACTION, 'preparation/ordinary-gateway-archive']
    if predecessor is not None:
        # This is the already committed 46->47 transaction, never an operation
        # to rerun. Its exact request and all beforeimages remain pinned.
        old = f.read_json(f.pin(predecessor))
        if old.get('schema') in ('friday.ordinary-telegram-project-update.v1','friday.ordinary-telegram-project-update.v2','friday.ordinary-telegram-project-update.v3','friday.ordinary-telegram-source-update.v2','friday.ordinary-telegram-source-update.v3','friday.ordinary-telegram-source-update.v4','friday.ordinary-telegram-source-update.v5','friday.ordinary-telegram-source-update.v6','friday.ordinary-telegram-source-update.v7','friday.ordinary-telegram-source-update.v8','friday.ordinary-telegram-source-update.v9','friday.ordinary-telegram-source-update.v10','friday.ordinary-telegram-source-update.v11','friday.ordinary-telegram-source-update.v12','friday.ordinary-telegram-source-update.v13','friday.ordinary-telegram-source-update.v14','friday.ordinary-telegram-source-update.v15','friday.ordinary-telegram-source-update.v16','friday.ordinary-telegram-source-update.v17','friday.ordinary-telegram-source-update.v18','friday.ordinary-telegram-source-update.v19','friday.ordinary-telegram-source-update.v20','friday.ordinary-telegram-source-update.v21','friday.ordinary-telegram-source-update.v22','friday.ordinary-telegram-source-update.v23','friday.ordinary-telegram-source-update.v24','friday.ordinary-telegram-source-update.v25','friday.ordinary-telegram-source-update.v26','friday.ordinary-telegram-source-update.v27','friday.ordinary-telegram-source-update.v28','friday.ordinary-telegram-source-update.v29','friday.ordinary-telegram-source-update.v30','friday.ordinary-telegram-source-update.v31','friday.ordinary-telegram-source-update.v32','friday.ordinary-telegram-source-update.v33','friday.ordinary-telegram-source-update.v34','friday.ordinary-telegram-source-update.v35','friday.ordinary-telegram-source-update.v36','friday.ordinary-telegram-source-update.v37','friday.ordinary-telegram-source-update.v38','friday.ordinary-telegram-source-update.v39','friday.ordinary-telegram-project-update.v4'):
            # Every exact historical committed update journal survives this transition.
            actual = update_history(home, old['transaction_history'], old['predecessor_update'], old.get('keyless_recovery'), old.get('inference_rebind'))
            roots = []
        f.require(old.get('schema') in ('friday.ordinary-telegram-project-update.v1','friday.ordinary-telegram-project-update.v2','friday.ordinary-telegram-project-update.v3','friday.ordinary-telegram-source-update.v1',
            'friday.ordinary-telegram-source-update.v2','friday.ordinary-telegram-source-update.v3','friday.ordinary-telegram-source-update.v4','friday.ordinary-telegram-source-update.v5','friday.ordinary-telegram-source-update.v6','friday.ordinary-telegram-source-update.v7','friday.ordinary-telegram-source-update.v8','friday.ordinary-telegram-source-update.v9','friday.ordinary-telegram-source-update.v10','friday.ordinary-telegram-source-update.v11','friday.ordinary-telegram-source-update.v12','friday.ordinary-telegram-source-update.v13','friday.ordinary-telegram-source-update.v14','friday.ordinary-telegram-source-update.v15','friday.ordinary-telegram-source-update.v16','friday.ordinary-telegram-source-update.v17','friday.ordinary-telegram-source-update.v18','friday.ordinary-telegram-source-update.v19','friday.ordinary-telegram-source-update.v20','friday.ordinary-telegram-source-update.v21','friday.ordinary-telegram-source-update.v22','friday.ordinary-telegram-source-update.v23','friday.ordinary-telegram-source-update.v24','friday.ordinary-telegram-source-update.v25','friday.ordinary-telegram-source-update.v26','friday.ordinary-telegram-source-update.v27','friday.ordinary-telegram-source-update.v28','friday.ordinary-telegram-source-update.v29','friday.ordinary-telegram-source-update.v30','friday.ordinary-telegram-source-update.v31','friday.ordinary-telegram-source-update.v32','friday.ordinary-telegram-source-update.v33','friday.ordinary-telegram-source-update.v34','friday.ordinary-telegram-source-update.v35','friday.ordinary-telegram-source-update.v36','friday.ordinary-telegram-source-update.v37','friday.ordinary-telegram-source-update.v38','friday.ordinary-telegram-source-update.v39','friday.ordinary-telegram-project-update.v4'),
            'ordinary_update_exact_predecessor_required')
        f.pin(old['previous_input']); f.pin(old['current_input'])
        name = 'preparation/ordinary-source-update-'+old['previous_input']['sha256']
        tx = f.directory(home/name)
        intent = f.read_json(tx/'intent.json'); committed = f.read_json(tx/'committed.json')
        f.require(intent.get('schema') == 'friday.ordinary-telegram-source-update-transaction.v1'
            and intent.get('state') == 'SOURCE_UPDATE_CONSUMED_NO_RETRY'
            and intent.get('request_sha256') == predecessor['sha256']
            and committed.get('state') == 'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED'
            and committed.get('previous_input') == old['previous_input']
            and committed.get('current_input') == old['current_input']
            and committed.get('gateway_started') is False and committed.get('workers_enabled') is False
            and not os.path.lexists(tx/'rolled-back.json'), 'ordinary_update_committed_predecessor_required')
        roots.append(name)
    for name in roots:
        root = f.directory(home/name)
        for path in root.rglob('*'):
            f.require(not path.is_symlink(), 'ordinary_update_history_link_refused')
            if path.is_dir():
                f.directory(path)
            else:
                actual[str(path.relative_to(home))] = f.digest(f.owned_file(path,private=True))
    if keyless_recovery is not None:
        name = checked_update_keyless_history(home, keyless_recovery, old, actual)
        for path in f.directory(home/name).rglob('*'):
            f.require(not path.is_symlink(), 'ordinary_update_history_link_refused')
            if path.is_dir(): f.directory(path)
            else: actual[str(path.relative_to(home))] = f.digest(f.owned_file(path,private=True))
    if inference_rebind is not None:
        actual.update(checked_update_inference_history(home,inference_rebind,old))
    f.require(type(expected) is dict and actual == expected
        and TRANSACTION+'/committed.json' in actual, 'ordinary_update_transaction_history_changed')
    f.require(f.read_json(home/TRANSACTION/'committed.json').get('state') ==
        'SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED', 'ordinary_update_committed_history_required')
    return actual


def checked_plugin_inventory(home, expected):
    """The installed private package, including all unchanged source files."""
    f = api(); actual = set(); root = f.directory(home/'plugins/friday_rework')
    for path in root.rglob('*'):
        f.require(not path.is_symlink(), 'ordinary_update_plugin_link_refused')
        if path.is_dir():
            f.directory(path)
        else:
            name = str(path.relative_to(home)); actual.add(name)
            f.require(name in expected and f.digest(f.owned_file(path,private=True)) == expected[name],
                'ordinary_update_installed_plugin_changed')
    f.require(actual == set(expected), 'ordinary_update_plugin_inventory_changed')


def check_browser_gateway(home, source, manifest, budget, *, staged):
    """Use only the pinned v10 afterimage for the complete ordinary check.

    Existing installed bytes are verified separately against the old receipt.
    This repairs the old checker predicate without weakening any binding check.
    """
    import tempfile
    import types
    f = api(); row, = manifest['files']; relative = row['path']
    f.require(relative == 'hermes_cli/friday_ordinary_gateway.py'
        and row.get('new_file') is False, 'ordinary_update_exact_browser_gateway_required')
    if staged:
        from scripts.dsh_prepare import run
        # No installed path changes before the consumed transaction journal.
        with tempfile.TemporaryDirectory(prefix='.ordinary-browser-gateway-',dir=home/'preparation') as name:
            root = Path(name); private_parents(root,relative)
            before = f.owned_file(source/relative)
            f.require(f.digest(before) == row['before_sha256'], 'ordinary_update_source_changed')
            write(root/relative,before,0o644)
            env = f.clean_environment(home); env['GIT_CEILING_DIRECTORIES'] = str(home)
            for checking in (True,False):
                command = ['git','--no-optional-locks','apply','--whitespace=nowarn']
                if checking: command.append('--check')
                command.append(str(f.ROOT/manifest['patch']))
                run(command,root,timeout=min(20,budget.check(reserve=1)),env=env,deadline=budget.deadline)
            data = f.owned_file(root/relative)
    else:
        data = f.owned_file(source/relative)
    f.require(f.digest(data) == row['sha256'] and len(data) == row['bytes'],
        'ordinary_update_browser_gateway_afterimage_changed')
    module = types.ModuleType('_friday_reviewed_browser_gateway')
    module.__file__ = str(source/relative)
    exec(compile(data,module.__file__,'exec'),module.__dict__)
    return module.check(home,role=False)


def checked_worker_declaration_publication(home, request, predecessor, marker):
    """Bridge v10 only through the exact already-consumed worker publication.

    Source updates do not rerun preparation or admit a generic input mismatch.
    The successful pinned journal binds the unchanged Native56 source, original
    request clock, both input generations and the installed marker beforeimage.
    """
    import copy
    import re
    f = api(); proof = request['worker_declaration_publication']
    f.require(type(proof) is dict and set(proof) == {'request','result'},
        'ordinary_update_worker_publication_pins_required')
    prepared = f.read_json(f.pin(proof['request']))
    result_path = f.pin(proof['result']); result = f.read_json(result_path)
    request_id = prepared.get('request_id')
    f.require(prepared.get('schema') == 'friday.ordinary-worker-preparation.v1'
        and isinstance(request_id,str) and re.fullmatch('[A-Za-z0-9_-]{1,64}',request_id)
        and prepared.get('home') == str(home)
        and prepared.get('current_input') == predecessor['current_input']
        and prepared.get('preparation_input') == request['previous_input']
        and prepared.get('source_receipt') == request['source_receipt']
        and prepared.get('profile') == request['profile']
        and prepared.get('native_unit') == request['native_unit'],
        'ordinary_update_worker_publication_binding_changed')
    tx = f.directory(home/'preparation'/('ordinary-workers-'+request_id))
    f.require(result_path == tx/'result.json' and not os.path.lexists(tx/'failure.json'),
        'ordinary_update_successful_worker_publication_required')
    intent = f.read_json(tx/'intent.json')
    f.require(result.get('state') == 'BOTH_WORKER_DECLARATIONS_PUBLISHED_QUALIFICATION_PENDING'
        and result.get('ready') is False and result.get('runtime_enabled') is False
        and result.get('runtime_acceptance') == 'NOT_GRANTED'
        and result.get('original_attempt') == intent
        and intent.get('request_id') == request_id
        and intent.get('request_sha256') == proof['request']['sha256']
        and intent.get('seconds') == prepared.get('seconds')
        and intent.get('resume_allowed') is False
        and type(intent.get('started_mono')) in (int,float)
        and type(intent.get('deadline_mono')) in (int,float)
        and abs(intent['deadline_mono']-intent['started_mono']-intent['seconds']) < 0.001
        and result.get('reports') == prepared.get('reports')
        and type(result.get('reports')) is dict
        and set(result['reports']) == {'source','toolchain','build','smoke','inventory','a0'},
        'ordinary_update_consumed_worker_publication_required')
    for ref in [*result['reports'].values(),*prepared['history']]: f.pin(ref)
    before_path = tx/('before-'+f.MARKER)
    before = f.read_json(before_path)
    f.require(f.digest(f.owned_file(before_path,private=True)) == prepared['marker']['sha256']
        and prepared['marker']['path'] == str(home/f.MARKER)
        and prepared['configuration']['path'] == str(home/'config.yaml')
        and f.digest(f.owned_file(tx/'before-config.yaml',private=True)) == prepared['configuration']['sha256']
        and before.get('input_sha256') == predecessor['current_input']['sha256']
        and before.get('source_receipt_sha256') == request['source_receipt']['sha256']
        and before.get('ordinary_gateway',{}).get('operator_entry',{}).get('input') == predecessor['current_input']
        and marker['ordinary_gateway']['operator_entry']['input'] == request['previous_input']
        and marker['profile_files']['config.yaml'] == result.get('configuration_sha256'),
        'ordinary_update_worker_beforeimage_changed')
    old = f.read_json(f.pin(prepared['current_input']))
    new = f.read_json(f.pin(prepared['preparation_input']))
    # The previous preparer admitted only its coherent installer package and
    # refreshed egress evidence. No operational setting is widened here.
    allowed = {'scripts/friday_install.py','scripts/friday_ordinary_install.py',
        'scripts/worker_install.py','scripts/friday_worker_preparation.py',
        'scripts/a0_prepare.py','scripts/friday_ordinary_a0_registration.py'}
    prior = old['project_files']; fresh = new['project_files']
    f.require(len(prior) == 178 and len(fresh) == 180
        and set(fresh) == set(prior) | {'scripts/friday_worker_preparation.py','scripts/friday_ordinary_a0_registration.py'}
        and all(fresh[name] == pin for name,pin in prior.items() if name not in allowed),
        'ordinary_update_worker_source_changed')
    left = copy.deepcopy(old); right = copy.deepcopy(new)
    for value in (left,right):
        value.pop('project_files')
        value['worker_install']['dsh']['web'].pop('egress_evidence')
    f.require(left == right and new['product']['runtime'] == {'enabled':False},
        'ordinary_update_worker_settings_changed')
    entry = marker['ordinary_gateway']['operator_entry']
    f.pin(entry['script'])
    f.require(entry['script']['sha256'] == fresh['scripts/friday_native.py'],
        'ordinary_update_worker_operator_changed')
    expected = copy.deepcopy(before)
    expected['input_sha256'] = marker['input_sha256']
    expected['profile_files']['config.yaml'] = marker['profile_files']['config.yaml']
    for field in ('operator_entry','configuration_sha256'):
        expected['ordinary_gateway'][field] = marker['ordinary_gateway'][field]
    f.require(expected == marker, 'ordinary_update_worker_marker_changed')


def update_inputs(request, budget):
    f = api()
    fields = {'schema','seconds','home','previous_input','current_input','marker','source_receipt',
        'stamp','configuration','profile','launcher','credential_files','native_unit','transaction_history'}
    source85 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v39'
    source84 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v38'
    source83 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v37'
    source82 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v36'
    source81 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v35'
    source80 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v34'
    source79 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v33'
    source78 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v32'
    source77 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v31'
    source76 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v30'
    source75 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v29'
    source74 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v28'
    source73 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v27'
    source72 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v26'
    source71 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v25'
    source70 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v24'
    source69 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v23'
    source68 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v22'
    source67 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v21'
    source66 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v20'
    source65 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v19'
    source64 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v18'
    source63 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v17'
    source62 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v16'
    source61 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v15'
    source60 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v14'
    source59 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v13'
    source58 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v12'
    source57 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v11'
    source56 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v10'
    source55 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v9'
    source54 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v8'
    source53 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v7'
    source52 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v6'
    source51 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v5'
    source50 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v4'
    source49 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v3'
    source48 = type(request) is dict and request.get('schema') == 'friday.ordinary-telegram-source-update.v2'
    f.require(type(request) is dict and set(request) == fields | ({'predecessor_update'} if source48 or source49 or source50 or source51 or source52 or source53 or source54 or source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85 else set()) | ({'worker_declaration_publication'} if source57 else set()) | ({'keyless_recovery'} if source78 else set()) | ({'inference_rebind'} if source80 or source81 else set()) | ({'retained_profile_files'} if source82 or source83 or source84 or source85 else set())
        and request['schema'] in ('friday.ordinary-telegram-source-update.v1','friday.ordinary-telegram-source-update.v2','friday.ordinary-telegram-source-update.v3','friday.ordinary-telegram-source-update.v4','friday.ordinary-telegram-source-update.v5','friday.ordinary-telegram-source-update.v6','friday.ordinary-telegram-source-update.v7','friday.ordinary-telegram-source-update.v8','friday.ordinary-telegram-source-update.v9','friday.ordinary-telegram-source-update.v10','friday.ordinary-telegram-source-update.v11','friday.ordinary-telegram-source-update.v12','friday.ordinary-telegram-source-update.v13','friday.ordinary-telegram-source-update.v14','friday.ordinary-telegram-source-update.v15','friday.ordinary-telegram-source-update.v16','friday.ordinary-telegram-source-update.v17','friday.ordinary-telegram-source-update.v18','friday.ordinary-telegram-source-update.v19','friday.ordinary-telegram-source-update.v20','friday.ordinary-telegram-source-update.v21','friday.ordinary-telegram-source-update.v22','friday.ordinary-telegram-source-update.v23','friday.ordinary-telegram-source-update.v24','friday.ordinary-telegram-source-update.v25','friday.ordinary-telegram-source-update.v26','friday.ordinary-telegram-source-update.v27','friday.ordinary-telegram-source-update.v28','friday.ordinary-telegram-source-update.v29','friday.ordinary-telegram-source-update.v30','friday.ordinary-telegram-source-update.v31','friday.ordinary-telegram-source-update.v32','friday.ordinary-telegram-source-update.v33','friday.ordinary-telegram-source-update.v34','friday.ordinary-telegram-source-update.v35','friday.ordinary-telegram-source-update.v36','friday.ordinary-telegram-source-update.v37','friday.ordinary-telegram-source-update.v38','friday.ordinary-telegram-source-update.v39')
        and type(request['seconds']) is int and 30 <= request['seconds'] <= 180,
        'ordinary_update_explicit_request_required')
    if source85:
        f.require(WEB_RUNTIME_HISTORY_MANIFEST_SHA256 is not None
            and WEB_RUNTIME_HISTORY_PATCH_SHA256 is not None
            and type(WEB_RUNTIME_HISTORY_FILES) is set and bool(WEB_RUNTIME_HISTORY_FILES),
            'ordinary_update_final_web_runtime_history_pins_required')
    if source84:
        f.require(FILE_REPLY_CONTEXT_MANIFEST_SHA256 is not None
            and FILE_REPLY_CONTEXT_PATCH_SHA256 is not None
            and type(FILE_REPLY_CONTEXT_FILES) is set and bool(FILE_REPLY_CONTEXT_FILES),
            'ordinary_update_final_file_reply_context_pins_required')
    if source83:
        f.require(COMBINED_INPUT_MANIFEST_SHA256 is not None and COMBINED_INPUT_PATCH_SHA256 is not None,
            'ordinary_update_final_combined_input_pins_required')
    if source82:
        f.require(WEB_INPUT_MANIFEST_SHA256 is not None and WEB_INPUT_PATCH_SHA256 is not None,
            'ordinary_update_final_web_input_pins_required')
    if source81:
        f.require(FILE_TOOL_CONTRACT_MANIFEST_SHA256 is not None
            and FILE_TOOL_CONTRACT_PATCH_SHA256 is not None,
            'ordinary_update_final_file_tool_pins_required')
    if source80:
        f.require(SPARK_REQUEST_BUDGET_MANIFEST_SHA256 is not None
            and SPARK_REQUEST_BUDGET_PATCH_SHA256 is not None
            and type(SPARK_REQUEST_BUDGET_FILES) is set and bool(SPARK_REQUEST_BUDGET_FILES)
            and type(SPARK_REQUEST_BUDGET_NEW_FILES) is set
            and SPARK_REQUEST_BUDGET_NEW_FILES <= SPARK_REQUEST_BUDGET_FILES,
            'ordinary_update_final_request_budget_pins_required')
    home = f.directory(f.canonical(request['home'])); source = f.directory(home/'hermes-agent')
    f.require(os.environ.get('HERMES_HOME') == str(home), 'ordinary_update_exact_environment_required')
    paths = {name:budget.call(f.pin,request[name]) for name in
        ('previous_input','current_input','marker','source_receipt','stamp','configuration','profile','launcher','native_unit')}
    for name, path in {'marker':home/f.MARKER,'source_receipt':home/'hermes-agent.source.json',
        'stamp':source/'install-stamp.json','configuration':home/'config.yaml',
        'profile':home/'FRIDAY-PROFILE.json','launcher':source/'.hermes/bin/hermes'}.items():
        f.require(paths[name] == path, 'ordinary_update_exact_installed_inputs_required')
    previous = f.read_json(paths['previous_input']); current = f.read_json(paths['current_input'])
    f.require(request['previous_input'] != request['current_input'], 'ordinary_update_new_input_required')
    f.require({k:v for k,v in previous.items() if k != 'project_files'} ==
        {k:v for k,v in current.items() if k != 'project_files'} and current['home'] == str(home),
        'ordinary_update_operational_settings_changed')
    _, donors = budget.call(f.spec_checked,current,cli_only=True)
    marker = f.read_json(paths['marker']); receipt = f.read_json(paths['source_receipt'])
    f.require(marker.get('completion_stage') == 'TELEGRAM_ORDINARY'
        and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE'
        and marker.get('schema') == f.SCHEMA and marker.get('home') == str(home)
        and marker.get('source') == str(source) and marker.get('runtime_ready') is False
        and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
        and marker.get('input_sha256') == request['previous_input']['sha256']
        and marker.get('source_receipt_sha256') == request['source_receipt']['sha256']
        and current['product']['runtime'] == {'enabled':False}, 'ordinary_update_committed_phase_required')
    budget.call(f.composition_checked,previous,source,receipt,donors['hermes'])
    manifest_name = WEB_RUNTIME_HISTORY_MANIFEST if source85 else FILE_REPLY_CONTEXT_MANIFEST if source84 else COMBINED_INPUT_MANIFEST if source83 else WEB_INPUT_MANIFEST if source82 else FILE_TOOL_CONTRACT_MANIFEST if source81 else SPARK_REQUEST_BUDGET_MANIFEST if source80 else SPARK_MULTIPASS_MANIFEST if source79 else PRIVACY_EFFECT_MANIFEST if source78 else DOCX_CREATION_MANIFEST if source77 else DOCUMENT_EXTRACTION_MANIFEST if source76 else FILE_REVISION_MANIFEST if source75 else TOOL_RESULT_CONTEXT_MANIFEST if source74 else DSH_SANDBOX_MANIFEST if source73 else CURRENT_TURN_MANIFEST if source72 else CONTEXT_SELF_MANIFEST if source71 else PRIVATE_REPLY_MANIFEST if source70 else PROMPT_PRIVACY_MANIFEST if source69 else MEMORY_SCOPE_MANIFEST if source68 else FIRST_CONTACT_COPY_MANIFEST if source67 else INLINE_PRIVACY_MANIFEST if source66 else TOOL_METADATA_MANIFEST if source65 else PUBLIC_SURFACE_MANIFEST if source64 else WORKER_TOOLS_MANIFEST if source63 else DIALOGUE_CONTINUATION_MANIFEST if source62 else FIRST_CONTACT_STATE_MANIFEST if source61 else TURN_SCOPE_MANIFEST if source60 else ADMIN_STARTUP_MANIFEST if source59 else INTERACTION_SCOPE_MANIFEST if source58 else PROFILE_RUNTIME_MANIFEST if source57 else BROWSER_GATEWAY_MANIFEST if source56 else BROWSER_MANIFEST if source55 else SEARCH_RECOVERY_MANIFEST if source54 else WEB_OUTPUT_MANIFEST if source53 else WEB_CONTINUATION_MANIFEST if source52 else ADMIN_BROADCAST_MANIFEST if source51 else ADMIN_RESTART_MANIFEST if source50 else FILE_CONTINUATION_MANIFEST if source49 else PRIVATE_STATE_MANIFEST if source48 else UPDATE_MANIFEST
    native_files = WEB_RUNTIME_HISTORY_FILES if source85 else FILE_REPLY_CONTEXT_FILES if source84 else COMBINED_INPUT_FILES if source83 else WEB_INPUT_FILES if source82 else FILE_TOOL_CONTRACT_FILES if source81 else SPARK_REQUEST_BUDGET_FILES if source80 else SPARK_MULTIPASS_FILES if source79 else PRIVACY_EFFECT_FILES if source78 else DOCX_CREATION_FILES if source77 else DOCUMENT_EXTRACTION_FILES if source76 else FILE_REVISION_FILES if source75 else TOOL_RESULT_CONTEXT_FILES if source74 else DSH_SANDBOX_FILES if source73 else CURRENT_TURN_FILES if source72 else CONTEXT_SELF_FILES if source71 else PRIVATE_REPLY_FILES if source70 else PROMPT_PRIVACY_FILES if source69 else MEMORY_SCOPE_FILES if source68 else FIRST_CONTACT_COPY_FILES if source67 else INLINE_PRIVACY_FILES if source66 else TOOL_METADATA_FILES if source65 else PUBLIC_SURFACE_FILES if source64 else WORKER_TOOLS_FILES if source63 else DIALOGUE_CONTINUATION_FILES if source62 else FIRST_CONTACT_STATE_FILES if source61 else TURN_SCOPE_FILES if source60 else ADMIN_STARTUP_FILES if source59 else INTERACTION_SCOPE_FILES if source58 else PROFILE_RUNTIME_FILES if source57 else BROWSER_GATEWAY_FILES if source56 else BROWSER_FILES if source55 else SEARCH_RECOVERY_FILES if source54 else WEB_OUTPUT_FILES if source53 else WEB_CONTINUATION_FILES if source52 else ADMIN_BROADCAST_FILES if source51 else ADMIN_RESTART_FILES if source50 else FILE_CONTINUATION_FILES if source49 else PRIVATE_STATE_FILES if source48 else UPDATE_FILES
    manifest = json.loads(f.owned_file(f.ROOT/manifest_name),object_pairs_hook=f.unique)
    old = previous['project_files']; new = current['project_files']
    patch = manifest['patch']
    f.require(patch == (WEB_RUNTIME_HISTORY_PATCH if source85 else FILE_REPLY_CONTEXT_PATCH if source84 else COMBINED_INPUT_PATCH if source83 else WEB_INPUT_PATCH if source82 else FILE_TOOL_CONTRACT_PATCH if source81 else SPARK_REQUEST_BUDGET_PATCH if source80 else SPARK_MULTIPASS_PATCH if source79 else 'patches/hermes/ordinary-private-refusal-effect.patch' if source78 else 'patches/hermes/ordinary-docx-creation.patch' if source77 else 'patches/hermes/ordinary-document-extraction.patch' if source76 else 'patches/hermes/ordinary-file-revision.patch' if source75 else 'patches/hermes/ordinary-tool-result-context.patch' if source74 else 'patches/hermes/ordinary-dsh-native-sandbox-profile.patch' if source73 else 'patches/hermes/ordinary-current-turn-compaction-privacy-reply.patch' if source72 else 'patches/hermes/ordinary-context-self-disclosure.patch' if source71 else 'patches/hermes/ordinary-private-reply-compression.patch' if source70 else 'patches/hermes/ordinary-prompt-privacy-dialogue.patch' if source69 else 'patches/hermes/ordinary-memory-scope-privacy.patch' if source68 else 'patches/hermes/ordinary-first-contact-copy.patch' if source67 else 'patches/hermes/ordinary-inline-privacy-connected-repair.patch' if source66 else 'patches/hermes/ordinary-tool-metadata-progress-privacy.patch' if source65 else 'patches/hermes/ordinary-public-surface-privacy.patch' if source64 else 'patches/hermes/ordinary-worker-tools-packaging.patch' if source63 else 'patches/hermes/ordinary-dialogue-continuation.patch' if source62 else 'patches/hermes/ordinary-first-contact-state.patch' if source61 else 'patches/hermes/ordinary-telegram-turn-scope.patch' if source60 else 'patches/hermes/ordinary-admin-startup.patch' if source59 else 'patches/hermes/ordinary-interaction-scope.patch' if source58 else 'patches/hermes/ordinary-profile-runtime.patch' if source57 else 'patches/hermes/ordinary-browser-gateway.patch' if source56 else 'patches/hermes/ordinary-browser.patch' if source55 else 'patches/hermes/ordinary-search-recovery.patch' if source54 else 'patches/hermes/ordinary-web-output.patch' if source53 else 'patches/hermes/ordinary-web-continuation.patch' if source52 else 'patches/hermes/ordinary-admin-broadcast.patch' if source51 else 'patches/hermes/ordinary-admin-restart.patch' if source50 else 'patches/hermes/ordinary-file-continuation.patch' if source49 else 'patches/hermes/ordinary-private-state.patch' if source48 else 'patches/hermes/ordinary-native-repair.patch')
        and set(new) == set(old) | {manifest_name,patch}
        and all(new[name] == pin for name,pin in old.items()
                if name not in (({'scripts/friday_ordinary_install.py'} if source50 or source51 or source52 or source53 or source54 or source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85 else {'scripts/friday_install.py','scripts/friday_ordinary_install.py'}) |
                                ({'scripts/friday_start.py'} if source48 or source54 else set()) |
                                ({'tools/render_dsh_local.py'} if source73 else set()) |
                                (set(FILE_TOOL_CONTRACT_PROJECT_AFTER) if source81 else set(SPARK_REQUEST_BUDGET_PROJECT_AFTER) if source80 else set(SPARK_MULTIPASS_PROJECT_AFTER) if source79 else set()) |
                                (SPARK_MULTIPASS_PLUGIN_FILES if source79 else PRIVACY_EFFECT_PLUGIN_FILES if source78 else CONTEXT_SELF_PLUGIN_FILES if source71 else TOOL_METADATA_PLUGIN_FILES if source65 else WORKER_TOOLS_PLUGIN_FILES if source63 else BROWSER_PLUGIN_FILES if source55 else WORKER_ATTACH_PLUGIN_FILES if source49 else set()))),
        'ordinary_update_only_reviewed_source_required')
    f.require(manifest.get('base_commit') == receipt['commit']
        and len(receipt['layers']) == (83 if source85 else 82 if source84 else 81 if source83 or source82 else 80 if source81 else 79 if source80 else 78 if source79 else 77 if source78 else 76 if source77 else 75 if source76 else 74 if source75 else 73 if source74 else 72 if source73 else 71 if source72 else 70 if source71 else 69 if source70 else 68 if source69 else 67 if source68 else 66 if source67 else 65 if source66 else 64 if source65 else 63 if source64 else 62 if source63 else 61 if source62 else 60 if source61 else 59 if source60 else 58 if source59 else 57 if source58 else 56 if source57 else 55 if source56 else 54 if source55 else 53 if source54 else 52 if source53 else 51 if source52 else 50 if source51 else 49 if source50 else 48 if source49 else 47 if source48 else 46) and manifest_name not in {r['manifest'] for r in receipt['layers']}
        and manifest.get('installed_prefix') == {r['manifest']:r['manifest_sha256'] for r in receipt['layers']}
        and new[manifest_name] == f.digest(f.owned_file(f.ROOT/manifest_name))
        and manifest['patch_sha256'] == new[patch] == f.digest(f.owned_file(f.ROOT/patch)),
        'ordinary_update_exact_prefix_required')
    rows = manifest['files']
    f.require(type(rows) is list and len(rows) == len(native_files) and {r['path'] for r in rows} == native_files,
        'ordinary_update_exact_native_files_required')
    if source63:
        f.directory(source/'tools')
        f.require(not os.path.lexists(source/'config'), 'ordinary_update_new_directory_exists')
    for row in rows:
        added = (source80 and row['path'] in SPARK_REQUEST_BUDGET_NEW_FILES) or (source79 and row['path'] in SPARK_MULTIPASS_NEW_FILES) or (source78 and row['path'] in PRIVACY_EFFECT_NEW_FILES) or (source77 and row['path'] in DOCX_CREATION_NEW_FILES) or (source75 and row['path'] in FILE_REVISION_NEW_FILES) or (source55 and row['path'] in BROWSER_NEW_FILES) or (source63 and row['path'] in WORKER_TOOLS_FILES)
        if added:
            f.require(row.get('new_file') is True and row.get('mode') == '100644'
                and row.get('before_sha256') is None and row['path'] not in receipt['files']
                and not os.path.lexists(source/row['path']), 'ordinary_update_new_source_exists')
        else:
            f.require(row.get('new_file') is False and row.get('mode') == '100644'
                and row['before_sha256'] == receipt['files'][row['path']]['sha256']
                and row['before_sha256'] == f.digest(f.owned_file(source/row['path'])),
                'ordinary_update_source_changed')
    # Reuse the shipped preparer's Git parser before any mutation. An extra
    # patch target must never escape this transaction's owned-file rollback.
    from scripts.hermes_prepare import overlay_layers, Budget as SourceBudget
    layers = budget.call(overlay_layers,f.ROOT,receipt['commit'],SourceBudget(budget.deadline))
    f.require(layers[-1][1]['manifest'] == manifest_name,
        'ordinary_update_final_layer_required')
    predecessor = request.get('predecessor_update')
    update_history(home,request['transaction_history'],predecessor,request.get('keyless_recovery'),request.get('inference_rebind'))
    if source48 or source49 or source50 or source51 or source52 or source53 or source54 or source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85:
        old_request = f.read_json(f.pin(predecessor))
        f.require(old_request['schema'] == ('friday.ordinary-telegram-source-update.v38' if source85 else 'friday.ordinary-telegram-source-update.v37' if source84 else 'friday.ordinary-telegram-source-update.v35' if source83 or source82 else 'friday.ordinary-telegram-source-update.v34' if source81 else PROJECT_INFERENCE_HELPER_SCHEMA if source80 else 'friday.ordinary-telegram-source-update.v32' if source79 else PROJECT_RUNTIME_SCHEMA if source78 else 'friday.ordinary-telegram-source-update.v30' if source77 else 'friday.ordinary-telegram-source-update.v29' if source76 else 'friday.ordinary-telegram-source-update.v28' if source75 else 'friday.ordinary-telegram-source-update.v27' if source74 else 'friday.ordinary-telegram-source-update.v26' if source73 else 'friday.ordinary-telegram-source-update.v25' if source72 else 'friday.ordinary-telegram-source-update.v24' if source71 else 'friday.ordinary-telegram-source-update.v23' if source70 else 'friday.ordinary-telegram-source-update.v22' if source69 else 'friday.ordinary-telegram-source-update.v21' if source68 else 'friday.ordinary-telegram-source-update.v20' if source67 else 'friday.ordinary-telegram-source-update.v19' if source66 else 'friday.ordinary-telegram-source-update.v18' if source65 else 'friday.ordinary-telegram-source-update.v17' if source64 else 'friday.ordinary-telegram-source-update.v16' if source63 else 'friday.ordinary-telegram-source-update.v15' if source62 else 'friday.ordinary-telegram-source-update.v14' if source61 else 'friday.ordinary-telegram-source-update.v13' if source60 else 'friday.ordinary-telegram-source-update.v12' if source59 else 'friday.ordinary-telegram-source-update.v11' if source58 else 'friday.ordinary-telegram-source-update.v10' if source57 else 'friday.ordinary-telegram-source-update.v9' if source56 else 'friday.ordinary-telegram-source-update.v8' if source55 else 'friday.ordinary-telegram-source-update.v7' if source54 else 'friday.ordinary-telegram-source-update.v6' if source53 else 'friday.ordinary-telegram-source-update.v5' if source52 else 'friday.ordinary-telegram-source-update.v4' if source51 else 'friday.ordinary-telegram-source-update.v3' if source50 else 'friday.ordinary-telegram-source-update.v2' if source49
            else 'friday.ordinary-telegram-source-update.v1'), 'ordinary_update_predecessor_version_changed')
        old_tx = home/'preparation'/('ordinary-source-update-'+old_request['previous_input']['sha256'])
        committed = f.read_json(old_tx/'committed.json')
        if source57:
            budget.call(checked_worker_declaration_publication,home,request,old_request,marker)
        if source78:
            recovery = f.read_json(f.pin(request['keyless_recovery']))
            f.require(recovery['recovery_input'] == request['previous_input']
                and recovery['source_receipt'] == request['source_receipt']
                and recovery['stamp'] == request['stamp'],
                'ordinary_update_keyless_current_binding_changed')
        f.require(old_request['home'] == str(home) and (source57 or (source78 and f.read_json(f.pin(request['keyless_recovery']))['recovery_input'] == request['previous_input']) or ((source80 or source81) and f.read_json(f.pin(request['inference_rebind']))['current_input'] == request['previous_input']) or old_request['current_input'] == request['previous_input'])
            and committed['source_receipt_sha256'] == request['source_receipt']['sha256'],
            'ordinary_update_predecessor_binding_changed')
    # Complete native identity/configuration/credential validation is reused;
    # no consumed query or historical installer phase is ever invoked.
    f.native_packages(source)
    from hermes_cli.friday_ordinary_gateway import check
    if source56:
        check_browser_gateway(home,source,manifest,budget,staged=True)
    else:
        check(home,role=False)
    f.require(all(f.digest(f.owned_file(home/name,private=True)) == pin
        for name,pin in marker['profile_files'].items() if not ((source49 or source50 or source51 or source52 or source53 or source54 or source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85) and name == 'config.yaml')),
        'ordinary_update_profile_changed')
    if source50 or source51 or source52 or source53 or source54 or source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85:
        before_plugins = {n:p for n,p in previous['project_files'].items() if n.startswith('plugins/friday_rework/')}
        f.require(marker.get('plugin_files') == before_plugins, 'ordinary_update_installed_plugin_marker_changed')
        checked_plugin_inventory(home, before_plugins)
    if source85:
        f.require(new[manifest_name] == WEB_RUNTIME_HISTORY_MANIFEST_SHA256
            and new[patch] == WEB_RUNTIME_HISTORY_PATCH_SHA256
            and request['previous_input']['sha256'] == WEB_RUNTIME_HISTORY_PREVIOUS_INPUT
            and request['predecessor_update']['sha256'] == WEB_RUNTIME_HISTORY_PREDECESSOR_REQUEST
            and len(request['transaction_history']) == WEB_RUNTIME_HISTORY_HISTORY_FILES
            and len(old) == 239 and len(new) == 241
            and len(receipt['files']) == WEB_RUNTIME_HISTORY_NATIVE_FILES
            and receipt['layers'][-1]['manifest'] == FILE_REPLY_CONTEXT_MANIFEST
            and WEB_RUNTIME_HISTORY_FILES <= set(receipt['files'])
            and {n for n in old if old[n] != new[n]} == {'scripts/friday_ordinary_install.py'}
            and old['scripts/friday_ordinary_install.py'] == WEB_RUNTIME_HISTORY_PREVIOUS_UPDATER
            and new['scripts/friday_ordinary_install.py'] == f.digest(f.owned_file(Path(__file__)))
            and f.digest(f.owned_file(old_tx/'committed.json',private=True)) == WEB_RUNTIME_HISTORY_PREDECESSOR_COMMITTED
            and len(before_plugins) == 45
            and not f.read_json(old_tx/'intent.json').get('project_only',False)
            and not committed.get('project_only',False),
            'ordinary_update_exact_web_runtime_history_delta_required')
        checked_source82_retained(home,request)
    if source84:
        f.require(new[manifest_name] == FILE_REPLY_CONTEXT_MANIFEST_SHA256
            and new[patch] == FILE_REPLY_CONTEXT_PATCH_SHA256
            and request['previous_input']['sha256'] == FILE_REPLY_CONTEXT_PREVIOUS_INPUT
            and request['predecessor_update']['sha256'] == FILE_REPLY_CONTEXT_PREDECESSOR_REQUEST
            and len(request['transaction_history']) == FILE_REPLY_CONTEXT_HISTORY_FILES
            and len(old) == 237 and len(new) == 239
            and len(receipt['files']) == FILE_REPLY_CONTEXT_NATIVE_FILES
            and receipt['layers'][-1]['manifest'] == COMBINED_INPUT_MANIFEST
            and FILE_REPLY_CONTEXT_FILES <= set(receipt['files'])
            and {n for n in old if old[n] != new[n]} == {'scripts/friday_ordinary_install.py'}
            and old['scripts/friday_ordinary_install.py'] == FILE_REPLY_CONTEXT_PREVIOUS_UPDATER
            and new['scripts/friday_ordinary_install.py'] == f.digest(f.owned_file(Path(__file__)))
            and f.digest(f.owned_file(old_tx/'committed.json',private=True)) == FILE_REPLY_CONTEXT_PREDECESSOR_COMMITTED
            and len(before_plugins) == 45
            and not f.read_json(old_tx/'intent.json').get('project_only',False)
            and not committed.get('project_only',False),
            'ordinary_update_exact_file_reply_context_delta_required')
        checked_source82_retained(home,request)
    if source83:
        f.require(new[manifest_name] == COMBINED_INPUT_MANIFEST_SHA256
            and new[patch] == COMBINED_INPUT_PATCH_SHA256
            and request['previous_input']['sha256'] == COMBINED_INPUT_PREVIOUS_INPUT
            and request['predecessor_update']['sha256'] == COMBINED_INPUT_PREDECESSOR_REQUEST
            and len(request['transaction_history']) == COMBINED_INPUT_HISTORY_FILES
            and len(old) == 235 and len(new) == 237
            and len(receipt['files']) == COMBINED_INPUT_NATIVE_FILES
            and receipt['layers'][-1]['manifest'] == FILE_TOOL_CONTRACT_MANIFEST
            and COMBINED_INPUT_FILES <= set(receipt['files'])
            and {n for n in old if old[n] != new[n]} == {'scripts/friday_ordinary_install.py'}
            and old['scripts/friday_ordinary_install.py'] == COMBINED_INPUT_PREVIOUS_UPDATER
            and new['scripts/friday_ordinary_install.py'] == f.digest(f.owned_file(Path(__file__)))
            and len(before_plugins) == 45
            and not f.read_json(old_tx/'intent.json').get('project_only',False)
            and not committed.get('project_only',False),
            'ordinary_update_exact_combined_input_delta_required')
        checked_source82_retained(home,request)
    if source82:
        f.require(new[manifest_name] == WEB_INPUT_MANIFEST_SHA256
            and new[patch] == WEB_INPUT_PATCH_SHA256
            and request['previous_input']['sha256'] == WEB_INPUT_PREVIOUS_INPUT
            and request['predecessor_update']['sha256'] == WEB_INPUT_PREDECESSOR_REQUEST
            and len(request['transaction_history']) == WEB_INPUT_HISTORY_FILES
            and len(old) == 235 and len(new) == 237
            and len(receipt['files']) == WEB_INPUT_NATIVE_FILES
            and receipt['layers'][-1]['manifest'] == FILE_TOOL_CONTRACT_MANIFEST
            and WEB_INPUT_FILES <= set(receipt['files'])
            and {n for n in old if old[n] != new[n]} == {'scripts/friday_ordinary_install.py'}
            and old['scripts/friday_ordinary_install.py'] == WEB_INPUT_PREVIOUS_UPDATER
            and new['scripts/friday_ordinary_install.py'] == f.digest(f.owned_file(Path(__file__)))
            and len(before_plugins) == 45
            and not f.read_json(old_tx/'intent.json').get('project_only',False)
            and not committed.get('project_only',False),
            'ordinary_update_exact_web_input_delta_required')
        checked_source82_retained(home,request)
    if source81:
        f.require(new[manifest_name] == FILE_TOOL_CONTRACT_MANIFEST_SHA256
            and new[patch] == FILE_TOOL_CONTRACT_PATCH_SHA256
            and request['previous_input']['sha256'] == FILE_TOOL_CONTRACT_PREVIOUS_INPUT
            and request['predecessor_update']['sha256'] == SOURCE81_PREDECESSOR_REQUEST
            and request['inference_rebind']['sha256'] == SOURCE81_BUDGET_REQUEST
            and len(request['transaction_history']) == SOURCE81_HISTORY_FILES
            and len(old) == 233 and len(new) == 235
            and len(receipt['files']) == FILE_TOOL_CONTRACT_NATIVE_FILES
            and receipt['layers'][-1]['manifest'] == SPARK_REQUEST_BUDGET_MANIFEST
            and FILE_TOOL_CONTRACT_FILES <= set(receipt['files'])
            and set(FILE_TOOL_CONTRACT_PROJECT_AFTER) == FILE_TOOL_CONTRACT_PLUGIN_FILES
            and {n for n in old if old[n] != new[n]} == set(FILE_TOOL_CONTRACT_PROJECT_BEFORE)
            and all(old[n] == h for n,h in FILE_TOOL_CONTRACT_PROJECT_BEFORE.items())
            and all(new[n] == h for n,h in FILE_TOOL_CONTRACT_PROJECT_AFTER.items())
            and new['scripts/friday_ordinary_install.py'] == f.digest(f.owned_file(Path(__file__)))
            and len(before_plugins) == 45
            and {n for n in before_plugins if old[n] != new[n]} == FILE_TOOL_CONTRACT_PLUGIN_FILES
            and not f.read_json(old_tx/'intent.json').get('project_only',False)
            and not committed.get('project_only',False),
            'ordinary_update_exact_file_tool_delta_required')
        checked_source81_retained(home,request)
    if source80:
        rebound = f.read_json(f.pin(request['inference_rebind']))
        after = f.read_json(home/'preparation'/('ordinary-inference-rebind-'+
            rebound['previous_input']['sha256'])/'committed.json')['after']
        for name,sha in PROJECT_INFERENCE_RECONCILIATION_PINS.items():
            f.pin({'path':str(home/name),'sha256':sha})
        f.require(SPARK_REQUEST_BUDGET_MANIFEST_SHA256 is not None
            and SPARK_REQUEST_BUDGET_PATCH_SHA256 is not None
            and new[manifest_name] == SPARK_REQUEST_BUDGET_MANIFEST_SHA256
            and new[patch] == SPARK_REQUEST_BUDGET_PATCH_SHA256
            and all(h is not None for h in SPARK_REQUEST_BUDGET_PROJECT_AFTER.values()),
            'ordinary_update_final_request_budget_pins_required')
        f.require(request['previous_input']['sha256'] == SPARK_REQUEST_BUDGET_PREVIOUS_INPUT
            and request['predecessor_update']['sha256'] == SOURCE80_HELPER_REQUEST
            and request['inference_rebind']['sha256'] == SOURCE80_REBIND_REQUEST
            and len(request['transaction_history']) == SOURCE80_HISTORY_FILES
            and len(old) == 231 and len(new) == 233
            and len(receipt['files']) == SPARK_REQUEST_BUDGET_NATIVE_FILES
            and receipt['layers'][-1]['manifest'] == SPARK_MULTIPASS_MANIFEST
            and set(receipt['files']) >= SPARK_REQUEST_BUDGET_FILES - SPARK_REQUEST_BUDGET_NEW_FILES
            and not (set(receipt['files']) & SPARK_REQUEST_BUDGET_NEW_FILES)
            and not (set(old) & SPARK_REQUEST_BUDGET_FILES)
            and set(SPARK_REQUEST_BUDGET_PROJECT_AFTER) == set(SPARK_REQUEST_BUDGET_PROJECT_BEFORE) - {'scripts/friday_ordinary_install.py'}
            and {n for n in old if old[n] != new[n]} == set(SPARK_REQUEST_BUDGET_PROJECT_BEFORE)
            and all(old[n] == h for n,h in SPARK_REQUEST_BUDGET_PROJECT_BEFORE.items())
            and all(new[n] == h for n,h in SPARK_REQUEST_BUDGET_PROJECT_AFTER.items())
            and new['scripts/friday_ordinary_install.py'] == f.digest(f.owned_file(Path(__file__)))
            and len(before_plugins) == 45
            and {n for n in before_plugins if old[n] != new[n]} == SPARK_REQUEST_BUDGET_PLUGIN_FILES
            and f.read_json(old_tx/'intent.json').get('project_only') is True
            and committed.get('project_only') is True
            and type(current['product']['runtime']['enabled']) is bool,
            'ordinary_update_exact_request_budget_delta_required')
        f.require(request['marker']['sha256'] == after[f.MARKER],
            'ordinary_update_rebound_marker_changed')
        for name,sha in after.items():
            f.pin({'path':str(home/name),'sha256':sha})
    if source79:
        f.require(SPARK_MULTIPASS_MANIFEST_SHA256 is not None
            and SPARK_MULTIPASS_PATCH_SHA256 is not None
            and new[manifest_name] == SPARK_MULTIPASS_MANIFEST_SHA256
            and new[patch] == SPARK_MULTIPASS_PATCH_SHA256,
            'ordinary_update_final_spark_pins_required')
        f.require(request['previous_input']['sha256'] == SPARK_MULTIPASS_PREVIOUS_INPUT
            and len(old) == 229 and len(new) == 231
            and len(receipt['files']) == SPARK_MULTIPASS_NATIVE_FILES
            and set(receipt['files']) >= SPARK_MULTIPASS_FILES - SPARK_MULTIPASS_NEW_FILES
            and not (set(receipt['files']) & SPARK_MULTIPASS_NEW_FILES)
            and not (set(old) & SPARK_MULTIPASS_FILES)
            and {n for n in old if old[n] != new[n]} == set(SPARK_MULTIPASS_PROJECT_BEFORE)
            and all(old[n] == h for n,h in SPARK_MULTIPASS_PROJECT_BEFORE.items())
            and all(new[n] == h for n,h in SPARK_MULTIPASS_PROJECT_AFTER.items())
            and len(before_plugins) == 45
            and {n for n in before_plugins if old[n] != new[n]} == SPARK_MULTIPASS_PLUGIN_FILES,
            'ordinary_update_exact_spark_multipass_delta_required')
    if source78:
        f.require(len(old) == 227 and len(new) == 229 and len(receipt['files']) == PRIVACY_EFFECT_NATIVE_FILES
            and set(receipt['files']) >= PRIVACY_EFFECT_FILES - PRIVACY_EFFECT_NEW_FILES
            and not (set(receipt['files']) & PRIVACY_EFFECT_NEW_FILES)
            and not (set(old) & PRIVACY_EFFECT_FILES)
            and {n for n in old if n.startswith('plugins/friday_rework/') and old[n] != new[n]} == PRIVACY_EFFECT_PLUGIN_FILES
            and all(old[n] == PRIVACY_EFFECT_PLUGIN_BEFORE and new[n] == PRIVACY_EFFECT_PLUGIN_AFTER for n in PRIVACY_EFFECT_PLUGIN_FILES),
            'ordinary_update_exact_privacy_effect_delta_required')
    if source77:
        f.require(len(old) == 220 and len(new) == 222 and set(receipt['files']) >= DOCX_CREATION_FILES - DOCX_CREATION_NEW_FILES
            and not (set(receipt['files']) & DOCX_CREATION_NEW_FILES) and not (set(old) & DOCX_CREATION_FILES),
            'ordinary_update_exact_docx_creation_delta_required')
    if source76:
        f.require(len(old) == 218 and len(new) == 220 and set(receipt['files']) >= DOCUMENT_EXTRACTION_FILES
            and not (set(old) & DOCUMENT_EXTRACTION_FILES),
            'ordinary_update_exact_document_extraction_delta_required')
    if source75:
        f.require(len(old) == 216 and len(new) == 218 and set(receipt['files']) >= FILE_REVISION_FILES - FILE_REVISION_NEW_FILES
            and not (set(old) & FILE_REVISION_FILES),
            'ordinary_update_exact_file_revision_delta_required')
    if source74:
        f.require(len(old) == 214 and len(new) == 216 and set(receipt['files']) >= TOOL_RESULT_CONTEXT_FILES
            and not (set(old) & TOOL_RESULT_CONTEXT_FILES),
            'ordinary_update_exact_tool_result_context_delta_required')
    if source73:
        f.require(len(old) == 212 and len(new) == 214 and set(receipt['files']) >= DSH_SANDBOX_FILES
            and all(old[row['path']] == row['before_sha256'] and new[row['path']] == row['sha256']
                for row in rows if row['path'] == 'tools/render_dsh_local.py'),
            'ordinary_update_exact_dsh_sandbox_delta_required')
    if source72:
        f.require(len(old) == 210 and len(new) == 212 and set(receipt['files']) >= CURRENT_TURN_FILES,
            'ordinary_update_exact_current_turn_delta_required')
    if source71:
        f.require(len(old) == 208 and len(new) == 210 and set(receipt['files']) >= CONTEXT_SELF_FILES
            and {n for n in old if n.startswith('plugins/friday_rework/') and old[n] != new[n]} == CONTEXT_SELF_PLUGIN_FILES,
            'ordinary_update_exact_context_self_delta_required')
    if source70:
        f.require(len(old) == 206 and len(new) == 208 and set(receipt['files']) >= PRIVATE_REPLY_FILES,
            'ordinary_update_exact_private_reply_delta_required')
    if source69:
        f.require(len(old) == 204 and len(new) == 206 and set(receipt['files']) >= PROMPT_PRIVACY_FILES,
            'ordinary_update_exact_prompt_privacy_delta_required')
    if source68:
        f.require(len(old) == 202 and len(new) == 204 and set(receipt['files']) >= MEMORY_SCOPE_FILES,
            'ordinary_update_exact_memory_scope_delta_required')
    if source67:
        f.require(len(old) == 200 and len(new) == 202 and set(receipt['files']) >= FIRST_CONTACT_COPY_FILES,
            'ordinary_update_exact_first_contact_copy_delta_required')
    if source66:
        f.require(len(old) == 198 and len(new) == 200 and set(receipt['files']) >= INLINE_PRIVACY_FILES,
            'ordinary_update_exact_inline_privacy_delta_required')
    if source65:
        f.require(len(old) == 196 and len(new) == 198 and set(receipt['files']) >= TOOL_METADATA_FILES
            and {n for n in old if n.startswith('plugins/friday_rework/') and old[n] != new[n]} == TOOL_METADATA_PLUGIN_FILES,
            'ordinary_update_exact_tool_metadata_delta_required')
    if source64:
        f.require(len(old) == 194 and len(new) == 196 and set(receipt['files']) >= PUBLIC_SURFACE_FILES,
            'ordinary_update_exact_public_surface_delta_required')
    if source63:
        f.require(len(old) == 192 and len(new) == 194
            and not (set(receipt['files']) & WORKER_TOOLS_FILES)
            and {n for n in old if n.startswith('plugins/friday_rework/') and old[n] != new[n]} == WORKER_TOOLS_PLUGIN_FILES,
            'ordinary_update_exact_worker_tools_delta_required')
    if source62:
        f.require(len(old) == 190 and len(new) == 192
            and set(receipt['files']) >= DIALOGUE_CONTINUATION_FILES,
            'ordinary_update_exact_dialogue_continuation_delta_required')
    if source61:
        f.require(len(old) == 188 and len(new) == 190
            and set(receipt['files']) >= FIRST_CONTACT_STATE_FILES,
            'ordinary_update_exact_first_contact_state_delta_required')
    if source60:
        f.require(len(old) == 186 and len(new) == 188
            and set(receipt['files']) >= TURN_SCOPE_FILES,
            'ordinary_update_exact_turn_scope_delta_required')
    if source59:
        f.require(len(old) == 184 and len(new) == 186
            and set(receipt['files']) >= ADMIN_STARTUP_FILES,
            'ordinary_update_exact_admin_startup_delta_required')
    if source58:
        f.require(len(old) == 182 and len(new) == 184
            and set(receipt['files']) >= INTERACTION_SCOPE_FILES,
            'ordinary_update_exact_interaction_scope_delta_required')
    if source57:
        f.require(len(old) == 180 and len(new) == 182
            and set(receipt['files']) >= PROFILE_RUNTIME_FILES,
            'ordinary_update_exact_profile_runtime_delta_required')
    if source56:
        f.require(len(old) == 176 and len(new) == 178
            and set(receipt['files']) >= BROWSER_GATEWAY_FILES,
            'ordinary_update_exact_browser_gateway_delta_required')
    if source55:
        before_plugins = {n:p for n,p in old.items() if n.startswith('plugins/friday_rework/')}
        after_plugins = {n:p for n,p in new.items() if n.startswith('plugins/friday_rework/')}
        f.require(len(old) == 174 and len(new) == 176 and set(before_plugins) == set(after_plugins)
            and {n for n in before_plugins if before_plugins[n] != after_plugins[n]} == BROWSER_PLUGIN_FILES,
            'ordinary_update_exact_browser_plugin_delta_required')
    if source49:
        before_plugins = {n:p for n,p in previous['project_files'].items() if n.startswith('plugins/friday_rework/')}
        after_plugins = {n:p for n,p in current['project_files'].items() if n.startswith('plugins/friday_rework/')}
        f.require(marker.get('plugin_files') == before_plugins and set(before_plugins) == set(after_plugins)
            and {n for n in before_plugins if before_plugins[n] != after_plugins[n]} == WORKER_ATTACH_PLUGIN_FILES,
            'ordinary_update_exact_worker_plugin_delta_required')
        checked_plugin_inventory(home, before_plugins)
    credentials = request['credential_files']
    f.require(type(credentials) is dict and set(credentials) == {'.env','auth.json'},
        'ordinary_update_credential_pins_required')
    for name,ref in credentials.items():
        f.require(not os.path.lexists(home/name) if ref is None else f.pin(ref) == home/name,
            'ordinary_update_credential_pin_changed')
    tx = home/'preparation'/('ordinary-source-update-'+request['previous_input']['sha256'])
    f.require(not os.path.lexists(tx), 'ordinary_update_consumed_no_retry')
    return home, source, previous, current, marker, receipt, manifest, donors, tx


@contextlib.contextmanager
def stopped_consumers(home, unit_ref, budget):
    """Prove native stop, then retain standard native custody for all three roles."""
    f = api()
    from gateway import host_rendezvous as hr
    from gateway.status import get_running_pid_identity_strict
    from hermes_cli import gateway as gw
    f.require(gw.get_systemd_unit_path(system=False) == f.pin(unit_ref)
        and not os.path.lexists(gw.get_systemd_unit_path(system=True)),
        'ordinary_update_exact_native_user_unit_required')
    runtime = f.directory(Path('/run/user')/str(os.getuid())); bus = runtime/'bus'; info = bus.lstat()
    f.require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
        'ordinary_update_owned_user_bus_required')
    unit = gw.get_service_name()+'.service'
    command = ['/usr/bin/env','XDG_RUNTIME_DIR='+str(runtime),
        'DBUS_SESSION_BUS_ADDRESS=unix:path='+str(bus),'/usr/bin/systemctl','--user','show',unit,
        '--property=Id,LoadState,ActiveState,SubState,MainPID,ControlPID']
    from scripts.dsh_prepare import run
    def prove():
        output = run(command,f.ROOT,timeout=min(15,budget.check(reserve=1)),
            env=f.clean_environment(home),deadline=budget.deadline)[0]
        pairs = [line.split('=',1) for line in output.splitlines() if line]
        f.require(len(pairs) == 6 and all(len(row) == 2 for row in pairs)
            and dict(pairs) == {'Id':unit,'LoadState':'loaded','ActiveState':'inactive',
                'SubState':'dead','MainPID':'0','ControlPID':'0'}, 'ordinary_update_native_stop_required')
        f.require(get_running_pid_identity_strict(home/'gateway.pid') is None,
            'ordinary_update_gateway_pid_present')
        for role in (hr.ROLE_GATEWAY,hr.ROLE_SERVE,hr.ROLE_DESKTOP_SERVE):
            f.require(not os.path.lexists(hr.record_path(role))
                and hr.read_record(role,include_stale=True) is None,
                'ordinary_update_no_native_consumer_required')
    claimed = []
    try:
        prove()
        f.directory(hr.host_state_dir())
        for role in (hr.ROLE_GATEWAY,hr.ROLE_SERVE,hr.ROLE_DESKTOP_SERVE):
            path = hr.lock_path(role)
            f.require(path.parent == hr.host_state_dir() and not hr.owns_host_lock(role),
                'ordinary_update_native_lock_scope_changed')
            before = None
            if os.path.lexists(path):
                f.owned_file(path); info = path.stat(); before = (info.st_dev,info.st_ino)
            outcome,_ = hr.claim_host_lock(role)
            f.require(outcome is hr.HostLockOutcome.ACQUIRED,
                'ordinary_update_native_lock_held_or_unavailable')
            claimed.append(role)
            # Native claim may create its ordinary empty lock; it never
            # publishes a role record or starts a gateway/dashboard consumer.
            f.owned_file(path); info = path.stat()
            f.require(hr.owns_host_lock(role) and (before is None or before == (info.st_dev,info.st_ino)),
                'ordinary_update_native_lock_identity_changed')
        prove()
        yield prove
    finally:
        for role in reversed(claimed): hr.release_host_lock(role)
        f.require(not any(hr.owns_host_lock(role) for role in claimed),
            'ordinary_update_native_lock_release_unconfirmed')


@contextlib.contextmanager
def retained_build_lock(source):
    """Retain the exact existing native build lock; never create or replace it."""
    f = api(); path = source/'.web_ui_build.lock'
    if not os.path.lexists(path):
        yield lambda: f.require(not os.path.lexists(path),'ordinary_update_web_build_lock_appeared')
        return
    f.require(f.owned_file(path) == b'', 'ordinary_update_native_build_lock_required')
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK); held = False
    try:
        before = os.fstat(fd)
        def prove():
            current = os.fstat(fd); named = path.lstat()
            fields = ('st_dev','st_ino','st_mode','st_uid','st_nlink','st_size','st_mtime_ns')
            f.require(stat.S_ISREG(current.st_mode) and current.st_uid == os.getuid()
                and current.st_nlink == 1 and current.st_size == 0
                and stat.S_IMODE(current.st_mode) in (0o600,0o644,0o664)
                and all(getattr(before,k) == getattr(current,k) == getattr(named,k) for k in fields),
                'ordinary_update_native_build_lock_changed')
        prove()
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); held = True
        prove(); yield prove
    finally:
        try:
            if held:
                try: prove()
                except BaseException as exc:
                    from scripts.dsh_prepare import StopUnconfirmed
                    raise StopUnconfirmed('native build lock custody requires reconciliation') from exc
        finally: os.close(fd)



PROJECT_UPDATE_SCHEMA = 'friday.ordinary-telegram-project-update.v1'
PROJECT_QUALIFICATION_SCHEMA = 'friday.ordinary-telegram-project-update.v2'
PROJECT_QUALIFICATION_NATIVE_FILES = 17682
PROJECT_QUALIFICATION_HISTORY_FILES = 417
PROJECT_QUALIFICATION_BEFORE = {
    'plugins/friday_rework/host_runtime.py':'89a45984ab69ca3c6fb8d339c09a123d7b76e4dda1a47099fa5a63e61b5d795c',
    'plugins/friday_rework/user_worker_join.py':'98094b0b4063ebc419c8c5de5cc3e0fc394ad5a577c3ad361964da67da5f1894',
    'scripts/worker_qualification.py':'fcb09bcb67e650141f057d3a32a67bc42bb9215e108c43171f3c9365fe5ac294',
    'scripts/friday_ordinary_install.py':'a271ae1941edbabebfd7359eef955d18c773c787542f989eb7c22635313b44d5',
}
PROJECT_QUALIFICATION_AFTER = {
    'plugins/friday_rework/host_runtime.py':'6435ccc10e8ea3f2b9a7fc1c639e5788f32ff18141344a6f58f0c5fcf68fd585',
    'plugins/friday_rework/user_worker_join.py':'41b560fd9c290cd7c07cbbe518e14767fde4fafb09a616778144ad6851bb5dd1',
    'scripts/worker_qualification.py':'3368b230ead0a1d371b8f8afb6a46298765d5832e9ef97fa3528876432ea92e1',
}
# This exact successor adds the installed worker helper closure. Source-only
# scripts remain in the reviewed project inventory and are never copied to home.
PROJECT_RUNTIME_SCHEMA = 'friday.ordinary-telegram-project-update.v3'
PROJECT_RUNTIME_NATIVE_FILES = 17682
PROJECT_RUNTIME_HISTORY_FILES = 422
PROJECT_INFERENCE_HELPER_SCHEMA = 'friday.ordinary-telegram-project-update.v4'
PROJECT_INFERENCE_HELPER = 'scripts/friday_ordinary_install.py'
PROJECT_INFERENCE_HELPER_BEFORE = '660e2901317ddd1c63f936c6157e043a6d2fcd0bdb49d1aaacce4d0e5fdbaa28'
PROJECT_INFERENCE_NATIVE_FILES = 17686
PROJECT_INFERENCE_HISTORY_FILES = 494
PROJECT_INFERENCE_INPUT_BEFORE = 'cbd86dd4da6febed50c38050150f66fba59bb8de71edbbc6798a66b1582d79b1'
PROJECT_INFERENCE_PREDECESSOR_INPUT = 'b0a7f22999b881b04a8ae1059d7d21feb562e7a2b2aa0958e87a686d375e0cc4'
PROJECT_INFERENCE_RECONCILIATION = 'preparation/ordinary-closed-reconciliation-native79-closed23-userbus-repair-20261016'
PROJECT_INFERENCE_RECONCILIATION_PINS = {
    PROJECT_INFERENCE_RECONCILIATION+'/intent.json':'9e3f99a9202c9e643ebadfe5178337c9b5aad16f89b73207cf466f1762195afd',
    PROJECT_INFERENCE_RECONCILIATION+'/committed.json':'dce9f69849dbf13378583b27b8de32d862cf0174b890aed07ad221b1ce223407',
    PROJECT_INFERENCE_RECONCILIATION+'/before/FRIDAY-INSTALL.json':'64a126decee4c29862ff1fdb118b52d92c9dcdae923a7d6ab5ed5e01442390d0',
}
PROJECT_RUNTIME_NEW = {
    'plugins/friday_rework/runtime_observers.py',
    'plugins/friday_rework/runtime_process.py',
    'plugins/friday_rework/runtime_containment.py',
    'plugins/friday_rework/runtime_primitives.py',
}
PROJECT_RUNTIME_BEFORE = {
    'plugins/friday_rework/host_runtime.py':'6435ccc10e8ea3f2b9a7fc1c639e5788f32ff18141344a6f58f0c5fcf68fd585',
    'plugins/friday_rework/user_worker_join.py':'41b560fd9c290cd7c07cbbe518e14767fde4fafb09a616778144ad6851bb5dd1',
    'plugins/friday_rework/a0_bootstrap.py':'16ff14e9a84d9786f8996d4e6ca041747daf4fa312a3bb01a5660025ead2a478',
    'scripts/worker_qualification.py':'3368b230ead0a1d371b8f8afb6a46298765d5832e9ef97fa3528876432ea92e1',
    'scripts/dsh_prepare.py':'d1a67a444530aaac43a6c86948fd26ef56fe272d8935282ea2c1f800f4417fa0',
    'scripts/install_containment.py':'e8a877bd2838df69a0bdf6ecde9dcec69887115f3b1043a150b58589949a643b',
    'scripts/friday_install.py':'882666c21807c7a243e91b3849302d0757f7ddc358fa1acbe1aabc2c712f9964',
    'scripts/friday_ordinary_install.py':'92b6bb29eb52fccaf6b3133b493372c23e918b28f13bdba2d200dd502831fb25',
}
# Frozen helper-closure candidate; the updater itself is pinned by current_input.
PROJECT_RUNTIME_AFTER = {
    'plugins/friday_rework/a0_bootstrap.py':'f64bf2427f2006417169a284293622c0cab31ff088537f995e2c512edd07251a',
    'plugins/friday_rework/host_runtime.py':'3855f0495dbd2547d96d44110a51cb0838e002f0e0bf4b3dac3f95077c049d7b',
    'plugins/friday_rework/runtime_containment.py':'41ba7c6853dadae5021fa6fee4520dfe4e620187d726ba4fb6693bb0df1953f7',
    'plugins/friday_rework/runtime_observers.py':'17d56e263a52610bb3872f9f97f5d5a95ebf2eaf9b9c0ac5faefacc33f5e7f6c',
    'plugins/friday_rework/runtime_primitives.py':'3a068a65fe6fbea085a07b50a37fcaddfe62fe5ba524be4de46d282321379fe6',
    'plugins/friday_rework/runtime_process.py':'edad3f51e9a8b180173eb1c17f1bde065eefc317e4ab3ceeb8ea9ef5499b5c6f',
    'plugins/friday_rework/user_worker_join.py':'e0dab0f3a21c3ac3ce841aa6d8176d4fd60ea4c57f6b633cdc0e2091e3e55358',
    'scripts/dsh_prepare.py':'f5c40cf793965f7c414256eb378bb9c2e6b61c0cbb71ae111276e61c8d32c663',
    'scripts/friday_install.py':'2685a9be13b27e5aab91c9502e8ca813d7aadf8ba23aba3dd70d9c4b35d7f03b',
    'scripts/install_containment.py':'e877f76a1e4b373bf1fecf083aef9c2af24befba2c55b19b25bfd65ecbbad3f1',
    'scripts/worker_qualification.py':'5af4c0b735da3c392c3adb12d6f637307764877dfa238cd09b0bd01518053dee',
}
PROJECT_DSH = 'plugins/friday_rework/adapters/dsh.py'
PROJECT_POLICY = 'config/apparmor/friday-dsh-native-v1'
PROJECT_DSH_BEFORE = 'ae00308381e976dd0c7130901979f6dc1bac1d84f9e25cc49fbc7bde1408a066'
PROJECT_AFTER = {
    PROJECT_DSH:'b055c33ece99f669ec2a185f8227ffa70eea54b1afb696384670641ccd2c0554',
    PROJECT_POLICY:'5a400147afe52cf1ce879112ca41f6d2ff5718032971f438f7e5461b02e4176b',
    'scripts/friday_start.py':'19547c818e52ead58e824baf3e115f4b8fa1fdc07f5e938dbe7198a8dde47406',
    'scripts/friday_native.py':'ef647de600903e70feb3ec4a3b4d907e1c6907843f737de1519ba5e7b35b43f4',
}


def project_update_inputs(request, budget):
    """Exact project-only successors; no donor source layer is introduced."""
    f = api()
    fields = {'schema','seconds','home','previous_input','current_input','marker','source_receipt',
        'stamp','configuration','profile','launcher','credential_files','native_unit',
        'transaction_history','predecessor_update'}
    f.require(type(request) is dict and set(request) == fields
        and request['schema'] in (PROJECT_UPDATE_SCHEMA, PROJECT_QUALIFICATION_SCHEMA,
            PROJECT_RUNTIME_SCHEMA, PROJECT_INFERENCE_HELPER_SCHEMA)
        and type(request['seconds']) is int and 30 <= request['seconds'] <= 180,
        'ordinary_project_explicit_request_required')
    home = f.directory(f.canonical(request['home'])); source = f.directory(home/'hermes-agent')
    f.require(os.environ.get('HERMES_HOME') == str(home), 'ordinary_update_exact_environment_required')
    paths = {name:budget.call(f.pin,request[name]) for name in
        ('previous_input','current_input','marker','source_receipt','stamp','configuration',
         'profile','launcher','native_unit','predecessor_update')}
    for name,path in {'marker':home/f.MARKER,'source_receipt':home/'hermes-agent.source.json',
        'stamp':source/'install-stamp.json','configuration':home/'config.yaml',
        'profile':home/'FRIDAY-PROFILE.json','launcher':source/'.hermes/bin/hermes'}.items():
        f.require(paths[name] == path, 'ordinary_update_exact_installed_inputs_required')
    previous = f.read_json(paths['previous_input']); current = f.read_json(paths['current_input'])
    old = previous['project_files']; new = current['project_files']
    f.require(request['previous_input'] != request['current_input']
        and {k:v for k,v in previous.items() if k != 'project_files'} ==
            {k:v for k,v in current.items() if k != 'project_files'}
        and current['home'] == str(home) and current['product']['runtime'] == {'enabled':False},
        'ordinary_update_operational_settings_changed')
    qualification = request['schema'] == PROJECT_QUALIFICATION_SCHEMA
    runtime = request['schema'] == PROJECT_RUNTIME_SCHEMA
    inference_helper = request['schema'] == PROJECT_INFERENCE_HELPER_SCHEMA
    if inference_helper:
        f.require(len(old) == 231 and set(new) == set(old)
            and old.get(PROJECT_INFERENCE_HELPER) == PROJECT_INFERENCE_HELPER_BEFORE
            and {n for n in old if old[n] != new[n]} == {PROJECT_INFERENCE_HELPER}
            and type(current['product']['runtime']['enabled']) is bool,
            'ordinary_project_exact_inference_helper_delta_required')
    elif runtime:
        allowed = set(PROJECT_RUNTIME_BEFORE)
        f.require(set(PROJECT_RUNTIME_AFTER) == (allowed-{'scripts/friday_ordinary_install.py'}) | PROJECT_RUNTIME_NEW
            and len(old) == 223 and set(new) == set(old) | PROJECT_RUNTIME_NEW
            and not (set(old) & PROJECT_RUNTIME_NEW)
            and all(old.get(n) == h for n,h in PROJECT_RUNTIME_BEFORE.items())
            and all(new.get(n) == h and new[n] != old.get(n)
                for n,h in PROJECT_RUNTIME_AFTER.items())
            and new['scripts/friday_ordinary_install.py'] != old['scripts/friday_ordinary_install.py']
            and all(new[n] == h for n,h in old.items() if n not in allowed)
            and all(old.get(n) == h for n,h in PROJECT_AFTER.items()),
            'ordinary_project_only_reviewed_runtime_delta_required')
    elif qualification:
        allowed = set(PROJECT_QUALIFICATION_BEFORE)
        f.require(len(old) == 223 and set(new) == set(old)
            and all(old.get(n) == h for n,h in PROJECT_QUALIFICATION_BEFORE.items())
            and all(new.get(n) == h and new[n] != old[n]
                for n,h in PROJECT_QUALIFICATION_AFTER.items())
            and new['scripts/friday_ordinary_install.py'] != old['scripts/friday_ordinary_install.py']
            and all(new[n] == h for n,h in old.items() if n not in allowed)
            and all(old.get(n) == h for n,h in PROJECT_AFTER.items()),
            'ordinary_project_only_reviewed_delta_required')
    else:
        allowed = {PROJECT_DSH,'scripts/friday_ordinary_install.py','scripts/friday_start.py','scripts/friday_native.py'}
        f.require(len(old) == 222 and set(new) == set(old) | {PROJECT_POLICY}
            and PROJECT_POLICY not in old and old.get(PROJECT_DSH) == PROJECT_DSH_BEFORE
            and all(new.get(name) == sha for name,sha in PROJECT_AFTER.items())
            and all(new[name] == sha for name,sha in old.items() if name not in allowed)
            and old[PROJECT_DSH] != new[PROJECT_DSH], 'ordinary_project_only_reviewed_delta_required')
    _,donors = budget.call(f.spec_checked,current,cli_only=True)
    marker = f.read_json(paths['marker']); receipt = f.read_json(paths['source_receipt'])
    f.require(marker.get('schema') == f.SCHEMA and marker.get('completion_stage') == 'TELEGRAM_ORDINARY'
        and marker.get('state') == 'INSTALLED_TEMPLATE_INCOMPLETE'
        and marker.get('home') == str(home) and marker.get('source') == str(source)
        and marker.get('runtime_ready') is False
        and marker.get('worker_state') == 'BOTH_WORKERS_PREPARATION_PENDING'
        and marker.get('input_sha256') == request['previous_input']['sha256']
        and marker.get('source_receipt_sha256') == request['source_receipt']['sha256']
        and len(receipt['layers']) == (79 if inference_helper else 77)
        and receipt['layers'][-1]['manifest'] == (SPARK_MULTIPASS_MANIFEST if inference_helper else DOCX_CREATION_MANIFEST),
        'ordinary_project_exact_source79_required' if inference_helper else 'ordinary_project_exact_source77_required')
    if inference_helper:
        f.require(len(receipt['files']) == PROJECT_INFERENCE_NATIVE_FILES
            and len(request['transaction_history']) == PROJECT_INFERENCE_HISTORY_FILES,
            'ordinary_project_exact_inference_inventory_required')
    elif runtime:
        f.require(len(receipt['files']) == PROJECT_RUNTIME_NATIVE_FILES
            and len(request['transaction_history']) == PROJECT_RUNTIME_HISTORY_FILES,
            'ordinary_project_exact_runtime_inventory_required')
    elif qualification:
        f.require(len(receipt['files']) == PROJECT_QUALIFICATION_NATIVE_FILES
            and len(request['transaction_history']) == PROJECT_QUALIFICATION_HISTORY_FILES,
            'ordinary_project_exact_qualification_inventory_required')
    budget.call(f.composition_checked,previous,source,receipt,donors['hermes'])
    budget.call(f.composition_checked,current,source,receipt,donors['hermes'])
    update_history(home,request['transaction_history'],request['predecessor_update'])
    predecessor = f.read_json(paths['predecessor_update'])
    if inference_helper:
        # The accepted archive-only reconciliation already admitted two helper
        # repairs after v33. Keep that completed transition and its old clocks;
        # it is ancestry to retain, never another recovery operation to execute.
        f.require(request['previous_input']['sha256'] == PROJECT_INFERENCE_INPUT_BEFORE
            and predecessor['current_input']['sha256'] == PROJECT_INFERENCE_PREDECESSOR_INPUT,
            'ordinary_project_exact_reconciled_input_required')
        for name,sha in PROJECT_INFERENCE_RECONCILIATION_PINS.items():
            f.pin({'path':str(home/name),'sha256':sha})
    f.require(predecessor.get('schema') == ('friday.ordinary-telegram-source-update.v33' if inference_helper else
        PROJECT_QUALIFICATION_SCHEMA if runtime else PROJECT_UPDATE_SCHEMA if qualification else
        'friday.ordinary-telegram-source-update.v31')
        and predecessor['home'] == str(home)
        and (inference_helper or predecessor['current_input'] == request['previous_input']),
        'ordinary_project_source79_predecessor_required' if inference_helper else 'ordinary_project_source77_predecessor_required')
    previous_tx = home/'preparation'/('ordinary-source-update-'+predecessor['previous_input']['sha256'])
    f.require(f.read_json(previous_tx/'committed.json')['source_receipt_sha256'] ==
        request['source_receipt']['sha256'], 'ordinary_update_predecessor_binding_changed')
    if qualification or runtime:
        f.require(f.read_json(previous_tx/'intent.json').get('project_only') is True
            and f.read_json(previous_tx/'committed.json').get('project_only') is True,
            'ordinary_project_exact_committed_project_predecessor_required')
    f.native_packages(source)
    from hermes_cli.friday_ordinary_gateway import check
    check(home,role=False)
    plugins = {n:p for n,p in old.items() if n.startswith('plugins/friday_rework/')}
    f.require(marker.get('plugin_files') == plugins, 'ordinary_update_installed_plugin_marker_changed')
    checked_plugin_inventory(home,plugins)
    f.require(all(f.digest(f.owned_file(home/name,private=True)) == sha
        for name,sha in marker['profile_files'].items() if name != 'config.yaml'), 'ordinary_update_profile_changed')
    credentials = request['credential_files']
    f.require(type(credentials) is dict and set(credentials) == {'.env','auth.json'},
        'ordinary_update_credential_pins_required')
    for name,ref in credentials.items():
        f.require(not os.path.lexists(home/name) if ref is None else f.pin(ref) == home/name,
            'ordinary_update_credential_pin_changed')
    tx = home/'preparation'/('ordinary-source-update-'+request['previous_input']['sha256'])
    f.require(not os.path.lexists(tx), 'ordinary_update_consumed_no_retry')
    return home,source,previous,current,marker,receipt,donors,tx


def project_update(request, request_path, budget):
    """Existing ordinary custody and journal, restricted to the reviewed installed plugin delta."""
    f = api(); home = f.directory(f.canonical(request['home']))
    fd = os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        home,source,previous,current,marker,receipt,donors,tx = project_update_inputs(request,budget)
        with stopped_consumers(home,request['native_unit'],budget) as native_prove, retained_build_lock(source) as build_prove:
            def prove(): native_prove(); build_prove(); budget.check()
            f.owned_file(request_path,private=True)
            request_state = update_file_state(request_path)
            f.require(request_state is not None and json.loads(request_state['data'],object_pairs_hook=f.unique) == request,
                'ordinary_update_request_changed')
            project_update_inputs(request,budget)
            expected_after = ({} if request['schema'] == PROJECT_INFERENCE_HELPER_SCHEMA else
                PROJECT_RUNTIME_AFTER if request['schema'] == PROJECT_RUNTIME_SCHEMA else
                PROJECT_QUALIFICATION_AFTER if request['schema'] == PROJECT_QUALIFICATION_SCHEMA else PROJECT_AFTER)
            plugin_names = sorted(n for n in expected_after if n.startswith('plugins/'))
            names = [*plugin_names,f.MARKER]
            saved = {name:update_file_state(home/name) for name in names}
            pins = {n:previous['project_files'].get(n) for n in plugin_names}
            pins[f.MARKER] = request['marker']['sha256']
            f.require(all((row is None and pins[name] is None) or (row is not None
                and row['mode'] in (0o600,0o644) and f.digest(row['data']) == pins[name])
                for name,row in saved.items()),
                'ordinary_update_beforeimage_changed')
            retained = {name:update_file_state(path) for name,path in {
                'source_receipt':home/'hermes-agent.source.json','stamp':source/'install-stamp.json',
                'configuration':home/'config.yaml','profile':home/'FRIDAY-PROFILE.json',
                'launcher':source/'.hermes/bin/hermes','native_unit':Path(request['native_unit']['path']),
                **{name:home/name for name in ('.env','auth.json')},
                **({name:home/name for name in PROJECT_INFERENCE_RECONCILIATION_PINS}
                    if request['schema'] == PROJECT_INFERENCE_HELPER_SCHEMA else {}),
            }.items()}
            f.require(all(state is not None and f.digest(state['data']) ==
                (PROJECT_INFERENCE_RECONCILIATION_PINS[name] if name in PROJECT_INFERENCE_RECONCILIATION_PINS
                 else request[name]['sha256'])
                for name,state in retained.items() if name not in ('.env','auth.json')),
                'ordinary_project_retained_pin_changed')
            for name in ('.env','auth.json'):
                ref = request['credential_files'][name]; state = retained[name]
                f.require((ref is None and state is None) or (ref is not None and state is not None
                    and f.digest(state['data']) == ref['sha256']), 'ordinary_update_credential_pin_changed')
            def unchanged():
                f.pin(request['previous_input']); f.pin(request['current_input'])
                budget.call(f.spec_checked,current,cli_only=True)
                for name,state in retained.items():
                    path = (Path(request['native_unit']['path']) if name == 'native_unit' else
                        source/'install-stamp.json' if name == 'stamp' else
                        source/'.hermes/bin/hermes' if name == 'launcher' else
                        home/'hermes-agent.source.json' if name == 'source_receipt' else
                        home/'config.yaml' if name == 'configuration' else
                        home/'FRIDAY-PROFILE.json' if name == 'profile' else home/name)
                    f.require(same_update_file(path,state),'ordinary_project_retained_file_changed')
                f.require(same_update_file(request_path,request_state),'ordinary_update_request_changed')
                update_history(home,request['transaction_history'],request['predecessor_update'])
                budget.call(f.composition_checked,current,source,receipt,donors['hermes'])
                prove()
            import copy
            updated = copy.deepcopy(marker)
            updated['input_sha256'] = request['current_input']['sha256']
            for name in plugin_names:
                updated['plugin_files'][name] = current['project_files'][name]
            updated['ordinary_gateway']['operator_entry'] = {'input':request['current_input'],
                'script':{'path':str(f.ROOT/'scripts/friday_native.py'),
                    'sha256':current['project_files']['scripts/friday_native.py']}}
            plugin_data = {n:f.owned_file(f.ROOT/n) for n in plugin_names}
            f.require(all(f.digest(data) == expected_after[n] for n,data in plugin_data.items()),
                'ordinary_update_worker_plugin_source_changed')
            unchanged()
            tx.mkdir(mode=0o700); before = tx/'before'; before.mkdir(mode=0o700)
            for name,row in saved.items():
                if row is not None:
                    private_parents(before,name); write(before/name,row['data'])
            write(tx/'intent.json',encoded({'schema':'friday.ordinary-telegram-source-update-transaction.v1',
                'state':'SOURCE_UPDATE_CONSUMED_NO_RETRY','project_only':True,
                'request_sha256':f.digest(request_state['data']),
                'before':{n:None if v is None else {'sha256':f.digest(v['data']),'mode':v['mode']}
                    for n,v in saved.items()}}),0o400)
            sync_directory(before); sync_directory(tx); sync_directory(tx.parent)
            owned = {}
            try:
                unchanged()
                for name,data in [*plugin_data.items(),(f.MARKER,encoded(updated))]:
                    prove(); publish_update_file(home/name,data,saved[name]['mode'] if saved[name] is not None else 0o600,saved[name],owned,name)
                from hermes_cli.friday_ordinary_gateway import check
                check(home,role=False); checked_plugin_inventory(home,updated['plugin_files'])
                unchanged()
                f.require(all(same_update_file(home/n,owned[n]) for n in names),
                    'ordinary_update_commit_ownership_changed')
                write(tx/'committed.json',encoded({'state':'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED',
                    'project_only':True,'previous_input':request['previous_input'],
                    'current_input':request['current_input'],'source_receipt_sha256':request['source_receipt']['sha256'],
                    'gateway_started':False,'workers_enabled':False}),0o400)
                sync_directory(tx)
                return {'state':'TELEGRAM_ORDINARY_PROJECT_UPDATED','ready':False,'gateway_started':False,
                    'workers_enabled':False,'full_release_accepted':False,'native_source_unchanged':True,
                    'source_receipt_sha256':request['source_receipt']['sha256']}
            except BaseException as original:
                try:
                    prove(); restore_update_files(home,saved,owned); unchanged()
                    write(tx/'rolled-back.json',encoded({'state':'ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY',
                        'project_only':True}),0o400); sync_directory(tx)
                except BaseException as restoration:
                    from scripts.dsh_prepare import StopUnconfirmed
                    f.remember_secondary(original,restoration)
                    raise StopUnconfirmed('ordinary project update restoration requires reconciliation') from original
                raise
    finally:
        os.close(fd)


def update(request, request_path, budget):
    """One finite committed-phase source update; original activation stays intact."""
    if type(request) is dict and request.get('schema') in (PROJECT_UPDATE_SCHEMA, PROJECT_QUALIFICATION_SCHEMA,
            PROJECT_RUNTIME_SCHEMA, PROJECT_INFERENCE_HELPER_SCHEMA):
        return project_update(request,request_path,budget)
    f = api(); home = f.directory(f.canonical(request['home']))
    fd = os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        home,source,previous,current,marker,receipt,manifest,donors,tx = update_inputs(request,budget)
        with stopped_consumers(home,request['native_unit'],budget) as native_prove, retained_build_lock(source) as build_prove:
            def prove(): native_prove(); build_prove()
            f.require(f.read_json(request_path) == request, 'ordinary_update_request_changed')
            # Recheck every explicit pin immediately before the source-only journal.
            update_inputs(request,budget)
            source85 = request['schema'] == 'friday.ordinary-telegram-source-update.v39'
            source84 = request['schema'] == 'friday.ordinary-telegram-source-update.v38'
            source83 = request['schema'] == 'friday.ordinary-telegram-source-update.v37'
            source82 = request['schema'] == 'friday.ordinary-telegram-source-update.v36'
            source81 = request['schema'] == 'friday.ordinary-telegram-source-update.v35'
            source80 = request['schema'] == 'friday.ordinary-telegram-source-update.v34'
            source79 = request['schema'] == 'friday.ordinary-telegram-source-update.v33'
            source78 = request['schema'] == 'friday.ordinary-telegram-source-update.v32'
            source77 = request['schema'] == 'friday.ordinary-telegram-source-update.v31'
            source76 = request['schema'] == 'friday.ordinary-telegram-source-update.v30'
            source75 = request['schema'] == 'friday.ordinary-telegram-source-update.v29'
            source74 = request['schema'] == 'friday.ordinary-telegram-source-update.v28'
            source73 = request['schema'] == 'friday.ordinary-telegram-source-update.v27'
            source72 = request['schema'] == 'friday.ordinary-telegram-source-update.v26'
            source71 = request['schema'] == 'friday.ordinary-telegram-source-update.v25'
            source70 = request['schema'] == 'friday.ordinary-telegram-source-update.v24'
            source69 = request['schema'] == 'friday.ordinary-telegram-source-update.v23'
            source68 = request['schema'] == 'friday.ordinary-telegram-source-update.v22'
            source67 = request['schema'] == 'friday.ordinary-telegram-source-update.v21'
            source66 = request['schema'] == 'friday.ordinary-telegram-source-update.v20'
            source65 = request['schema'] == 'friday.ordinary-telegram-source-update.v19'
            source64 = request['schema'] == 'friday.ordinary-telegram-source-update.v18'
            source63 = request['schema'] == 'friday.ordinary-telegram-source-update.v17'
            source62 = request['schema'] == 'friday.ordinary-telegram-source-update.v16'
            source61 = request['schema'] == 'friday.ordinary-telegram-source-update.v15'
            source60 = request['schema'] == 'friday.ordinary-telegram-source-update.v14'
            source59 = request['schema'] == 'friday.ordinary-telegram-source-update.v13'
            source58 = request['schema'] == 'friday.ordinary-telegram-source-update.v12'
            source57 = request['schema'] == 'friday.ordinary-telegram-source-update.v11'
            source56 = request['schema'] == 'friday.ordinary-telegram-source-update.v10'
            source55 = request['schema'] == 'friday.ordinary-telegram-source-update.v9'
            source54 = request['schema'] == 'friday.ordinary-telegram-source-update.v8'
            source53 = request['schema'] == 'friday.ordinary-telegram-source-update.v7'
            source52 = request['schema'] == 'friday.ordinary-telegram-source-update.v6'
            source51 = request['schema'] == 'friday.ordinary-telegram-source-update.v5'
            source50 = request['schema'] == 'friday.ordinary-telegram-source-update.v4'
            source49 = request['schema'] == 'friday.ordinary-telegram-source-update.v3'
            plugin_changes = sorted(FILE_TOOL_CONTRACT_PLUGIN_FILES if source81 else SPARK_REQUEST_BUDGET_PLUGIN_FILES if source80 else SPARK_MULTIPASS_PLUGIN_FILES if source79 else PRIVACY_EFFECT_PLUGIN_FILES if source78 else CONTEXT_SELF_PLUGIN_FILES if source71 else TOOL_METADATA_PLUGIN_FILES if source65 else WORKER_TOOLS_PLUGIN_FILES if source63 else BROWSER_PLUGIN_FILES if source55 else WORKER_ATTACH_PLUGIN_FILES) if source81 or source80 or source79 or source78 or source71 or source65 or source63 or source55 or source49 else []
            names = [f.MARKER,'hermes-agent.source.json','hermes-agent/install-stamp.json'] + [
                'hermes-agent/'+row['path'] for row in manifest['files']] + plugin_changes
            new_files = SPARK_REQUEST_BUDGET_NEW_FILES if source80 else SPARK_MULTIPASS_NEW_FILES if source79 else PRIVACY_EFFECT_NEW_FILES if source78 else DOCX_CREATION_NEW_FILES if source77 else FILE_REVISION_NEW_FILES if source75 else WORKER_TOOLS_FILES if source63 else BROWSER_NEW_FILES if source55 else set()
            absent = {'hermes-agent/'+name for name in new_files}
            saved = ({name:update_file_state(home/name) for name in names}
                if source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85 else {name:{'data':f.owned_file(home/name),
                    'mode':stat.S_IMODE((home/name).stat().st_mode)} for name in names})
            f.require(all(row is None or row['mode'] in (0o600,0o644) for row in saved.values()),
                'ordinary_update_beforeimage_mode_required')
            if source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85:
                before_pins = {f.MARKER:request['marker']['sha256'],
                    'hermes-agent.source.json':request['source_receipt']['sha256'],
                    'hermes-agent/install-stamp.json':request['stamp']['sha256']}
                before_pins.update({'hermes-agent/'+row['path']:row['before_sha256']
                    for row in manifest['files'] if row['path'] not in new_files})
                before_pins.update({name:previous['project_files'][name] for name in plugin_changes})
                f.require(all((row is None) == (name in absent) and
                    (row is None or f.digest(row['data']) == before_pins[name])
                    for name,row in saved.items()), 'ordinary_update_beforeimage_changed')
            import copy
            receipt = copy.deepcopy(receipt)
            for row in manifest['files']:
                receipt['files'][row['path']] = {k:row[k] for k in ('sha256','bytes','mode')}
            manifest_name = WEB_RUNTIME_HISTORY_MANIFEST if source85 else FILE_REPLY_CONTEXT_MANIFEST if source84 else COMBINED_INPUT_MANIFEST if source83 else WEB_INPUT_MANIFEST if source82 else FILE_TOOL_CONTRACT_MANIFEST if source81 else SPARK_REQUEST_BUDGET_MANIFEST if source80 else SPARK_MULTIPASS_MANIFEST if source79 else PRIVACY_EFFECT_MANIFEST if source78 else DOCX_CREATION_MANIFEST if source77 else DOCUMENT_EXTRACTION_MANIFEST if source76 else FILE_REVISION_MANIFEST if source75 else TOOL_RESULT_CONTEXT_MANIFEST if source74 else DSH_SANDBOX_MANIFEST if source73 else CURRENT_TURN_MANIFEST if source72 else CONTEXT_SELF_MANIFEST if source71 else PRIVATE_REPLY_MANIFEST if source70 else PROMPT_PRIVACY_MANIFEST if source69 else MEMORY_SCOPE_MANIFEST if source68 else FIRST_CONTACT_COPY_MANIFEST if source67 else INLINE_PRIVACY_MANIFEST if source66 else TOOL_METADATA_MANIFEST if source65 else PUBLIC_SURFACE_MANIFEST if source64 else WORKER_TOOLS_MANIFEST if source63 else DIALOGUE_CONTINUATION_MANIFEST if source62 else FIRST_CONTACT_STATE_MANIFEST if source61 else TURN_SCOPE_MANIFEST if source60 else ADMIN_STARTUP_MANIFEST if source59 else INTERACTION_SCOPE_MANIFEST if source58 else PROFILE_RUNTIME_MANIFEST if source57 else BROWSER_GATEWAY_MANIFEST if source56 else BROWSER_MANIFEST if source55 else SEARCH_RECOVERY_MANIFEST if source54 else WEB_OUTPUT_MANIFEST if source53 else WEB_CONTINUATION_MANIFEST if source52 else ADMIN_BROADCAST_MANIFEST if source51 else ADMIN_RESTART_MANIFEST if source50 else FILE_CONTINUATION_MANIFEST if source49 else PRIVATE_STATE_MANIFEST if request['schema'].endswith('.v2') else UPDATE_MANIFEST
            receipt['layers'].append({'manifest':manifest_name,
                'manifest_sha256':current['project_files'][manifest_name],'patch_sha256':manifest['patch_sha256']})
            stamp = f.read_json(source/'install-stamp.json')
            stamp['fridaySource'] = {'baseTree':receipt['base_tree'],'layers':receipt['layers']}
            receipt_data = encoded(receipt); receipt_sha = f.digest(receipt_data)
            updated = copy.deepcopy(marker)
            updated['input_sha256'] = request['current_input']['sha256']
            updated['source_receipt_sha256'] = receipt_sha
            if source81 or source80 or source79 or source78 or source71 or source65 or source63 or source55 or source49:
                updated['plugin_files'] = {n:p for n,p in current['project_files'].items() if n.startswith('plugins/friday_rework/')}
            updated['ordinary_gateway']['source_receipt_sha256'] = receipt_sha
            updated['ordinary_gateway']['operator_entry'] = {'input':request['current_input'],
                'script':{'path':str(f.ROOT/'scripts/friday_native.py'),
                    'sha256':current['project_files']['scripts/friday_native.py']}}
            publication = [('hermes-agent.source.json',receipt_data),
                ('hermes-agent/install-stamp.json',encoded(stamp)),(f.MARKER,encoded(updated))]
            after = {name:f.digest(data) for name,data in publication}
            after.update({'hermes-agent/'+row['path']:row['sha256'] for row in manifest['files']})
            plugin_data = {name:f.owned_file(f.ROOT/name) for name in plugin_changes}
            f.require(all(f.digest(data) == current['project_files'][name] for name,data in plugin_data.items()),
                'ordinary_update_worker_plugin_source_changed')
            after.update({name:f.digest(data) for name,data in plugin_data.items()})
            tx.mkdir(mode=0o700); before = tx/'before'; before.mkdir(mode=0o700)
            for name,row in saved.items():
                if row is None: continue
                target = before/name; private_parents(before,name)
                write(target,row['data'])
            write(tx/'intent.json',encoded({'schema':'friday.ordinary-telegram-source-update-transaction.v1',
                'state':'SOURCE_UPDATE_CONSUMED_NO_RETRY','request_sha256':f.digest(f.owned_file(request_path,private=True)),
                **({'new_directories':['hermes-agent/config']} if source63 else {}),
                'before':{name:({'absent':True} if row is None else {'sha256':f.digest(row['data']),'mode':row['mode']}) for name,row in saved.items()}}))
            sync_directory(before); sync_directory(tx); sync_directory(tx.parent)
            owned = {}; created_directory = None
            def directory_custody():
                if created_directory is not None:
                    path = source/'config'; f.directory(path)
                    info = path.lstat()
                    f.require(tuple(getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_mode')) == created_directory
                        and {p.name for p in path.iterdir()} <= {'RESEARCH.md'},
                        'ordinary_update_directory_ownership_changed')
            try:
                prove()
                if source63:
                    # Exact absent parent belongs to this additive layer only.
                    # Never adopt an existing directory or follow a symlink.
                    (source/'config').mkdir(mode=0o700)
                    info = (source/'config').lstat()
                    created_directory = tuple(getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_mode'))
                    directory_custody(); sync_directory(source)
                from scripts.dsh_prepare import run
                env = f.clean_environment(home); env['GIT_CEILING_DIRECTORIES'] = str(source.parent)
                patch_root = source
                if source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85:
                    # Git mutates only our private staging tree. Actual source
                    # publication records the precise created inode before rename/link.
                    patch_root = tx/'after'; patch_root.mkdir(mode=0o700)
                    for row in manifest['files']:
                        name = 'hermes-agent/'+row['path']
                        private_parents(patch_root,row['path'])
                        if saved[name] is not None:
                            write(patch_root/row['path'],saved[name]['data'],saved[name]['mode'])
                for checking in (True,False):
                    command = ['git','--no-optional-locks','apply','--whitespace=nowarn']
                    if checking: command.append('--check')
                    command.append(str(f.ROOT/manifest['patch']))
                    run(command,patch_root,timeout=min(20,budget.check(reserve=1)),env=env,deadline=budget.deadline)
                for row in manifest['files']:
                    data = f.owned_file(patch_root/row['path'])
                    f.require(f.digest(data) == row['sha256'] and len(data) == row['bytes'],
                        'ordinary_update_patch_output_changed')
                    if source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85: (patch_root/row['path']).chmod(0o600)
                if source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85:
                    for row in manifest['files']:
                        name = 'hermes-agent/'+row['path']; budget.check(); prove(); directory_custody()
                        publish_update_file(home/name,f.owned_file(patch_root/row['path']),
                            0o644,saved[name],owned,name)
                for name,data in plugin_data.items():
                    # Same owned exact-byte private publication used by the native installer.
                    f.require(f.digest(f.owned_file(home/name,private=True)) == f.digest(saved[name]['data']),
                        'ordinary_update_worker_plugin_preimage_changed')
                    if source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85: publish_update_file(home/name,data,saved[name]['mode'],saved[name],owned,name)
                    else: replace(home/name,data,saved[name]['mode'])
                if source49 or source50 or source51 or source52 or source53 or source54 or source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85:
                    checked_plugin_inventory(home, updated['plugin_files'])
                budget.call(f.composition_checked,current,source,receipt,donors['hermes'])
                for name,data in publication:
                    budget.check()
                    if source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85: publish_update_file(home/name,data,saved[name]['mode'],saved[name],owned,name)
                    else: replace(home/name,data,saved[name]['mode'])
                # The ordinary binding and complete native source identity must
                # agree before the update can commit. No service is launched.
                from hermes_cli.friday_ordinary_gateway import check
                if source56:
                    check_browser_gateway(home,source,manifest,budget,staged=False)
                else:
                    check(home,role=False)
                if source49 or source50 or source51 or source52 or source53 or source54 or source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85:
                    checked_plugin_inventory(home, updated['plugin_files'])
                update_history(home,request['transaction_history'],request.get('predecessor_update'),request.get('keyless_recovery'),request.get('inference_rebind')); prove(); budget.check()
                if source82 or source83 or source84 or source85:
                    checked_source82_retained(home,request)
                    budget.call(f.spec_checked,current,cli_only=True)
                if source81:
                    checked_source81_retained(home,request,after=True)
                    budget.call(f.spec_checked,current,cli_only=True)
                if source80:
                    rebound = f.read_json(f.pin(request['inference_rebind']))
                    after_rebind = f.read_json(home/'preparation'/('ordinary-inference-rebind-'+
                        rebound['previous_input']['sha256'])/'committed.json')['after']
                    for name,sha in after_rebind.items():
                        if name != f.MARKER: f.pin({'path':str(home/name),'sha256':sha})
                    for name in ('previous_input','current_input','configuration','profile','launcher','native_unit'):
                        f.pin(request[name])
                    for name,ref in request['credential_files'].items():
                        f.require(not os.path.lexists(home/name) if ref is None else f.pin(ref) == home/name,
                            'ordinary_update_credential_pin_changed')
                    for name,sha in PROJECT_INFERENCE_RECONCILIATION_PINS.items():
                        f.pin({'path':str(home/name),'sha256':sha})
                    budget.call(f.spec_checked,current,cli_only=True)

                if source57:
                    budget.call(checked_worker_declaration_publication,home,request,
                        f.read_json(f.pin(request['predecessor_update'])),marker)
                if source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85:
                    f.require(all(name in owned and same_update_file(home/name,owned[name]) for name in names),
                        'ordinary_update_commit_ownership_changed')
                directory_custody()
                write(tx/'committed.json',encoded({'state':'SOURCE_UPDATED_NOT_RUNTIME_ACCEPTED',
                    'previous_input':request['previous_input'],'current_input':request['current_input'],
                    'source_receipt_sha256':receipt_sha,'gateway_started':False,'workers_enabled':False}))
                sync_directory(tx)
                return {'state':'TELEGRAM_ORDINARY_SOURCE_UPDATED','ready':False,'gateway_started':False,
                    'workers_enabled':False,'full_release_accepted':False,'source_receipt_sha256':receipt_sha}
            except BaseException as original:
                try:
                    prove(); directory_custody()
                    if source55 or source56 or source57 or source58 or source59 or source60 or source61 or source62 or source63 or source64 or source65 or source66 or source67 or source68 or source69 or source70 or source71 or source72 or source73 or source74 or source75 or source76 or source77 or source78 or source79 or source80 or source81 or source82 or source83 or source84 or source85:
                        restore_update_files(home,saved,owned)
                        if created_directory is not None:
                            directory_custody()
                            (source/'config').rmdir(); sync_directory(source)
                    else:
                        # Unknown concurrent bytes are never overwritten by rollback.
                        f.require(all(f.digest(f.owned_file(home/name)) in
                            {f.digest(row['data']),after[name]} for name,row in saved.items()),
                            'ordinary_update_restore_ownership_changed')
                        # Restore only this transaction's exact Native/plugin/metadata beforeimages.
                        for name,row in reversed(list(saved.items())):
                            replace(home/name,row['data'],row['mode'])
                        f.require(all(f.digest(f.owned_file(home/name)) == f.digest(row['data'])
                            and stat.S_IMODE((home/name).stat().st_mode) == row['mode'] for name,row in saved.items()),
                            'ordinary_update_restore_failed')
                    update_history(home,request['transaction_history'],request.get('predecessor_update'),request.get('keyless_recovery'),request.get('inference_rebind'))
                    write(tx/'rolled-back.json',encoded({'state':'ROLLED_BACK_OWN_SOURCE_ONLY_NO_RETRY'}))
                    sync_directory(tx)
                except BaseException as restoration:
                    from scripts.dsh_prepare import StopUnconfirmed
                    f.remember_secondary(original,restoration)
                    raise StopUnconfirmed('ordinary source update restoration requires reconciliation') from original
                raise
    finally:
        os.close(fd)


def start(value,input_path,input_hash,budget):
    """Re-exec the exact native PM generation for the ordinary service handoff."""
    f = api()
    home,donors = budget.call(f.spec_checked,value,cli_only=True)
    marker = budget.call(f.read_json,home/f.MARKER)
    f.require(marker.get('completion_stage') == 'TELEGRAM_ORDINARY'
        and marker.get('input_sha256') == input_hash
        and f.digest(f.owned_file(input_path,private=True)) == input_hash,
        'ordinary_current_installation_required')
    source = home/'hermes-agent'
    f.composition_checked(value,source,f.read_json(home/'hermes-agent.source.json'),donors['hermes'])
    from scripts.install_containment import Containment
    custody = Containment(value['containment'],budget,f.clean_environment(home))
    selected = custody.run([value['bootstrap_python']['path'],'-B','-c',
        'from pm.environments import project_python;from pathlib import Path;print(project_python(Path.cwd()))'],
        source,timeout=15)[0]
    f.require(Path(selected).is_absolute() and Path(selected).is_file(),'native_pm_python_missing')
    budget.check()
    os.execve(selected,[selected,'-B',str(f.ROOT/'scripts/friday_native.py'),'start-telegram',
        '--input',str(input_path),'--deadline',str(budget.deadline)],f.clean_environment(home))


def rollback(request,budget):
    """Restore this transaction only after native stop/uninstall is proved.

    Product/user/session data are retained. Unknown service ownership or changed
    beforeimages refuse restoration; this is never a gateway stop/retry command.
    """
    f=api()
    f.require(type(request) is dict and set(request)=={'schema','seconds','home','current_input'}
        and request['schema']=='friday.ordinary-telegram-rollback.v1'
        and type(request['seconds']) is int and 30<=request['seconds']<=180,'ordinary_rollback_request_required')
    home=f.directory(f.canonical(request['home']));source=home/'hermes-agent'
    value=f.read_json(f.pin(request['current_input']));f.spec_checked(value,cli_only=True)
    marker=f.read_json(home/f.MARKER)
    f.require(marker.get('completion_stage')=='TELEGRAM_ORDINARY'
        and marker.get('input_sha256')==request['current_input']['sha256'],'ordinary_rollback_current_source_required')
    donors={r['id']:r for r in f.read_json(f.pin(value['sources_lock']))['repositories']}
    f.composition_checked(value,source,f.read_json(home/'hermes-agent.source.json'),donors['hermes'])
    f.native_packages(source)
    from gateway import host_rendezvous as hr
    from hermes_cli import gateway as gw
    f.require(not gw.get_systemd_unit_path(system=False).exists()
        and not gw.get_systemd_unit_path(system=True).exists()
        and hr.read_record(hr.ROLE_GATEWAY,include_stale=True) is None
        and not gw.find_gateway_pids(),'ordinary_rollback_native_stop_and_uninstall_required')
    tx=home/TRANSACTION;before=tx/'before';intent=f.read_json(tx/'intent.json')
    committed=f.read_json(tx/'committed.json')
    f.require(committed['state']=='SOURCE_ACTIVATED_NOT_RUNTIME_ACCEPTED'
        and not os.path.lexists(tx/'source-rollback.intent.json'),'ordinary_rollback_once_required')
    manifest=f.read_json(f.ROOT/MANIFEST)
    expected={'FRIDAY-INSTALL.json','hermes-agent.source.json','config.yaml','hermes-agent/install-stamp.json',
              'plugins/friday_rework/onboarding.py'}|{'hermes-agent/'+r['path'] for r in manifest['files'] if not r['new_file']}
    f.require(set(intent['before'])==expected and intent['new_files']==[r['path'] for r in manifest['files'] if r['new_file']],
        'ordinary_rollback_scope_changed')
    for name,row in intent['before'].items():
        f.require(f.digest(f.owned_file(before/name,private=True))==row['sha256'], 'ordinary_rollback_beforeimage_changed')
    fd=os.open(home,os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        budget.check()
        rollback_before=tx/'rollback-before';rollback_before.mkdir(mode=0o700)
        retained={}
        for name in ('config.yaml','FRIDAY-INSTALL.json'):
            raw=f.owned_file(home/name,private=True);write(rollback_before/name,raw);retained[name]={'path':str(rollback_before/name),'sha256':f.digest(raw)}
        write(tx/'source-rollback.intent.json',encoded({'state':'CONSUMED_SOURCE_ROLLBACK','retained_current_configuration':retained}))
        for row in manifest['files']:
            if row['new_file']:
                budget.check();(source/row['path']).unlink()
        for name,row in intent['before'].items():
            if name==f.MARKER:continue
            budget.check();replace(home/name,f.owned_file(before/name,private=True),row['mode'])
        row=intent['before'][f.MARKER];replace(home/f.MARKER,f.owned_file(before/f.MARKER,private=True),row['mode'])
        f.require(all(f.digest(f.owned_file(home/name))==row['sha256'] for name,row in intent['before'].items()),'ordinary_rollback_verification_failed')
        write(tx/'source-rollback.done.json',encoded({'state':'SOURCE_ROLLED_BACK','runtime_data_retained':True}))
        return {'state':'ORDINARY_SOURCE_ROLLED_BACK','ready':False,'runtime_data_retained':True}
    finally:os.close(fd)


FIRST_CONTACT_CONFIG_SUFFIX = b'onboarding:\n  seen:\n    profile_build_offered: true\n'


def first_contact_recovery_inputs(request, home, source, *, restored=False):
    """Validate original admission without admitting the known-invalid config.

    The exception is one byte-exact native append. No receipt, access generation,
    root policy or ordinary profile checker is relaxed or rewritten.
    """
    f = api()
    from hermes_cli import friday_user_scope as user
    from hermes_cli import friday_product_access as access
    from hermes_cli.friday_ordinary_gateway import check
    from hermes_cli.plugins_state import _plugin_data_namespace
    from hermes_yaml import safe_load
    refs = ('installed_input','root_marker','source_receipt','stamp','root_configuration',
            'root_profile','native_unit','onboarding','user_marker','configuration','backup','access_state')
    paths = {}
    for name in refs:
        ref = request[name]
        # The BAD pin is intentionally replaced only after committed publication.
        paths[name] = f.canonical(ref['path']) if restored and name == 'configuration' else f.pin(ref)
        f.owned_file(paths[name],private=name not in ('stamp','source_receipt','native_unit'))
        mode = stat.S_IMODE(paths[name].stat().st_mode)
        f.require(mode in ((0o400,0o600) if name == 'installed_input' else (0o600,0o644) if name in ('stamp','source_receipt','native_unit') else (0o600,)),
            'ordinary_recovery_input_mode_required')
    profile = access.profile_name(request['profile'])
    f.require(profile != 'default', 'ordinary_recovery_named_profile_required')
    f.directory(home/'profiles')
    profile_home = f.directory(home/'profiles'/profile)
    for name,path in {'root_marker':home/f.MARKER,'source_receipt':home/'hermes-agent.source.json',
        'stamp':source/'install-stamp.json','root_configuration':home/'config.yaml',
        'root_profile':home/'FRIDAY-PROFILE.json','onboarding':profile_home/user.ONBOARDING,
        'user_marker':profile_home/user.MARKER,'configuration':profile_home/'config.yaml',
        'access_state':home/'plugin-data'/_plugin_data_namespace('friday_rework','')/'state.json'}.items():
        f.require(paths[name] == path,'ordinary_recovery_exact_paths_required')
    backup = paths['backup']
    # Native mkdir uses0755 or0775 beneath the already-checked admitted0700
    # home. That private ancestor prevents group access; backup files stay0600.
    for parent in (profile_home/'backups',profile_home/'backups/config'):
        f.canonical(str(parent)); info = parent.lstat()
        f.require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) in (0o700,0o755,0o775),
            'ordinary_recovery_owned_native_backup_directory_required')
    f.require(backup.parent == profile_home/'backups/config'
        and backup.name.startswith('config.yaml.good.') and len(backup.name) > len('config.yaml.good.'),
        'ordinary_recovery_native_backup_required')
    original = f.read_json(paths['installed_input']); marker = f.read_json(paths['root_marker'])
    receipt = f.read_json(paths['source_receipt']); stamp = f.read_json(paths['stamp'])
    f.require(original.get('home') == str(home) and marker.get('home') == str(home)
        and marker.get('source') == str(source) and marker.get('input_sha256') == request['installed_input']['sha256']
        and marker.get('source_receipt_sha256') == request['source_receipt']['sha256']
        and stamp.get('fridaySource',{}).get('baseTree') == receipt.get('base_tree')
        and stamp.get('fridaySource',{}).get('layers') == receipt.get('layers'),
        'ordinary_recovery_original_source_binding_required')
    # Root-only checker retains its original source/credential/history/route checks.
    check(home,role=False)
    # Root check already validates the policy. Read exact pinned raw YAML here:
    # native settings()/load_config_readonly() may initialize a home skeleton.
    root_cfg = safe_load(f.owned_file(paths['root_configuration'],private=True))
    settings = root_cfg['plugins']['entries']['friday_rework']['settings']
    policy = settings['user_isolation']; accounts = settings['product_access']['accounts']
    binding = request['binding']
    f.require(type(binding) is dict and binding.get('runtime_profile') == profile
        and binding.get('platform') == 'telegram' and policy is not None
        and [r for r in policy['bindings'] if r['runtime_profile'] == profile] == [binding],
        'ordinary_recovery_original_binding_required')
    principal = tuple(binding[k] for k in ('platform','transport_profile','account_id','user_id'))
    key = access.principal_id(*principal)
    f.require(len([r for r in accounts if tuple(r[k] for k in
        ('platform','transport_profile','account_id')) == principal[:3] and profile in r['runtime_profiles']]) == 1,
        'ordinary_recovery_original_account_required')
    state = f.read_json(paths['access_state'])
    admitted = access.validate_access(state[access.KEY])['users'].get(key)
    f.require(admitted is not None and admitted['enabled'] is True and admitted['role'] == 'user'
        and tuple(admitted[k] for k in ('platform','transport_profile','account_id','user_id')) == principal
        and admitted.get('generation') == request['generation'], 'ordinary_recovery_original_access_required')
    onboarding = f.read_json(paths['onboarding']); user_marker = f.read_json(paths['user_marker'])
    info = profile_home.stat()
    f.require(set(onboarding) == {'schema','binding_sha256','config_sha256','soul_sha256',
        'required_secrets','directory_identity','template','authorization_home'}
        and onboarding['schema'] == 'friday.onboarding.v1' and onboarding['authorization_home'] == str(home)
        and onboarding['directory_identity'] == [info.st_dev,info.st_ino]
        and onboarding['binding_sha256'] == user._fingerprint(binding)
        and onboarding['config_sha256'] == request['backup']['sha256'],
        'ordinary_recovery_original_receipt_required')
    f.require(user_marker == {'schema':'friday.user-home.v1','principal':key,'profile':profile,
        'binding_sha256':user._fingerprint(binding),'onboarding_sha256':request['onboarding']['sha256']},
        'ordinary_recovery_original_marker_required')
    f.require(f.digest(f.owned_file(profile_home/'SOUL.md',private=True)) == onboarding['soul_sha256'],
        'ordinary_recovery_original_soul_required')
    from agent.secret_scope import load_env_file
    names = onboarding['required_secrets']; f.owned_file(profile_home/'.env',private=True)
    f.require(type(names) is list and bool(names) and all(type(n) is str for n in names),
        'ordinary_recovery_original_secret_scope_required')
    values = load_env_file(profile_home/'.env')
    f.require(all(values.get(n) for n in names),'ordinary_recovery_original_secrets_required')
    before = update_file_state(paths['configuration']); old = f.owned_file(backup,private=True)
    f.require(before is not None and before['mode'] == 0o600
        and (restored or list(before['identity']) == request['configuration_identity']),
        'ordinary_recovery_configuration_identity_changed')
    f.require(stat.S_IMODE(backup.stat().st_mode) == 0o600,'ordinary_recovery_private_backup_mode_required')
    cfg = safe_load(old)
    f.require(type(cfg) is dict and 'onboarding' not in cfg,
        'ordinary_recovery_backup_already_has_onboarding')
    if restored:
        f.require(before['data'] == old,'ordinary_recovery_restored_bytes_changed')
    else:
        f.require(before['data'] == old + FIRST_CONTACT_CONFIG_SUFFIX,
            'ordinary_recovery_exact_native_append_required')
        expected = dict(cfg); expected['onboarding'] = {'seen':{'profile_build_offered':True}}
        f.require(safe_load(before['data']) == expected,'ordinary_recovery_only_known_field_required')
    return profile_home, before, old


@contextlib.contextmanager
def retained_first_contact_config_lock(config_path):
    """Refuse unsafe native a+ lock targets before its PID stamp can write."""
    f = api(); path = config_path.with_name(config_path.name+'.lock')
    before = update_file_state(path)
    f.require(before is not None and before['data'] == b'' and before['mode'] in (0o600,0o644,0o664),
        'ordinary_recovery_existing_native_config_lock_required')
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        def prove():
            opened = os.fstat(fd)
            identity = tuple(getattr(opened,k) for k in ('st_dev','st_ino','st_uid','st_nlink','st_mode'))
            current = update_file_state(path)
            f.require(identity == before['identity'] and current is not None
                and current['identity'] == before['identity'], 'ordinary_recovery_native_config_lock_identity_changed')
        prove()
        from hermes_cli.config import config_write_transaction
        with config_write_transaction(config_path):
            prove()
            yield
            prove()
    finally:
        os.close(fd)


def recover_first_contact_config(request, request_path, budget):
    """One consumed exact-byte repair, always leaving native consumers stopped."""
    f = api()
    fields = {'schema','seconds','home','profile','binding','generation','allowed_delta','configuration_identity',
        'installed_input','root_marker','source_receipt','stamp','root_configuration','root_profile',
        'native_unit','onboarding','user_marker','configuration','backup','access_state'}
    f.require(type(request) is dict and set(request) == fields
        and request['schema'] == 'friday.ordinary-first-contact-config-recovery.v1'
        and type(request['seconds']) is int and 30 <= request['seconds'] <= 180
        and type(request['generation']) is int and request['generation'] >= 1
        and request['allowed_delta'] == 'append-onboarding.seen.profile_build_offered=true'
        and type(request['configuration_identity']) is list and len(request['configuration_identity']) == 5
        and all(type(n) is int for n in request['configuration_identity']),
        'ordinary_recovery_explicit_request_required')
    home = f.directory(f.canonical(request['home'])); source = f.directory(home/'hermes-agent')
    f.require(os.environ.get('HERMES_HOME') == str(home),'ordinary_recovery_exact_environment_required')
    f.directory(home/'preparation')
    request_path = f.canonical(str(request_path)); request_state = update_file_state(request_path)
    f.owned_file(request_path,private=True)
    f.require(f.read_json(request_path) == request,'ordinary_recovery_request_changed')
    fd = os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        opened = os.fstat(fd); linked = home.lstat()
        f.require((opened.st_dev,opened.st_ino) == (linked.st_dev,linked.st_ino),
            'ordinary_recovery_home_identity_changed')
        # Authenticate native code before importing the code that holds host custody.
        original = f.read_json(f.pin(request['installed_input']))
        receipt = f.read_json(f.pin(request['source_receipt']))
        donors = {r['id']:r for r in f.read_json(f.pin(original['sources_lock']))['repositories']}
        budget.call(f.composition_checked,original,source,receipt,donors['hermes'])
        f.native_packages(source)
        with stopped_consumers(home,request['native_unit'],budget) as prove, retained_build_lock(source) as build_prove:
            budget.check(); prove(); build_prove()
            pinned_before = {name:update_file_state(f.canonical(ref['path'])) for name,ref in request.items()
                if type(ref) is dict and set(ref) == {'path','sha256'}}
            profile_home,before,old = first_contact_recovery_inputs(request,home,source)
            tx = home/'preparation'/('ordinary-first-contact-config-recovery-'+request['configuration']['sha256'])
            f.require(not os.path.lexists(tx),'ordinary_recovery_consumed_no_retry')
            with retained_first_contact_config_lock(profile_home/'config.yaml'):
                prove();build_prove();budget.check()
                f.require(same_update_file(request_path,request_state),'ordinary_recovery_request_identity_changed')
                # Revalidate every pin, policy, access-history byte and inode under native CAS lock.
                _,again,checked_old = first_contact_recovery_inputs(request,home,source)
                f.require(again == before and checked_old == old,'ordinary_recovery_cas_changed')
                f.require(all(same_update_file(Path(request[name]['path']),state)
                    for name,state in pinned_before.items()),'ordinary_recovery_pinned_identity_changed')
                tx.mkdir(mode=0o700)
                write(tx/'bad-config.yaml',before['data'])
                write(tx/'intent.json',encoded({'schema':'friday.ordinary-first-contact-config-recovery-transaction.v1',
                    'state':'CONSUMED_NO_RETRY','request_sha256':f.digest(request_state['data']),
                    'bad_sha256':request['configuration']['sha256'],'restored_sha256':request['backup']['sha256'],
                    'consumers_started':False,'source_updated':False,'database_changed':False}))
                sync_directory(tx);sync_directory(tx.parent)
                owned = {}
                try:
                    prove();build_prove();budget.check()
                    publish_update_file(profile_home/'config.yaml',old,before['mode'],before,owned,'config.yaml')
                    _,after,_ = first_contact_recovery_inputs(request,home,source,restored=True)
                    f.require(after == owned['config.yaml'],'ordinary_recovery_publication_identity_changed')
                    f.require(all(same_update_file(Path(request[name]['path']),state)
                        for name,state in pinned_before.items() if name != 'configuration'),
                        'ordinary_recovery_unchanged_original_identity_required')
                    from hermes_cli import friday_user_scope as user
                    user.check_onboarding_home(home,profile_home,request['binding'])
                    principal = tuple(request['binding'][k] for k in
                        ('platform','transport_profile','account_id','user_id'))
                    info = profile_home.stat()
                    # Unchanged complete per-event admission check, with no published capability.
                    with user.authority(profile_home):
                        user.UserScope(home,profile_home,request['profile'],principal,dict(request['binding']),
                            (info.st_dev,info.st_ino),request['generation']).check()
                    prove();build_prove();budget.check()
                    write(tx/'committed.json',encoded({'state':'EXACT_CONFIG_RESTORED_CONSUMERS_STOPPED',
                        'config_sha256':request['backup']['sha256'],'source_updated':False,
                        'database_changed':False,'runtime_accepted':False,'consumers_started':False}))
                    sync_directory(tx)
                except BaseException as original_error:
                    # Publication may already have happened. Never restore BAD or retry blindly.
                    try:
                        prove();build_prove()
                        write(tx/'failed.json',encoded({'state':'CONSUMED_RECONCILIATION_REQUIRED',
                            'restored_config_retained':bool(owned) and same_update_file(profile_home/'config.yaml',owned.get('config.yaml')),
                            'consumers_stopped':True,'consumers_started':False}))
                        sync_directory(tx)
                    except BaseException as evidence_error:
                        from scripts.dsh_prepare import StopUnconfirmed
                        f.remember_secondary(original_error,evidence_error)
                        raise StopUnconfirmed('ordinary recovery stop/evidence requires reconciliation') from original_error
                    raise
                return {'state':'EXACT_CONFIG_RESTORED_CONSUMERS_STOPPED','ready':False,
                    'source_updated':False,'database_changed':False,'consumers_started':False}
    finally:
        os.close(fd)


# Exact, separate CURRENT-deployment inference rebind. Source update v33 above
# remains unchanged. This action never starts a consumer or changes an admission.
REBIND_SCHEMA = 'friday.ordinary-existing-inference-rebind.v1'
REBIND_BUDGET_SCHEMA = 'friday.ordinary-existing-inference-rebind.v2'


def inference_delta(current, original, replacement):
    """Apply compiler-caused changes only; reject drift at every changed leaf.

    Native onboarding identities and owner settings outside that delta survive.
    A changed list is one exact CAS value, never an implicit scope merge.
    """
    import copy
    f = api()
    if original == replacement: return copy.deepcopy(current)
    if type(original) is dict and type(replacement) is dict:
        f.require(type(current) is dict, 'ordinary_rebind_configuration_delta_drift')
        result = copy.deepcopy(current)
        for key in set(original) | set(replacement):
            if key not in original:
                f.require(key not in current, 'ordinary_rebind_configuration_delta_drift')
                result[key] = copy.deepcopy(replacement[key])
            elif key not in replacement:
                f.require(key in current and current[key] == original[key],
                    'ordinary_rebind_configuration_delta_drift')
                del result[key]
            elif original[key] != replacement[key]:
                f.require(key in current, 'ordinary_rebind_configuration_delta_drift')
                result[key] = inference_delta(current[key],original[key],replacement[key])
        return result
    f.require(current == original, 'ordinary_rebind_configuration_delta_drift')
    return copy.deepcopy(replacement)


def inference_private_reasoning(config):
    """Explicit requested privacy migration even when historical flags are absent."""
    f=api()
    for mapping,key in ((config,'display'),):
        f.require(key not in mapping or type(mapping[key]) is dict,'ordinary_rebind_reasoning_display_shape_required')
    display=config.setdefault('display',{})
    display['show_reasoning']=False
    f.require('platforms' not in display or type(display['platforms']) is dict,
        'ordinary_rebind_reasoning_display_shape_required')
    platforms=display.setdefault('platforms',{})
    f.require('telegram' not in platforms or type(platforms['telegram']) is dict,
        'ordinary_rebind_reasoning_display_shape_required')
    platforms.setdefault('telegram',{})['show_reasoning']=False
    return config


def inference_env_values(raw):
    """Parse owned dotenv without interpolation or process/global fallbacks."""
    import io
    from dotenv.parser import parse_stream
    f = api(); values = {}; parts = []
    try:
        text = raw.decode('utf-8')
        f.require('${' not in text, 'ordinary_rebind_dotenv_interpolation_refused')
        for item in parse_stream(io.StringIO(text)):
            f.require(not item.error, 'ordinary_rebind_dotenv_invalid')
            if item.key is not None:
                f.require(item.key not in values and isinstance(item.value,str),
                    'ordinary_rebind_dotenv_duplicate_or_invalid')
                values[item.key] = item.value
            parts.append((item.key,item.original.string))
    except (UnicodeError,TypeError):
        raise ValueError('ordinary_rebind_dotenv_invalid') from None
    return values,parts


def inference_secret(value):
    api().require(isinstance(value,str) and 0 < len(value) <= 16384 and value.isascii()
        and value == value.strip() and '${' not in value
        and not any(ord(c)<32 or ord(c)==127 for c in value),
        'ordinary_rebind_credential_missing_or_invalid')
    return value


def inference_env_after(raw, new_primary):
    """Retain this home's 27B key independently and preserve every other byte."""
    f = api(); values,parts = inference_env_values(raw)
    primary = 'FRIDAY_LLM_API_KEY'; compressor = 'FRIDAY_COMPRESSION_API_KEY'
    old = inference_secret(values.get(primary)); inference_secret(new_primary)
    f.require(compressor not in values or values[compressor] == old,
        'ordinary_rebind_existing_compression_key_conflict')
    def line(name,value):
        # python-dotenv's supported single-quoted representation; no interpolation.
        return name + "='" + value.replace('\\','\\\\').replace("'","\\'") + "'\n"
    result = ''.join(line(primary,new_primary) if name == primary else original
        for name,original in parts)
    if compressor not in values:
        result += ('' if not result or result.endswith('\n') else '\n') + line(compressor,old)
    after = result.encode(); checked,_ = inference_env_values(after)
    f.require(checked == dict(values,**{primary:new_primary,compressor:old}),
        'ordinary_rebind_credential_roundtrip_failed')
    return after


def inference_primary_reference(reference):
    """Read exactly the supplied protected selector, never search for a key."""
    from scripts.install_credentials import references
    f = api(); references({'FRIDAY_LLM_API_KEY':reference})
    raw = f.owned_file(f.canonical(reference['path']),private=True)
    f.require(len(raw)<=1024*1024, 'ordinary_rebind_credential_source_too_large')
    try:
        values = (json.loads(raw,object_pairs_hook=f.unique) if reference['format']=='json'
            else inference_env_values(raw)[0])
        f.require(type(values) is dict, 'ordinary_rebind_credential_source_invalid')
        return inference_secret(values.get(reference['name']))
    except (UnicodeError,TypeError,KeyError):
        raise ValueError('ordinary_rebind_credential_source_invalid') from None


@contextlib.contextmanager
def inference_locks(home, profile_home, access_path, budget):
    """Native ordering: state, root/user config, root/user dotenv; no new locks."""
    from hermes_cli.config import _env_write_lock
    from hermes_cli.plugins_state import PluginState
    from plugins.friday_rework.associations import Associations
    from hermes_cli.auth import _auth_store_lock
    f = api(); paths = [home/'config.yaml.lock',profile_home/'config.yaml.lock',
        home/'.env.lock',profile_home/'.env.lock',home/'auth.lock',profile_home/'auth.lock',
        access_path.with_name('.state.json.lock')]
    states = {}
    for path in paths:
        state = update_file_state(path)
        f.require(state is not None and state['data'] == b'' and state['mode'] == 0o600,
            'ordinary_rebind_existing_private_native_lock_required')
        states[path] = state['identity']
    def prove():
        for path,identity in states.items():
            state = update_file_state(path)
            f.require(state is not None and state['identity'] == identity,
                'ordinary_rebind_native_lock_identity_changed')
    # Native admission.lock serializes supported access/onboarding writers.
    # Holding .state.json.lock across native proof reads would self-deadlock.
    admission=access_path.with_name('admission.lock')
    state=update_file_state(admission)
    f.require(state is not None and state['data']==b'v1\n' and state['mode']==0o600,
        'ordinary_rebind_existing_native_admission_required')
    states[admission]=state['identity']
    state_document=f.read_json(access_path)
    f.require('associations.v1' in state_document,'ordinary_rebind_existing_associations_required')
    with Associations(PluginState('friday_rework'))._locked():
        with retained_first_contact_config_lock(home/'config.yaml'):
            with retained_first_contact_config_lock(profile_home/'config.yaml'):
                with _auth_store_lock(target_path=home/'auth.json'), _auth_store_lock(target_path=profile_home/'auth.json'), \
                        _env_write_lock(home/'.env'), _env_write_lock(profile_home/'.env'):
                    prove(); yield prove; prove()


def inference_rebind_inputs(request, budget):
    """Exact pinned beforeimages, unchanged source inventory and historical clocks."""
    f = api()
    budget_only = type(request) is dict and request.get('schema') == REBIND_BUDGET_SCHEMA
    fields = {'schema','seconds','home','profile','previous_input','current_input',
        'native_unit','before','retained'} | (set() if budget_only else {'primary_credentials'})
    f.require(type(request) is dict and set(request)==fields
        and request['schema'] in (REBIND_SCHEMA,REBIND_BUDGET_SCHEMA) and request['profile']=='dest_telegram'
        and type(request['seconds']) is int and 30<=request['seconds']<=180,
        'ordinary_rebind_explicit_request_required')
    home = f.directory(f.canonical(request['home']));source=f.directory(home/'hermes-agent')
    f.require(os.environ.get('HERMES_HOME')==str(home),'ordinary_rebind_exact_environment_required')
    f.directory(home/'profiles');profile_home=f.directory(home/'profiles'/request['profile'])
    f.directory(home/'preparation')
    # Authenticate the existing native package before importing its helpers.
    before_input=f.read_json(f.pin(request['previous_input']))
    after_input=f.read_json(f.pin(request['current_input']))
    budget.call(f.inspect,before_input,request['previous_input']['sha256'])
    from hermes_cli import friday_user_scope as user
    from hermes_cli.plugins_state import _plugin_data_namespace
    relative = 'profiles/'+request['profile']+'/'
    names = {'config.yaml','FRIDAY-PROFILE.json',f.MARKER,'.env',relative+'config.yaml',
        relative+user.ONBOARDING,relative+user.MARKER,relative+'.env'}
    if budget_only: names -= {'.env',relative+'.env','FRIDAY-PROFILE.json'}
    f.require(type(request['before']) is dict and set(request['before'])==names,
        'ordinary_rebind_exact_before_inventory_required')
    for name,ref in request['before'].items():
        f.require(f.pin(ref)==home/name,'ordinary_rebind_exact_before_path_required')
        f.owned_file(home/name,private=True)
        f.require(update_file_state(home/name)['mode']==0o600,
            'ordinary_rebind_existing_private_file_required')
    # Existing pools can override provider credentials. Preserve them and refuse
    # until their exact provider-entry migration is independently reviewed.
    for own in (home,profile_home):
        f.require(not os.path.lexists(own/'auth.json'),
            'ordinary_rebind_existing_auth_pool_migration_required')
    if not budget_only:
        credentials=request['primary_credentials']
        f.require(type(credentials) is dict and set(credentials)=={'root','user'},
            'ordinary_rebind_separate_home_credential_references_required')
        from scripts.install_credentials import references
        for reference in credentials.values(): references({'FRIDAY_LLM_API_KEY':reference})
    f.require(request['previous_input']!=request['current_input']
        and before_input.get('home')==after_input.get('home')==str(home)
        and {k:v for k,v in before_input.items() if k!='product'}==
            {k:v for k,v in after_input.items() if k!='product'},
        'ordinary_rebind_source_inventory_or_original_budget_changed')
    old=before_input['product'];new=after_input['product']
    if budget_only:
        budget_field='request_budget_seconds'
        f.require(type(old) is dict and type(new) is dict
            and {'inference','compression_inference','compression_multipass'} <= set(old)
            and type(old['inference']) is dict and type(new.get('inference')) is dict
            and budget_field in new['inference']
            and old['inference'].get(budget_field) != new['inference'][budget_field]
            and {k:v for k,v in old.items() if k!='inference'} ==
                {k:v for k,v in new.items() if k!='inference'}
            and {k:v for k,v in old['inference'].items() if k!=budget_field} ==
                {k:v for k,v in new['inference'].items() if k!=budget_field}
            and old['inference']['key_env']=='FRIDAY_LLM_API_KEY'
            and old['compression_inference']['key_env']=='FRIDAY_COMPRESSION_API_KEY'
            and all(type(p['runtime']) is dict and set(p['runtime'])=={'enabled'}
                and p['runtime']['enabled'] is False for p in (old,new)),
            'ordinary_rebind_exact_primary_request_budget_delta_required')
    else:
        route_fields={'inference','compression_inference','compression_multipass'}
        f.require(type(old) is dict and type(new) is dict
            and 'compression_inference' not in old and 'compression_multipass' not in old
            and route_fields<=set(new)
            and all(type(p['runtime']) is dict and set(p['runtime'])=={'enabled'}
                and p['runtime']['enabled'] is False for p in (old,new))
            and {k:v for k,v in old.items() if k not in route_fields}==
                {k:v for k,v in new.items() if k not in route_fields}
            and old['inference']['key_env']==new['inference']['key_env']=='FRIDAY_LLM_API_KEY'
            and new['compression_inference']['key_env']=='FRIDAY_COMPRESSION_API_KEY'
            and {k:v for k,v in old['inference'].items() if k!='key_env'}==
                {k:v for k,v in new['compression_inference'].items() if k!='key_env'},
            'ordinary_rebind_exact_preserved_compressor_and_scope_required')
    # Do not bypass the normal restart input validator: current versions reject
    # split declarations until its separately reviewed integration is installed.
    budget.call(f.spec_checked,after_input,cli_only=True)
    marker=f.read_json(home/f.MARKER)
    f.require(marker.get('completion_stage')=='TELEGRAM_ORDINARY'
        and marker.get('runtime_ready') is False
        and f.cli_historical_scope_closed(marker['original_attempt'],'friday.native-install.v1')
        and (marker.get('cli_segment') is None or
            f.cli_historical_scope_closed(marker['cli_segment']['clock'],'friday.cli-segment-clock.v1')),
        'ordinary_rebind_closed_original_clocks_required')
    access_path=home/'plugin-data'/_plugin_data_namespace('friday_rework','')/'state.json'
    required={'hermes-agent.source.json','hermes-agent/install-stamp.json',
        'hermes-agent/.hermes/bin/hermes','SOUL.md',relative+'SOUL.md',str(access_path.relative_to(home)),
        str(access_path.with_name('admission.lock').relative_to(home)),
        *marker['ordinary_gateway']['history']}
    if budget_only: required.update({'.env',relative+'.env','FRIDAY-PROFILE.json'})
    retained=request['retained']
    f.require(type(retained) is dict and required<=set(retained)
        and not set(retained)&names,'ordinary_rebind_retained_history_required')
    for name,ref in retained.items():
        path=Path(name)
        f.require(not path.is_absolute() and '..' not in path.parts and '.' not in path.parts
            and f.pin(ref)==home/path,'ordinary_rebind_exact_retained_path_required')
    f.pin(request['native_unit'])
    return home,source,profile_home,access_path,before_input,after_input,marker


@contextlib.contextmanager
def inference_retaining_cleanup(fd):
    """Native custody teardown cannot replace the transaction's primary cause."""
    primary=None
    try:
        with contextlib.ExitStack() as stack:
            stack.callback(os.close,fd)
            try:
                yield stack
            except BaseException as error:
                primary=error
                raise
    except BaseException as cleanup:
        if primary is None or cleanup is not primary:
            from scripts.dsh_prepare import StopUnconfirmed
            cause=primary if primary is not None else cleanup
            if cleanup is not cause: api().remember_secondary(cause,cleanup)
            raise StopUnconfirmed('ordinary inference rebind custody cleanup requires reconciliation') from cause
        raise


def rebind_inference(request, request_path, budget):
    """One finite operator transaction; consumers remain stopped, all-or-rollback.

    Only compiler-caused inference deltas and native reseals are published. The
    journal is not a capability or a new history entry in ordinary_gateway.
    """
    import copy
    budget_only = request.get('schema') == REBIND_BUDGET_SCHEMA
    f=api();request_path=f.canonical(str(request_path))
    request_state=update_file_state(request_path);f.owned_file(request_path,private=True)
    f.require(request_state is not None and json.loads(request_state['data'],object_pairs_hook=f.unique)==request,
        'ordinary_rebind_request_changed')
    # Statically reject unknown fields/pools/unsupported restart inputs before
    # host custody or any journal/configuration/credential publication.
    home,source,profile_home,access_path,previous,current,marker=inference_rebind_inputs(request,budget)
    tx=home/'preparation'/('ordinary-inference-rebind-'+request['previous_input']['sha256'])
    f.require(not os.path.lexists(tx),'ordinary_rebind_consumed_no_retry')
    fd=os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    with inference_retaining_cleanup(fd) as native_stack:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        home_identity=(os.fstat(fd).st_dev,os.fstat(fd).st_ino)
        directory_identities={path:(path.lstat().st_dev,path.lstat().st_ino) for path in
            (home,home/'profiles',profile_home,source,home/'preparation',access_path.parent)}
        def directories_unchanged():
            for path,identity in directory_identities.items():
                f.directory(path);info=path.lstat()
                f.require((info.st_dev,info.st_ino)==identity,'ordinary_rebind_directory_identity_changed')
        native_prove=native_stack.enter_context(stopped_consumers(home,request['native_unit'],budget))
        build_prove=native_stack.enter_context(retained_build_lock(source))
        lock_prove=native_stack.enter_context(inference_locks(home,profile_home,access_path,budget))
        def custody():
            native_prove();build_prove();lock_prove();directories_unchanged();budget.check()
            info=home.lstat()
            f.require((info.st_dev,info.st_ino)==home_identity,'ordinary_rebind_home_identity_changed')
        again=inference_rebind_inputs(request,budget)
        f.require(again==(home,source,profile_home,access_path,previous,current,marker),
            'ordinary_rebind_cas_changed')
        saved={name:update_file_state(home/name) for name in request['before']}
        retained={name:update_file_state(home/name) for name in request['retained']}
        f.require(all(v is not None and f.digest(v['data'])==request['before'][n]['sha256'] for n,v in saved.items())
            and all(v is not None and f.digest(v['data'])==request['retained'][n]['sha256'] for n,v in retained.items()),
            'ordinary_rebind_exact_snapshot_hash_changed')
        external={request_path:request_state,Path(request['previous_input']['path']):update_file_state(Path(request['previous_input']['path'])),
            Path(request['current_input']['path']):update_file_state(Path(request['current_input']['path'])),
            Path(request['native_unit']['path']):update_file_state(Path(request['native_unit']['path']))}
        f.require(all(state is not None and f.digest(state['data'])==ref['sha256'] for ref,state in
            ((request['previous_input'],external[Path(request['previous_input']['path'])]),
             (request['current_input'],external[Path(request['current_input']['path'])]),
             (request['native_unit'],external[Path(request['native_unit']['path'])]))),
            'ordinary_rebind_exact_external_hash_changed')
        # A reference may not alias any destination or historical state.
        for reference in request.get('primary_credentials',{}).values():
            path=f.canonical(reference['path'])
            f.require(path not in {home/n for n in saved} and path not in {home/n for n in retained},
                'ordinary_rebind_credential_source_alias_refused')
            state=update_file_state(path);f.owned_file(path,private=True)
            external[path]=state
        def retained_unchanged():
            custody()
            f.require(all(same_update_file(home/n,v) for n,v in retained.items())
                and all(same_update_file(p,v) for p,v in external.items())
                and all(not os.path.lexists(h/'auth.json') for h in (home,profile_home)),
                'ordinary_rebind_retained_or_protected_reference_changed')
        def before_unchanged():
            retained_unchanged()
            f.require(all(same_update_file(home/n,v) for n,v in saved.items()),
                'ordinary_rebind_beforeimage_identity_changed')
        from tools.configure_product import compose_product
        from plugins.friday_rework.onboarding import prepare_admin_config_edit,finish_admin_config_edit,validate_template
        from hermes_cli.config import atomic_config_write
        from hermes_cli import friday_user_scope as user
        from hermes_cli.friday_ordinary_gateway import normalized_configuration,credential_identity,check
        from hermes_yaml import safe_load
        old_bundle=compose_product(previous['product']);new_bundle=compose_product(current['product'])
        original_cfg=safe_load(saved['config.yaml']['data'])
        settings_path=lambda cfg:cfg['plugins']['entries']['friday_rework']['settings']
        templates=settings_path(original_cfg)['onboarding']['templates']
        f.require(type(templates) is dict and set(templates)=={'friday-local','friday-ordinary-local'},
            'ordinary_rebind_exact_existing_templates_required')
        ordinary_before=templates['friday-ordinary-local']
        ordinary_settings=settings_path(ordinary_before['config'])
        f.require('worker_inputs' not in ordinary_before
            and type(ordinary_settings.get('runtime')) is dict
                    and set(ordinary_settings['runtime'])=={'enabled'}
                    and ordinary_settings['runtime']['enabled'] is False
            and 'worker_requirements' not in ordinary_settings,
            'ordinary_rebind_ordinary_template_independence_required')
        root_cfg=inference_delta(original_cfg,old_bundle['config'],new_bundle['config'])
        old_base=old_bundle['config']['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']
        new_base=new_bundle['config']['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']
        old_ordinary=copy.deepcopy(old_base);old_ordinary.pop('worker_inputs',None)
        new_ordinary=copy.deepcopy(new_base);new_ordinary.pop('worker_inputs',None)
        rebound_templates=settings_path(root_cfg)['onboarding']['templates']
        rebound_templates['friday-ordinary-local']=inference_delta(ordinary_before,old_ordinary,new_ordinary)
        if not budget_only: inference_private_reasoning(root_cfg)
        for selected_template in rebound_templates.values():
            if not budget_only: inference_private_reasoning(selected_template['config'])
            validate_template(selected_template)
        proof_name='profiles/'+request['profile']+'/'+user.ONBOARDING
        user_prefix='profiles/'+request['profile']+'/'
        proof=json.loads(saved[proof_name]['data']);template=proof['template']
        f.require(template in templates,'ordinary_rebind_existing_template_alias_required')
        old_template=old_base if template=='friday-local' else old_ordinary
        new_template=rebound_templates[template]
        user_cfg=inference_delta(safe_load(saved[user_prefix+'config.yaml']['data']),old_template['config'],
            new_base['config'])
        if not budget_only: inference_private_reasoning(user_cfg)
        required=list(proof['required_secrets'])
        if not budget_only and 'FRIDAY_COMPRESSION_API_KEY' not in required: required.append('FRIDAY_COMPRESSION_API_KEY')
        # Existing profiles may have additional, already admitted capabilities
        # (for example the scoped browser). The native edit validator below
        # checks the complete candidate against that profile's current binding;
        # the base template's tools are not its authorization inventory.
        prepared=prepare_admin_config_edit(profile_home,user_cfg,required_secrets=required)
        f.require(prepared is not None and prepared['marker'] is not None,
            'ordinary_rebind_existing_admitted_onboarding_required')
        profile=(None if budget_only else inference_delta(json.loads(saved['FRIDAY-PROFILE.json']['data']),old_bundle['contract'],new_bundle['contract']))
        if budget_only:
            f.require(old_bundle['contract']==new_bundle['contract'], 'ordinary_rebind_budget_contract_changed')
        before_unchanged();f.require(not os.path.lexists(tx),'ordinary_rebind_consumed_no_retry')
        tx.mkdir(mode=0o700);stage=tx/'stage';stage.mkdir(mode=0o700)
        before=tx/'before';before.mkdir(mode=0o700)
        # Intent is consumed before any staging/publication. A failed
        # preparation is retained, never re-executed under a new clock.
        write(tx/'intent.json',encoded({'schema':request['schema'],'state':'CONSUMED_NO_RETRY',
            'request_sha256':f.digest(request_state['data']),'seconds':request['seconds'],
            'previous_input':request['previous_input'],'current_input':request['current_input'],
            'before':{n:{'sha256':f.digest(v['data']),'mode':v['mode']} for n,v in saved.items()},
            'consumers_started':False,'workers_enabled':False,'database_changed':False}),0o400)
        sync_directory(tx);sync_directory(tx.parent)
        owned={}
        try:
            for name,state in saved.items():
                private_parents(before,name);write(before/name,state['data'])
            for prefix,cfg in (('',root_cfg),(user_prefix,user_cfg)):
                private_parents(stage,prefix+'config.yaml')
                # Fresh private staging destination: complete afterimage
                # through the native atomic writer, no omission bypass.
                atomic_config_write(stage/prefix/'config.yaml',cfg)
                f.require(safe_load(f.owned_file(stage/prefix/'config.yaml',private=True))==cfg,
                    'ordinary_rebind_staged_configuration_changed')
                if not budget_only:
                    original=saved[prefix+'.env']['data']
                    selected=inference_primary_reference(request['primary_credentials']['user' if prefix else 'root'])
                    write(stage/prefix/'.env',inference_env_after(original,selected));del selected
            stage_user=stage/user_prefix
            write(stage_user/user.ONBOARDING,saved[proof_name]['data'])
            write(stage_user/user.MARKER,saved[user_prefix+user.MARKER]['data'])
            finish_admin_config_edit(stage_user,prepared)
            write(stage/'FRIDAY-PROFILE.json',retained['FRIDAY-PROFILE.json']['data'] if budget_only else encoded(profile))
            updated=copy.deepcopy(marker)
            updated['input_sha256']=request['current_input']['sha256']
            updated['profile_files']['config.yaml']=f.digest(f.owned_file(stage/'config.yaml',private=True))
            updated['profile_files']['FRIDAY-PROFILE.json']=f.digest(f.owned_file(stage/'FRIDAY-PROFILE.json',private=True))
            phase=updated['ordinary_gateway']
            phase['profile_sha256']=updated['profile_files']['FRIDAY-PROFILE.json']
            # Effective native config includes defaults; raw-YAML hashing
            # would differ from the exact ordinary check on restart.
            from hermes_cli.config_effective import load_user_config_effective
            phase['configuration_sha256']=normalized_configuration(load_user_config_effective(stage/'config.yaml',fail_closed=True))
            if not budget_only: phase['credential_files']['.env']=credential_identity(stage)[0]
            phase['operator_entry']['input']=request['current_input']
            write(stage/f.MARKER,encoded(updated))
            staged={name:update_file_state(stage/name) for name in saved}
            f.require(all(v is not None and v['mode']==0o600 for v in staged.values()),
                'ordinary_rebind_complete_private_stage_required')
            # Native split admission and root contract validation before
            # replacing the first durable live file. No test receipt can
            # substitute for these real native configuration validators.
            from hermes_cli.friday_credential_admission import local_route,profile_policy
            local_route(root_cfg);local_route(user_cfg);profile_policy(stage,root_cfg)
            # Bytes were fsynced by write(); retain all nested directory entries
            # durably before replacing the first existing deployment file.
            for durable_root in (before,stage):
                for directory in sorted((p for p in durable_root.rglob('*') if p.is_dir()),
                        key=lambda p:len(p.parts),reverse=True):
                    f.directory(directory);sync_directory(directory)
                sync_directory(durable_root)
            sync_directory(tx)
            before_unchanged()
            order=['config.yaml',user_prefix+'config.yaml',proof_name,user_prefix+user.MARKER,f.MARKER] if budget_only else [
                '.env',user_prefix+'.env','config.yaml',user_prefix+'config.yaml',
                'FRIDAY-PROFILE.json',proof_name,user_prefix+user.MARKER,f.MARKER]
            for name in order:
                retained_unchanged();budget.check(reserve=15)
                f.require(all(same_update_file(home/n,owned.get(n,v)) for n,v in saved.items()),
                    'ordinary_rebind_publication_cas_changed')
                f.require(same_update_file(stage/name,staged[name]),'ordinary_rebind_stage_identity_changed')
                publish_update_file(home/name,staged[name]['data'],saved[name]['mode'],saved[name],owned,name)
            retained_unchanged();check(home,role=False)
            settings=root_cfg['plugins']['entries']['friday_rework']['settings']
            bindings=[b for b in settings['user_isolation']['bindings'] if b['runtime_profile']==request['profile']]
            f.require(len(bindings)==1,'ordinary_rebind_single_existing_binding_required')
            binding=bindings[0];principal=tuple(binding[k] for k in ('platform','transport_profile','account_id','user_id'))
            from hermes_cli.friday_product_access import current_access,principal_id
            with user.authority(home): row=current_access()['users'][principal_id(*principal)]
            f.require(row['enabled'] is True and row['role']=='user','ordinary_rebind_original_user_disabled')
            info=profile_home.stat()
            with user.authority(profile_home):
                user.UserScope(home,profile_home,request['profile'],principal,dict(binding),
                    (info.st_dev,info.st_ino),row['generation']).check()
            budget.call(f.inspect,current,request['current_input']['sha256'])
            retained_unchanged()
            f.require(all(same_update_file(home/n,owned[n]) for n in saved),
                'ordinary_rebind_commit_identity_changed')
            result={'state':('EXACT_REQUEST_BUDGET_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED' if budget_only else
                'EXACT_INFERENCE_REBOUND_CONSUMERS_STOPPED_NOT_RUNTIME_ACCEPTED'),
                'ready':False,'workers_enabled':False,'consumers_started':False,'database_changed':False,
                'after':{n:f.digest(v['data']) for n,v in staged.items()}}
            write(tx/'committed.json',encoded(result),0o400);sync_directory(tx)
            return result
        except BaseException as original_error:
            try:
                # Retain original finite custody and budget. If their
                # proof fails, preserve the primary error and stop closed.
                native_prove();build_prove();lock_prove();directories_unchanged()
                restore_update_files(home,saved,owned)
                f.require(all(same_update_file(home/n,v) for n,v in retained.items())
                    and all(same_update_file(p,v) for p,v in external.items()),
                    'ordinary_rebind_rollback_retained_state_changed')
                check(home,role=False)
                write(tx/'rolled-back.json',encoded({'state':'ROLLED_BACK_CONSUMED_NO_RETRY',
                    'consumers_started':False,'database_changed':False}),0o400);sync_directory(tx)
            except BaseException as restoration:
                from scripts.dsh_prepare import StopUnconfirmed
                f.remember_secondary(original_error,restoration)
                raise StopUnconfirmed('ordinary inference rebind rollback requires reconciliation') from original_error
            raise


def recovery_main():
    """Dedicated maintenance dispatch; the ordinary installer phases stay unchanged."""
    import sys
    import time
    # Direct module/script invocation resolves the existing product package.
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path: sys.path.insert(0,str(root))
    f = api(); started = time.monotonic()
    parser = f.SafeParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('phase',choices=('recover-first-contact-config','rebind-inference'))
    parser.add_argument('--request',required=True,type=Path)
    args = parser.parse_args(); os.umask(0o077)
    try:
        request = f.read_json(args.request)
        from scripts.install_containment import Budget
        budget = Budget(request.get('seconds'),started=started)
        result = (rebind_inference(request,args.request,budget) if args.phase=='rebind-inference'
            else recover_first_contact_config(request,args.request,budget))
        print(json.dumps(result,sort_keys=True))
    except Exception as exc:
        from scripts.dsh_prepare import StopUnconfirmed
        if args.phase=='rebind-inference' and isinstance(exc,StopUnconfirmed):
            f.exit_retaining_cause(parser,3,exc,args.phase)
        f.exit_retaining_cause(parser,2,exc,args.phase)


if __name__ == '__main__':
    recovery_main()
