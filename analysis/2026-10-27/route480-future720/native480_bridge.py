# UNBOUND ANALYSIS EXCERPTS. Incomplete dependencies; never use as an installed module.
# Source/export correspondence is structural only after declared substitutions.
def _module():
    compat=_compat()
    old={'path':str(compat['OLD']/'bridge/maintenance.py'),'sha256':'UNBOUND_RETAINED_VERIFIER_SHA'}
    ns=compat['module'](old,'_analysis_retained_native480')
    ns['source480']=compat['original_source480']
    original_verify=ns['verify480']
    def verify(request_ref,receipt_ref,config=None):
        shadow=compat['qualified_runtime600'](config) if config is not None else None
        result=original_verify(request_ref,receipt_ref,shadow)
        if config is not None and config['budget_seconds']==720: result['runtime']=compat['future_runtime720'](shadow)
        return compat['current_native_source'](result)
    ns['verify480']=verify
    return ns

def verify480(request_ref,receipt_ref,config=None):
    return _module()['verify480'](request_ref,receipt_ref,config)

def current480():return _module()['current480']()

def runtime480(config,request_ref,receipt_ref):
    compat=_compat();shadow=compat['qualified_runtime600'](config)
    current=_module()['runtime480'](shadow,request_ref,receipt_ref)
    return compat['future_runtime720'](current) if config['budget_seconds']==720 else current

