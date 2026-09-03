"""Prometheus instrumentation for this service - two things worth watching separately: HTTP
traffic into this service's own routes (main.py's middleware records these) and outbound
delivery attempts to a user's own target_url (delivery.py::deliver_one records these). Scraped
by the existing self-hosted Prometheus (homelab-infra repo, monitoring/01-prometheus.yaml), same
setup studylife-mcp/studylife-ai already use.

target_url is deliberately never used as a label anywhere here - it's an arbitrary
user-configured value with unbounded cardinality (a new label value per registered webhook), so
every upstream metric uses a fixed "webhook-target" label instead. That loses per-destination
breakdown, but keeps the metric set bounded regardless of how many webhooks get registered.

Default process/platform collectors (process_*, python_gc_*, etc.) are registered automatically
on prometheus_client's default registry the moment the module is imported - nothing extra to do
for those here, just don't build a custom CollectorRegistry that would leave them out.
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# HTTP-level metrics, recorded once per request by main.py's middleware for every route
# (including /health and /metrics itself) - route is always the matched route TEMPLATE
# (e.g. "/internal/webhooks/{webhook_id}"), never the raw path, so a real webhook id never
# becomes a label value.
REQUEST_DURATION_SECONDS = Histogram(
    "studylife_webhooks_request_duration_seconds",
    "HTTP request duration in seconds, by route and method.",
    ["route", "method"],
)

REQUESTS_TOTAL = Counter(
    "studylife_webhooks_requests_total",
    "Total HTTP requests, by route, method, and status class.",
    ["route", "method", "status_class"],
)

# Outbound delivery metrics, recorded once per attempt in delivery.py::deliver_one. "outcome"
# distinguishes a genuine network/timeout failure from a response that came back but wasn't
# 2xx - both count as "not delivered" for deliveries_total below, but they're different failure
# modes worth telling apart here (a subscriber's server being down vs. it rejecting the payload).
UPSTREAM_REQUESTS_TOTAL = Counter(
    "studylife_webhooks_upstream_requests_total",
    "Total outbound delivery attempts, by target and outcome.",
    ["target", "outcome"],
)

UPSTREAM_REQUEST_DURATION_SECONDS = Histogram(
    "studylife_webhooks_upstream_request_duration_seconds",
    "Outbound delivery duration in seconds, by target.",
    ["target"],
)

# Mirrors DeliveryResult.delivered (db/delivery.py) as a Prometheus counter - the simplest
# possible "is delivery working" signal, independent of the more detailed outcome breakdown
# above. No delivery_attempts/retry histogram: deliver_all does a single attempt per
# subscriber with no retry mechanism, so there's nothing to count attempts of yet.
DELIVERIES_TOTAL = Counter(
    "studylife_webhooks_deliveries_total",
    "Total webhook deliveries, by outcome.",
    ["outcome"],
)


def render_latest() -> tuple[bytes, str]:
    """Returns (body, content_type) for the /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
