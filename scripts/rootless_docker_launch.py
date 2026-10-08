#!/usr/bin/python3
"""Source of the existing private launch.py; installation requires parent review.

Enable memory only inside this unit's already delegated subtree, before Docker
caches its capabilities. No unit, outer limit, ancestor or permission changes.
"""
import hashlib
import os
from pathlib import Path
import stat
import sys
import fcntl
import json
import re
import subprocess
import time
from contextlib import contextmanager

ROOT = Path('/home/jericho/jericho/Friday_rework/.runtime/rootless-docker')
CGROUP_ROOT = Path('/sys/fs/cgroup')
SELF_CGROUP = Path('/proc/self/cgroup')
SERVICE_GROUP = '/user.slice/user-1000.slice/user@1000.service/app.slice/friday-rework-docker.service'
UID = 1000
UNIT_SHA256 = '53e6d86ff912f4ad0761362bc5e7937d2131e48892469236be09db6b49bcd0ba'
CONFIG_SHA256 = '4a423b2c8869a9fc5281b42141940301eed066866d64a6c55e9581ab507d45fb'
SCRIPT_SHA256 = '200203633806081a401e60aefdf68a8fa73fc7dc80aa854c52a69d47710a3488'
INSTALLED_UNIT = Path('/home/jericho/.config/systemd/user/friday-rework-docker.service')
STATE = Path('/run/user/1000/friday-rework-docker')
REQUEST = ROOT / 'config/local-route.json'
GUARD = STATE / 'route-guard.json'
NFT = Path('/usr/sbin/nft')
NSENTER = Path('/usr/bin/nsenter')
BRIDGE = 'br-frwa0local'
ENDPOINTS = [{'ip': '192.168.1.78', 'port': 8001, 'transport': 'tcp'},
             {'ip': '192.168.1.78', 'port': 8002, 'transport': 'tcp'}]
NS_GET_USERNS = 0xb701


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def no_duplicates(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, 'duplicate_route_field')
        result[k] = v
    return result


def exact_json(text):
    require(len(text.encode()) <= 1024 * 1024, 'route_readback_too_large')
    return json.loads(text, object_pairs_hook=no_duplicates,
                      parse_constant=lambda _: require(False, 'nonfinite_route_field'))


def stable_bytes(path, uid, limit=1024*1024):
    require(path.is_absolute() and path.resolve() == path, 'route_path_changed')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == uid
                and before.st_nlink == 1 and before.st_size <= limit
                and not before.st_mode & 0o022, 'route_file_changed')
        b = os.read(fd, limit + 1)
        after = os.fstat(fd); named = path.lstat()
        key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns,
                         s.st_ctime_ns, s.st_mode, s.st_uid, s.st_nlink)
        require(len(b) <= limit and key(before) == key(after) == key(named), 'route_file_race')
        return b
    finally:
        os.close(fd)


def private_json(path, uid):
    require(stat.S_IMODE(path.lstat().st_mode) == 0o600, 'route_private_mode')
    return exact_json(stable_bytes(path, uid).decode())


# Public web permission is explicit and separate from fixed local inference.
# This source revision changes no live unit, ancestor resource or old grant.
PUBLIC_DENY = ['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8',
               '169.254.0.0/16','172.16.0.0/12','192.0.0.0/24','192.0.2.0/24',
               '192.168.0.0/16','198.18.0.0/15','198.51.100.0/24','203.0.113.0/24','224.0.0.0/3']


def checked_web(web):
    import ipaddress
    require(isinstance(web,dict) and set(web)=={'profile','dns','public_https'}
            and web['profile']=='searxng-google' and web['public_https'] is True
            and isinstance(web['dns'],list) and 1 <= len(web['dns']) <= 2
            and len(set(web['dns']))==len(web['dns']), 'web_route_shape')
    for text in web['dns']:
        ip=ipaddress.ip_address(text)
        require(ip.version==4 and ip.is_global and str(ip)==text,'web_dns_not_public')
    return web


def web_rule_text(chain, web):
    rows=[]
    # Incoming rules are established replies only. Egress is limited to exact
    # DNS servers or public IPv4 HTTPS; no private-document/model reroute.
    directions = (True,) if chain=='input' else ((False,True) if chain=='forward' else (False,))
    for incoming in directions:
        prefix='meta nfproto ipv4 '
        if incoming: prefix+='iifname "tap0" '
        if chain=='forward': prefix+=('oifname' if incoming else 'iifname')+' "'+BRIDGE+'" '
        if not incoming: prefix+='oifname "tap0" '
        addr='saddr' if incoming else 'daddr';port='sport' if incoming else 'dport'
        state='established' if incoming else '{ new, established }'
        for proto in ('udp','tcp'):
            rows.append(prefix+'meta l4proto '+proto+' ip '+addr+' { '+', '.join(web['dns'])+' } '+proto+' '+port+' 53 ct state '+state+' counter accept')
        rows.append(prefix+'meta l4proto tcp ip '+addr+' != { '+', '.join(PUBLIC_DENY)+' } tcp '+port+' 443 ct state '+state+' counter accept')
    return rows


