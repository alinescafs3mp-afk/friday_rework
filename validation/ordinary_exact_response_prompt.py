"""Finite source-level integration control; all admission/storage seams are fixtures.

Reads only the supplied final native source tree. No real DB, lifecycle hook,
model, transport or network is invoked. The normal native restore/build function
is selected intact from AST; its security decorator is represented by an explicit
fixture identity guard, and current capability/database validators are fixtures.
"""
import ast
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import types

os.umask(0o077)
sys.dont_write_bytecode = True
native = Path(sys.argv[1])
pins = {
    'agent/onboarding.py': 'd492d64d2258b5952b8f28904fabaf098485841f25fddc49ad02c89a4ca10e6f',
    'hermes_cli/friday_prompt_scope.py': '438e20d5d8922a218ca2eb69ef4822dcd9f2cc1af41ee98885b3dae04fe37702',
}
checks = []

def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append({'name': name, 'state': 'PASS'})

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

check('final accepted two source bodies', all(digest(native / name) == pin for name, pin in pins.items()))
scope_seam = types.ModuleType('hermes_cli.friday_user_scope')
class ScopeDenied(PermissionError):
    pass
scope_seam.ScopeDenied = ScopeDenied
scope_seam.current = lambda **kwargs: None
scope_seam.check_agent = lambda value: None
scope_seam.check_database = lambda value: None
sys.modules[scope_seam.__name__] = scope_seam
scope = types.ModuleType('final_friday_prompt_scope')
exec(compile((native / 'hermes_cli/friday_prompt_scope.py').read_bytes(), str(native / 'hermes_cli/friday_prompt_scope.py'), 'exec'), scope.__dict__)

class Cap:
    key = 'fixture-principal'
    admission_generation = 1
    home = Path('/nonexistent-private-fixture')
    directory_identity = (1, 2)
    def check(self):
        return self
cap = Cap()
scope.current = lambda **kwargs: cap
scope.check_database = lambda value: None if value is cap else (_ for _ in ()).throw(ScopeDenied())
agent = types.SimpleNamespace(session_id='fixture-session', platform='telegram', model='unchanged-fixture-model', provider='unchanged-fixture-provider')
scope.check_agent = lambda value: None if value is agent else (_ for _ in ()).throw(ScopeDenied())
old_prompt = 'old native v6 fixture prompt'
old_stamp = scope._stamp(cap, agent.session_id, old_prompt)
old_stamp['dialogue_revision'] = 'friday.public-identity.v6'
row = {'system_prompt': old_prompt, 'model_config': json.dumps({scope.FIELD: old_stamp}), 'tool_names': '["stale_fixture_tool"]', 'history_sentinel': ['retained message']}
history = [{'role': 'user', 'content': 'retained fixture question'}]
history_before = copy.deepcopy(history)
events = []
class DB:
    db_path = cap.home / 'state.db'
    reads = 0
    writes = 0
    def get_session(self, session_id):
        assert session_id == agent.session_id
        self.reads += 1
        return copy.deepcopy(row)
    def update_system_prompt(self, session_id, prompt):
        assert session_id == agent.session_id
        self.writes += 1
        row['system_prompt'] = prompt
        row['model_config'] = json.dumps({scope.FIELD: scope.for_persistence(self, session_id, prompt)})
