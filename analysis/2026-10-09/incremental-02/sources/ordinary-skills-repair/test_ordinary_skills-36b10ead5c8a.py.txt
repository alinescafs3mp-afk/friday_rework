"""Native skill dispatch/projections under real two-user onboarding; offline only."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import pytest
from test_user_onboarding import env, complete, admitted, home
from hermes_cli import friday_user_scope as scope
from hermes_cli import friday_skill_io as io
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from tools import skills_tool as skills, skill_manager_tool as manager
from agent import prompt_builder, skill_commands, skill_preprocessing
from tools.registry import registry


@contextmanager
def entered(env, uid='1'):
    ok, source = admitted(env, uid)
    assert ok
    token = set_hermes_home_override(str(home(env, uid)))
    try:
        with scope.scoped_source(source) as cap:
            yield cap
    finally:
        reset_hermes_home_override(token)


def dispatch(tool, **args):
    result = registry.dispatch(tool, args, task_id='same-task')
    return json.loads(result) if isinstance(result, str) else result


def document(name='procedure', description='Own verified procedure', body='Use authoritative sources.'):
    return f'---\nname: {name}\ndescription: {description}\n---\n{body}\n'


def make(env, uid='1', name='procedure', **kwargs):
    complete(env, uid)
    with entered(env, uid):
        result = dispatch('skill_manage', action='create', name=name, content=document(name, **kwargs))
        assert result.get('success'), result


def test_native_dispatch_remembers_and_reuses_own_procedure(env):
    make(env)
    with entered(env):
        for sub in ('references','templates','assets','scripts'):
            result = dispatch('skill_manage', action='write_file', name='procedure', file_path=sub+'/guide.md', file_content='Own source and outcome')
            assert result.get('success'), result
        assert dispatch('skills_list')['skills'][0]['name']=='procedure'
        loaded=dispatch('skill_view',name='procedure')
        assert loaded['success'] and 'authoritative sources' in loaded['content']
        assert set(loaded['linked_files'])=={'references','templates','assets','scripts'}
        assert dispatch('skill_view',name='procedure',file_path='references/guide.md')['content']=='Own source and outcome'
        assert 'Own verified procedure' in prompt_builder.build_skills_system_prompt()
        assert '/procedure' in skill_commands.get_skill_commands()
        assert dispatch('skill_manage', action='patch',name='procedure',old_string='Own verified procedure',new_string='Revised own procedure')['success']
        assert 'Revised own procedure' in prompt_builder.build_skills_system_prompt()
        text,names,missing=skill_commands.build_preloaded_skills_prompt(['procedure'])
        assert names==['procedure'] and not missing and 'authoritative sources' in text
    with entered(env):
        assert 'Revised own procedure' in dispatch('skill_view',name='procedure')['description']


def test_two_same_named_skills_do_not_merge_histories_names_or_content(env):
    make(env,'1',description='USER_A_ONLY')
    make(env,'2',description='USER_B_ONLY')
    for uid,own,other in [('1','USER_A_ONLY','USER_B_ONLY'),('2','USER_B_ONLY','USER_A_ONLY')]:
        with entered(env,uid):
            result=json.dumps(dispatch('skill_view',name='procedure'))
            assert own in result and other not in result
            index=prompt_builder.build_skills_system_prompt()
            assert own in index and other not in index
            missing=dispatch('skill_manage',action='edit',name='absent',content=document())
            assert not missing['success'] and 'user-'+('2' if uid=='1' else '1') not in json.dumps(missing)


@pytest.mark.parametrize('kind',['symlink_file','symlink_dir','hardlink','fifo','oversize'])
def test_unsafe_document_objects_fail_closed_without_content(env,kind):
    make(env)
    p=home(env)/'skills/procedure/SKILL.md'
    target=env.home/'FOREIGN';target.write_text('FOREIGN_SECRET_SENTINEL');target.chmod(0o600)
    if kind=='symlink_dir':
        d=p.parent;d.rename(d.with_name('saved'));d.symlink_to(env.home,target_is_directory=True)
    else:
        p.unlink()
        if kind=='symlink_file':p.symlink_to(target)
        elif kind=='hardlink':os.link(target,p)
        elif kind=='fifo':os.mkfifo(p,0o600)
        elif kind=='oversize':p.write_bytes(b'x'*(io.MAX_FILE+1));p.chmod(0o600)
    with entered(env):
        result=dispatch('skill_view',name='procedure')
        assert not result.get('success') and 'FOREIGN_SECRET_SENTINEL' not in json.dumps(result)
    assert target.read_text()=='FOREIGN_SECRET_SENTINEL'


def test_same_mtime_size_replacement_reaches_actual_new_content(env):
    make(env,body='Original verified facts')
    with entered(env):
        first=dispatch('skill_view',name='procedure');assert 'Original' in first['content']
        p=home(env)/'skills/procedure/SKILL.md';st=p.stat();p.write_text(p.read_text().replace('Original','Modified'));os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
        second=dispatch('skill_view',name='procedure')
        assert 'Modified' in second['content'] and not second.get('dedup')


def test_readiness_and_preload_have_no_implicit_execution_or_secret_registration(env,monkeypatch):
    make(env,body='!`touch NEVER_RUN`\n${HERMES_SKILL_DIR}/scripts/x.py')
    calls=[]
    import pm
    monkeypatch.setattr(pm,'ensure',lambda *a,**k:calls.append('pm'))
    monkeypatch.setattr(skills,'_capture_required_environment_variables',lambda *a,**k:calls.append('capture'))
    from tools import env_passthrough, credential_files
    monkeypatch.setattr(env_passthrough,'register_env_passthrough',lambda *a,**k:calls.append('env'))
    monkeypatch.setattr(credential_files,'register_credential_files',lambda *a,**k:calls.append('credential'))
    from hermes_cli import plugins
    monkeypatch.setattr(plugins,'discover_plugins',lambda *a,**k:calls.append('plugins'))
    with entered(env):
        p=home(env)/'skills/procedure/SKILL.md'
        p.write_text(p.read_text().replace('description:', 'deps: [imaginary-package]\nrequired_credential_files: [/foreign/credentials]\ndescription:'))
        loaded=dispatch('skill_view',name='procedure')
        assert loaded['success'] and loaded['setup_needed'] and loaded['readiness_status']=='setup_needed'
        assert '!`touch NEVER_RUN`' in loaded['content']
        assert str(p.parent)+'/scripts/x.py' in loaded['content']
        assert dispatch('skills_list')['success']
        text,_,_=skill_commands.build_preloaded_skills_prompt(['procedure'])
        assert 'Not executed or verified' in text
        assert skill_preprocessing.preprocess_skill_content('!`touch NEVER_RUN`',p.parent,skills_cfg={'inline_shell':True})=='!`touch NEVER_RUN`'
        with pytest.raises(scope.ScopeDenied):skill_preprocessing.run_inline_shell('true',p.parent,1)
    assert calls==[] and not (home(env)/'NEVER_RUN').exists()


def test_direct_foreign_roots_and_home_overrides_refuse(env):
    make(env,'1');complete(env,'2')
    from agent.skill_utils import get_skill_search_roots
    with entered(env):
        with pytest.raises(scope.ScopeDenied):get_skill_search_roots(home(env,'2')/'skills')
        with pytest.raises(scope.ScopeDenied):prompt_builder.build_skills_system_prompt(skills_dir_override=home(env,'2')/'skills')
        with pytest.raises(scope.ScopeDenied):skill_commands.build_auto_load_prompt(home_override=home(env,'2'))
        assert dispatch('skill_view',name='../../user-2/skills/procedure').get('error') == 'product_user_scope_refused'

from test_user_isolation import users


@pytest.mark.parametrize('projection',['view','list','prompt','commands','autoload'])
def test_retained_readers_refuse_after_disable_and_reenable(users,projection):
    root=users.homes[0]/'skills';root.mkdir(mode=0o700)
    skill=root/'procedure';skill.mkdir(mode=0o700)
    p=skill/'SKILL.md';p.write_text(document());p.chmod(0o600)
    operations={
        'view':lambda:skills.skill_view('procedure'),
        'list':skills.skills_list,
        'prompt':prompt_builder.build_skills_system_prompt,
        'commands':skill_commands.get_skill_commands,
        'autoload':lambda:skill_commands.build_auto_load_prompt(user_config={'skills':{'auto_load':['procedure']}}),
    }
    with users.enter(0):
        assert operations[projection]()
        users.access('1',enabled=False)
        users.access('1',enabled=True)
        with pytest.raises(scope.ScopeDenied):operations[projection]()
    assert p.read_text()==document()


def test_read_revocation_before_return_does_not_disclose_document(users,monkeypatch):
    root=users.homes[0]/'skills';root.mkdir(mode=0o700)
    skill=root/'procedure';skill.mkdir(mode=0o700)
    p=skill/'SKILL.md';p.write_text(document());p.chmod(0o600)
    original=io.read_text
    def interrupted(*args,**kwargs):
        result=original(*args,**kwargs)
        users.access('1',enabled=False)
        return result
    with users.enter(0):
        monkeypatch.setattr(io,'read_text',interrupted)
        with pytest.raises(scope.ScopeDenied):skills.skill_view('procedure')