def web_rule_expr(chain, web):
    def match(left,right,op='=='):return {'match':{'op':op,'left':left,'right':right}}
    def meta(k,v):return match({'meta':{'key':k}},v)
    def payload(protocol,field,v,op='=='):return match({'payload':{'protocol':protocol,'field':field}},v,op)
    rows=[]
    directions = (True,) if chain=='input' else ((False,True) if chain=='forward' else (False,))
    for incoming in directions:
        for proto in ('udp','tcp','https'):
            protocol='tcp' if proto=='https' else proto
            r=[meta('nfproto','ipv4'),meta('l4proto',protocol)]
            if incoming:r.append(meta('iifname','tap0'))
            if chain=='forward':r.append(meta('oifname' if incoming else 'iifname',BRIDGE))
            if not incoming:r.append(meta('oifname','tap0'))
            if proto=='https':
                addresses={'set':[{'prefix':{'addr':p.split('/')[0],'len':int(p.split('/')[1])}} for p in PUBLIC_DENY]}
                r.append(payload('ip','saddr' if incoming else 'daddr',addresses,'!='))
            else:r.append(payload('ip','saddr' if incoming else 'daddr',{'set':web['dns']}))
            r += [payload(protocol,'sport' if incoming else 'dport',443 if proto=='https' else 53),
                  match({'ct':{'key':'state'}},['established'] if incoming else ['new','established'],'in'),
                  {'counter':None},{'accept':None}]
            rows.append(r)
    return rows


def policy(web=None):
    # Fixed per this TEST grant, not a general firewall command interface.
    lines = ['create table inet frw_a0_local']
    for chain in ('input', 'forward', 'output'):
        lines.append('add chain inet frw_a0_local ' + chain +
                     ' { type filter hook ' + chain + ' priority -10; policy drop; }')
    rules = {
        'input': ['meta nfproto ipv6 counter drop',
                  'meta nfproto ipv4 meta l4proto tcp iifname "tap0" ip saddr 192.168.1.78 tcp sport { 8001, 8002 } ct state established counter accept',
                  'counter drop'],
        'forward': ['meta nfproto ipv6 counter drop',
                    'meta nfproto ipv4 meta l4proto tcp iifname "br-frwa0local" oifname "tap0" ip daddr 192.168.1.78 tcp dport { 8001, 8002 } ct state { new, established } counter accept',
                    'meta nfproto ipv4 meta l4proto tcp iifname "tap0" oifname "br-frwa0local" ip saddr 192.168.1.78 tcp sport { 8001, 8002 } ct state established counter accept',
                    'counter drop'],
        'output': ['meta nfproto ipv6 counter drop',
                   'meta nfproto ipv4 meta l4proto tcp oifname "tap0" ip daddr 192.168.1.78 tcp dport { 8001, 8002 } ct state { new, established } counter accept',
                   'counter drop']}
    for chain, rs in rules.items():
        lines.extend('add rule inet frw_a0_local ' + chain + ' ' + r for r in rs)
    if web is not None:
        checked_web(web)
        # Insert only explicit DNS and public HTTPS before the final drop.
        for chain in ('input','forward','output'):
            extra = web_rule_text(chain, web)
            terminal = 'add rule inet frw_a0_local ' + chain + ' counter drop'
            at = lines.index(terminal)
            lines[at:at] = ['add rule inet frw_a0_local ' + chain + ' ' + rule for rule in extra]
    return '\n'.join(lines) + '\n'


def policy_hash(web=None):
    return hashlib.sha256(policy(web).encode()).hexdigest()


def expected_rules(web=None):
    def match(left, right):
        return {'match': {'op': '==', 'left': left, 'right': right}}
    def meta(k, v): return match({'meta': {'key': k}}, v)
    def payload(protocol, field, v): return match({'payload': {'protocol': protocol, 'field': field}}, v)
    def allow(incoming, bridge=False):
        out = [meta('nfproto', 'ipv4'), meta('l4proto', 'tcp')]
        if incoming: out += [meta('iifname', 'tap0')]
        if bridge: out += [meta('oifname' if incoming else 'iifname', BRIDGE)]
        if not incoming: out += [meta('oifname', 'tap0')]
        out += [payload('ip', 'saddr' if incoming else 'daddr', '192.168.1.78'),
                payload('tcp', 'sport' if incoming else 'dport', {'set': [8001, 8002]}),
                {'match': {'op': 'in', 'left': {'ct': {'key': 'state'}},
                           'right': ['established'] if incoming else ['new', 'established']}},
                {'counter': None}, {'accept': None}]
        return out
    deny6 = [meta('nfproto', 'ipv6'), {'counter': None}, {'drop': None}]
    deny = [{'counter': None}, {'drop': None}]
    rows = {'input': [deny6, allow(True), deny],
            'forward': [deny6, allow(False, True), allow(True, True), deny],
            'output': [deny6, allow(False), deny]}
    if web is not None:
        checked_web(web)
        for chain in rows: rows[chain][-1:-1] = web_rule_expr(chain, web)
    return rows


