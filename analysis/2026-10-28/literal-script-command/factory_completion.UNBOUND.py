raise RuntimeError('UNBOUND analysis excerpt; omitted bindings and dependencies; do not execute')

def completed(context_ref, output):
    """Verify this exact deterministic existing factory completion, no rebind.

    Static evidence is historical, never a fresh CAP/clock/cursor admission.
    The carrier independently checks its live cursor and current boundary.
    """
    read=checked_loader()
    def get(ref):
        if type(ref)is not dict or set(ref) not in ({'path','sha256'},{'path','sha256','bytes'}):raise ValueError('exact_protected_reference_required')
        raw=read(ref['path'])
        if hashlib.sha256(raw).hexdigest()!=ref['sha256'] or ('bytes'in ref and len(raw)!=ref['bytes']):raise ValueError('source_or_context_changed')
        return raw
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('duplicate_static_evidence_key')
            result[k]=v
        return result
    root=Path(output)
    if (not root.is_absolute() or root.parent!=HOME/'UNBOUND_CACHE' or not root.name.startswith('UNBOUND_STATIC_PREFIX-')
            or root.is_symlink()):raise ValueError('exact_Root_output_required')
    ctx=json.loads(get(context_ref),object_pairs_hook=unique)
    if (type(ctx)is not dict or set(ctx)!={'schema','operator','contract','binding','current_tuple','current_session','UNBOUND_CLOSED_EFFECT_KEY'}
            or ctx['schema']!='UNBOUND_STATIC_BIND_CONTEXT_SCHEMA' or ctx['operator']!='Root'):raise ValueError('exact_actual_Root_context_required')
    contract=json.loads(get(ctx['contract']),object_pairs_hook=unique)
    gate_raw=get(GATE_SOURCE);template=get(TEMPLATE);get(OLD_GATE);get(PREPARER)
    # Use the exact factory serialization, without executing live gate checks.
    gate={'__file__':GATE_SOURCE['path'],'__name__':'UNBOUND_COMPLETED_STATIC_DECODE'}
    exec(compile(gate_raw,GATE_SOURCE['path'],'exec'),gate)
    bound_gate=assignment(gate_raw,'CONTRACT',contract)
    binding_raw=gate['encode'](ctx['binding'])
    gate_ref=pin(root/'UNBOUND_GATE.py',bound_gate)
    binding_ref=tester_pin(root/'UNBOUND_BINDING.json',binding_raw)
    candidate=assignment(assignment(assignment(template,'UNBOUND_GATE_SOURCE_SLOT',gate_ref),
        'UNBOUND_ORDINARY_BINDING_SLOT',binding_ref),'UNBOUND_CLOSED_EFFECT_BINDING_SLOT',ctx['UNBOUND_CLOSED_EFFECT_KEY'])
    source_ref=tester_pin(root/'bot_tester.py',candidate)
    if source_ref['sha256']!=EXPECTED_CANDIDATE_SHA256:raise ValueError('exact_reviewed_candidate_pin_required')
    for ref in (gate_ref,binding_ref,source_ref):get(ref)
    manifest=json.loads(read(str(root/'STATIC-BOUND.json')),object_pairs_hook=unique)
    expected=dict(schema='UNBOUND_STATIC_BOUND_SCHEMA',operator='Root',source=source_ref,gate=gate_ref,
        binding=binding_ref,context={k:context_ref[k] for k in ('path','sha256')},contract=ctx['contract'],template=TEMPLATE,preparer_unchanged=PREPARER,
        expected_installed_before_sha256=BASE_SHA,installed=False,admitted=False,clock_created=False,
        worker_or_model_or_Telegram_calls=False,native_or_service_or_auth_calls=False,
        current_clock_session_serial_cursor_and_once_authority='UNBOUND')
    if (type(manifest)is not dict or set(manifest)!=set(expected)|{'checked'}
            or any(manifest[k]!=v for k,v in expected.items()) or type(manifest['checked'])is not dict
            or set(p.name for p in root.iterdir())!={'UNBOUND_GATE.py','UNBOUND_BINDING.json','bot_tester.py','STATIC-BOUND.json'}):
        raise ValueError('exact_static_completion_required')
    return manifest


