# UNBOUND ANALYSIS EXCERPT. Incomplete dependencies; not a runnable tester.
# Original operational values are omitted; see SOURCE-PROVENANCE.json.
def preflight(api, timeout=10, guard=None):
    expires = time.monotonic() + timeout
    def budget():
        remaining = expires - time.monotonic()
        if guard is not None:
            guarded = guard()
            remaining = min(expires - time.monotonic(), guarded)
        if remaining <= 0:
            raise Refused('Preflight deadline expired')
        return remaining
    me = api.call('getMe', timeout=budget())
    if me.get('is_bot') is not True or type(me.get('id')) is not int or me['id'] != TESTER or me['id'] == PEER:
        raise Refused('Authenticated identity is not pinned tester bot')
    webhook = api.call('getWebhookInfo', timeout=budget())
    if webhook.get('url') != '':
        raise Refused('Tester has webhook; do not delete or replace it')
    peer = api.call('getChat', {'chat_id': USERNAME}, timeout=budget())
    if peer.get('id') != PEER or peer.get('type') != 'private':
        raise Refused('Authenticated target lookup numeric peer mismatch')
    return {'tester_id': me['id'], 'is_bot': True, 'webhook_empty': True,
            'peer_id': peer['id'], 'mode_verified': False,
            'note': 'Both bot modes require external operator confirmation'}
