"""Real native prompt assembly, admission and cache continuation; synthetic users only.

These tests prove prompt adoption and native state preservation, not model style.
Run with the fully composed Native62 checkout on sys.path and project tests available.
"""
import copy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pathlib import Path
from contextlib import contextmanager
import contextvars
import weakref


@pytest.fixture
def env(tmp_path,monkeypatch):
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.friday_product_access import KEY,principal_id
    from hermes_cli.plugins_state import PluginState
    from gateway.config import Platform
    from gateway.session import SessionSource
    from gateway.session_identity import RoutingIdentity
    root=tmp_path/'home';root.mkdir(mode=0o700)
    monkeypatch.setenv('HERMES_HOME',str(root))
    import hermes_constants as hc
    monkeypatch.setattr(hc,'_PINNED_PROCESS_HERMES_HOME',str(root))
    monkeypatch.setattr(scope,'_CURRENT',contextvars.ContextVar('dialogue-test-current',default=None))
    monkeypatch.setattr(scope,'_SOURCE',contextvars.ContextVar('dialogue-test-source',default=None))
    monkeypatch.setattr(scope,'_ENGAGED',False)
    def write(p,v):p.write_text(json.dumps(v));p.chmod(0o600)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    bindings=[dict(platform='telegram',transport_profile='default',account_id='synthetic-account',user_id=str(i),runtime_profile='fixture-user-'+str(i),tools=['memory','read_file']) for i in (1,2)]
    cfg={'plugins':{'enabled':['friday_rework'],'entries':{'friday_rework':{'settings':{'product_access':{'enabled':True,'accounts':[dict(platform='telegram',transport_profile='default',account_id='synthetic-account',runtime_profiles=[b['runtime_profile'] for b in bindings])]},'user_isolation':{'enabled':True,'bindings':bindings}}}}},'gateway':{'multiplex_profiles':True,'profile_routes':[{'name':'friday-'+principal_id(*(b[k] for k in ('platform','transport_profile','account_id','user_id'))),'platform':b['platform'],'bot_profile':b['transport_profile'],'user_id':b['user_id'],'profile':b['runtime_profile'],'enabled':True} for b in bindings]}}
    write(root/'config.yaml',cfg)
    rows={principal_id(*(b[k] for k in ('platform','transport_profile','account_id','user_id'))):{k:b[k] for k in ('platform','transport_profile','account_id','user_id')}|dict(enabled=True,role='user') for b in bindings}
    with scope.authority(root):PluginState('friday_rework').set(KEY,dict(schema=KEY,users=rows))
    homes={};sources={};adapters=[]
    class Adapter:pass
    for b in bindings:
        h=scope.provision_new_home(root,b,{'max_iterations':8});homes[b['user_id']]=h
        (h/'SOUL.md').write_text('Synthetic signed identity: Пятница. Preserve safety and tool authority.\n');(h/'SOUL.md').chmod(0o600)
        (h/'.env').write_text('SYNTHETIC_FIXTURE_KEY=offline-fixture\n');(h/'.env').chmod(0o600)
        st=h.stat();receipt=dict(schema='friday.onboarding.v1',binding_sha256=scope._fingerprint(b),config_sha256=sha(h/'config.yaml'),soul_sha256=sha(h/'SOUL.md'),required_secrets=['SYNTHETIC_FIXTURE_KEY'],directory_identity=[st.st_dev,st.st_ino],template='synthetic',authorization_home=str(root))
        write(h/scope.ONBOARDING,receipt)
        marker=json.loads((h/scope.MARKER).read_text());marker['onboarding_sha256']=sha(h/scope.ONBOARDING);write(h/scope.MARKER,marker)
        adapter=Adapter();adapters.append(adapter)
        s=SessionSource(Platform.TELEGRAM,'synthetic-chat',user_id=b['user_id'],chat_type='dm',profile=b['runtime_profile'])
        s._identity=RoutingIdentity('default',b['runtime_profile'],root,h,multiplexed=True,transport_inferred=False,transport=weakref.ref(adapter))
        with scope.authority(root):scope.admit_source(s)
        sources[b['user_id']]=s
    token=set_hermes_home_override(str(root))
    try:yield SimpleNamespace(root=root,homes=homes,sources=sources,adapters=adapters)
    finally:reset_hermes_home_override(token)


