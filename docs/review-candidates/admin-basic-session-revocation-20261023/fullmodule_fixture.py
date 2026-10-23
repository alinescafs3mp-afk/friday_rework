#!/usr/bin/env python3
"""Real native modules, synthetic credentials only. Parent is sole executor.

The fixture never substitutes project modules or providers. Its only source overlay
is exact candidate files over genuine117-pinned dependency files, imported normally.
Full HTTP gate/browser/service installation is intentionally outside this observation.
"""
from __future__ import annotations
import argparse
import asyncio
import base64
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import secrets
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback

HERE = Path(__file__).resolve().parent
REQUIRED = (
    'plugins/dashboard_auth/basic/__init__.py',
    'plugins/dashboard_auth/basic/_sessions.py',
    'hermes_cli/dashboard_auth/routes.py',
    'hermes_cli/dashboard_auth/refresh_singleflight.py',
)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_private(path, value):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())

def load_modules(source, synthetic_home):
    os.environ['HERMES_HOME'] = str(synthetic_home)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source))
    import plugins.dashboard_auth.basic as basic
    import hermes_cli.dashboard_auth as registry
    import hermes_cli.dashboard_auth.routes as routes
    import hermes_cli.dashboard_auth.middleware as middleware
    import hermes_cli.dashboard_auth.refresh_singleflight as singleflight
    from fastapi import FastAPI, HTTPException
    from starlette.requests import Request
    from hermes_cli.dashboard_auth.base import ProviderError, RefreshExpiredError
    # Every imported first-party module must be the real staged byte-identical file.
    origins = {}
    for name, module in list(sys.modules.items()):
        if name == 'hermes_constants' or name == 'hermes_cli' or name.startswith('hermes_cli.') or name == 'plugins' or name.startswith('plugins.'):
            location = getattr(module, '__file__', None)
            if location:
                resolved = Path(location).resolve()
                assert resolved.is_relative_to(source), (name, str(resolved))
                origins[name] = {'relative': str(resolved.relative_to(source)), 'sha256': sha(resolved)}
    return basic, registry, routes, middleware, singleflight, FastAPI, HTTPException, Request, ProviderError, RefreshExpiredError, origins

def child_main(args):
    payload = json.loads(Path(args.child).read_text())
    source = Path(payload['source'])
    home = Path(payload['home'])
    basic, registry, routes, middleware, singleflight, FastAPI, HTTPException, Request, ProviderError, RefreshExpiredError, origins = load_modules(source, home)
    factory = lambda: basic.BasicAuthProvider(username=payload['username'], password_hash=payload['password_hash'], secret=bytes.fromhex(payload['secret']), session_store_dir=payload['store'])
    p = factory()
    assert p.verify_session(access_token=payload['revoked_at']) is None
    try:
        p.refresh_session(refresh_token=payload['revoked_rt'])
    except RefreshExpiredError:
        pass
    else:
        raise AssertionError('persisted revoked refresh accepted in new process')
    assert p.verify_session(access_token=payload['allowed_at']) is not None
    assert p.refresh_session(refresh_token=payload['allowed_rt']).access_token
    print(json.dumps({'event': 'ready', 'pid': os.getpid(), 'executable': sys.executable, 'origins': origins}), flush=True)
    # Native pipe boundary, no polling loop and no network.
    assert sys.stdin.readline().strip() == 'REVOKE'
    revoke_started=time.time()
    p.revoke_session(refresh_token=payload['race_rt'])
    print(json.dumps({'event': 'revoked', 'pid': os.getpid(), 'started_unix':revoke_started, 'ended_unix':time.time()}), flush=True)
    return 0

