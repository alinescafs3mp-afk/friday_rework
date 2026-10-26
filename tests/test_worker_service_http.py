"""Second public web edge and existing source consumers; no native imports."""
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_worker_service_source as source
import test_worker_service_native as native


d = source.declaration
ANCHOR = d.WEB_PROBE_TARGET
TARGET = d.WEB_HTTP_TARGET
DISCRIMINATOR = d.WEB_HTTP_SERVICE_DISCRIMINATOR


class HttpServiceEdge(unittest.TestCase):
    def test_current_public_bytes_match_second_target_and_first_edge_is_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        for name, digest in TARGET.items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(d.service_transition_discriminator(d.SERVICE_ANCHOR, ANCHOR),
            d.WEB_PROBE_SERVICE_DISCRIMINATOR)
        self.assertEqual(d.service_transition_discriminator(ANCHOR, TARGET), DISCRIMINATOR)
        self.assertEqual(d.service_transition_pair(DISCRIMINATOR), (ANCHOR, TARGET))
        self.assertEqual(d.service_installed_discriminator(TARGET), DISCRIMINATOR)

    def test_only_exact_second_edge_and_unchanged_observations_are_accepted(self):
        for old, new, expected in ((ANCHOR, ANCHOR, False), (ANCHOR, TARGET, True), (TARGET, TARGET, False)):
            self.assertIs(d.service_source_edge(old, new, ANCHOR), expected)
        self.assertEqual(set(d.service_source_transition(ANCHOR, TARGET)), source.CHANGED)
        for old, new in ((d.SERVICE_ANCHOR, TARGET), (TARGET, ANCHOR), (TARGET, TARGET)):
            with self.assertRaises(d.DeclarationError): d.service_source_transition(old, new)
        for name in TARGET:
            changed = dict(TARGET); changed[name] = 'f' * 64
            with self.subTest(name=name), self.assertRaises(d.DeclarationError):
                d.service_source_transition(ANCHOR, changed)
        for bad in (None, [], True, 'foreign'):
            with self.assertRaises(d.DeclarationError): d.service_transition_pair(bad)

    def second_fixture(self):
        data = source.fixture()
        old = source.get(data.root, source.TEMPLATE_INPUTS)
        old['workers']['a0']['a0']['runtime']['sha256'] = ANCHOR['scripts/a0_runtime.py']
        data.incoming['workers']['a0']['a0']['runtime']['sha256'] = TARGET['scripts/a0_runtime.py']
        data.bundle['changes'][0]['before_sha256'] = source.fingerprint(old)
        data.bundle['changes'][0]['after_reference']['sha256'] = source.fingerprint(data.incoming)
        return data

    def test_second_declaration_retains_ordinary_identity_and_other_inputs(self):
        data = self.second_fixture(); before = source.encoded(data.root)
        plan = source.plan(data)
        self.assertEqual(plan['service_source_transition'], DISCRIMINATOR)
        self.assertFalse(plan['native_authority'])
        self.assertEqual(len(plan['semantic_changes']), 1)
        self.assertEqual(source.encoded(data.root), before)
        self.assertEqual(plan['profile_config'], data.profile)
        for path, value in ((('workers', 'a0', 'a0', 'runtime', 'sha256'), d.WEB_PROBE_RUNTIME_SHA256),
                (('workers', 'a0', 'a0', 'launcher', 'sha256'), 'f' * 64),
                (('workers', 'dsh', 'budget_seconds'), True)):
            bad = self.second_fixture(); source.put(bad.incoming, path, value)
            with self.subTest(path=path), self.assertRaises(d.DeclarationError): source.plan(bad)

    def test_second_installation_requires_same_already_installed_tuple(self):
        current = native.installed_tuple(); current['project_files'].update(TARGET)
        plan = {'service_source_transition': DISCRIMINATOR}
        d.service_installation_delta(current, copy.deepcopy(current), plan)
        for wrong in (d.WEB_PROBE_SERVICE_DISCRIMINATOR, 'foreign', True):
            with self.assertRaises(d.DeclarationError):
                d.service_installation_delta(current, current, {'service_source_transition': wrong})
        changed = copy.deepcopy(current); changed['budget_seconds'] = True
        with self.assertRaises(d.DeclarationError): d.service_installation_delta(current, changed, plan)

    def test_operator_selects_second_donors_and_refuses_first_beforeimage(self):
        operator = native.operator_namespace()['StoppedOperator']({}, None)
        operator.home = Path('/synthetic/home')
        operator.f = SimpleNamespace(ROOT=Path('/synthetic/canonical'))
        operator.previous = native.installed_tuple(); operator.previous['project_files'].update(TARGET)
        operator.current = copy.deepcopy(operator.previous)
        operator.request['before'] = {name: {'path': str(operator.home / name),
            'sha256': ANCHOR[name.removeprefix('worker-runtime-source/')]}
            for name in native.SOURCE_NAMES}
        calls = []
        def pin(ref, private=False):
            calls.append(copy.deepcopy(ref)); path = Path(ref['path'])
            operator.external[path] = {'data': b'neutral donor'}
            return path
        operator._pin = pin
        operator._service_source_layout()
        self.assertEqual({r['path']: r['sha256'] for r in calls},
            {str(operator.f.ROOT / name): digest for name, digest in TARGET.items()})
        self.assertEqual(set(operator.service_after), set(native.SOURCE_NAMES))
        for name in native.SOURCE_NAMES:
            operator.request['before'][name]['sha256'] = d.SERVICE_ANCHOR[name.removeprefix('worker-runtime-source/')]
        with self.assertRaises(native.declaration.DeclarationError): operator._service_source_layout()

    def test_writer_joins_second_edge_and_rejects_first_edge_or_mixed_donor(self):
        namespace = native.extract(native.MODULES / 'worker_declaration_writer.py',
            ('_service_publication_names', '_service_afterimages'), {
                'require': d.require, 'service_transition_pair': d.service_transition_pair,
                'service_publication_sources': d.service_publication_sources, 'hashlib': hashlib})
        authority = SimpleNamespace(home=Path('/synthetic/home'), before={}, service_after={})
        digests = {}
        for name in native.SOURCE_NAMES:
            relative = name.removeprefix('worker-runtime-source/')
            old = ('old:' + name).encode(); new = ('new:' + name).encode()
            digests[old], digests[new] = ANCHOR[relative], TARGET[relative]
            authority.before[name] = {'data': old, 'mode': 0o400}
            authority.service_after[name] = {'data': new}
        def digest(data): return SimpleNamespace(hexdigest=lambda: digests[data])
        with patch.object(hashlib, 'sha256', side_effect=digest):
            plan = {'service_source_transition': DISCRIMINATOR}
            self.assertIs(namespace['_service_afterimages'](authority, plan), authority.service_after)
            with self.assertRaises(d.DeclarationError):
                namespace['_service_afterimages'](authority,
                    {'service_source_transition': d.WEB_PROBE_SERVICE_DISCRIMINATOR})
            digests[authority.service_after[native.SOURCE_NAMES[0]]['data']] = 'f' * 64
            with self.assertRaises(d.DeclarationError): namespace['_service_afterimages'](authority, plan)


if __name__ == '__main__': unittest.main()
