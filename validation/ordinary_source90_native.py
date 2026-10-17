"""Independent final composition controls; real native handlers/guards/SQLite.

Product access and provider transport use explicit isolated fixture records.
No installed authority, credentials, Telegram, network or model is exercised.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import ordinary_source90_native_web as n
from hermes_state import SessionDB
import hermes_state_search_snapshot as snap
from tools.session_search_tool import session_search, _discover_impl

OBS = []


class Composition(n.NativeControls):
    def setUp(self):
        super().setUp()
        self.dbs = []
        for cap in self.caps:
            cap.binding['tools'] += ['session_search', 'skills_list', 'skill_view', 'skill_manage']
            marker = {'schema': 'friday.user-home.v1', 'principal': cap.key,
                      'profile': cap.profile, 'binding_sha256': n.us._fingerprint(cap.binding)}
            (cap.home / n.us.MARKER).write_text(json.dumps(marker))
            (cap.home / n.us.MARKER).chmod(0o600)
            (cap.home / 'skills').mkdir(mode=0o700)
            db = SessionDB(cap.home / 'state.db')
            db.db_path.chmod(0o600)
            self.dbs.append(db)
        self.db = self.dbs[0]
        self.seed(self.db, self.caps[0], 'past', 'composeneedle alpha')
        self.seed(self.dbs[1], self.caps[1], 'foreign', 'composeneedle foreign-secret')

    def tearDown(self):
        for db in self.dbs:
            db.close()
        super().tearDown()

    def seed(self, db, cap, sid, content, source='telegram'):
        db.create_session(sid, source=source)
        origin = {'friday_account_origin': {'schema': 'friday.account_origin.v1',
            'platform': cap.principal[0], 'transport_profile': cap.principal[1], 'account_id': cap.principal[2]}}
        db._conn.execute('UPDATE sessions SET user_id=?,profile_name=?,origin_json=? WHERE id=?',
            (cap.principal[3], cap.profile, json.dumps(origin), sid))
        db.append_message(sid, role='user', content=content)
        db._conn.commit()

    def query(self, query='composeneedle', **kw):
        return json.loads(session_search(query=query, db=self.db, **kw))

    def proof(self, value, count):
        self.assertIs(value['success'], True, value)
        self.assertEqual(value['count'], count, value)
        proof = value['search_snapshot']
        response = dict(value)
        response.pop('search_snapshot')
        self.assertEqual(proof['response_sha256'], hashlib.sha256(snap._canonical(response)).hexdigest())
        self.assertEqual(proof['content_integrity'], 'SQLITE_FTS5_RANK1_PASS')
        self.assertEqual(value['index_status']['completeness'], 'CONTENT_COMPLETE_FOR_DECLARED_PROJECTIONS')
        self.assertEqual(value['index_status']['query_snapshot_binding'], 'ESTABLISHED')
        self.assertEqual(proof['result_semantics'], 'native_filters_ranking_limits;not_unrestricted_absence_proof')
        return proof

    def refused(self, value, reason=None):
        self.assertIs(value['success'], False, value)
        self.assertFalse({'results', 'count', 'search_snapshot'} & set(value), value)
        self.assertEqual(value['index_status']['completeness'], 'NOT_ESTABLISHED')
        if reason:
            self.assertEqual(value['reason'], reason, value)

    def test_real_scope_query_positive_negative_and_web_fence_preserve_memory(self):
        with self.active():
            turn, _ = self.fail_search()
            with n.wc.bind_web_call(self.call(turn, name='memory-call')):
                n.us.guard_tool('session_search', {'query': 'composeneedle'})
                hit = self.query()
                self.proof(hit, 1)
                self.assertNotIn('foreign-secret', json.dumps(hit))
                self.proof(self.query('genuine-absent'), 0)
                denied = self.dispatch(self.call(turn), 'web_extract', {'urls': ['https://fixture.test']})
                self.assertIn('error', json.loads(denied))
            self.assertEqual(len(self.fx.spawns), 1)
            OBS.append({'control': self._testMethodName, 'real_native_scope': True,
                        'memory_proof': True, 'false_empty': False, 'web_spawns': 1})

    def test_native_current_exclude_hidden_and_foreign_preserved(self):
        self.seed(self.db, self.caps[0], 'current', 'composeneedle current')
        self.seed(self.db, self.caps[0], 'excluded', 'composeneedle excluded')
        self.seed(self.db, self.caps[0], 'hidden', 'composeneedle hidden', source='subagent')
        with self.active():
            value = self.query(current_session_id='current', exclude_session_ids=['excluded'])
            self.proof(value, 1)
            self.assertEqual(value['results'][0]['session_id'], 'past')
            self.assertEqual(self.query(profile='b'), {'success': False, 'error': 'product_user_scope_refused'})
            foreign = json.loads(session_search(query='composeneedle', db=self.dbs[1]))
            self.assertEqual(foreign, {'success': False, 'error': 'product_user_scope_refused'})

    def test_native_scope_foreign_rows_refuse_before_ram_copy(self):
        self.db._conn.execute("UPDATE sessions SET user_id='other'")
        self.db._conn.commit()
        with self.active(), patch.object(snap._SLOTS, 'acquire', side_effect=AssertionError('must not copy')):
            self.assertEqual(self.query(), {'success': False, 'error': 'product_user_scope_refused'})

    def test_actual_content_index_corruption_never_returns_false_empty(self):
        row = self.db._conn.execute('SELECT id,content,tool_name,tool_calls FROM messages').fetchone()
        self.db._conn.execute("INSERT INTO messages_fts(messages_fts,rowid,content,tool_name,tool_calls) VALUES('delete',?,?,?,?)", tuple(row))
        self.db._conn.commit()
        with self.active():
            self.refused(self.query(), 'sqlite_snapshot_failed')

    def test_arbitrary_hydration_fault_is_typed_and_resources_released(self):
        def broken(db, *args, **kw):
            raise RuntimeError('PRIVATE_TRACE_MUST_NOT_ESCAPE')
        with self.active():
            with patch.object(snap._SnapshotDB, 'get_anchored_view', broken):
                value = self.query()
            self.refused(value, 'discovery_data_failed')
            self.assertNotIn('PRIVATE_TRACE', json.dumps(value))
            self.proof(self.query(), 1)

    def test_runtime_marker_fault_is_typed_without_private_detail(self):
        from tools.session_search_tool import _discover_payload
        def broken():
            raise RuntimeError('PRIVATE_MARKER_TRACE')
        value = json.loads(_discover_payload(SimpleNamespace(fts_rebuild_status=broken), 'query', 'adaptive', []))
        self.refused(value)
        self.assertEqual(value['error'], 'session_search_index_status_failed')
        self.assertNotIn('PRIVATE_MARKER', json.dumps(value))

    def test_real_marker_invalid_ranges_refuse_without_proof(self):
        with self.active():
            for entries in [[('fts_rebuild_progress', '1')], [('fts_rebuild_high_water', None)],
                    [('fts_rebuild_high_water', str(1 << 63))],
                    [('fts_rebuild_high_water', '1'), ('fts_rebuild_progress', '2')]]:
                self.db._conn.execute("DELETE FROM state_meta WHERE key LIKE 'fts_rebuild_%'")
                self.db._conn.executemany('INSERT INTO state_meta VALUES (?,?)', entries)
                self.db._conn.commit()
                self.refused(self.query())

    def test_actual_message_eligibility_boundary_not_new_product_limit(self):
        for i in range(199):
            self.db.append_message('past', role='assistant', content=f'bounded filler {i}')
        with self.active():
            self.assertEqual(self.proof(self.query(), 1)['message_count'], 200)
            self.db.append_message('past', role='assistant', content='201st filler')
            expected = json.loads(_discover_impl(self.db, query='composeneedle', role_filter=None,
                limit=3, sort=None, detail='adaptive'))
            with patch.object(snap._SLOTS, 'acquire', side_effect=AssertionError('must not allocate RAM')):
                value = self.query()
                miss = self.query('genuine-absent')
            self.assertEqual(value['results'], expected['results'])
            for result in [value, miss]:
                self.assertNotIn('search_snapshot', result)
                self.assertEqual(result['index_status']['completeness'], 'NOT_ESTABLISHED')
                self.assertEqual(result['index_status']['attestation_reason'], 'message_count_exceeds_checked_subset')
            self.assertEqual(miss['count'], 0)
            self.assertIn('not established', miss['message'])

    def test_real_database_size_eligibility_remains_native_compatible(self):
        self.db._conn.execute('CREATE TABLE fixture_large_unrelated(x BLOB)')
        self.db._conn.execute('INSERT INTO fixture_large_unrelated VALUES (zeroblob(?))', (17 * 1024 * 1024,))
        self.db._conn.commit()
        with self.active(), patch.object(snap._SLOTS, 'acquire', side_effect=AssertionError('must not allocate RAM')):
            value = self.query()
            self.assertIs(value['success'], True, value)
            self.assertEqual(value['count'], 1)
            self.assertNotIn('search_snapshot', value)
            self.assertEqual(value['index_status']['attestation_reason'], 'database_size_exceeds_checked_subset')

    def test_real_content_size_eligibility_remains_native_compatible(self):
        self.db.append_message('past', role='tool', content='z' * (4 * 1024 * 1024 + 1))
        with self.active(), patch.object(snap._SLOTS, 'acquire', side_effect=AssertionError('must not allocate RAM')):
            value = self.query()
            self.assertIs(value['success'], True, value)
            self.assertEqual(value['count'], 1)
            self.assertNotIn('search_snapshot', value)
            self.assertEqual(value['index_status']['attestation_reason'], 'content_size_exceeds_checked_subset')


    def test_read_vm_capacity_time_failures_release_for_later_request(self):
        with self.active():
            for name, value, reason in [('_MAX_SECONDS', -1, 'time_budget_exceeded')]:
                with patch.object(snap, name, value):
                    self.refused(self.query(), reason)
                self.proof(self.query(), 1)
            def actual_vm_load(db, *args, **kw):
                try:
                    db._conn.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<10000) SELECT sum(x) FROM n').fetchall()
                except sqlite3.Error:
                    pass  # Deliberate negative control: native fail-open still cannot attest.
                return []
            with patch.object(snap, '_MAX_VM_STEPS', 0), \
                    patch.object(snap._SnapshotDB, 'search_messages', actual_vm_load):
                self.refused(self.query(), 'execution_budget_exceeded')
            self.proof(self.query(), 1)
            with patch.object(self.db._read_budget, 'acquire', return_value=False):
                self.refused(self.query(), 'native_read_capacity_exceeded')
            self.proof(self.query(), 1)
            self.assertTrue(snap._SLOTS.acquire(False))
            self.assertTrue(snap._SLOTS.acquire(False))
            try:
                self.refused(self.query(), 'snapshot_capacity_exceeded')
            finally:
                snap._SLOTS.release()
                snap._SLOTS.release()
            self.proof(self.query(), 1)

    def receipt(self, name, args, turn=None, cid='receipt-call'):
        value = json.loads(self.dispatch(self.call(turn, name=cid), name, args))
        receipt = value.pop('_friday_scope_receipt')
        canonical = lambda value: (json.dumps(value, ensure_ascii=True, sort_keys=True) + '\n').encode()
        self.assertEqual(receipt['result_sha256'], hashlib.sha256(canonical(value)).hexdigest())
        self.assertEqual(receipt['arguments_sha256'], hashlib.sha256(canonical(args)).hexdigest())
        self.assertEqual(receipt['principal_id'], self.caps[0].key)
        self.assertEqual(receipt['generation'], self.caps[0].admission_generation)
        self.assertEqual(receipt['session_id'], 's-a')
        self.assertEqual(receipt['tool_call_id'], cid)
        self.assertEqual(receipt['tool_name'], name)
        source = {'skills_list': 'tools/skills_tool.py', 'skill_view': 'agent/skill_utils.py',
                  'skill_manage': 'tools/skill_manager_tool.py'}[name]
        self.assertEqual(receipt['handler']['source'], source)
        self.assertEqual(receipt['handler']['registry_scope'], str(self.caps[0].home))
        if name == 'skill_view':
            self.assertEqual(receipt['handler']['closure'][0]['callable']['source'], 'tools/skills_tool.py')
        OBS.append({'control': 'actual-native-receipt', 'tool': name, 'handler_source': source,
                    'scope_session_call_args_result_join': True})
        return value

    def test_actual_three_skill_handlers_receipted_under_same_web_failed_turn(self):
        content = '---\nname: independent-skill\ndescription: offline composition fixture\n---\n# Fixture\nPrivate fixture text.\n'
        with self.active():
            turn, _ = self.fail_search()
            self.receipt('skills_list', {}, turn, 'actual-list')
            created = self.receipt('skill_manage', {'action': 'create', 'name': 'independent-skill', 'content': content}, turn, 'actual-manage')
            self.assertNotIn('error', created, created)
            viewed = self.receipt('skill_view', {'name': 'independent-skill'}, turn, 'actual-view')
            self.assertIn('Private fixture text', json.dumps(viewed))
            self.assertEqual(len(self.fx.spawns), 1)

    def test_missing_call_refuses_before_actual_skill_mutation(self):
        with self.active():
            before = list((self.caps[0].home / 'skills').rglob('*'))
            value = json.loads(n.mt.handle_function_call('skill_manage', {'action': 'create',
                'name': 'must-not-exist', 'content': '# Forbidden'}, 'task', tool_call_id=None,
                session_id='s-a', skip_pre_tool_call_hook=True, skip_tool_request_middleware=True,
                skip_tool_execution_middleware=True))
            self.assertIn('error', value)
            self.assertNotIn('_friday_scope_receipt', value)
            self.assertEqual(before, list((self.caps[0].home / 'skills').rglob('*')))

    def test_real_registry_register_dispatch_restore_aba_withholds_receipt(self):
        effects = []
        ids = SimpleNamespace(session_id='s-a', tool_call_id='native-aba')
        with self.active():
            original = n.registry.get_entry('skills_list')
            generation = n.registry._generation
            def substituted(args, **kw):
                effects.append('actual-B')
                return json.dumps({'success': True, 'actual': 'B'})
            def dispatch():
                n.registry.register(name='skills_list', toolset=original.toolset,
                    schema=original.schema, handler=substituted)
                replacement = n.registry.get_entry('skills_list')
                try:
                    return n.registry.dispatch('skills_list', {})
                finally:
                    self.assertTrue(n.registry.restore_registration('skills_list', replacement, original))
            with self.assertRaises(n.us.ScopeDenied):
                n.mt._friday_skill_dispatch('skills_list', {}, ids, dispatch)
            self.assertEqual(effects, ['actual-B'])
            self.assertIs(n.registry.get_entry('skills_list'), original)
            self.assertGreaterEqual(n.registry._generation, generation + 2)
            self.receipt('skills_list', {}, cid='after-aba')
            OBS.append({'control': 'native-register-dispatch-restore-ABA',
                        'generation_advanced': n.registry._generation - generation,
                        'effect_count': len(effects), 'receipt_refused': True,
                        'post_effect_refusal_is_not_rollback': True})

    def test_commit_between_own_scope_check_and_backup_is_same_admitted_snapshot(self):
        original = snap._check_database_rows
        calls = []
        def check_then_commit(cap, source):
            original(cap, source)
            calls.append('admitted-before-concurrent-write')
            with sqlite3.connect(self.db.db_path) as writer:
                writer.execute("UPDATE messages SET content='later-replacement-no-match'")
        with self.active(), patch.object(snap, '_check_database_rows', check_then_commit):
            value = self.query()
        self.proof(value, 1)
        self.assertEqual(len(calls), 1)
        self.assertIn('composeneedle', json.dumps(value['results']))
        self.assertNotIn('later-replacement', json.dumps(value))
        self.assertEqual(self.db._conn.execute('SELECT content FROM messages').fetchone()[0], 'later-replacement-no-match')

    def test_compatibility_decode_failure_refuses_without_false_empty_or_retry(self):
        for i in range(200):
            self.db.append_message('past', role='assistant', content=f'compat filler {i}')
        self.db._conn.execute("UPDATE messages SET display_metadata='{invalid' WHERE role='user'")
        self.db._conn.commit()
        calls = []
        original = snap._SnapshotDB.search_messages
        def read_once(db, *args, **kw):
            calls.append('one-native-query')
            return original(db, *args, **kw)
        with self.active(), patch.object(snap._SnapshotDB, 'search_messages', read_once):
            value = self.query()
        self.refused(value, 'discovery_data_failed')
        self.assertEqual(calls, ['one-native-query'])

    def test_native_cap_revocation_after_real_mutation_withholds_receipt(self):
        args = {'action': 'create', 'name': 'effect-before-revoke',
                'content': '---\nname: effect-before-revoke\ndescription: explicit offline fixture\n---\n# Created\n'}
        ids = SimpleNamespace(session_id='s-a', tool_call_id='post-effect-revoke')
        effects = []
        cap = self.caps[0]
        with self.active():
            def dispatch():
                value = n.registry.dispatch('skill_manage', args)
                self.assertNotIn('error', json.loads(value), value)
                effects.append('created')
                cap.revoked = True
                return value
            try:
                with self.assertRaises(n.us.ScopeDenied):
                    n.mt._friday_skill_dispatch('skill_manage', args, ids, dispatch)
            finally:
                cap.revoked = False  # Fixture cleanup only; never a product authority repair.
            self.assertEqual(effects, ['created'])
            self.assertTrue(any(p.name == 'SKILL.md' for p in (cap.home / 'skills').rglob('*')))
            OBS.append({'control': 'native-cap-post-effect-revocation', 'effect_count': 1,
                        'receipt_refused': True, 'rollback_claimed': False, 'retry_permission_claimed': False})


if __name__ == '__main__':
    web_names = ['test_direct_lazy_registry_same_turn_stop_no_three_url_extract',
        'test_transport_family_guard_and_scope_capability_restrictions',
        'test_native_concurrent_batch_dispatch_direct_and_lazy',
        'test_cancellation_stays_sticky_and_delegated_turn_is_shared',
        'test_actual_delegation_record_and_native_turn_reset_preserve_web_lifecycle',
        'test_cleanup_receipt_exception_retains_unconfirmed_native_ownership']
    own_names = [name for name in unittest.defaultTestLoader.getTestCaseNames(Composition)
                 if name in Composition.__dict__]
    suite = unittest.TestSuite(n.NativeControls(name) for name in web_names)
    suite.addTests(Composition(name) for name in own_names)
    names = [test.id() for test in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    loaded = {name: {'source': str(Path(module.__file__).relative_to(n.BASE)),
                    'sha256': hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()}
              for name, module in sorted(sys.modules.items())
              if getattr(module, '__file__', None)
              and Path(module.__file__).is_relative_to(n.BASE)
              and Path(module.__file__).is_file()}
    value = {'schema': 'friday.public-source90-native-controls.v1',
        'state': 'PASS' if result.wasSuccessful() else 'FAIL',
        'tests': result.testsRun, 'test_names': names, 'failures': len(result.failures),
        'errors': len(result.errors), 'skipped': len(result.skipped),
        'observations': OBS + n.OBS, 'loaded_native_sources': loaded,
        'python': sys.version, 'sqlite': sqlite3.sqlite_version,
        'seams': ['synthetic product-access and principal records',
                  'finite local provider child replaces transport and native custody launch',
                  'tool catalog capability declaration; presentation middleware wrapper'],
        'real': ['native UserScope guards', 'native direct/lazy/registry/batch dispatch',
                 'native memory SQLite snapshot/proof', 'three native skill handlers and provenance'],
        'CJK_extension_control': 'NOT_RUN by this portable subset; requires separately supplied native extension',
        'model_network_telegram_installed_activation': 'NOT_RUN',
        'all_fixture_provider_children_reaped': True}
    n.ROOT_TMP.cleanup()
    print(json.dumps(value, indent=2, sort_keys=True))
    raise SystemExit(not result.wasSuccessful())
