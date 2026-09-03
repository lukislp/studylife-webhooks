"""studylife-webhooks: a small microservice extending StudyLife (see
github.com/lukislp/studylife) so external automations (Zapier, n8n, Discord, etc.) can react to
StudyLife events over plain signed HTTP callbacks, instead of StudyLife needing a bespoke
integration per destination.

Every /internal/* route is authenticated by one flat shared secret (X-StudyLife-Shared-Secret,
see require_shared_secret below) - the same pattern StudyLife's own AiProxyClient uses for its
/internal/* calls to studylife-ai (register-key/revoke-key), not the more elaborate per-request
signed proxy token that /chat|/agent needs (there is no per-request user-impersonation concern
here: every call already carries its own explicit user_id in the body/query).

Deliberately does NOT validate event_type/events against a closed catalog anywhere in this
service - it only ever does a plain string match between a registration's stored `events` list
and whatever `event_type` arrives in POST /internal/events (see db.find_subscribers). StudyLife's
own WebhookEventTypes catalog is documentation for callers, not a contract this service enforces
- a brand-new event type on the StudyLife side needs no corresponding change here at all, which
is the whole point of "theoretically subscribe to anything" instead of one hardcoded event.
"""

import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from studylife_webhooks import db
from studylife_webhooks.config import settings
from studylife_webhooks.delivery import deliver_all
from studylife_webhooks.metrics import (
    REQUEST_DURATION_SECONDS,
    REQUESTS_TOTAL,
    render_latest,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="studylife-webhooks", lifespan=lifespan)


@app.middleware("http")
async def record_request_metrics(request: Request, call_next):
    """Times every request and records it under the matched route TEMPLATE, not the raw path -
    request.scope["route"] is only populated once routing has resolved the request, so it's
    read AFTER call_next() returns, not before. A 404 (no route matched at all) falls back to
    the fixed "unmatched" label instead of the raw path - otherwise a webhook_id typo'd into
    the URL, or the id of a webhook that was since deleted, would create a fresh label value
    per request, which is exactly the unbounded-cardinality problem route templates avoid."""
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    route = request.scope.get("route")
    route_label = route.path if route is not None else "unmatched"
    status_class = f"{response.status_code // 100}xx"

    REQUEST_DURATION_SECONDS.labels(route=route_label, method=request.method).observe(
        duration
    )
    REQUESTS_TOTAL.labels(
        route=route_label, method=request.method, status_class=status_class
    ).inc()

    return response


@app.get("/metrics")
def metrics() -> Response:
    body, content_type = render_latest()
    return Response(body, media_type=content_type)


def require_shared_secret(
    x_studylife_shared_secret: Annotated[str | None, Header()] = None,
) -> None:
    if (
        not settings.shared_secret
        or x_studylife_shared_secret != settings.shared_secret
    ):
        raise HTTPException(
            status_code=401, detail="Invalid or missing X-StudyLife-Shared-Secret"
        )


class WebhookOut(BaseModel):
    id: str
    target_url: str
    events: list[str]
    created_at: str
    # secret is deliberately NEVER included here - only CreateWebhookOut (the one-time creation
    # response) ever returns it, same "show the plaintext exactly once" pattern StudyLife itself
    # uses for API keys.

    @classmethod
    def from_webhook(cls, w: db.Webhook) -> "WebhookOut":
        return cls(
            id=w.id, target_url=w.target_url, events=w.events, created_at=w.created_at
        )


class CreateWebhookIn(BaseModel):
    user_id: int
    target_url: str = Field(min_length=1)
    events: list[str] = Field(min_length=1)


class CreateWebhookOut(WebhookOut):
    secret: str


class PublishEventIn(BaseModel):
    user_id: int
    event_type: str
    occurred_at: str
    payload: dict = Field(default_factory=dict)


class PublishEventOut(BaseModel):
    delivered: int
    failed: int


@app.get("/internal/webhooks", dependencies=[Depends(require_shared_secret)])
def list_webhooks(user_id: Annotated[int, Query()]) -> list[WebhookOut]:
    return [WebhookOut.from_webhook(w) for w in db.list_webhooks(user_id)]


@app.post("/internal/webhooks", dependencies=[Depends(require_shared_secret)])
def create_webhook(body: CreateWebhookIn) -> CreateWebhookOut:
    webhook = db.create_webhook(body.user_id, body.target_url, body.events)
    return CreateWebhookOut(
        id=webhook.id,
        target_url=webhook.target_url,
        events=webhook.events,
        created_at=webhook.created_at,
        secret=webhook.secret,
    )


@app.delete(
    "/internal/webhooks/{webhook_id}", dependencies=[Depends(require_shared_secret)]
)
def delete_webhook(webhook_id: str, user_id: Annotated[int, Query()]) -> None:
    if not db.delete_webhook(user_id, webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found")


@app.post("/internal/events", dependencies=[Depends(require_shared_secret)])
async def publish_event(body: PublishEventIn) -> PublishEventOut:
    subscribers = db.find_subscribers(body.user_id, body.event_type)
    results = await deliver_all(
        subscribers, body.event_type, body.occurred_at, body.payload
    )
    delivered = sum(1 for r in results if r.delivered)
    return PublishEventOut(delivered=delivered, failed=len(results) - delivered)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