def checked_policy(text, web=None):
    data = exact_json(text)
    require(isinstance(data, dict) and set(data) == {'nftables'}
            and isinstance(data['nftables'], list), 'policy_json_shape')
    table = None; chains = {}; rules = {'input': [], 'forward': [], 'output': []}
    for entry in data['nftables']:
        require(isinstance(entry, dict) and len(entry) == 1, 'policy_object_shape')
        kind, obj = next(iter(entry.items()))
        if kind == 'metainfo': continue
        require(kind in {'table', 'chain', 'rule'} and isinstance(obj, dict), 'unexpected_policy_object')
        obj = dict(obj)
        if 'handle' in obj:
            require(type(obj['handle']) is int and obj['handle'] > 0, 'invalid_policy_handle')
            del obj['handle']
        if kind == 'table':
            require(table is None and obj == {'family': 'inet', 'name': 'frw_a0_local'}, 'policy_table_changed')
            table = obj
        elif kind == 'chain':
            name = obj.get('name')
            require(name in rules and name not in chains and obj == {
                'family': 'inet', 'table': 'frw_a0_local', 'name': name,
                'type': 'filter', 'hook': name, 'prio': -10, 'policy': 'drop'}, 'policy_chain_changed')
            chains[name] = obj
        else:
            name = obj.get('chain')
            require(set(obj) == {'family', 'table', 'chain', 'expr'}
                    and obj['family'] == 'inet' and obj['table'] == 'frw_a0_local'
                    and name in rules and isinstance(obj['expr'], list), 'policy_rule_changed')
            normalized = []
            for expression in obj['expr']:
                if isinstance(expression, dict) and set(expression) == {'counter'}:
                    counter = expression['counter']
                    require(isinstance(counter, dict) and set(counter) == {'packets', 'bytes'}
                            and all(type(v) is int and v >= 0 for v in counter.values()), 'policy_counter_changed')
                    normalized.append({'counter': None})
                else:
                    # Anonymous sets are mathematical sets, not ordered lists.
                    if isinstance(expression, dict) and set(expression) == {'match'}:
                        expression = exact_json(canonical(expression))
                        right = expression['match'].get('right')
                        if expression['match'].get('left') == {'ct': {'key': 'state'}}:
                            require(expression['match'].get('op') == 'in', 'policy_ct_operator_changed')
                            values = (right if isinstance(right, list) else
                                      right['set'] if isinstance(right, dict) and set(right) == {'set'} else [right])
                            require(all(isinstance(v, str) for v in values)
                                    and len(values) == len(set(values)), 'policy_ct_mask_changed')
                            expression['match']['right'] = [v for v in ('new', 'established') if v in values]
                            require(set(values).issubset({'new', 'established'}), 'policy_ct_mask_changed')
                        if isinstance(right, dict) and set(right) == {'set'}:
                            values = right['set']
                            require(isinstance(values, list) and len(values) == len({canonical(v) for v in values}), 'policy_duplicate_set_value')
                            if set(map(canonical, values)) == {'8001', '8002'}: right['set'] = [8001, 8002]
                    normalized.append(expression)
            rules[name].append(normalized)
    require(table is not None and set(chains) == set(rules)
            and rules == expected_rules(web), 'policy_semantics_changed')
    return policy_hash(web)


