from pathlib import Path
import pytest
from test_ordinary_dialogue_continuation import env,entered,home,native_agent,protected
from agent import prompt_builder as pb, system_prompt as sp
from hermes_cli import friday_prompt_scope as ps, friday_user_scope as scope

@pytest.mark.parametrize('kind',['merged','cursor','individual'])
def test_real_typed_project_context_recovery_is_relative_and_donor_unchanged(env,monkeypatch,kind):
    cwd=home(env)/'workspace'/'project';cwd.mkdir();monkeypatch.chdir(cwd)
    monkeypatch.setattr(pb,'_config_readonly',lambda key:{'context_file_max_chars':20000})
    first='Own top project instructions Hermes Linux Rust. '*330
    second='Own nested project instructions Friday Alice. '*340
    monkeypatch.setattr(pb,'_agents_md_candidates',lambda path:[('../AGENTS.md',cwd.parent/'AGENTS.md',first),('AGENTS.md',cwd/'AGENTS.md',second)])
    monkeypatch.setattr(pb,'_cursorrules_candidates',lambda path:[('.cursorrules',cwd/'.cursorrules','Own cursor project guidance Hermes Linux. '*800)])
    def render():
        if kind=='merged':return pb._load_agents_md(cwd,32768)
        if kind=='cursor':return pb._load_cursorrules(cwd,32768)
        return pb._context_section(first*2,'AGENTS.md','AGENTS.md',cwd/'AGENTS.md',32768)
    with entered(env):
        before=protected(home(env));result=render()
        assert '[...truncated' in result and str(home(env)) not in result
        assert ('tool: project/.cursorrules]' if kind=='cursor' else 'tool: project/AGENTS.md]') in result
        assert 'Hermes Linux' in result and protected(home(env))==before
    monkeypatch.setattr(scope,'_ENGAGED',False)
    donor=render();assert str(cwd/('.cursorrules' if kind=='cursor' else 'AGENTS.md')) in donor


def test_real_long_identity_truncation_does_not_offer_inaccessible_physical_file(env,monkeypatch):
    payload=ps._SHIPPED_IDENTITY+'\n\n'+('Own signed personality; warm humor, language Rust. '*700)
    native_read=pb._read_text_with_timeout
    monkeypatch.setattr(pb,'_read_text_with_timeout',lambda path:payload if Path(path).name=='SOUL.md' else native_read(path))
    monkeypatch.setattr(pb,'_config_readonly',lambda key:{'context_file_max_chars':20000})
    with entered(env):
        before=protected(home(env));result=pb.load_soul_md(32768,home_override=home(env))
        assert result and '[...truncated identity instructions' in result
        assert str(home(env)) not in result and 'tool: ' not in result and 'SOUL.md' not in result
        assert 'not accessible through file tools' in result and 'warm humor' in result
        assert protected(home(env))==before
    monkeypatch.setattr(scope,'_ENGAGED',False)
    donor=pb.load_soul_md(32768,home_override=home(env));assert str(home(env)/'SOUL.md') in donor


def test_foreign_recovery_path_has_no_fallback_and_revoked_agent_has_no_prompt(env,monkeypatch):
    with entered(env):
        with pytest.raises(ValueError):pb._context_read_path(home(env).parent/'foreign'/'AGENTS.md')
        a=native_agent();scope.current(required=True).revoked=True
        with pytest.raises(scope.ScopeDenied):sp.build_system_prompt(a)

@pytest.mark.parametrize('question',['Как тебя зовут?','Как правильно склонять твоё имя?','Кого ты имеешь в виду?','Разбери код Hermes Linux в Alice.py; затем продолжим.'])
def test_representative_questions_are_preserved_without_canned_responses(env,monkeypatch,question):
    monkeypatch.chdir(home(env)/'workspace')
    with entered(env):
        a=native_agent();prompt=sp.build_system_prompt(a,question)
        assert question in prompt and ps.CONFIDENTIALITY_GUIDANCE in prompt
        assert 'Тёплый тон, уместные эмоции и юмор сохраняй' in prompt
        assert 'Имена' not in a.tools[0]['function']['description']


def test_prompt_byte_delta_same_correct68_fixture_tools_and_history(env,monkeypatch):
    import sys,importlib.util,hashlib,json,copy
    from test_ordinary_dialogue_continuation import own_db
    D=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location('_correct68_prompt_scope',D/'predecessor-native/hermes_cli/friday_prompt_scope.py')
    before_scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(before_scope)
    with monkeypatch.context() as m:
        m.setitem(sys.modules,'hermes_cli.friday_prompt_scope',before_scope)
        spec=importlib.util.spec_from_file_location('_correct68_system_prompt',D/'predecessor-native/agent/system_prompt.py')
        before_sp=importlib.util.module_from_spec(spec);spec.loader.exec_module(before_sp)
    soul=(D/'test-project/config/SOUL.md').read_text().strip()
    research=(D/'test-project/config/RESEARCH.md').read_text().strip()
    monkeypatch.setattr(pb,'load_soul_md',lambda *args,**kwargs:soul)
    monkeypatch.setattr(pb,'_embedder_environment_hint',lambda:research)
    monkeypatch.chdir(home(env)/'workspace');db=own_db(env)
    try:
        with entered(env):
            for i in range(13):db.append_message('actual-native-own-session','assistant' if i%2==0 else 'user','Prior actual fixture follow-up '+str(i))
            history=copy.deepcopy(db.get_messages('actual-native-own-session'));protected_before=protected(home(env))
            a=native_agent(db);b=native_agent(db)
            for agent in (a,b):agent.platform='telegram';agent._frozen_workspace_snapshot=(sp._workspace_pin_key(),'')
            old=before_sp.build_system_prompt(a,'SAME_CALLER_CONTEXT');new=sp.build_system_prompt(b,'SAME_CALLER_CONTEXT')
            assert a.tools==b.tools and len(history)==14 and db.get_messages(a.session_id)==history
            assert protected(home(env))==protected_before
            result={'before_correct68_utf8_bytes':len(old.encode()),'after69r2_utf8_bytes':len(new.encode()),'delta_utf8_bytes':len(new.encode())-len(old.encode()),'same_tools':True,'same_history_rows':len(history),'same_protected_signed_files':True,'before_contains_exact_shipped_identity':ps._SHIPPED_IDENTITY in old,'after_contains_exact_shipped_identity':ps._SHIPPED_IDENTITY in new,'canonical_personality_suffix_preserved':soul[len(ps._SHIPPED_IDENTITY):] in new,'private_runtime_home_before':str(home(env)) in old,'private_runtime_home_after':str(home(env)) in new,'full_final_wire_or_latency_measurement':False,'fixture_public_research_hint':True}
            assert result['before_contains_exact_shipped_identity'] and not result['after_contains_exact_shipped_identity']
            assert result['canonical_personality_suffix_preserved'] and not result['private_runtime_home_after']
            (D/'PROMPT-BYTE-DELTA69R2.json').write_text(json.dumps(result,indent=2)+'\n')
    finally:db.close()
