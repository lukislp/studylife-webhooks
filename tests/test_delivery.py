import hashlib
import hmac
import json

import httpx

from studylife_webhooks.db import Webhook
from studylife_webhooks.delivery import deliver_all, deliver_one, sign_payload
from studylife_webhooks.metrics import DELIVERIES_TOTAL, UPSTREAM_REQUESTS_TOTAL


def _counter_value(counter, **labels) -> float:
    """prometheus_client counters are process-global, so tests read a before/after delta
    rather than asserting an absolute value - other tests in this process may already have
    incremented the same label combination."""
    return counter.labels(**labels)._value.get()


def _webhook(
    target_url: str = "https://example.com/hook", secret: str = "shh"
) -> Webhook:
    return Webhook(
        id="w1",
        user_id=1,
        target_url=target_url,
        events=["session.completed"],
        secret=secret,
        created_at="2026-01-01T00:00:00Z",
    )


def test_sign_payload_matches_manual_hmac():
    body = b'{"a":1}'
    expected = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert sign_payload("secret", body) == expected


async def test_deliver_one_success_sends_signature_header_and_body():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = request.content
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    webhook = _webhook(secret="my-secret")

    result = await deliver_one(
        webhook,
        "session.completed",
        "2026-08-29T12:00:00Z",
        {"sessionId": 42},
        transport=transport,
    )

    assert result.delivered is True
    assert result.status_code == 200
    expected_signature = sign_payload("my-secret", captured["body"])
    assert captured["headers"]["x-studylife-webhook-signature"] == expected_signature
    body = json.loads(captured["body"])
    assert body == {
        "event_type": "session.completed",
        "occurred_at": "2026-08-29T12:00:00Z",
        "payload": {"sessionId": 42},
    }


async def test_deliver_one_non_success_status_is_not_delivered():
    transport = httpx.MockTransport(lambda request: httpx.Response(500))

    result = await deliver_one(
        _webhook(), "session.completed", "2026-08-29T12:00:00Z", {}, transport=transport
    )

    assert result.delivered is False
    assert result.status_code == 500


async def test_deliver_one_network_failure_does_not_raise():
    def handler(request: httpx.Request):
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(handler)

    result = await deliver_one(
        _webhook(), "session.completed", "2026-08-29T12:00:00Z", {}, transport=transport
    )

    assert result.delivered is False
    assert result.error is not None


async def test_deliver_all_empty_list_returns_empty():
    assert await deliver_all([], "session.completed", "2026-08-29T12:00:00Z", {}) == []


async def test_deliver_one_success_increments_ok_and_delivered_metrics():
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    before_upstream = _counter_value(
        UPSTREAM_REQUESTS_TOTAL, target="webhook-target", outcome="ok"
    )
    before_delivered = _counter_value(DELIVERIES_TOTAL, outcome="delivered")

    await deliver_one(
        _webhook(), "session.completed", "2026-08-29T12:00:00Z", {}, transport=transport
    )

    assert (
        _counter_value(UPSTREAM_REQUESTS_TOTAL, target="webhook-target", outcome="ok")
        == before_upstream + 1
    )
    assert _counter_value(DELIVERIES_TOTAL, outcome="delivered") == before_delivered + 1


async def test_deliver_one_non_success_increments_http_error_and_failed_metrics():
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    before_upstream = _counter_value(
        UPSTREAM_REQUESTS_TOTAL, target="webhook-target", outcome="http_error"
    )
    before_failed = _counter_value(DELIVERIES_TOTAL, outcome="failed")

    await deliver_one(
        _webhook(), "session.completed", "2026-08-29T12:00:00Z", {}, transport=transport
    )

    assert (
        _counter_value(
            UPSTREAM_REQUESTS_TOTAL, target="webhook-target", outcome="http_error"
        )
        == before_upstream + 1
    )
    assert _counter_value(DELIVERIES_TOTAL, outcome="failed") == before_failed + 1


async def test_deliver_one_timeout_increments_timeout_metric_not_failed():
    def handler(request: httpx.Request):
        raise httpx.TimeoutException("timed out", request=request)

    transport = httpx.MockTransport(handler)
    before_timeout = _counter_value(
        UPSTREAM_REQUESTS_TOTAL, target="webhook-target", outcome="timeout"
    )
    before_failed = _counter_value(
        UPSTREAM_REQUESTS_TOTAL, target="webhook-target", outcome="failed"
    )

    await deliver_one(
        _webhook(), "session.completed", "2026-08-29T12:00:00Z", {}, transport=transport
    )

    assert (
        _counter_value(
            UPSTREAM_REQUESTS_TOTAL, target="webhook-target", outcome="timeout"
        )
        == before_timeout + 1
    )
    # Not double-counted under the generic "failed" outcome too - TimeoutException must be
    # caught before the broader httpx.HTTPError branch.
    assert (
        _counter_value(
            UPSTREAM_REQUESTS_TOTAL, target="webhook-target", outcome="failed"
        )
        == before_failed
    )


async def test_deliver_all_delivers_to_every_subscriber_independently():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200 if "a.test" in str(request.url) else 500)

    transport = httpx.MockTransport(handler)
    webhooks = [
        _webhook(target_url="https://a.test"),
        _webhook(target_url="https://b.test"),
    ]

    results = await deliver_all(
        webhooks, "session.completed", "2026-08-29T12:00:00Z", {}, transport=transport
    )

    assert len(calls) == 2
    assert sum(1 for r in results if r.delivered) == 1
    assert sum(1 for r in results if not r.delivered) == 1
