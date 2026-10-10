"""Execute selected actual source bodies with explicit inert authority/I/O fixtures.

No native module initializer, model, process, service, database or runtime gate
is executed. These are finite source controls, not installed isolation proof.
"""
import argparse
import ast
import builtins
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from types import SimpleNamespace as S
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'base', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    rows, pins, modules = [], {}, {}

    def read(path):
        data = path.read_bytes()
        pins[str(path)] = hashlib.sha256(data).hexdigest()
        return data

    def importer(name, globals=None, locals=None, fromlist=(), level=0):
        assert level == 0 and name in modules, ('unexpected native import', name)
        return modules[name]

    def selected(path, names, env, cls=None):
        nodes = ast.parse(read(path)).body
        if cls:
            nodes = next(n for n in nodes if isinstance(n, ast.ClassDef) and n.name == cls).body
        wanted = [copy.deepcopy(n) for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
        assert len(wanted) == len(names)
        for n in wanted:
            n.decorator_list = []
        env['__builtins__'] = {**vars(builtins), '__import__': importer}
        exec(compile(ast.fix_missing_locations(ast.Module(body=wanted, type_ignores=[])), str(path), 'exec',
                     flags=0x1000000), env)
        return env

    def check(name, call):
        call()
        rows.append({'name': name, 'status': 'PASS'})

    def truth(value):
        assert value

    native_path = args.candidate / 'tools/process_registry.py'
    results_path = args.candidate / 'tools/process_registry_results.py'
    scope_path = args.base / 'hermes_cli/friday_user_scope.py'
    helper_path = args.candidate / 'tools/process_registry_authority.py'
    for path in (native_path, results_path, helper_path):
        ast.parse(read(path))
    check('three_native_sources_parse', lambda: None)

    class Denied(PermissionError):
        pass

    state = {'pin': {'principal': ['transport', 'profile', 'account', 'alice'],
                     'profile': 'alice', 'home': '/fixture/alice', 'authorization_home': '/fixture/admin',
                     'binding_sha256': 'a' * 64, 'generation': 'generation1'},
             'lost': False, 'enabled': True, 'marker': False}
    def current():
        if state['lost']:
            raise Denied()
        p = state['pin']
        return None if p is None else S(principal=p['principal'], profile=p['profile'], home=p['home'],
               authorization_home=p['authorization_home'], binding={'fixture': True}, admission_generation=p['generation'])
    def agent_check(agent):
        if agent.authority != state['pin'] or agent.cancelled:
            raise Denied()
    def guard(name, args):
        current()
        if not state['enabled']:
            raise Denied()
    class Marker:
        def __truediv__(self, other): return self
        def exists(self): return state['marker']
    modules['hermes_constants'] = S(get_hermes_home=lambda: Marker())
    scope = selected(scope_path, ['delegation_authority', 'delegation_visible'],
                     {'current': current, 'ScopeDenied': Denied, '_fingerprint': lambda value: 'a' * 64,
                      'MARKER': '.fixture-marker'})
    modules['hermes_cli.friday_user_scope'] = S(**scope, check_agent=agent_check, guard_tool=guard)
    env = selected(helper_path, ['capture_authority', 'visible', 'require_visible', 'resolve_visible',
                                'check_handoff', 'handle_process'], {'json': json})
    modules['tools.process_registry_authority'] = S(**env)
    original = copy.deepcopy(state['pin'])
    own = S(id='proc_abcd1111', user_authority=copy.deepcopy(original), command='own')
    foreign = S(id='proc_abcd2222', user_authority={**original, 'profile': 'bob'}, command='foreign')
    legacy = S(id='proc_cafe1111', user_authority=None, command='legacy')
    refreshed = []
    reg = S(_lock=threading.Lock(), _MIN_PREFIX_CHARS=4, _running={s.id: s for s in (own, foreign, legacy)},
            _finished={}, _refresh_detached_session=lambda session: refreshed.append(session.id) or session)
    modules['tools.process_registry_results'] = S(load_completed_results=lambda prefix='': {})
    check('current_authority_resolves_own_exact', lambda: truth(env['resolve_visible'](reg, own.id) is own))
    refreshed.clear()
    check('foreign_exact_refused_before_refresh', lambda: truth(env['resolve_visible'](reg, foreign.id) is None and not refreshed))
    check('foreign_prefix_does_not_disclose_or_create_ambiguity', lambda: truth(env['resolve_visible'](reg, 'abcd') is own))
    check('unscoped_legacy_not_adopted', lambda: truth(env['resolve_visible'](reg, legacy.id) is None))
    state['pin'] = {**original, 'generation': 'generation2'}
    check('new_grant_cannot_adopt_original_process', lambda: truth(env['resolve_visible'](reg, own.id) is None))
    state['pin'] = original
    twin = S(id='proc_abcd3333', user_authority=original)
    reg._running[twin.id] = twin
    check('two_visible_prefix_matches_refused', lambda: truth(env['resolve_visible'](reg, 'abcd') is None))
    reg._running.pop(twin.id)
    for field in ('principal', 'profile', 'home', 'authorization_home', 'binding_sha256', 'generation'):
        pin = {**original, field: ['foreign'] if field == 'principal' else 'foreign'}
        check('authority_mismatch_' + field, lambda pin=pin: truth(not env['visible'](pin)))
    check('malformed_retained_identity_refused', lambda: truth(not env['visible']('alice')))
    state['lost'] = True
    check('lost_context_refuses_retained_identity', lambda: truth(not env['visible'](original)))
    state['lost'] = False
    state['pin'] = None
    check('unscoped_cannot_read_scoped_process', lambda: truth(not env['visible'](original)))
    check('legacy_unscoped_visibility_preserved', lambda: truth(env['visible'](None)))
    state['marker'] = True
    check('marked_home_without_scope_refused', lambda: truth(not env['visible'](None)))
    state.update(pin=original, marker=False)

    actions = ['poll', 'log', 'wait', 'kill', 'write', 'submit', 'close']
    calls = []
    def operation(sid, args):
        calls.append((args['action'], sid))
        return {'status': 'fixture', 'output': 'private-output'}
    native = S(process_registry=reg, tool_error=lambda text: json.dumps({'error': text}),
               _SESSION_ACTIONS={name: (operation, True) for name in actions},
               _redact_process_result=lambda result: result,
               _handoff_process=lambda sid, args, task: operation(sid, args),
               _list_processes=lambda task: {'processes': []})
    modules['tools'] = S(process_registry=native)
    for name in actions + ['handoff']:
        calls.clear()
        result = json.loads(env['handle_process']({'action': name, 'session_id': foreign.id}, task_id='owner'))
        check('no_foreign_effect_' + name, lambda result=result: truth(result == {'error': 'product_user_scope_refused'} and not calls))
        result = json.loads(env['handle_process']({'action': name, 'session_id': 'abcd'}, task_id='owner'))
        check('own_canonical_id_dispatch_' + name, lambda result=result, name=name: truth(result['status'] == 'fixture' and calls == [(name, own.id)]))
    def revoke_during_wait(sid, args):
        state['lost'] = True
        return {'output': 'must-not-escape'}
    native._SESSION_ACTIONS['wait'] = (revoke_during_wait, False)
    result = json.loads(env['handle_process']({'action': 'wait', 'session_id': own.id}))
    check('revocation_during_wait_suppresses_output', lambda: truth(result == {'error': 'product_user_scope_refused'}))
    state.update(lost=False, enabled=False)
    calls.clear()
    for name in actions + ['list', 'handoff']:
        result = json.loads(env['handle_process']({'action': name, 'session_id': own.id}))
        assert result == {'error': 'product_user_scope_refused'} and not calls
    check('tool_allowlist_refusal_precedes_every_process_action', lambda: None)
    state['enabled'] = True
    good = S(authority=original, cancelled=False)
    env['check_handoff'](good, good, own)
    check('same_retained_parent_child_handoff_allowed', lambda: None)
    for bad in [S(authority={**original, 'generation': 'generation2'}, cancelled=False),
                S(authority=original, cancelled=True)]:
        for child, parent in [(bad, good), (good, bad)]:
            try: env['check_handoff'](child, parent, own)
            except Denied: pass
            else: raise AssertionError('foreign/cancelled handoff permitted')
    check('handoff_rejects_foreign_or_cancelled_parent_and_child', lambda: None)

    modules['gateway.session_context'] = S(get_session_env=lambda key, default='': 'conversation')
    spawn = selected(native_path, ['_new_session'], {'ProcessSession': lambda **kw: S(**kw),
                     'uuid': uuid, 'time': time, '_is_wsl_launcher_command': lambda command: False}, 'ProcessRegistry')
    session = spawn['_new_session']('command', 'container', 'raw-owner', 'session', '/cwd')
    check('native_constructor_captures_original_authority_and_raw_owner', lambda: truth(session.user_authority == original and session.owner_task_id == 'raw-owner' and session.task_id == 'container'))
    state['pin'] = {**original, 'generation': 'generation2'}
    check('retained_pin_not_rebound_by_new_grant', lambda: truth(session.user_authority == original))
    state['pin'] = original

    # The native list filters BEFORE PID refresh; its trusted default is
    # deliberately unfiltered so revoked-owner cleanup can still find targets.
    for i, s in enumerate((own, foreign, legacy)):
        s.owner_task_id='owner';s.session_key='same-session';s.cwd='/cwd';s.pid=None;s.started_at=time.time()
        s.exited=False;s.output_buffer='private';s.wsl_chain=False;s.watch_patterns=[];s.notify_on_complete=False
        s.persist_on_release=False;s.detached=False
    reg._uncollected_gone=lambda s:False
    reg._reconcile_local_exit=lambda s:None
    lists = selected(native_path, ['list_sessions'], {'load_completed_results':lambda:{}, 'time':time}, 'ProcessRegistry')
    refreshed.clear()
    output=lists['list_sessions'](reg, task_id='owner', visible_only=True)
    check('shared_task_and_session_keys_do_not_leak_foreign_rows', lambda:truth([r['session_id'] for r in output]==[own.id] and refreshed==[own.id]))
    state['lost']=True
    output=lists['list_sessions'](reg)
    check('trusted_cleanup_enumeration_survives_revocation',lambda:truth(len(output)==3))
    state['lost']=False

    base_tree=ast.parse(read(args.base/'tools/process_registry.py'))
    new_tree=ast.parse(read(native_path))
    def method(tree,name):
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ProcessRegistry')
        return next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    for name in ('get','kill_process','kill_all','kill_started_since','_reap_untracked','running_owned_by'):
        assert ast.dump(method(base_tree,name))==ast.dump(method(new_tree,name))
    check('trusted_stop_and_lookup_bodies_unchanged',lambda:None)
    # Exact durable field contracts: legacy rows have no authority; no loader
    # can invent current authority when reconstructing a retained result.
    for tree,name in [(new_tree,'_CHECKPOINT_FIELDS'),(ast.parse(read(results_path)),'_RESULT_FIELDS')]:
        node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
        assert any(isinstance(n,ast.Constant) and n.value=='user_authority' for n in ast.walk(node))
    check('checkpoint_and_completed_result_both_retain_authority',lambda:None)
    result_tree=ast.parse(read(results_path))
    fields=ast.literal_eval(next(n.value for n in result_tree.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='_RESULT_FIELDS' for t in n.targets)))
    record={key:'' for key in fields}
    record.update(id=own.id,user_authority=copy.deepcopy(original),parent_session_id='conversation',output='private')
    class ResultPath:
        stem=own.id
        name=own.id+'.json'
        def read_text(self,encoding):return json.dumps(record)
    def make_result(**kw):return S(**kw,_completion_event=threading.Event())
    modules['tools.process_registry']=S(ProcessSession=make_result)
    log=S(warning=lambda *a,**k:None,debug=lambda *a,**k:None)
    loader=selected(results_path,['load_completed_results'],{'_result_paths':lambda:[ResultPath()],
        '_RESULT_FIELDS':fields,'_owns_result':lambda owner,parent:owner==parent,'json':json,'re':re,
        'sqlite3':sqlite3,'logger':log})['load_completed_results']
    loaded=loader()
    check('retained_result_load_keeps_original_identity',lambda:truth(loaded[own.id].user_authority==original))
    record['user_authority']={**original,'generation':'generation0'}
    check('retained_result_old_generation_filtered',lambda:truth(not loader()))
    record['user_authority']={**original,'profile':'bob'}
    check('retained_result_foreign_profile_filtered',lambda:truth(not loader()))
    record.pop('user_authority')
    check('legacy_receipt_not_adopted_by_scoped_user',lambda:truth(not loader()))
    state['pin']=None
    loaded=loader()
    check('legacy_receipt_unscoped_compatibility_preserved',lambda:truth(loaded[own.id].user_authority is None))
    state['pin']=original
    scope_tree=ast.parse(read(scope_path))
    safe=next(n for n in scope_tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SAFE' for t in n.targets))
    allowed=ast.literal_eval(safe.value.args[0])
    assert 'terminal' not in allowed and 'process_manage' not in allowed
    check('ordinary_terminal_and_process_remain_disabled',lambda:None)
    report={'status':'SOURCE_CONTROLS_PASS','checks':rows,'count':len(rows),'source_pins':pins,
            'method':'selected actual AST bodies with explicit inert scope, admission, registry, I/O and agent fixtures',
            'native_module_imports':False,'installed_runtime':False,'runtime_acceptance':'NOT_RUN',
            'limitations':['No OS isolation, service launch, PTY, process stop, real admission/database or notification delivery exercised.']}
    args.output.write_text(json.dumps(report,indent=2)+'\n');args.output.chmod(0o600)
    print(json.dumps({'status':report['status'],'checks':len(rows)}))


if __name__=='__main__':
    main()
