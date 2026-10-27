# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.
"""Exact S447 source-only successor of the existing S443 consumer; import is inert."""
from pathlib import Path
import hashlib, os, stat
_COMPAT = {'path': '<PRIVATE_CACHE>/PRIVATE_REF_07e78811c568fd24/source/compat.py', 'sha256': 'PRIVATE_REF_02fcb1106bb4b088'}
def _compat():
    p=Path(_COMPAT['path'])
    def need(ok):
        if not ok:raise ValueError('s447_compat_source_changed')
    need(p.is_absolute() and p.resolve()==p)
    parents={}
    for parent in p.parents:
        info=parent.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid in (0,os.getuid()) and not info.st_mode&0o022)
        parents[parent]=(info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)
    fields=('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_gid==os.getgid() and before.st_nlink==1 and stat.S_IMODE(before.st_mode)==0o600 and before.st_size<=2*1024**2)
        with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(2*1024**2+1)
        after=os.fstat(fd);named=p.lstat()
        need(len(raw)<=2*1024**2 and all(getattr(before,k)==getattr(after,k)==getattr(named,k) for k in fields) and hashlib.sha256(raw).hexdigest()==_COMPAT['sha256'])
    finally:os.close(fd)
    need(all((q.lstat().st_dev,q.lstat().st_ino,q.lstat().st_uid,q.lstat().st_gid,q.lstat().st_mode)==identity for q,identity in parents.items()))
    ns={'__file__':str(p),'__name__':'_s447_exact_source_compat'}
    exec(compile(raw,str(p),'exec'),ns)
    return ns

def _module():
    compat=_compat()
    old={'path':str(compat['OLD']/'bridge/maintenance.py'),'sha256':'PRIVATE_REF_1890db4b4077b6ec'}
    ns=compat['module'](old,'_s447_retained_native480')
    ns['source480']=compat['original_source480']
    original_verify=ns['verify480']
    def verify(request_ref,receipt_ref,config=None):
        result=original_verify(request_ref,receipt_ref,config)
        return compat['current_native_source'](result)
    ns['verify480']=verify
    return ns

def verify480(request_ref,receipt_ref,config=None):
    return _module()['verify480'](request_ref,receipt_ref,config)
def current480():return _module()['current480']()
def runtime480(config,request_ref,receipt_ref):return _module()['runtime480'](config,request_ref,receipt_ref)
