HEADERS = {"X-StudyLife-Shared-Secret": "test-shared-secret"}


def test_health_needs_no_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_internal_routes_reject_missing_shared_secret(client):
    assert client.get("/internal/webhooks", params={"user_id": 1}).status_code == 401
    assert (
        client.post(
            "/internal/webhooks",
            json={"user_id": 1, "target_url": "https://x", "events": ["*"]},
        ).status_code
        == 401
    )
    assert (
        client.delete("/internal/webhooks/some-id", params={"user_id": 1}).status_code
        == 401
    )
    assert (
        client.post(
            "/internal/events",
            json={
                "user_id": 1,
                "event_type": "session.completed",
                "occurred_at": "2026-01-01T00:00:00Z",
            },
        ).status_code
        == 401
    )


def test_internal_routes_reject_wrong_shared_secret(client):
    response = client.get(
        "/internal/webhooks",
        params={"user_id": 1},
        headers={"X-StudyLife-Shared-Secret": "wrong"},
    )
    assert response.status_code == 401


def test_create_webhook_returns_secret_once(client):
    response = client.post(
        "/internal/webhooks",
        json={
            "user_id": 1,
            "target_url": "https://example.com/hook",
            "events": ["session.completed"],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["target_url"] == "https://example.com/hook"
    assert body["events"] == ["session.completed"]
    assert len(body["secret"]) > 20


def test_list_webhooks_never_includes_the_secret(client):
    client.post(
        "/internal/webhooks",
        json={
            "user_id": 1,
            "target_url": "https://example.com/hook",
            "events": ["session.completed"],
        },
        headers=HEADERS,
    )

    response = client.get("/internal/webhooks", params={"user_id": 1}, headers=HEADERS)

    assert response.status_code == 200
    listed = response.json()
    assert len(listed) == 1
    assert "secret" not in listed[0]


def test_list_webhooks_scoped_to_user_id(client):
    client.post(
        "/internal/webhooks",
        json={"user_id": 1, "target_url": "https://a.test", "events": ["*"]},
        headers=HEADERS,
    )
    client.post(
        "/internal/webhooks",
        json={"user_id": 2, "target_url": "https://b.test", "events": ["*"]},
        headers=HEADERS,
    )

    response = client.get("/internal/webhooks", params={"user_id": 1}, headers=HEADERS)

    assert [w["target_url"] for w in response.json()] == ["https://a.test"]


def test_delete_webhook(client):
    created = client.post(
        "/internal/webhooks",
        json={"user_id": 1, "target_url": "https://a.test", "events": ["*"]},
        headers=HEADERS,
    ).json()

    response = client.delete(
        f"/internal/webhooks/{created['id']}", params={"user_id": 1}, headers=HEADERS
    )
    assert response.status_code == 200

    remaining = client.get(
        "/internal/webhooks", params={"user_id": 1}, headers=HEADERS
    ).json()
    assert remaining == []


def test_delete_webhook_wrong_user_id_returns_404(client):
    created = client.post(
        "/internal/webhooks",
        json={"user_id": 1, "target_url": "https://a.test", "events": ["*"]},
        headers=HEADERS,
    ).json()

    response = client.delete(
        f"/internal/webhooks/{created['id']}", params={"user_id": 2}, headers=HEADERS
    )
    assert response.status_code == 404


def test_publish_event_delivers_to_matching_subscribers(client, monkeypatch):
    client.post(
        "/internal/webhooks",
        json={
            "user_id": 1,
            "target_url": "https://a.test",
            "events": ["session.completed"],
        },
        headers=HEADERS,
    )
    client.post(
        "/internal/webhooks",
        json={
            "user_id": 1,
            "target_url": "https://b.test",
            "events": ["timer.started"],
        },
        headers=HEADERS,
    )

    from studylife_webhooks import main
    from studylife_webhooks.delivery import DeliveryResult

    async def fake_deliver_all(webhooks, event_type, occurred_at, payload):
        assert (
            len(webhooks) == 1
        )  # only the session.completed subscriber, not the timer.started one
        return [
            DeliveryResult(webhook_id=webhooks[0].id, delivered=True, status_code=200)
        ]

    monkeypatch.setattr(main, "deliver_all", fake_deliver_all)

    response = client.post(
        "/internal/events",
        json={
            "user_id": 1,
            "event_type": "session.completed",
            "occurred_at": "2026-08-29T12:00:00Z",
            "payload": {"sessionId": 1},
        },
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {"delivered": 1, "failed": 0}


def test_publish_event_with_no_subscribers_delivers_nothing(client):
    response = client.post(
        "/internal/events",
        json={
            "user_id": 1,
            "event_type": "session.completed",
            "occurred_at": "2026-08-29T12:00:00Z",
        },
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {"delivered": 0, "failed": 0}


def test_metrics_endpoint_exposes_request_duration_after_a_request(client):
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "studylife_webhooks_request_duration_seconds" in response.text


def test_metrics_use_route_template_not_the_raw_id_in_the_path(client):
    real_id = "some-real-id-123"

    response = client.delete(
        f"/internal/webhooks/{real_id}", params={"user_id": 1}, headers=HEADERS
    )
    assert response.status_code == 404  # no such webhook - route still matched though

    body = client.get("/metrics").text

    assert "/internal/webhooks/{webhook_id}" in body
    assert real_id not in body
