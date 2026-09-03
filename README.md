# StudyLife Webhooks

A small microservice extending [StudyLife](https://github.com/lukislp/studylife) with outbound
webhooks: register a target URL and a list of event types, and this service fires a signed HTTP
`POST` to it whenever one of those events happens - sessions, notes, course goals, session
templates, course resources, custom study programs, the exam planner, and more (see "Event
types" below). Point it at Zapier, n8n, a Discord webhook, or anything else you can give a URL to.

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

## Event types

The canonical, up-to-date list lives in `WebhookEventTypes.cs` in the `studylife` repo (every
call site fires one of these) - this service itself never validates against it, it only matches
a registration's `events` list against whatever `event_type` string arrives, so a brand-new
event type on the StudyLife side never needs a change here. Subscribe to individual types or
`"*"` for everything.

| Event type | Fires when |
| --- | --- |
| `timer.started` | A timer/focus session starts running |
| `timer.ended` | A running timer pauses, resets, or completes |
| `session.created` | A study session is logged |
| `session.completed` | A study session is marked completed |
| `session.deleted` | A study session is deleted |
| `new_record.set` | A new personal longest-session record is set |
| `note.created` | A note is created |
| `note.updated` | A note is edited |
| `note.deleted` | A note is deleted |
| `course_goal.created` | A grade/deadline goal is set for a course for the first time |
| `course_goal.updated` | An existing course goal is edited |
| `course_goal.completed` | A course goal's completion date is set (fires alongside created/updated) |
| `course_goal.deleted` | A course goal is deleted |
| `course_resource.created` | A resource link is added to a course |
| `course_resource.deleted` | A course resource is deleted |
| `session_template.created` | A reusable session template is created |
| `session_template.deleted` | A session template is deleted |
| `study_program.created` | A custom study program is created |
| `study_program.completed` | A custom study program is manually marked completed |
| `study_program.deleted` | A custom study program is deleted |
| `plan.generated` | The exam planner generates a batch of study sessions |

## Metrics

`GET /metrics` (no auth, same port as everything else) exposes Prometheus metrics: HTTP request
duration/count for every route (labeled by the matched route *template*, e.g.
`/internal/webhooks/{webhook_id}` - never the raw path, so a real webhook id never becomes a
label value) plus outbound delivery outcomes to subscribers' own target URLs (labeled with a
fixed `webhook-target` value, never the actual URL, which is arbitrary and user-configured -
unbounded cardinality otherwise).

| Metric | Type | Labels | Shows |
| --- | --- | --- | --- |
| `studylife_webhooks_request_duration_seconds` | Histogram | `route`, `method` | HTTP latency per route |
| `studylife_webhooks_requests_total` | Counter | `route`, `method`, `status_class` | HTTP request volume by outcome |
| `studylife_webhooks_upstream_requests_total` | Counter | `target`, `outcome` (`ok`/`http_error`/`failed`/`timeout`) | Outbound delivery attempts by outcome |
| `studylife_webhooks_upstream_request_duration_seconds` | Histogram | `target` | Outbound delivery latency |
| `studylife_webhooks_deliveries_total` | Counter | `outcome` (`delivered`/`failed`) | Overall delivery success rate |

No `delivery_attempts` histogram - `deliver_all` makes a single attempt per subscriber with no
retry mechanism, so there's nothing to count attempts of yet.

Scraped by the homelab's existing self-hosted Prometheus (`homelab-infra` repo,
`monitoring/01-prometheus.yaml`) - a `studylife-webhooks` scrape job is being added there as
part of the same rollout that instrumented this service.

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
