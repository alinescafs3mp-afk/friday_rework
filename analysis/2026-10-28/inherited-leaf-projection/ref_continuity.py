# UNBOUND ANALYSIS EXCERPTS. Incomplete dependencies; never install or execute.
# Only declared string substitutions; no runtime equivalence claim.
_S436_NATIVE_VERIFIER = {'path': 'UNBOUND_VERIFY_NATIVE_PATH', 'sha256': 'UNBOUND_REFERENCE_SHA_1'}

_S443_NATIVE480_VERIFIER = {'path': 'UNBOUND_VERIFY480_PATH', 'sha256': 'UNBOUND_REFERENCE_SHA_2'}

def _s446_source_compat():
    reference = {'path': 'UNBOUND_COMPAT_PATH', 'sha256': 'UNBOUND_REFERENCE_SHA_3'}
    raw = _r481_read(reference)
    namespace = {'__file__':reference['path'],'__name__':'_s446_installed_source_compat'}
    exec(compile(raw,reference['path'],'exec'),namespace)
    return namespace

# Only the verifier-reference assignment is selected; dispatch and guards are omitted.
def selected_worker_verifier_reference():
    verifier = {'path': 'UNBOUND_VERIFY480_PATH', 'sha256': 'UNBOUND_REFERENCE_SHA_2'}
