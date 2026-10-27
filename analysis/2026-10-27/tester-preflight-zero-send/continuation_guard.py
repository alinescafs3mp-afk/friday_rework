# UNBOUND ANALYSIS EXCERPT. Incomplete dependencies; not a runnable tester.
# Original operational values are omitted; see SOURCE-PROVENANCE.json.
class TesterExcerpt:
    def continuation_receipt(self, run, *, with_prior=False):
        # The independently retained admission obliges this run even if its mutable
        # field is removed. The immutable send-window/receive chain also binds it.
        matches = []
        for path in self.store.root.glob('continue-*.json'):
            value = self.store.get(path)
            if value.get('plan', {}).get('new_run_id') == run['id']:
                raw = safe_read(path)
                matches.append((value, dict(basename=path.name, bytes=len(raw), sha256=digest(raw))))
        if not matches and 'continuation_reference' not in run:
            return None
        if len(matches) != 1 or run.get('continuation_reference') != matches[0][1]:
            raise Refused('Mandatory continuation admission missing or changed')
        value, ref = matches[0]; plan = value['plan']
        if (value.get('plan_sha256') != digest(encoded(plan))
                or run['scenario'] != plan['new_scenario'] or run['step'] != 0
                or run['id'] != plan['new_run_id']):
            raise Refused('Continuation task commitment changed')
        closed = getattr(self, '_closed_text_predecessor', None)
        if closed == (run['id'], plan):
            # serial_predecessor already pinned this exact immutable admission and
            # run. Verify its own task/ACK/window/receipts without walking its parent.
            # Current origin/credential/cursor authority remains checked by the NEW
            # plan's continuation_material before any effect, never by this shortcut.
            return (plan, [], ref, None) if with_prior else (plan, [], ref)
        old, updates, prior = self.continuation_material(plan)
        root = no_symlinks(self.store.root).stat()
        if (prior['state_identity'] != dict(path=str(self.store.root), device=root.st_dev, inode=root.st_ino, uid=root.st_uid)
                or root.st_uid != os.getuid() or stat.S_IMODE(root.st_mode) != 0o700):
            raise Refused('Continuation state root changed')
        for name, field in [('consumer.lock', 'consumer_identity'), ('tester-token', 'credential_identity')]:
            if input_stat(no_symlinks(self.store.root / name).stat()) != prior[field]:
                raise Refused('Continuation consumer or credential identity changed')
        return (plan, updates, ref, prior) if with_prior else (plan, updates, ref)

    def guard(self, run, *, http_cap=10):
        continuation = self.continuation_receipt(run, with_prior=True)
        if historical_capture_scenario(run.get('scenario')) and (continuation is None
                or continuation[0].get('predecessor', {}).get('run_id') not in ('UNBOUND_PREDECESSOR_A','UNBOUND_PREDECESSOR_B')
                or continuation[0].get('new_task', {}).get('kind') != 'resume-worker-file-task'
                or continuation[0]['new_task'].get('worker') != 'DSH'):
            raise Refused('Extended capture requires exact historical admission; no dispatch')
        monotonic_budget = http_cap
        if continuation is not None:
            monotonic_budget = self.recovery_guard(continuation[0], http_cap=http_cap)
            if run.get('send_state') in ('none', 'intent'):
                prior = continuation[3]
                if prior is None:
                    _, _, prior = self.continuation_material(continuation[0])
                if digest(safe_read(self.store.root / 'cursor.json')) != prior['cursor_sha256']:
                    raise Refused('Continuation receive cursor drifted before new outbound effect')
                self.cursor_offsets(self.store.get(self.store.root / 'cursor.json'))
        if (self.store.root / 'observer-stop.json').exists():
            raise Refused('Observer stopped; product cancellation is separate')
        if self.clock() >= run['deadline']:
            raise Refused('Original scenario deadline expired; product may still run')
        cooldown = self.store.get(self.store.root / 'cooldown.json', {})
        if self.clock() < cooldown.get('until', 0):
            raise Refused('retry_after cooldown active; no network request allowed')
        if continuation is not None:
            monotonic_budget = self.recovery_guard(continuation[0], http_cap=http_cap)  # Sample after durable validation reads.
        return min(http_cap, monotonic_budget, run['deadline'] - self.clock())
