"""Pure, unbound future receive guard; current native15 cannot satisfy it.

The caller must bind expected_authority independently from the retained native
principal and admission. No grant is inferred from web_custody or these rows.
This code does not import or call the product, stop work, or change any clock.
"""
import hashlib
import json
import math

SCHEMA = 'frw.gateway.own-web-inflight-readonly.v1'


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def enc(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True)+'\n').encode()


def exact_quiescent(receipt):
    return (type(receipt) is dict and receipt.get('status') == 'QUIESCENT'
            and receipt.get('sessions') == [] and receipt.get('recovery_blocked') is False)


def quiescent_projection(native):
    """Additive custody must agree at receive, pre-send and strict cleanup."""
    projected = native.get('own_web_inflight')
    require(projected is None or type(projected) is dict
            and projected.get('schema') == SCHEMA and projected.get('sessions') == []
            and projected.get('recovery_blocked') is False
            and projected.get('unretained_calls') == [],
            'native_web_quiescent_projection_contradiction')


def guard(native, *, owned, run, expected_run_id, clock, now, receive_cutoff,
          value, before, resource_state, resource_before, dispatch_now,
          expected_authority, classify_layers):
    """Allow exact current own ordinary web only; return classification, never authority.

    Existing receive binding/native-user checks run before this function. Their
    current value and the same resource snapshot must be passed intact. Terminal
    and pre-send uses retain the original strict quiescent guard.
    """
    require(native is value['native'], 'same_current_native_observation_required')
    require(all(native.get(k) == [] for k in (
        'detached_owned_work', 'live_owned_delegations', 'durable_pending_delegations')),
        'native_detached_or_delegation_UNKNOWN')
    require(exact_quiescent(native.get('terminal_custody')), 'native_terminal_custody_UNKNOWN')
    web = native.get('web_custody')
    if exact_quiescent(web):
        quiescent_projection(native)
        return dict(state='QUIESCENT', sessions=[])
    require(type(web) is dict and web.get('status') == 'STOP_UNCONFIRMED'
            and web.get('recovery_blocked') is False
            and type(web.get('sessions')) is list and 1 <= len(web['sessions']) <= 8
            and all(type(s) is str and s for s in web['sessions'])
            and len(set(web['sessions'])) == len(web['sessions']), 'native_web_custody_UNKNOWN')
    projected = native.get('own_web_inflight')
    require(type(projected) is dict, 'native_own_web_identity_observation_missing')
    require(projected.get('schema') == SCHEMA, 'native_own_web_observation_schema_required')
    require(projected.get('recovery_blocked') is False and projected.get('unretained_calls') == [],
            'native_own_web_recovery_or_unretained_UNKNOWN')
    require(type(now) in (int, float) and math.isfinite(now)
            and clock['boot_id'] == native['boot_id']
            and clock['origin_monotonic'] <= now < receive_cutoff
            and receive_cutoff == clock['deadline_monotonic'] - 90,
            'original_receive_clock_cleanup90_required')
    require(run['id'] == expected_run_id and run.get('send_state') == 'sent'
            and owned['sent_message_id'] == run['sent_message_id']
            and owned['request_sha256'] == hashlib.sha256(enc(run['request_metadata'])).hexdigest(),
            'same_original_run_request_required')
    leases = [r for group in value['leases'] for r in group]
    users = [r for r in value['rows'] if r.get('id') == owned['own_user_row_id'] and r.get('role') == 'user']
    require(len(users) == 1 and owned['lease'] is not None and leases == [owned['lease']]
            and value['role'] == before['role'] and value['route_sha256'] == owned['route_sha256']
            and native['active'] is True and native['session_id'] == owned['session_id']
            and native['session_key'] == owned['session_key']
            and native['generation'] == native['ctx_generation'] == owned['generation']
            and native['ctx_inbound_message_id'] == native['event_message_id'] == str(users[0]['platform_message_id'])
            and native['active_session_keys'] == [owned['session_key']]
            and native['active_adapters'] == 1 and native['adapter_generations'] == [owned['generation']]
            and native['turn_tokens'] == [dict(session_id=owned['session_id'], owner_key=owned['session_key'],
                generation=owned['generation'], released=False)]
            and native['pending_messages'] == native['queued_events'] == 0
            and native['pending_command'] is False and native['approvals'] is False,
            'exact_active_own_request_generation_lease_required')
    require(type(expected_authority) is dict and set(expected_authority) == {
        'principal', 'profile', 'home', 'authorization_home', 'binding_sha256', 'generation'}
        and type(expected_authority['principal']) is list and len(expected_authority['principal']) == 4
        and all(type(x) is str and x for x in expected_authority['principal'])
        and all(type(expected_authority[k]) is str and expected_authority[k] for k in (
            'profile', 'home', 'authorization_home', 'binding_sha256'))
        and type(expected_authority['generation']) is int and expected_authority['generation'] > 0,
        'independent_original_principal_authority_binding_required')
    require(all(projected.get(k) == v for k, v in dict(session_id=owned['session_id'],
        session_key=owned['session_key'], generation=owned['generation'],
        event_message_id=native['event_message_id'], user_authority=expected_authority).items())
        and all(type(projected.get(k)) is str and projected[k] for k in ('task_id','turn_id')),
        'native_web_original_principal_turn_request_binding_changed')
    rows = projected.get('sessions')
    require(type(rows) is list and 1 <= len(rows) <= 8 and all(type(r) is dict for r in rows)
            and sorted(r.get('id','') for r in rows) == sorted(web['sessions']),
            'native_all_retained_web_sessions_coverage_required')
    latest = value['rows'][-1]
    require(latest.get('role') == 'assistant' and latest.get('finish_reason') == 'tool_calls',
            'current_native_active_tool_dispatch_required')
    calls = latest.get('tool_calls')
    if type(calls) is str:
        calls = json.loads(calls)
    require(type(calls) is list and 1 <= len(calls) <= 16, 'bounded_current_native_tool_calls_required')
    tools = {}
    for item in calls:
        require(type(item) is dict and type(item.get('id')) is str and item['id']
                and item['id'] not in tools and type(item.get('function')) is dict,
                'unique_native_tool_call_identity_required')
        name = item['function'].get('name')
        if name == 'tool_call':
            args = item['function'].get('arguments')
            if type(args) is str:
                args = json.loads(args)
            require(type(args) is dict and set(args) == {'calls'}
                    and type(args['calls']) is list and len(args['calls']) == 1
                    and type(args['calls'][0]) is dict
                    and set(args['calls'][0]) == {'name','arguments'}
                    and type(args['calls'][0]['arguments']) is dict,
                    'exact_single_native_web_dispatch_envelope_required')
            name = args['calls'][0]['name']
        tools[item['id']] = name
    seen = set()
    for row in rows:
        require(row.get('attribution') == 'OWN' and row.get('attribution_reasons') == [],
                'native_own_web_attribution_UNKNOWN')
        require(all(row.get(k) == v for k,v in dict(task_id=projected['task_id'],
            owner_task_id=projected['task_id'],session_key=owned['session_key'],
            parent_session_id=owned['session_id'],user_authority=expected_authority,
            web_turn_id=projected['turn_id'],web_boot_id=clock['boot_id']).items()),
            'web_session_owner_principal_turn_changed')
        tool = row.get('web_tool_call_id')
        require(type(tool) is str and tool not in seen and tools.get(tool) in ('web_search','web_extract'),
                'exact_ordinary_web_tool_call_required')
        seen.add(tool)
        require(row.get('web_custody') is True and all(row.get(k) is False for k in (
            'web_unconfirmed','web_settled','web_stop_requested','detached','exited','scope_stop_pending')),
            'web_session_UNKNOWN_recovery_cancelled_or_settled')
        require(type(row.get('web_deadline')) in (int,float) and math.isfinite(row['web_deadline'])
                and now < row['web_deadline'] <= clock['deadline_monotonic'],
                'web_original_finite_deadline_required')
        call = row.get('call')
        require(type(call) is dict and all(call.get(k) == v for k,v in dict(
            call_id=tool,task_id=projected['task_id'],session_id=owned['session_id'],
            session_key=owned['session_key'],turn_id=projected['turn_id'],user_authority=expected_authority).items())
            and all(call.get(k) is True for k in (
                'uses_web','same_active_agent','same_registry_session','same_web_turn','registered_on_agent'))
            and all(call.get(k) is False for k in ('stopped','turn_stopped','turn_failed')),
            'current_native_call_link_or_stop_fence_changed')
    layers = classify_layers(resource_state, before=resource_before, boot_id=clock['boot_id'],
        dispatch_at=run['send_dispatch_at'], now=dispatch_now, owned=owned,native=native,leases=value['leases'])
    require({'friday-inbound-pending','friday-whole-turn','friday-native-session-queue'} <= set(layers),
            'own_web_known_enclosing_resource_layers_required')
    return dict(state='ACTIVE_EXACT_OWN_WEB', sessions=sorted(web['sessions']), layers=sorted(layers))


