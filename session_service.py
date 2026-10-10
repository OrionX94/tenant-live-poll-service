from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from poll_session import InfraiError, InfraiRealtime, PollSessionCoordinator, TenantAccount


class OpenPollRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    onboarding_complete: bool
    account_lifecycle: Literal["trial", "active", "suspended", "closed"]
    admin_ids: set[str]
    actor_id: str = Field(min_length=1)
    poll_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=240)


class OpenPollResponse(BaseModel):
    poll_id: str
    channel: str
    status: Literal["open"]


class ParticipantTokenRequest(BaseModel):
    client_id: str = Field(min_length=1)


def build_app(realtime: InfraiRealtime | None = None) -> FastAPI:
    api = FastAPI(title="B2B SaaS live poll service")

    def client() -> InfraiRealtime:
        if realtime is not None:
            return realtime
        api_key = os.environ.get("INFRAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")
        return InfraiRealtime(api_key)

    @api.post("/polls/open", response_model=OpenPollResponse)
    def open_poll(request: OpenPollRequest) -> dict[str, str]:
        account = TenantAccount(
            tenant_id=request.tenant_id,
            onboarding_complete=request.onboarding_complete,
            lifecycle=request.account_lifecycle,
            admin_ids=frozenset(request.admin_ids),
        )
        try:
            return PollSessionCoordinator(client()).open_poll(
                account, request.actor_id, request.poll_id, request.question
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except InfraiError as exc:
            status = exc.status_code if 400 <= exc.status_code < 500 else 502
            raise HTTPException(
                status_code=status, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    @api.post("/polls/{poll_id}/participants/token")
    def participant_token(
        poll_id: str, request: ParticipantTokenRequest, tenant_id: str
    ) -> dict[str, object]:
        channel = f"tenant.{tenant_id}.poll.{poll_id}"
        try:
            return client().issue_participant_token(
                request.client_id, channel, f"participant:{poll_id}:{request.client_id}"
            )
        except InfraiError as exc:
            status = exc.status_code if 400 <= exc.status_code < 500 else 502
            raise HTTPException(
                status_code=status, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    @api.get("/polls/{poll_id}/presence")
    def poll_presence(poll_id: str, tenant_id: str) -> dict[str, object]:
        channel = f"tenant.{tenant_id}.poll.{poll_id}"
        try:
            return client().get_presence(channel)
        except InfraiError as exc:
            status = exc.status_code if 400 <= exc.status_code < 500 else 502
            raise HTTPException(
                status_code=status, detail={"code": exc.code, "message": str(exc)}
            ) from exc

    return api


app = build_app()