def fifo_child_main(args):
    """Real Linux FIFOs; parent process enforces the external five-second bound."""
    payload=json.loads(Path(args.fifo_child).read_text())
    source=Path(payload['source']);home=Path(payload['home'])
    basic, registry, routes, middleware, singleflight, FastAPI, HTTPException, Request, ProviderError, RefreshExpiredError, origins=load_modules(source,home)
    private=home/'fifo-negative-controls';private.mkdir(mode=0o700)
    observations=[]
    try:
        for label in ['state.json','anchor']:
            target=private/label.replace('.','-')
            def factory():
                return basic.BasicAuthProvider(username=payload['username'],password_hash=payload['password_hash'],secret=bytes.fromhex(payload['secret']),session_store_dir=target)
            q=factory()
            own=q.complete_password_login(username=payload['username'],password=payload['password'])
            path=target/'state.json' if label=='state.json' else Path(str(target)+'.anchor')
            path.unlink();os.mkfifo(path,0o600)
            assert stat.S_ISFIFO(path.lstat().st_mode)
            for operation in ['existing-provider-verify','fresh-provider-constructor']:
                began=time.monotonic()
                try:
                    if operation=='existing-provider-verify':q.verify_session(access_token=own.access_token)
                    else:factory()
                except ProviderError:
                    elapsed=time.monotonic()-began
                    assert elapsed < 1.0,'FIFO rejection exceeded one second'
                    observations.append({'fifo':label,'operation':operation,'outcome':'ProviderError','elapsed_seconds':round(elapsed,6)})
                else:raise AssertionError('non-regular FIFO accepted: '+label+' '+operation)
                assert stat.S_ISFIFO(path.lstat().st_mode),'FIFO silently replaced/reset'
        print(json.dumps({'event':'fifo-controls-complete','pid':os.getpid(),'executable':sys.executable,'observations':observations,'origins':origins}),flush=True)
        return 0
    finally:
        shutil.rmtree(private)

