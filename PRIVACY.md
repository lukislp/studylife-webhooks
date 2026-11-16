# Privacy Policy - StudyAtrium Webhooks

StudyAtrium Webhooks is a microservice extending a self-hosted
[StudyAtrium](https://github.com/lukislp/studylife) instance. There is no vendor server involved -
this service is self-hosted alongside your own StudyAtrium instance, and your data goes exactly
two places: your own registered target URLs, and this service's own local SQLite database.

## What this service reads

- **Nothing directly from you.** This service is never contacted by your browser or by
  StudyAtrium's client - only by your own StudyAtrium server's backend, on your behalf, over
  `/internal/*` endpoints authenticated by one shared secret you configure on both sides.
- **Event data StudyAtrium sends it** (e.g. that a session completed, and a small summary of that
  session - course name, duration) exactly at the moment it happens, so it can forward that data
  to whichever of your own registrations are subscribed to that event type.

## What this service stores

Locally, in this service's own SQLite database, never shared with StudyAtrium or anyone else:

- The target URLs you've registered and which event types each is subscribed to.
- A per-registration signing secret (used to sign outgoing deliveries so your receiving
  endpoint can verify authenticity) - shown to you once, at creation time.

## Deleting your data

When an account is deleted in StudyAtrium, your StudyAtrium server calls this service to delete every
registration stored for that account (target URLs, event lists and signing secrets). The call is
retried until this service confirms it, and the rows are overwritten in the database file
(`secure_delete`), not just unlinked. Backups of the database file you made yourself are not touched.

## What this service sends

- A signed HTTP `POST` to each of your registered target URLs, only when a subscribed event
  actually happens, containing exactly the event payload StudyAtrium sent this service (see the
  README for the exact shape).

## What this service never does

- Never collects analytics, telemetry, or crash reports.
- Never contacts any server other than the target URLs you explicitly register.
- Never reads anything from your StudyAtrium account beyond the specific event payloads StudyAtrium
  itself chooses to forward.

## Source

This service is open source (AGPL-3.0): <https://github.com/lukislp/studylife-webhooks>.
