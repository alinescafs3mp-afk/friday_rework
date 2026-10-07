"""Native worker web inputs; no transport, credential store or admission producer.

The trusted host supplies current network verification. A readiness/evidence
file alone never authorizes egress. Retrieval stays in each intact donor.
"""
from dataclasses import dataclass
import json
from pathlib import Path


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
        if self.profile != 'exa-paid':
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
                        (r.get('id') in {'web', 'web-search-exa', 'web-fetch-http', 'tool-web'} or 'insert' in r)]
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
