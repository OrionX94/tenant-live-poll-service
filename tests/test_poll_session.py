from poll_session import PollSessionCoordinator, TenantAccount


class RecordingRealtime:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def create_channel(self, channel: str, operation_id: str) -> dict[str, object]:
        self.calls.append(("create", channel, operation_id))
        return {"channel": channel}

    def publish_results(
        self,
        channel: str,
        account_id: str,
        data: dict[str, object],
        operation_id: str,
    ) -> dict[str, object]:
        self.calls.append(("publish", channel, account_id, data, operation_id))
        return {"published": True}


def test_active_onboarded_admin_opens_tenant_scoped_poll() -> None:
    realtime = RecordingRealtime()
    account = TenantAccount("acme", True, "active", frozenset({"admin-7"}))

    result = PollSessionCoordinator(realtime).open_poll(
        account, "admin-7", "q3-priorities", "What should we automate next?"
    )

    assert result == {
        "poll_id": "q3-priorities",
        "channel": "tenant.acme.poll.q3-priorities",
        "status": "open",
    }
    assert realtime.calls[0] == (
        "create",
        "tenant.acme.poll.q3-priorities",
        "poll-open:q3-priorities",
    )
    assert realtime.calls[1][3] == {
        "poll_id": "q3-priorities",
        "question": "What should we automate next?",
        "status": "open",
        "counts": {},
    }


def test_suspended_account_cannot_open_poll() -> None:
    realtime = RecordingRealtime()
    account = TenantAccount("acme", True, "suspended", frozenset({"admin-7"}))

    try:
        PollSessionCoordinator(realtime).open_poll(
            account, "admin-7", "q3-priorities", "What should we automate next?"
        )
    except PermissionError as exc:
        assert "active" in str(exc)
    else:
        raise AssertionError("suspended account was allowed to open a poll")

    assert realtime.calls == []

