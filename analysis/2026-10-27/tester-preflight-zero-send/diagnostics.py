# UNBOUND ANALYSIS EXCERPT. Incomplete dependencies; not a runnable tester.
# Original operational values are omitted; see SOURCE-PROVENANCE.json.
def send_failure_diagnostic(exc, phase='SEND_API_CALL'):
    # Fixed diagnostic vocabulary only. Never serialize exception text/reason/URL.
    phases = {'HTTP_WHOLE_CALL', 'HTTP_REQUEST_OR_HEADERS', 'HTTP_RESPONSE_BODY',
              'HTTP_RESPONSE_STATUS', 'HTTP_RESPONSE_ENVELOPE', 'SEND_API_CALL'}
    causes = {'LOCAL_HTTP_ALARM_DEADLINE', 'LOCAL_HTTP_BODY_DEADLINE',
              'HTTP_STATUS_3XX', 'HTTP_STATUS_4XX', 'HTTP_STATUS_5XX', 'HTTP_STATUS_OTHER',
              'TRANSPORT_TIMEOUT', 'TRANSPORT_URL_FAILURE', 'TRANSPORT_OS_FAILURE',
              'TRANSPORT_OUTCOME_UNKNOWN'}
    phase = phase if type(phase) is str and phase in phases else 'SEND_API_CALL'
    if isinstance(exc, urllib.error.HTTPError):
        status = exc.code
        category = status // 100 if type(status) is int else None
        return ('HTTP_STATUS_' + str(category) + 'XX' if category in (3, 4, 5)
                else 'HTTP_STATUS_OTHER'), 'HTTP_RESPONSE_STATUS'
    if isinstance(exc, TimeoutError):
        return 'TRANSPORT_TIMEOUT', phase
    if isinstance(exc, urllib.error.URLError):
        return ('TRANSPORT_TIMEOUT' if isinstance(exc.reason, TimeoutError)
                else 'TRANSPORT_URL_FAILURE'), phase
    if isinstance(exc, OSError):
        return 'TRANSPORT_OS_FAILURE', phase
    if isinstance(exc, Refused):
        code = getattr(exc, 'cause_code', None)
        supplied_phase = getattr(exc, 'phase_code', None)
        return (code if type(code) is str and code in causes else 'TRANSPORT_OUTCOME_UNKNOWN',
                supplied_phase if type(supplied_phase) is str and supplied_phase in phases else phase)
    return 'TRANSPORT_OUTCOME_UNKNOWN', phase

class TesterExcerpt:
    def pre_request_diagnostic(self, run, exc, phase):
        phases = {'SEND_ADMISSION', 'SEND_CLAIM', 'CURSOR_AUTHORITY', 'SCENARIO_VALIDATION',
                  'PRE_REQUEST_GUARD', 'INPUT_CUSTODY', 'GET_PREFLIGHT', 'METADATA_PREPARATION',
                  'PRE_INTENT_REVALIDATION'}
        if phase not in phases:
            return
        classes = ((RateLimited, 'RATE_LIMITED'), (Refused, 'REFUSED'),
                   (urllib.error.HTTPError, 'HTTP_ERROR'), (urllib.error.URLError, 'URL_ERROR'),
                   (TimeoutError, 'TIMEOUT_ERROR'), (OSError, 'OS_ERROR'),
                   (ValueError, 'VALUE_ERROR'), (TypeError, 'TYPE_ERROR'), (KeyError, 'KEY_ERROR'))
        category = next((label for kind, label in classes if isinstance(exc, kind)), 'EXCEPTION')
        allowed = {'send', '_send', 'prepared_unsent', 'resume_prepared', 'continuation_receipt',
                   'continuation_material', 'unknown_reconciliation_context', 'serial_predecessor',
                   'worker_resume_material', 'guard', 'recovery_guard', 'preflight', 'budget', 'call',
                   'worker_route_material', 'worker_route_effects',
                   'retired_prepared', 'prepared_absent_claim_pin',
                   '_call', 'network_deadline', 'cursor_offsets', 'safe_read', 'no_symlinks',
                   'validate_scenario', 'read_document_input', 'document_multipart', 'send_ack_budget'}
        frames = []; trace = exc.__traceback__
        for _ in range(128):
            if trace is None:
                break
            code = trace.tb_frame.f_code
            if code.co_filename == __file__ and code.co_name in allowed:
                frames.append(dict(source='bot_tester.py', function=code.co_name, line=trace.tb_lineno))
                frames = frames[-8:]
            trace = trace.tb_next
        report = dict(schema='friday.tester.pre-request-diagnostic.v1', run_id=run['id'],
                      at=stamp(), phase=phase, exception_class=category, frames=frames)
        # Preserve the first observation. It is diagnostic only, never a retry grant.
        path = self.store.root / ('pre-request-' + run['id'] + '.json')
        self.store.run_path(run['id'])
        fd = os.open(no_symlinks(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded(report)); stream.flush(); os.fsync(stream.fileno())
        fd = os.open(self.store.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
