"""Host fields in the existing association document, not a second job store."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from .associations import AssociationError, _number, _text
from .boundary import parse_brief
from .supervision import UnitObservation


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def association_address(correlation, ingress):
    # Reference derived from native identity; never a new independent task ID.
    return "native-" + digest({"correlation": correlation, "ingress": ingress})


def owner_from_ingress(correlation, ingress):
    message = ingress["message"]
    return {**{k: message[k] for k in ("bot_id", "user_id", "chat_id", "thread_id", "message_id")},
            "session_id": correlation["session_id"], "session_key": ingress["session_key"],
            "profile": ingress["runtime_profile"]}


def validate_host_record(row):
    # Local import avoids the admission/store dependency cycle.
    from .admission import CALL_FIELDS, _snapshot
    from .controller import _inputs_digest
    from .adapters.contract import VerifiedInput
    from .host_runtime import validate_runtime
    try:
        host = row["host"]
        if not isinstance(host, dict) or set(host) != {"binding", "inputs", "observation", "terminal", "quiescence"}:
            raise ValueError()
        binding = host["binding"]
        if not isinstance(binding, dict) or set(binding) != {"correlation", "ingress", "brief", "runtime"}:
            raise ValueError()
        call = binding["correlation"]
        if not isinstance(call, dict) or set(call) != set(CALL_FIELDS):
            raise ValueError()
        for value in call.values():
            _text(value)
        if call["task_id"] != call["session_id"]:
            raise ValueError()
        ingress = _snapshot(binding["ingress"])
        brief = parse_brief(binding["brief"])
        runtime = validate_runtime(binding["runtime"])
        address = association_address(call, ingress)
        if (row["existing_task_id"] != address or row["owner"] != owner_from_ingress(call, ingress)
                or row["admission_hash"] != hashlib.sha256(address.encode()).hexdigest()
                or row["brief_sha256"] != digest(vars(brief)) or row["worker_kind"] != brief.worker
                or row["workspace_reference"] != str(Path(runtime["workspace_root"]) / address)
                or row["supervisor"] != {"scope": "user", "unit": "friday-rework-worker-" + address[7:39] + ".service"}
                or runtime["runtime_profile"] != ingress["runtime_profile"]
                or row["budget_seconds"] != runtime["budget_seconds"]):
            raise ValueError()
        if host["inputs"] is not None:
            if not isinstance(host["inputs"], list):
                raise ValueError()
            inputs = tuple(VerifiedInput(**item) for item in host["inputs"])
            _inputs_digest(inputs)
            staging = Path(runtime["staging_root"]) / address
            for item in inputs:
                if (Path(item.host_path).parent != staging
                        or item.worker_path != "/job-input/verified/" + Path(item.host_path).name
                        or item.receipt_reference != "association:" + address + "#ingress"):
                    raise ValueError()
        observation = host["observation"]
        if observation is not None:
            from .adapters.contract import NativeObservation
            value = NativeObservation(**observation)
            if value.state not in {"running", "completed", "failed", "stopped", "unknown"}:
                raise ValueError()
            _text(value.evidence_reference, 2048)
            _number(value.elapsed_seconds)
            if row["native"] and (value.invocation_id != row["native"]["invocation_id"]
                                  or value.worker_reference != row["native"]["worker_reference"]):
                raise ValueError()
        terminal = host["terminal"]
        if terminal is not None:
            if (not isinstance(terminal, dict) or set(terminal) != {"state", "evidence_reference", "at_unix"}
                    or terminal["state"] not in {"completed", "failed", "stopped"}):
                raise ValueError()
            _text(terminal["evidence_reference"], 2048)
            _number(terminal["at_unix"])
        quiet = host["quiescence"]
        if quiet is not None:
            if not isinstance(quiet, dict) or set(quiet) != {"kind", "at_unix", "observation"}:
                raise ValueError()
            _number(quiet["at_unix"])
            if quiet["kind"] == "never_submitted":
                if (quiet["observation"] is not None or row["submission_observation"] != "NOT_SUBMITTED"
                        or row["stop_intent"] is None):
                    raise ValueError()
            elif quiet["kind"] == "native":
                observed = UnitObservation(**quiet["observation"])
                if (type(observed.missing) is not bool or type(observed.main_pid) is not int
                        or not observed.quiescent or observed.unit != row["supervisor"]["unit"]
                        or row["native"] and observed.invocation_id not in {"", row["native"]["invocation_id"]}):
                    raise ValueError()
            else:
                raise ValueError()
        if terminal is not None:
            if quiet is None or observation is None or observation["state"] != terminal["state"]:
                raise ValueError()
            if terminal["state"] == "completed" and (row["native"] is None or quiet["kind"] != "native"):
                raise ValueError()
    except Exception as exc:
        raise AssociationError("invalid_host_association") from exc


def quiescence_record(observed, clock):
    if not isinstance(observed, UnitObservation) or not observed.quiescent:
        raise AssociationError("STOP_UNCONFIRMED")
    return {"kind": "native", "at_unix": clock(), "observation": asdict(observed)}
