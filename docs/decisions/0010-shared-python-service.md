# 0010 — Shared Python service and SQLite

## Decision

Add an optional Python 3.12+ service using standard-library SQLite, HTTP, timezone,
and SMTP modules. The existing Expo client talks to it over authenticated HTTP.
SQLite is shared through one service, not over a network filesystem. Deploy one
service process with a durable local volume behind an HTTPS reverse proxy.

## Why

The user's existing reporting pipeline is Python. This provides a small deployment
without a new managed provider, native dependency, document renderer, or recurring
license. Report import is deferred at the user’s request. Transactions
and optimistic task versions preserve concurrent edits. Daily delivery runs on the
service rather than depending on a phone background task.

## Limits

The initial service uses three existing role slots with private account tokens,
not organization-wide SSO or multi-tenancy. Tokens stay in client memory, are
cleared at sign-out, and can be rotated in the server users file. A one-process
service is an internal small-team deployment; a larger deployment should replace
the HTTP adapter and migrate SQLite to PostgreSQL. SMTP cannot guarantee exactly
once delivery; ambiguous attempts are surfaced for manual reconciliation.
