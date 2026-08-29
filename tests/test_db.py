from studylife_webhooks import db


def test_create_and_list_webhook(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "studylife_webhooks.config.settings.db_path", str(tmp_path / "t.db")
    )
    db.init_db()

    created = db.create_webhook(
        user_id=1, target_url="https://example.com/hook", events=["session.completed"]
    )
    assert created.user_id == 1
    assert created.target_url == "https://example.com/hook"
    assert created.events == ["session.completed"]
    assert len(created.secret) > 20  # a real random secret, not empty/trivial

    listed = db.list_webhooks(1)
    assert len(listed) == 1
    assert listed[0].id == created.id
    assert (
        listed[0].secret == created.secret
    )  # list still returns the stored secret internally - main.py's WebhookOut is what hides it from the API response


def test_list_webhooks_scoped_to_user_id(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "studylife_webhooks.config.settings.db_path", str(tmp_path / "t.db")
    )
    db.init_db()

    db.create_webhook(
        user_id=1, target_url="https://a.test", events=["session.completed"]
    )
    db.create_webhook(
        user_id=2, target_url="https://b.test", events=["session.completed"]
    )

    assert len(db.list_webhooks(1)) == 1
    assert len(db.list_webhooks(2)) == 1
    assert db.list_webhooks(1)[0].target_url == "https://a.test"


def test_delete_webhook_scoped_to_user_id(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "studylife_webhooks.config.settings.db_path", str(tmp_path / "t.db")
    )
    db.init_db()

    webhook = db.create_webhook(
        user_id=1, target_url="https://a.test", events=["session.completed"]
    )

    # A different user_id must not be able to delete someone else's registration.
    assert db.delete_webhook(user_id=2, webhook_id=webhook.id) is False
    assert len(db.list_webhooks(1)) == 1

    assert db.delete_webhook(user_id=1, webhook_id=webhook.id) is True
    assert len(db.list_webhooks(1)) == 0


def test_delete_nonexistent_webhook_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "studylife_webhooks.config.settings.db_path", str(tmp_path / "t.db")
    )
    db.init_db()

    assert db.delete_webhook(user_id=1, webhook_id="does-not-exist") is False


def test_find_subscribers_matches_exact_event_type(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "studylife_webhooks.config.settings.db_path", str(tmp_path / "t.db")
    )
    db.init_db()

    db.create_webhook(
        user_id=1, target_url="https://a.test", events=["session.completed"]
    )
    db.create_webhook(user_id=1, target_url="https://b.test", events=["timer.started"])

    matches = db.find_subscribers(1, "session.completed")
    assert [w.target_url for w in matches] == ["https://a.test"]


def test_find_subscribers_wildcard_matches_any_event(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "studylife_webhooks.config.settings.db_path", str(tmp_path / "t.db")
    )
    db.init_db()

    db.create_webhook(user_id=1, target_url="https://everything.test", events=["*"])

    assert len(db.find_subscribers(1, "session.completed")) == 1
    assert (
        len(db.find_subscribers(1, "a-totally-new-event-type-nobody-registered-for"))
        == 1
    )


def test_find_subscribers_never_crosses_user_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "studylife_webhooks.config.settings.db_path", str(tmp_path / "t.db")
    )
    db.init_db()

    db.create_webhook(user_id=1, target_url="https://a.test", events=["*"])

    assert db.find_subscribers(2, "session.completed") == []
