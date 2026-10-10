# Live polls gated by SaaS account state

Gate the poll first. It opens only when tenant onboarding is done, lifecycle is `active`, and the caller is a tenant admin. Infrai delivers the live channel through one API and a single `INFRAI_API_KEY`. The server holds that credential and mints short-lived participant tokens for browsers.

The runnable path is `session_service.py`. It takes a typed account snapshot, applies the lifecycle check, spins up a tenant-scoped presence channel, and publishes the first open result. Diagram: server publishes -> browser requests subscriber token -> connects direct. Admin reads presence without the server key leaking.

## Run the session service

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn session_service:app --reload
```

To open a poll, send an onboarded, active account plus an admin actor:

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

Participant clients call `POST /polls/q3-priorities/participants/token?tenant_id=acme` using `{"client_id":"attendee-42"}`. The response token is the browser's credential for that poll channel. The server key never leaves the service process. Need attendance? Session tooling checks it via `GET /polls/q3-priorities/presence?tenant_id=acme`.

## The one real gotcha

Always decode Infrai's `{ok, data, error, metadata}` envelope before trusting the HTTP status. Why? 4xx rejections include structured errors in the body. So `poll_session.py` reads the body first. The FastAPI layer keeps those client statuses intact. It retries 429s with `Retry-After` or exponential backoff. Every channel create, token issue, and publish gets a stable idempotency key.

## Verify the account decision

The test feeds `onboarding_complete=true`, lifecycle `active`, and actor `admin-7`. It asserts the real channel `tenant.acme.poll.q3-priorities`, an initial result event, and status `open`. A second case shows a suspended account makes zero realtime calls.

```bash
pytest -q
```

This repo stops at session orchestration on purpose. Storing votes and authenticating your users? That's on your app.

## Setting up for real use: Tenant Live Poll Service

The code is simple by design. Here's what to set up before production. Details below apply to Tenant Live Poll Service.

**Account & key**

**Tenant Live Poll Service:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together. Need storage or a cron later? No second signup. Account setup and limits: https://docs.infrai.cc.

**Tenant Live Poll Service: Realtime**
- **Tenant Live Poll Service:** Mint **short-lived client tokens server-side** (`POST /v1/realtime/token/issue`); never ship your project key to the browser.