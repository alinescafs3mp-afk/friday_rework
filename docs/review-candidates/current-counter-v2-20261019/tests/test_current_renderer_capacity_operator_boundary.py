"""Synthetic operator schema isolation; no deployment readiness is attested.

Prepared source only. Run solely inside the parent's authorized fixture boundary
against the capacity AFTERIMAGE operator. Renderer loading is deliberately
replaced by a synthetic return so these are delta-contract tests only.
"""
import copy
import pytest
from scripts import friday_ordinary_install as operator


def product(capacity=40960):
    return {
        'inference': {'key_env': 'FRIDAY_LLM_API_KEY', 'model': 'synthetic-primary',
                      'context': 262144},
        'compression_inference': {
            'key_env': 'FRIDAY_COMPRESSION_API_KEY', 'model': 'dispatcher',
            'context': capacity, 'max_input': capacity - 6,
            'main_output': 4096, 'summary_output': 4096,
            'margin': 1024, 'template_overhead': 2048},
        'compression_multipass': {'enabled': True, 'max_calls': 64},
        'runtime': {'enabled': False},
        'retained_budget': {'seconds': 1800, 'consumed': True}}


def exact():
    return {'binding': {'path': '/synthetic/current-binding.json', 'sha256': 'a' * 64},
            'deployment': {'path': '/synthetic/current-deployment.json', 'sha256': 'b' * 64}}


@pytest.mark.parametrize('capacity', [40960, 65536])
def test_v3_initial_add_is_available_at_either_supported_capacity(monkeypatch, capacity):
    old = product(capacity)
    new = copy.deepcopy(old)
    new['compression_inference']['exact_renderer'] = exact()
    before = copy.deepcopy((old, new))
    seen = []
    def references(value):
        seen.append(copy.deepcopy(value))
        return ('synthetic-binding', 'synthetic-deployment')
    monkeypatch.setattr(operator, 'inference_renderer_references', references)
    assert operator.inference_renderer_delta(old, new) == ('synthetic-binding', 'synthetic-deployment')
    assert seen == [new] and (old, new) == before


@pytest.mark.parametrize('bound', [False, True])
def test_capacity_upgrade_preserves_renderer_absence_or_exact_binding(bound):
    old = product()
    if bound:
        old['compression_inference']['exact_renderer'] = exact()
    new = copy.deepcopy(old)
    new['compression_inference'].update(context=65536, max_input=65530)
    before = copy.deepcopy((old, new))
    operator.inference_capacity_delta(old, new)
    assert (old, new) == before


def test_no_schema_can_combine_capacity_upgrade_and_initial_renderer_add(monkeypatch):
    old = product()
    new = copy.deepcopy(old)
    new['compression_inference'].update(context=65536, max_input=65530, exact_renderer=exact())
    def forbidden(*args):
        raise AssertionError('renderer validation must not precede valid delta')
    monkeypatch.setattr(operator, 'inference_renderer_references', forbidden)
    with pytest.raises(ValueError, match='exact_compression_capacity_delta'):
        operator.inference_capacity_delta(old, new)
    with pytest.raises(ValueError, match='exact_compressor_renderer_delta'):
        operator.inference_renderer_delta(old, new)


@pytest.mark.parametrize('change', ['binding', 'deployment', 'remove'])
def test_capacity_cannot_replace_or_remove_an_existing_renderer(change):
    old = product()
    old['compression_inference']['exact_renderer'] = exact()
    new = copy.deepcopy(old)
    new['compression_inference'].update(context=65536, max_input=65530)
    if change == 'remove':
        del new['compression_inference']['exact_renderer']
    else:
        new['compression_inference']['exact_renderer'][change]['sha256'] = 'c' * 64
    with pytest.raises(ValueError, match='exact_compression_capacity_delta'):
        operator.inference_capacity_delta(old, new)


def test_v3_does_not_become_a_replacement_route_when_already_bound(monkeypatch):
    old = product(65536)
    old['compression_inference']['exact_renderer'] = exact()
    new = copy.deepcopy(old)
    new['compression_inference']['exact_renderer']['binding']['sha256'] = 'c' * 64
    def forbidden(*args):
        raise AssertionError('rebind must fail before validating replacement documents')
    monkeypatch.setattr(operator, 'inference_renderer_references', forbidden)
    with pytest.raises(ValueError, match='exact_compressor_renderer_delta'):
        operator.inference_renderer_delta(old, new)