def checked_request(value, now=None):
    keys = {'schema', 'owner', 'nonce', 'accepted_unix', 'deadline_unix', 'original_budget_seconds', 'accepted_monotonic_ns',
            'launcher_sha256', 'policy_sha256', 'tools', 'endpoints'}
    require(isinstance(value, dict) and set(value) in (keys, keys | {'web'})
            and value['schema'] == 'friday.a0.local-route-request.v1', 'route_request_shape')
    require(isinstance(value['owner'], str) and re.fullmatch(r'(astra|sol):[A-Za-z0-9][A-Za-z0-9._-]{0,95}#[1-9][0-9]*', value['owner'])
            and re.fullmatch(r'[0-9a-f]{32}', value['nonce']), 'route_owner_changed')
    now = time.time() if now is None else now
    times = [value['accepted_unix'], value['deadline_unix'], now]
    require(all(type(x) in (float, int) and 0 < x < float('inf') for x in times)
            and type(value['original_budget_seconds']) is int
            and 30 <= value['original_budget_seconds'] <= 1800
            and value['deadline_unix'] - value['accepted_unix'] == value['original_budget_seconds']
            and value['accepted_unix'] <= now < value['deadline_unix'] - 25, 'route_budget_changed')
    require(type(value['accepted_monotonic_ns']) is int and value['accepted_monotonic_ns'] > 0
            and value['accepted_monotonic_ns'] <= time.monotonic_ns()
            < value['accepted_monotonic_ns'] + (value['original_budget_seconds'] - 25)*10**9, 'route_monotonic_budget_changed')
    if 'web' in value: checked_web(value['web'])
    require(value['endpoints'] == ENDPOINTS and value['policy_sha256'] == policy_hash(value.get('web')), 'route_policy_changed')
    require(re.fullmatch(r'[0-9a-f]{64}', value['launcher_sha256'])
            and isinstance(value['tools'], dict) and set(value['tools']) == {'dockerd', 'rootlesskit', 'slirp4netns', 'nft', 'nsenter'}
            and all(re.fullmatch(r'[0-9a-f]{64}', x) for x in value['tools'].values()), 'route_source_pins')
    return value


def tool_paths():
    return {'dockerd': ROOT.parent / 'docker-29.8.2/docker/dockerd',
            'rootlesskit': Path('/usr/bin/rootlesskit'), 'slirp4netns': Path('/usr/bin/slirp4netns'),
            'nft': NFT, 'nsenter': NSENTER}


def request_checked(uid):
    request = checked_request(private_json(REQUEST, uid))
    require(hashlib.sha256(stable_bytes(ROOT / 'launch.py', uid)).hexdigest() == request['launcher_sha256'], 'route_launcher_changed')
    for key, p in tool_paths().items():
        require(p.resolve() == p and stat.S_ISREG(p.lstat().st_mode)
                and not p.lstat().st_mode & 0o022 and p.lstat().st_mode & 0o111
                and hashlib.sha256(p.read_bytes()).hexdigest() == request['tools'][key], 'route_tool_changed')
    return request