def home(env,uid='1'):return env.homes[uid]
def complete(env,uid='1'):return None


@contextmanager
def entered(env,uid='1'):
    with scope.authority(home(env,uid)),scope.scoped_source(env.sources[uid]) as cap:yield cap


def own_db(env):
    from hermes_state import SessionDB
    with entered(env):
        db=SessionDB(home(env)/'state.db')
        db.create_session('actual-native-own-session','telegram',user_id='1',profile_name='fixture-user-1',origin_json=json.dumps({'friday_account_origin':{'schema':'friday.account_origin.v1','platform':'telegram','transport_profile':'default','account_id':'synthetic-account'}}),model_config={'keep_native_field':'PRESERVE'})
        db.append_message('actual-native-own-session','user','Continue my original task')
    return db


def tool_definition(description):
    return {'type':'function','function':{'name':'read_file','description':description,'parameters':{'type':'object','properties':{}}}}


def revoke(env):scope.current(required=True).revoked=True
from hermes_cli import friday_prompt_scope as ps, friday_user_scope as scope
from agent import system_prompt as sp, conversation_loop as loop


def native_agent(db=None, caching=False):
    a = SimpleNamespace(
        load_soul_identity=True, skip_context_files=False, valid_tool_names={'read_file'},
        _task_completion_guidance=False, _parallel_tool_call_guidance=False,
        _tool_use_enforcement=False, _execution_guidance=False, _environment_probe=False,
        _kanban_worker_guidance='', _memory_store=None, _memory_manager=None,
        model='local-test', provider='custom', platform='cli', pass_session_id=False,
        session_id='actual-native-own-session', _session_db=db, _use_prompt_caching=caching,
        _cached_system_prompt=None, _cached_system_prompt_static=None,
        _persist_disabled=True, enabled_toolsets=None, disabled_toolsets=None,
        _platform_hint_overrides=None, _session_title_hint='', _surface_switch_note='',
        _gateway_turn_context_notes='', _plugin_system_prompt_sections_snapshot=(),
        _emit_diagnostic_status=lambda *_args: None, tools=[tool_definition('CURRENT_GRANTED')],
        context_compressor=SimpleNamespace(context_length=32768))
    scope.capture_agent(a)
    a._build_system_prompt=MagicMock(side_effect=lambda msg: sp.build_system_prompt(a,msg))
    return a


def protected(home):
    return {n:hashlib.sha256((home/n).read_bytes()).hexdigest()
            for n in ('SOUL.md','config.yaml',scope.MARKER,scope.ONBOARDING)}


def test_effective_prompt_preserves_signed_identity_caller_and_tools(env, monkeypatch):
    complete(env)
    monkeypatch.chdir(home(env))
    with entered(env):
        a=native_agent();before=protected(home(env));tools=copy.deepcopy(a.tools)
        text=sp.build_system_prompt(a,'CALLER_CONTEXT_SENTINEL')
        assert text.count(ps.DIALOGUE_GUIDANCE)==1
        assert 'CALLER_CONTEXT_SENTINEL' in text
        assert (home(env)/'SOUL.md').read_text().strip() in text
        assert a._cached_system_prompt_static.count(ps.DIALOGUE_GUIDANCE)==1
        assert a.tools==tools and protected(home(env))==before
        assert 'в ответ на новое приветствие' in ps.DIALOGUE_GUIDANCE
        assert 'без обязательных шаблонных' in ps.DIALOGUE_GUIDANCE


