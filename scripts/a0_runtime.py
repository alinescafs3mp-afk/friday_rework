"""Dedicated intact A0 container through existing Docker/user-systemd only.

Preparation is offline. Live operations require an exact reviewed plan and a
separate current Astra CONTROL; the CLI hash is an integrity check, not permission.
No API message submission, model calls, daemon start, retry, pull or image removal.
"""
from __future__ import annotations

import argparse
import configparser
from contextlib import contextmanager
import fcntl
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import subprocess
import sys
import tempfile
import time

PROJECT = Path('/home/jericho/jericho/Friday_rework')
RUNTIME = PROJECT / '.runtime/a0-runtime-sol'
DOCKER = PROJECT / '.runtime/docker-29.8.2/docker/docker'
SOCKET = 'unix:///run/user/1000/friday-rework-docker/docker.sock'
LAUNCHER = PROJECT / '.runtime/rootless-docker/launch.py'
LOCAL_ENDPOINTS = [{'ip': '192.168.1.78', 'port': 8001, 'transport': 'tcp'},
                   {'ip': '192.168.1.78', 'port': 8002, 'transport': 'tcp'}]
DAEMON = 'friday-rework-docker.service'
IMAGE = 'sha256:6b300a0a4341632f021fb1b5d2641296ff4882ba7636e228f57c58bc9105c4f8'
DONOR = 'e3051fb584b1a36be2b0a0c90606f1c2c2d356ec'
DONOR_TREE = 'f7bfedfa472b9d1bc28a88caf8be08d17daf8813'
DONOR_DESCRIBE = 'e3051fb'
MEMORY = 2 * 1024**3
PIDS = 256
STARTUP_SECONDS = 120
STOP_SECONDS = 2
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/home/jericho', 'LC_ALL': 'C',
       'XDG_RUNTIME_DIR': '/run/user/1000',
       'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus',
       'DOCKER_CONFIG': str(PROJECT / '.runtime/docker-client')}
START_SCRIPT = ('umask 077; . /ins/setup_venv.sh; . /ins/copy_A0.sh; '
                'mkdir -p /a0/usr/uploads; cd /a0; '
                'exec python run_ui.py --dockerized=true --host=127.0.0.1 --port=5000')
INVENTORY_SCRIPT = '''import importlib.metadata as m,json,platform,sys
print(json.dumps({"python":sys.version,"executable":sys.executable,
 "platform":platform.platform(),"distributions":sorted(
 [{"name":d.metadata["Name"],"version":d.version} for d in m.distributions()],
 key=lambda x:(x["name"].lower(),x["version"]))}))'''
INVENTORY_COMMAND = '; '.join(shlex.join([python, '-B', '-c', INVENTORY_SCRIPT])
                             for python in ['/opt/venv-a0/bin/python', '/opt/venv/bin/python'])
HEALTH_SCRIPT = '''import json,urllib.request
try:
 with urllib.request.urlopen("http://127.0.0.1:5000/api/health",timeout=3) as r:
  data=json.load(r)
 print(json.dumps({"http":200,"gitinfo_present":bool(data.get("gitinfo")),
  "native_error_present":bool(data.get("error"))}))
except Exception:
 print(json.dumps({"http":None,"status":"NOT_READY"}))
 raise SystemExit(1)'''
# Read effective native token within the container; never return or log it.
AUTH_SCRIPT = '''import json,urllib.request,urllib.error
from helpers import dotenv,settings,runtime
runtime.initialize();dotenv.load_dotenv()
url="http://127.0.0.1:5000/api/api_log_get?context_id=frw-nonexistent&length=1"
for label,key in [("wrong","frw-invalid-key"),("native",settings.create_auth_token())]:
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={"X-API-KEY":key}),timeout=3) as r:
   status=r.status
 except urllib.error.HTTPError as e: status=e.code
 except Exception: status=None
 print(json.dumps({"key_kind":label,"http":status}))'''


class RuntimeErrorBoundary(RuntimeError):
    """Categorical errors only; captured native error text is never printed."""


