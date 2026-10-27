raise RuntimeError('UNBOUND analysis excerpt; omitted bindings and dependencies; do not execute')

def accepted(m, *, candidate_path, candidate_sha256, root_review_path, root_review_sha256):
    candidate, candidate_id = m['read_file'](candidate_path, private=True)
    review, review_id = m['read_file'](root_review_path, private=True)
    expected = dict(schema='UNBOUND_ROOT_REVIEW_SCHEMA', operator='Root', status='ACCEPTED',
        source=str(m['SOURCE']), before_sha256=BEFORE, candidate=str(m['checked_path'](candidate_path)),
        candidate_sha256=candidate_sha256)
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('duplicate_Root_review_key')
            result[k]=v
        return result
    if (m['sha'](candidate) != candidate_sha256 or m['sha'](review) != root_review_sha256
            or json.loads(review,object_pairs_hook=unique) != expected):
        raise ValueError('actual_Root_exact_candidate_review_required')
    return candidate, candidate_id, review_id, expected


def completion(m, **args):
    """Read the original installer completion under its unchanged two locks.

    Bytes equality alone is never completion. Partial/UNKNOWN install evidence
    cannot call install again; historical clock/intent records remain untouched.
    """
    for directory in (m['STATE'], WORK):
        s = m['checked_path'](directory).stat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != m['UID'] or stat.S_IMODE(s.st_mode) != 0o700:
            raise ValueError('existing_private_install_directories_required')
    backup_path, intent_path, receipt_path = (WORK/n for n in ('installed-before.py','INTENT.json','RECEIPT.json'))
    backup, backup_id = m['read_file'](backup_path, private=True)
    if m['sha'](backup) != BEFORE: raise ValueError('original_install_backup_changed')
    # Only the exact original baseline supplies native Store.lock definitions.
    ns = {'__file__':str(m['SOURCE']), '__name__':'UNBOUND_ORIGINAL_INSTALL_LOCKS'}
    exec(compile(backup,str(m['SOURCE']),'exec'),ns)
    store = object.__new__(ns['Store']); store.root = m['STATE']
    with store.lock(create=False) as consumer, store.lock(m['STATE']/'tester-token', create=False) as token:
        fds=[('consumer.lock',consumer),('tester-token',token)]
        locks={name:m['identity'](os.fstat(fd)) for name,fd in fds}
        result=checked_completion(m, args, backup, intent_path, receipt_path, locks)
        for name,fd in fds:
            if (m['identity'](os.fstat(fd))!=locks[name]
                    or m['identity'](m['checked_path'](m['STATE']/name).stat())!=locks[name]):
                raise ValueError('original_completion_lock_inode_changed')
        if m['read_file'](backup_path,private=True)!=(backup,backup_id):raise ValueError('original_backup_changed_during_read')
        return result


def checked_completion(m, args, backup, intent_path, receipt_path, locks):
    """Pure receipt join after held reads; separately testable without live state."""
    candidate, candidate_id, review_id, expected = accepted(m, **args)
    held={}
    def document(path):
        raw, identity = m['read_file'](path, private=True);held[path]=(raw,identity)
        def unique(pairs):
            out = {}
            for k,v in pairs:
                if k in out: raise ValueError('duplicate_install_evidence_key')
                out[k] = v
            return out
        return json.loads(raw, object_pairs_hook=unique)
    intent, receipt = document(intent_path), document(receipt_path)
    base_fields = set(expected)|{'root_review','root_review_sha256','before_identity','candidate_identity',
        'review_identity','locks','backup','temporary','temporary_identity','at_unix'}
    identity_fields={'device','inode','uid','gid','mode','nlink','size','mtime_ns','ctime_ns'}
    for identity in (intent.get('before_identity'),intent.get('temporary_identity')):
        if (type(identity)is not dict or set(identity)!=identity_fields
                or any(type(v)is not int or v<0 for v in identity.values())):
            raise ValueError('exact_native_identity_format_required')
    if (type(intent) is not dict or set(intent) != base_fields|{'state'} or intent['state'] != 'INTENT'
            or type(receipt) is not dict or set(receipt) != base_fields|{'state','after_identity','after_sha256','finished_unix'}
            or receipt['state'] != 'INSTALLED_SOURCE_ONLY'
            or {k:v for k,v in receipt.items() if k not in ('state','after_identity','after_sha256','finished_unix')}
                != {k:v for k,v in intent.items() if k != 'state'}
            or any(intent[k] != v for k,v in expected.items())
            or intent['root_review'] != str(m['checked_path'](args['root_review_path']))
            or intent['root_review_sha256'] != args['root_review_sha256']
            or intent['candidate_identity'] != candidate_id or intent['review_identity'] != review_id
            or intent['locks'] != locks or intent['backup'] != str(WORK/'installed-before.py')
            or m['sha'](backup) != BEFORE
            or any(type(receipt[k]) not in (int,float) or not math.isfinite(receipt[k]) for k in ('at_unix','finished_unix'))
            or receipt['finished_unix'] < receipt['at_unix']):
        raise ValueError('exact_original_install_completion_required')
    temporary = m['checked_path'](intent['temporary'])
    if temporary.parent != m['SOURCE'].parent or not temporary.name.startswith('.UNBOUND_INSTALL_STAGE-') or os.path.lexists(temporary):
        raise ValueError('original_staged_file_boundary_required')
    installed, installed_id = m['read_file'](m['SOURCE'], private=True)
    stable = ('device','inode','uid','gid','mode','nlink','size','mtime_ns')
    if (installed != candidate or receipt['after_sha256'] != args['candidate_sha256']
            or installed_id != receipt['after_identity']
            or any(installed_id[k] != intent['temporary_identity'][k] for k in stable)
            or any(intent['before_identity'][k] != installed_id[k] for k in ('uid','gid','mode'))
            or intent['before_identity']['size'] != len(backup)):
        raise ValueError('actual_installed_completion_bytes_or_identity_changed')
    for path,snapshot in held.items():
        if m['read_file'](path,private=True)!=snapshot:raise ValueError('install_completion_changed_during_read')
    if m['read_file'](m['SOURCE'],private=True)!=(installed,installed_id):raise ValueError('installed_completion_changed_during_read')
    if accepted(m,**args)!=(candidate,candidate_id,review_id,expected):raise ValueError('candidate_or_review_changed_during_read')
    return dict(source=str(m['SOURCE']),sha256=args['candidate_sha256'],
        exact_candidate_already_installed=True,installation_performed=False,
        original_installer=OLD,completion_receipt=dict(path=str(receipt_path),
            sha256=m['sha'](held[receipt_path][0])))


def run(*, verify_only=False, **args):
    read = reader(); m = original(read)
    refread(read,dict(path=args['candidate_path'],sha256=args['candidate_sha256']))
    refread(read,dict(path=args['root_review_path'],sha256=args['root_review_sha256']))
    present = [os.path.lexists(WORK/n) for n in ('installed-before.py','INTENT.json','RECEIPT.json')]
    if any(present) or verify_only:
        return completion(m, **args)
    accepted(m, **args)  # Root review is required even if bytes happen to match.
    result = m['install'](**args)
    completion(m, **args)  # Readback proof, never a second install.
    return result