@pytest.mark.parametrize('caching',[False,True])
@pytest.mark.parametrize('old_revision',[None,'friday.natural-dialogue.obsolete'])
def test_old_cached_prompt_rebuilds_once_with_transcript_and_authority_retained(env, monkeypatch, caching, old_revision):
    complete(env);monkeypatch.chdir(home(env));db=own_db(env)
    try:
        with entered(env) as cap:
            old=native_agent(db,caching)
            # A historical cached prompt uses exactly the Source61 stamp key set.
            db.update_system_prompt(old.session_id,'PRE_REVISION_CACHED_PROMPT')
            db.update_session_tool_names(old.session_id,[tool_definition('OLD_CACHED_PIN')])
            row=db.get_session(old.session_id);meta=json.loads(row['model_config'])
            if old_revision is None:meta[ps.FIELD].pop('dialogue_revision')
            else:meta[ps.FIELD]['dialogue_revision']=old_revision
            db.update_session_meta(old.session_id,json.dumps(meta))
            db.append_message(old.session_id,'assistant','The synthetic remembered value is cedar.')
            db.append_message(old.session_id,'user','Use the value from before.')
            history=copy.deepcopy(db.get_messages(old.session_id));before=protected(home(env))
            stale=db.get_session(old.session_id)
            fresh=native_agent(db,caching)
            assert not ps.matches(fresh,stale['system_prompt'],stale)
            loop._restore_or_build_system_prompt(fresh,'RETAIN_CALLER_CONTEXT',history)
            fresh._build_system_prompt.assert_called_once()
            effective=fresh._cached_system_prompt
            assert effective.count(ps.DIALOGUE_GUIDANCE)==1 and 'RETAIN_CALLER_CONTEXT' in effective
            committed=db.get_session(old.session_id);stored=json.loads(committed['model_config'])
            assert stored['keep_native_field']=='PRESERVE'
            assert stored[ps.FIELD]['dialogue_revision']==ps.DIALOGUE_REVISION
            assert stored[ps.FIELD]['generation']==cap.admission_generation
            assert ps.matches(fresh,effective,committed)
            assert 'OLD_CACHED_PIN' not in json.dumps(fresh.tools)
            assert db.get_messages(old.session_id)==history
            assert protected(home(env))==before
            resumed=native_agent(db,caching)
            loop._restore_or_build_system_prompt(resumed,None,history)
            resumed._build_system_prompt.assert_not_called()
            assert resumed._cached_system_prompt==effective
            assert db.get_messages(old.session_id)==history
            assert protected(home(env))==before
    finally:db.close()


def test_guidance_cannot_authorize_foreign_or_revoked_agent(env,monkeypatch):
    complete(env,'1');complete(env,'2')
    with entered(env,'1'):
        a=native_agent();assert ps.dialogue_parts(a)==[ps.DIALOGUE_GUIDANCE, ps.CONFIDENTIALITY_GUIDANCE]
    with entered(env,'2'):
        with pytest.raises(scope.ScopeDenied):sp.build_system_prompt(a)
    with entered(env,'1'):
        a=native_agent();revoke(env)
        with pytest.raises(scope.ScopeDenied):sp.build_system_prompt(a)


