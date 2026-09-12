"""Atheris fuzz harness for the request models and the payload signature.

Contract under test: PublishEventIn / CreateWebhookIn either validate a JSON body or raise
pydantic's ValidationError (which FastAPI turns into a 422) - never anything else - and
sign_payload() accepts every byte string and always yields a 64-character hex digest.

Run locally (Linux, needs the atheris wheel):
    uv sync --frozen --group fuzz
    uv run python fuzz/fuzz_publish_event.py -max_total_time=60
CI runs the same harness for a short, fixed time budget (see .github/workflows/ci.yml).
"""

from __future__ import annotations

import sys

import atheris
from pydantic import ValidationError

with atheris.instrument_imports():
    from studylife_webhooks.delivery import sign_payload
    from studylife_webhooks.main import CreateWebhookIn, PublishEventIn


def test_one_input(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    body = fdp.ConsumeBytes(256)
    for model in (PublishEventIn, CreateWebhookIn):
        try:
            model.model_validate_json(body)
        except ValidationError:
            pass
    digest = sign_payload(fdp.ConsumeUnicodeNoSurrogates(32), body)
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise AssertionError(f"sign_payload produced {digest!r}")


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