def bind(context_ref,output):
    read=checked_loader()
    def get(ref):
        if type(ref)is not dict or set(ref)!={'path','sha256'}:raise ValueError('exact_protected_reference_required')
        raw=read(ref['path'])
        if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('source_or_context_changed')
        return raw
    # The packaged exact gate digest is frozen by build; caller cannot select it.
    if GATE_SOURCE is None:raise ValueError('PACKAGED_GATE_PIN_UNBOUND')
    raw=get(GATE_SOURCE);gate={'__file__':GATE_SOURCE['path'],'__name__':'UNBOUND_PACKAGED_GATE'}
    exec(compile(raw,GATE_SOURCE['path'],'exec'),gate)
    ctx_raw=get(context_ref);ctx=gate['decode'](ctx_raw)
    if (type(ctx)is not dict or set(ctx)!={'schema','operator','contract','binding','current_tuple','current_session','UNBOUND_CLOSED_EFFECT_KEY'}
            or ctx['schema']!='UNBOUND_STATIC_BIND_CONTEXT_SCHEMA' or ctx['operator']!='Root'):raise ValueError('exact_actual_Root_context_required')
    contract_raw=get(ctx['contract']);contract=gate['decode'](contract_raw)
    gate['CONTRACT']=contract
    # All source joins and exact ordinary gates run before any output write.
    checked=gate['check'](ctx['binding'],ctx['current_tuple'],ctx['current_session'],dispatch=False)
    template=get(TEMPLATE);get(OLD_GATE);get(PREPARER)
    typed={'__file__':TEMPLATE['path'],'__name__':'UNBOUND_CLOSED_EFFECT_BOUND_CHECK'}
    exec(compile(template,TEMPLATE['path'],'exec'),typed)
    typed['UNBOUND_CLOSED_EFFECT_BINDING_SLOT']=ctx['UNBOUND_CLOSED_EFFECT_KEY']
    store=object.__new__(typed['Store']);store.root=HOME/'UNBOUND_TESTER_STATE';store.runs=store.root/'runs'
    runner=object.__new__(typed['Runner']);runner.store=store;runner.clock=typed['time'].time
    typed['UNBOUND_CLOSED_EFFECT_PROOF_FUNCTION'](runner)
    root=Path(output)
    if (not root.is_absolute() or root.parent!=HOME/'UNBOUND_CACHE' or not root.name.startswith('UNBOUND_STATIC_PREFIX-')
            or root.exists() or root.is_symlink() or root.parent.resolve()!=root.parent):raise ValueError('absent_exact_Root_output_required')
    for q in (root.parent,*root.parent.parents):
        s=q.lstat()
        if s.st_uid not in (0,os.getuid()) or s.st_mode&0o022:raise ValueError('protected_output_parent_required')
    gate_candidate=assignment(raw,'CONTRACT',contract)
    if normalized(raw,{'CONTRACT'})!=normalized(gate_candidate,{'CONTRACT'}):raise ValueError('gate_binding_changed_code')
    compile(gate_candidate,'UNBOUND_BOUND_GATE.py','exec')
    bound_gate=pin(root/'UNBOUND_GATE.py',gate_candidate)
    binding_raw=gate['encode'](ctx['binding'])
    bound_binding=tester_pin(root/'UNBOUND_BINDING.json',binding_raw)
    candidate=assignment(template,'UNBOUND_GATE_SOURCE_SLOT',bound_gate)
    candidate=assignment(candidate,'UNBOUND_ORDINARY_BINDING_SLOT',bound_binding)
    candidate=assignment(candidate,'UNBOUND_CLOSED_EFFECT_BINDING_SLOT',ctx['UNBOUND_CLOSED_EFFECT_KEY'])
    if hashlib.sha256(candidate).hexdigest()!=EXPECTED_CANDIDATE_SHA256:raise ValueError('exact_reviewed_candidate_pin_required')
    if normalized(template,{'UNBOUND_GATE_SOURCE_SLOT','UNBOUND_ORDINARY_BINDING_SLOT','UNBOUND_CLOSED_EFFECT_BINDING_SLOT'})!=normalized(candidate,{'UNBOUND_GATE_SOURCE_SLOT','UNBOUND_ORDINARY_BINDING_SLOT','UNBOUND_CLOSED_EFFECT_BINDING_SLOT'}):raise ValueError('tester_code_changed')
    compile(candidate,'UNBOUND_BOUND_TESTER.py','exec')
    root.mkdir(mode=0o700)
    def put(name,data):
        fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb')as f:f.write(data);f.flush();os.fsync(f.fileno())
        return pin(root/name,data)
    put('UNBOUND_GATE.py',gate_candidate)
    put('UNBOUND_BINDING.json',binding_raw)
    source=put('bot_tester.py',candidate);source['bytes']=len(candidate)
    result=dict(schema='UNBOUND_STATIC_BOUND_SCHEMA',operator='Root',source=source,gate=bound_gate,binding=bound_binding,
        context=context_ref,contract=ctx['contract'],template=TEMPLATE,preparer_unchanged=PREPARER,checked=checked,
        expected_installed_before_sha256=BASE_SHA,installed=False,admitted=False,clock_created=False,
        worker_or_model_or_Telegram_calls=False,native_or_service_or_auth_calls=False,
        current_clock_session_serial_cursor_and_once_authority='UNBOUND')
    put('STATIC-BOUND.json',gate['encode'](result))
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return result
