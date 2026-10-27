# UNBOUND ANALYSIS EXCERPTS. Incomplete dependencies; never install or execute.
# Only declared string substitutions; no runtime equivalence claim.
HOST_INHERITED = 'plugins/friday_rework/host_record.py'

def _prior_compat():
    proof,tx=source_proof();projected,prior_tx,accepted=_source3_projection(proof,tx)
    producer=module(PRIOR_PRODUCER,'_route480_historical_source3_producer');adapter=producer['_verified_adapter'](PRIOR_PACKAGE);original_read=adapter['read']
    def retained_read(path):return projected[str(path)]if str(path)in projected else original_read(path)
    adapter['read']=retained_read
    prior_proof=adapter['verify_successor'](PRIOR_PACKAGE,pin(PRIOR_FAMILY/'bound/REQUEST.json'),accepted['committed'])
    need(all(prior_proof[a]==accepted[b]for a,b in(('current_input','current_input'),('current_marker','marker'),('commit','committed'),('plan','plan'),('source_receipt','source_receipt'))),'route480_source3_acceptance_join')
    prior=module(PRIOR_COMPAT,'_route480_historical_source3_compat');original_raw=prior['raw']
    def retained_raw(path):return projected[str(path)][0]if str(path)in projected else original_raw(path)
    prior['raw']=retained_raw;prior['source_proof']=lambda:(prior_proof,prior_tx)
    _inherit_historical_host(prior,PRIOR_COMPAT,projected[str(H/'plugins/friday_rework/host_record.py')],proof)
    return prior,proof,tx

def _inherit_historical_host(namespace,reference,inherited,proof):
    need(type(reference)is dict and set(reference)=={'path','sha256'}
         and reference['path']in HOST_HISTORY_MODULES
         and reference==HOST_HISTORY_MODULES[reference['path']]['module'],'route480_exact_historical_module')
    read(reference)
    package=document(proof['package'])
    need(proof['package']==pin(FAMILY/'PACKAGE.json') and package['native_after']=={},'route480_exact_current_source_package')
    row=package['baseline'][HOST_INHERITED];data,info=inherited
    need(type(data)is bytes and sha(data)==row['sha256']==HOST_INHERITED_SHA
         and row['bytes']==len(data) and row['mode']==0o600
         and [getattr(info,k)for k in('st_dev','st_ino','st_uid','st_nlink','st_mode')]==row['identity']
         and info.st_gid==os.getgid() and info.st_uid==os.getuid() and info.st_nlink==1,'route480_authenticated_inherited_host')
    selected=HOST_HISTORY_MODULES[reference['path']]
    host_path=str(H/HOST_INHERITED)
    if selected['kind']=='producer':
        original=namespace['_verified_adapter'];expected=selected['package']
        def verified_adapter(package_ref):
            need(package_ref==expected,'route480_exact_historical_adapter_package')
            old=document(package_ref);current=document(old['current_input'])
            need(current['project_files'][HOST_INHERITED]==HOST_INHERITED_SHA,'route480_historical_input_host_changed')
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
            if type(ref)is dict and ref.get('path')in HOST_HISTORY_MODULES:
                need(ref==HOST_HISTORY_MODULES[ref['path']]['module'],'route480_historical_module_hash_changed')
                result=original_module(ref,name)
                _inherit_historical_host(result,ref,inherited,proof)
                return result
            return original_module(ref,name)
        namespace['raw']=inherited_raw
        namespace['module']=inherited_module
