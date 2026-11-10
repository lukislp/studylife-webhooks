# StudyLife Webhooks

[![CI](https://github.com/lukislp/studylife-webhooks/actions/workflows/ci.yml/badge.svg)](https://github.com/lukislp/studylife-webhooks/actions/workflows/ci.yml) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/lukislp/studylife-webhooks/badge)](https://scorecard.dev/viewer/?uri=github.com/lukislp/studylife-webhooks) [![CodeQL](https://github.com/lukislp/studylife-webhooks/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/lukislp/studylife-webhooks/security/code-scanning)
[![Release](https://img.shields.io/github/v/release/lukislp/studylife-webhooks)](https://github.com/lukislp/studylife-webhooks/releases)
[![License: AGPL-3.0](https://img.shields.io/github/license/lukislp/studylife-webhooks)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB)](https://www.python.org/)

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
4. When the StudyLife account is deleted, StudyLife calls `DELETE /internal/users/{user_id}` and this
   service removes every registration of that user (idempotent: `{"deleted": n}`, also for a user with
   nothing registered; StudyLife retries it until it gets a 200).

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
| `STUDYLIFE_WEBHOOKS_TLS_CERT_FILE` / `STUDYLIFE_WEBHOOKS_TLS_KEY_FILE` | PEM certificate chain and private key. When both are set, the app is also served over HTTPS (see [TLS](#tls)). Unset (default) is the explicit plain-HTTP opt-out for local runs. |
| `STUDYLIFE_WEBHOOKS_TLS_PORT` | HTTPS port (default `8443`). |
| `STUDYLIFE_WEBHOOKS_TLS_RELOAD_INTERVAL_SECONDS` | How often the certificate files are checked for a renewal (default `300`). |

### TLS

Every call from StudyLife carries the shared secret, so that hop is encrypted. With both TLS files set, [`tls.py`](src/studylife_webhooks/tls.py) starts a second `uvicorn.Server` in the same process that serves the same app over HTTPS on `STUDYLIFE_WEBHOOKS_TLS_PORT`, TLS 1.2 minimum. Only one file set, an unloadable certificate or a port that cannot be bound stops the start, so the service never runs without the TLS listener it was asked for. uvicorn does not reload certificates itself; `tls.py` checks the files periodically and loads a renewed pair into the running listener, so new handshakes use it without a restart.

In k3s the certificate is a cert-manager `Certificate` ([`k8s/05-tls-certificate.yaml`](k8s/05-tls-certificate.yaml), Flux-managed) from StudyLife's internal CA (`studylife-internal-ca-issuer`) for `studylife-webhooks.studylife-webhooks.svc.cluster.local`, `studylife-webhooks.studylife-webhooks.svc` and `studylife-webhooks`. StudyLife validates it against that CA, host name included (`AddonTls:CaCertificatePath`, see StudyLife's [SECURITY-ASSURANCE.md](https://github.com/lukislp/studylife/blob/main/docs/SECURITY-ASSURANCE.md) section 8.3), and with `AddonTls:RequireHttps` refuses `http://` add-on URLs. Port `8000` stays plain HTTP for the kubelet probes and Prometheus.

Rollout order: this repository first (Certificate, port and TLS variables through Flux; the listener starts with the release image), then the updated `k8s/04-network-policies.yaml` applied by hand (it only adds `8443`), then StudyLife's switch of `StudyLifeWebhooks__BaseUrl` to `https://studylife-webhooks.studylife-webhooks.svc.cluster.local:8443`.

## Development

```
uv sync
uv run pytest
uv run uvicorn studylife_webhooks.main:app --reload
```

## License

AGPL-3.0 - see [LICENSE](LICENSE).
