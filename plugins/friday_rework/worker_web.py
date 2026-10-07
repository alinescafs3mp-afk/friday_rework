"""Protected web inputs and the existing host-network admission producer.

Only operator policy plus current bounded native DNS/TLS observations can
admit web. Retrieval stays in the intact donors; no credential store is added.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re


class WorkerWebError(RuntimeError):
    pass


def scoped_environment(home, names):
    """Read only explicitly present values in the receiving Hermes scope."""
    from agent.secret_scope import current_secret_scope, current_secret_scope_home
    from gateway.platforms._shared import get_scoped_secret
    from hermes_constants import get_hermes_home
    scope = current_secret_scope()
    if (scope is None or current_secret_scope_home() != home
            or get_hermes_home() != Path(home) or not set(names).issubset(scope)):
        raise WorkerWebError('worker_scoped_keys_unavailable')
    result = {}
    for name in names:
        value = get_scoped_secret(name)
        if (not isinstance(value, str) or not value or len(value) > 4096
                or any(ord(c) < 32 or ord(c) == 127 for c in value)
                or value != scope[name]):
            raise WorkerWebError('worker_scoped_keys_unavailable')
        result[name] = value
    return result


@dataclass(frozen=True)
class DshWebInputs:
    """Pinned operator inputs, never model arguments or a live grant."""
    resolver: object
    trust_bundle: object
    egress_evidence: object
    research_policy: object
    profile: str = 'exa-paid'

    def pins(self):
        if self.profile not in ('exa-paid', 'exa-keyless'):
            raise WorkerWebError('unsupported_worker_web_profile')
        return (self.resolver, self.trust_bundle, self.egress_evidence, self.research_policy)

    def checked_patch(self, content):
        # Published renderer emits JSON, also valid native Cordis YAML. Refuse
        # expression-bearing YAML rather than evaluate it in the host.
        from tools.web_profile import dsh_web_patch
        try:
            rows = json.loads(content)
            if not isinstance(rows, list):
                raise ValueError()
            # Cordis indexes inserted entries immediately: a later direct patch
            # can replace Exa's config, including its URL or inline credential.
            # Include that entry in the exact rendered web configuration check.
            selected = [r for r in rows if isinstance(r, dict) and
                        (r.get('id') in {'web', 'web-search-exa', 'web-search-exa-keyless', 'mcp-exa', 'web-fetch-http', 'tool-web'} or 'insert' in r)]
            tool = next(r['config'] for r in selected if r.get('id') == 'tool-web')
            fetch = next(r['config'] for r in selected if r.get('id') == 'web-fetch-http')
            expected = dsh_web_patch(self.profile,
                search_max_results=tool['searchMaxResults'], search_max_queries=tool['searchMaxQueries'],
                timeout_ms=tool['searchTimeoutMs'], fetch_max_chars=tool['fetchMaxOutputChars'],
                fetch_max_bytes=fetch['maxResponseBytes'])
            if selected != expected:
                raise ValueError()
            if any(r.get('id') == 'web-search-deepseek' and r.get('disabled') is not True
                   for r in rows if isinstance(r, dict)):
                raise ValueError()
        except (ValueError, KeyError, TypeError, StopIteration, UnicodeError):
            raise WorkerWebError('worker_web_patch_mismatch') from None
        for pin in self.pins():
            pin.read()
        if not 1 <= len(self.research_policy.read()) <= 16000:
            raise WorkerWebError('worker_research_policy_bound')
        return self

    def mounts(self):
        # Separate DNS/TLS inputs. No ambient proxy, trust or foreign home.
        return ['--dir', '/etc', '--ro-bind', str(self.resolver.path), '/etc/resolv.conf']


def a0_web_files(profile, *, timeout_seconds=15):
    """Preparation data for native SearXNG + document_query, not startup.

    The current A0 launcher/guard permits run_ui only and local inference
    egress. Its owner must supply a reviewed intact service/startup/network
    composition before installing these inputs; this function cannot do so.
    """
    if (profile != 'searxng-google' or type(timeout_seconds) is not int
            or not 1 <= timeout_seconds <= 30):
        raise WorkerWebError('unsupported_a0_web_inputs')
    return {
        '/etc/searxng/settings.yml': {
            'use_default_settings': {'engines': {'keep_only': ['google']}},
            'general': {'debug': False, 'instance_name': 'Friday worker research'},
            'search': {'safe_search': 0, 'formats': ['json']},
            # Leave protected secret provisioning to the native installation.
            # An empty override is accepted by SearXNG and is not a start guard.
            'server': {'bind_address': '127.0.0.1', 'port': 55510,
                       'limiter': False, 'image_proxy': False},
            'outgoing': {'request_timeout': timeout_seconds, 'max_request_timeout': timeout_seconds},
            'engines': [{'name': 'google', 'engine': 'google', 'shortcut': 'g', 'disabled': False}],
        },
        '/a0/usr/plugins/_document_query/config.json': {
            'fetch_timeout': timeout_seconds, 'fetch_retries': 1,
            'fetch_retry_backoff': 0, 'max_remote_bytes': 1000000,
            'gather_timeout': timeout_seconds + 1,
        },
    }


# Executed by the already pinned native Node in the same DSH mount/network
# boundary, without keys. No search, model request, redirects or body retrieval.
DSH_NETWORK_PROBE = r"""
import dns from 'node:dns/promises';
import https from 'node:https';
import net from 'node:net';
function publicIP(a) {
  if (net.isIPv4(a)) {
    const p=a.split('.').map(Number);
    return !(p[0]===0 || p[0]===10 || p[0]===127 || p[0]>=224 ||
      (p[0]===169&&p[1]===254) || (p[0]===172&&p[1]>=16&&p[1]<=31) ||
      (p[0]===192&&(p[1]===168 || (p[1]===0&&p[2]===0) || (p[1]===0&&p[2]===2))) ||
      (p[0]===100&&p[1]>=64&&p[1]<=127) || (p[0]===198&&(p[1]===18||p[1]===19||p[1]===51)) ||
      (p[0]===203&&p[1]===0&&p[2]===113));
  }
  // Only global unicast IPv6; refuse mapped, ULA, linklocal and documentation.
  return net.isIPv6(a) && /^[23]/.test(a) && !a.toLowerCase().startsWith('2001:db8:');
}
const urls=JSON.parse(process.argv[2]);
const expiry=Date.now()+4000;
const rows=[];
try {
  for (const url of urls) {
    const u=new URL(url);
    const addresses=await dns.lookup(u.hostname,{all:true});
    if (!addresses.length || addresses.some(x=>!publicIP(x.address))) throw Error('dns');
    const a=addresses[0];
    const status=await new Promise((resolve,reject)=>{
      const r=https.request(u,{method:'HEAD',agent:false,rejectUnauthorized:true,
        lookup:(name,opts,cb)=>opts.all ? cb(null,[a]) : cb(null,a.address,a.family)},res=>{
        if (!res.socket.authorized || res.statusCode<200 || res.statusCode>=500) {
          res.destroy();reject(Error('tls_http'));return;
        }
        resolve(res.statusCode);res.destroy();
      });
      const timer=setTimeout(()=>r.destroy(Error('deadline')),Math.max(1,expiry-Date.now()));
      r.on('close',()=>clearTimeout(timer));r.on('error',reject);r.end();
    });
    rows.push({url,address:a.address,status,tls:true});
  }
  console.log(JSON.stringify({schema:'friday.dsh-web-observation.v1',rows}));
} catch { process.exitCode=1; }
"""


def web_policy(web, home, profile, now):
    """An explicit protected operator declaration, not a readiness receipt."""
    import math
    import ipaddress
    import os
    import stat
    from urllib.parse import urlsplit
    p = web.egress_evidence.path
    st = p.lstat()
    if (st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) not in (0o400, 0o600)
            or st.st_nlink != 1 or p.resolve() != p or st.st_size > 16000):
        raise WorkerWebError('worker_web_policy_not_private')
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise WorkerWebError('worker_web_policy_duplicate')
            result[key] = value
        return result
    try:
        v = json.loads(web.egress_evidence.read(), object_pairs_hook=pairs)
        if (not isinstance(v, dict) or set(v) != {'schema','runtime_home','runtime_profile',
                'boot_id','net_namespace','expires_unix','allow_public_https','document_probes'}
                or v['schema'] != 'friday.worker-web.policy.v1'
                or v['runtime_home'] != home or v['runtime_profile'] != profile
                or v['allow_public_https'] is not True
                or type(v['expires_unix']) not in (int,float) or not math.isfinite(v['expires_unix'])
                or v['expires_unix'] <= now
                or not isinstance(v['net_namespace'],list) or len(v['net_namespace']) != 2
                or any(type(x) is not int or x <= 0 for x in v['net_namespace'])
                or not isinstance(v['boot_id'],str)
                or not isinstance(v['document_probes'],list) or not 1 <= len(v['document_probes']) <= 2):
            raise ValueError()
        for text in v['document_probes']:
            u = urlsplit(text)
            try: ipaddress.ip_address(u.hostname or '')
            except ValueError: pass
            else: raise ValueError()
            if (len(text) > 1024 or any(ord(c)<=32 for c in text) or '%' in text or '\\' in text
                    or u.scheme != 'https' or u.username is not None or u.password is not None
                    or u.port is not None or u.query or u.fragment
                    or not u.hostname or not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)+',u.hostname)
                    or text != 'https://' + u.hostname + u.path):
                raise ValueError()
        if len(set(v['document_probes'])) != len(v['document_probes']):
            raise ValueError()
    except (ValueError,TypeError,KeyError,UnicodeError):
        raise WorkerWebError('worker_web_policy_invalid') from None
    return v


class DshNetworkCheck:
    """Current host-net proof, bound to the actual ordinary adapter and store.

    DSH's existing bwrap shares this network namespace. Probe uses that exact
    boundary, pinned Node, resolver and CA. Repeat at the two existing launch
    checkpoints; no daemon, new unit or cached grant. Any failure propagates.
    """
    def __init__(self, config, associations, adapter):
        self.config, self.store, self.adapter = config, associations, adapter

    def __call__(self, original, web):
        import hashlib
        import ipaddress
        import os
        import subprocess
        from .adapters.dsh import _identity
        def current():
            row, root = self.adapter._row(original)
            self.adapter._admit(row)
            if row.get('host',{}).get('binding',{}).get('runtime') != self.config:
                raise WorkerWebError('worker_web_runtime_changed')
            self.adapter._pins()
            return row, root
        def identity():
            st = Path('/proc/self/ns/net').stat()
            return Path('/proc/sys/kernel/random/boot_id').read_text().strip(), [st.st_dev,st.st_ino]
        row, root = current()
        policy = web_policy(web,self.config['runtime_home'],self.config['runtime_profile'],self.store.clock())
        before = identity()
        if before != (policy['boot_id'],policy['net_namespace']):
            raise WorkerWebError('worker_web_namespace_changed')
        urls = [('https://mcp.exa.ai/' if web.profile == 'exa-keyless' else 'https://api.exa.ai/'),*policy['document_probes']]
        left = self.adapter._remaining(row)
        if left <= 5:
            raise WorkerWebError('worker_web_original_budget_exhausted')
        script = root/'inputs/web-network.mjs'
        if script.read_bytes() != DSH_NETWORK_PROBE.encode():
            raise WorkerWebError('worker_web_probe_changed')
        argv = self.adapter._boundary(root,[str(self.adapter.config.node.path),'/job-input/web-network.mjs',json.dumps(urls)])
        try:
            r = subprocess.run(argv,env=self.adapter._environment(),stdin=subprocess.DEVNULL,
                               capture_output=True,timeout=min(5,left),check=False)
            v = json.loads(r.stdout)
            if (r.returncode != 0 or len(r.stdout)>16000 or r.stderr
                    or not isinstance(v,dict) or set(v) != {'schema','rows'}
                    or v['schema'] != 'friday.dsh-web-observation.v1' or len(v['rows']) != len(urls)):
                raise ValueError()
            for url, observation in zip(urls,v['rows']):
                if (set(observation) != {'url','address','status','tls'} or observation['url'] != url
                        or not ipaddress.ip_address(observation['address']).is_global
                        or observation['tls'] is not True or type(observation['status']) is not int
                        or not 200 <= observation['status'] < 500):
                    raise ValueError()
        except (OSError,subprocess.TimeoutExpired,ValueError,TypeError,KeyError):
            raise WorkerWebError('worker_web_native_dns_tls_refused') from None
        after, _ = current()
        if (_identity(after) != _identity(row) or identity() != before
                or web_policy(web,self.config['runtime_home'],self.config['runtime_profile'],self.store.clock()) != policy):
            raise WorkerWebError('worker_web_changed_during_probe')
        return {'identity':_identity(after),'policy_sha256':web.egress_evidence.sha256,'observation':v}


def keyless_source():
    """Exact shipped native provider glue, staged after intact Harness build."""
    return Path(__file__).resolve().with_name("adapters").joinpath("dsh_keyless_web.mjs").read_bytes()
