"""Outgoing delivery to a user's own target_url - signed with that webhook's own secret so the
receiving end can verify the payload genuinely came from here, not just anyone who guessed the
URL. Deliveries for the same event fan out concurrently (asyncio.gather) so one slow/unreachable
subscriber can't delay another's delivery, bounded by Settings.delivery_timeout_seconds so a
dead subscriber can't stall the whole /internal/events call either.

target_url is user input and this service runs inside the cluster, so every delivery goes through
egress.VettedTransport: the host is resolved and vetted at connect time and the socket only ever
reaches a public address (2026-11-16 audit M4). Redirects are not followed and no environment
proxy is used."""

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

import httpx

from studylife_webhooks.config import settings
from studylife_webhooks.db import Webhook
from studylife_webhooks.egress import VettedTransport, is_address_rejection
from studylife_webhooks.metrics import (
    DELIVERIES_TOTAL,
    UPSTREAM_REQUEST_DURATION_SECONDS,
    UPSTREAM_REQUESTS_TOTAL,
)

# Fixed label value for every outbound delivery - target_url is an arbitrary user-configured
# URL with unbounded cardinality, so it never becomes a metric label (see metrics.py's module
# docstring).
_TARGET_LABEL = "webhook-target"


@dataclass
class DeliveryResult:
    webhook_id: str
    delivered: bool
    status_code: int | None = None
    error: str | None = None


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def deliver_one(
    webhook: Webhook,
    event_type: str,
    occurred_at: str,
    payload: dict,
    transport: httpx.AsyncBaseTransport | None = None,
) -> DeliveryResult:
    """transport is injectable purely for tests (httpx.MockTransport, or a VettedTransport with
    a fake resolver) - real callers use the default, a VettedTransport on system DNS."""
    # user_id names the webhook's owner and sits inside the signed body, so the signature also
    # proves whose event this is - a receiver shared by several users (e.g. a chat bot) needs it.
    body = json.dumps(
        {
            "event_type": event_type,
            "occurred_at": occurred_at,
            "user_id": webhook.user_id,
            "payload": payload,
        }
    ).encode()
    signature = sign_payload(webhook.secret, body)
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=settings.delivery_timeout_seconds,
            transport=transport or VettedTransport(),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                webhook.target_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    # Same naming convention as GitHub/Stripe-style webhooks - a hex HMAC-SHA256
                    # of the exact raw body sent, so the receiver can verify it without needing
                    # to re-serialize (and potentially reorder/reformat) the JSON themselves.
                    "X-StudyLife-Webhook-Signature": signature,
                },
            )
    except httpx.TimeoutException as exc:
        # Must be checked before the generic httpx.HTTPError below - TimeoutException is a
        # subclass of it, and "the subscriber never responded in time" is worth telling apart
        # from other network failures (e.g. connection refused).
        _record_upstream(start, outcome="timeout")
        DELIVERIES_TOTAL.labels(outcome="failed").inc()
        return DeliveryResult(webhook_id=webhook.id, delivered=False, error=str(exc))
    except httpx.HTTPError as exc:
        # "blocked": the target resolved to a non-public address and no connection was opened.
        _record_upstream(start, outcome="blocked" if is_address_rejection(exc) else "failed")
        DELIVERIES_TOTAL.labels(outcome="failed").inc()
        return DeliveryResult(webhook_id=webhook.id, delivered=False, error=str(exc))

    _record_upstream(start, outcome="ok" if response.is_success else "http_error")
    DELIVERIES_TOTAL.labels(outcome="delivered" if response.is_success else "failed").inc()
    return DeliveryResult(
        webhook_id=webhook.id,
        delivered=response.is_success,
        status_code=response.status_code,
    )


def _record_upstream(start: float, outcome: str) -> None:
    UPSTREAM_REQUEST_DURATION_SECONDS.labels(target=_TARGET_LABEL).observe(
        time.perf_counter() - start
    )
    UPSTREAM_REQUESTS_TOTAL.labels(target=_TARGET_LABEL, outcome=outcome).inc()


async def deliver_all(
    webhooks: list[Webhook],
    event_type: str,
    occurred_at: str,
    payload: dict,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[DeliveryResult]:
    if not webhooks:
        return []
    return await asyncio.gather(
        *(deliver_one(w, event_type, occurred_at, payload, transport) for w in webhooks)
    )
