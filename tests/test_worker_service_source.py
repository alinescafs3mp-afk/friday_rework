"""Pure public service-source compatibility controls, with synthetic data only.

Run directly with stdlib unittest. FRIDAY_WORKER_DECLARATIONS_CANDIDATE may
select an exact candidate file; the default is the repository-relative module.
No package initializers, native imports, installed files, workers or services
are involved. These controls cannot grant native execution authority.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest


MODULE_PATH = Path(os.environ.get('FRIDAY_WORKER_DECLARATIONS_CANDIDATE',
    Path(__file__).resolve().parents[1] /
    'plugins/friday_rework/worker_declarations.py'))
SPEC = importlib.util.spec_from_file_location('standalone_worker_declarations', MODULE_PATH)
declaration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(declaration)

ANCHOR = {
    'scripts/a0_runtime.py': 'd46880a70ac70dadefb56281d21137e1aa12e1042f71e47ba455956e2477cc32',
    'scripts/rootless_docker_launch.py': 'b6825c510a7b50be20419fc0f57fee042dc9beef6d10a58b10fef1592da2fd77',
    'plugins/friday_rework/adapters/a0_profile.py': 'a0ebc0925111dfb06c99e381c20a8cea079761e9ddea8ef2ef2af7a68cc57bc9',
    'plugins/friday_rework/adapters/a0_web.py': '1daf09d50e2443d0984b26d40356478c7a3d210ccd373d92e0781ec5e78d7bf0',
    'scripts/friday-rework-docker.service': '53e6d86ff912f4ad0761362bc5e7937d2131e48892469236be09db6b49bcd0ba',
}
TARGET = dict(ANCHOR, **{
    'scripts/a0_runtime.py': 'f02f471dc6546999e8d33d004768650ab51f3eefe5d1ab36b1ab0eee928f59b8',
    'plugins/friday_rework/adapters/a0_web.py': 'ba8c7a73ef8452184d1b832fc207f1d954a8efe15ac0b8ab799b5b1986a34d76',
})
CHANGED = {'plugins/friday_rework/adapters/a0_web.py', 'scripts/a0_runtime.py'}
SETTINGS = ('plugins', 'entries', 'friday_rework', 'settings')
TEMPLATE = SETTINGS + ('onboarding', 'templates', 'friday-local')
TEMPLATE_INPUTS = TEMPLATE + ('worker_inputs',)
TEMPLATE_A0 = TEMPLATE + ('config', 'a0_deployment')
HOME = Path('/synthetic-service-fixture/home')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def ref(path, sha='a' * 64):
    return {'path': str(path), 'sha256': sha}


def get(value, path):
    for part in path:
        value = value[part]
    return value


def put(value, path, replacement):
    get(value, path[:-1])[path[-1]] = replacement


def worker_inputs():
    deployment = {'name': 'synthetic-main',
        'chat': {'endpoint': 'http://192.0.2.1:8000/v1', 'model': 'synthetic-main',
                 'context_length': 1024, 'max_output_tokens': 256, 'timeout': 60},
        'utility': {'endpoint': 'http://192.0.2.2:8000/v1', 'model': 'synthetic-utility'},
        'embedding': {'endpoint': 'http://192.0.2.3:8000/v1', 'model': 'synthetic-embedding'}}
    policy = ref(HOME / 'synthetic-inputs/network.nft', 'b' * 64)
    return {'required': ['dsh', 'a0'],
        'source_scope': {'home': str(HOME), 'profile': 'default'},
        'a0_network': {'policy': policy, 'endpoints': [
            deployment[role]['endpoint'] for role in ('chat', 'utility', 'embedding')]},
        'workers': {
            'dsh': {'budget_seconds': 1, 'max_total_bytes': 4096,
                    'dsh': {'cpu_percent': 100, 'native_files': []}},
            'a0': {'budget_seconds': 60, 'max_total_bytes': 4096, 'a0': {
                'deployment': deployment,
                'runtime': ref(HOME / 'worker-runtime-source/scripts/a0_runtime.py',
                               ANCHOR['scripts/a0_runtime.py']),
                'launcher': ref(HOME / 'rootless-docker/launch.py',
                                ANCHOR['scripts/rootless_docker_launch.py']),
                'policy': copy.deepcopy(policy), 'capability': None}}}}


def fixture():
    old = worker_inputs()
    incoming = copy.deepcopy(old)
    incoming['workers']['a0']['a0']['runtime']['sha256'] = TARGET['scripts/a0_runtime.py']
    profile_home = HOME / 'profiles/synthetic-user'
    binding = {'platform': 'telegram', 'transport_profile': 'default',
        'account_id': 'synthetic-account', 'user_id': 'synthetic-user',
        'runtime_profile': profile_home.name, 'tools': ['read_file', 'friday_work']}
    profile = {'a0_deployment': copy.deepcopy(old['workers']['a0']['a0']['deployment']),
        'model': {'default': 'synthetic-main', 'base_url': 'http://192.0.2.1:8000/v1'},
        'providers': {'friday-local': {'models': {'synthetic-main': {
            'context_length': 1024, 'bounded_context': {'main_max_output_tokens': 256}}}}},
        'web': {'profile': 'synthetic-web', 'enabled': True},
        'browser': {'enabled': True}, 'preserved': {'typed': 1, 'null': None},
        'plugins': {'entries': {'friday_rework': {'settings': {'runtime': {'enabled': False}}}}}}
    root = copy.deepcopy(profile)
    get(root, SETTINGS).update(user_isolation={'bindings': [copy.deepcopy(binding)]},
        onboarding={'templates': {'friday-local': {
            'config': copy.deepcopy(profile), 'worker_inputs': copy.deepcopy(old)}}})
    root['owner_history'] = {'consumed': True, 'original_budget_seconds': 120,
                             'started_mono': 11, 'deadline_mono': 131}
    identity = {'schema': 'frw.current-dest-worker-identity.v1',
        'binding': binding, 'binding_sha256': fingerprint(binding),
        'principal': hashlib.sha256(encoded([binding[k] for k in
            ('platform', 'transport_profile', 'account_id', 'user_id')])).hexdigest(),
        'enabled': True, 'generation': 1, 'profile': str(profile_home),
        'profile_template': 'friday-ordinary-local', 'worker_attach_template': 'friday-local',
        'source_refs': {
            'root_configuration': ref(HOME / 'config.yaml'),
            'configuration': ref(profile_home / 'config.yaml', 'c' * 64),
            'onboarding': ref(profile_home / '.friday-onboarding.json'),
            'user_marker': ref(profile_home / '.friday-user-scope.json'),
            'stale_attachment': ref(profile_home / 'workers/attachment.json'),
            'access_state': ref(HOME / 'plugin-data/synthetic-namespace/state.json')}}
    bundle = {'schema': 'friday.worker-web-service-source-declaration.v1',
        'state': 'PROPOSED_NOT_APPLIED_NOT_AN_EXECUTABLE_MIGRATION_REQUEST',
        'identity_reference': ref(HOME / 'synthetic-inputs/identity.json'),
        'root_before': copy.deepcopy(identity['source_refs']['root_configuration']),
        'profile_before': copy.deepcopy(identity['source_refs']['configuration']),
        'changes': [{'document': 'root_config', 'path': list(TEMPLATE_INPUTS),
            'before_sha256': fingerprint(old),
            'after_reference': ref(HOME / 'synthetic-inputs/worker-inputs.json',
                                   fingerprint(incoming))}]}
    return SimpleNamespace(root=root, profile=profile, incoming=incoming,
                           identity=identity, bundle=bundle)


def plan(data):
    return declaration.plan_declaration_delta(data.root, data.profile,
        data.incoming, data.identity, data.bundle)


class ServiceSourceControls(unittest.TestCase):
    def refused(self, function, *args, **kwargs):
        with self.assertRaises(declaration.DeclarationError):
            function(*args, **kwargs)

    def test_public_pins_and_five_file_boundary_are_exact(self):
        self.assertEqual(set(declaration.SERVICE_FILES), set(ANCHOR))
        self.assertEqual(declaration.SERVICE_ANCHOR, ANCHOR)
        self.assertEqual(declaration.WEB_PROBE_TARGET, TARGET)
        self.assertEqual(declaration.WEB_PROBE_SERVICE_DISCRIMINATOR,
                         'PUBLIC_A0_WEB_OVERLAY_XMLRPC_EXACT')
        self.assertIs(declaration.web_probe_service_transition(ANCHOR, TARGET), True)
        changed = declaration.service_source_transition(ANCHOR, TARGET)
        self.assertEqual(len(changed), 2)
        self.assertEqual(set(changed), CHANGED)

    def test_transition_refuses_missing_extra_foreign_partial_and_rollback(self):
        cases = [(ANCHOR, ANCHOR), (TARGET, TARGET), (TARGET, ANCHOR),
                 (None, TARGET), (ANCHOR, None)]
        for name in ANCHOR:
            old = dict(ANCHOR); old.pop(name)
            new = dict(TARGET); new[name] = 'f' * 64
            cases.extend([(old, TARGET), (ANCHOR, new)])
        cases.extend([(dict(ANCHOR, foreign='a' * 64), TARGET),
                      (ANCHOR, dict(TARGET, foreign='b' * 64))])
        partial = dict(ANCHOR)
        partial['scripts/a0_runtime.py'] = TARGET['scripts/a0_runtime.py']
        cases.append((ANCHOR, partial))
        for old, new in cases:
            with self.subTest(old=old, new=new):
                self.assertIs(declaration.web_probe_service_transition(old, new), False)
                self.refused(declaration.service_source_transition, old, new)

    def test_project_projection_has_only_the_five_public_entries(self):
        project = dict(ANCHOR, **{'synthetic/retained.txt': 'd' * 64})
        self.assertEqual(declaration.service_project_sources(project), ANCHOR)
        projected = declaration.service_project_sources(project)
        projected['scripts/a0_runtime.py'] = 'f' * 64
        self.assertEqual(project['scripts/a0_runtime.py'], ANCHOR['scripts/a0_runtime.py'])
        for invalid in (None, [], False):
            self.refused(declaration.service_project_sources, invalid)

    def test_source_edges_distinguish_pending_and_unchanged(self):
        extra = {'synthetic/retained.txt': 'd' * 64}
        for old, new, changed in ((ANCHOR, ANCHOR, False),
                                  (ANCHOR, TARGET, True), (TARGET, TARGET, False)):
            self.assertIs(declaration.service_source_edge(dict(old, **extra),
                dict(new, **extra), ANCHOR), changed)
        self.assertIs(declaration.service_source_edge(ANCHOR, TARGET, ANCHOR,
                                                     target=TARGET), True)
        mixed = dict(TARGET); mixed['scripts/a0_runtime.py'] = ANCHOR['scripts/a0_runtime.py']
        for old, new in ((TARGET, ANCHOR), (mixed, TARGET), (ANCHOR, mixed), ({}, TARGET)):
            self.refused(declaration.service_source_edge, old, new, ANCHOR)
        self.refused(declaration.service_source_edge, ANCHOR, TARGET, TARGET)
        self.refused(declaration.service_source_edge, ANCHOR, TARGET, ANCHOR, target=mixed)

    def test_pending_project_returns_detached_full_current_inventory(self):
        old = {'project_files': dict(ANCHOR, **{'synthetic/retained': 'd' * 64}),
               'home': str(HOME), 'budget_seconds': 1, 'consumed': True}
        new = copy.deepcopy(old); new['project_files'].update(TARGET)
        before = encoded([old, new])
        result = declaration.pending_service_project(old, new)
        self.assertEqual(result, new['project_files'])
        result['synthetic/retained'] = 'f' * 64
        self.assertEqual(encoded([old, new]), before)
        self.assertIsNone(declaration.pending_service_project(old, old))
        for name, value in (('budget_seconds', True), ('consumed', 1), ('extra', None)):
            changed = copy.deepcopy(new); changed[name] = value
            self.refused(declaration.pending_service_project, old, changed)
        self.refused(declaration.pending_service_project, new, old)
        self.refused(declaration.pending_service_project, {}, new)

    def test_pending_target_only_accepts_reviewed_anchor_or_target(self):
        self.assertIsNone(declaration.service_pending_target(ANCHOR, ANCHOR, TARGET))
        self.assertIsNone(declaration.service_pending_target(ANCHOR, TARGET, TARGET))
        mixed = dict(TARGET); mixed['scripts/a0_runtime.py'] = 'f' * 64
        for anchor, current, future in ((TARGET, ANCHOR, TARGET),
                (ANCHOR, mixed, TARGET), (ANCHOR, None, TARGET), (ANCHOR, ANCHOR, mixed)):
            self.refused(declaration.service_pending_target, anchor, current, future)

    def publication(self):
        before = {'worker-runtime-source/' + name: ref(
            HOME / 'worker-runtime-source' / name, digest) for name, digest in ANCHOR.items()}
        after = {'worker-runtime-source/' + name: digest for name, digest in TARGET.items()}
        return before, after

    def test_publication_joins_both_changed_staged_source_mirrors(self):
        before, after = self.publication()
        snapshot = encoded([before, after])
        self.assertIsNone(declaration.service_publication_sources(before, after,
            ANCHOR, TARGET, HOME))
        self.assertEqual(encoded([before, after]), snapshot)

    def test_publication_refuses_incomplete_foreign_paths_pins_and_added_rows(self):
        mutations = ['missing-before', 'missing-after', 'old-sha', 'new-sha',
                     'wrong-path', 'relative-path', 'extra-reference-field',
                     'extra-after', 'unrelated-sha', 'outside-stage']
        for name in CHANGED:
            staged = 'worker-runtime-source/' + name
            for mutation in mutations:
                before, after = self.publication()
                if mutation == 'missing-before': before.pop(staged)
                elif mutation == 'missing-after': after.pop(staged)
                elif mutation == 'old-sha': before[staged]['sha256'] = 'f' * 64
                elif mutation == 'new-sha': after[staged] = 'f' * 64
                elif mutation == 'wrong-path': before[staged]['path'] += '.foreign'
                elif mutation == 'relative-path': before[staged]['path'] = staged
                elif mutation == 'extra-reference-field': before[staged]['mode'] = '100600'
                elif mutation == 'extra-after': after['worker-runtime-source/added.py'] = 'f' * 64
                elif mutation == 'unrelated-sha': after['worker-runtime-source/scripts/rootless_docker_launch.py'] = 'f' * 64
                else:
                    before['outside-stage'] = ref(HOME / 'outside-stage')
                    after['outside-stage'] = 'a' * 64
                with self.subTest(name=name, mutation=mutation):
                    self.refused(declaration.service_publication_sources, before,
                        after, ANCHOR, TARGET, HOME)

    def test_worker_inputs_allow_only_runtime_digest_and_keep_launcher_unchanged(self):
        old = worker_inputs(); new = copy.deepcopy(old)
        new['workers']['a0']['a0']['runtime']['sha256'] = TARGET['scripts/a0_runtime.py']
        snapshot = encoded([old, new])
        self.assertIsNone(declaration.service_worker_inputs(old, new, HOME))
        self.assertEqual(encoded([old, new]), snapshot)
        self.assertEqual(old['workers']['a0']['a0']['launcher'],
                         new['workers']['a0']['a0']['launcher'])

    def test_worker_inputs_refuse_pin_path_resource_and_typed_complement_drift(self):
        for mutation in ('old-runtime', 'new-runtime', 'unchanged-runtime', 'launcher',
                'foreign-launcher', 'runtime-path', 'both-runtime-paths', 'launcher-path',
                'boolean-budget', 'float-budget', 'added-budget', 'deployment',
                'reference-extra', 'missing-runtime', 'missing-launcher'):
            old = worker_inputs(); new = copy.deepcopy(old)
            new['workers']['a0']['a0']['runtime']['sha256'] = TARGET['scripts/a0_runtime.py']
            a0 = new['workers']['a0']['a0']
            if mutation == 'old-runtime': old['workers']['a0']['a0']['runtime']['sha256'] = 'f' * 64
            elif mutation == 'new-runtime': a0['runtime']['sha256'] = 'f' * 64
            elif mutation == 'unchanged-runtime': a0['runtime']['sha256'] = ANCHOR['scripts/a0_runtime.py']
            elif mutation == 'launcher': a0['launcher']['sha256'] = 'f' * 64
            elif mutation == 'foreign-launcher':
                a0['launcher']['sha256'] = old['workers']['a0']['a0']['launcher']['sha256'] = 'f' * 64
            elif mutation == 'runtime-path': a0['runtime']['path'] += '.foreign'
            elif mutation == 'both-runtime-paths':
                a0['runtime']['path'] = old['workers']['a0']['a0']['runtime']['path'] = str(HOME / 'foreign.py')
            elif mutation == 'launcher-path': a0['launcher']['path'] += '.foreign'
            elif mutation == 'boolean-budget': new['workers']['dsh']['budget_seconds'] = True
            elif mutation == 'float-budget': new['workers']['dsh']['budget_seconds'] = 1.0
            elif mutation == 'added-budget': new['extra_budget'] = None
            elif mutation == 'deployment': a0['deployment']['name'] = 'foreign'
            elif mutation == 'reference-extra': a0['runtime']['mode'] = '100600'
            elif mutation == 'missing-runtime': a0.pop('runtime')
            else: a0.pop('launcher')
            snapshot = encoded([old, new])
            with self.subTest(mutation=mutation):
                self.refused(declaration.service_worker_inputs, old, new, HOME)
                self.assertEqual(encoded([old, new]), snapshot)

    def test_service_plan_is_one_detached_change_and_no_native_authority(self):
        data = fixture(); original = encoded(vars(data))
        result = plan(data)
        self.assertEqual(result, declaration.service_declaration_plan(data.root,
            data.profile, data.incoming, data.identity, data.bundle))
        self.assertEqual(result['state'], 'SOURCE_DECLARATION_DELTA_ONLY_NOT_NATIVE_AUTHORITY')
        for field in ('ready', 'native_authority', 'workers_enabled'):
            self.assertIs(result[field], False)
        self.assertIs(result['native_apply_implemented'], True)
        self.assertEqual(result['service_source_transition'],
                         declaration.WEB_PROBE_SERVICE_DISCRIMINATOR)
        self.assertIs(result['launcher']['installed'], False)
        self.assertEqual(result['semantic_changes'], [{'document': 'root_config',
            'path': list(TEMPLATE_INPUTS),
            'before_sha256': fingerprint(get(data.root, TEMPLATE_INPUTS)),
            'after_sha256': fingerprint(data.incoming)}])
        self.assertEqual(result['profile_config'], data.profile)
        restored = copy.deepcopy(result['root_config'])
        put(restored, TEMPLATE_INPUTS, get(data.root, TEMPLATE_INPUTS))
        self.assertEqual(encoded(restored), encoded(data.root))
        self.assertEqual(get(result['root_config'], TEMPLATE_INPUTS), data.incoming)
        get(result['root_config'], TEMPLATE_INPUTS)['workers']['dsh']['budget_seconds'] = 0
        result['profile_config']['browser']['enabled'] = False
        self.assertEqual(encoded(vars(data)), original)

    def test_service_plan_refuses_identity_current_pin_binding_and_generation_conflicts(self):
        for mutation in ('identity-schema', 'principal', 'binding-fingerprint', 'current-binding',
                'boolean-generation', 'disabled', 'profile-path', 'root-raw-cas', 'profile-raw-cas',
                'identity-ref', 'identity-source-path', 'duplicate-binding', 'enabled-runtime'):
            data = fixture()
            if mutation == 'identity-schema': data.identity['schema'] = 'foreign'
            elif mutation == 'principal': data.identity['principal'] = 'f' * 64
            elif mutation == 'binding-fingerprint': data.identity['binding_sha256'] = 'f' * 64
            elif mutation == 'current-binding': get(data.root, SETTINGS)['user_isolation']['bindings'][0]['user_id'] = 'foreign'
            elif mutation == 'boolean-generation': data.identity['generation'] = True
            elif mutation == 'disabled': data.identity['enabled'] = False
            elif mutation == 'profile-path': data.identity['profile'] += '-foreign'
            elif mutation == 'root-raw-cas': data.bundle['root_before']['sha256'] = 'f' * 64
            elif mutation == 'profile-raw-cas': data.bundle['profile_before']['sha256'] = 'f' * 64
            elif mutation == 'identity-ref': data.bundle['identity_reference']['path'] = '../identity.json'
            elif mutation == 'identity-source-path': data.identity['source_refs']['configuration']['path'] += '.foreign'
            elif mutation == 'duplicate-binding': get(data.root, SETTINGS)['user_isolation']['bindings'].append(copy.deepcopy(data.identity['binding']))
            else: get(data.profile, SETTINGS)['runtime']['enabled'] = True
            original = encoded(vars(data))
            with self.subTest(mutation=mutation):
                self.refused(plan, data)
                self.assertEqual(encoded(vars(data)), original)

    def test_service_plan_refuses_scope_required_workers_and_unchanged_deployment_conflicts(self):
        for mutation in ('scope-home', 'scope-profile', 'required-missing', 'required-order',
                'missing-dsh', 'both-missing-dsh', 'extra-worker', 'both-extra-worker',
                'workers-list', 'profile-deployment', 'root-deployment', 'template-deployment',
                'incoming-deployment'):
            data = fixture()
            if mutation == 'scope-home': data.incoming['source_scope']['home'] += '-foreign'
            elif mutation == 'scope-profile': data.incoming['source_scope']['profile'] = 'foreign'
            elif mutation == 'required-missing': data.incoming['required'] = ['a0']
            elif mutation == 'required-order': data.incoming['required'].reverse()
            elif mutation in ('missing-dsh', 'both-missing-dsh'):
                data.incoming['workers'].pop('dsh')
                if mutation.startswith('both-'): get(data.root, TEMPLATE_INPUTS)['workers'].pop('dsh')
            elif mutation in ('extra-worker', 'both-extra-worker'):
                data.incoming['workers']['foreign'] = {}
                if mutation.startswith('both-'): get(data.root, TEMPLATE_INPUTS)['workers']['foreign'] = {}
            elif mutation == 'workers-list': data.incoming['workers'] = []
            elif mutation == 'profile-deployment': data.profile['a0_deployment']['chat']['model'] = 'foreign'
            elif mutation == 'root-deployment': data.root['a0_deployment']['name'] = 'foreign'
            elif mutation == 'template-deployment': get(data.root, TEMPLATE_A0)['embedding']['model'] = 'foreign'
            else: data.incoming['workers']['a0']['a0']['deployment']['name'] = 'foreign'
            # Rebind the declared CAS when the before input was changed; a bad
            # scope/worker join must fail independently of a stale digest.
            data.bundle['changes'][0]['before_sha256'] = fingerprint(get(data.root, TEMPLATE_INPUTS))
            data.bundle['changes'][0]['after_reference']['sha256'] = fingerprint(data.incoming)
            with self.subTest(mutation=mutation):
                self.refused(plan, data)

    def test_service_plan_refuses_nonexact_change_rows_and_invalid_after_refs(self):
        for mutation in ('wrong-schema', 'wrong-state', 'none', 'zero', 'duplicate',
                'wrong-document', 'wrong-path', 'before-fingerprint', 'extra-field',
                'after-pin', 'after-path', 'after-null', 'boolean-before'):
            data = fixture(); row = data.bundle['changes'][0]
            if mutation == 'wrong-schema': data.bundle['schema'] = 'foreign'
            elif mutation == 'wrong-state': data.bundle['state'] = 'APPLY_NOW'
            elif mutation == 'none': data.bundle['changes'] = None
            elif mutation == 'zero': data.bundle['changes'] = []
            elif mutation == 'duplicate': data.bundle['changes'].append(copy.deepcopy(row))
            elif mutation == 'wrong-document': row['document'] = 'profile_config'
            elif mutation == 'wrong-path': row['path'] = ['a0_deployment']
            elif mutation == 'before-fingerprint': row['before_sha256'] = 'f' * 64
            elif mutation == 'extra-field': row['native_apply'] = True
            elif mutation == 'after-pin': row['after_reference']['sha256'] = '0' * 64
            elif mutation == 'after-path': row['after_reference']['path'] = '/synthetic/../foreign'
            elif mutation == 'after-null': row['after_reference'] = None
            else: row['before_sha256'] = True
            with self.subTest(mutation=mutation):
                self.refused(plan, data)

    def test_legacy_four_change_schema_keeps_its_existing_planning_behavior(self):
        data = fixture()
        incoming = copy.deepcopy(get(data.root, TEMPLATE_INPUTS))
        deployment = incoming['workers']['a0']['a0']['deployment']
        deployment['name'] = 'synthetic-renamed-main'
        incoming['workers']['a0']['a0']['launcher']['sha256'] = 'e' * 64
        data.incoming = incoming
        data.bundle['schema'] = 'frw.current-both-spark-declaration-change-data.v1'
        data.bundle['changes'] = [{'document': document, 'path': list(path),
            'before': copy.deepcopy(get(config, path)), 'after': copy.deepcopy(deployment)}
            for document, config, path in (
                ('root_config', data.root, ('a0_deployment',)),
                ('profile_config', data.profile, ('a0_deployment',)),
                ('root_config', data.root, TEMPLATE_A0))] + [{
                    'document': 'root_config', 'path': list(TEMPLATE_INPUTS),
                    'before_sha256': fingerprint(get(data.root, TEMPLATE_INPUTS)),
                    'after_reference': ref(HOME / 'synthetic-inputs/legacy-inputs.json',
                                           fingerprint(incoming))}]
        original = encoded(vars(data)); result = plan(data)
        self.assertEqual(len(result['semantic_changes']), 4)
        self.assertIs(result['native_apply_implemented'], True)
        self.assertIs(result['ready'], False)
        self.assertIs(result['native_authority'], False)
        self.assertEqual(encoded(vars(data)), original)


if __name__ == '__main__':
    unittest.main()