def proc_identity(pid):
    require(type(pid) is int and pid > 0, 'invalid_route_pid')
    p = Path('/proc', str(pid)); st = (p / 'stat').read_text()
    fields = st[st.rfind(')') + 2:].split()
    return {'pid': pid, 'start': fields[19], 'ppid': int(fields[1]),
            'cgroup': (p / 'cgroup').read_text().strip(),
            'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


@contextmanager
def namespaces(pid):
    fds = {}
    try:
        for name in ('user', 'mnt', 'net'):
            fds[name] = os.open('/proc/' + str(pid) + '/ns/' + name, os.O_RDONLY | os.O_CLOEXEC)
        identity = {k: [os.fstat(fd).st_dev, os.fstat(fd).st_ino] for k, fd in fds.items()}
        for name in ('mnt', 'net'):
            owner = fcntl.ioctl(fds[name], NS_GET_USERNS)
            try: require([os.fstat(owner).st_dev, os.fstat(owner).st_ino] == identity['user'], 'foreign_namespace_owner')
            finally: os.close(owner)
        yield identity, fds
    finally:
        for fd in fds.values(): os.close(fd)


def native_call(argv, *, data=None, fds=(), timeout=5):
    require(type(timeout) in (int, float) and 0 < timeout <= 5, 'route_probe_budget_invalid')
    try:
        r = subprocess.run(argv, input=data, capture_output=True, text=True, timeout=timeout,
                           env={'PATH': '/usr/bin:/usr/sbin', 'LC_ALL': 'C', 'HOME': '/home/jericho',
                                'XDG_RUNTIME_DIR': '/run/user/1000',
                                'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus'}, pass_fds=fds, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('route_native_check_failed') from None
    require(r.returncode == 0 and len(r.stdout.encode()) <= 1024*1024, 'route_native_check_failed')
    return r.stdout


def unit_identity(*, timeout=None):
    raw = native_call(['/usr/bin/systemctl', '--user', 'show', 'friday-rework-docker.service',
                       '--property=InvocationID,MainPID,ControlGroup,DropInPaths,Restart'],
                      **({} if timeout is None else {'timeout': timeout}))
    fields = dict(x.split('=', 1) for x in raw.splitlines())
    require(set(fields) == {'InvocationID', 'MainPID', 'ControlGroup', 'DropInPaths', 'Restart'}
            and re.fullmatch(r'[0-9a-f]{32}', fields['InvocationID'])
            and fields['ControlGroup'] == SERVICE_GROUP and fields['Restart'] == 'no'
            and fields['DropInPaths'] == '' and fields['MainPID'].isdecimal(), 'route_native_owner_changed')
    return {'invocation_id': fields['InvocationID'], 'parent_pid': int(fields['MainPID'])}


def parent_route(request, env):
    require(not GUARD.exists(), 'prior_guard_blocks_restart')
    STATE.mkdir(mode=0o700, exist_ok=True); owned_directory(STATE)
    require(not (STATE / 'rootlesskit/child_pid').exists(), 'prior_namespace_blocks_restart')
    unit = unit_identity(); require(unit['parent_pid'] == os.getpid(), 'foreign_route_mainpid')
    me = proc_identity(os.getpid())
    with namespaces(os.getpid()) as (ns, _):
        # On the host the net/mount namespaces are owned by the initial userns.
        for name in ('user', 'net'):
            require(ns[name][1] == Path('/proc/1/ns/' + name).stat().st_ino, 'parent_not_host_namespace')
        context = {'parent': me, 'host_namespaces': ns, **unit,
                   'state_identity': [STATE.stat().st_dev, STATE.stat().st_ino],
                   'request_sha256': hashlib.sha256(stable_bytes(REQUEST, UID)).hexdigest()}
    env.update({'DOCKERD_ROOTLESS_ROOTLESSKIT_DETACH_NETNS': 'false',
                'DOCKERD_ROOTLESS_ROOTLESSKIT_DISABLE_HOST_LOOPBACK': 'true',
                'DOCKERD': str(ROOT / 'launch.py'), 'FRW_A0_ROUTE': canonical(context)})


def child_identity(context):
    require(os.getuid() == 0 and os.geteuid() == 0 and context['parent']['pid'] == context['parent_pid'], 'wrong_route_child_uid')
    parent = proc_identity(context['parent_pid'])
    require(parent == context['parent'] and parent['cgroup'] == '0::' + SERVICE_GROUP + '/dockerd', 'route_parent_reused')
    require(Path('/proc', str(parent['pid']), 'exe').resolve() == tool_paths()['rootlesskit'], 'route_parent_executable')
    current = proc_identity(os.getpid())
    require(current['boot'] == parent['boot'] and current['cgroup'] == parent['cgroup'], 'foreign_route_child_cgroup')
    ancestor = current
    for _ in range(16):
        if ancestor['pid'] == parent['pid']: break
        ancestor = proc_identity(ancestor['ppid'])
    require(ancestor == parent, 'foreign_route_child_lineage')
    mappings = {}
    for kind in ('uid', 'gid'):
        rows = [list(map(int, line.split())) for line in Path('/proc/self/' + kind + '_map').read_text().splitlines()]
        require(len(rows) == 2 and rows[0] == [0, UID, 1]
                and rows[1][0] == 1 and rows[1][1] > UID and rows[1][2] >= 65536, 'route_mapping_changed')
        mappings[kind] = rows
    return current, mappings


def write_guard(value):
    # RootlessKit's supported /run copy-up may alias an ancestor. Bind the
    # held leaf directory to the parent's exact inode instead of trusting it.
    directory = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        st = os.fstat(directory)
        require([st.st_dev, st.st_ino] == value['context']['state_identity']
                and st.st_uid == 0 and not st.st_mode & 0o022, 'route_state_owner_changed')
        fd = os.open('route-guard.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            b = (canonical(value) + '\n').encode()
            require(os.write(fd, b) == len(b), 'route_guard_short_write'); os.fsync(fd)
        finally: os.close(fd)
        os.fsync(directory)
    finally: os.close(directory)


def child_route():
    require(sys.argv[1:] == ['--config-file=' + str(ROOT / 'config/daemon.json')]
            and os.environ.get('_DOCKERD_ROOTLESS_CHILD') == '1'
            and os.environ.get('DOCKERD_ROOTLESS_ROOTLESSKIT_DETACH_NETNS') == 'false'
            and os.environ.get('DOCKERD_ROOTLESS_ROOTLESSKIT_NET') == 'slirp4netns'
            and os.environ.get('DOCKERD_ROOTLESS_ROOTLESSKIT_PORT_DRIVER') == 'builtin'
            and os.environ.get('DOCKERD') == str(ROOT / 'launch.py'), 'route_child_arguments_changed')
    request = request_checked(0); context = exact_json(os.environ['FRW_A0_ROUTE'])
    require(context['request_sha256'] == hashlib.sha256(stable_bytes(REQUEST, 0)).hexdigest(), 'route_request_changed_after_parent')
    for p, pin in [(ROOT / 'config/daemon.json', CONFIG_SHA256),
                   (ROOT / 'supervisor/friday-rework-docker.service', UNIT_SHA256),
                   (ROOT.parent / 'docker-29.8.2/docker-rootless-extras/dockerd-rootless.sh', SCRIPT_SHA256)]:
        require(hashlib.sha256(stable_bytes(p, 0)).hexdigest() == pin, 'route_native_source_changed')
    current, mappings = child_identity(context)
    with namespaces(os.getpid()) as (ns, _):
        require(all(ns[k] != context['host_namespaces'][k] for k in ns), 'host_or_detached_route_namespace')
        interfaces = {x.split(':', 1)[0].strip() for x in Path('/proc/net/dev').read_text().splitlines()[2:]}
        require(interfaces == {'lo', 'tap0'} and not GUARD.exists(), 'route_interface_or_prior_state')
        existing = exact_json(native_call([str(NFT), '--json', 'list', 'ruleset']))
        require(set(existing) == {'nftables'} and all(set(x) == {'metainfo'} for x in existing['nftables']), 'conflicting_namespace_policy')
        native_call([str(NFT), '--check', '--file', '-'], data=policy(request.get('web')))
        native_call([str(NFT), '--file', '-'], data=policy(request.get('web')))
        checked_policy(native_call([str(NFT), '--json', '--numeric-priority', 'list', 'table', 'inet', 'frw_a0_local']), request.get('web'))
        require(child_identity(context) == (current, mappings), 'route_identity_changed_before_exec')
        require(request_checked(0) == request, 'route_source_changed_before_exec')
        receipt = {'schema': 'friday.a0.local-route-guard.v1', 'request': request,
                   'context': context, 'daemon': current, 'namespaces': ns, 'mappings': mappings,
                   'policy_sha256': policy_hash(request.get('web')), 'status': 'GUARDED_BEFORE_DOCKERD'}
        write_guard(receipt)
        fd = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            leaf = os.open('route-guard.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            try: require(exact_json(os.read(leaf, 1024*1024).decode()) == receipt, 'route_receipt_not_retained')
            finally: os.close(leaf)
        finally: os.close(fd)
    # Fixed executable and args only. No arbitrary child command forwarding.
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'DOCKER_CONFIG') if k in os.environ}
    if os.environ.get('NOTIFY_SOCKET'): env['NOTIFY_SOCKET'] = os.environ['NOTIFY_SOCKET']
    env.update({'ROOTLESSKIT_STATE_DIR': '/run/user/1000/friday-rework-docker/rootlesskit'})
    binary = tool_paths()['dockerd']
    os.execve(str(binary), [str(binary), '--config-file=' + str(ROOT / 'config/daemon.json')], env)


def observe_guard(descriptor, *, budget=None):
    """Bounded current check through held FDs, never enter host/foreign namespaces."""
    # The producer supplies its original clock; no new probe budget is minted.
    def unit_now():
        return unit_identity() if budget is None else unit_identity(timeout=min(5, budget()))
    request = request_checked(UID); unit = unit_now()
    require(descriptor.get('web') == request.get('web'), 'guard_web_permission_changed')
    receipt = private_json(GUARD, UID)
    require(receipt['schema'] == 'friday.a0.local-route-guard.v1'
            and receipt['status'] == 'GUARDED_BEFORE_DOCKERD'
            and receipt['request'] == request and receipt['policy_sha256'] == policy_hash(request.get('web'))
            and receipt['context']['request_sha256'] == hashlib.sha256(stable_bytes(REQUEST, UID)).hexdigest()
            and hashlib.sha256(stable_bytes(GUARD, UID)).hexdigest() == descriptor['guard_receipt_sha256'], 'guard_receipt_changed')
    require(unit == {k: receipt['context'][k] for k in ('invocation_id', 'parent_pid')}
            and unit['invocation_id'] == descriptor['invocation_id']
            and request['owner'] == descriptor['owner'] and request['nonce'] == descriptor['nonce']
            and descriptor['request_sha256'] == receipt['context']['request_sha256']
            and descriptor['launcher_sha256'] == request['launcher_sha256']
            and descriptor['policy_sha256'] == policy_hash(request.get('web')), 'guard_binding_changed')
    daemon = receipt['daemon']; parent = receipt['context']['parent']
    # ppid may change only by daemonizing; this configuration forbids that.
    require(proc_identity(daemon['pid']) == daemon and proc_identity(parent['pid']) == parent
            and Path('/proc', str(daemon['pid']), 'exe').resolve() == tool_paths()['dockerd'], 'guard_process_reused')
    with namespaces(daemon['pid']) as (ns, fds):
        require(ns == receipt['namespaces'] == descriptor['namespaces']
                and all(ns[k] != receipt['context']['host_namespaces'][k] for k in ns), 'guard_namespace_changed')
        argv = [str(NSENTER), '--no-fork', '--setuid=0', '--setgid=0',
                *['--' + {'mnt': 'mount'}.get(k, k) + '=/proc/self/fd/' + str(fds[k]) for k in ('user', 'mnt', 'net')],
                '--', str(NFT), '--json', '--numeric-priority', 'list', 'table', 'inet', 'frw_a0_local']
        call_limits = {} if budget is None else {'timeout': min(5, budget())}
        checked_policy(native_call(argv, fds=tuple(fds.values()), **call_limits), request.get('web'))
        # Held FDs preserve the inspected namespace, not the daemon's current
        # membership. Reopen through /proc after readback before admitting it.
        with namespaces(daemon['pid']) as (current_ns, _):
            require(current_ns == ns == receipt['namespaces'] == descriptor['namespaces'],
                    'guard_namespace_changed_during_readback')
            require(proc_identity(daemon['pid']) == daemon and proc_identity(parent['pid']) == parent
                    and Path('/proc', str(daemon['pid']), 'exe').resolve() == tool_paths()['dockerd']
                    and unit_now() == unit and request_checked(UID) == request
                    and hashlib.sha256(stable_bytes(GUARD, UID)).hexdigest() == descriptor['guard_receipt_sha256'],
                    'guard_drift_during_readback')
    return {'status': 'CURRENT_GUARD_CHECKED', 'nonce': request['nonce'], 'policy_sha256': policy_hash(request.get('web'))}


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def owned_directory(path):
    s = path.lstat()
    require(path.resolve() == path and stat.S_ISDIR(s.st_mode)
            and s.st_uid == UID and not s.st_mode & 0o022, 'delegation_directory_changed')


def read_file(path):
    # Never follow a substituted leaf, including the writable delegation file.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'delegation_file_changed')
        with os.fdopen(fd, 'r', closefd=False) as f:
            return f.read().strip()
    finally:
        os.close(fd)


def checked_source(path, expected):
    require(path.resolve() == path, 'launch_input_symlink')
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_uid == UID and not s.st_mode & 0o022,
            'launch_input_owner_or_mode_changed')
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'launch_input_pin_changed')


