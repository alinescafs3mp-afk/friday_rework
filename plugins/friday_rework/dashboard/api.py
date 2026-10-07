"""Supported trusted Hermes dashboard API module. Imported without a WorkerHost."""
import importlib.util
from pathlib import Path
import sys
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
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
