"""Registration storage - one small SQLite table, this service's own state (StudyLife never
stores a copy of it, see WebhooksProxyClient's doc comment on the studylife side). Plain sqlite3
used synchronously (FastAPI runs sync def endpoints in a threadpool automatically) rather than
aiosqlite - this service's request volume is registration CRUD plus one write per StudyLife
event, nowhere near enough to need an async driver."""

import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from studylife_webhooks.config import settings


@dataclass
class Webhook:
    id: str
    user_id: int
    target_url: str
    events: list[str]
    secret: str
    created_at: str


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS webhooks (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                target_url TEXT NOT NULL,
                events TEXT NOT NULL,
                secret TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_webhooks_user_id ON webhooks(user_id)"
        )


@contextmanager
def _connect():
    conn = sqlite3.connect(settings.db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_webhook(row: tuple) -> Webhook:
    id_, user_id, target_url, events_json, secret, created_at = row
    return Webhook(
        id=id_,
        user_id=user_id,
        target_url=target_url,
        events=json.loads(events_json),
        secret=secret,
        created_at=created_at,
    )


def list_webhooks(user_id: int) -> list[Webhook]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, user_id, target_url, events, secret, created_at FROM webhooks WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return [_row_to_webhook(r) for r in rows]


def create_webhook(user_id: int, target_url: str, events: list[str]) -> Webhook:
    webhook = Webhook(
        id=uuid.uuid4().hex,
        user_id=user_id,
        target_url=target_url,
        events=events,
        # Plaintext, deliberately: this secret signs every outgoing delivery (HMAC-SHA256, see
        # delivery.py) so the subscriber can verify authenticity - unlike an API key (compared,
        # so hashing is fine), a signing secret must be retrievable to compute new signatures.
        # Same trust boundary as any webhook provider (Stripe, GitHub, etc.) that works this way.
        secret=secrets.token_urlsafe(32),
        created_at=datetime.now(UTC).isoformat(),
    )
    with _connect() as conn:
        conn.execute(
            "INSERT INTO webhooks (id, user_id, target_url, events, secret, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                webhook.id,
                webhook.user_id,
                webhook.target_url,
                json.dumps(webhook.events),
                webhook.secret,
                webhook.created_at,
            ),
        )
    return webhook


def delete_webhook(user_id: int, webhook_id: str) -> bool:
    """Scoped to user_id - a webhook id alone must never be enough to delete someone else's
    registration. Returns whether a row was actually deleted."""
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM webhooks WHERE id = ? AND user_id = ?", (webhook_id, user_id)
        )
    return cursor.rowcount > 0


def find_subscribers(user_id: int, event_type: str) -> list[Webhook]:
    """Every webhook for this user whose events list contains this exact event_type, or the
    wildcard "*" (subscribe to everything - see the README) - a plain string match, no schema
    validation against a closed catalog, so a brand-new event type on the StudyLife side is
    matchable here without any change to this service."""
    return [
        w for w in list_webhooks(user_id) if event_type in w.events or "*" in w.events
    ]