def checked_unit_registration():
    """Accept only the exact existing native registration or a pinned regular unit."""
    target = ROOT / 'supervisor/friday-rework-docker.service'
    # Both paths are fixed code-owned locations. Check every owner directory
    # through their common boundary, including the boundary itself.
    boundary = Path(os.path.commonpath((ROOT, INSTALLED_UNIT.parent)))
    require(boundary != Path('/'), 'unit_registration_boundary_changed')
    for directory in (target.parent, INSTALLED_UNIT.parent):
        while True:
            owned_directory(directory)
            if directory == boundary:
                break
            require(directory.is_relative_to(boundary), 'unit_registration_boundary_changed')
            directory = directory.parent
    checked_source(target, UNIT_SHA256)
    st = INSTALLED_UNIT.lstat()
    if stat.S_ISLNK(st.st_mode):
        require(st.st_uid == UID and os.readlink(INSTALLED_UNIT) == str(target)
                and INSTALLED_UNIT.resolve() == target,
                'unit_registration_changed')
    else:
        checked_source(INSTALLED_UNIT, UNIT_SHA256)


def checked_native_service_limits():
    """A pinned file cannot prove the user manager reloaded its finite limits."""
    names = ('RuntimeMaxUSec', 'TimeoutStartUSec', 'TimeoutStopUSec', 'Restart',
             'KillMode', 'SendSIGKILL', 'DelegateSubgroup', 'MemoryMax', 'TasksMax',
             'CPUQuotaPerSecUSec', 'DropInPaths', 'MainPID', 'InvocationID', 'ControlGroup')
    raw = native_call(['/usr/bin/systemctl', '--user', 'show', 'friday-rework-docker.service',
                       '--property=' + ','.join(names)])
    pairs = [line.split('=', 1) for line in raw.splitlines()]
    fields = dict(pairs)
    require(len(pairs) == len(fields) and set(fields) == set(names), 'launch_native_limits_unknown')
    expected = {'Restart': 'no', 'KillMode': 'control-group', 'SendSIGKILL': 'yes',
                'DelegateSubgroup': 'dockerd', 'MemoryMax': str(20 * 1024**3),
                'TasksMax': '2048', 'CPUQuotaPerSecUSec': '8s', 'DropInPaths': '',
                'MainPID': str(os.getpid()), 'ControlGroup': SERVICE_GROUP}
    require(all(fields[k] == v for k, v in expected.items())
            and re.fullmatch(r'[0-9a-f]{32}', fields['InvocationID']), 'launch_native_boundary_changed')
    scales = {'us': 1e-6, 'ms': .001, 's': 1, 'min': 60, 'h': 3600}
    for name, seconds in zip(names[:3], (120, 45, 20)):
        value = fields[name]
        require(re.fullmatch(r'(?:[0-9]+(?:\.[0-9]+)?(?:us|ms|s|min|h) ?)+', value),
                'launch_finite_native_deadline_required')
        actual = sum(float(n) * scales[u] for n, u in
                     re.findall(r'([0-9]+(?:\.[0-9]+)?)(us|ms|min|s|h)', value))
        require(actual == seconds, 'launch_finite_native_deadline_changed')
    return fields


