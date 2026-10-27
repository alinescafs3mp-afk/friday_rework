# UNBOUND analysis excerpt. Not a complete tester, authorization or runnable module.
# Original method body retained except the declared private literal substitutions.
# Dependencies and original/sanitized hashes are listed in PROVENANCE.json.
raise RuntimeError("UNBOUND analysis excerpt; installation and execution are prohibited")

class RunnerUNBOUND:
    def literal_command_material(self, plan, comparison, previous_plan, *, dispatch=False):
        # One exact native command, never a prose/model task or a nonce on the wire.
        spec = plan['new_task']
        if (plan.get('schema') != 'friday.tester.continue-closed-unknown.v2'
                or not isinstance(spec, dict)
                or set(spec) != {'kind', 'nonce', 'command', 'root_command_reference'}
                or spec.get('kind') != 'literal-script-command'
                or spec.get('command') not in ('/status', '/stop')
                or not isinstance(spec.get('nonce'), str) or not re.fullmatch('[a-f0-9]{32}', spec['nonce'])
                or spec['nonce'] == previous_plan.get('new_task', {}).get('nonce')
                or plan['predecessor']['semantic_review_reference'] is not None
                or plan['new_run_id'] == comparison['id']
                or plan['action_id'] == previous_plan.get('action_id')):
            raise Refused('One exact separately authorized literal status or stop required')
        expected_scenario = dict(peer_id=PEER, tester_id=TESTER, peer_username=USERNAME,
            deadline_seconds=120, max_updates=16, pace_seconds=2,
            steps=[dict(request=spec['command'], observe=dict(mode='bounded_reply_capture',
                window_seconds=30, max_messages=4, max_text_chars=8000,
                max_documents=0, document_max_bytes=1048576))])
        if (encoded(plan['new_scenario']) != encoded(expected_scenario)
                or type(plan['ack_timeout_seconds']) is not int or plan['ack_timeout_seconds'] != 10):
            raise Refused('Literal command requires exact wire bytes and finite text-only capture')
        report = self.s444_read(spec['root_command_reference'])
        expected = dict(schema='frw.Root.literal-script-command-authority.v1', operator='Root',
            predecessor=plan['predecessor'], current_tuple=plan['current_tuple'], clock=plan['clock'],
            action_id=plan['action_id'], new_run_id=plan['new_run_id'], nonce=spec['nonce'],
            command=spec['command'], request_sha256=digest(spec['command'].encode('utf-8')),
            tester_sha256=digest(safe_read(__file__)),
            original_outcome='UNKNOWN_RETAINED_NO_REPLAY', original_send_replay_authorized=False,
            worker_or_model_authorized=False, expected_response_binding='EXACT_REPLY_TO_REQUEST_UNGRADED')
        if (not isinstance(report, dict) or set(report) != set(expected) | {'runtime', 'expected_reply_text'}
                or any(encoded(report.get(k)) != encoded(v) for k,v in expected.items())
                or not isinstance(report['expected_reply_text'], str)
                or not 1 <= len(report['expected_reply_text']) <= 8000):
            raise Refused('Exact Root precommitted command/outcome authority required')
        # Root records observable local facts through the existing trusted consumer.
        # None explicitly means not externally observable, never a proven zero.
        # Admission permits only this scoped command and ungraded reply capture;
        # it proves neither global idle/custody nor cessation after native /stop.
        # The receiver neither probes a model nor imports the installed product.
        runtime = self.s444_read(report['runtime'])
        identity = dict(transport_profile='default', bot_id=str(PEER), user_id=str(TESTER),
            chat_id=str(TESTER), runtime_profile='UNBOUND_RUNTIME_PROFILE',
            session_id='UNBOUND_SESSION_ID')
        fixed = dict(schema='frw.Root.literal-script-command-runtime.v1', operator='Root',
            current_tuple=plan['current_tuple'], boot_id=plan['clock']['boot_id'], identity=identity,
            authorized=True, managed_presentation=True, same_live_unsuspended_session=True)
        observable_counts = ('active_agents', 'owned_nonquiescent_worker_rows')
        external_counts = ('pending_messages', 'detached_work', 'web_custody', 'terminal_custody')
        runtime_fields = set(fixed) | set(observable_counts) | set(external_counts) | {
            'effective_locale', 'observed_monotonic', 'session_tip_sha256'}
        if (not isinstance(runtime, dict) or set(runtime) != runtime_fields
                or any(encoded(runtime.get(k)) != encoded(v) for k,v in fixed.items())
                or any(type(runtime[k]) is not int or runtime[k] != 0 for k in observable_counts)
                or any(runtime[k] is not None and (type(runtime[k]) is not int or runtime[k] != 0)
                    for k in external_counts)
                or type(runtime['effective_locale']) is not str
                or runtime['effective_locale'] not in ('UNOBSERVED', 'en', 'ru')
                or not isinstance(runtime['session_tip_sha256'], str)
                or not re.fullmatch('[a-f0-9]{64}', runtime['session_tip_sha256'])
                or type(runtime['observed_monotonic']) not in (int, float)
                or not math.isfinite(runtime['observed_monotonic'])
                or not plan['clock']['origin_monotonic'] <= runtime['observed_monotonic'] < plan['clock']['deadline_monotonic']):
            raise Refused('Exact authorized current session and honest observable runtime report required')
        if dispatch and not 0 <= time.monotonic() - runtime['observed_monotonic'] <= 30:
            raise Refused('Literal command runtime evidence expired before dispatch')
        # This is a precommitted oracle, not acceptance of any future reply.
        oracle = ('UNBOUND_STATUS_ORACLE_PART_1'
                  'UNBOUND_STATUS_ORACLE_PART_2'
                  if spec['command'] == '/status' else 'UNBOUND_STOP_ORACLE')
        if report['expected_reply_text'] != oracle:
            raise Refused('Exact installed Russian idle-command oracle required')
        return report
