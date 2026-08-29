# StudyLife Webhooks

A small microservice extending [StudyLife](https://github.com/lukislp/studylife) with outbound
webhooks: register a target URL and a list of event types, and this service fires a signed HTTP
`POST` to it whenever one of those events happens - session started/completed/deleted, a new
personal record, a focus timer starting/ending. Point it at Zapier, n8n, a Discord webhook, or
anything else you can give a URL to.

## How it works

1. In StudyLife's own Setup page, add a webhook: a target URL and which events you want (or
   `"*"` for everything - this service never validates event names against a closed list, so a
   brand-new event type on the StudyLife side works here without any update to this service).
2. StudyLife's backend calls this service's `/internal/*` endpoints on your behalf (session-
   authenticated on the StudyLife side, authenticated to this service by one shared secret) -
   you never talk to this service directly.
3. When something happens, StudyLife tells this service, and this service delivers a signed
   `POST` to every matching registration concurrently (one slow/unreachable subscriber never
   delays another's delivery).

## Delivery payload

```json
{
  "event_type": "session.completed",
  "occurred_at": "2026-08-29T12:00:00Z",
  "payload": { "sessionId": 42, "courseName": "Analysis II", "durationMinutes": 52.0 }
}
```

Each delivery carries an `X-StudyLife-Webhook-Signature` header - a hex HMAC-SHA256 of the exact
raw request body, keyed with the webhook's own secret (shown once, at creation time, the same
"plaintext exactly once" pattern StudyLife itself uses for API keys). Verify it before trusting
the payload:

```python
import hashlib, hmac

expected = hmac.new(secret.encode(), request_body_bytes, hashlib.sha256).hexdigest()
hmac.compare_digest(expected, request.headers["X-StudyLife-Webhook-Signature"])
```

## Configuration

| Env var | Description |
| --- | --- |
| `STUDYLIFE_WEBHOOKS_SHARED_SECRET` | Must match the `studylife` repo's `StudyLifeWebhooks:SharedSecret` exactly - authenticates every `/internal/*` call as genuinely coming from StudyLife. |
| `STUDYLIFE_WEBHOOKS_DB_PATH` | SQLite file for registration state (default `webhooks.db`). This service's own state - StudyLife never stores a copy of it. |
| `STUDYLIFE_WEBHOOKS_DELIVERY_TIMEOUT_SECONDS` | Per-delivery HTTP timeout (default `5.0`). |

## Development

```
uv sync
uv run pytest
uv run uvicorn studylife_webhooks.main:app --reload
```

## License

AGPL-3.0 - see [LICENSE](LICENSE).