def prepare_memory():
    """One bounded pre-exec check/write. A failed postcondition prevents exec."""
    require(os.getuid() == UID and os.geteuid() == UID, 'wrong_launch_uid')
    require(read_file(SELF_CGROUP) == '0::' + SERVICE_GROUP + '/dockerd', 'wrong_self_cgroup')
    parent = CGROUP_ROOT / SERVICE_GROUP.lstrip('/')
    child = parent / 'dockerd'
    owned_directory(parent); owned_directory(child)
    require(read_file(parent / 'cgroup.type') == 'domain'
            and read_file(child / 'cgroup.type') == 'domain', 'wrong_delegation_type')
    require(not read_file(parent / 'cgroup.procs'), 'delegated_parent_has_processes')
    require(read_file(child / 'cgroup.procs').split() == [str(os.getpid())], 'foreign_dockerd_processes')
    require('memory' in read_file(parent / 'cgroup.controllers').split(), 'memory_not_delegated')
    # These are observations of unchanged service limits, never writes.
    q, period = read_file(parent / 'cpu.max').split()
    require(read_file(parent / 'memory.max') == str(20 * 1024**3)
            and read_file(parent / 'pids.max') == '2048'
            and q != 'max' and int(period) > 0 and int(q) == 8 * int(period),
            'outer_service_limits_changed')
    control = parent / 'cgroup.subtree_control'
    fd = os.open(control, os.O_RDWR | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == UID and s.st_mode & 0o200
                and not s.st_mode & 0o022, 'delegation_control_not_owned_writable')
        before = set(os.read(fd, 4096).decode().split())
        if 'memory' not in before:
            # Recheck ownership context immediately before the sole write.
            require(read_file(SELF_CGROUP) == '0::' + SERVICE_GROUP + '/dockerd'
                    and not read_file(parent / 'cgroup.procs'), 'delegation_changed_before_write')
            os.lseek(fd, 0, os.SEEK_SET)
            require(os.write(fd, b'+memory') == len(b'+memory'), 'short_delegation_write')
        os.lseek(fd, 0, os.SEEK_SET)
        after = set(os.read(fd, 4096).decode().split())
        require(after == before | {'memory'}, 'memory_enable_not_confirmed')
        for name in ('memory.max', 'memory.swap.max'):
            value = read_file(child / name)
            require(value == 'max' or (value.isdecimal() and int(value) >= 0),
                    'child_memory_interface_invalid')
        require(read_file(SELF_CGROUP) == '0::' + SERVICE_GROUP + '/dockerd'
                and not read_file(parent / 'cgroup.procs'), 'delegation_changed_after_write')
    finally:
        os.close(fd)


