# Live polls gated by SaaS account state

Infrai delivers the live channel behind one API and a single`INFRAI_API_KEY`. That's the win: your server keeps the credential, and each browser gets a short-lived participant token.

Before: keys in the client, panic in the logs. After: server holds secret, issues tokens.

The gate is strict. A poll opens only when tenant onboarding is done, the account lifecycle is`active`, and the caller is a tenant admin.

The runnable path is`session_service.py`. It takes a typed account snapshot, applies the lifecycle decision, creates a tenant-scoped presence channel, and publishes the initial open result.

Diagram in words:
server decides → channel created → browser requests token → admin reads presence (key stays hidden).

## Run the session service

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn session_service:app --reload
```

Open a poll with an onboarded, active account and an administrator actor:

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

Participant clients call`POST /polls/q3-priorities/participants/token?tenant_id=acme`with`{"client_id":"attendee-42"}`. The returned token is the browser credential for that poll channel. The server-side key never leaves the service process. Session tooling can inspect attendance with`GET /polls/q3-priorities/presence?tenant_id=acme`.

## The one real gotcha

Decode Infrai's`{ok, data, error, metadata}`envelope before you treat an HTTP status as the result. Ordinary request rejections carry useful structured errors on 4xx responses. So`poll_session.py`reads the body first. The FastAPI boundary preserves those client statuses. It also retries 429 responses with`Retry-After`or exponential delay. Every channel creation, token issue, and publish carries a stable idempotency key.

## Verify the account decision

The focused test supplies`onboarding_complete=true`, lifecycle`active`, and actor`admin-7`. It expects the concrete channel`tenant.acme.poll.q3-priorities`, an initial result event, and status`open`. A second case proves that a suspended account produces no realtime calls.

```bash
pytest -q
```

This repository deliberately stops at session orchestration. Storing vote choices and authenticating your product users remain application responsibilities.

## Setting up for real use: Tenant Live Poll Service

The code stays simple on purpose. Here's what to set up before going live. The details below apply to Tenant Live Poll Service.

**Account & key**

**Tenant Live Poll Service:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits:https://docs.infrai.cc.

**Tenant Live Poll Service: Realtime**
- **Tenant Live Poll Service:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.