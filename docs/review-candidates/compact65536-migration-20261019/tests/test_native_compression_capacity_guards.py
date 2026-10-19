"""Native guards and exact accounting envelopes; synthetic counting is no deployment proof."""
from dataclasses import replace
from types import SimpleNamespace
import copy
import pytest
from agent.bounded_context import BoundedContextPolicy,BoundedContextOverflowError,BoundedRendererBindingError
from hermes_cli import friday_credential_admission as admission
from tools.configure_product import compose_product
from test_capacity_legacy_a0 import capacity_spec


def policy(capacity=65536):
    return BoundedContextPolicy('custom:friday-compression','dispatcher','http://192.168.1.78:8001/v1',
        capacity,65530 if capacity==65536 else 40954,4096,4096,1024,2048,4096)


def test_exact_renderer_new_capacity_increases_actual_input_budget_and_preserves_reservation(monkeypatch):
    renderer=SimpleNamespace(identity={'synthetic':True},count=lambda body:{'count':50000,'wire_sha256':'a'*64})
    monkeypatch.setattr(BoundedContextPolicy,'renderer',lambda self:renderer)
    request={'model':'dispatcher','messages':[{'role':'user','content':'synthetic'}],'max_tokens':4096}
    result=policy().check_request(request,compression=True)
    assert result['input_budget']==60416 and result['input_count']==50000
    assert result['output_reservation']==4096
    assert result['verification_scope']=='validated_local_deployment_binding_requires_separate_live_acceptance'
    with pytest.raises(BoundedContextOverflowError):policy(40960).check_request(request,compression=True)
    with pytest.raises(BoundedContextOverflowError):
        renderer.count=lambda body:{'count':60417,'wire_sha256':'a'*64}
        policy().check_request(request,compression=True)


@pytest.mark.parametrize('field,value',[('context_length',65535),('server_max_input_tokens',65529),
    ('main_max_output_tokens',8192),('compression_max_output_tokens',8192),
    ('safety_margin_tokens',512),('template_overhead_tokens',1024),('model','foreign')])
def test_exact_new_renderer_envelope_cannot_expand_or_retune_other_reservations(monkeypatch,field,value):
    renderer=SimpleNamespace(identity={},count=lambda body:{'count':1,'wire_sha256':'a'*64})
    monkeypatch.setattr(BoundedContextPolicy,'renderer',lambda self:renderer)
    p=replace(policy(),**{field:value})
    with pytest.raises(BoundedRendererBindingError):
        p.check_request({'model':p.model,'messages':[{'role':'user','content':'synthetic'}],'max_tokens':4096},compression=True)


def test_native_route_accepts_both_supported_capacity_envelopes():
    spec=capacity_spec();cfg=compose_product(spec)['config']
    assert admission.local_route(cfg)[0]=='custom:friday-local'
    # Preserve the genuine historical route, including its previous input ceiling.
    spec['compression_inference'].update(context=40960,max_input=40954)
    assert admission.local_route(compose_product(spec)['config'])[0]=='custom:friday-local'


@pytest.mark.parametrize('fault',['primary_capacity','model_capacity','auxiliary_capacity','input','margin','output','overhead','context_bool','other_context'])
def test_native_new_capacity_route_refuses_mismatched_or_unreviewed_envelopes(fault):
    cfg=compose_product(capacity_spec())['config']
    model=cfg['providers']['friday-compression']['models']['dispatcher'];bounded=model['bounded_context']
    if fault=='primary_capacity':cfg['model']['context_length']=65536
    elif fault=='model_capacity':model['context_length']=40960
    elif fault=='auxiliary_capacity':cfg['auxiliary']['compression']['context_length']=40960
    elif fault=='input':bounded['server_max_input_tokens']=65529
    elif fault=='margin':bounded['safety_margin_tokens']=512
    elif fault=='output':bounded['compression_max_output_tokens']=8192
    elif fault=='overhead':bounded['template_overhead_tokens']=1024
    elif fault=='context_bool':cfg['auxiliary']['compression']['context_length']=True
    elif fault=='other_context':
        model['context_length']=cfg['auxiliary']['compression']['context_length']=73728
    with pytest.raises(ValueError):admission.local_route(cfg)
