#!/usr/bin/env python3
"""Exact normal28 source gate; never an installation or effect admission.

The adjacent SHA-pinned baseline specifies all 127 project files and original
24/25/final-R5 receipt identities. Full source inventory and executable modes
are checked before selected, unchanged exporter/installer/renderer definitions
execute. Module initializers and native imports never execute. Negative controls
mutate in-memory inputs only. Git may parse patches with --numstat; never apply.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import copy
import enum
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import stat
import subprocess
import time
from types import SimpleNamespace as S
import __future__
from urllib.parse import urlsplit


BASELINE_SHA256 = 'ad7879698e0dd293f9a19470540bbed83b1f405a48bee7bb0b907cc06a9a100b'
RECEIPT_KEYS = {'schema', 'status', 'commit', 'base_tree', 'sources_lock_sha256',
                'source_file_count', 'layers', 'files', 'dependencies_installed', 'services_started'}
REQUIRED = {'delegate_task', 'skills_list', 'skill_view', 'skill_manage'}
DENIED = {'terminal', 'process_manage', 'execute_code', 'browser'}


class GateRefused(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise GateRefused(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    value = {}
    for key, row in pairs:
        require(key not in value, 'duplicate_json_key')
        value[key] = row
    return value


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(GateRefused('nonfinite_json')))


def relative(name):
    require(isinstance(name, str) and name and '\\' not in name and '\x00' not in name,
            'unsafe_inventory_path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and str(path) == name,
            'unsafe_inventory_path')
    return name


def record_schema(row):
    require(isinstance(row, dict) and set(row) == {'sha256', 'bytes', 'mode'}, 'file_row_schema')
    require(isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']),
            'file_row_sha')
    require(type(row['bytes']) is int and 0 <= row['bytes'] <= 64 * 1024**2,
            'file_row_size')
    require(row['mode'] in {'100644', '100755'}, 'file_row_mode')


class Gate:
    def __init__(self, args):
        self.args = args
        self.deadline = time.monotonic() + args.seconds
        self.rows, self.bodies, self.reads, self.imports = [], [], {}, []
        self.modules = {'__future__': __future__}
        self.expected_bytes = {}
        self.git_calls = 0
        self.started_mono = time.monotonic()

    def remaining(self):
        left = self.deadline - time.monotonic()
        require(left > 0, 'source_gate_deadline')
        return left

    def read(self, path):
        self.remaining()
        path = Path(path)
        require(path.is_absolute() and path.resolve() == path, 'canonical_input_required')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                    and before.st_nlink == 1, 'owned_regular_input_required')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(64 * 1024**2 + 1)
            after = os.fstat(fd)
            keys = ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_uid', 'st_nlink',
                    'st_mtime_ns', 'st_ctime_ns')
            require(len(raw) <= 64 * 1024**2 and
                    all(getattr(before, k) == getattr(after, k) for k in keys), 'input_changed')
        finally:
            os.close(fd)
        self.reads[str(path)] = {'sha256': sha(raw), 'bytes': len(raw),
                                'mode': '100755' if before.st_mode & 0o111 else '100644'}
        self.remaining()
        return raw

    def verified_payload(self, path, raw):
        require(str(path) in self.expected_bytes and sha(raw) == self.expected_bytes[str(path)],
                'selected_source_substitution_refused')
        return raw

    def verified(self, path):
        return self.verified_payload(path, self.read(path))

    def pinned_json(self, path, digest):
        raw = self.read(path)
        require(sha(raw) == digest, 'pinned_input_sha_mismatch')
        return parse(raw)

    def check(self, name, call, category):
        self.remaining()
        call()
        self.rows.append({'name': name, 'category': category, 'status': 'PASS'})

    def refusal(self, name, call, reason, category):
        def body():
            try:
                call()
            except (ValueError, RuntimeError, PermissionError) as exc:
                require(str(exc) == reason, 'unexpected_refusal:' + str(exc))
            else:
                raise GateRefused('missing_refusal:' + reason)
        self.check(name, body, category)

    def importer(self, name, globals=None, locals=None, fromlist=(), level=0):
        require(name in self.modules and level in {0, 1}, 'native_import_forbidden:' + name)
        self.imports.append({'name': name, 'level': level})
        return self.modules[name]

    def selected(self, path, name, env):
        raw = self.verified(path)
        nodes = [n for n in ast.parse(raw).body if
                 isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
        require(len(nodes) == 1 and not nodes[0].decorator_list, 'selected_body_required')
        node = nodes[0]
        env['__builtins__'] = {**vars(builtins), '__import__': self.importer}
        body = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
                copy.deepcopy(node)]
        exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])),
                     str(path), 'exec'), env)
        self.bodies.append({'path': str(path), 'name': name, 'file_sha256': sha(raw),
                            'body_sha256': sha(ast.get_source_segment(raw.decode(), node).encode()),
                            'line': node.lineno, 'end_line': node.end_lineno, 'body_modified': False})
        return env[name]

    def constant(self, path, name):
        nodes = [n for n in ast.parse(self.verified(path)).body if
                 (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name
                                                  for t in n.targets)) or
                 (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == name)]
        require(len(nodes) == 1, 'exact_constant_required')
        node = nodes[0].value
        if isinstance(node, ast.Call):
            require(isinstance(node.func, ast.Name) and node.func.id == 'frozenset'
                    and len(node.args) == 1 and not node.keywords, 'literal_frozenset_required')
            return frozenset(ast.literal_eval(node.args[0]))
        return ast.literal_eval(node)

    def inventory(self, root, expected):
        require(isinstance(expected, dict), 'inventory_schema')
        actual = set()
        for path in root.rglob('*'):
            self.remaining()
            require(not path.is_symlink(), 'source_link_refused')
            if not path.is_dir():
                actual.add(str(path.relative_to(root)))
        require(actual == set(expected), 'exact_inventory_required')
        for name, row in expected.items():
            relative(name)
            record_schema(row)
            raw = self.read(root / name)
            require(self.reads[str(root / name)] == row, 'source_bytes_or_mode_changed')
            self.expected_bytes[str(root / name)] = sha(raw)

    def receipt_schema(self, receipt, layers, files):
        require(isinstance(receipt, dict) and set(receipt) == RECEIPT_KEYS, 'source_receipt_schema')
        require(receipt['schema'] == 'friday.hermes-source.v1'
                and receipt['status'] == 'SOURCE_COMPOSED_NOT_RUNTIME_ACCEPTED',
                'source_receipt_status')
        donor = self.baseline['donor']
        require(receipt['commit'] == donor['commit'] and receipt['base_tree'] == donor['tree']
                and receipt['source_file_count'] == donor['source_file_count'], 'donor_identity_required')
        require(receipt['dependencies_installed'] is False and receipt['services_started'] is False,
                'source_only_status_required')
        require(receipt['sources_lock_sha256'] == self.baseline['project']['sources.lock.json']['sha256'],
                'source_lock_identity_required')
        require(isinstance(receipt['layers'], list) and len(receipt['layers']) == layers,
                'exact_layer_count_required')
        manifests = set()
        for row in receipt['layers']:
            require(isinstance(row, dict) and set(row) == {'manifest', 'manifest_sha256', 'patch_sha256'},
                    'source_layer_schema')
            relative(row['manifest'])
            require(row['manifest'] not in manifests, 'duplicate_receipt_layer')
            manifests.add(row['manifest'])
            require(all(isinstance(row[k], str) and re.fullmatch('[0-9a-f]{64}', row[k])
                        for k in ['manifest_sha256', 'patch_sha256']), 'source_layer_sha')
        require(isinstance(receipt['files'], dict) and len(receipt['files']) == files,
                'exact_source_count_required')
        for name, row in receipt['files'].items():
            relative(name)
            record_schema(row)

    def patch_numstat(self, directory, args, budget, *, data=None):
        require(directory == self.args.repository and args == ['apply', '--numstat', '-z', '-'],
                'git_effect_forbidden')
        self.git_calls += 1
        env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'GIT_OPTIONAL_LOCKS': '0',
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
               'GIT_TERMINAL_PROMPT': '0'}
        result = subprocess.run(['git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
                                 '-c', 'core.hooksPath=' + os.devnull, '-C', str(directory), *args],
                                input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, timeout=min(30, self.remaining()))
        require(result.returncode == 0, 'git_numstat_failed')
        return result.stdout

    def source_controls(self):
        a = self.args
        self.baseline = self.pinned_json(a.baseline, BASELINE_SHA256)
        b = self.baseline
        require(set(b) == {'schema', 'scope', 'project_files_sha256', 'project', 'donor', 'receipts',
                           'expected', 'historical_checker', 'effect_admission', 'runtime'}
                and b['schema'] == 'friday.normal28-source-gate-baseline.v1'
                and b['scope'] == 'EXACT_NORMAL28_SOURCE_ONLY'
                and b['effect_admission'] is False and b['runtime'] == 'NOT_RUN', 'baseline_schema')
        pins = self.pinned_json(a.project_files, b['project_files_sha256'])
        require(pins == {n: r['sha256'] for n, r in b['project'].items()} and len(pins) == 127,
                'project_inventory_identity_required')
        self.check('exact_127_project_bytes_modes_inventory', lambda: self.inventory(a.repository, b['project']), 'source')
        self.check('historical_25_checker_bytes_preserved', lambda: require(
            pins[b['historical_checker']['path']] == b['historical_checker']['sha256'],
            'historical_checker_changed'), 'source')
        receipts = {}
        for key, path, layer_count, file_count in [
            ('original24', a.original_receipt, 24, 17636), ('skills25', a.skills_receipt, 25, 17639),
            ('normal28', a.receipt, 28, 17647), ('final_r5', a.r5_receipt, 28, 17647)]:
            row = self.pinned_json(path, b['receipts'][key])
            self.check(key + '_exact_receipt_schema_identity_source_only',
                       lambda row=row, lc=layer_count, fc=file_count: self.receipt_schema(row, lc, fc), 'source')
            receipts[key] = row
        old, skills, final = receipts['original24'], receipts['skills25'], receipts['normal28']
        self.check('original_24_complete_17636_source_bytes_modes',
                   lambda: self.inventory(a.original_source, old['files']), 'baseline')
        self.check('historical_skills_25_complete_17639_source_bytes_modes',
                   lambda: self.inventory(a.skills_source, skills['files']), 'baseline')
        self.check('final_frozen_receipt_exact_R5_saved_bytes', lambda: require(
            self.read(a.receipt) == self.read(a.r5_receipt), 'final_R5_receipt_changed'), 'source')
        self.check('full_17647_source_bytes_modes_inventory_no_links_extras',
                   lambda: self.inventory(a.source, final['files']), 'source')
        lock = parse(self.verified(a.repository / 'sources.lock.json'))
        donors = [r for r in lock['repositories'] if r['id'] == 'hermes']
        require(len(donors) == 1 and donors[0]['commit'] == b['donor']['commit']
                and donors[0]['tree'] == b['donor']['tree'], 'donor_lock_identity_required')
        donor = donors[0]
        export = {'Path': Path, 'PurePosixPath': PurePosixPath, 'os': os, 'stat': stat,
                  'json': json, 'hashlib': hashlib, 're': re, 'git': self.patch_numstat}
        for name in ['Refused', 'require', 'sha', 'relative', 'regular', 'unique_object', 'read_json', 'overlay_layers']:
            self.selected(a.repository / 'scripts/hermes_prepare.py', name, export)
        ordered = export['overlay_layers'](a.repository, donor['commit'], self)
        self.ordered = ordered
        self.check('actual_exporter_discovers_exact_28_in_receipt_order', lambda: require(
            len(ordered) == 28 and [{k: row[k] for k in ('manifest', 'manifest_sha256', 'patch_sha256')}
                                  for _, row in ordered] == final['layers'], 'exporter_receipt_order'), 'exporter')
        positions = {name: i for i, (name, _) in enumerate(ordered)}
        self.check('all_28_dependencies_precede_consumers_and_exact_SHA', lambda: require(
            all(positions[parent] < positions[name] and pins[parent] == digest
                for name, layer in ordered for parent, digest in layer['requires'].items()),
            'overlay_topology_changed'), 'exporter')
        self.check('terminal_final_layer_requires_all_27_exact_predecessors', lambda: require(
            ordered[-1][0] == b['expected']['final_layer']
            and set(ordered[-1][1]['requires']) == set(positions) - {ordered[-1][0]},
            'final_prerequisites_required'), 'exporter')
        self.check('original_24_layers_and_17636_paths_retained', lambda: require(
            old['layers'] == skills['layers'][:24] == final['layers'][:24]
            and set(old['files']) <= set(skills['files']) <= set(final['files']),
            'original_source_baseline_changed'), 'baseline')
        self.check('historical_skills_25_exact_3_additions_29_changed_files', lambda: self.skills_delta(old, skills, ordered[24]), 'baseline')
        self.check('historical_all_29_skills_output_sources_parse_without_import',
                   lambda: [ast.parse(self.verified(a.skills_source / name)) for name in ordered[24][1]['files']], 'baseline')
        self.check('all_4_post_original_layers_exact_before_after_metadata', lambda: self.layer_chain(old, final, ordered[24:]), 'baseline')
        self.check('all_28_last_writer_final_hash_size_modes_and_intermediate_pins', lambda: self.final_writers(final, ordered), 'baseline')
        raw_json = export['read_json']
        final_manifest = ordered[-1][1]['manifest']
        def exp_negative(name, reason, mutation, target=final_manifest):
            def changed(path):
                value, digest = raw_json(path)
                if str(path.relative_to(a.repository)) == target:
                    value = copy.deepcopy(value)
                    mutation(value)
                return value, digest
            export['read_json'] = changed
            try:
                self.refusal(name, lambda: export['overlay_layers'](a.repository, donor['commit'], self), reason, 'exporter_negative')
            finally:
                export['read_json'] = raw_json
        exp_negative('exporter_wrong_donor_refused', 'overlay_base_mismatch', lambda v: v.update(base_commit='0' * 40))
        exp_negative('exporter_wrong_patch_SHA_refused', 'overlay_hash_mismatch', lambda v: v.update(patch_sha256='0' * 64))
        exp_negative('exporter_wrong_prerequisite_SHA_refused', 'overlay_prerequisite_mismatch',
                     lambda v: v['prerequisites'].update({'patches/hermes/user-skills.patch': '0' * 64}))
        exp_negative('exporter_missing_dependency_refused', 'overlay_prerequisite_mismatch',
                     lambda v: v['prerequisites'].update({'absent.patch': '0' * 64}))
        exp_negative('exporter_dependency_traversal_refused', 'invalid_relative_path',
                     lambda v: v['prerequisites'].update({'../absent.patch': '0' * 64}))
        exp_negative('exporter_dependency_cycle_refused', 'overlay_dependency_cycle',
                     lambda v: v['prerequisites'].update({ordered[-1][0]: pins[ordered[-1][0]]}))
        exp_negative('exporter_missing_patch_file_inventory_refused', 'overlay_file_inventory_mismatch', lambda v: v['files'].pop())
        exp_negative('exporter_invalid_file_SHA_refused', 'invalid_overlay_file', lambda v: v['files'][0].update(sha256='broken'))
        exp_negative('exporter_boolean_file_size_refused', 'invalid_overlay_size', lambda v: v['files'][0].update(bytes=True))
        exp_negative('exporter_duplicate_file_inventory_refused', 'invalid_overlay_file', lambda v: v['files'].append(copy.deepcopy(v['files'][0])))
        install = {'Path': Path, 'os': os, 'stat': stat, 'json': json, 'hashlib': hashlib, 're': re, 'ROOT': a.repository}
        for name in ['Refused', 'require', 'canonical', 'owned_file', 'digest', 'source_checked', 'composition_checked']:
            self.selected(a.repository / 'scripts/friday_install.py', name, install)
        spec = {'project_files': pins, 'sources_lock': {'sha256': pins['sources.lock.json']}}
        self.check('actual_installer_own_canonical_owned_reader_complete_127_28_17647',
                   lambda: install['composition_checked'](spec, a.source, final, donor), 'installer')
        def ins_negative(name, reason, mutate):
            v, r, d = copy.deepcopy(spec), copy.deepcopy(final), copy.deepcopy(donor)
            mutate(v, r, d)
            self.refusal(name, lambda: install['composition_checked'](v, a.source, r, d), reason, 'installer_negative')
        first = next(iter(final['files']))
        for name, reason, mutation in [
            ('missing_layer', 'composition_overlay_set_changed', lambda v, r, d: r['layers'].pop()),
            ('duplicate_layer', 'composition_overlay_set_changed', lambda v, r, d: r['layers'].__setitem__(0, r['layers'][1])),
            ('manifest_SHA', 'composition_overlay_manifest_changed', lambda v, r, d: r['layers'][0].update(manifest_sha256='0' * 64)),
            ('patch_SHA', 'composition_overlay_patch_changed', lambda v, r, d: r['layers'][0].update(patch_sha256='0' * 64)),
            ('source_lock', 'composition_source_lock_changed', lambda v, r, d: r.update(sources_lock_sha256='0' * 64)),
            ('donor', 'hermes_composition_identity_required', lambda v, r, d: d.update(commit='0' * 40)),
            ('file_SHA', 'composed_source_changed', lambda v, r, d: r['files'][first].update(sha256='0' * 64)),
            ('file_mode', 'composed_source_changed', lambda v, r, d: r['files'][first].update(mode='100755' if r['files'][first]['mode'] == '100644' else '100644')),
            ('unsafe_path', 'unsafe_source_inventory_path', lambda v, r, d: r['files'].update({'../foreign': r['files'][first]})),
            ('old_25_project_manifest_set', 'composition_overlay_set_changed', lambda v, r, d: v.update(project_files={n: h for n, h in pins.items() if n not in {row['manifest'] for row in final['layers'][25:]}})),
        ]:
            ins_negative('installer_' + name + '_refused', reason, mutation)
        self.schema_negatives(final)
        self.check('strict_current_graph_contract', lambda: self.graph_contract(ordered, final, pins), 'exporter')
        graph = [(n, copy.deepcopy(row)) for n, row in ordered]
        graph[-1][1]['requires'].pop(next(iter(graph[-1][1]['requires'])))
        self.refusal('gate_final_prerequisite_omission_refused', lambda: self.graph_contract(graph, final, pins),
                     'final_prerequisites_required', 'gate_negative')
        graph = [(n, copy.deepcopy(row)) for n, row in ordered]
        graph[0][1]['requires'][graph[-1][0]] = pins[graph[-1][0]]
        self.refusal('gate_consumer_before_dependency_refused', lambda: self.graph_contract(graph, final, pins),
                     'overlay_topology_changed', 'gate_negative')
        graph = [(n, copy.deepcopy(row)) for n, row in ordered]
        graph[-1][1]['requires'][graph[0][0]] = '0' * 64
        self.refusal('gate_dependency_SHA_substitution_refused', lambda: self.graph_contract(graph, final, pins),
                     'overlay_topology_changed', 'gate_negative')
        self.receipts = receipts

    def graph_contract(self, ordered, final, pins):
        require(len(ordered) == 28 and len({n for n, _ in ordered}) == 28
                and [{k: r[k] for k in ('manifest', 'manifest_sha256', 'patch_sha256')}
                     for _, r in ordered] == final['layers'], 'exporter_receipt_order')
        positions = {n: i for i, (n, _) in enumerate(ordered)}
        require(all(parent in positions and positions[parent] < positions[name]
                    and pins.get(parent) == digest for name, row in ordered
                    for parent, digest in row['requires'].items()), 'overlay_topology_changed')
        require(ordered[-1][0] == self.baseline['expected']['final_layer']
                and set(ordered[-1][1]['requires']) == set(positions) - {ordered[-1][0]},
                'final_prerequisites_required')

    def skills_delta(self, old, skills, layer):
        require(layer[0] == 'patches/hermes/user-skills.patch' and len(layer[1]['files']) == 29,
                'historical_skills_layer_required')
        require(set(skills['files']) - set(old['files']) == set(self.baseline['expected']['skills_added']),
                'historical_skills_additions_changed')
        changed = {n for n, row in skills['files'].items() if row != old['files'].get(n)}
        require(changed == set(layer[1]['files']), 'historical_skills_delta_changed')
        self.layer_chain(old, skills, [layer])

    def layer_chain(self, old, final, layers):
        current = copy.deepcopy(old['files'])
        for _, layer in layers:
            for name, row in layer['files'].items():
                prior = current.get(name)
                if row.get('new_file'):
                    require(prior is None, 'overlay_new_file_already_present')
                if row.get('before_sha256'):
                    require(prior is not None and prior['sha256'] == row['before_sha256'], 'overlay_before_metadata_changed')
                mode = row.get('mode', prior['mode'] if prior else '100644')
                current[name] = {'sha256': row['sha256'], 'bytes': row['bytes'], 'mode': mode}
        require(current == final['files'], 'overlay_chain_final_inventory_changed')

    def final_writers(self, final, layers):
        last = {}
        for _, layer in layers:
            for name, row in layer['files'].items():
                if name in last and row.get('before_sha256'):
                    require(last[name]['sha256'] == row['before_sha256'], 'intermediate_overlay_changed')
                last[name] = row
        for name, row in last.items():
            actual = final['files'][name]
            require(actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes']
                    and row.get('mode', actual['mode']) == actual['mode'], 'last_writer_changed')

    def schema_negatives(self, final):
        for name, reason, mutate in [
            ('extra_field', 'source_receipt_schema', lambda r: r.update(extra=True)),
            ('runtime_status', 'source_receipt_status', lambda r: r.update(status='RUNTIME_ACCEPTED')),
            ('runtime_effect', 'source_only_status_required', lambda r: r.update(services_started=True)),
            ('donor_tree', 'donor_identity_required', lambda r: r.update(base_tree='0' * 40)),
            ('nominal_count', 'donor_identity_required', lambda r: r.update(source_file_count=17647)),
            ('missing_inventory', 'exact_source_count_required', lambda r: r['files'].pop(next(iter(r['files'])))),
            ('duplicate_layer', 'duplicate_receipt_layer', lambda r: r['layers'].__setitem__(0, r['layers'][1])),
            ('file_row_schema', 'file_row_schema', lambda r: r['files'][next(iter(r['files']))].update(extra=1)),
            ('file_SHA_format', 'file_row_sha', lambda r: r['files'][next(iter(r['files']))].update(sha256='oops')),
            ('file_mode_format', 'file_row_mode', lambda r: r['files'][next(iter(r['files']))].update(mode='644')),
        ]:
            r = copy.deepcopy(final)
            mutate(r)
            self.refusal('gate_schema_' + name + '_refused', lambda r=r: self.receipt_schema(r, 28, 17647), reason, 'gate_negative')
        self.refusal('duplicate_JSON_key_refused', lambda: parse(b'{"x":1,"x":2}'), 'duplicate_json_key', 'gate_negative')
        self.refusal('nonfinite_JSON_refused', lambda: parse(b'{"x":NaN}'), 'nonfinite_json', 'gate_negative')
        self.refusal('source_receipt_SHA_substitution_refused', lambda: self.pinned_json(self.args.receipt, '0' * 64), 'pinned_input_sha_mismatch', 'gate_negative')
        source = self.args.repository / 'tools/configure_product.py'
        self.refusal('selected_consumer_source_substitution_refused', lambda: self.verified_payload(source, self.read(source) + b'\n# substituted\n'), 'selected_source_substitution_refused', 'gate_negative')
        omitted = dict(final['files']); omitted.pop(next(iter(omitted)))
        self.refusal('actual_filesystem_omitted_source_inventory_refused', lambda: self.inventory(self.args.source, omitted), 'exact_inventory_required', 'gate_negative')
        self.refusal('git_effectful_apply_refused_before_spawn', lambda: self.patch_numstat(self.args.repository, ['apply', '-'], self, data=b''), 'git_effect_forbidden', 'gate_negative')

    def renderer_controls(self):
        """Actual pure consumers with explicitly limited native identity fixtures."""
        P, H = self.args.repository, self.args.source
        nodes = []
        for node in ast.parse(self.verified(H / 'hermes_cli/config_defaults.py')).body:
            if isinstance(node, ast.FunctionDef) and node.name == '_aux':
                require(not node.decorator_list, 'default_helper_decorator_refused')
                nodes.append(copy.deepcopy(node))
            if isinstance(node, ast.Assign):
                nodes.append(copy.deepcopy(node))
                if any(isinstance(t, ast.Name) and t.id == 'DEFAULT_CONFIG' for t in node.targets):
                    break
        default_env = {'__builtins__': {**vars(builtins), '__import__': self.importer}}
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                     'native-default-data-only', 'exec'), default_env)
        defaults = default_env['DEFAULT_CONFIG']; original_defaults = copy.deepcopy(defaults)
        safe = self.constant(H / 'hermes_cli/friday_user_scope.py', 'SAFE')
        self.check('actual_SAFE_has_skills_delegation_excludes_terminal_process',
                   lambda: require(REQUIRED <= safe and not DENIED & safe, 'ordinary_SAFE_changed'), 'capability')
        scope = S(SAFE=safe)
        web = {'Path': Path, '__file__': str(P / 'tools/web_profile.py'),
               'HERMES_PROFILES': self.constant(P / 'tools/web_profile.py', 'HERMES_PROFILES')}
        for name in ['_profile', '_bound', 'research_policy', 'hermes_web_config']:
            self.selected(P / 'tools/web_profile.py', name, web)
        local = {'hermes_web_config': web['hermes_web_config'], 'research_policy': web['research_policy'],
                 're': re, 'ipaddress': ipaddress, 'urlsplit': urlsplit}
        build = self.selected(P / 'tools/configure_local_test.py', 'build_config', local)
        class Platform(enum.Enum):
            TELEGRAM = 'telegram'
            DISCORD = 'discord'
            LOCAL = 'local'
        self.modules['gateway.config'] = S(Platform=Platform, PLATFORM_TOKEN_ENV_NAMES={
            Platform.TELEGRAM: 'TELEGRAM_BOT_TOKEN', Platform.DISCORD: 'DISCORD_BOT_TOKEN'})
        self.modules['gateway.config_env'] = S(_ENV_ENABLE_CREDENTIALS={Platform.TELEGRAM: [], Platform.DISCORD: []})
        def profile_name(value):
            require(value == 'default', 'fixture_default_profile_required')
            return value
        def env_name(value):
            require(isinstance(value, str) and re.fullmatch('[A-Z][A-Z0-9_]*', value), 'fixture_env_reference_required')
        self.modules['hermes_cli.friday_product_access'] = S(profile_name=profile_name)
        self.modules['hermes_cli'] = S(friday_user_scope=scope)
        self.modules['hermes_cli.config'] = S(DEFAULT_CONFIG=defaults, validate_env_var_name_for_write=env_name)
        runtime = {}
        self.selected(P / 'plugins/friday_rework/host_runtime.py', 'HostUnavailable', runtime)
        def enabled_forbidden(value):
            raise runtime['HostUnavailable']('fixture_enabled_runtime_forbidden')
        runtime['validate_runtime'] = enabled_forbidden
        configured = self.selected(P / 'plugins/friday_rework/host_runtime.py', 'configured_runtimes', runtime)
        self.modules['plugins.friday_rework.host_runtime'] = S(HostUnavailable=runtime['HostUnavailable'], configured_runtimes=configured)
        join = {'configured_runtimes': configured, 'copy': copy}
        for name in ['installation_inputs', 'validate_installation_inputs']:
            self.selected(P / 'plugins/friday_rework/user_worker_join.py', name, join)
        self.modules['plugins.friday_rework.user_worker_join'] = S(installation_inputs=join['installation_inputs'])
        self.modules['user_worker_join'] = S(validate_installation_inputs=join['validate_installation_inputs'])
        onboard = {'copy': copy, 'scope': scope, 're': re, 'ipaddress': ipaddress,
                   'urlsplit': urlsplit, 'RESOURCE': P / 'plugins/friday_rework'}
        for name in ['_local', 'validate_template']:
            self.selected(P / 'plugins/friday_rework/onboarding.py', name, onboard)
        self.modules['plugins.friday_rework.onboarding'] = S(validate_template=onboard['validate_template'])
        auth = {'_LOOPBACK_HOST_VALUES': self.constant(H / 'hermes_cli/web_server.py', '_LOOPBACK_HOST_VALUES')}
        for name in ['should_require_auth', 'should_require_dashboard_auth']:
            self.selected(H / 'hermes_cli/web_server.py', name, auth)
        self.modules['hermes_cli.web_server'] = S(should_require_dashboard_auth=auth['should_require_dashboard_auth'])
        renderer = {'copy': copy, 'hashlib': hashlib, 'ROOT': P, 're': re, 'ipaddress': ipaddress,
                    'urlsplit': urlsplit, 'build_config': build, 'hermes_web_config': web['hermes_web_config'],
                    'research_policy': web['research_policy']}
        for name in ['INFERENCE', 'AUTH_NAMES', 'NORMAL_TOOLSETS', 'USER_TOOLSETS']:
            renderer[name] = self.constant(P / 'tools/configure_product.py', name)
        for name in ['_exact', '_text', '_dashboard', 'compose_product']:
            self.selected(P / 'tools/configure_product.py', name, renderer)
        inputs = self.selected(P / 'tests/test_product_profile.py', 'inputs', {})
        compose = renderer['compose_product']; bundles = {}
        for profile in ['exa-paid', 'exa-keyless']:
            spec = inputs(); spec['web']['profile'] = profile
            bundle = compose(spec); bundles[profile] = bundle
            self.check('actual_renderer_' + profile + '_ordinary_isolation_local_routes_unready',
                       lambda bundle=bundle, spec=spec: self.bundle_contract(bundle, spec, safe, defaults), 'renderer')
        self.check('native_defaults_not_mutated', lambda: require(defaults == original_defaults, 'native_defaults_mutated'), 'renderer')
        for missing in sorted(REQUIRED):
            scope.SAFE = safe - {missing}
            reason = 'scoped_native_delegation_required' if missing == 'delegate_task' else 'scoped_native_skills_required'
            try:
                self.refusal('actual_renderer_missing_' + missing + '_refused', lambda: compose(inputs()), reason, 'renderer_negative')
            finally:
                scope.SAFE = safe
        temporary = build(**inputs()['inference'])
        self.check('temporary_local_test_profile_stays_distinct', lambda: require(
            temporary['memory']['memory_enabled'] is False and temporary['toolsets'] == []
            and temporary['agent']['api_max_retries'] == 1
            and temporary['auxiliary']['title_generation']['enabled'] is False, 'temporary_profile_changed'), 'renderer')
        for name, reason, mutation in [
            ('disabled_web', 'mandatory_explicit_scoped_web_required', lambda v: v['web'].update(profile='disabled')),
            ('missing_web_limit', 'web_limits_required', lambda v: v['web'].update(extract_timeout=None)),
            ('enabled_workers', 'explicit_worker_runtime_contract_required', lambda v: v['runtime'].update(enabled=True)),
            ('foreign_receiving_profile', 'receiving_transport_authority_required', lambda v: v['accounts'][0].update(transport_profile='foreign')),
            ('duplicate_receiver', 'duplicate_receiving_account', lambda v: v['accounts'].append(copy.deepcopy(v['accounts'][0]))),
            ('remote_HTTP_dashboard', 'remote_dashboard_https_required', lambda v: v['dashboard'].update(public_url='http://friday.example:9119')),
            ('foreign_operator', 'native_basic_operator_identity_required', lambda v: v['dashboard']['operator'].update(provider='oauth')),
            ('credential_reference_alias', 'separate_scoped_credential_references_required', lambda v: v['inference'].update(key_env='TELEGRAM_BOT_TOKEN')),
        ]:
            spec = inputs(); mutation(spec)
            self.refusal('actual_renderer_' + name + '_refused', lambda spec=spec: compose(spec), reason, 'renderer_negative')
        base = bundles['exa-paid']['config']['plugins']['entries']['friday_rework']['settings']['onboarding']['templates']['friday-local']
        for tool in ['terminal', 'process_manage']:
            template = copy.deepcopy(base); template['tools'].append(tool)
            self.refusal('actual_template_' + tool + '_grant_refused', lambda t=template: onboard['validate_template'](t), 'incomplete_onboarding_template', 'capability_negative')
        for name, reason, mutation in [
            ('cloud_fallback', 'explicit_local_inference_required', lambda v: v['config'].update(fallback_providers=['cloud'])),
            ('admin_import', 'ordinary_profile_cannot_import_authority', lambda v: v['config']['plugins']['entries']['friday_rework']['settings'].update(admin={'enabled': True})),
            ('gateway_import', 'ordinary_profile_cannot_import_authority', lambda v: v['config'].update(gateway={'multiplex_profiles': True})),
            ('inline_credentials', 'inline_credentials_refused', lambda v: v['config']['plugins'].update(secret='SYNTHETIC')),
            ('incomplete_worker_set', 'both_normal_worker_inputs_required', lambda v: v['worker_inputs'].update(workers={'dsh': {}})),
        ]:
            template = copy.deepcopy(base); mutation(template)
            self.refusal('actual_template_' + name + '_refused', lambda t=template: onboard['validate_template'](t), reason, 'template_negative')
        self.capability_controls(H, safe)

    def bundle_contract(self, bundle, spec, safe, defaults):
        config = bundle['config']; settings = config['plugins']['entries']['friday_rework']['settings']
        template = settings['onboarding']['templates']['friday-local']; ordinary = template['config']
        require(settings['runtime'] == {'enabled': False}
                and ordinary['plugins']['entries']['friday_rework']['settings'] == {
                    'runtime': {'enabled': False}, 'results': {'enabled': True}}
                and template['worker_inputs'] == {'required': ['dsh', 'a0'], 'workers': {}}
                and not bundle['contract']['ready'] and bundle['contract']['state'] == 'TEMPLATE_INCOMPLETE',
                'runtime_template_must_remain_unadmitted')
        require(set(template['tools']) == safe == set(bundle['contract']['ordinary_scope'])
                and not DENIED & set(template['tools']) and 'terminal' not in config
                and not {'terminal', 'process'} & set(ordinary['toolsets']), 'ordinary_capability_expansion')
        require({'skills', 'delegation'} <= set(ordinary['toolsets'])
                and all({'skills', 'delegation'} <= set(v) for v in ordinary['platform_toolsets'].values()),
                'ordinary_toolsets_required')
        require(not {'dashboard', 'gateway', 'platforms', 'secrets', 'mcp_servers'} & set(ordinary)
                and 'dashboard_auth/basic' not in ordinary['plugins']['enabled']
                and 'dashboard_auth/basic' in ordinary['plugins']['disabled'], 'ordinary_authority_import')
        require(ordinary['skills']['create_dir'] is None
                and all(ordinary['skills'][k] == [] for k in ['external_dirs', 'trusted_project_dirs', 'auto_load'])
                and ordinary['skills']['project_discovery'] is False, 'ordinary_skill_discovery_expansion')
        require(all(config[k] == defaults[k] for k in ['memory', 'skills', 'tools', 'approvals']), 'native_defaults_lost')
        require(config['fallback_providers'] == [] and config['fallback_model'] == {}
                and config['delegation']['fallback_providers'] == []
                and config['delegation']['base_url'] == config['model']['base_url']
                and config['delegation']['key_env'] == spec['inference']['key_env']
                and 'api_key' not in config['delegation'], 'local_routes_required')
        for route in config['auxiliary'].values():
            if isinstance(route, dict) and 'provider' in route:
                require(route['base_url'] == config['model']['base_url']
                        and route['model'] == spec['inference']['model']
                        and route['fallback_chain'] == [] and 'api_key' not in route, 'aux_local_routes_required')
        require(config['web']['cache_enabled'] == defaults['web']['cache_enabled']
                and config['web']['keyless_rescue'] is False
                and config['auth'] == {'adopt_external_logins': False}
                and config['dashboard']['require_auth'] is True and bundle['contract']['native_dashboard']['auth_required']
                and config['platforms']['telegram'] == {'enabled': True}
                and config['platforms']['discord'] == {'enabled': False}, 'native_configuration_source_contract')
        require(bundle['soul'].encode() == self.verified(self.args.repository / 'config/SOUL.md')
                == self.verified(self.args.repository / 'plugins/friday_rework/SOUL.md'), 'Friday_personality_bytes_changed')

    def capability_controls(self, H, safe):
        env = {'current': lambda: S(binding={'tools': sorted(safe)}, home=Path('/fixture/ordinary')),
               'check_database': lambda cap: None, '_DELEGATION': S(get=lambda: None)}
        self.selected(H / 'hermes_cli/friday_user_scope.py', 'ScopeDenied', env)
        guard = self.selected(H / 'hermes_cli/friday_user_scope.py', 'guard_tool', env)
        for name in sorted(REQUIRED):
            self.check('actual_guard_allows_explicit_ordinary_' + name, lambda n=name: guard(n, {}), 'capability')
        for name in ['terminal', 'process_manage']:
            self.refusal('actual_guard_denies_ordinary_' + name, lambda n=name: guard(n, {}), 'product_user_scope_refused', 'capability_negative')

    def result(self):
        parent_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        child_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024
        require(parent_rss + child_rss < 1024**3, 'observed_memory_bound_exceeded')
        return {'schema': 'friday.normal28-current-source-gate-controls.v1', 'status': 'AUTHOR_SOURCE_ONLY_PASS',
                'passed': len(self.rows), 'failed': 0, 'checks': self.rows, 'baseline_sha256': BASELINE_SHA256,
                'subject': {'project_files': 127, 'source_files': 17647, 'layers': 28, 'final_prerequisites': 27,
                            'original24_files': 17636, 'skills25_files': 17639, 'nominal_donor_files': 17590},
                'selected_bodies': self.bodies, 'read_pins': self.reads,
                'layer_graph': [{'patch': n, 'manifest': r['manifest'], 'manifest_sha256': r['manifest_sha256'],
                                 'patch_sha256': r['patch_sha256'], 'requires': r['requires'],
                                 'file_count': len(r['files'])} for n, r in self.ordered],
                'fixtures': ['profile identity: default only', 'env-name reference validation only',
                             'three-platform Enum and two token-name maps; no credential values',
                             'enabled worker runtime validator always refuses',
                             'guard ordinary principal only; database/ambient delegation inert'],
                'fixture_imports': self.imports, 'git_operations': {'numstat_only_calls': self.git_calls,
                                                                 'apply': 0, 'export': 0, 'optional_locks': False},
                'full_subject_modules_imported': 0, 'subject_module_initializers': 0,
                'native_import_MRO_build_auth_TLS_installation_gate': 'NOT_RUN', 'runtime': 'NOT_RUN',
                'independent_acceptance': False, 'effect_admission': False,
                'normal3600': 'UNSTARTED', 'kernel120': 'NOT_GRANTED', 'G8': 'OWNER_STEP_PENDING_NOT_EXECUTED',
                'ordinary_terminal_process': 'DENIED', 'workers_admitted': False,
                'credentials_read': False, 'affinity': sorted(os.sched_getaffinity(0)),
                'final_subject_seal': 'ALL_PROJECT_AND_24_25_28_SOURCE_BYTES_MODES_AND_RECEIPT_PINS_UNCHANGED',
                'source_gate_elapsed_seconds': round(time.monotonic() - self.started_mono, 3),
                'memory_observation': {'parent_peak_rss_bytes': parent_rss,
                                       'sequential_git_child_peak_rss_bytes': child_rss,
                                       'conservative_sum_below_1GiB': True},
                'address_space_limit': list(resource.getrlimit(resource.RLIMIT_AS))}

    def seal_subject(self):
        """Final pin verification, not another control run or runtime gate."""
        a, b = self.args, self.baseline
        self.pinned_json(a.baseline, BASELINE_SHA256)
        self.pinned_json(a.project_files, b['project_files_sha256'])
        for key, path in [('original24', a.original_receipt), ('skills25', a.skills_receipt),
                          ('normal28', a.receipt), ('final_r5', a.r5_receipt)]:
            self.pinned_json(path, b['receipts'][key])
        self.inventory(a.repository, b['project'])
        for key, root in [('original24', a.original_source), ('skills25', a.skills_source), ('normal28', a.source)]:
            self.inventory(root, self.receipts[key]['files'])
        for row in self.bodies:
            require(sha(self.read(Path(row['path']))) == row['file_sha256'], 'selected_body_seal_changed')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ['repository', 'source', 'original-source', 'skills-source', 'receipt', 'project-files', 'baseline',
                 'original-receipt', 'skills-receipt', 'r5-receipt', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=600)
    args = parser.parse_args(argv)
    require(0 < args.seconds <= 1800, 'finite_source_gate_budget_required')
    for name in ['repository', 'source', 'original_source', 'skills_source', 'receipt', 'project_files', 'baseline',
                 'original_receipt', 'skills_receipt', 'r5_receipt']:
        path = getattr(args, name)
        require(path.is_absolute() and path.resolve() == path, 'canonical_input_required')
    require(args.repository.is_dir() and args.source.is_dir(), 'subject_directories_required')
    out = args.output
    require(out.is_absolute() and out.parent.resolve() == out.parent and not out.exists()
            and not out.is_symlink(), 'fresh_output_required')
    require(not any(out.is_relative_to(root) for root in [args.repository, args.source,
                                                       args.original_source, args.skills_source]),
            'output_inside_subject_refused')
    info = out.parent.stat()
    require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, 'private_output_parent_required')
    os.umask(0o077)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    gate = Gate(args)
    gate.source_controls()
    gate.renderer_controls()
    gate.seal_subject()
    result = gate.result()
    gate.remaining()
    payload = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        gate.remaining(); stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({'AUTHOR_SOURCE_PASS': result['passed'], 'runtime': 'NOT_RUN',
                      'independent_acceptance': False, 'output_sha256': sha(payload)}))


if __name__ == '__main__':
    main()
