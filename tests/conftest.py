import os

import pytest
from fastapi.testclient import TestClient

os.environ["STUDYLIFE_WEBHOOKS_SHARED_SECRET"] = "test-shared-secret"


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "test-webhooks.db"
    monkeypatch.setattr("studylife_webhooks.config.settings.db_path", str(db_path))

    from studylife_webhooks.main import app

    with TestClient(app) as test_client:
        yield test_client
