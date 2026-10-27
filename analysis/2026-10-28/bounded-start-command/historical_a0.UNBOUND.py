"""Incomplete Source6 analysis excerpts; never import/install/run as a consumer.

Two complete original functions; selected constants have explicit UNBOUND values.
Other globals/readers/proof producers are deliberately omitted. No permission to
replace historical bytes, bypass current validation, or replay a consumed effect.
"""

A0_INHERITED = 'UNBOUND_INHERITED_A0_LEAF'

A0_INHERITED_SHA = 'UNBOUND_INHERITED_A0_SOURCE_SHA256'

A0_HISTORY_MODULES = 'UNBOUND_FIXED_10_MODULE_EDGES_AND_5_PACKAGES'

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
        need(row['sha256']==expected,'source6_prior_beforeimage_hash')
        if name in published_names:
            publication=document(pin(prior_tx/('published-'+str(published_names.index(name))+'.json')))
            need(publication=={name:{'sha256':sha(data),'bytes':len(data),'mode':row['mode'],'identity':ident}},'source6_prior_publication_identity')
        else:
            need(name==A0_INHERITED and read(PRIOR_PLUGINS[name])==data,'source6_exact_inherited_a0_beforeimage')
        projected[str(H/name)]=(data,SimpleNamespace(st_dev=dev,st_ino=ino,st_uid=uid,st_gid=os.getgid(),st_nlink=nlink,st_mode=mode,st_size=len(data)))
    return projected,prior_tx,accepted

def _inherit_historical_a0(namespace,reference,inherited,proof):
    need(type(reference)is dict and set(reference)=={'path','sha256'}
         and reference['path']in A0_HISTORY_MODULES
         and reference==A0_HISTORY_MODULES[reference['path']]['module'],'route480_exact_historical_module')
    read(reference)
    package=document(proof['package'])
    need(proof['package']==pin(FAMILY/'PACKAGE.json') and package['native_after']=={},'route480_exact_current_source_package')
    row=package['baseline'][A0_INHERITED];data,info=inherited
    need(type(data)is bytes and sha(data)==row['sha256']==A0_INHERITED_SHA
         and row['bytes']==len(data) and row['mode']==0o600
         and [getattr(info,k)for k in('st_dev','st_ino','st_uid','st_nlink','st_mode')]==row['identity']
         and info.st_gid==os.getgid() and info.st_uid==os.getuid() and info.st_nlink==1,'route480_authenticated_inherited_host')
    selected=A0_HISTORY_MODULES[reference['path']]
    host_path=str(H/A0_INHERITED)
    if selected['kind']=='producer':
        original=namespace['_verified_adapter'];expected=selected['package']
        def verified_adapter(package_ref):
            need(package_ref==expected,'route480_exact_historical_adapter_package')
            old=document(package_ref);current=document(old['current_input'])
            need(current['project_files'][A0_INHERITED]==A0_INHERITED_SHA,'route480_historical_input_host_changed')
            adapter=original(package_ref);original_read=adapter['read']
            def inherited_read(path):
                return inherited if str(path)==host_path else original_read(path)
            adapter['read']=inherited_read
            return adapter
        namespace['_verified_adapter']=verified_adapter
    else:
        original_raw=namespace['raw'];original_module=namespace['module']
        def inherited_raw(path):
            return data if str(path)==host_path else original_raw(path)
        def inherited_module(ref,name):
            if type(ref)is dict and ref.get('path')in A0_HISTORY_MODULES:
                need(ref==A0_HISTORY_MODULES[ref['path']]['module'],'route480_historical_module_hash_changed')
                result=original_module(ref,name)
                _inherit_historical_a0(result,ref,inherited,proof)
                return result
            return original_module(ref,name)
        namespace['raw']=inherited_raw
        namespace['module']=inherited_module
