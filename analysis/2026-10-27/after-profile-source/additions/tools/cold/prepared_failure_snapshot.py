"""Optional fixed-field helper for an existing Root failure handler.

No native imports, writes, effects or retry entry. Capture in the existing
exception handler before discarding the exception. This observes retained frame
values plus current file hashes; it cannot prove a past transient hash value.
"""
import hashlib
import json
from pathlib import Path


def prepared_failure_snapshot(exc, expected_prepared_code):
    if type(exc) is not PermissionError:
        return None
    tb = BaseException.__traceback__.__get__(exc)
    for _ in range(64):
        if tb is None:
            return None
        if tb.tb_frame.f_code is expected_prepared_code:
            local = tb.tb_frame.f_locals
            if not all(k in local for k in ('root', 'home', 'proof', 'binding', 'st')):
                return {'state': 'PREPARED_FRAME_INPUTS_UNAVAILABLE'}
            try:
                root,home,proof,binding,st = (local[k] for k in ('root','home','proof','binding','st'))
                if (not isinstance(root, Path) or not isinstance(home, Path)
                        or type(proof) is not dict or type(binding) is not dict):
                    return {'state': 'PREPARED_FRAME_INPUT_TYPES_UNEXPECTED'}
                fp=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                config=hashlib.sha256((home/'config.yaml').read_bytes()).hexdigest()
                soul=hashlib.sha256((home/'SOUL.md').read_bytes()).hexdigest()
                predicates = {'binding_sha256':proof['binding_sha256']==fp,
                    'authorization_home':proof['authorization_home']==str(root),
                    'directory_identity':proof['directory_identity']==[st.st_dev,st.st_ino],
                    'config_sha256':proof['config_sha256']==config,
                    'soul_sha256':proof['soul_sha256']==soul}
                now=home.lstat()
                return {'state':'FRAME_VALUES_AND_CURRENT_FILES_OBSERVED',
                    'historical_failed_predicate_proven':False,
                    'matches':predicates,
                    'captured_directory_matches_current':(st.st_dev,st.st_ino)==(now.st_dev,now.st_ino)}
            except BaseException:
                return {'state':'PREPARED_FRAME_SNAPSHOT_UNAVAILABLE'}
        tb = tb.tb_next
    return {'state':'PREPARED_FRAME_SEARCH_LIMIT'}
