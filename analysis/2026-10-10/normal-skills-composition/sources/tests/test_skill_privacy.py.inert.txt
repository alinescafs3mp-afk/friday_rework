from test_user_onboarding import save
"""Real native registered consumers; synthetic principals and secrets, no network."""
import json
from types import SimpleNamespace
import pytest
from test_user_onboarding import env, complete, home, ident
from test_ordinary_skills import entered, document, dispatch
from test_user_isolation import users
from hermes_cli import friday_user_scope as scope
from agent import skill_utils, skill_commands, system_prompt
from tools import skills_tool, skill_usage

SENTINEL='SYNTHETIC_OTHER_PRINCIPAL_SECRET'
EXPR='${FRIDAY_REPAIR_ONLY_SENTINEL}'


def install_document(root, body):
    folder=root/'skills'/'procedure';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    p=folder/'SKILL.md';p.write_text(body);p.chmod(0o600)
    return p


def config_document():
    return ('---\nname: procedure\ndescription: Native config regression\nmetadata:\n  hermes:\n    config:\n'
            '      - key: docpath\n        description: Own configured document path\n'
            '        default: "'+EXPR+'"\n---\nOwn verified procedure.\n')


@pytest.mark.parametrize('configured',[False,True])
def test_real_preload_and_agent_autoload_keep_arbitrary_variables_literal(env,monkeypatch,configured):
    env.template['config']['skills'].update({'auto_load':['procedure'],'config':{'docpath':EXPR} if configured else {}})
    save(env,env.cfg)
    if configured:
        with pytest.raises(ValueError,match="ambient_templates_or_credentials_refused"):
            complete(env)
        return  # Real onboarding refuses ambient config before creating an admitted home.
    complete(env);install_document(home(env),config_document())
    monkeypatch.setenv('FRIDAY_REPAIR_ONLY_SENTINEL',SENTINEL)
    with entered(env):
        text,names,missing=skill_commands.build_preloaded_skills_prompt(['procedure'])
        assert names==['procedure'] and not missing
        assert 'docpath = '+EXPR in text and SENTINEL not in text
        agent=SimpleNamespace(valid_tool_names=['skill_view'],session_id='native-autoload')
        parts=system_prompt._auto_load_parts(agent)
        assert parts and 'docpath = '+EXPR in parts[0] and SENTINEL not in ''.join(parts)
        assert system_prompt._auto_load_parts(agent)==parts


def test_explicit_own_paths_do_not_use_host_home_or_lookalike_variables(users,monkeypatch):
    monkeypatch.setenv('HOME','/not-the-product-user')
    monkeypatch.setenv('HOME_SECRET',SENTINEL)
    monkeypatch.setenv('HERMES_HOME_SECRET',SENTINEL)
    monkeypatch.setenv('FRIDAY_REPAIR_ONLY_SENTINEL',SENTINEL)
    with users.enter(0):
        expected=str(users.homes[0]/'home')
        for value in ('~','~/notes','$HOME','${HOME}','$HOME/notes','${HOME}/notes'):
            result=skill_utils._expand_skill_config_path(value)
            assert result==(expected+'/notes' if value.endswith('/notes') else expected)
        assert skill_utils._expand_skill_config_path('${HERMES_HOME}/skills')==str(users.homes[0]/'skills')
        for value in ('$HOME_SECRET','$HERMES_HOME_SECRET','${FRIDAY_REPAIR_ONLY_SENTINEL}','~another-user/docs'):
            assert skill_utils._expand_skill_config_path(value)==value


def revoke(env):
    with scope.authority(env.home):
        env.admin.set_user('default',**ident(),enabled=False,role='user')


@pytest.mark.parametrize('bridge',['registry','model_tools'])
def test_real_registered_view_never_returns_content_after_telemetry_revocation(env,monkeypatch,bridge):
    complete(env);install_document(home(env),document(body='PRIVATE_CONTENT_MUST_NOT_RETURN'))
    import model_tools
    def interrupted(*a,**kw):
        revoke(env)
        scope.current()  # real sticky revocation, raised inside best-effort telemetry
    monkeypatch.setattr(skill_usage,'bump_view',interrupted)
    with entered(env) as cap:
        if bridge=='registry':result=dispatch('skill_view',name='procedure')
        else:result=json.loads(model_tools.handle_function_call('skill_view',{'name':'procedure'},task_id='revocation-native'))
        assert not result.get('success') and result.get('error')
        assert 'PRIVATE_CONTENT_MUST_NOT_RETURN' not in json.dumps(result)
        assert cap.revoked


def test_best_effort_telemetry_failure_keeps_authorized_native_view(env,monkeypatch):
    complete(env);install_document(home(env),document(body='AUTHORIZED_PRIVATE_CONTENT'))
    def failed(*a,**kw):raise RuntimeError('synthetic telemetry storage failure')
    monkeypatch.setattr(skill_usage,'bump_view',failed)
    with entered(env):
        result=dispatch('skill_view',name='procedure')
        assert result['success'] and 'AUTHORIZED_PRIVATE_CONTENT' in result['content']


def test_agent_autoload_cached_return_refuses_retained_revoked_scope(env):
    env.template['config']['skills'].update({'auto_load':['procedure']})
    save(env,env.cfg)
    complete(env);install_document(home(env),document(body='CACHED_PRIVATE_CONTENT'))
    with entered(env):
        agent=SimpleNamespace(valid_tool_names=['skill_view'],session_id='cached-native')
        assert 'CACHED_PRIVATE_CONTENT' in ''.join(system_prompt._auto_load_parts(agent))
        revoke(env)
        with pytest.raises(scope.ScopeDenied):system_prompt._auto_load_parts(agent)


def test_agent_autoload_cache_does_not_cross_two_actual_onboarded_users(env):
    env.template['config']['skills'].update({'auto_load':['procedure']})
    save(env,env.cfg)
    for uid in ('1','2'):
        complete(env,uid);install_document(home(env,uid),document(body='ONLY_USER_'+uid))
    agent=SimpleNamespace(valid_tool_names=['skill_view'],session_id='shared-object-control')
    with entered(env,'1'):
        first=''.join(system_prompt._auto_load_parts(agent))
        assert 'ONLY_USER_1' in first and 'ONLY_USER_2' not in first
    with entered(env,'2'):
        second=''.join(system_prompt._auto_load_parts(agent))
        assert 'ONLY_USER_2' in second and 'ONLY_USER_1' not in second


def test_unmanaged_native_config_expansion_remains_available(env,monkeypatch):
    # A fresh unscoped donor process retains the native administrator behavior.
    monkeypatch.setenv('FRIDAY_REPAIR_ONLY_SENTINEL',SENTINEL)
    assert scope.current() is None
    assert skill_utils._expand_skill_config_path(EXPR)==SENTINEL
