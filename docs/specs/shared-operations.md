# Shared operations, tasks, and reports

## Authorized scope

Implement the user's requested shared database, report builder, automatic report
delivery, and task assignment in the fork. Preserve the existing demo workflow.
Existing shift-log, issue, component, and photo specs continue to apply. This spec
extends them before implementation; the user has requested implementation.

## Shared mode

- `EXPO_PUBLIC_API_URL` selects the shared service. Without it, demo behavior is unchanged.
- Sign in with a private per-account access token. The service determines identity;
  submitting a different account ID never grants that account's permissions.
- A single Python service owns a persistent SQLite database. Clients never open
  the database file directly. Transactions serialize writes, and daily blank
  sheets are created in the configured operational timezone.
- All existing log, issue, sign-off, and photo operations persist. Shared photos
  contain image bytes rather than a device-local path.
- No real work data, email, token, database, or SMTP secret goes into the public repo.

## Tasks

- All authenticated accounts can view tasks and create unassigned/self-assigned work.
  The Operations Manager can assign/reassign any task. Assigned staff can update
  their work; the creator can update unassigned work.
- Fields: title, description, assignee, due date, priority, status, optional source
  issue/reference, timestamps, version, and append-only activity.
- Statuses: new, in progress, waiting, done. Completing a task requires a completion
  note. Reopening retains its history. Conflicting edits return an actionable error.
- Issues can be converted to linked tasks without duplicates. Resolving one does
  not silently resolve the other. Conversion preserves the original issue first-seen
  timestamp for report classification.
- Report import is explicitly out of scope for this update. Tasks are created in the
  app or from existing shift issues. Missing observations never imply resolution.

## Reports and delivery

- Operations Manager chooses report date, timezone, overnight start/end, and title.
  A report snapshots outstanding older work, new overnight work, updated older work,
  overnight completions, overdue tasks, and unassigned tasks. Includes current issues
  without counting an issue again if it has a linked task.
- Dates are interpreted in the selected timezone; the overnight interval crosses
  midnight. Previous outstanding means still open at report generation, first seen
  before the overnight interval. Historical reports are immutable saved snapshots,
  not a reconstruction of past status from today's records.
- Preview, save, and download self-contained HTML or CSV. HTML is printable to PDF
  in the browser. No external report-design service is required.
- Manager configures daily local delivery time, timezone, report window, recipients,
  and enabled state. Default is disabled. Credentials live only on the server.
- A server worker claims each schedule/date once in SQLite. SMTP sends a plain text
  summary plus HTML attachment. Failures are visible; explicit retry is available.
  A crash with uncertain SMTP acceptance is marked unknown instead of blindly resending.
  No automatic duplicate resend of ambiguous deliveries.
- Required screens use existing components/tokens, labeled controls, loading/empty/
  retry states, and fit desktop and phone layouts. New sections are in the sidebar/drawer.

## Verification

- Python integration tests: restart persistence, authentication/role enforcement,
  sign-off order, photo storage, task conflicts/completion, issue/task deduplication,
  report boundaries/escaping, schedule claims/DST, SMTP failures and retries.
- Playwright: task creation/assignment/status, report preview/export/save, schedule
  validation, and shared-mode authentication through a local service. Existing demo
  E2E suite remains mandatory. Manual real-iPhone check is reported separately.