def require(ok, code):
    if not ok:
        raise RuntimeErrorBoundary(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def private(path, *, directory=False):
    p = Path(path)
    require(p.is_absolute() and p.resolve() == p, 'unsafe_private_path')
    s = p.lstat()
    require(s.st_uid == os.getuid() and (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode))
            and stat.S_IMODE(s.st_mode) in ({0o700} if directory else {0o400, 0o600}),
            'private_identity_or_mode')
    return p


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, value, *, replace=False):
    """Atomic, private, fsynced native receipt; no task/queue store."""
    path = Path(path)
    private(path.parent, directory=True)
    fd, name = tempfile.mkstemp(prefix='.receipt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, sort_keys=True, indent=2)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        if replace:
            private(path)
            os.replace(name, path)
        else:
            os.link(name, path)
        sync_dir(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def templates():
    # Actual plugin preset collection schema, never legacy flat model settings.
    chat = {'provider': 'openai', 'name': 'dispatcher',
            'api_base': 'http://192.168.1.78:8001/v1', 'ctx_length': 40960,
            'ctx_history': 0.7, 'vision': False, 'rl_requests': 0,
            'rl_input': 0, 'rl_output': 0,
            'kwargs': {'max_tokens': 4096, 'timeout': 60, 'a0_api_mode': 'chat'}}
    utility = dict(chat, ctx_input=0.7)
    utility.pop('ctx_history')
    return {'plugins/_model_config/presets.yaml':
            [{'name': 'Default', 'chat': chat, 'utility': utility,
              'embedding': {'provider': 'other', 'name': 'qwen3-embedding-0.6b',
                            'api_base': 'http://192.168.1.78:8002/v1',
                            'kwargs': {'timeout': 30}, 'rl_requests': 0, 'rl_input': 0}}],
            'plugins/_model_config/config.json': {'model_preset': 'Default'},
            'plugins/_code_execution/config.json': {'ssh_enabled': 'false'},
            'settings.json': {'agent_profile': 'agent0', 'workdir_path': '/a0/usr/workdir',
                              'uvicorn_access_logs_enabled': False}}


def metadata_descriptor(value):
    """Only a new owned standalone clone; never a donor or worktree pointer."""
    require(isinstance(value, dict) and set(value) == {'source', 'manifest_sha256'}
            and isinstance(value['source'], str)
            and re.fullmatch(r'[0-9a-f]{64}', value.get('manifest_sha256', '')),
            'invalid_git_metadata_pin')
    p = Path(value['source'])
    root = RUNTIME / 'git-metadata'
    require(p.is_absolute() and len(p.parts) == len(root.parts) + 3
            and p.parent.parent.parent == root and p.name == '.git'
            and p.parent.name == 'repo'
            and re.fullmatch(r'[0-9a-f]{64}', p.parent.parent.name)
            and not any(c in str(p) for c in ',\n\r'), 'foreign_git_metadata_path')
    return p


def git_metadata_snapshot(source):
    """Read-only proof of authentic objects and a self-contained clone.

    Parent stages/reviews the clone separately. This function never clones,
    fetches, edits configuration or manufactures history. Files are all pinned;
    later admission refuses any drift. Stop uses the recorded mount identity.
    """
    source = metadata_descriptor({'source': str(source), 'manifest_sha256': '0' * 64})
    for p in (RUNTIME, RUNTIME / 'git-metadata', source.parent.parent, source.parent):
        private(p, directory=True)
    require(source.is_dir() and source.resolve() == source, 'git_metadata_pointer_or_missing')
    records = {}; total = 0
    for base, dirs, names in os.walk(source, followlinks=False):
        for name in dirs + names:
            p = Path(base) / name; s = p.lstat(); rel = p.relative_to(source).as_posix()
            require(s.st_uid == os.getuid() and not s.st_mode & 0o022
                    and (stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode))
                    and not p.is_symlink(), 'unsafe_git_metadata_file')
            require(name not in {'gitdir', 'commondir', 'alternates', 'http-alternates', 'grafts'}
                    and not rel.startswith('refs/replace/'), 'external_git_metadata_reference')
            if stat.S_ISREG(s.st_mode):
                require(not rel.startswith('refs/'), 'git_metadata_refs_changed')
                total += s.st_size
                require(s.st_nlink == 1 and total <= 512 * 1024**2 and len(records) < 4096,
                        'git_metadata_sharing_or_size')
                records[rel] = {'sha256': sha(p), 'size': s.st_size}
    require(source.lstat().st_uid == os.getuid() and not source.lstat().st_mode & 0o022,
            'unsafe_git_metadata_file')
    require((source / 'HEAD').read_text() == DONOR + '\n' and 'index' in records
            and 'config' in records, 'git_metadata_head_or_index_changed')
    require('shallow' in records and (source / 'shallow').read_text() == DONOR + '\n',
            'git_metadata_shallow_changed')
    # Reject include/external-command configuration BEFORE invoking Git. A
    # normal owned clone has only these four local core settings after origin
    # removal; no host/global configuration is copied or inherited.
    local = configparser.ConfigParser(interpolation=None, strict=True)
    local.read_string((source / 'config').read_text())
    require(local.sections() == ['core'] and not local.defaults()
            and set(local['core']) == {'repositoryformatversion', 'filemode', 'bare', 'logallrefupdates'},
            'git_metadata_config_changed')
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_OPTIONAL_LOCKS': '0'}
    def git(*args):
        r = subprocess.run(['/usr/bin/git', '--no-optional-locks', '--git-dir=' + str(source),
                            '--work-tree=' + str(source.parent), '-c', 'core.fsmonitor=false',
                            '-c', 'core.hooksPath=/dev/null', *args], env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        require(r.returncode == 0, 'git_metadata_objects_invalid')
        if args[0] == 'for-each-ref':
            require(not r.stderr, 'git_metadata_refs_changed')
        return r.stdout
    config = dict(item.split('\n', 1) for item in git('config', '--local', '--null', '--list').split('\0') if item)
    require(set(config) == {'core.repositoryformatversion', 'core.filemode', 'core.bare', 'core.logallrefupdates'}
            and config['core.repositoryformatversion'] == '0' and config['core.bare'] == 'false'
            and config['core.logallrefupdates'] == 'true' and config['core.filemode'] in {'true', 'false'},
            'git_metadata_config_changed')
    # The authentic pinned donor is detached/shallow with NO refs. Enumerate
    # packed and loose refs before interpreting objects with ordinary Git
    # replacement semantics (the native reader does not disable replacements).
    require(git('for-each-ref', '--format=%(refname)') == '', 'git_metadata_refs_changed')
    require(git('rev-parse', '--is-shallow-repository').strip() == 'true',
            'git_metadata_shallow_changed')
    require(git('describe', '--tags', '--always').strip() == DONOR_DESCRIBE,
            'git_metadata_describe_changed')
    require(git('rev-parse', '--verify', 'HEAD^{commit}').strip() == DONOR
            and git('rev-parse', '--verify', 'HEAD^{tree}').strip() == DONOR_TREE,
            'git_metadata_object_identity_changed')
    # Compare stage-zero path/mode/object entries directly, without write-tree
    # (which may write objects/index). NUL records preserve unusual filenames.
    entries = []; paths = []
    for row in git('ls-tree', '-r', '--full-tree', '-z', DONOR_TREE).split('\0')[:-1]:
        header, path = row.split('\t', 1)
        mode, kind, oid = header.split(' ')
        entries.append(f'{mode} {oid} 0\t{path}\0'); paths.append(path)
    require(git('ls-files', '--stage', '-z') == ''.join(entries), 'git_metadata_index_changed')
    # Flags such as assume-valid, skip-worktree and intent-to-add can mask
    # differences from native readers even when mode/object entries agree.
    debug = git('ls-files', '--debug', '-z'); offset = 0
    stats = re.compile(r'  ctime: [0-9]+:[0-9]+\n  mtime: [0-9]+:[0-9]+\n'
                       r'  dev: [0-9]+\tino: [0-9]+\n  uid: [0-9]+\tgid: [0-9]+\n'
                       r'  size: [0-9]+\tflags: 0\n')
    for path in paths:
        prefix = path + '\0'
        require(debug.startswith(prefix, offset), 'git_metadata_index_flags_changed')
        match = stats.match(debug, offset + len(prefix))
        require(match is not None, 'git_metadata_index_flags_changed')
        offset = match.end()
    require(offset == len(debug), 'git_metadata_index_flags_changed')
    git('fsck', '--full', '--no-reflogs')
    # Git reads must leave every observed file intact (including the index).
    require(all(sha(source / n) == r['sha256'] for n, r in records.items()), 'git_metadata_read_drift')
    return {'donor': DONOR, 'tree': DONOR_TREE, 'files': records}


def check_git_metadata(value):
    source = metadata_descriptor(value)
    manifest = private(source.parent.parent / 'metadata.json')
    data = manifest.read_bytes()
    require(hashlib.sha256(data).hexdigest() == value['manifest_sha256'], 'git_metadata_manifest_changed')
    require(json.loads(data) == git_metadata_snapshot(source), 'git_metadata_manifest_mismatch')


def probe_config_checked(cfg, configured, expected):
    """Check the resolved startup scope, including unexpected override fields."""
    require(isinstance(cfg, dict) and configured == 'Default' and cfg.get('model_preset') == 'Default'
            and set(cfg) <= {'model_preset', 'allow_chat_override', 'vision_model',
                            'chat_model', 'utility_model', 'embedding_model'}
            and cfg.get('vision_model', {}) == {}, 'native_preset_or_override_changed')
    for slot in ('chat', 'utility', 'embedding'):
        require(cfg.get(slot + '_model') == expected[slot], 'native_slot_changed')


def native_probe():
    """Finite no-model startup inspection; only allowlisted facts are returned."""
    from contextlib import redirect_stdout, redirect_stderr
    # Native imports/hooks/errors may print; their output is never exported.
    with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
        base = Path('/a0/usr')
        expected = templates()
        for name, value in expected.items():
            p = base / name
            require(p.is_file() and p.resolve() == p and json.loads(p.read_text()) == value,
                    'native_input_missing_or_changed')
        from helpers import plugins, providers
        from plugins._model_config.helpers import model_config
        import models
        selected = plugins.find_plugin_asset('_model_config', 'config.json',
                                             project_name='', agent_profile='agent0')
        require(selected and Path(selected['path']).resolve() == base / 'plugins/_model_config/config.json',
                'native_scope_override_changed')
        cfg = model_config.get_config(agent_profile='agent0', project_name=None)
        configured = model_config.get_configured_preset_name(agent_profile='agent0', project_name=None)
        preset = expected['plugins/_model_config/presets.yaml'][0]
        probe_config_checked(cfg, configured, preset)
        slots = {}
        for slot in ('chat', 'utility', 'embedding'):
            typ = models.ModelType.EMBEDDING if slot == 'embedding' else models.ModelType.CHAT
            mc = model_config.build_model_config(cfg[slot + '_model'], typ)
            want = preset[slot]
            require(mc.provider == want['provider'] and mc.name == want['name']
                    and mc.api_base == want['api_base'] and not mc.api_key
                    and mc.ctx_length == want.get('ctx_length', 0) and mc.vision is False
                    and mc.limit_requests == mc.limit_input == mc.limit_output == 0
                    and mc.kwargs == want['kwargs'], 'native_constructed_slot_changed')
            provider = providers.get_provider_config('embedding' if slot == 'embedding' else 'chat', mc.provider)
            require(provider and provider.get('litellm_provider') == 'openai'
                    and provider.get('kwargs', {}) == ({} if slot == 'embedding' else {'a0_api_mode': 'chat'}),
                    'native_provider_mapping_changed')
            slots[slot] = {'provider': mc.provider, 'transport_provider': 'openai', 'name': mc.name,
                           'api_base': mc.api_base, 'ctx_length': mc.ctx_length,
                           'max_tokens': mc.kwargs.get('max_tokens'), 'timeout': mc.kwargs['timeout'],
                           'api_mode': mc.kwargs.get('a0_api_mode')}
        keys = {}
        for provider in ('openai', 'other'):
            key = models.get_api_key(provider)
            keys[provider] = isinstance(key, str) and bool(key.strip()) and key.strip() not in {'None', 'NA'}
        require(all(keys.values()), 'native_distinct_key_not_ready')
        try:
            from helpers import tokens
            text = 'Friday native token probe. Привет, Дест.'
            count = tokens.count_tokens(text)
            approx = tokens.approximate_tokens(text)
            require(type(count) is int and 0 < count < 256 and approx == int(count * 1.1), 'native_token_counter_changed')
        except RuntimeErrorBoundary:
            raise
        except Exception:
            raise RuntimeErrorBoundary('native_token_cache_unavailable') from None
    return {'status': 'NO_MODEL_STARTUP_PROBE_PASS', 'scope': 'agent0/no-project/no-context',
            'configured_preset': 'Default', 'selected_preset': 'Default', 'slots': slots,
            'key_ready': keys, 'tokens': {'encoding': 'cl100k_base', 'count': count, 'approximate': approx},
            'temporary_test': True, 'hard_total_prompt_bound': False}


def probe_script():
    # Same tested functions; no parallel implementation of native resolution.
    parts = ['import json,os\nfrom pathlib import Path\n']
    parts += [inspect.getsource(x) for x in (RuntimeErrorBoundary, require, templates, probe_config_checked, native_probe)]
    parts.append("try:\n print(json.dumps(native_probe(),sort_keys=True))\nexcept Exception as exc:\n print(json.dumps({'status':'REFUSED','code':str(exc) if isinstance(exc,RuntimeErrorBoundary) else 'native_probe_failed'}))\n")
    return '\n'.join(parts)


def probe_report_checked(data):
    require(isinstance(data, dict) and set(data) == {'status', 'scope', 'configured_preset',
            'selected_preset', 'slots', 'key_ready', 'tokens', 'temporary_test', 'hard_total_prompt_bound'}
            and data['status'] == 'NO_MODEL_STARTUP_PROBE_PASS'
            and data['scope'] == 'agent0/no-project/no-context'
            and data['configured_preset'] == data['selected_preset'] == 'Default'
            and data['temporary_test'] is True and data['hard_total_prompt_bound'] is False
            and data['key_ready'] == {'openai': True, 'other': True}
            and all(type(x) is bool for x in data['key_ready'].values()), 'native_probe_report_changed')
    expected = {}
    for slot in ('chat', 'utility', 'embedding'):
        cfg = templates()['plugins/_model_config/presets.yaml'][0][slot]
        expected[slot] = {'provider': cfg['provider'], 'transport_provider': 'openai', 'name': cfg['name'],
                          'api_base': cfg['api_base'], 'ctx_length': cfg.get('ctx_length', 0),
                          'max_tokens': cfg['kwargs'].get('max_tokens'), 'timeout': cfg['kwargs']['timeout'],
                          'api_mode': cfg['kwargs'].get('a0_api_mode')}
    require(data['slots'] == expected, 'native_probe_report_changed')
    t = data['tokens']
    require(isinstance(t, dict) and set(t) == {'encoding', 'count', 'approximate'}
            and t['encoding'] == 'cl100k_base' and type(t['count']) is int and 0 < t['count'] < 256
            and type(t['approximate']) is int and t['approximate'] == int(t['count'] * 1.1),
            'native_probe_report_changed')
    return data


def local_network(value, owner):
    """A previously created bridge and fresh guarded namespace, never permission."""
    keys = {'schema', 'name', 'id', 'owner', 'nonce', 'labels', 'bridge', 'endpoints',
            'launcher_sha256', 'policy_sha256', 'request_sha256', 'guard_receipt_sha256',
            'invocation_id', 'namespaces'}
    require(isinstance(value, dict) and set(value) == keys
            and value['schema'] == 'friday.a0.local-network.v1'
            and value['owner'] == owner
            and isinstance(value['nonce'], str) and re.fullmatch(r'[0-9a-f]{32}', value['nonce'])
            and value['name'] == 'frw-a0-local-' + value['nonce'][:12]
            and value['bridge'] == 'br-frwa0local' and value['endpoints'] == LOCAL_ENDPOINTS
            and value['labels'] == {'friday.rework.owner': owner, 'friday.rework.route': value['nonce']},
            'invalid_local_network')
    require(all(isinstance(value[k], str) and re.fullmatch(r'[0-9a-f]{64}', value[k])
                for k in ('id', 'launcher_sha256', 'policy_sha256', 'request_sha256', 'guard_receipt_sha256'))
            and isinstance(value['invocation_id'], str) and re.fullmatch(r'[0-9a-f]{32}', value['invocation_id']),
            'invalid_local_network_pins')
    ns = value['namespaces']
    require(isinstance(ns, dict) and set(ns) == {'user', 'mnt', 'net'}
            and all(isinstance(x, list) and len(x) == 2 and all(type(y) is int and y > 0 for y in x)
                    for x in ns.values()), 'invalid_local_network_namespace')
    return json.loads(json.dumps(value))


def network_checked(value, obj, *, container_id=None):
    require(isinstance(obj, dict) and obj.get('Id') == value['id'] and obj.get('Name') == value['name']
            and obj.get('Driver') == 'bridge' and obj.get('Scope') == 'local'
            and obj.get('EnableIPv6') is False and obj.get('Internal') is False
            and obj.get('Attachable') is False and obj.get('Ingress') is False
            and obj.get('ConfigOnly') is False and obj.get('Labels') == value['labels']
            and obj.get('Options') == {'com.docker.network.bridge.name': value['bridge'],
                                      'com.docker.network.bridge.enable_icc': 'false'}, 'local_network_identity_changed')
    members = obj.get('Containers')
    require(isinstance(members, dict) and set(members).issubset({container_id} if container_id else set()),
            'foreign_local_network_member')
    for member in members.values():
        require(isinstance(member, dict) and re.fullmatch(r'[0-9a-f]{64}', member.get('EndpointID', '')),
                'local_endpoint_unknown')
    return obj


def plan(accepted_unix, deadline_unix, *, assignment, generation, owner_slot,
         original_budget_seconds, mode='runtime', pins=None, git_metadata=None, network=None,
         association_binding=None, accepted_monotonic_ns=None, boot_id=None):
    """Create operator input, never a launch grant or implicit continuation.

    The private reviewed plan retains the original independent phase identity
    and time bounds. No identity or budget is inferred from historical tasks.
    """
    require(mode in {'runtime', 'inventory'}, 'invalid_mode')
    require(isinstance(assignment, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}', assignment)
            and type(generation) is int and generation > 0
            and isinstance(owner_slot, str) and owner_slot in {'astra', 'sol'}, 'invalid_phase_identity')
    require(type(original_budget_seconds) is int and 30 <= original_budget_seconds <= 1800,
            'invalid_phase_budget')
    require(all(type(x) in (int, float) and math.isfinite(x) for x in [accepted_unix, deadline_unix])
            and accepted_unix > 0 and deadline_unix - accepted_unix == original_budget_seconds,
            'original_budget_mismatch')
    owner = f'{owner_slot}:{assignment}#{generation}'
    identity_input = {'owner': owner, 'assignment': assignment, 'generation': generation,
                      'accepted_unix': accepted_unix, 'mode': mode}
    if association_binding is not None:
        binding = host_identity(association_binding)
        require(mode == 'runtime' and generation == 1 and assignment == binding['existing_task_id']
                and accepted_unix == binding['created_at_unix']
                and deadline_unix == binding['deadline_unix']
                and original_budget_seconds == binding['budget_seconds'], 'foreign_host_plan')
        require(type(accepted_monotonic_ns) is int and accepted_monotonic_ns > 0
                and isinstance(boot_id, str) and re.fullmatch('[0-9a-f-]{36}', boot_id),
                'original_host_clock_missing')
        identity_input.update(association_binding=binding,
                              accepted_monotonic_ns=accepted_monotonic_ns, boot_id=boot_id)
    else:
        require(accepted_monotonic_ns is None and boot_id is None, 'unbound_host_clock')
    if network is not None:
        require(mode == 'runtime', 'inventory_local_network_refused')
        network = local_network(network, owner)
        identity_input['local_network'] = network
    if git_metadata is not None:
        require(mode == 'runtime', 'inventory_git_mount_refused')
        metadata_descriptor(git_metadata)
        identity_input['git_metadata'] = dict(git_metadata)
    identity = digest(identity_input)
    if pins is None:
        pins = {'code_sha256': sha(__file__), 'docker_sha256': sha(DOCKER),
                'daemon_unit_sha256': sha(PROJECT / '.runtime/rootless-docker/supervisor/friday-rework-docker.service')}
    require(set(pins) == {'code_sha256', 'docker_sha256', 'daemon_unit_sha256'}
            and all(isinstance(x, str) and re.fullmatch(r'[0-9a-f]{64}', x) for x in pins.values()),
            'invalid_pins')
    result = {'schema': 'friday.a0.runtime-plan.v2', 'assignment': assignment,
            'generation': generation, 'owner_slot': owner_slot, 'owner': owner, 'identity': identity,
            'image': IMAGE, 'donor': DONOR, 'mode': mode,
            'runtime_root': str(RUNTIME), 'state_dir': str(RUNTIME / identity / 'usr'),
            'unit': 'friday-rework-worker-' + identity[:32] + '.service',
            'container_name': 'frw-a0-' + identity[:32],
            'accepted_unix': accepted_unix, 'deadline_unix': deadline_unix,
            'original_budget_seconds': original_budget_seconds,
            'network': 'none' if network is None else network, 'ports': [],
            'memory_bytes': MEMORY, 'cpus': 2, 'pids': PIDS,
            'startup_seconds': STARTUP_SECONDS, 'stop_seconds': STOP_SECONDS,
            'templates_sha256': digest(templates()), **pins,
            **({'git_metadata': dict(git_metadata)} if git_metadata is not None else {})}
    if association_binding is not None:
        result.update(association_binding=binding, accepted_monotonic_ns=accepted_monotonic_ns,
                      boot_id=boot_id, unit=binding['supervisor']['unit'],
                      container_name='frw-a0-' + assignment[7:39])
    return result


def host_identity(value):
    fields = {'existing_task_id', 'admission_hash', 'owner', 'worker_kind', 'brief_sha256',
              'workspace_reference', 'supervisor', 'created_at_unix', 'budget_seconds', 'deadline_unix'}
    require(isinstance(value, dict) and set(value) == fields
            and re.fullmatch('native-[0-9a-f]{64}', value['existing_task_id'])
            and value['worker_kind'] == 'a0'
            and all(re.fullmatch('[0-9a-f]{64}', value[x]) for x in ('admission_hash', 'brief_sha256'))
            and value['admission_hash'] == hashlib.sha256(value['existing_task_id'].encode()).hexdigest()
            and value['supervisor'] == {'scope': 'user', 'unit': 'friday-rework-worker-' + value['existing_task_id'][7:39] + '.service'}
            and isinstance(value['owner'], dict)
            and set(value['owner']) == {'bot_id', 'user_id', 'chat_id', 'thread_id', 'message_id', 'session_key', 'session_id', 'profile'}
            and all(isinstance(x, str) and len(x) <= 512 and '\x00' not in x for x in value['owner'].values())
            and isinstance(value['workspace_reference'], str)
            and Path(value['workspace_reference']).is_absolute()
            and '..' not in Path(value['workspace_reference']).parts, 'invalid_host_identity')
    return json.loads(json.dumps(value, allow_nan=False))


def validate(p, *, check_files=True):
    pins = None if check_files else {k: p[k] for k in ['code_sha256', 'docker_sha256', 'daemon_unit_sha256']}
    expected = plan(p['accepted_unix'], p['deadline_unix'], assignment=p['assignment'],
                    generation=p['generation'], owner_slot=p['owner_slot'],
                    original_budget_seconds=p['original_budget_seconds'], mode=p['mode'], pins=pins,
                    git_metadata=p.get('git_metadata'),
                    network=None if p['network'] == 'none' else p['network'],
                    association_binding=p.get('association_binding'),
                    accepted_monotonic_ns=p.get('accepted_monotonic_ns'), boot_id=p.get('boot_id'))
    require(p == expected, 'plan_identity_or_boundary_changed')
    if check_files and 'git_metadata' in p:
        check_git_metadata(p['git_metadata'])
    return p


def remaining(p, now=None):
    now = time.time() if now is None else now
    # Never grant extra time on clock rollback, or reset the accepted budget.
    require(math.isfinite(now) and now >= p['accepted_unix'], 'clock_rollback')
    value = p['deadline_unix'] - now - 25  # native container + cleanup reserve
    if 'association_binding' in p:
        require(p['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'host_boot_changed')
        elapsed = (time.monotonic_ns() - p['accepted_monotonic_ns']) / 1e9
        require(elapsed >= 0, 'host_monotonic_rollback')
        value = min(value, p['original_budget_seconds'] - elapsed - 25)
    require(value >= 5, 'budget_exhausted')
    return int(value)


def labels(p):
    return {'friday.rework.owner': p['owner'], 'friday.rework.assignment': p['assignment'],
            'friday.rework.generation': str(p['generation']),
            'friday.rework.plan': p.get('association_binding', {}).get('admission_hash', digest(p))}


def create_argv(p):
    validate(p)
    args = [str(DOCKER), '--host', SOCKET, 'create', '--name', p['container_name'],
            '--pull=never', '--network=' + ('none' if p['network'] == 'none' else p['network']['id']), '--restart=no', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--pids-limit=' + str(PIDS),
            '--memory=' + str(MEMORY), '--memory-swap=' + str(MEMORY), '--cpus=2',
            '--stop-timeout=' + str(STOP_SECONDS), '--ulimit=nofile=65535:65535',
            '--log-driver=none']
    for k, v in labels(p).items():
        args += ['--label', k + '=' + v]
    if p['mode'] == 'inventory':
        return args + ['--read-only', '--entrypoint=/bin/bash', IMAGE, '-ceu', INVENTORY_COMMAND]
    args += ['--mount', 'type=bind,src=' + p['state_dir'] + ',dst=/a0/usr']
    if 'git_metadata' in p:
        args += ['--mount', 'type=bind,src=' + p['git_metadata']['source'] + ',dst=/a0/.git,readonly,bind-propagation=rprivate']
    return args + [
                   '--env=HF_HUB_OFFLINE=1', '--env=TRANSFORMERS_OFFLINE=1',
                   '--workdir=/a0', '--entrypoint=/bin/bash', IMAGE, '-ceu', START_SCRIPT]


def container_checked(p, obj, cid=None, *, stop_owned=False):
    """Validate exact owner/ID/exposure; resource drift cannot block owned stop.

    Launch/observation still require exact resource limits. Only the checked
    same container stop path may omit mutable resource admission limits.
    """
    require(isinstance(obj, dict) and re.fullmatch(r'[0-9a-f]{64}', obj.get('Id', '')),
            'invalid_container_id')
    require(cid is None or obj['Id'] == cid, 'container_replaced')
    actual_labels = obj['Config'].get('Labels') or {}
    require(obj.get('Name') == '/' + p['container_name'] and obj.get('Image') == IMAGE
            and obj['Config'].get('Image') == IMAGE
            and {k: v for k, v in actual_labels.items() if k.startswith('friday.rework.')} == labels(p),
            'container_owner_or_image_changed')
    h = obj['HostConfig']
    state = obj['State']
    require(type(state.get('Running')) is bool and type(state.get('Pid')) is int
            and state['Pid'] >= 0 and (state['Running'] or state['Pid'] == 0),
            'inconsistent_container_state')
    require(h.get('NetworkMode') == ('none' if p['network'] == 'none' else p['network']['id']) and not h.get('Privileged')
            and not h.get('PortBindings') and not h.get('PublishAllPorts')
            and not h.get('Binds') and not h.get('Devices') and not h.get('DeviceRequests')
            and h.get('PidMode', '') == '' and h.get('IpcMode') in {'private', ''}
            and h.get('RestartPolicy') == {'Name': 'no', 'MaximumRetryCount': 0}
            and h.get('CapDrop') == ['ALL'] and not h.get('CapAdd')
            and h.get('SecurityOpt') == ['no-new-privileges'],
            'container_boundary_changed')
    if p['network'] != 'none' and not stop_owned:
        networks = obj.get('NetworkSettings', {}).get('Networks')
        value = p['network']
        require(isinstance(networks, dict) and set(networks) == {value['name']}
                and networks[value['name']].get('NetworkID') == value['id'], 'container_network_changed')
        # No injected proxy, DNS override or implicit cloud transport.
        env = obj['Config'].get('Env')
        require(isinstance(env, list) and all(isinstance(x, str) for x in env)
                and not any(x.partition('=')[0].lower() in {
                    'http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy', 'no_proxy'} for x in env)
                and not h.get('Dns') and not h.get('DnsOptions') and not h.get('DnsSearch')
                and not h.get('ExtraHosts') and not h.get('Links'), 'local_transport_override_changed')
    if p['mode'] == 'inventory':
        require(h.get('ReadonlyRootfs') is True and obj.get('Mounts') == []
                and obj['Config'].get('Entrypoint') == ['/bin/bash']
                and obj['Config'].get('Cmd') == ['-ceu', INVENTORY_COMMAND], 'inventory_boundary_changed')
    else:
        mounts = obj.get('Mounts')
        require(h.get('ReadonlyRootfs') is False and isinstance(mounts, list)
                and len(mounts) == (2 if 'git_metadata' in p else 1),
                'runtime_mounts_changed')
        by_dest = {m.get('Destination'): m for m in mounts}
        require(len(by_dest) == len(mounts) and '/a0/usr' in by_dest, 'runtime_mounts_changed')
        m = by_dest['/a0/usr']
        require(m.get('Type') == 'bind' and m.get('Source') == p['state_dir']
                and m.get('Destination') == '/a0/usr' and m.get('RW') is True
                and m.get('Propagation') == 'rprivate', 'runtime_mounts_changed')
        if 'git_metadata' in p:
            m = by_dest.get('/a0/.git', {})
            require(m.get('Type') == 'bind' and m.get('Source') == p['git_metadata']['source']
                    and m.get('Destination') == '/a0/.git' and m.get('RW') is False
                    and m.get('Propagation') == 'rprivate', 'git_mount_identity_changed')
        require(obj['Config'].get('Entrypoint') == ['/bin/bash']
                and obj['Config'].get('Cmd') == ['-ceu', START_SCRIPT]
                and obj['Config'].get('WorkingDir') == '/a0', 'runtime_command_changed')
    if not stop_owned:
        require(h.get('Memory') == MEMORY and h.get('MemorySwap') == MEMORY
                and h.get('NanoCpus') == 2_000_000_000 and h.get('PidsLimit') == PIDS,
                'container_resource_boundary_changed')
    return obj


def process_identity(pid):
    try:
        s = Path('/proc', str(pid), 'stat').read_text()
        fields = s[s.rfind(')') + 2:].split()
        return {'pid': pid, 'start_ticks': int(fields[19]), 'state': fields[0]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def cgroup_snapshot(group):
    root = Path('/sys/fs/cgroup') / group.lstrip('/')
    require(group.startswith('/') and root.resolve() == root, 'invalid_cgroup')
    if not root.exists():
        return {'group': group, 'populated': False, 'processes': []}
    events = dict(x.split() for x in (root / 'cgroup.events').read_text().splitlines())
    require(events.get('populated') in {'0', '1'}, 'unknown_cgroup_state')
    ids = set()
    for f in root.rglob('cgroup.procs'):
        try:
            ids.update(map(int, f.read_text().split()))
        except FileNotFoundError:
            pass
    return {'group': group, 'populated': events['populated'] == '1',
            'processes': [x for pid in sorted(ids) if (x := process_identity(pid))]}


def cessation(before):
    survivors = []
    for x in before['processes']:
        current = process_identity(x['pid'])
        if current and current['start_ticks'] == x['start_ticks'] and current['state'] != 'Z':
            survivors.append(current)
    after = cgroup_snapshot(before['group'])
    return {'confirmed': not survivors and after['populated'] is False, 'before': before,
            'survivors': survivors, 'after': after}


def native_supervisor():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from plugins.friday_rework.supervision import NativeSupervisor
    return NativeSupervisor()


class Runtime:
    """Single native boundary wrapper; no scheduler, daemon or message replay."""
    def __init__(self, p, *, runner=None, supervisor=None, stopping=False):
        self.p = validate(p, check_files=not stopping)
        # A corrected host wrapper may stop an old reviewed plan, but an
        # unverified executable must never receive an effectful control call.
        require(sha(DOCKER) == p['docker_sha256'], 'docker_binary_changed')
        self.runner = runner or self._command
        self.supervisor = supervisor or native_supervisor()
        self.directory = RUNTIME / p['identity']
        self.receipt_path = self.directory / 'native.json'
        self.known = None
        self.create_attempted = False

    @staticmethod
    def _command(argv, timeout=10):
        try:
            r = subprocess.run(argv, env=ENV, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise RuntimeErrorBoundary('native_control_uncertain') from e
        require(r.returncode == 0, 'native_command_failed')
        return r.stdout

    def docker(self, *args, timeout=10):
        return self.runner([str(DOCKER), '--host', SOCKET, *args], timeout)

    @contextmanager
    def locked(self):
        # This is not a writer-lock bypass; a busy runtime refuses immediately.
        private(RUNTIME, directory=True)
        fd = os.open(RUNTIME / 'runtime.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            s = os.fstat(fd)
            require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid()
                    and stat.S_IMODE(s.st_mode) == 0o600, 'unsafe_runtime_lock')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def receipt(self):
        r = self.known
        if r is None:
            r = json.loads(private(self.receipt_path).read_text())
        require(r.get('plan_sha256') == digest(self.p), 'receipt_plan_changed')
        require(re.fullmatch(r'[0-9a-f]{64}', r.get('container_id', '')), 'receipt_container_unknown')
        self.known = r
        return r

    def association(self, r):
        a = {'supervisor': {'scope': 'user', 'unit': self.p['unit']},
             'admission_hash': self.p.get('association_binding', {}).get('admission_hash', digest(self.p))}
        if r.get('invocation_id'):
            a['native'] = {'invocation_id': r['invocation_id'], 'worker_reference': r['container_id']}
        return a

    def inspect(self, r, *, stop_owned=False, timeout=10):
        xs = json.loads(self.docker('inspect', r['container_id'], timeout=timeout))
        require(isinstance(xs, list) and len(xs) == 1, 'container_observation_unknown')
        obj = container_checked(self.p, xs[0], r['container_id'], stop_owned=stop_owned)
        if not stop_owned:
            self.check_network(container_id=r['container_id'])
        return obj

    def check_network(self, *, container_id=None):
        if self.p['network'] == 'none': return None
        n = self.p['network']; local_network(n, self.p['owner'])
        # Load only exact reviewed bytes, no import-path fallback or helper service.
        before = LAUNCHER.lstat()
        require(LAUNCHER.resolve() == LAUNCHER and stat.S_ISREG(before.st_mode)
                and before.st_uid == os.getuid() and before.st_nlink == 1
                and not before.st_mode & 0o022 and before.st_size <= 128*1024, 'local_launcher_identity_changed')
        fd = os.open(LAUNCHER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            source = os.read(fd, 128*1024 + 1)
            after = os.fstat(fd); named = LAUNCHER.lstat()
            key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode)
            require(key(before) == key(after) == key(named)
                    and hashlib.sha256(source).hexdigest() == n['launcher_sha256'], 'local_launcher_pin_changed')
        finally: os.close(fd)
        namespace = {'__file__': str(LAUNCHER), '__name__': 'frw_checked_local_launcher'}
        exec(compile(source, str(LAUNCHER), 'exec'), namespace)
        # Current native unit, live PID-start/boot, owned held namespace FDs and
        # nft semantic readback are all checked here; a boolean is insufficient.
        namespace['observe_guard'](n)
        request = namespace['request_checked'](os.getuid())
        require(request['accepted_unix'] == self.p['accepted_unix']
                and request['deadline_unix'] == self.p['deadline_unix']
                and request['original_budget_seconds'] == self.p['original_budget_seconds'], 'local_original_budget_changed')
        if 'association_binding' in self.p:
            require(request['owner'] == self.p['owner']
                    and request['accepted_monotonic_ns'] == self.p['accepted_monotonic_ns']
                    and self.p['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                    'foreign_host_route_clock')
        xs = json.loads(self.docker('network', 'inspect', n['id']))
        require(isinstance(xs, list) and len(xs) == 1, 'local_network_unknown')
        network_checked(n, xs[0], container_id=container_id)
        return {'status': 'CURRENT_LOCAL_NETWORK_CHECKED', 'id': n['id']}

    def unit_argv(self, cid, plan_path, plan_file_sha):
        seconds = min(remaining(self.p), STARTUP_SECONDS)
        require(re.fullmatch(r'[0-9a-f]{64}', cid), 'invalid_container_id')
        # Native timeout cleanup uses the immutable, already checked actual ID.
        # It must not depend on a receipt write/read, current plan expiry or a
        # concurrent observer's file lock. Docker IDs cannot be reassigned.
        cleanup = shlex.join([str(DOCKER), '--host', SOCKET, 'stop', '--time', str(STOP_SECONDS), cid])
        props = ['Description=Friday rework ' + self.association({})['admission_hash'], 'Restart=no',
                 'RuntimeMaxSec=' + str(seconds) + 's', 'TimeoutStartSec=10s',
                 'TimeoutStopSec=20s', 'KillMode=control-group', 'SendSIGKILL=yes',
                 'UMask=0077', 'MemoryMax=256M', 'CPUQuota=100%', 'TasksMax=64',
                 'ExecStopPost=' + cleanup, 'StandardError=null',
                 ('StandardOutput=append:' + str(self.directory / 'inventory.jsonl')
                  if self.p['mode'] == 'inventory' else 'StandardOutput=null')]
        if self.p['mode'] == 'inventory':
            props.append('RemainAfterExit=yes')
        return ['/usr/bin/systemd-run', '--user', '--unit=' + self.p['unit'],
                '--service-type=exec', '--expand-environment=no',
                *['--property=' + x for x in props], str(DOCKER), '--host', SOCKET,
                'start', '--attach', cid]

    def start(self, plan_path, plan_file_sha, *, before_ui=None, on_created=None):
        try:
            return self._start_locked(plan_path, plan_file_sha, before_ui=before_ui, on_created=on_created)
        except BaseException as original:
            if self.known is not None:
                try:
                    # The inner receipt lock has been released before stopping
                    # the actual native unit; no nested writer or lock bypass.
                    self.supervisor.stop(self.association(self.known))
                except BaseException:
                    original.add_note('STOP_UNCONFIRMED; native unit cleanup not confirmed')
            raise

    def _start_locked(self, plan_path, plan_file_sha, *, before_ui=None, on_created=None):
        require('association_binding' in self.p or before_ui is None and on_created is None,
                'unbound_host_hook')
        require('association_binding' not in self.p or callable(before_ui) and callable(on_created),
                'host_pre_ui_hook_required')
        # Daemon start is deliberately outside this wrapper; current CONTROL
        # must first authorize and inspect the existing dedicated daemon.
        with self.locked():
            reviewed = private(plan_path)
            require(sha(reviewed) == plan_file_sha
                    and json.loads(reviewed.read_text()) == self.p, 'reviewed_plan_changed')
            validate(self.p); remaining(self.p)
            require(not self.directory.exists(), 'prior_or_uncertain_attempt_blocks_restart')
            daemon = self.runner(['/usr/bin/systemctl', '--user', 'show', DAEMON,
                                  '--property=ActiveState,DelegateSubgroup,MemoryMax,TasksMax,CPUQuotaPerSecUSec,Restart,KillMode,SendSIGKILL,DropInPaths'], 5)
            fields = dict(x.split('=', 1) for x in daemon.splitlines())
            require(fields == {'ActiveState': 'active', 'DelegateSubgroup': 'dockerd',
                               'MemoryMax': str(20 * 1024**3), 'TasksMax': '2048',
                               'CPUQuotaPerSecUSec': '8s', 'Restart': 'no',
                               'KillMode': 'control-group', 'SendSIGKILL': 'yes',
                               'DropInPaths': ''}, 'dedicated_daemon_not_ready')
            info = json.loads(self.docker('info', '--format={{json .}}'))
            require(info.get('CgroupVersion') == '2' and info.get('CgroupDriver') == 'systemd'
                    and 'name=rootless' in info.get('SecurityOptions', [])
                    and info.get('ServerVersion') == '29.8.2', 'native_docker_boundary_unsupported')
            require(all(info.get(k) is True for k in ['MemoryLimit', 'SwapLimit', 'CpuCfsPeriod', 'CpuCfsQuota', 'PidsLimit']),
                    'native_docker_resource_limits_unsupported')
            require(not self.docker('ps', '-q').strip(), 'active_container_blocks_admission')
            # Any prior native object with this exact name blocks replacement.
            require(not self.docker('ps', '-aq', '--filter', 'name=^/' + self.p['container_name'] + '$').strip(),
                    'existing_container_blocks_admission')
            self.check_network()
            self.directory.mkdir(mode=0o700)
            write_json(self.directory / 'attempt.json', {'plan_sha256': digest(self.p), 'phase': 'CREATE_UNKNOWN'})
            if self.p['mode'] == 'runtime':
                materialize(self.directory / 'usr')
                if before_ui is not None:
                    before_ui(self.directory / 'usr')
                    remaining(self.p)
            try:
                self.create_attempted = True
                cid = self.runner(create_argv(self.p), 10).strip()
                require(re.fullmatch(r'[0-9a-f]{64}', cid), 'create_outcome_unknown')
                self.known = {'plan_sha256': digest(self.p), 'container_id': cid,
                              'invocation_id': '', 'observations': []}
                if on_created is not None:
                    on_created(self.known)
                self.inspect(self.known)
                write_json(self.receipt_path, self.known)
                self.runner(self.unit_argv(cid, plan_path, plan_file_sha), 10)
                obs = self.supervisor.observe(self.association(self.known))
                require(not obs.missing and obs.invocation_id, 'unit_submission_unknown')
                self.known['invocation_id'] = obs.invocation_id
                write_json(self.receipt_path, self.known, replace=True)
                return {'status': 'STARTED_NATIVE_BOUNDARY', 'container_id': cid,
                        'invocation_id': obs.invocation_id, 'health': 'NOT_RUN'}
            except BaseException as original:
                # An uncertain create/start is never replayed. Reconcile only
                # this plan's exact named, labelled image object, then stop.
                try:
                    if self.known is None:
                        xs = json.loads(self.docker('inspect', self.p['container_name']))
                        require(len(xs) == 1, 'create_outcome_unknown')
                        obj = container_checked(self.p, xs[0], stop_owned=True)
                        self.known = {'plan_sha256': digest(self.p), 'container_id': obj['Id'],
                                      'invocation_id': '', 'observations': []}
                    self._stop(self.known)
                except BaseException:
                    original.add_note('STOP_UNCONFIRMED; exact native attempt retained; no replay')
                raise

    def observe(self):
        checked = None
        try:
            with self.locked():
                r = self.receipt(); obj = self.inspect(r, stop_owned=True)
                unit = self.supervisor.observe(self.association(r))
                if not r.get('invocation_id') and unit.invocation_id:
                    r['invocation_id'] = unit.invocation_id
                checked = r
                self.check_network(container_id=r['container_id'])
                container_checked(self.p, obj, r['container_id'])
                state = obj['State']
                sample = {'unit_quiescent': unit.quiescent, 'running': state['Running'],
                          'pid': state['Pid'], 'exit_code': state['ExitCode'], 'cgroup': None}
                if state['Running']:
                    snapshot = self.snapshot_container(obj)
                    # Retain this observation in checked memory before caps or
                    # receipt I/O can fail; cleanup must not reread bad storage.
                    r['observations'].append(snapshot)
                    group = snapshot['group']
                    cg = Path('/sys/fs/cgroup') / group.lstrip('/')
                    caps = {n: (cg / n).read_text().strip()
                            for n in ['memory.max', 'memory.swap.max', 'cpu.max', 'pids.max']}
                    q, period = caps['cpu.max'].split()
                    require(caps['memory.max'] == str(MEMORY) and caps['memory.swap.max'] == '0'
                            and caps['pids.max'] == str(PIDS)
                            and q != 'max' and int(q) == 2 * int(period), 'container_actual_caps_changed')
                    sample['cgroup'] = snapshot; sample['caps'] = caps
                    self.known = r
                    write_json(self.receipt_path, r, replace=True)
                return sample
        except BaseException as original:
            if checked is not None:
                self.failure_cleanup(checked, original)
            raise

    def failure_cleanup(self, checked, original):
        """Only after container AND native ownership checks, outside file lock.

        Always attempt both independent boundaries. NativeSupervisor rechecks
        invocation/owner immediately before stop; no foreign/replaced fallback.
        Receipt/cgroup failure cannot prevent requesting native stop.
        """
        try:
            self.supervisor.stop(self.association(checked))
        except BaseException as error:
            original.add_note('STOP_UNCONFIRMED; native cleanup: ' + type(error).__name__)
        try:
            with self.locked():
                self._stop(checked)
        except BaseException as error:
            original.add_note('STOP_UNCONFIRMED; container/cgroup/receipt cleanup: ' + type(error).__name__)

    def snapshot_container(self, obj):
        pid = obj['State']['Pid']
        require(type(pid) is int and pid > 0, 'container_pid_unknown')
        line = Path('/proc', str(pid), 'cgroup').read_text().strip()
        require(line.startswith('0::/') and '\n' not in line, 'container_cgroup_unknown')
        group = line[3:]
        # systemd's rootless Docker scope can be a sibling of the daemon
        # service; assert exact container scope and its own limits, never
        # falsely claim inheritance from the daemon's 20 GiB/8 CPU bound.
        require(group.endswith('/docker-' + obj['Id'] + '.scope'), 'container_cgroup_identity_changed')
        snapshot = cgroup_snapshot(group)
        require(snapshot['populated'] and snapshot['processes'], 'container_descendants_unknown')
        return snapshot

    def _stop(self, r):
        obj = self.inspect(r, stop_owned=True)
        initial = None
        sampling_error = None
        if obj['State']['Running']:
            try:
                r['observations'].append(self.snapshot_container(obj))
            except BaseException as e:
                sampling_error = e
        # Stop intent storage never precedes required stop on a failure path.
        try:
            if obj['State']['Running']:
                self.docker('stop', '--time', str(STOP_SECONDS), r['container_id'], timeout=8)
        except BaseException as e:
            initial = e
        try:
            after = self.inspect(r, stop_owned=True)
            checks = [cessation(x) for x in r.get('observations', [])]
            stopped = after['State']['Running'] is False and after['State']['Pid'] == 0
            require(stopped and all(x['confirmed'] for x in checks), 'STOP_UNCONFIRMED')
        except BaseException as error:
            if initial is not None:
                initial.add_note('STOP_UNCONFIRMED; post-stop reconciliation: ' + type(error).__name__)
                raise initial
            raise
        if initial:
            raise initial
        result = {'status': 'STOP_CONFIRMED', 'container_id': r['container_id'],
                'descendant_checks': checks,
                'pid_start_sampling': 'RETAINED' if checks else 'NOT_RETAINED',
                'current_sampling': 'UNKNOWN' if sampling_error else 'OBSERVED_OR_ALREADY_EXITED',
                'native_container_stopped': True}
        output = self.directory / 'stop.json'
        write_json(output, result, replace=output.exists())
        return result

    def stop(self, *, from_stop_post=False):
        checked = None
        try:
            with self.locked():
                r = self.receipt()
                self.inspect(r, stop_owned=True)
                unit = self.supervisor.observe(self.association(r))
                if not r.get('invocation_id') and unit.invocation_id:
                    r['invocation_id'] = unit.invocation_id
                checked = r
                result = self._stop(r)
        except BaseException as original:
            if checked is not None:
                self.failure_cleanup(checked, original)
            raise
        # Native stop is attempted once; uncertainty must not replay it.
        # Directory/attempt tombstone forbids replacement while stopping.
        if not from_stop_post:
            self.supervisor.stop(self.association(r))
        return result

    def health(self, *, auth=False):
        try:
            return self._health(auth=auth)
        except BaseException as original:
            if self.p['network'] != 'none' and self.known is not None:
                # Outside the receipt lock. Both existing stop paths recheck
                # their own immutable ownership; guard/key/setup I/O cannot
                # keep an admitted dedicated worker running.
                self.failure_cleanup(self.known, original)
            raise

    def _health(self, *, auth=False):
        with self.locked():
            r = self.receipt(); obj = self.inspect(r)
            require(obj['State']['Running'] and self.p['mode'] == 'runtime', 'runtime_not_running')
            # GET only; no model request/POST/replay. Native errors not exported.
            script = AUTH_SCRIPT if auth else HEALTH_SCRIPT
            return self.docker('exec', '--workdir=/a0', r['container_id'],
                               '/opt/venv-a0/bin/python', '-c', script, timeout=10)

    def probe(self):
        try:
            return self._probe()
        except BaseException as original:
            if self.p['network'] != 'none' and self.known is not None:
                self.failure_cleanup(self.known, original)
            raise

    def _probe(self):
        with self.locked():
            validate(self.p); seconds = min(15, remaining(self.p))
            r = self.receipt(); obj = self.inspect(r)
            require(obj['State']['Running'] and self.p['mode'] == 'runtime', 'runtime_not_running')
            unit = self.supervisor.observe(self.association(r))
            require(not unit.missing and unit.invocation_id == r.get('invocation_id')
                    and not unit.quiescent, 'native_probe_unit_changed')
            # Existing network=none/container/native deadline, no wrappers/calls.
            data = json.loads(self.docker('exec', '--workdir=/a0', r['container_id'],
                             '/opt/venv-a0/bin/python', '-B', '-c', probe_script(), timeout=seconds))
            if data.get('status') == 'REFUSED':
                code = data.get('code')
                allowed = {'native_input_missing_or_changed', 'native_scope_override_changed',
                           'native_preset_or_override_changed', 'native_slot_changed',
                           'native_constructed_slot_changed', 'native_provider_mapping_changed',
                           'native_distinct_key_not_ready', 'native_token_counter_changed',
                           'native_token_cache_unavailable', 'native_probe_failed'}
                raise RuntimeErrorBoundary(code if code in allowed else 'native_probe_refused')
            return probe_report_checked(data)


def materialize(usr):
    """New owned usr only. No existing state, credentials or source is copied."""
    usr.mkdir(mode=0o700)
    for relative, value in templates().items():
        p = usr / relative
        parent = usr
        for name in Path(relative).parts[:-1]:
            parent /= name
            parent.mkdir(mode=0o700, exist_ok=True)
            private(parent, directory=True)
        # JSON is a supported YAML subset; no host dependency/install needed.
        write_json(p, value)
    for name in ['uploads', 'workdir']:
        (usr / name).mkdir(mode=0o700)
    fd = os.open(usr / '.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write('AUTH_LOGIN=friday-rework\nAUTH_PASSWORD=' + secrets.token_hex(32) + '\n'
                'A0_PERSISTENT_RUNTIME_ID=' + secrets.token_hex(16) + '\n'
                'WEB_UI_HOST=127.0.0.1\nWEB_UI_PORT=5000\n')
        f.flush(); os.fsync(f.fileno())
    sync_dir(usr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['start', 'observe', 'stop', 'health', 'auth-check', 'config-probe'])
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--reviewed-plan-sha256', required=True)
    args = ap.parse_args()
    p = private(args.plan)
    require(sha(p) == args.reviewed_plan_sha256, 'reviewed_plan_changed')
    runtime = Runtime(json.loads(p.read_text()), stopping=args.action == 'stop')
    if args.action == 'start':
        result = runtime.start(p, args.reviewed_plan_sha256)
    elif args.action == 'observe':
        result = runtime.observe()
    elif args.action == 'stop':
        result = runtime.stop()
    elif args.action == 'config-probe':
        result = runtime.probe()
    else:
        result = {'checks': [json.loads(x) for x in runtime.health(auth=args.action == 'auth-check').splitlines()]}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No raw native output, paths containing credentials, chained traceback.
        code = str(exc) if isinstance(exc, RuntimeErrorBoundary) else 'runtime_control_failed'
        print(json.dumps({'status': 'REFUSED_OR_UNCONFIRMED', 'code': code}), file=sys.stderr)
        raise SystemExit(1) from None