def main(args):
    started = time.time()
    result = {'schema': 'frw.s207.real-fullmodule-fixture.v1', 'pid': os.getpid(), 'argv': sys.argv,
              'executable': sys.executable, 'started_unix': started, 'cases': [], 'children': [],
              'not_run': ['installed runtime', 'live owner credentials', 'full HTTP gated middleware', 'browser/service/model/network', 'root-owned custody negative control'],
              'synthetic_state_removed': False}
    root = Path(tempfile.mkdtemp(prefix='private-run-', dir=HERE))
    root.chmod(0o700)
    child = None
    def case(name, function):
        begin = time.monotonic()
        try:
            detail = function()
            result['cases'].append({'name': name, 'status': 'PASS', 'elapsed_seconds': round(time.monotonic()-begin, 4), 'detail': detail})
        except Exception as exc:
            result['cases'].append({'name': name, 'status': 'FAIL', 'elapsed_seconds': round(time.monotonic()-begin, 4), 'exception': type(exc).__name__, 'message': str(exc)[:400], 'traceback': traceback.format_exc()[-3000:]})
    try:
        source = root/'source'
        shutil.copytree(HERE/'native', source)
        candidate = Path(args.candidate).resolve()
        overlay = list(REQUIRED)
        # A supplied candidate middleware is real code, otherwise unchanged beforeimage.
        for rel in overlay:
            p = candidate/rel
            assert p.is_file(), 'missing candidate ' + rel
            dst = source/rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dst)
        middleware_candidate = candidate/'hermes_cli/dashboard_auth/middleware.py'
        shutil.copyfile(middleware_candidate if middleware_candidate.is_file() else HERE.parent/'before/hermes_cli/dashboard_auth/middleware.py', source/'hermes_cli/dashboard_auth/middleware.py')
        pins = json.loads((HERE/'DEPENDENCY-PINS.json').read_text())
        for pin in pins['files']:
            if pin['relative'] not in overlay:
                assert sha(source/pin['relative']) == pin['sha256'], 'dependency drift '+pin['relative']
        result['source_hashes'] = {str(p.relative_to(source)): sha(p) for p in sorted(source.rglob('*.py'))}
        home = root/'synthetic-home'
        home.mkdir(mode=0o700)
        basic, registry, routes, middleware, singleflight, FastAPI, HTTPException, Request, ProviderError, RefreshExpiredError, origins = load_modules(source, home)
        result['origins'] = origins
        result['third_party'] = {name: {'version': getattr(importlib.import_module(name), '__version__', None), 'origin': getattr(importlib.import_module(name), '__file__', None)} for name in ['fastapi', 'starlette', 'httpx', 'pydantic']}
        username = 'fixture-user'
        password = secrets.token_urlsafe(24)
        password_hash = basic.hash_password(password)
        secret = secrets.token_bytes(32)
        store = home/'basic-store'
        def provider(path=store):
            return basic.BasicAuthProvider(username=username, password_hash=password_hash, secret=secret, ttl_seconds=60, session_store_dir=path)
        p = provider()
        registry.clear_providers()
        registry.register_provider(p)
        app = FastAPI()
        def request(cookie='', path='/api/private', method='GET'):
            headers = [(b'cookie', cookie.encode())] if cookie else []
            return Request({'type': 'http', 'http_version': '1.1', 'scheme': 'http', 'method': method, 'path': path, 'raw_path': path.encode(), 'query_string': b'', 'root_path': '', 'headers': headers, 'client': ('127.0.0.1', 32109), 'server': ('fixture.invalid',80), 'app': app})
        def login():
            response = asyncio.run(routes.auth_password_login(request(path='/auth/password-login', method='POST'), routes._PasswordLoginBody(provider='basic', username=username, password=password)))
            assert response.status_code == 200
            from http.cookies import SimpleCookie
            jar = SimpleCookie()
            for key, val in response.raw_headers:
                if key.lower()==b'set-cookie': jar.load(val.decode())
            from hermes_cli.dashboard_auth.cookies import read_session_cookies
            cookie = '; '.join(k+'='+v.value for k,v in jar.items())
            at,rt = read_session_cookies(request(cookie))
            assert at and rt
            return at,rt,cookie
        def verify(at):
            return middleware._verify_access_token(request(), access_token=at, provider_hint='basic')
        def native_refresh(rt):
            return asyncio.run(routes.auth_native_refresh(request(path='/auth/native/refresh', method='POST'), routes._NativeRefreshBody(refresh_token=rt, provider='basic')))
        def denied_refresh(rt):
            response = native_refresh(rt)
            assert getattr(response,'status_code',None)==401, 'native refresh accepted revoked token'
        def logout(cookie):
            response = asyncio.run(routes.auth_logout(request(cookie, '/auth/logout', 'POST')))
            assert response.status_code==302, 'logout did not report success'
            return response
        state = {}
        def core():
            a = login(); b = login()
            assert a[:2] != b[:2], 'same-second independent logins share credentials/family'
            assert verify(a[0]) is not None and verify(b[0]) is not None
            refreshed = native_refresh(a[1])
            assert isinstance(refreshed,dict) and refreshed['access_token']
            # A success cache was just primed with retained old RT; logout must dominate it.
            logout(a[2])
            assert verify(a[0]) is None
            assert verify(refreshed['access_token']) is None
            denied_refresh(a[1]); denied_refresh(refreshed['refresh_token'])
            assert verify(b[0]) is not None
            assert isinstance(native_refresh(b[1]),dict)
            # Real module reload drops module caches; durable state still denies.
            reloaded = importlib.reload(basic)
            q = provider()
            assert q.verify_session(access_token=a[0]) is None
            try: q.refresh_session(refresh_token=a[1])
            except RefreshExpiredError: pass
            else: raise AssertionError('reload accepted revoked refresh')
            state.update(revoked=a, allowed=b)
            return {'path':'password-login -> provider scan -> native refresh (primed) -> logout -> verify/refresh; real module reload', 'independent_session':'allowed'}
        case('native_login_verify_refresh_logout_retained_tokens_and_reload', core)
        def access_only_logout():
            a=login()
            at_only='; '.join(piece for piece in a[2].split('; ') if piece.split('=',1)[-1] != a[1])
            from hermes_cli.dashboard_auth.cookies import read_session_cookies
            observed_at,observed_rt=read_session_cookies(request(at_only))
            assert observed_at==a[0] and not observed_rt,'fixture failed to remove refresh cookie'
            logout(at_only)
            assert verify(a[0]) is None
            denied_refresh(a[1])
            return {'ATcookie_only_logout':'family access and retained refresh denied'}
        case('actual_route_access_cookie_only_logout_revokes_new_family',access_only_logout)
        def invalid_credentials():
            for user,pw in [(username,password+'wrong'),('missing-user',password)]:
                try: p.complete_password_login(username=user,password=pw)
                except basic.InvalidCredentialsError: pass
                else: raise AssertionError('invalid password/username accepted')
            return None
        case('real_scrypt_wrong_password_and_unknown_user', invalid_credentials)
        def invalid_tokens():
            a=login()
            for token in ['garbage','',a[0][:-3]+'abc',a[1]]:
                assert verify(token) is None
            for token in ['garbage','',a[1][:-3]+'abc',a[0]]:
                if token:
                    denied_refresh(token)
            at_payload=basic._unsign(a[0],secret,'access');rt_payload=basic._unsign(a[1],secret,'refresh')
            assert at_payload and rt_payload
            at_payload['exp']=int(time.time())-1;rt_payload['exp']=int(time.time())-1
            assert verify(basic._sign(at_payload,secret)) is None
            denied_refresh(basic._sign(rt_payload,secret))
            # Cryptographically valid malformed containers must not crash token verification.
            for payload in [{}, {'kind':'access','exp':'bad'}, {'kind':'access','exp':int(time.time())+500,'sub':[]}, {'kind':'access','exp':int(time.time())+500,'sub':username,'sid':[]}]:
                token=basic._sign(payload,secret)
                try: outcome=verify(token)
                except ProviderError: continue
                assert outcome is None, 'malformed signed token accepted'
        case('tamper_expiry_kind_and_signed_malformed_claims', invalid_tokens)
        def foreign_revoke():
            a=login()
            def snapshot(path):
                if not path.exists():return None
                return {str(x.relative_to(path)):(sha(x),x.stat().st_ino,x.stat().st_mtime_ns) for x in path.iterdir() if x.is_file()}
            before=snapshot(store)
            p.revoke_session(refresh_token='foreign-opaque-not-basic')
            wrong_secret=basic._sign({'sub':username,'kind':'refresh','exp':int(time.time())+500},secrets.token_bytes(32))
            p.revoke_session(refresh_token=wrong_secret)
            wrong_subject=basic._sign({'sub':'another-principal','kind':'refresh','exp':int(time.time())+500},secret)
            p.revoke_session(refresh_token=wrong_subject)
            assert snapshot(store)==before,'foreign revoke touched ledger/lock'
            assert verify(a[0]) is not None
            return {'foreign_opaque_wrong_secret_wrong_subject':'no store writes; own session allowed'}
        case('foreign_credentials_logout_iteration_is_noop_without_store_writes',foreign_revoke)
        def atomic_failure():
            target=home/'atomic-failure-store';q=provider(target)
            own=q.complete_password_login(username=username,password=password)
            ledger=next(x for x in target.iterdir() if x.is_file() and x.read_bytes().lstrip().startswith(b'{'))
            before=ledger.read_bytes();real_replace=os.replace;calls=[]
            def fail_replace(*pos,**kw):
                calls.append(1)
                raise PermissionError('synthetic pre-publication syscall fault')
            os.replace=fail_replace
            try:
                try:q.revoke_session(refresh_token=own.refresh_token)
                except ProviderError:pass
                else:raise AssertionError('durable revoke claimed success after failed publication')
            finally:os.replace=real_replace
            assert calls,'atomic publication did not use os.replace'
            assert ledger.read_bytes()==before,'failed atomic publication damaged prior ledger'
            assert not [x for x in target.iterdir() if (x.name.endswith('.tmp') or x.name.startswith('.state-'))],'fault leaked atomic temp file'
            assert q.verify_session(access_token=own.access_token) is not None
            q.revoke_session(refresh_token=own.refresh_token)
            assert q.verify_session(access_token=own.access_token) is None
            return {'fault':'real os.replace syscall only; actual provider/store unchanged','prior_ledger':'exact bytes preserved','retry':'explicit known-unpublished failure then one successful revoke'}
        case('injected_prepublication_filesystem_failure_atomic_integrity_and_recovery',atomic_failure)
        def legacy():
            exp=int(time.time())+1000
            old_at=basic._sign({'sub':username,'kind':'access','exp':exp},secret)
            old_rt=basic._sign({'sub':username,'kind':'refresh','exp':exp+5000},secret)
            assert verify(old_at) is not None, 'legacy signing compatibility lost'
            from hermes_cli.dashboard_auth.cookies import set_session_cookies
            from fastapi.responses import Response
            resp=Response();set_session_cookies(resp,access_token=old_at,refresh_token=old_rt,access_token_expires_in=1000,use_https=False,provider='basic')
            from http.cookies import SimpleCookie
            jar=SimpleCookie()
            for key,value in resp.raw_headers:
                if key==b'set-cookie':jar.load(value.decode())
            cookie='; '.join(k+'='+v.value for k,v in jar.items())
            logout(cookie)
            assert verify(old_at) is None
            denied_refresh(old_rt)
            return {'legacy_exact_observed_pair':'denied', 'migration_limit':'unobserved earlier sid-less access tokens cannot be mapped to a refresh family; no TTL inference asserted'}
        case('legacy_signing_compatibility_and_exact_logout_pair_revocation',legacy)
        def storage_controls():
            sub=home/'storage-controls';sub.mkdir(mode=0o700)
            observations=[]
            def closed(path,label):
                try:
                    bad=provider(path)
                    minted=bad.complete_password_login(username=username,password=password)
                    accepted=bad.verify_session(access_token=minted.access_token)
                except (ProviderError,ValueError,OSError):
                    observations.append(label);return
                raise AssertionError(label+' store accepted authentication')
            target=sub/'target';good=provider(target);s=good.complete_password_login(username=username,password=password)
            files=[x for x in target.iterdir() if x.is_file()]
            assert files, 'persistent store produced no files'
            json_files=[]
            for path in files:
                assert stat.S_IMODE(path.stat().st_mode)==0o600, 'store/lock file not0600'
                try: json.loads(path.read_text());json_files.append(path)
                except (ValueError,UnicodeError):pass
            assert stat.S_IMODE(target.stat().st_mode)==0o700
            assert len(json_files)==1, 'expected exactly one JSON ledger'
            ledger=json_files[0]; original=ledger.read_bytes()
            ledger.write_bytes(b'{"invalid":"truncated"')
            before=ledger.read_bytes()
            try: outcome=good.verify_session(access_token=s.access_token)
            except ProviderError: outcome=None
            assert outcome is None and ledger.read_bytes()==before,'corruption reset/bypass'
            closed(target,'corrupt ledger')
            assert ledger.read_bytes()==before,'corrupt ledger silently repaired/reset'
            ledger.write_bytes(original)
            envelope=json.loads(original);envelope['state']['sessions']['synthetic-tampered-record']=int(time.time())+1000
            ledger.write_text(json.dumps(envelope));tampered=ledger.read_bytes()
            try:outcome=good.verify_session(access_token=s.access_token)
            except ProviderError:outcome=None
            assert outcome is None and ledger.read_bytes()==tampered,'valid JSON HMAC tamper accepted/reset'
            closed(target,'HMAC tamper');ledger.write_bytes(original)
            ledger.chmod(0o644);closed(target,'unsafe ledger mode');assert stat.S_IMODE(ledger.stat().st_mode)==0o644;ledger.chmod(0o600)
            target.chmod(0o755);closed(target,'unsafe directory mode');assert stat.S_IMODE(target.stat().st_mode)==0o755;target.chmod(0o700)
            alias=sub/'directory-link';alias.symlink_to(target,target_is_directory=True);closed(alias,'symlink directory')
            ledger.unlink();ledger.symlink_to(sub/'outside-ledger');(sub/'outside-ledger').write_bytes(original);(sub/'outside-ledger').chmod(0o600);closed(target,'symlink ledger');assert (sub/'outside-ledger').read_bytes()==original;ledger.unlink();ledger.write_bytes(original);ledger.chmod(0o600)
            link=sub/'hardlink';os.link(ledger,link);closed(target,'hardlinked ledger');assert ledger.stat().st_nlink==2;link.unlink()
            # Store loss may only deny prior store-bound credentials; new store cannot resurrect them.
            ledger.unlink()
            try: outcome=good.verify_session(access_token=s.access_token)
            except ProviderError:outcome=None
            assert outcome is None,'missing ledger resurrected prior credential'
            closed(target,'missing ledger')
            assert not ledger.exists(),'missing ledger silently reset'
            return observations
        case('corruption_permissions_symlink_hardlink_and_missing_ledger_fail_closed',storage_controls)
        def replacement_custody():
            target=home/'replacement-store';q=provider(target)
            own=q.complete_password_login(username=username,password=password)
            lock=target/'lock';old_lock=target/'saved-lock';lock.rename(old_lock)
            fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            try:
                try:outcome=q.verify_session(access_token=own.access_token)
                except ProviderError:outcome=None
                assert outcome is None,'existing provider accepted replacement lock inode'
            finally:lock.unlink();old_lock.rename(lock)
            assert q.verify_session(access_token=own.access_token) is not None
            moved=home/'moved-original-store';target.rename(moved)
            try:
                try:provider(target)
                except ProviderError:pass
                else:raise AssertionError('retained anchor allowed absent store recreation')
                try:outcome=q.verify_session(access_token=own.access_token)
                except ProviderError:outcome=None
                assert outcome is None,'existing provider accepted replacement directory inode'
            finally:
                if target.exists():shutil.rmtree(target)
                moved.rename(target)
            assert q.verify_session(access_token=own.access_token) is not None
            return {'replaced_lock':'denied','removed_directory_with_retained_anchor':'denied','restored_verified_original':'allowed'}
        case('lock_directory_replacement_and_new_store_identity_custody',replacement_custody)
        def anchor_and_total_store_loss():
            target=home/'anchor-controls';q=provider(target)
            own=q.complete_password_login(username=username,password=password)
            exp=int(time.time())+800
            old_at=basic._sign({'sub':username,'kind':'access','exp':exp},secret)
            old_rt=basic._sign({'sub':username,'kind':'refresh','exp':exp+500},secret)
            q.revoke_session(refresh_token=old_rt,access_token=old_at)
            anchor=Path(str(target)+'.anchor');assert anchor.is_file(),'no independent custody anchor'
            assert stat.S_IMODE(anchor.stat().st_mode)==0o600
            original=anchor.read_bytes()
            for label,operation in [('missing',lambda:anchor.unlink()),('corrupt',lambda:anchor.write_bytes(b'{bad')),('unsafe-mode',lambda:anchor.chmod(0o644))]:
                operation()
                try:
                    try:outcome=q.verify_session(access_token=own.access_token)
                    except ProviderError:outcome=None
                    assert outcome is None,label+' anchor bypassed existing instance'
                    try:provider(target)
                    except ProviderError:pass
                    else:raise AssertionError(label+' anchor bypassed fresh provider')
                finally:
                    if anchor.exists():anchor.unlink()
                    fd=os.open(anchor,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                    with os.fdopen(fd,'wb') as handle:handle.write(original)
            # This isolated store is actually deleted, retaining only its independent anchor.
            shutil.rmtree(target)
            assert anchor.read_bytes()==original
            for token in [own.access_token,old_at]:
                try:outcome=q.verify_session(access_token=token)
                except ProviderError:outcome=None
                assert outcome is None,'deleted store accepted retained access'
            try:provider(target)
            except ProviderError:pass
            else:raise AssertionError('whole store loss silently reset despite retained anchor')
            assert anchor.read_bytes()==original
            return {'whole_directory_deleted':'retained new/legacy access denied; fresh provider refused','anchor_missing_corrupt_mode':'failclosed','full_anchor_and_store_loss':'outside custody guarantee, deliberate full reprovision not tested'}
        case('anchor_custody_and_actual_whole_store_directory_loss_fail_closed',anchor_and_total_store_loss)
        def bounded_flock():
            target=home/'flock-controls';q=provider(target)
            own=q.complete_password_login(username=username,password=password)
            descriptor=os.open(target/'lock',os.O_RDWR);fcntl.flock(descriptor,fcntl.LOCK_EX)
            observed=[]
            def blocked_verify():
                began=time.monotonic()
                try:
                    q.verify_session(access_token=own.access_token)
                    observed.append(('accepted',time.monotonic()-began))
                except ProviderError:observed.append(('unavailable',time.monotonic()-began))
            worker=threading.Thread(target=blocked_verify,name='fixture-held-flock-verifier',daemon=True)
            try:
                worker.start();worker.join(5)
                assert not worker.is_alive(),'store lock acquisition exceeded five seconds'
                assert observed and observed[0][0]=='unavailable' and observed[0][1] < 5,observed
            finally:
                fcntl.flock(descriptor,fcntl.LOCK_UN);os.close(descriptor);worker.join(5)
            assert not worker.is_alive() and q.verify_session(access_token=own.access_token) is not None
            return {'contention_outcome':observed[0][0],'seconds':round(observed[0][1],3),'worker_joined':True,'after_release':'allowed'}
        case('real_flock_contention_deadline_and_recovery',bounded_flock)
        def fifo_custody():
            nonlocal child
            inp=root/'fifo-private-input.json'
            payload={'source':str(source),'home':str(home),'username':username,'password':password,'password_hash':password_hash,'secret':secret.hex()}
            write_private(inp,payload)
            argv=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'--fifo-child',str(inp)]
            record={'pid':None,'argv':argv,'started_unix':time.time(),'external_timeout_seconds':5};result['children'].append(record)
            child=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={'HERMES_HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1','PATH':os.environ.get('PATH','/usr/bin:/bin')},cwd=root)
            record['pid']=child.pid
            try:
                try:out,err=child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill();out,err=child.communicate(timeout=3)
                    record['timeout']=True
                    raise AssertionError('FIFO custody child blocked: killed and reaped at five seconds')
                record.update(returncode=child.returncode,stderr=err[:1500],events=[json.loads(line) for line in out.splitlines() if line.strip()])
                assert child.returncode==0,'FIFO custody subprocess failed'
                events=record['events'];assert len(events)==1 and events[0]['event']=='fifo-controls-complete'
                assert len(events[0]['observations'])==4
                return {'platform':'Linux','controls':events[0]['observations'],'external_bound_seconds':5,'child_reaped':True}
            finally:
                if child.poll() is None:
                    child.kill();child.communicate(timeout=3)
                record.update(ended_unix=time.time(),returncode=child.returncode,reaped=True)
                inp.unlink(missing_ok=True)
        case('real_linux_fifo_state_and_anchor_rejected_without_blocking_or_reset',fifo_custody)
        def atomic_concurrency():
            target=home/'atomic-store';q=provider(target)
            s=q.complete_password_login(username=username,password=password)
            ledger=next(x for x in target.iterdir() if x.is_file() and x.read_bytes().lstrip().startswith(b'{'))
            errors=[]; stop=threading.Event(); reads=[0]
            def reader():
                while not stop.is_set():
                    try: json.loads(ledger.read_text());reads[0]+=1
                    except Exception as exc:errors.append(type(exc).__name__);stop.set()
            thread=threading.Thread(target=reader,name='fixture-ledger-reader',daemon=True);thread.start()
            workers=[];sessions=[];session_lock=threading.Lock()
            def mint():
                try:
                    session=q.complete_password_login(username=username,password=password)
                    with session_lock:sessions.append(session)
                except Exception as exc:errors.append(type(exc).__name__)
            try:
                for _ in range(4):
                    worker=threading.Thread(target=mint,name='fixture-login-writer',daemon=True);workers.append(worker);worker.start()
                for worker in workers:worker.join(10);assert not worker.is_alive(),'writer failed to terminate'
            finally:
                stop.set();thread.join(5)
                for worker in workers:worker.join(5)
            assert not any(worker.is_alive() for worker in workers),'writer cleanup incomplete'
            assert not thread.is_alive() and not errors,errors
            assert len(sessions)==4 and reads[0]>0
            for session in sessions:assert q.verify_session(access_token=session.access_token) is not None
            assert not [x for x in target.iterdir() if (x.name.endswith('.tmp') or x.name.startswith('.state-'))],'orphan atomic temp files'
            return {'concurrent_writers':4,'complete_json_reads':reads[0],'workers_reaped':True}
        case('atomic_publication_real_concurrent_writers_and_reader',atomic_concurrency)
        def logout_failure():
            a=login()
            json_files=[x for x in store.iterdir() if x.is_file() and x.read_bytes().lstrip().startswith(b'{')]
            assert len(json_files)==1
            ledger=json_files[0];before=ledger.read_bytes();ledger.write_bytes(b'{bad')
            try:
                try:response=asyncio.run(routes.auth_logout(request(a[2],'/auth/logout','POST')))
                except HTTPException as exc:assert exc.status_code==503
                else:assert response.status_code==503,'logout claimed durable success on corrupted store'
                assert ledger.read_bytes()==b'{bad','logout silently reset ledger'
            finally:ledger.write_bytes(before);ledger.chmod(0o600)
        case('real_logout_corrupt_store_reports_non_success_and_preserves_bytes',logout_failure)
        def restart_race():
            nonlocal child
            assert 'revoked' in state,'core prerequisite missing'
            race=login();others=[];denied_attempts=0;attempted_refreshes=6
            payload={'source':str(source),'home':str(home),'username':username,'password_hash':password_hash,'secret':secret.hex(),'store':str(store),'revoked_at':state['revoked'][0],'revoked_rt':state['revoked'][1],'allowed_at':state['allowed'][0],'allowed_rt':state['allowed'][1],'race_rt':race[1]}
            inp=root/'child-private-input.json';write_private(inp,payload)
            argv=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'--child',str(inp)]
            begin=time.time();child=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={'HERMES_HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1','PATH':os.environ.get('PATH','/usr/bin:/bin')},cwd=root)
            record={'pid':child.pid,'argv':argv,'started_unix':begin};result['children'].append(record)
            sel=selectors.DefaultSelector();sel.register(child.stdout,selectors.EVENT_READ)
            try:
                assert sel.select(12),'restart child did not become ready'
                line=child.stdout.readline();ready=json.loads(line);assert ready['event']=='ready' and ready['pid']==child.pid
                record['ready']=ready
                preceding=native_refresh(race[1])
                assert isinstance(preceding,dict) and verify(preceding['access_token']) is not None,'preceding successful real refresh missing'
                record['preceding_successful_refresh_unix']=time.time()
                child.stdin.write('REVOKE\n');child.stdin.flush();child.stdin.close();child.stdin=None
                # Both may linearize first; after successful revoke every derived token must deny.
                for _ in range(attempted_refreshes):
                    value=native_refresh(race[1])
                    if isinstance(value,dict):others.append(value)
                    else:
                        assert value.status_code==401
                        denied_attempts+=1
                out,err=child.communicate(timeout=15);record.update(ended_unix=time.time(),returncode=child.returncode,reaped=child.poll() is not None,stderr=err[:1500],events=[json.loads(x) for x in out.splitlines() if x.strip()])
                assert child.returncode==0 and any(x.get('event')=='revoked' for x in record['events'])
                assert verify(race[0]) is None
                denied_refresh(race[1])
                assert verify(preceding['access_token']) is None
                denied_refresh(preceding['refresh_token'])
                for value in others:
                    assert verify(value['access_token']) is None
                    denied_refresh(value['refresh_token'])
                assert verify(state['allowed'][0]) is not None
            finally:
                sel.close()
                if child.poll() is None:
                    child.terminate()
                    try:child.communicate(timeout=3)
                    except subprocess.TimeoutExpired:child.kill();child.communicate(timeout=3)
                record.update(ended_unix=time.time(),returncode=child.returncode,reaped=True)
                inp.unlink(missing_ok=True)
            return {'restart_denied':'retained access and refresh','preceding_successful_real_refresh':True,'preceding_refresh_credentials_denied_after_revoke':True,'attempted_refreshes_after_revoke_signal':attempted_refreshes,'refresh_successes_after_signal':len(others),'refresh_denials_after_signal':denied_attempts,'observed_order':'revoke-first' if not others else 'at least one refresh completed before revoke','post_signal_derived_credentials_checked':len(others),'unrelated_session':'allowed','coverage':'bounded observed scheduling only; not exhaustive race interleavings'}
        case('real_process_restart_and_cross_process_revoke_refresh_race',restart_race)
        result['status']='PASS' if all(c['status']=='PASS' for c in result['cases']) else 'FAIL'
    except Exception as exc:
        result.update(status='ERROR',exception=type(exc).__name__,message=str(exc)[:400],traceback=traceback.format_exc()[-3000:])
    finally:
        if child is not None and child.poll() is None:
            child.kill();child.communicate(timeout=3)
        shutil.rmtree(root)
        result['synthetic_state_removed']=not root.exists()
        result['ended_unix']=time.time();result['elapsed_seconds']=round(time.time()-started,4)
        output=Path(args.output);output.write_text(json.dumps(result,indent=2)+'\n');output.chmod(0o600)
        print(json.dumps({'status':result['status'],'pid':os.getpid(),'cases':len(result['cases']),'failed':[c['name'] for c in result['cases'] if c['status']!='PASS'],'output':str(output),'synthetic_state_removed':result['synthetic_state_removed']}))
    return 0 if result['status']=='PASS' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--candidate');parser.add_argument('--output');parser.add_argument('--child');parser.add_argument('--fifo-child')
    args=parser.parse_args()
    if args.fifo_child:raise SystemExit(fifo_child_main(args))
    if args.child:raise SystemExit(child_main(args))
    assert args.candidate and args.output
    raise SystemExit(main(args))