def refusal_custody_snapshot(native):
    """Protected metadata-only first-refusal supplement; never tool arguments.

    Caller writes this once under its existing protected failure artifact. This
    does not call native again, so the originally refused observation is retained.
    """
    def fields(value, names):
        return {k: value[k] for k in names if k in value}
    common = ('status','sessions','recovery_blocked')
    authority_keys = ('principal','profile','home','authorization_home','binding_sha256','generation')
    out = {k: fields(native[k], common) if type(native.get(k)) is dict else None
           for k in ('web_custody','terminal_custody')}
    projected = native.get('own_web_inflight')
    out['own_web_inflight_present'] = type(projected) is dict
    if type(projected) is dict:
        out['own_web_inflight'] = fields(projected, ('schema','session_id','session_key','generation',
            'event_message_id','task_id','turn_id'))
        out['own_web_inflight']['user_authority'] = fields(projected.get('user_authority') or {},authority_keys)
        out['own_web_inflight'].update(fields(projected, ('recovery_blocked',)))
        calls = projected.get('unretained_calls')
        if type(calls) is list and len(calls) <= 16:
            out['own_web_inflight']['unretained_calls'] = [
                fields(call, ('call_id','task_id','session_id','session_key','turn_id',
                    'uses_web','stopped','turn_stopped','turn_failed','same_active_agent',
                    'same_registry_session','same_web_turn','registered_on_agent'))
                if type(call) is dict else dict(invalid_shape=type(call).__name__) for call in calls]
            for original, item in zip(calls, out['own_web_inflight']['unretained_calls']):
                if type(original) is dict:
                    item['user_authority'] = fields(original.get('user_authority') or {},authority_keys)
        else:
            out['own_web_inflight']['unretained_calls_shape_invalid'] = True
        rows = projected.get('sessions')
        if type(rows) is list and len(rows) <= 8:
            out['own_web_inflight']['sessions'] = []
            for row in rows:
                if type(row) is not dict:
                    out['own_web_inflight']['sessions'].append(dict(invalid_shape=type(row).__name__))
                    continue
                item = fields(row, ('id','task_id','owner_task_id','session_key','parent_session_id',
                    'web_tool_call_id','web_turn_id','web_boot_id','web_deadline','web_custody',
                    'web_unconfirmed','web_settled','web_stop_requested','detached','exited','scope_stop_pending'))
                item['user_authority'] = fields(row.get('user_authority') or {},authority_keys)
                if row.get('attribution') in ('OWN','FOREIGN','UNKNOWN','UNMATCHED','RECOVERY'):
                    item['attribution'] = row['attribution']
                reasons = row.get('attribution_reasons')
                allowed_reasons = {'registry_recovery_blocked','detached_registry_session',
                    'registered_call_unavailable','same_active_agent','same_web_turn',
                    'same_registry_session','registered_on_agent','uses_web','web_custody_missing',
                    'ambiguous_registry_call_association'}
                for name in ('parent_session','session_key','task','raw_task','turn','call','principal',
                             'active_session','active_key','active_task','active_turn','active_principal'):
                    allowed_reasons.update((name+'_missing',name+'_mismatch'))
                if type(reasons) is list and len(reasons) <= 32:
                    item['attribution_reasons'] = [r for r in reasons
                        if type(r) is str and r in allowed_reasons]
                call = row.get('call')
                if type(call) is dict:
                    item['call'] = fields(call, ('call_id','task_id','session_id','session_key','turn_id',
                        'uses_web','stopped','turn_stopped','turn_failed','same_active_agent',
                        'same_registry_session','same_web_turn','registered_on_agent'))
                    item['call']['user_authority'] = fields(call.get('user_authority') or {},authority_keys)
                out['own_web_inflight']['sessions'].append(item)
        else:
            out['own_web_inflight']['sessions_shape_invalid'] = True
    # A separate round-trip creates a frozen value without aliasing native state.
    return json.loads(json.dumps(out,ensure_ascii=True,allow_nan=False))
