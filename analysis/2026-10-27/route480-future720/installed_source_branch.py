# UNBOUND ANALYSIS EXCERPTS. Incomplete dependencies; never use as an installed module.
# Source/export correspondence is structural only after declared substitutions.
# Selected statements only; surrounding validator/dispatch is omitted.
def selected_current480_branch(row, route, native, runtime, _current_main=None):
    if runtime.get('a0',{}).get('runtime',{}).get('sha256') == 'UNBOUND_NATIVE_RUNTIME_SHA':
        if _current_main is not None and (_current_main.get('home') != runtime.get('runtime_home')
                or _current_main.get('profile') != runtime.get('runtime_profile')):
            raise HostUnavailable('foreign_current480_source_target')
        from .runtime_primitives import owned_file, canonical
        verifier = {'path': 'UNBOUND_CURRENT_VERIFIER_PATH', 'sha256': 'UNBOUND_CURRENT_VERIFIER_SHA'}
        path = canonical(verifier['path'])
        raw = owned_file(path,private=True)
        if hashlib.sha256(raw).hexdigest() != verifier['sha256']:
            raise HostUnavailable('current480_verifier_source_changed')
        namespace={'__file__':str(path),'__name__':'_analysis_current480_source'}
        exec(compile(raw,str(path),'exec'),namespace)
        current=namespace['current480']()
        proof=namespace['verify480'](current['request'],current['receipt'],config=runtime)
        # This independent source proof grants no old SourceMaintenance reattach.
        return {'schema':'friday.worker-current480-source.v1','native480':current,
                'proof':proof,'reattachment_authority':False}
