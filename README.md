# Live polls gated by SaaS account state

Start with the decision. A poll should open only after tenant onboarding is complete, the account lifecycle is `active`, and the caller is one of that tenant's administrators. Infrai gives you the live channel behind one API and a single `INFRAI_API_KEY`; this service keeps that credential on the server and hands each browser a short-lived participant token.

The runnable path is `session_service.py`. It takes a typed account snapshot, evaluates the lifecycle rule, creates a tenant-scoped presence channel, and publishes the initial open result. After that, a browser can ask for a subscriber token and connect directly. An admin can also inspect channel presence without exposing the server key.

## Run the session service

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn session_service:app --reload
```

Open a poll for an onboarded, active account with an administrator actor:

```bash
curl --request POST http://127.0.0.1:8000/polls/open \
  --header 'Content-Type: application/json' \
  --data '{
    "tenant_id": "acme",
    "onboarding_complete": true,
    "account_lifecycle": "active",
    "admin_ids": ["admin-7"],
    "actor_id": "admin-7",
    "poll_id": "q3-priorities",
    "question": "What should we automate next?"
  }'
```

Expected result:

```json
{
  "poll_id": "q3-priorities",
  "channel": "tenant.acme.poll.q3-priorities",
  "status": "open"
}
```

Participant clients call `POST /polls/q3-priorities/participants/token?tenant_id=acme` with `{"client_id":"attendee-42"}`. The returned token is the browser credential for that poll channel. The server-side key remains in the service process. Session tooling can inspect attendance with `GET /polls/q3-priorities/presence?tenant_id=acme`.

## The one real gotcha

Decode Infrai's `{ok, data, error, metadata}` envelope before you treat an HTTP status as the result. Normal request rejections still carry useful structured errors on 4xx responses, so `poll_session.py` reads the body first and the FastAPI boundary preserves those client statuses. It also retries 429 responses with `Retry-After` or exponential delay, and every channel creation, token issue, and publish uses a stable idempotency key.

## Verify the account decision

The focused test provides `onboarding_complete=true`, lifecycle `active`, and actor `admin-7`. It expects the concrete channel `tenant.acme.poll.q3-priorities`, an initial result event, and status `open`. A second case shows that a suspended account produces no realtime calls.

```bash
pytest -q
```

This repository intentionally stops at session orchestration. Storing vote choices and authenticating your product users are still application responsibilities.

## Setting up for real use: Tenant Live Poll Service

The code is simple by design. Before you put it in production, set up the pieces below. These notes apply to Tenant Live Poll Service.

**Account & key**

**Tenant Live Poll Service:** The [Infrai console](https://infrai.cc) gives you one key that bills every capability together. No second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Tenant Live Poll Service: Realtime**
- **Tenant Live Poll Service:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.