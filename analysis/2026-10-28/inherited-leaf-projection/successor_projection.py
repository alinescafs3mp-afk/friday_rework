# UNBOUND ANALYSIS EXCERPTS. Incomplete dependencies; never install or execute.
# Only declared string substitutions; no runtime equivalence claim.
CHANGED = ('plugins/friday_rework/user_worker_join.py', 'plugins/friday_rework/worker_provision.py')

METADATA=('hermes-agent.source.json','hermes-agent/install-stamp.json','FRIDAY-INSTALL.json')

PROJECTED=(*CHANGED,*METADATA)

def source_proof():
    producer=module(PRODUCER,'_source5_existing_source92_verifier');package_ref=pin(FAMILY/'PACKAGE.json');package=document(package_ref)
    request_ref=pin(FAMILY/'bound/REQUEST.json');tx=H/'preparation'/('ordinary-source-update-'+PRIOR_INPUT['sha256'])
    proof=producer['verify_successor'](package_ref,request_ref,pin(tx/'committed.json'))
    need(proof['previous_input']==PRIOR_INPUT and proof['package']==package_ref and proof['request']==request_ref
         and set(package['plugin_after'])==set(CHANGED) and package['native_after']=={},'source5_exact_two_pin_source4_successor')
    return proof,tx

def _source4_projection(proof,tx):
    package=document(proof['package']);plan=document(proof['plan']);accepted=document(PRIOR_ACCEPTANCE);old=document(PRIOR_PACKAGE)
    need(accepted['accepted']is True and accepted['accepted_source_only']is True and accepted['fresh_process']is True
         and accepted['current_input']==old['current_input']==PRIOR_INPUT,'source5_exact_accepted_source4')
    need(set(package['baseline'])==set(PROJECTED) and plan['before']==package['baseline'],'source5_exact_five_beforeimages')
    prior_tx=H/'preparation'/('ordinary-source-update-'+old['previous_input']['sha256'])
    need(accepted['committed']['path']==str(prior_tx/'committed.json'),'source5_actual_source4_journal')
    published_names=[*sorted(old['plugin_after']),*METADATA];previous=document(PRIOR_INPUT);projected={}
    for name in PROJECTED:
        row=package['baseline'][name];data=raw(tx/'before'/name);ident=row['identity']
        need(type(ident)is list and len(ident)==5 and all(type(n)is int for n in ident),'source5_before_identity')
        dev,ino,uid,nlink,mode=ident
        need(uid==os.getuid() and nlink==1 and stat.S_ISREG(mode) and stat.S_IMODE(mode)==row['mode']==0o600
             and row['bytes']==len(data) and row['sha256']==sha(data),'source5_before_custody')
        expected=previous['project_files'][name]if name in CHANGED else accepted['marker'if name=='FRIDAY-INSTALL.json'else'source_receipt']['sha256']if name!='hermes-agent/install-stamp.json'else old['retained_stamp']['sha256']
        publication=document(pin(prior_tx/('published-'+str(published_names.index(name))+'.json')))
        need(row['sha256']==expected and publication=={name:{'sha256':sha(data),'bytes':len(data),'mode':row['mode'],'identity':ident}},'source5_source4_publication_identity')
        projected[str(H/name)]=(data,SimpleNamespace(st_dev=dev,st_ino=ino,st_uid=uid,st_gid=os.getgid(),st_nlink=nlink,st_mode=mode,st_size=len(data)))
    return projected,prior_tx,accepted

def _prior_compat():
    proof,tx=source_proof();projected,prior_tx,accepted=_source4_projection(proof,tx)
    producer=module(PRIOR_PRODUCER,'_source5_retained_source4_producer');adapter=producer['_verified_adapter'](PRIOR_PACKAGE);original_read=adapter['read']
    def retained_read(path):return projected[str(path)]if str(path)in projected else original_read(path)
    adapter['read']=retained_read
    oldproof=adapter['verify_successor'](PRIOR_PACKAGE,pin(PRIOR_FAMILY/'bound/REQUEST.json'),accepted['committed'])
    need(all(oldproof[a]==accepted[b]for a,b in(('current_input','current_input'),('current_marker','marker'),('commit','committed'),('plan','plan'),('source_receipt','source_receipt'))),'source5_source4_acceptance_join')
    prior=module(PRIOR_COMPAT,'_source5_reviewed_retained_source4_compat');original_raw=prior['raw']
    def retained_raw(path):return projected[str(path)][0]if str(path)in projected else original_raw(path)
    def retained_sources():
        expected=copy.deepcopy(source_pins_for_observation())
        for name,reference in PRIOR_PLUGINS.items():
            need(sha(raw(tx/'before'/name))==reference['sha256'],'source5_observation_beforeimage')
            expected[name]={'path':str(H/name),'sha256':reference['sha256']}
        return expected
    prior['raw']=retained_raw;prior['source_proof']=lambda:(oldproof,prior_tx);prior['source_pins_for_observation']=retained_sources
    return prior,proof,tx
