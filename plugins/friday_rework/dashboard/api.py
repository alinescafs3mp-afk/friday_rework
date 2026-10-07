"""Supported trusted Hermes dashboard API module. Imported without a WorkerHost."""
import importlib.util
from pathlib import Path
import sys
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, SecretStr
from hermes_cli.friday_product_access import admin_policy, session_allowed

# The dashboard importer loads api.py by file location, outside the agent plugin
# namespace. Load the package definitions once; register(ctx) is never called.
_name = "_friday_dashboard_projection"
if _name not in sys.modules:
    _root = Path(__file__).resolve().parents[1]
    _spec = importlib.util.spec_from_file_location(_name, _root / "__init__.py", submodule_search_locations=[str(_root)])
    _package = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _package
    try:
        _spec.loader.exec_module(_package)
    except Exception:
        sys.modules.pop(_name, None)
        raise
from _friday_dashboard_projection.admin import Administration, masked


def require_admin(request: Request):
    try:
        allowed = (admin_policy() is not None and getattr(request.app.state, "auth_required", False) is True
                   and session_allowed(getattr(request.state, "session", None)))
    except Exception:
        allowed = False
    if not allowed:
        raise HTTPException(403, "product_admin_required")

    return request.state.session


router = APIRouter(dependencies=[Depends(require_admin)])
_admin = Administration()


def call(method, *args, **kwargs):
    try:
        return masked(method(*args, **kwargs))
    except PermissionError as exc:
        if str(exc) == "receiving_transport_authority_required":
            raise HTTPException(403, "receiving_transport_authority_required_select_receiving_profile") from None
        raise HTTPException(403, "product_scope_refused") from None
    except (ValueError, KeyError, IndexError):
        raise HTTPException(400, "invalid_or_unproved_product_reference") from None
    except Exception:
        raise HTTPException(503, "native_state_unavailable_or_write_unconfirmed") from None


class UserChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str = Field(min_length=1, max_length=64)
    transport_profile: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=512)
    user_id: str = Field(min_length=1, max_length=512)
    enabled: StrictBool
    role: Literal["user", "admin"]


class PairApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str = Field(min_length=1, max_length=64)
    transport_profile: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=512)
    request_id: str = Field(min_length=1, max_length=128)


class TaskControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["status", "pause", "cancel"]


class SettingsChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: Literal["model", "web", "toolset", "skill", "operational"]
    values: dict = Field(max_length=8)


class ScheduleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume"]


@router.get("/profiles")
def profiles():
    return call(_admin.profiles)


@router.get("/users")
def users(profile: str):
    return call(_admin.users, profile)


@router.put("/users")
def change_user(body: UserChange, profile: str):
    return call(_admin.set_user, profile, **body.model_dump())


@router.get("/pairing")
def pairing(profile: str):
    return call(_admin.pairing, profile)


@router.post("/pairing/approve")
def approve(body: PairApproval, profile: str):
    return call(_admin.approve, profile, **body.model_dump())


@router.get("/conversations")
def conversations(profile: str, query: str = Query("", max_length=512), limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0, le=100000),
                  platform: str = Query("", max_length=512), user_id: str = Query("", max_length=512), account_id: str = Query("", max_length=512),
                  chat_id: str = Query("", max_length=512), thread_id: str = Query("", max_length=512)):
    filters = {k: v for k, v in dict(platform=platform, user_id=user_id, account_id=account_id, chat_id=chat_id, thread_id=thread_id).items() if v}
    return call(_admin.conversations, profile, query=query, limit=limit, offset=offset, filters=filters)


@router.get("/conversations/{session_id}")
def conversation(session_id: str, profile: str, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0, le=100000)):
    return call(_admin.conversation, profile, session_id, limit=limit, offset=offset)


@router.get("/tasks")
def tasks(profile: str):
    return call(_admin.tasks, profile)


@router.post("/tasks/{task_id}/control")
def task_control(task_id: str, body: TaskControl, profile: str, session=Depends(require_admin)):
    return call(_admin.control, profile, session, task_id, body.action)


@router.put("/settings")
def settings_change(body: SettingsChange, profile: str, session=Depends(require_admin)):
    return call(_admin.write_settings, profile, body.model_dump(), session)


@router.get("/schedules")
def schedules(profile: str):
    return call(_admin.schedules, profile)


@router.post("/schedules/{job_id}/control")
def schedule_control(job_id: str, body: ScheduleChange, profile: str, session=Depends(require_admin)):
    return call(_admin.schedules, profile, body.action, job_id, session)


@router.get("/attachments/{task_id}/{index}")
def attachment(task_id: str, index: int, profile: str):
    try:
        payload = _admin.attachment(profile, task_id, index)
    except PermissionError:
        raise HTTPException(403, "product_scope_refused") from None
    except Exception:
        raise HTTPException(400, "attachment_ownership_or_bytes_unproved") from None
    return Response(payload, media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename=friday-output.bin",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.get("/effective")
def effective(profile: str):
    return call(_admin.effective, profile)


@router.get("/inputs/{task_id}/{index}")
def input_attachment(task_id: str, index: int, profile: str):
    try:
        payload = _admin.input_attachment(profile, task_id, index)
    except PermissionError:
        raise HTTPException(403, "product_scope_refused") from None
    except Exception:
        raise HTTPException(400, "attachment_ownership_or_bytes_unproved") from None
    return Response(payload, media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename=friday-input.bin",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


class OnboardingIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str = Field(min_length=1, max_length=64)
    transport_profile: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=512)
    user_id: str = Field(min_length=1, max_length=512)
    expected_config_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class OnboardingPrepare(OnboardingIdentity):
    template: str = Field(min_length=1, max_length=64)
    runtime_profile: str = Field(pattern="^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class OnboardingActivate(OnboardingIdentity):
    generation: StrictInt = Field(ge=1)


class OnboardingCredential(OnboardingActivate):
    name: str = Field(pattern="^[A-Z][A-Z0-9_]{0,127}$")
    value: SecretStr


@router.get("/onboarding")
def onboarding_templates(profile: str):
    return call(_admin.onboarding_templates, profile)


@router.post("/onboarding/prepare")
def onboarding_prepare(body: OnboardingPrepare, profile: str, session=Depends(require_admin)):
    return call(_admin.onboarding_prepare, profile, session=session, **body.model_dump())


@router.put("/onboarding/credentials")
def onboarding_credentials(body: OnboardingCredential, profile: str, session=Depends(require_admin)):
    values = body.model_dump(); values["value"] = body.value.get_secret_value()
    return call(_admin.onboarding_credentials, profile, session=session, **values)


@router.post("/onboarding/activate")
def onboarding_activate(body: OnboardingActivate, profile: str, session=Depends(require_admin)):
    return call(_admin.onboarding_activate, profile, session=session, **body.model_dump())


class WorkerPrepare(OnboardingActivate):
    worker: Literal['dsh', 'a0']
    runtime: dict
    a0_network: dict | None = None


class WorkerConfigure(OnboardingActivate):
    worker: Literal['dsh', 'a0']
    preparation: dict
    runtime_receipt: dict


@router.post('/onboarding/worker/prepare')
def onboarding_worker_prepare(body: WorkerPrepare, profile: str, session=Depends(require_admin)):
    return call(_admin.onboarding_worker_prepare, profile, session=session, **body.model_dump())


@router.post('/onboarding/worker/configure')
def onboarding_worker_configure(body: WorkerConfigure, profile: str, session=Depends(require_admin)):
    return call(_admin.onboarding_worker_configure, profile, session=session, **body.model_dump())
