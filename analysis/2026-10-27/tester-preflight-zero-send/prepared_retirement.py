# UNBOUND ANALYSIS EXCERPT. Incomplete dependencies; not a runnable tester.
# Original operational values are omitted; see SOURCE-PROVENANCE.json.
class TesterExcerpt:
    def prepared_claim_pin(self, plan, *, retirement_only=False):
        claim = no_symlinks(self.store.root / 'continuations' / self.continuation_key(plan) / 'SEND-ATTEMPT.json')
        def custody(value):
            return tuple(getattr(value, name) for name in ('st_dev', 'st_ino', 'st_uid', 'st_gid',
                         'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
        try:
            fd = os.open(claim, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            if not retirement_only:
                raise
            return self.prepared_absent_claim_pin(plan)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600
                    or before.st_size > 1024):
                raise Refused('Prepared claim custody changed')
            raw = stream.read(1025)
            if (len(raw) > 1024 or custody(before) != custody(os.fstat(stream.fileno()))
                    or custody(before) != custody(no_symlinks(claim).stat())):
                raise Refused('Prepared claim changed while reading')
        return raw, custody(before)

    def prepared_absent_claim_pin(self, plan):
        # Absence is a retirement proof only. Pin the protected directory through
        # an FD and distinguish a missing leaf from a missing/replaced parent.
        parent = no_symlinks(self.store.root / 'continuations' / self.continuation_key(plan))
        def custody(value):
            return tuple(getattr(value, name) for name in ('st_dev', 'st_ino', 'st_uid', 'st_gid',
                         'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISDIR(before.st_mode) or before.st_uid != os.getuid()
                    or stat.S_IMODE(before.st_mode) != 0o700):
                raise Refused('Prepared absent-claim directory custody changed')
            try:
                claim_fd = os.open('SEND-ATTEMPT.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                   dir_fd=fd)
            except FileNotFoundError:
                pass
            else:
                os.close(claim_fd)
                raise Refused('Prepared claim is present; absence cannot be presumed')
            if (custody(before) != custody(os.fstat(fd))
                    or custody(before) != custody(no_symlinks(parent).stat())):
                raise Refused('Prepared absent-claim directory changed while checking')
            return None, custody(before)
        finally:
            os.close(fd)

    def prepared_unsent(self, run, *, expected_claim=None, with_claim=False,
                        retirement=None, historical_cursor=None, retirement_only=False):
        # A claim alone is not an attempt. Only the exact pristine durable row can
        # continue the missing pre-intent boundary; extra fields always fail closed.
        fields = {'id', 'scenario', 'scenario_sha256', 'created_at', 'deadline', 'step',
                  'status', 'send_state', 'sent_ids', 'seen', 'message_ids', 'observations',
                  'update_count', 'last_text', 'repeat_count', 'send_attempts',
                  'capture_start_offset', 'continuation_reference', 'new_ack_timeout_seconds'}
        if (not isinstance(run, dict) or set(run) != fields
                or run.get('status') != 'PREPARED' or run.get('send_state') != 'none'
                or any(type(run[k]) is not int or run[k] != 0
                       for k in ('step', 'update_count', 'repeat_count', 'send_attempts'))
                or any(type(run[k]) is not list or run[k] != []
                       for k in ('sent_ids', 'seen', 'message_ids', 'observations'))
                or run['last_text'] is not None or type(run['capture_start_offset']) is not int
                or run['capture_start_offset'] < 0
                or type(run['deadline']) not in (int, float) or not math.isfinite(run['deadline'])
                or safe_read(self.store.run_path(run['id'])) != encoded(run if retirement is None else
                    dict(run, status='STOPPED', prepared_retirement_reference=retirement))):
            raise Refused('Only the exact durable pristine admitted prepared run can resume')
        validate_scenario(run['scenario'])
        if run['scenario_sha256'] != digest(encoded(run['scenario'])):
            raise Refused('Prepared scenario commitment changed')
        admitted = self.continuation_receipt(run)
        if admitted is None or admitted[0]['new_task'].get('kind') != 'resume-worker-file-task':
            raise Refused('Prepared recovery requires the existing missing-stage worker admission')
        plan, _, ref = admitted
        value = self.read_reference(ref)
        expected = dict(schema='friday.tester.closed-unknown-admission.v1', plan=plan,
                        plan_sha256=digest(encoded(plan)), original_outcome='UNKNOWN',
                        original_replayed=False, status='ONE_NEW_EFFECT_ADMITTED_NO_RETRY',
                        response_binding='UNBOUND')
        if 'predecessor' in plan:
            expected['predecessor_cursor'] = value.get('predecessor_cursor')
        if value != expected or type(run['new_ack_timeout_seconds']) is not int or run['new_ack_timeout_seconds'] != plan['ack_timeout_seconds']:
            raise Refused('Prepared immutable admission changed')
        parent = no_symlinks(self.store.root / 'continuations' / self.continuation_key(plan))
        ps = parent.stat()
        if (not stat.S_ISDIR(ps.st_mode) or ps.st_uid != os.getuid()
                or stat.S_IMODE(ps.st_mode) != 0o700):
            raise Refused('Prepared claim directory custody changed')
        claim_pin = self.prepared_claim_pin(plan, retirement_only=retirement_only)
        if expected_claim is not None and claim_pin != expected_claim:
            raise Refused('Exact existing prepared claim changed during recovery')
        raw = claim_pin[0]
        once = json.loads(raw, object_pairs_hook=unique_object) if raw is not None else None
        if (raw is not None and (not isinstance(once, dict) or set(once) != {'run_id', 'at', 'no_retry'}
                or once['run_id'] != run['id'] or once['no_retry'] is not True or raw != encoded(once))):
            raise Refused('Prepared recovery requires its exact existing no-retry claim')
        try:
            created = dt.datetime.fromisoformat(run['created_at'])
            valid_time = (created.utcoffset() == dt.timedelta(0)
                          and created.isoformat() == run['created_at']
                          and created <= dt.datetime.now(dt.timezone.utc)
                          and run['deadline'] <= created.timestamp() + run['scenario']['deadline_seconds'] + 1)
            if raw is not None:
                claimed = dt.datetime.fromisoformat(once['at'])
                valid_time = (valid_time and claimed.utcoffset() == dt.timedelta(0)
                              and claimed.isoformat() == once['at']
                              and created <= claimed <= dt.datetime.now(dt.timezone.utc))
        except (TypeError, ValueError, OverflowError):
            valid_time = False
        if not valid_time:
            raise Refused('Prepared creation and claim timestamp custody changed')
        # Include malformed/stray attempt names, ACK/window/receive witnesses and
        # downloads, not merely the expected attempt1 JSON. No send marker is benign.
        allowed_names = {'pre-request-' + run['id'] + '.json'}
        if retirement is not None:
            allowed_names.add('retired-prepared-' + run['id'] + '.json')
        for directory in (self.store.root, self.store.downloads):
            if any(run['id'] in path.name and path.name not in allowed_names
                   for path in directory.iterdir()):
                raise Refused('Physical send or capture witness forbids prepared recovery')
        if {path.name for path in parent.iterdir()} != (set() if raw is None else {'SEND-ATTEMPT.json'}):
            raise Refused('Unexpected continuation claim witness forbids prepared recovery')
        if historical_cursor is None:
            cursor = self.store.get(self.store.root / 'cursor.json')
            self.cursor_offsets(cursor)
        else:
            # This is a protected historical retirement proof. Current inventory
            # is checked by the enclosing operation at its safe boundary; replaying
            # that check here would reject its own durable processing intent.
            if (retirement is None or not isinstance(historical_cursor, dict)
                    or digest(encoded(historical_cursor)) != plan['predecessor']['cursor_sha256']):
                raise Refused('Retired prepared historical cursor changed')
            cursor = historical_cursor
        if cursor['offset'] != run['capture_start_offset']:
            raise Refused('Prepared current receive cursor changed')
        if raw is None and self.prepared_absent_claim_pin(plan) != claim_pin:
            raise Refused('Exact absent prepared claim changed during retirement')
        return (admitted, claim_pin) if with_claim else admitted

    def retired_prepared(self, run):
        if not isinstance(run, dict) or run.get('status') != 'STOPPED':
            raise Refused('Exact zero-send retirement row required')
        ref = run.get('prepared_retirement_reference')
        receipt = self.read_reference(ref, 'retired-prepared-' + run['id'] + '.json')
        fields = {'schema', 'run_id', 'prepared_run', 'prepared_run_sha256', 'admission',
                  'claim_sha256', 'claim_custody', 'cursor', 'cursor_sha256', 'at',
                  'status', 'send_attempts', 'no_retry', 'original_failure_cause'}
        if (not isinstance(receipt, dict) or set(receipt) != fields
                or receipt['schema'] != 'friday.tester.retired-prepared.v1'
                or receipt['run_id'] != run['id']
                or receipt['status'] != 'RETIRED_BEFORE_OUTBOUND_INTENT'
                or type(receipt['send_attempts']) is not int or receipt['send_attempts'] != 0
                or receipt['no_retry'] is not True or receipt['original_failure_cause'] != 'UNKNOWN'
                or not isinstance(receipt['prepared_run'], dict)
                or receipt['prepared_run_sha256'] != digest(encoded(receipt['prepared_run']))
                or receipt['admission'] != run.get('continuation_reference')
                or receipt['cursor_sha256'] != digest(encoded(receipt['cursor']))
                or not (receipt['claim_sha256'] is None
                        or (isinstance(receipt['claim_sha256'], str)
                            and re.fullmatch('[a-f0-9]{64}', receipt['claim_sha256'])))
                or type(receipt['claim_custody']) is not list or len(receipt['claim_custody']) != 9
                or any(type(v) is not int for v in receipt['claim_custody'])):
            raise Refused('Protected zero-send retirement receipt changed')
        try:
            at = dt.datetime.fromisoformat(receipt['at'])
            if (at.utcoffset() != dt.timedelta(0) or at.isoformat() != receipt['at']
                    or at > dt.datetime.now(dt.timezone.utc)):
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            raise Refused('Retirement closure timestamp changed') from None
        pristine = receipt['prepared_run']
        # The authenticated zero-send closure is history, not a fresh dispatch
        # of its old authority. Reuse the existing exact-admission shortcut only
        # while rechecking this closure's pristine row/claim/cursor custody.
        historical = self.read_reference(receipt['admission'])
        if not isinstance(historical, dict) or not isinstance(historical.get('plan'), dict):
            raise Refused('Retired immutable admission changed')
        saved_closed = getattr(self, '_closed_text_predecessor', None)
        self._closed_text_predecessor = (pristine.get('id'), historical['plan'])
        try:
            admitted, claim_pin = self.prepared_unsent(pristine, with_claim=True,
                retirement=ref, historical_cursor=receipt['cursor'], retirement_only=True)
        finally:
            self._closed_text_predecessor = saved_closed
        if (receipt['claim_sha256'] != (digest(claim_pin[0]) if claim_pin[0] is not None else None)
                or receipt['claim_custody'] != list(claim_pin[1])):
            raise Refused('Retired original no-retry claim changed')
        return pristine, admitted, ref

    def retire_prepared(self, run, consumer_fd, credential_fd):
        if consumer_fd is None or credential_fd is None:
            raise Refused('Retirement requires both existing exclusive named locks')
        admitted, claim_pin = self.prepared_unsent(run, with_claim=True, retirement_only=True)
        plan = admitted[0]
        _, _, prior = self.continuation_material(plan)
        # Local closure can occur after the old clock expires. It grants no network
        # effect and changes neither that clock nor any send/worker authority.
        for name, field, fd in [('consumer.lock', 'consumer_identity', consumer_fd),
                                ('tester-token', 'credential_identity', credential_fd)]:
            if (input_stat(no_symlinks(self.store.root / name).stat()) != prior[field]
                    or input_stat(os.fstat(fd)) != prior[field]):
                raise Refused('Retirement named lock identity changed')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refused('Another tester consumer is active') from None
        cursor = self.store.get(self.store.root / 'cursor.json')
        if digest(encoded(cursor)) != prior['cursor_sha256']:
            raise Refused('Retirement current cursor authority changed')
        for path in self.store.runs.glob('*.json'):
            if path in (self.store.run_path(run['id']), self.store.run_path(prior['run_id'])):
                continue
            other = self.store.get(path)
            if (other.get('status') not in ('EVIDENCE_READY', 'STOPPED', 'FAILED')
                    or other.get('send_state') in ('intent', 'unknown')):
                raise Refused('Other unfinished work blocks prepared retirement')
        self.prepared_unsent(run, expected_claim=claim_pin, retirement_only=True)
        receipt = dict(schema='friday.tester.retired-prepared.v1', run_id=run['id'],
                       prepared_run=run.copy(), prepared_run_sha256=digest(encoded(run)),
                       admission=run['continuation_reference'],
                       claim_sha256=digest(claim_pin[0]) if claim_pin[0] is not None else None,
                       claim_custody=list(claim_pin[1]),
                       cursor=cursor, cursor_sha256=digest(encoded(cursor)),
                       at=stamp(), status='RETIRED_BEFORE_OUTBOUND_INTENT', send_attempts=0,
                       no_retry=True, original_failure_cause='UNKNOWN')
        raw = encoded(receipt); name = 'retired-prepared-' + run['id'] + '.json'
        path = self.store.root / name
        if path.exists():
            raise Refused('Retirement receipt already exists; reconcile exact closure without replay')
        self.store.write(path, raw)
        run.update(status='STOPPED', prepared_retirement_reference=dict(basename=name, bytes=len(raw), sha256=digest(raw)))
        self.save(run)
        self.retired_prepared(run)
        return dict(run_id=run['id'], status='STOPPED', send_state='none', send_attempts=0,
                    original_failure_cause='UNKNOWN', outbound_dispatched=False,
                    retirement=run['prepared_retirement_reference'], acceptance='NOT_ESTABLISHED')