agent._session_db = DB()
agent._build_system_prompt = lambda message: events.append(('build', message)) or '\n'.join(scope.dialogue_parts(agent)) + '\n' + scope.ordinary_platform_hint(agent, 'You are on Telegram. MEDIA:/absolute/path/to/file')
function_names = {'_restore_or_build_system_prompt', '_persist_system_prompt'}
tree = ast.parse((native / 'agent/conversation_loop.py').read_bytes())
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in function_names]
assert {n.name for n in functions} == function_names
runtime = {
    '_friday_guard_skill_read': lambda f: f,
    '_friday_prompt_scope': scope,
    'logger': logging.getLogger('finite-source88-fixture'),
    '_stored_prompt_matches_runtime': lambda a, p: True,
    '_bot_chat_prompt_stale': lambda a, p: False,
    '_restore_pinned_tools': lambda a, r: events.append(('restore_tools', copy.deepcopy(r))) or ['current_fixture_tool'],
    'stage_surface_switch_note': lambda *args: False,
    'note_inert_pinned_tools': lambda *args: None,
    'record_prompt_rebuild': lambda *args: events.append(('record_rebuild', args[2])),
}
exec(compile(ast.Module(body=functions, type_ignores=[]), 'final-native-restore-build-selected', 'exec'), runtime)
for name in ['tools.mcp_tool_agent', 'hermes_cli.lifecycle', 'agent.credits_tracker', 'agent.system_prompt']:
    sys.modules[name] = types.ModuleType(name)
def persist_fixture_tool_names(a):
    events.append(('persist_tools',))
    row['tool_names'] = json.dumps(['current_fixture_tool'])
sys.modules['tools.mcp_tool_agent'].persist_agent_tool_names = persist_fixture_tool_names
sys.modules['hermes_cli.lifecycle'].invoke_hook = lambda *args, **kwargs: events.append(('fixture_native_hook', args[0]))
sys.modules['agent.credits_tracker'].seed_credits_at_session_start = lambda a: None
sys.modules['agent.system_prompt'].reconstruct_static_prefix = lambda *args, **kwargs: None
sys.modules['agent.system_prompt'].restore_plugin_prompt_sections = lambda *args: None
restore = runtime['_restore_or_build_system_prompt']
restore(agent, 'unchanged fixture system message', history)
new_prompt = row['system_prompt']
new_stamp = json.loads(row['model_config'])[scope.FIELD]
check('stale v6 follows native rebuild and persists v7 once', len([e for e in events if e[0] == 'build']) == 1 and agent._session_db.writes == 1 and new_stamp['dialogue_revision'] == 'friday.public-identity.v7' and new_prompt == agent._cached_system_prompt and new_prompt != old_prompt)
check('stale v6 discards stale tool row before current admission build', [e for e in events if e[0] == 'restore_tools'] == [('restore_tools', None)])
check('normal rebuilt prompt contains accepted guidance and caption contract', scope.DIALOGUE_GUIDANCE in new_prompt and scope.CONFIDENTIALITY_GUIDANCE in new_prompt and 'If the user specifies exact caption text' in new_prompt and 'If the user explicitly requests no caption' in new_prompt)
check('history and unrelated stored fields retained in fixture', history == history_before and row['history_sentinel'] == ['retained message'])
check('rebuild requests current tool pin persistence through declared fixture seam', row['tool_names'] == '["current_fixture_tool"]' and ('persist_tools',) in events)
events.clear()
restore(agent, 'same fixture system message', history)
check('next exact v7 restores native persisted bytes without second rebuild/write', not any(e[0] == 'build' for e in events) and agent._session_db.writes == 1 and agent._cached_system_prompt == new_prompt and any(e[0] == 'restore_tools' and e[1] is not None for e in events))
before = (agent._session_db.reads, agent._session_db.writes, copy.deepcopy(events))
scope.check_agent = lambda value: (_ for _ in ()).throw(ScopeDenied())
try:
    restore(agent, 'denied fixture', history)
except ScopeDenied:
    denied = True
else:
    denied = False
check('denied scope stops before restore/build/persistence', denied and before == (agent._session_db.reads, agent._session_db.writes, events))
check('final accepted source unchanged after finite control', all(digest(native / name) == pin for name, pin in pins.items()))
print(json.dumps({'state': 'PASS', 'checks': checks, 'native_source': str(native), 'native_restore_source_sha256': digest(native / 'agent/conversation_loop.py'), 'count': len(checks), 'limits': 'Source-level native restore/build/persist integration with explicit fake admission, in-memory session DB, lifecycle/credits/tool seams; no live acceptance or actual database effects.'}, ensure_ascii=False, indent=2))
