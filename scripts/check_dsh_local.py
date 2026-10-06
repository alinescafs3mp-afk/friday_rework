#!/usr/bin/env python3
"""Finite native CLI component checks; loopback error responses are not inference."""

import argparse
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time

spec = importlib.util.spec_from_file_location(
    "dsh_renderer", Path(__file__).resolve().parents[1] / "tools/render_dsh_local.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

GUARD = r'''
const fs = require('node:fs');
const net = require('node:net');
const original = net.Socket.prototype.connect;
net.Socket.prototype.connect = function(...args) {
  const [options] = Array.isArray(args[0]) ? args[0] : net._normalizeArgs(args);
  const host = options.host || 'localhost';
  const allowed = !!options.path ||
    (['127.0.0.1', '::1', 'localhost'].includes(host) &&
     String(options.port) === process.env.FRW_FIXTURE_PORT);
  fs.appendFileSync(process.env.FRW_NETWORK_LOG,
    JSON.stringify({kind: options.path ? 'ipc' : 'tcp', host: options.path ? null : host,
                    port: options.port || null, allowed}) + '\n', {mode: 0o600});
  if (!allowed) {
    process.nextTick(() => this.destroy(new Error('FRW offline network denied')));
    return this;
  }
  return original.apply(this, args);
};
'''


def run_native(argv, *, cwd, env, timeout=30):
    start = time.monotonic()
    child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = child.communicate(b'Offline component refusal check.\n', timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(child.pid, signal.SIGTERM)
        try:
            stdout, stderr = child.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            stdout, stderr = child.communicate(timeout=3)
    survivors = []
    for p in Path('/proc').glob('[0-9]*'):
        try:
            fields = (p/'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == child.pid and fields[0] != 'Z':
                survivors.append(int(p.name))
        except (OSError, ValueError, IndexError):
            pass
    if survivors:
        os.killpg(child.pid, signal.SIGKILL)
        raise RuntimeError('Owned CLI descendants survived termination')
    return {'returncode': child.returncode, 'elapsed_seconds': round(time.monotonic()-start, 3),
            'timed_out': timed_out, 'surviving_owned_pids': survivors}, stdout, stderr


def main():
    if not __debug__:
        raise RuntimeError('Component assertions must remain enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--donor', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    node, donor, evidence = args.node.resolve(strict=True), args.donor.resolve(strict=True), args.evidence.absolute()
    evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (evidence != evidence.resolve() or evidence.stat().st_mode & 0o077
            or evidence.stat().st_uid != os.getuid() or any(evidence.iterdir())):
        raise ValueError('A private evidence directory is required')
    cli = donor/'apps/cli/lib/bin.js'
    if hashlib.sha256(cli.read_bytes()).hexdigest() != '1a03dee18683483ff6a1b27b2a1e650230da6bcca9a0f55f7d81b3308c3f307f':
        raise ValueError('Built CLI differs from accepted FRW002 artifact')
    requests = []
    stall = threading.Event()
    class Refusal(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
            requests.append({'path': self.path, 'model': body.get('model'),
                             'max_tokens': body.get('max_tokens'),
                             'max_completion_tokens': body.get('max_completion_tokens'),
                             'authorization_present': 'Authorization' in self.headers})
            if stall.is_set():
                # A fixture delay, not a peer-delivery wait or model call.
                threading.Event().wait(1)
            response = b'{"error":{"message":"FRW fixture model unavailable","type":"invalid_request_error","code":"model_not_found"}}'
            self.send_response(400); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response))); self.end_headers()
            try:
                self.wfile.write(response)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Refusal)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    cases = {}
    try:
        with tempfile.TemporaryDirectory(prefix='frw005-cli-', dir=evidence) as temp:
            root = Path(temp); guard = root/'network-guard.cjs'; guard.write_text(GUARD); guard.chmod(0o600)
            patch = root/'local.patch.yml'
            renderer.publish_private(patch, renderer.build_patch(
                purpose='temporary-local-test', api='openai-completions',
                base_url=f'http://127.0.0.1:{server.server_port}/v1', model='fixture-local',
                context_window=40960, max_tokens=4096, summary_max_tokens=2048,
                headroom_tokens=4096, api_key_env='FRIDAY_FIXTURE_API_KEY', request_timeout_ms=2000))
            def case(name, app_args, extra_patch=None, keyed=True, guard_check=False):
                home = root/name; home.mkdir(mode=0o700)
                network = evidence/(name+'.network.jsonl')
                env = {'PATH': str(node.parent)+':/usr/bin:/bin', 'HOME': str(home),
                       'DSH_HOME': str(home/'dsh'), 'DSH_TELEMETRY_DISABLED': '1',
                       'LANG': 'C.UTF-8', 'FRW_NETWORK_LOG': str(network),
                       'FRW_FIXTURE_PORT': str(server.server_port)}
                if keyed:
                    env['FRIDAY_FIXTURE_API_KEY'] = 'FRW_SECRET_CANARY_005'
                argv = [str(node), '--require', str(guard), str(cli), '--profile', 'headless',
                        '--patch', str(extra_patch or patch), *app_args]
                if guard_check:
                    argv = [str(node), '--require', str(guard), '-e',
                            "require('http').get('http://8.8.8.8:80/',()=>process.exit(9)).on('error',()=>process.exit(7))"]
                begin = len(requests)
                observation, stdout, stderr = run_native(argv, cwd=home, env=env)
                assert b'FRW_SECRET_CANARY_005' not in stdout+stderr, 'Fixture credential leaked'
                for suffix, data in (('stdout', stdout), ('stderr', stderr)):
                    p = evidence/(name+'.'+suffix)
                    with p.open('xb') as f:f.write(data)
                    p.chmod(0o600)
                observation.update(requests=requests[begin:],
                    stdout_sha256=hashlib.sha256(stdout).hexdigest(),
                    stderr_sha256=hashlib.sha256(stderr).hexdigest(),
                    network=[json.loads(line) for line in network.read_text().splitlines()] if network.exists() else [])
                if '--json' in app_args and stdout:
                    events = [json.loads(line) for line in stdout.splitlines()]
                    observation['turn_end_reasons'] = [e.get('reason') for e in events
                        if e.get('type')=='status' and e.get('phase')=='turn_end']
                    observation['final_present'] = any(e.get('type')=='final' for e in events)
                assert not observation['timed_out'], 'Native refusal exceeded component deadline'
                assert not any(not row['allowed'] for row in observation['network']) or guard_check
                cases[name] = observation
                return observation
            assert case('network-denial-control', [], guard_check=True)['returncode'] == 7
            assert case('effective-dump', ['--dump-config'])['returncode'] == 0
            assert case('native-startup', ['--help'])['returncode'] == 0
            failure = case('local-model-refusal', ['--json', '-'])
            assert failure['returncode'] == 1 and failure['requests'], 'No native local request/refusal'
            assert all(r['path']=='/v1/chat/completions' and r['model']=='fixture-local'
                       and (r['max_tokens']==4096 or r['max_completion_tokens']==4096)
                       for r in failure['requests']), 'Wrong native route/output reservation'
            assert failure['final_present'] and failure['turn_end_reasons']
            assert all(r.get('kind')=='error' for r in failure['turn_end_reasons'])
            missing = case('missing-key', ['--json', '-'], keyed=False)
            assert missing['returncode'] == 1 and not missing['requests'], 'Missing credential reached server'
            bad = root/'invalid.patch.yml'; bad.write_text('[{broken'); bad.chmod(0o600)
            invalid = case('invalid-native-patch', ['--json', '-'], extra_patch=bad)
            assert invalid['returncode'] == 1 and not invalid['requests']
            delayed_patch = root/'delayed.patch.yml'
            renderer.publish_private(delayed_patch, renderer.build_patch(
                purpose='temporary-local-test', api='openai-completions',
                base_url=f'http://127.0.0.1:{server.server_port}/v1', model='fixture-local',
                context_window=40960, max_tokens=4096, summary_max_tokens=2048,
                headroom_tokens=4096, api_key_env='FRIDAY_FIXTURE_API_KEY', request_timeout_ms=200))
            stall.set()
            delayed = case('local-request-timeout', ['--json', '-'], extra_patch=delayed_patch)
            stall.clear()
            assert delayed['returncode'] == 1 and delayed['requests'], 'Native request timeout missing'
            assert delayed['turn_end_reasons'] and all(r.get('kind')=='error'
                for r in delayed['turn_end_reasons']), 'Timeout reported success'
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
    result = {'status': 'PASS', 'scope': 'real CLI component checks with loopback refusal only',
              'inference': 'NOT_RUN', 'product_acceptance': 'NOT_RUN', 'cases': cases,
              'node_sha256': hashlib.sha256(node.read_bytes()).hexdigest(),
              'cli_sha256': hashlib.sha256(cli.read_bytes()).hexdigest()}
    path = evidence/'cli-component-checks.json'
    with path.open('x') as f:json.dump(result, f, indent=2); f.write('\n')
    path.chmod(0o600)
    print(json.dumps({'status': 'PASS', 'cases': len(cases), 'evidence': str(path)}))


if __name__ == '__main__':
    main()
