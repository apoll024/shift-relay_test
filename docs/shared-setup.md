# Shared operations setup

Shared mode adds a durable, shared SQLite database, assigned tasks, a report builder, and scheduled email delivery. The Python service owns the database; devices connect over authenticated HTTP. The original fictional demo still runs when `EXPO_PUBLIC_API_URL` is blank. Reports are built from tasks and shift issues recorded in this app; there is no report importer.

## Local development

Requires Node 20+ and Python 3.11+ with IANA timezone data. No additional Python packages are required.

```bash
npm ci
npm run server:init
npm run server
```

In another terminal, copy `.env.example` to `.env`, set `EXPO_PUBLIC_API_URL=http://localhost:8090`, and run `npm run web`. Restart Expo after changing the URL. Sign in using the corresponding token in `server/data/access-tokens.json`. Share tokens privately. Credentials and database files are gitignored. Tokens are held in memory on the client, so a reload requires signing in again.

There are currently three account slots: `jordan` (Morning Shift Manager), `avery` (Night Shift Manager), and `elena` (Operations Manager). Change their display names in the private `users.json`, then restart the service. IDs determine permissions. This initial version uses private access tokens, not an account administration screen or SSO.

A physical phone needs a reachable service URL. For deployment, use HTTPS and set `SHIFT_RELAY_ORIGINS` to the exact web app origin. The server defaults to loopback. Device-local photo paths are never saved in shared mode: image bytes are validated and persisted with the record.

## Tasks and reports

Open **Tasks** from the sidebar or phone drawer. The Operations Manager can assign/reassign tasks, set priorities and due dates, and change status. Shift Managers can create self-assigned or unassigned tasks, and update tasks assigned to them (or their own unassigned tasks). Completing a task requires a note. Updates keep an activity history; concurrent edits return a conflict instead of overwriting silently. Reload the task before retrying a conflict.

The Issues screen's **Create or open task** action links an issue to one task and reuses it on repeated clicks. Conversion preserves the original issue first-seen time. Task completion and issue resolution are separate actions; an unresolved issue remains outstanding even when its linked task is done.

The manager-only **Reports** screen lets you choose a title, date, timezone, and overnight window, then preview and save an immutable snapshot. Sections include outstanding older items, newly raised overnight items, updates, completions, overdue items, and unassigned work. An issue represented by an active task is counted once.

The overnight window starts on the previous calendar day and ends on the selected day, with an exclusive end. Future cutoffs are clipped to the generation time. Reports use the **current status at generation**, including when selecting an earlier date; they do not reconstruct historical state. Saved snapshots preserve what was generated. Downloads on web provide escaped HTML and CSV. Print the HTML from a browser to save a PDF. Native screens support preview, saving, and scheduling; use the web app for downloads.

## Daily email schedule

The report screen includes one daily schedule, disabled by default. Set its recipients, timezone, local delivery time, and overnight window, then enable and save it. SMTP credentials live only on the server. Entering recipients without configuring SMTP will result in a visible failed delivery.

The service checks every 30 seconds and claims at most one delivery per schedule/local date, including across daylight-saving changes. If it starts after today's delivery time, it generates today's report; it does not backfill missed days. Changing the schedule after today's delivery was claimed does not resend it. Keep the service running for automation to operate.

Delivery history shows queued, sending, sent, failed, or unknown. **Sent** means accepted by the SMTP server, not confirmed inbox delivery. A confirmed failed delivery can be retried explicitly using its original snapshot and recipients. Partial acceptance, a lost connection during sending, or a restart while sending produce **unknown**, which is never automatically retried because it could duplicate mail. Check the mail server before deciding what to do with an unknown delivery.

Set `SMTP_HOST`, `SMTP_FROM`, and optionally `SMTP_USER`/`SMTP_PASSWORD`; port defaults to 587 with `SMTP_SECURITY=starttls`. `ssl` defaults to port 465. `none` is intended for a trusted local relay. Emails contain text and HTML plus an HTML attachment. Never put SMTP secrets in `EXPO_PUBLIC_` variables.

## Docker deployment

```bash
cp server/env.example .env.server
# Edit .env.server: timezone, exact web origin, and SMTP settings.
docker compose build
docker compose run --rm relay python -m server.app --init-users
docker compose up -d
```

The named `relay-data` volume holds credentials and the database. Access tokens are inside `/data/access-tokens.json`. Put the loopback-published port 8090 behind an HTTPS reverse proxy, deploy the Expo web app with the service URL, and keep backups. Run **one service process** against this volume. Do not delete the volume to restart or update the service.

| Server variable | Default / purpose |
| --- | --- |
| `SHIFT_RELAY_DB` | `server/data/shift-relay.sqlite3`; Docker uses `/data/shift-relay.sqlite3` |
| `SHIFT_RELAY_USERS_FILE` | `server/data/users.json`; Docker uses `/data/users.json` |
| `SHIFT_RELAY_TIMEZONE` | `America/Los_Angeles`; shift dates and initial report defaults |
| `SHIFT_RELAY_HOST` / `SHIFT_RELAY_PORT` | `127.0.0.1` / `8090`; Docker binds internally to `0.0.0.0` |
| `SHIFT_RELAY_ORIGINS` | Comma-separated exact browser origins; defaults to localhost ports 8081 and 8181 |
| `SMTP_*` | Server-only mail configuration above |

Compose reads `.env.server`; direct `python -m server.app` reads exported environment variables, not that file automatically. Shared mode starts with empty operational data; it does not load the fictional demo seed.

Use SQLite's backup API or stop the service before copying database files. Copying only the live `.sqlite3` file can omit changes in its WAL. Example with the service running:

```python
import sqlite3
with sqlite3.connect('server/data/shift-relay.sqlite3') as source:
    with sqlite3.connect('/secure/backups/shift-relay.sqlite3') as backup:
        source.backup(backup)
```

## Verification

```bash
npm run typecheck
npm run lint
npm run format:check
npm run test:server
npm run e2e
npm run e2e:shared
```

Shared E2E starts an isolated temporary database and fictional accounts, checks cross-session task updates, report downloads, schedule validation, permissions, and shared photos on desktop and phone-sized web viewports. Backend tests cover persistence, permissions, report boundaries, schedule claims, retry behavior, and a loopback SMTP sink. No real recipient is emailed during testing. An optional `PLAYWRIGHT_EXECUTABLE_PATH` selects an installed Chromium binary. Native camera and layout still need an Expo Go check on a real iPhone.
