from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """STUDYLIFE_WEBHOOKS_SHARED_SECRET must match the studylife repo's
    StudyLifeWebhooks:SharedSecret config value exactly - it's the one thing that authenticates
    every /internal/* call as genuinely coming from StudyLife (see WebhooksProxyClient there).
    DB_PATH is a local SQLite file - registration state is this service's own, StudyLife never
    stores a copy of it."""

    model_config = SettingsConfigDict(env_prefix="STUDYLIFE_WEBHOOKS_")

    shared_secret: str = ""
    db_path: str = "webhooks.db"
    # Per-delivery HTTP timeout when POSTing to a user's own target_url - short enough that one
    # slow/unreachable subscriber can't stall the whole /internal/events call for long, since
    # deliveries to multiple subscribers for the same event run concurrently regardless.
    delivery_timeout_seconds: float = 5.0


settings = Settings()