def main():
    require(Path(__file__).absolute() == ROOT / 'launch.py'
            and Path(__file__).resolve() == ROOT / 'launch.py', 'not_installed_private_launcher')
    if os.environ.get('_DOCKERD_ROOTLESS_CHILD') == '1':
        return child_route()
    require(sys.argv[1:] == [], 'unexpected_launcher_arguments')
    owned_directory(ROOT)
    runtime = ROOT.parent
    binary = runtime / 'docker-29.8.2'
    script = binary / 'docker-rootless-extras/dockerd-rootless.sh'
    checked_unit_registration()
    checked_native_service_limits()
    checked_source(ROOT / 'config/daemon.json', CONFIG_SHA256)
    checked_source(script, SCRIPT_SHA256)
    request = request_checked(UID) if REQUEST.exists() or REQUEST.is_symlink() else None
    prepare_memory()
    # Original launcher command/environment; only the pre-exec check is added.
    env = {'PATH': '/usr/bin:/usr/sbin:' + str(binary / 'docker'),
           'HOME': '/home/jericho', 'XDG_RUNTIME_DIR': '/run/user/1000',
           'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus',
           'DOCKER_CONFIG': str(runtime / 'docker-client'),
           'DOCKERD_ROOTLESS_ROOTLESSKIT_STATE_DIR': '/run/user/1000/friday-rework-docker/rootlesskit',
           'DOCKERD_ROOTLESS_ROOTLESSKIT_NET': 'slirp4netns',
           'DOCKERD_ROOTLESS_ROOTLESSKIT_PORT_DRIVER': 'builtin'}
    if os.environ.get('NOTIFY_SOCKET'):
        env['NOTIFY_SOCKET'] = os.environ['NOTIFY_SOCKET']
    if request is not None:
        parent_route(request, env)
    os.execve(str(script), [str(script), '--config-file=' + str(ROOT / 'config/daemon.json')], env)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No retry, fallback, sudo or permission relaxation.
        print('rootless_launch_preflight_failed:' + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None
