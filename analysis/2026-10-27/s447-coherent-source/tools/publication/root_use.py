# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.
"""Callable source recipe in the existing authenticated native Dashboard graph.

No server, route, login, Session, clock or grant is created here. Root passes the
real currently verified Session from the normal Dashboard authentication path.
"""
import contextlib
import importlib
import json
from pathlib import Path
import signal
import sys

PUBLISHER = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/publication/publish_fourlink.py', 'sha256': 'PRIVATE_REF_4334f06dc46ee764'}


@contextlib.contextmanager
def cancellation():
    handlers = {n:signal.getsignal(n) for n in (signal.SIGTERM,signal.SIGINT)}
    def stop(signum, frame):
        raise InterruptedError('Root_publication_cancelled')
    try:
        for n in handlers:signal.signal(n,stop)
        yield
    finally:
        for n,handler in handlers.items():signal.signal(n,handler)


def invoke_current(*, dashboard_api, session, arguments, operation, inputs):
    """Root's actual native context supplies only current identity and inputs.

    operation='bind': inputs={source,postboot_proof_ref,output_directory,
                             clock_ref,parent_clock_ref}
    operation='apply': inputs={request_ref}
    arguments excludes Session (supplied as the actual session parameter).
    """
    from hermes_cli.dashboard_auth.base import Session
    from hermes_constants import get_process_hermes_home
    home = Path('<INSTALL_HOME>')
    if (get_process_hermes_home()!=home or type(session) is not Session
            or sys.modules.get('hermes_dashboard_plugin_friday_rework') is not dashboard_api
            or Path(dashboard_api.__file__).resolve()!=home/'plugins/friday_rework/dashboard/api.py'):
        raise PermissionError('existing_authenticated_native_Dashboard_required')
    om = importlib.import_module('_friday_dashboard_projection.onboarding')
    admin_module = importlib.import_module('_friday_dashboard_projection.admin')
    if type(dashboard_api._admin) is not admin_module.Administration:
        raise PermissionError('existing_native_Administration_required')
    onboarding = om.Onboarding(dashboard_api._admin, storage_readonly=True)
    args = dict(arguments, session=session)
    onboarding._verify_operator(args['profile'],session)
    # Bootstrap only this pinned maintenance source. It imports no second
    # plugin namespace and obtains the existing graph from Onboarding itself.
    raw = Path(PUBLISHER['path']).read_bytes()
    import hashlib
    if hashlib.sha256(raw).hexdigest()!=PUBLISHER['sha256']:
        raise ValueError('frozen_publisher_changed')
    ns={'__file__':PUBLISHER['path'],'__name__':'_S443_Root_fourlink_publication'}
    exec(compile(raw,PUBLISHER['path'],'exec'),ns)
    ns['read_ref'](PUBLISHER)
    with cancellation():
        if operation=='bind':
            return ns['bind_candidates'](onboarding,arguments=args,**inputs)
        if operation=='apply':
            return ns['apply'](onboarding,arguments=args,**inputs)
        raise ValueError('finite_bind_or_apply_operation_required')
