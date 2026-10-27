raise RuntimeError('UNBOUND analysis excerpt; omitted bindings and dependencies; do not execute')

def child(phase,args,cap):
    now=time.monotonic();remaining=min(cap,OUTER_DEADLINE-now-CHILD_RESERVE)
    if not math.isfinite(remaining) or remaining<=2:raise TimeoutError('original_clock_exhausted')
    put(phase+'-INTENT.json',dict(argv=args,began_monotonic=now,original_deadline=OUTER_DEADLINE,timeout_seconds=remaining,no_retry=True))
    r=subprocess.run(['UNBOUND_TIMEOUT_EXECUTABLE','--signal=TERM','--kill-after=2s',str(remaining)+'s',*args],capture_output=True)
    result=dict(exit_code=r.returncode,elapsed_seconds=time.monotonic()-now,stdout=r.stdout.decode('utf-8','replace'),stderr=r.stderr.decode('utf-8','replace'))
    put(phase+'-RETURN.json',result)
    if r.returncode:raise RuntimeError('phase_failed_'+phase)
    for line in reversed(result['stdout'].splitlines()):
        try:return json.loads(line)
        except ValueError:pass
    raise ValueError('missing_json_'+phase)


def perform_setup(x):
    factory=module(FIXED['factory'][0],held(dict(path=FIXED['factory'][0],sha256=FIXED['factory'][1])),'UNBOUND_EXACT_SETUP_REVIEW_PIN')
    expected=dict(schema='UNBOUND_ROOT_REVIEW_SCHEMA',operator='Root',status='ACCEPTED',source=str(TESTER),
        before_sha256=BASE,candidate=str(STATIC/'bot_tester.py'),candidate_sha256=factory['EXPECTED_CANDIDATE_SHA256'])
    if doc(x['tester_root_review'])!=expected:raise ValueError('actual_Root_exact_candidate_review_required')
    result=child('BIND-SOURCE',[PYTHON,'-I','-B',FIXED['factory'][0],'--context',x['static_context']['path'],'--sha256',x['static_context']['sha256'],'--output',str(STATIC)],120)
    source=result['source'];held(source)
    review=doc(x['tester_root_review'])
    expected=dict(schema='UNBOUND_ROOT_REVIEW_SCHEMA',operator='Root',status='ACCEPTED',source=str(TESTER),before_sha256=BASE,candidate=source['path'],candidate_sha256=source['sha256'])
    if review!=expected:raise ValueError('actual_Root_exact_candidate_review_required')
    (P/'install').mkdir(mode=0o700)
    child('CAS-INSTALL',[PYTHON,'-I','-B',FIXED['installer'][0],'--candidate-path',source['path'],'--candidate-sha256',source['sha256'],'--root-review-path',x['tester_root_review']['path'],'--root-review-sha256',x['tester_root_review']['sha256']],60)
    return source


def verified_setup(x):
    # Never infer completion from target bytes or an intent alone.
    marker=doc(ref(SETUP_W/'ROOT-SETUP-RETURNED.json'))
    if (type(marker)is not dict or set(marker)!={'schema','operator','source','static_context','tester_root_review','static_manifest','install_receipt','original_clock'}
            or marker['schema']!='UNBOUND_SETUP_RETURNED_SCHEMA' or marker['operator']!='Root'
            or marker['static_context']!=x['static_context'] or marker['tester_root_review']!=x['tester_root_review']):
        raise ValueError('exact_completed_setup_required')
    for key in ('source','static_context','tester_root_review','static_manifest','install_receipt','original_clock'):held(marker[key])
    if (marker['static_manifest']['path']!=str(STATIC/'STATIC-BOUND.json')
            or marker['install_receipt']['path']!=str(P/'install/RECEIPT.json')
            or marker['original_clock']['path']!=str(SETUP_W/'ORIGINAL-CLOCK.json')):raise ValueError('exact_setup_completion_paths_required')
    for phase in ('BIND-SOURCE','CAS-INSTALL'):
        outcome=doc(ref(SETUP_W/(phase+'-RETURN.json')))
        if outcome.get('exit_code')!=0:raise ValueError('partial_setup_no_retry')
        doc(ref(SETUP_W/(phase+'-INTENT.json')))
    f=module(FIXED['factory'][0],held(dict(path=FIXED['factory'][0],sha256=FIXED['factory'][1])),'UNBOUND_EXACT_COMPLETED_FACTORY')
    bound=f['completed'](x['static_context'],STATIC)
    if bound['source']!=marker['source']:raise ValueError('setup_bound_source_changed')
    i=module(FIXED['installer'][0],held(dict(path=FIXED['installer'][0],sha256=FIXED['installer'][1])),'UNBOUND_EXACT_COMPLETED_INSTALLER')
    proof=i['run'](verify_only=True,candidate_path=bound['source']['path'],candidate_sha256=bound['source']['sha256'],
        root_review_path=x['tester_root_review']['path'],root_review_sha256=x['tester_root_review']['sha256'])
    if proof['completion_receipt']!=small(marker['install_receipt']):raise ValueError('setup_native_receipt_changed')
    return bound['source']


def setup_only(x):
    global W,OUTER_DEADLINE,ENTERED,CHILD_RESERVE
    fields={'schema','operator','static_context','tester_root_review'}
    if type(x)is not dict or set(x)!=fields or x['schema']!='UNBOUND_SETUP_INPUT_SCHEMA' or x['operator']!='Root':raise ValueError('exact_Root_setup_inputs_required')
    for key in fields-{'schema','operator'}:held(x[key])
    for path,digest in FIXED.values():held(dict(path=path,sha256=digest))
    for path in (W,SETUP_W,STATIC,P/'install'):
        if os.path.lexists(path):raise ValueError('existing_setup_effect_reconcile_no_retry')
    W=SETUP_W;W.mkdir(mode=0o700);ENTERED=True
    origin=time.monotonic();OUTER_DEADLINE=origin+240;CHILD_RESERVE=15
    clock=put('ORIGINAL-CLOCK.json',dict(operator='Root',origin_monotonic=origin,original_deadline_monotonic=OUTER_DEADLINE,
        total_seconds=240,reserve_seconds=15,no_reset=True,setup_only=True))
    source=perform_setup(x)
    marker=put('ROOT-SETUP-RETURNED.json',dict(schema='UNBOUND_SETUP_RETURNED_SCHEMA',operator='Root',source=source,
        static_context=x['static_context'],tester_root_review=x['tester_root_review'],
        static_manifest=ref(STATIC/'STATIC-BOUND.json'),install_receipt=ref(P/'install/RECEIPT.json'),original_clock=clock))
    # A fresh process performs all later tester actions. No A0 admission here.
    print(json.dumps(dict(source=source,proof=marker,ordinary_clock_created=False,ordinary_A0_invoked=False),sort_keys=True))
