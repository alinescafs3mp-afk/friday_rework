"""Native retry policy boundaries; no network or model calls."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from agent.bounded_context import BoundedContextPolicy, BoundedContextError
from agent.turn_truncation import boosted_output_cap


def make_agent(cap=4096, maximum=4096):
    policy = BoundedContextPolicy('custom:test', 'fixture', 'http://127.0.0.1:8011/v1',
        262144, 240000, cap, 2048, 1024, 2048)
    return SimpleNamespace(max_tokens=maximum, api_mode='chat_completions',
                           _bounded_context_policy=policy)


@pytest.mark.parametrize('cap,base,expected', [(4096,4096,4096),(4096,512,1024),
                                               (1024,512,1024),(8192,4096,8192),
                                               (131072,32768,65536)])
def test_native_retry_uses_selected_profile_reservation(cap,base,expected):
    agent=make_agent(cap,base)
    assert boosted_output_cap(agent,base,1)==expected
    prior=base
    for retry in range(1,5):
        current=boosted_output_cap(agent,prior,retry)
        assert prior <= current <= cap
        prior=current


@pytest.mark.parametrize('field', ['max_tokens','requested','base'])
@pytest.mark.parametrize('bad', [8192,0,-1,True,4096.0,'4096'])
def test_invalid_or_already_over_grant_input_refused(field,bad):
    agent=make_agent(); values={'requested':4096,'base':None}
    if field=='max_tokens':agent.max_tokens=bad
    else:values[field]=bad
    with pytest.raises(BoundedContextError):
        boosted_output_cap(agent,values['requested'],1,values['base'])


def test_unbounded_native_growth_and_anthropic_ceiling_unchanged(monkeypatch):
    agent=make_agent();agent._bounded_context_policy=None
    assert boosted_output_cap(agent,4096,1)==8192
    assert boosted_output_cap(agent,4096,4)==32768
    from agent import turn_truncation
    monkeypatch.setattr(turn_truncation, '_model_output_limit', lambda a: 8192)
    assert boosted_output_cap(agent,4096,4)==8192
    assert boosted_output_cap(agent,8192,1)==8192


def test_bound_policy_keeps_final_wire_guard():
    policy=make_agent()._bounded_context_policy
    with pytest.raises(BoundedContextError,match='output cap exceeds policy reservation'):
        policy.check_request({'model':'fixture','messages':[{'role':'user','content':'test'}],
                              'max_tokens':8192})


def test_missing_native_defaults_use_selected_reservation():
    assert boosted_output_cap(make_agent(1024,None),None,1)==1024
