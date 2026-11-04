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
    # TLS for the StudyLife -> studylife-webhooks hop (see tls.py and README.md "TLS"). With both
    # files set (PEM certificate chain and key; in the cluster the cert-manager certificate from
    # k8s/05-tls-certificate.yaml), the app is also served over HTTPS on tls_port. Only one of
    # the two set, or a file that cannot be loaded, stops the start. The plain port stays for
    # the kubelet probes and Prometheus. The shipped k8s manifests set both; unset is the
    # explicit plain-HTTP opt-out for local runs.
    tls_cert_file: str | None = None
    tls_key_file: str | None = None
    tls_port: int = 8443
    # How often (seconds) the certificate files are checked for a renewal; new handshakes then
    # use the renewed pair without a restart.
    tls_reload_interval_seconds: float = 300.0


settings = Settings()