def test_unscoped_native_prompt_unchanged_and_donor_cache_reuse(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(scope,'_ENGAGED',False)
    a=native_agent();a.load_soul_identity=False;a.skip_context_files=True
    assert ps.dialogue_parts(a)==[]
    before=sp.build_system_prompt(a,'DONOR_CONTEXT')
    with monkeypatch.context() as m:
        m.setattr(sp,'_friday_dialogue_parts',lambda agent: [])
        assert sp.build_system_prompt(a,'DONOR_CONTEXT')==before
    assert ps.DIALOGUE_GUIDANCE not in before
    row={'system_prompt':'EXACT_DONOR_CACHE','model_config':'{}'}
    assert ps.matches(a,row['system_prompt'],row)


def test_revision_rebuild_pin_clear_is_atomic_with_prompt_commit(env,monkeypatch):
    db=own_db(env)
    try:
        with entered(env):
            a=native_agent(db)
            db.update_system_prompt(a.session_id,'OLD_PROMPT')
            db.update_session_tool_names(a.session_id,[tool_definition('OLD_PIN')])
            meta=json.loads(db.get_session(a.session_id)['model_config']);meta[ps.FIELD].pop('dialogue_revision')
            db.update_session_meta(a.session_id,json.dumps(meta))
            before=db.get_session(a.session_id)
            with monkeypatch.context() as m:
                def failed(*args,**kwargs):raise OSError('synthetic native prompt transaction failure')
                m.setattr(db,'_store_system_prompt',failed)
                with pytest.raises(OSError):db.update_system_prompt(a.session_id,'UNCOMMITTED_PROMPT')
            after=db.get_session(a.session_id)
            assert all(after[k]==before[k] for k in ('system_prompt','tool_names','model_config'))
            assert not ps.matches(a,after['system_prompt'],after)
            db.update_system_prompt(a.session_id,'CURRENT_PROMPT')
            committed=db.get_session(a.session_id)
            assert committed['tool_names'] is None
            assert ps.matches(a,committed['system_prompt'],committed)
    finally:db.close()


def test_managed_readonly_core_projection_preserves_dialogue_and_context(env,monkeypatch):
    from agent.bounded_context import BoundedContextPolicy
    from hermes_cli import friday_credential_admission as admission
    from tools.file_tools import READ_FILE_SCHEMA
    from agent.coding_context import CODING_AGENT_GUIDANCE, _TODO_SENTENCE, _NO_TODO_SENTENCE
    import agent.coding_context as cc
    native_coding=cc.coding_system_prompt_parts
    monkeypatch.setattr(cc,'coding_system_prompt_parts',lambda **kwargs:native_coding(**kwargs,config={'agent':{'coding_context':'on'}}))
    monkeypatch.chdir(home(env)/'workspace')
    policy=BoundedContextPolicy('custom:friday-local','dispatcher','http://127.0.0.1:9000/v1',40960,40954,4096,4096,1024,2048,4096)
    monkeypatch.setattr(admission,'_ORDINARY_READONLY',(home(env),{},{}))
    monkeypatch.setattr(admission,'cli_ordinary_readonly_current',lambda *args:None)
    monkeypatch.setattr('agent.bounded_context.configured_policy',lambda:policy)
    with entered(env):
        a=native_agent();a._bounded_context_policy=policy
        custom=copy.deepcopy(READ_FILE_SCHEMA)
        # The already-admitted bounded lane's narrow schema, not generic file continuation.
        custom['parameters']['properties'].pop('char_offset',None)
        a.tools=admission.ordinary_readonly_schemas([{'type':'function','function':custom}])
        a.context_compressor.context_length=40960
        brief=CODING_AGENT_GUIDANCE.replace(_TODO_SENTENCE,_NO_TODO_SENTENCE)
        a._frozen_workspace_snapshot=(sp._workspace_pin_key(),'')
        direct=cc.coding_system_prompt_parts(platform=a.platform,cwd=home(env),model=a.model,valid_tool_names=a.valid_tool_names,workspace_block='')
        assert direct[0]
        prompt=sp.build_system_prompt(a,'UNTOUCHED_CONTEXT\n\n'+brief)
        rendered=sp.render_ordinary_readonly_prompt(a,prompt)
        assert rendered!=prompt, (sp._coding_parts(a), prompt[:len(prompt)-len(ps.DIALOGUE_GUIDANCE)])
        assert rendered.count(ps.DIALOGUE_GUIDANCE)==1
        assert 'UNTOUCHED_CONTEXT\n\n'+brief in rendered
        assert (home(env)/'SOUL.md').read_text().strip() in rendered
        assert 'If the same region fails twice' in rendered

def test_managed_prompt_uses_product_help_and_confidentiality_without_backend_advertising(env,monkeypatch):
    monkeypatch.chdir(home(env))
    with entered(env):
        a=native_agent()
        effective=sp.build_system_prompt(a,None)
        assert effective.count(ps.CONFIDENTIALITY_GUIDANCE)==1
        assert effective.count(ps.PRODUCT_HELP_GUIDANCE)==1
        assert sp.HERMES_AGENT_HELP_GUIDANCE not in effective
        assert sp.HERMES_AGENT_HELP_GUIDANCE_NO_SKILLS not in effective
        for donor in (sp.HERMES_AGENT_HELP_GUIDANCE,sp.HERMES_AGENT_HELP_GUIDANCE_NO_SKILLS):
            assert ps.product_help_guidance(a,donor)==ps.PRODUCT_HELP_GUIDANCE
        assert 'не подтверждают его статус' in ps.CONFIDENTIALITY_GUIDANCE
        assert 'Не выдумывай работодателя' in ps.CONFIDENTIALITY_GUIDANCE
        assert 'это правило не запрещает их читать' in ps.CONFIDENTIALITY_GUIDANCE
        revoke(env)
        with pytest.raises(scope.ScopeDenied):ps.product_help_guidance(a,'donor')


def test_unscoped_product_help_preserves_each_native_variant():
    assert scope.current() is None
    for donor in (sp.HERMES_AGENT_HELP_GUIDANCE,sp.HERMES_AGENT_HELP_GUIDANCE_NO_SKILLS):
        assert ps.product_help_guidance(native_agent(),donor)==donor
