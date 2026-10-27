# UNBOUND ANALYSIS EXCERPTS. Incomplete dependencies; never use as an installed module.
# Source/export correspondence is structural only after declared substitutions.
def _postboot_a0_config(c,value):
    """Admit prepublication CAS or the exact later A0-only runtime projection."""
    import yaml
    home=Path(c['runtime_home']); reference=value['config']
    _postboot_a0_need(reference['path']==str(home/'config.yaml'),'postboot_a0_config_path_changed')
    archive={'path':str(_postboot_a0_folder(c,value)/'config.before.yaml'),'sha256':reference['sha256']}
    before_raw=_r481_read(archive)
    current_ref=pin(home/'config.yaml')
    if current_ref==reference: return
    before=yaml.safe_load(before_raw); current=yaml.safe_load(_r481_read(current_ref))
    expected=copy.deepcopy(before)
    old=expected['plugins']['entries']['friday_rework']['settings']['runtime']
    rows=configured_runtimes(old)
    _postboot_a0_need('dsh' in rows and 'a0' in rows and old.get('enabled') is True
        and 'workers' in old,'postboot_a0_fourlink_prior_runtime_changed')
    # Preserve the whole original document and DSH subtree byte-semantically.
    old['workers']['a0']=copy.deepcopy(c)
    _postboot_a0_need(_postboot_dsh_same(current,expected),'postboot_a0_fourlink_runtime_projection_changed')

def _postboot_a0_inputs(c, value, *, binding=None, generation=None):
    """Current mutable owner/CAS plus exact native successor, no clock renewal."""
    from hermes_cli import friday_user_scope as scope
    home = Path(c['runtime_home'])
    _postboot_a0_need('a0' in c and c['runtime_home']==str(_r481_HOME)
        and c['runtime_profile']=='UNBOUND_PROFILE', 'postboot_a0_exact_home_required')
    qualified=_s446_source_compat()['qualified_runtime600'](c,value)
    keys = {'schema','home','profile','generation','binding','preparations','native_successor',
        'runtime_sha256','sources','original_attempt','config','credentials','plan',
        'bootstrap_original','custody','observation','observed','effects','per_job_authority'}
    _postboot_a0_need(type(value) is dict and set(value) in (keys,keys|{'closed_predecessor'}) and value['schema']==_POSTBOOT_A0_SCHEMA
        and value['home']==str(home) and value['profile']==c['runtime_profile']
        and type(value['generation']) is int and value['generation']>=1
        and (generation is None or value['generation']==generation)
        and (binding is None or value['binding']==binding)
        and value['binding']['runtime_profile']==c['runtime_profile']
        and value['runtime_sha256']==digest({k:v for k,v in qualified.items() if k!='runtime_receipt'})
        and value['effects']=='OBSERVATION_ONLY' and value['per_job_authority']=='NOT_GRANTED',
        'postboot_a0_identity_changed')
    scope._private(home,directory=True)
    setup = _postboot_dsh_document(pin(home/scope.ONBOARDING))
    _postboot_a0_need(setup['binding_sha256']==scope._fingerprint(value['binding']),
                      'postboot_a0_current_binding_changed')
    _postboot_a0_need((value['sources']==_postboot_a0_sources() or _s446_source_compat()['retained_a0_observation'](c,value,_postboot_a0_sources())), 'postboot_a0_sources_changed')
    successor = value['native_successor']
    _postboot_a0_need(type(successor) is dict and set(successor)=={'request','receipt'},
                      'postboot_a0_exact_native_receipt_required')
    _postboot_a0_native480(c,successor['request'],successor['receipt'])
    for kind,ref in value['preparations'].items():
        _postboot_a0_need(kind in ('a0','dsh'),'postboot_a0_preparations_changed')
        v,before = preparation(home,c['runtime_profile'],kind,ref)
        _postboot_a0_need(v['generation']==value['generation']
            and v['principal_binding_sha256']==setup['binding_sha256'], 'postboot_a0_preparation_owner_changed')
        if kind=='a0':
            expected = _postboot_a0_runtime480(before,successor['request'],successor['receipt'])
            _postboot_a0_need({k:v for k,v in qualified.items() if k!='runtime_receipt'}==
                {k:v for k,v in expected.items() if k!='runtime_receipt'}, 'postboot_a0_preparation_changed')
    _postboot_a0_need(set(value['preparations'])=={'a0','dsh'}, 'postboot_a0_preparations_changed')
    _postboot_a0_config(c,value)
    _postboot_a0_need(value['credentials']==credentials(home), 'postboot_a0_owner_inputs_changed')
    claim = _r481_claim_checked(value['original_attempt'])
    _postboot_a0_need(claim['budget_seconds']==600==qualified['budget_seconds']
        and claim['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'postboot_a0_genuine_current_boot_required')
    _postboot_a0_folder(c,value)
    a0_deployment_contract(c)
    return home,claim

