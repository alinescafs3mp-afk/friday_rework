"""Administrator projections over native stores. No WorkerHost or transcript copy."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import re
import hashlib
import hashlib

from hermes_cli.friday_product_access import admin_policy, access_policy, principal_id, profile_name, settings
from .access import ProductAccess
from .associations import Associations, _sync_directory


def masked(value):
    """Native structural masking plus fields native configuration does not classify.

    Text is also scrubbed against configured secrets; no environment enumeration
    or protected value is returned to a caller.
    """
    from hermes_cli.config import redact_config_value
    from agent.redact import redact_for_egress
    def walk(v, depth=0):
        if depth > 20:
            return "[REDACTED]"
        if isinstance(v, dict):
            return {k: ("[REDACTED]" if re.search(
                r"password|secret|token|credential|authorization|api[_-]?key|private[_-]?key", str(k), re.I
            ) else walk(x, depth + 1)) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x, depth + 1) for x in v]
        if isinstance(v, str):
            return redact_for_egress(v)
        return v
    return walk(redact_config_value(value))


class Administration:
    def __init__(self):
        from hermes_constants import get_process_hermes_home
        self.launch_home = get_process_hermes_home()

    def profiles(self):
        policy = admin_policy()
        if policy is None:
            raise PermissionError("product_admin_not_configured")
        return list(dict.fromkeys(policy["profiles"]))

    @contextmanager
    def scope(self, profile):
        profile_name(profile)
        if profile not in self.profiles():
            raise PermissionError("foreign_product_profile")
        from hermes_cli.profiles import get_profile_dir
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        home = get_profile_dir(profile)
        if not home.is_dir() or home.resolve() != home or home.is_symlink():
            raise PermissionError("unsafe_product_profile")
        token = set_hermes_home_override(str(home))
        try:
            yield home
        finally:
            reset_hermes_home_override(token)

    @staticmethod
    def _state():
        from hermes_cli.plugins_state import PluginState
        return PluginState("friday_rework")

    @staticmethod
    @contextmanager
    def _db(home):
        from hermes_state import SessionDB
        # Missing native history is unknown, not a new empty transcript database.
        path = home / "state.db"
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError("native_session_store_missing")
        db = SessionDB(path, read_only=True)
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _rows(state):
        store = Associations(state)
        return store.snapshot()

    def users(self, profile):
        with self.scope(profile):
            policy = access_policy()
            if policy is None or not any(a["transport_profile"] == profile for a in policy["accounts"]):
                raise PermissionError("receiving_transport_authority_required")
            accounts = [a for a in policy["accounts"] if a["transport_profile"] == profile]
            authority = ("LOCAL_CLI_AUTHORIZATION" if all(a['platform'] == 'cli' for a in accounts) else
                         "RECEIVING_TRANSPORT_AND_LOCAL_CLI_AUTHORIZATION" if any(a['platform'] == 'cli' for a in accounts) else "RECEIVING_TRANSPORT")
            return {"profile": profile, "authority": authority, "accounts": accounts,
                    "users": [{"principal_id": key, **row} for key, row in ProductAccess(self._state()).users().items()]}

    def set_user(self, profile, **values):
        if values.get("transport_profile") != profile:
            raise PermissionError("receiving_transport_authority_required")
        with self.scope(profile) as root:
            if values.get("enabled") is True:
                self._require_complete_onboarding(root, values)
            result = ProductAccess(self._state()).set_user(**values)
            return {"recorded": True, "admission": "PRODUCT_INTERSECTION_NEXT_REQUEST",
                    "native_grant": "EXPLICIT_OS_UID_MAPPING_REQUIRED" if values['platform'] == 'cli' else "REQUIRED_SEPARATELY", "user": result}

    @staticmethod
    def _require_complete_onboarding(root, values):
        from hermes_cli import friday_user_scope as scope
        active = scope.policy(root)
        if active is None:
            if values['platform'] == 'cli': raise PermissionError('private_profile_setup_required')
            return
        key = principal_id(*(values[k] for k in ("platform", "transport_profile", "account_id", "user_id")))
        bindings = [b for b in active["bindings"] if principal_id(*(b[k] for k in
                    ("platform", "transport_profile", "account_id", "user_id"))) == key]
        if len(bindings) != 1: raise PermissionError("private_profile_setup_required")
        from hermes_constants import get_default_hermes_root
        binding = bindings[0]; home = get_default_hermes_root(home=root) / "profiles" / binding["runtime_profile"]
        scope._private(home, directory=True)
        scope._private(home / scope.MARKER)
        marker = json.loads((home / scope.MARKER).read_text())
        expected = {"schema": "friday.user-home.v1", "principal": key,
                    "profile": binding["runtime_profile"], "binding_sha256": scope._fingerprint(binding)}
        if (home / scope.ONBOARDING).exists() or (home / scope.ONBOARDING).is_symlink() or (
                isinstance(marker, dict) and "onboarding_sha256" in marker):
            # Digest-bound setup cannot downgrade to the legacy-home contract
            # by deleting its receipt. Missing readiness never enables access.
            try:
                scope._private(home / scope.ONBOARDING)
                scope.check_onboarding_home(root, home, binding)
                expected["onboarding_sha256"] = hashlib.sha256((home / scope.ONBOARDING).read_bytes()).hexdigest()
            except OSError as exc:
                raise PermissionError("private_profile_setup_required") from exc
        if marker != expected:
            raise PermissionError("private_profile_setup_required")

    def onboarding_templates(self, profile):
        from .onboarding import Onboarding
        return Onboarding(self).templates(profile)

    def onboarding_prepare(self, profile, *, session=None, **values):
        from .onboarding import Onboarding
        return Onboarding(self).prepare(profile, session=session, **values)

    def onboarding_credentials(self, profile, *, session=None, **values):
        from .onboarding import Onboarding
        return Onboarding(self).credentials(profile, session=session, **values)

    def onboarding_worker_prepare(self, profile, *, session=None, **values):
        from .onboarding import Onboarding
        return Onboarding(self).prepare_worker(profile, session=session, **values)

    def onboarding_worker_configure(self, profile, *, session=None, **values):
        from .onboarding import Onboarding
        return Onboarding(self).configure_worker(profile, session=session, **values)

    def onboarding_workers_prepare(self, profile, *, session=None, **values):
        from .onboarding import Onboarding
        return Onboarding(self).prepare_workers(profile, session=session, **values)

    def onboarding_workers_qualify(self, profile, *, session=None, **values):
        from .onboarding import Onboarding
        return Onboarding(self).qualify_workers(profile, session=session, **values)

    def onboarding_workers_state(self, profile, *, session=None, **values):
        from .onboarding import Onboarding
        return Onboarding(self).workers_state(profile, session=session, **values)

    def onboarding_activate(self, profile, *, session=None, **values):
        from .onboarding import Onboarding
        return Onboarding(self).activate(profile, session=session, **values)

    def pairing(self, profile):
        authority = self.users(profile)
        if all(a['platform'] == 'cli' for a in authority['accounts']):
            return {'pending': [], 'approved': [], 'local_cli': 'EXPLICIT_UID_MAPPING_NO_CHANNEL_PAIRING'}
        with self.scope(profile):
            from gateway.pairing import PairingStore
            store = PairingStore()
            # Pairing codes are credentials; expose only request ids to the console.
            pending = store.list_pending()
            return {"pending": pending, "approved": store.list_approved()}

    def approve(self, profile, *, platform, transport_profile, account_id, request_id):
        if platform == 'cli': raise PermissionError('cli_has_no_messaging_pairing')
        if transport_profile != profile:
            raise PermissionError("receiving_transport_authority_required")
        with self.scope(profile):
            policy = access_policy()
            if policy is None or not any((a["platform"], a["transport_profile"], a["account_id"]) ==
                    (platform, transport_profile, account_id) for a in policy["accounts"]):
                raise PermissionError("foreign_product_account")
            from gateway.pairing import PairingStore
            store = PairingStore()
            # Explicit request id only: no ambiguous code/request fallback or retry.
            if not store.looks_like_request_id(request_id):
                raise ValueError("invalid_pairing_request")
            user = store.approve_request(platform, request_id)
            if not user:
                raise ValueError("pairing_request_not_found")
            user_id = user.get("user_id")
            try:
                _sync_directory(store._dir)
                if not PairingStore().is_approved(platform, user_id):
                    raise RuntimeError("native_pairing_write_unconfirmed")
                from hermes_cli import friday_user_scope as scope
                active = scope.policy(Path(__import__("hermes_constants").get_hermes_home()))
                if active is not None:
                    key = principal_id(platform, transport_profile, account_id, user_id)
                    binding = next((b for b in active["bindings"] if principal_id(*(b[k] for k in
                        ("platform", "transport_profile", "account_id", "user_id"))) == key), None)
                    if binding:
                        from hermes_constants import get_default_hermes_root, get_hermes_home
                        home = get_default_hermes_root(home=get_hermes_home()) / "profiles" / binding["runtime_profile"]
                        if (home / scope.ONBOARDING).exists() and not (home / scope.MARKER).exists():
                            return {"recorded": True, "enabled": False, "admission": "DISABLED_SETUP_PENDING",
                                    "native_grant": "PAIRING_APPROVED"}
                self._require_complete_onboarding(Path(__import__("hermes_constants").get_hermes_home()),
                    dict(platform=platform, transport_profile=transport_profile, account_id=account_id, user_id=user_id))
                result = ProductAccess(self._state()).set_user(platform=platform,
                    transport_profile=transport_profile, account_id=account_id,
                    user_id=user_id, enabled=True, role="user")
            except Exception as exc:
                # The native grant may have committed. Product default deny stays
                # authoritative; a lost write acknowledgement is never success.
                raise RuntimeError("pairing_grant_may_exist_product_write_unconfirmed") from exc
            return {"recorded": True, "user": result, "native_grant": "PAIRING_APPROVED"}

    @staticmethod
    def _identity(row, policy):
        fields = ("user_id", "chat_id", "thread_id", "session_key", "transport_profile")
        identity = {k: row.get(k) for k in fields}
        try:
            origin = json.loads(row.get("origin_json") or "null")
        except (ValueError, TypeError):
            origin = None
        platform = row.get("source")
        identity.update(platform=platform, account_id=None, principal_id=None, evidence="UNKNOWN")
        if not isinstance(origin, dict) or any(
            (origin.get(k) or "") != (row.get(k) or "") for k in ("user_id", "chat_id", "thread_id")
        ) or origin.get("platform") != platform:
            return identity
        # Historical account evidence belongs to the native row at creation.
        # The current mutable account policy must never relabel old conversations.
        account = origin.get("friday_account_origin")
        if (not isinstance(account, dict) or set(account) != {"schema", "platform", "transport_profile", "account_id"}
                or account["schema"] != "friday.account_origin.v1" or account["platform"] != platform
                or account["transport_profile"] != row.get("transport_profile") or not row.get("user_id")):
            return identity
        try:
            key = principal_id(platform, account["transport_profile"], account["account_id"], row["user_id"])
        except ValueError:
            return identity
        identity.update(account_id=account["account_id"], evidence="NATIVE_CREATED_TRANSPORT_ACCOUNT",
                        principal_id=key)
        return identity

    @staticmethod
    def _task_projection(row):
        # Native observations are retained observations, never a new status probe.
        return {k: copy.deepcopy(row.get(k)) for k in ("existing_task_id", "owner", "worker_kind",
            "created_at_unix", "budget_seconds", "deadline_unix", "elapsed_seconds",
            "submission_observation", "stop_intent", "execution_observation", "goal_verification", "delivery")} | {
            "native": row.get("native"), "observation_freshness": "RETAINED_NATIVE_RECORD",
            "attachments": [{"index": i, **{k: a.get(k) for k in
                ("logical_name", "size_bytes", "sha256", "complete", "verification")}}
                for i, a in enumerate((row.get("result") or {}).get("artifacts", []))],
            "inputs": [{"index": i, "logical_name": Path(a["host_path"]).name,
                "size_bytes": a["size_bytes"], "sha256": a["sha256"], "ownership": "RECHECK_ON_DOWNLOAD"}
                for i, a in enumerate((row.get("host") or {}).get("inputs") or [])],
            "stop_available": True, "stop_reason": "VERIFY_CURRENT_ADMIN_AND_OWNING_GATEWAY_ON_ACTION",
            "quiescent": (row.get("host") or {}).get("quiescence") is not None}

    def tasks(self, profile):
        with self.scope(profile):
            return [self._task_projection(row) for row in self._rows(self._state()).values()]

    def conversations(self, profile, *, query="", limit=100, offset=0, filters=None):
        if not isinstance(query, str) or len(query) > 512 or not 1 <= limit <= 200 or not 0 <= offset <= 100000:
            raise ValueError("invalid_admin_page")
        filters = filters or {}
        if set(filters) - {"platform", "user_id", "account_id", "chat_id", "thread_id"} or any(not isinstance(v, str) or len(v) > 512 for v in filters.values()):
            raise ValueError("invalid_admin_filter")
        with self.scope(profile) as home, self._db(home) as db:
            policy = access_policy()
            rows = db.list_sessions_rich(limit=limit, offset=offset, search_query=query or None,
                include_children=True, include_archived=True, include_hidden=True,
                project_compression_tips=False, order_by_last_active=True)
            if query:
                # Use native indexed message search as well as native id/title
                # search. Preserve raw session IDs; never collapse lineage users.
                selected = {r["id"]: r for r in rows}
                for hit in db.search_messages(query, limit=limit, offset=offset):
                    sid = hit["session_id"]
                    if sid not in selected:
                        row = db.get_session(sid)
                        if row is not None:
                            selected[sid] = row
                rows = list(selected.values())
            projected = [{"profile": profile, "session_id": row["id"], "title": row.get("title"),
                     "parent_session_id": row.get("parent_session_id"), "identity": self._identity(row, policy)} for row in rows]
            # This is a bounded native page, not a claim of a global filtered count.
            return [r for r in projected if all(r["identity"].get(k) == v for k, v in filters.items())]

    def conversation(self, profile, session_id, *, limit=100, offset=0):
        if (not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", session_id)
                or type(limit) is not int or type(offset) is not int
                or not 1 <= limit <= 200 or not 0 <= offset <= 100000):
            raise ValueError("invalid_admin_session")
        with self.scope(profile) as home, self._db(home) as db:
            row = db.get_session(session_id)
            if row is None:
                raise ValueError("native_session_not_found")
            identity = self._identity(row, access_policy())
            messages = db.get_messages(session_id, limit=limit + 1, offset=offset, include_ancestors=False)
            has_more = len(messages) > limit
            messages = messages[:limit]
            next_offset = offset + limit if has_more and offset + limit <= 100000 else None
            page = {"offset": offset, "limit": limit, "count": len(messages), "has_more": has_more,
                    "previous_offset": max(0, offset - limit) if offset else None,
                    "next_offset": next_offset, "end": not has_more,
                    "state": "BOUNDED_LIMIT" if has_more and next_offset is None else ("MORE" if has_more else "END")}
            joined = []
            for task in self._rows(self._state()).values():
                owner = task["owner"]
                if (owner["session_id"] == session_id and owner["session_key"] == identity["session_key"]
                        and identity["evidence"] != "UNKNOWN" and owner["bot_id"] == identity["account_id"]
                        and owner["user_id"] == identity["user_id"] and owner["chat_id"] == identity["chat_id"]
                        and owner["thread_id"] == (identity["thread_id"] or "")
                        and (owner["profile"] or "default") == profile):
                    joined.append(self._task_projection(task))
            return {"profile": profile, "session_id": session_id, "identity": identity,
                    "messages": [{k: m.get(k) for k in ("id", "role", "content", "timestamp", "tool_name")} for m in messages],
                    "tasks": joined, "page": page, "ancestor_history": "NOT_MERGED", "attachments": "USE_VERIFIED_TASK_REFERENCES_ONLY"}

    def attachment(self, profile, task_id, index):
        from .artifacts import StagedArtifact, read_staged
        from .host_record import validate_host_record
        from .results import output_root
        if type(index) is not int or not 0 <= index < 16:
            raise ValueError("invalid_admin_attachment")
        with self.scope(profile):
            row = self._rows(self._state()).get(task_id)
            if row is None or (row["owner"]["profile"] or "default") != profile:
                raise PermissionError("foreign_task_attachment")
            # This initial package exposes only existing verified staged outputs.
            # Received files without a full checked task mapping remain unknown.
            validate_host_record(row)
            artifacts = (row.get("result") or {}).get("artifacts", [])
            if index >= len(artifacts):
                raise ValueError("unverified_attachment")
            artifact = StagedArtifact(**artifacts[index])
            if artifact.logical_name.lower() in {".env", "config.yaml", "state.json", "id_rsa", "id_ed25519"}:
                raise PermissionError("protected_configuration_attachment")
            payload = read_staged(staging_root=output_root(row), artifact=artifact, max_bytes=16 * 1024**2)
            return payload

    def input_attachment(self, profile, task_id, index):
        from .artifacts import StagedArtifact, read_staged
        from .host_record import validate_host_record
        if type(index) is not int or not 0 <= index < 64:
            raise ValueError("invalid_admin_attachment")
        with self.scope(profile):
            row = self._rows(self._state()).get(task_id)
            if row is None or (row["owner"]["profile"] or "default") != profile:
                raise PermissionError("foreign_task_attachment")
            validate_host_record(row)
            host = row["host"]; inputs = host["inputs"] or []
            message = host["binding"]["ingress"]["message"]
            media = message["media"]
            if index >= len(inputs) or len(inputs) != len(media):
                raise ValueError("ambiguous_input_mapping")
            item, received = inputs[index], media[index]
            origin, content = received.get("origin"), received.get("content")
            if (not origin or not content or origin["message_id"] not in {message["message_id"], message["reply_to_message_id"]}
                    or any(origin[k] != message[k] for k in ("bot_id", "chat_id", "thread_id"))
                    or content != {"size_bytes": item["size_bytes"], "sha256": item["sha256"]}):
                raise ValueError("unproved_input_ownership")
            name = Path(item["host_path"]).name
            artifact = StagedArtifact(name, name, "application/octet-stream", item["size_bytes"], item["sha256"], item["receipt_reference"])
            runtime = host["binding"]["runtime"]
            root = Path(runtime["staging_root"]) / task_id
            return read_staged(staging_root=root, artifact=artifact, max_bytes=16 * 1024**2)

    def health(self):
        # Existing admin route authority is checked before this read-only view.
        from .startup_health import worker_health
        return worker_health()

    def effective(self, profile):
        with self.scope(profile) as home:
            from hermes_cli.config import load_config_readonly
            from .admin_settings import options, private_config
            cfg = load_config_readonly()
            return {"profile": profile, "settings": {k: cfg.get(k) for k in
                ("model", "auxiliary", "agent", "streaming", "gateway", "platform_toolsets", "skills", "web", "plugins")},
                "changes_available": True, "typed_options": options(cfg, home),
                "config_sha256": private_config(home / "config.yaml"),
                "runtime_application": "PERSISTED_NEXT_NATIVE_SESSION_OR_RELOAD",
                "native_stores": "PairingStore / SessionDB / Friday PluginState",
                "web_worker_journeys": "NOT_RUN"}

    def control(self, profile, session, task_id, action):
        from .admin_controls import authority_home, request_control
        from hermes_cli.friday_product_access import admin_policy, session_allowed
        with authority_home(self.launch_home):
            if admin_policy() is None or not session_allowed(session) or profile not in self.profiles():
                raise PermissionError("verified_admin_required")
        return request_control(self.launch_home, profile, session, task_id, action)

    def _verify_session(self, profile, session):
        from .admin_controls import authority_home
        from hermes_cli.friday_product_access import admin_policy, session_allowed
        with authority_home(self.launch_home):
            if admin_policy() is None or not session_allowed(session) or profile not in self.profiles():
                raise PermissionError("verified_admin_required")

    def write_settings(self, profile, body, session):
        from .admin_settings import edit
        self._verify_session(profile, session)
        with self.scope(profile) as home:
            return edit(profile, home, body, lambda: self._verify_session(profile, session))

    def schedules(self, profile, action=None, job_id=None, session=None):
        from .admin_settings import schedules
        if action is not None: self._verify_session(profile, session)
        with self.scope(profile):
            return schedules(action, job_id, lambda: self._verify_session(profile, session))
