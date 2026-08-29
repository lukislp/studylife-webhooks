# Privacy Policy - StudyLife Webhooks

StudyLife Webhooks is a microservice extending a self-hosted
[StudyLife](https://github.com/lukislp/studylife) instance. There is no vendor server involved -
this service is self-hosted alongside your own StudyLife instance, and your data goes exactly
two places: your own registered target URLs, and this service's own local SQLite database.

## What this service reads

- **Nothing directly from you.** This service is never contacted by your browser or by
  StudyLife's client - only by your own StudyLife server's backend, on your behalf, over
  `/internal/*` endpoints authenticated by one shared secret you configure on both sides.
- **Event data StudyLife sends it** (e.g. that a session completed, and a small summary of that
  session - course name, duration) exactly at the moment it happens, so it can forward that data
  to whichever of your own registrations are subscribed to that event type.

## What this service stores

Locally, in this service's own SQLite database, never shared with StudyLife or anyone else:

- The target URLs you've registered and which event types each is subscribed to.
- A per-registration signing secret (used to sign outgoing deliveries so your receiving
  endpoint can verify authenticity) - shown to you once, at creation time.

## What this service sends

- A signed HTTP `POST` to each of your registered target URLs, only when a subscribed event
  actually happens, containing exactly the event payload StudyLife sent this service (see the
  README for the exact shape).

## What this service never does

- Never collects analytics, telemetry, or crash reports.
- Never contacts any server other than the target URLs you explicitly register.
- Never reads anything from your StudyLife account beyond the specific event payloads StudyLife
  itself chooses to forward.

## Source

This service is open source (AGPL-3.0): <https://github.com/lukislp/studylife-webhooks>.
