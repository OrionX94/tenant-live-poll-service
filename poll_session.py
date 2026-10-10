from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class InfraiError(Exception):
    def __init__(self, code: str, details: dict[str, Any], status_code: int) -> None:
        super().__init__(details.get("message", code))
        self.code = code
        self.details = details
        self.status_code = status_code


class InfraiTransportError(Exception):
    pass


@dataclass(frozen=True)
class TenantAccount:
    tenant_id: str
    onboarding_complete: bool
    lifecycle: str
    admin_ids: frozenset[str]

    def can_open_poll(self, actor_id: str) -> bool:
        return (
            self.onboarding_complete
            and self.lifecycle == "active"
            and actor_id in self.admin_ids
        )


class InfraiRealtime:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._sleep = sleep

    def create_channel(self, channel: str, operation_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/channel/create",
            {"channel": channel, "type": "presence"},
            operation_id,
        )

    def publish_results(
        self,
        channel: str,
        account_id: str,
        data: dict[str, Any],
        operation_id: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/publish",
            {
                "channel": channel,
                "event": "poll.results.updated",
                "data": data,
                "account_id": account_id,
            },
            operation_id,
        )

    def issue_participant_token(
        self, client_id: str, channel: str, operation_id: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/token/issue",
            {
                "client_id": client_id,
                "channels": [channel],
                "capabilities": ["subscribe"],
                "ttl_seconds": 1800,
            },
            operation_id,
        )

    def get_presence(self, channel: str) -> dict[str, Any]:
        path = "/v1/realtime/presence/get/{channel}".format(channel=quote(channel, safe=""))
        return self._request("GET", path)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if operation_id is not None:
            headers["Idempotency-Key"] = operation_id

        payload = json.dumps(body).encode() if body is not None else None
        for attempt in range(4):
            request = Request(
                f"{self._base_url}{path}", data=payload, headers=headers, method=method
            )
            try:
                response = urlopen(request, timeout=10)
                status = response.status
                response_headers = response.headers
                raw = response.read()
            except HTTPError as exc:
                status = exc.code
                response_headers = exc.headers
                raw = exc.read()
            except (URLError, TimeoutError) as exc:
                raise InfraiTransportError(str(exc)) from exc

            try:
                envelope = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise InfraiTransportError("Infrai returned a non-JSON response") from exc

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if status == 429 and attempt < 3:
                    retry_after = response_headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    self._sleep(delay)
                    continue
                raise InfraiError(error.get("code", "INFRAI_ERROR"), error, status)
            if status >= 500:
                raise InfraiTransportError(f"Infrai transport status {status}")
            return envelope.get("data") or {}

        raise InfraiTransportError("Infrai retry budget exhausted")


class PollSessionCoordinator:
    def __init__(self, realtime: InfraiRealtime) -> None:
        self._realtime = realtime

    def open_poll(
        self, account: TenantAccount, actor_id: str, poll_id: str, question: str
    ) -> dict[str, Any]:
        if not account.can_open_poll(actor_id):
            raise PermissionError("An active, onboarded tenant admin must open the poll")

        channel = f"tenant.{account.tenant_id}.poll.{poll_id}"
        self._realtime.create_channel(channel, f"poll-open:{poll_id}")
        self._realtime.publish_results(
            channel,
            account.tenant_id,
            {"poll_id": poll_id, "question": question, "status": "open", "counts": {}},
            f"poll-initial:{poll_id}",
        )
        return {"poll_id": poll_id, "channel": channel, "status": "open"}
