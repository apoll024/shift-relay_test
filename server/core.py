"""Persistent domain operations. No network calls occur inside database transactions."""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import html
import io
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
PHASES = ("morning", "midday", "night")
CHECKS = {
    "morning": "Restock status checked",
    "midday": "Restock status handed off",
    "night": "Restock staged or shortage recorded",
}
TASK_STATUSES = ("new", "inProgress", "waiting", "done")
PRIORITIES = ("low", "normal", "high", "urgent")
CATEGORIES = ("safety", "equipment", "security", "temperature", "other")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def text(value, name: str, maximum: int = 10000, required: bool = False) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ApiError(400, f"{name} must be text of at most {maximum} characters.")
    value = value.strip()
    if required and not value:
        raise ApiError(400, f"{name} is required.")
    return value


def choice(value, options, name):
    if value not in options:
        raise ApiError(400, f"Choose a valid {name}.")
    return value


def iso(value) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(UTC)
    except (AttributeError, TypeError, ValueError):
        raise ApiError(400, "Timestamps must include a timezone.") from None


def stamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def date_key(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ApiError(400, "Dates must be YYYY-MM-DD.") from None


def clock(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
            raise ValueError()
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        raise ApiError(400, "Times must be HH:MM in 24-hour format.") from None


def zone(value):
    try:
        return ZoneInfo(value)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        raise ApiError(400, "Choose an IANA timezone, such as America/Los_Angeles.") from None


def manager(user):
    if user["id"] != "elena":
        raise ApiError(403, "Operations Manager access is required.")


def shift_manager(user):
    if user["id"] not in ("jordan", "avery"):
        raise ApiError(403, "A Shift Manager must perform this action.")


def photo_inputs(value, maximum=10):
    if not isinstance(value, list) or len(value) > maximum:
        raise ApiError(400, f"Add no more than {maximum} photos at a time.")
    result = []
    for photo in value:
        if not isinstance(photo, dict):
            raise ApiError(400, "A photo must contain image data and a source.")
        uri = photo.get("uri")
        if not isinstance(uri, str) or len(uri) > 8_000_000:
            raise ApiError(400, "Each photo must be smaller than 6 MB.")
        match = re.fullmatch(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\r\n]+)", uri)
        if not match:
            raise ApiError(400, "Shared photos need JPEG, PNG, or WebP image data.")
        try:
            raw = base64.b64decode(match[2], validate=True)
        except ValueError:
            raise ApiError(400, "Invalid photo data.") from None
        signatures = {
            "jpeg": raw.startswith(b"\xff\xd8\xff"),
            "png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "webp": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
        }
        if not signatures[match[1]]:
            raise ApiError(400, "Photo contents do not match the image type.")
        result.append({"uri": uri, "source": choice(photo.get("source"), ("camera", "upload"), "photo source")})
    return result


class Service:
    def __init__(self, database, users, operational_timezone="America/Los_Angeles", now=None):
        self.database = str(database)
        self.users = users
        self.timezone = zone(operational_timezone)
        self.now = now or (lambda: datetime.now(UTC))
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS logs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS issues (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, source_key TEXT UNIQUE, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS schedules (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS deliveries (
                    id TEXT PRIMARY KEY, schedule_id TEXT NOT NULL, local_date TEXT NOT NULL,
                    data TEXT NOT NULL, UNIQUE(schedule_id, local_date)
                );
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def authenticate(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        for user in self.users:
            if hmac.compare_digest(user["tokenHash"], digest):
                return self.public_user(user)
        raise ApiError(401, "Access token is invalid. Sign in again.")

    @staticmethod
    def public_user(user):
        return {"id": user["id"], "name": user["name"], "role": "manager" if user["id"] == "elena" else "shiftManager"}

    @staticmethod
    def rows(db, table):
        return [json.loads(row["data"]) for row in db.execute(f"SELECT data FROM {table}")]

    @staticmethod
    def get(db, table, identifier):
        identifier = text(identifier, "Record ID", 200, True)
        row = db.execute(f"SELECT data FROM {table} WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ApiError(404, "This record does not exist.")
        return json.loads(row["data"])

    @staticmethod
    def put(db, table, record):
        encoded = json.dumps(record)
        updated = db.execute(f"UPDATE {table} SET data=? WHERE id=?", (encoded, record["id"]))
        if updated.rowcount == 0:
            db.execute(f"INSERT INTO {table}(id,data) VALUES(?,?)", (record["id"], encoded))

    def ensure_today(self, db):
        today = self.now().astimezone(self.timezone).date().isoformat()
        for phase in PHASES:
            identifier = f"LOG-{today}-{phase}"
            record = {"id": identifier, "operationalDate": today, "phase": phase,
                      "status": "pending", "confirmations": [{"id": f"{identifier}-check", "label": CHECKS[phase], "confirmed": False}],
                      "note": None, "signOffs": [], "checkEvents": [], "issueReview": None, "walkPhotos": []}
            db.execute("INSERT OR IGNORE INTO logs(id,data) VALUES(?,?)", (identifier, json.dumps(record)))
        return today

    def operation(self, user, request):
        if not isinstance(request, dict) or not isinstance(request.get("operation"), str):
            raise ApiError(400, "Choose an operation.")
        operation = request["operation"]
        payload = request.get("input", {})
        if not isinstance(payload, dict):
            raise ApiError(400, "Operation input must be an object.")
        if payload.get("accountId", user["id"]) != user["id"]:
            raise ApiError(403, "The submitted account does not match your session.")
        with self.connect() as db:
            today = self.ensure_today(db)
            at = stamp(self.now())
            if operation == "listLogs":
                return sorted(self.rows(db, "logs"), key=lambda log: (log["operationalDate"], PHASES.index(log["phase"])), reverse=True)
            if operation == "detailLog":
                return self.get(db, "logs", request.get("id"))
            if operation == "listIssues":
                return sorted(self.rows(db, "issues"), key=lambda issue: issue["raisedAt"], reverse=True)
            if operation in ("toggleCheck", "addWalkPhotos", "removeWalkPhoto", "signOffLog"):
                return self.log_operation(db, user, operation, payload, today, at)
            if operation in ("raiseIssue", "resolveIssue"):
                return self.issue_operation(db, user, operation, payload, today, at)
            if operation == "workspace":
                return {"users": [self.public_user(item) for item in self.users],
                        "tasks": sorted(self.rows(db, "tasks"), key=lambda item: item["updatedAt"], reverse=True),
                        "reports": sorted(self.rows(db, "reports"), key=lambda item: item["generatedAt"], reverse=True)[:50] if user["id"] == "elena" else [],
                        "schedules": self.rows(db, "schedules") if user["id"] == "elena" else [],
                        "deliveries": sorted(self.rows(db, "deliveries"), key=lambda item: item["createdAt"], reverse=True)[:50] if user["id"] == "elena" else []}
            if operation in ("createTask", "updateTask"):
                return self.task_operation(db, user, operation, payload, at)
            if operation in ("previewReport", "saveReport"):
                manager(user)
                report = self.build_report(db, payload, user, self.now())
                if operation == "saveReport":
                    self.put(db, "reports", report)
                return report
            if operation == "getReport":
                manager(user)
                return self.get(db, "reports", payload.get("id"))
            if operation == "saveSchedule":
                manager(user)
                schedule = self.validate_schedule(payload, at)
                self.put(db, "schedules", schedule)
                return schedule
            if operation == "retryDelivery":
                manager(user)
                delivery = self.get(db, "deliveries", payload.get("id"))
                if delivery["status"] != "failed":
                    raise ApiError(409, "Only a confirmed failed delivery can be retried. Review unknown deliveries with your mail server.")
                delivery.update(status="queued", error=None)
                self.put(db, "deliveries", delivery)
                return delivery
        raise ApiError(400, "Unknown operation.")

    def log_operation(self, db, user, operation, payload, today, at):
        log = self.get(db, "logs", payload.get("id"))
        identifier = log["id"]
        phase = log["phase"]
        if operation == "removeWalkPhoto":
            manager(user)
            log["walkPhotos"] = [photo for photo in log["walkPhotos"] if photo["id"] != payload.get("photoId")]
        else:
            if log["operationalDate"] != today or log["status"] == "signedOff":
                raise ApiError(409, "Only today's open shift can be changed.")
            if operation == "addWalkPhotos":
                allowed = PHASES if user["id"] == "elena" else ("morning", "midday") if user["id"] == "jordan" else ("midday", "night")
                if phase not in allowed:
                    raise ApiError(403, "Photos can only be added to your shift's forms.")
                for photo in photo_inputs(payload.get("photos", [])):
                    log["walkPhotos"].append({**photo, "id": str(uuid.uuid4()), "caption": None, "actor": user["name"], "at": at})
            else:
                required = "avery" if log["status"] == "awaitingSecondSignOff" or phase == "night" else "jordan"
                if user["id"] != required:
                    raise ApiError(403, "The Shift Manager on duty must perform this action.")
                day = {item["phase"]: item for item in self.rows(db, "logs") if item["operationalDate"] == today}
                if phase == "midday" and day["morning"]["status"] != "signedOff":
                    raise ApiError(409, "Complete Morning before sending the handoff.")
                if phase == "night" and day["midday"]["status"] != "signedOff":
                    raise ApiError(409, "Receive the Midday handoff before completing Night.")
                if operation == "toggleCheck":
                    if log["status"] != "pending" or not isinstance(payload.get("checked"), bool):
                        raise ApiError(409, "This check cannot be changed.")
                    check = next((item for item in log["confirmations"] if item["id"] == payload.get("checkId")), None)
                    if check is None:
                        raise ApiError(404, "This check does not exist.")
                    if check["confirmed"] != payload["checked"]:
                        check["confirmed"] = payload["checked"]
                        log["checkEvents"].append({"checkId": check["id"], "label": check["label"], "checked": payload["checked"], "actor": user["name"], "at": at})
                elif log["status"] == "awaitingSecondSignOff":
                    open_ids = [item["id"] for item in self.rows(db, "issues") if item["status"] == "open"]
                    reviewed = payload.get("reviewedIssueIds", [])
                    if not isinstance(reviewed, list) or any(item not in reviewed for item in open_ids):
                        raise ApiError(409, "Review every open issue before receiving the handoff.")
                    if open_ids:
                        log["issueReview"] = {"issueIds": open_ids, "actor": user["name"], "at": at}
                        log["checkEvents"].append({"checkId": f"{identifier}-issues", "label": f"Open issues reviewed ({len(open_ids)})", "checked": True, "actor": user["name"], "at": at})
                    log["signOffs"].append({"actor": user["name"], "at": at})
                    log["status"] = "signedOff"
                else:
                    if not all(item["confirmed"] for item in log["confirmations"]):
                        raise ApiError(409, "Confirm the required check before signing off.")
                    log["note"] = text(payload.get("note", ""), "Note") or None
                    log["signOffs"].append({"actor": user["name"], "at": at})
                    log["status"] = "awaitingSecondSignOff" if phase == "midday" else "signedOff"
        self.put(db, "logs", log)
        return log

    def issue_operation(self, db, user, operation, payload, today, at):
        shift_manager(user)
        photos = photo_inputs(payload.get("photos", []), 5)
        if operation == "raiseIssue":
            category = choice(payload.get("category"), CATEGORIES, "category")
            details = text(payload.get("details", ""), "Issue details", required=category == "other")
            if category == "safety" and not photos:
                raise ApiError(400, "Add an evidence photo for a Safety hazard.")
            phase = "morning" if user["id"] == "jordan" else "night"
            log_id = payload.get("sourceLogId") or f"LOG-{today}-{phase}"
            log = self.get(db, "logs", log_id)
            if log["operationalDate"] != today or log["status"] == "signedOff":
                raise ApiError(409, "Raise issues on today's open shift.")
            issue = {"id": str(uuid.uuid4()), "category": category, "details": details, "sourceLogId": log_id,
                     "photos": [], "status": "open", "raisedBy": user["name"], "raisedAt": at,
                     "resolvedBy": None, "resolvedAt": None, "events": [{"type": "raised", "actor": user["name"], "at": at}]}
            purpose = "evidence"
        else:
            issue = self.get(db, "issues", payload.get("id"))
            if issue["status"] == "resolved":
                return issue
            issue.update(status="resolved", resolvedBy=user["name"], resolvedAt=at)
            issue["events"].append({"type": "resolved", "actor": user["name"], "at": at})
            purpose = "resolution"
        for photo in photos:
            issue["photos"].append({**photo, "id": str(uuid.uuid4()), "purpose": purpose, "takenBy": user["name"], "takenAt": at})
            issue["events"].append({"type": "photoAdded", "actor": user["name"], "at": at})
        self.put(db, "issues", issue)
        return issue

    def assignee(self, value):
        if value is not None and value not in [user["id"] for user in self.users]:
            raise ApiError(400, "Choose a workspace member or leave the task unassigned.")
        return value

    def task_operation(self, db, user, operation, payload, at):
        if operation == "createTask":
            source_issue = payload.get("sourceIssueId") or None
            source_key = None
            issue = None
            if source_issue:
                issue = self.get(db, "issues", source_issue)
                source_key = f"issue:{issue['id']}"
                existing = db.execute("SELECT data FROM tasks WHERE source_key=?", (source_key,)).fetchone()
                if existing:
                    return json.loads(existing["data"])
            assignee = self.assignee(payload.get("assigneeId"))
            if user["id"] != "elena" and assignee not in (None, user["id"]):
                raise ApiError(403, "Only the Operations Manager can assign someone else.")
            due = date_key(payload["dueDate"]) if payload.get("dueDate") else None
            record = {"id": str(uuid.uuid4()), "title": text(payload.get("title"), "Task title", 200, True),
                      "description": text(payload.get("description", ""), "Description"), "assigneeId": assignee,
                      "dueDate": due, "priority": choice(payload.get("priority", "normal"), PRIORITIES, "priority"),
                      "status": "new", "sourceIssueId": source_issue, "sourceKey": source_key,
                      "sourceReference": issue["sourceLogId"] if issue else None, "sourceObservedAt": issue["raisedAt"] if issue else None,
                      "createdBy": user["id"], "createdAt": at, "updatedAt": at, "completedAt": None,
                      "version": 1, "activity": [{"actor": user["name"], "at": at, "message": "Task created"}]}
            db.execute("INSERT INTO tasks(id,source_key,data) VALUES(?,?,?)", (record["id"], source_key, json.dumps(record)))
            return record
        record = self.get(db, "tasks", payload.get("id"))
        if user["id"] != "elena" and not (record["assigneeId"] == user["id"] or (record["assigneeId"] is None and record["createdBy"] == user["id"])):
            raise ApiError(403, "Only the assignee, the creator of unassigned work, or the Operations Manager can update this task.")
        if payload.get("version") != record["version"]:
            raise ApiError(409, "Someone changed this task. Refresh and reopen it before saving.")
        assignee = self.assignee(payload.get("assigneeId", record["assigneeId"]))
        if user["id"] != "elena" and assignee != record["assigneeId"]:
            raise ApiError(403, "Only the Operations Manager can reassign tasks.")
        status = choice(payload.get("status", record["status"]), TASK_STATUSES, "task status")
        note = text(payload.get("note", ""), "Update note", 4000)
        if status == "done" and record["status"] != "done" and not note:
            raise ApiError(400, "Add a completion note explaining what was done.")
        changes = []
        new_values = {"title": text(payload.get("title", record["title"]), "Task title", 200, True),
                      "description": text(payload.get("description", record["description"]), "Description"),
                      "assigneeId": assignee, "dueDate": date_key(payload.get("dueDate", record["dueDate"])) if payload.get("dueDate", record["dueDate"]) else None,
                      "priority": choice(payload.get("priority", record["priority"]), PRIORITIES, "priority"), "status": status}
        for key, value in new_values.items():
            if record[key] != value:
                changes.append(f"{key}: {record[key] or 'none'} → {value or 'none'}")
        if status != record["status"]:
            record["completedAt"] = at if status == "done" else None
        record.update(new_values)
        if changes or note:
            record["activity"].append({"actor": user["name"], "at": at, "message": "; ".join(changes + ([note] if note else []))})
            record.update(updatedAt=at, version=record["version"] + 1)
            self.put(db, "tasks", record)
        return record

    @staticmethod
    def report_options(payload):
        options = {"date": date_key(payload.get("date")), "timezone": text(payload.get("timezone", "America/Los_Angeles"), "Timezone", 100, True),
                   "overnightStart": payload.get("overnightStart", "17:00"), "overnightEnd": payload.get("overnightEnd", "08:00"),
                   "title": text(payload.get("title", "Morning operations report"), "Report title", 200, True)}
        zone(options["timezone"])
        if "\n" in options["title"] or "\r" in options["title"]:
            raise ApiError(400, "Report title must be a single line.")
        if clock(options["overnightStart"]) <= clock(options["overnightEnd"]):
            raise ApiError(400, "Overnight start must be later than end; the window crosses midnight.")
        return options

    def build_report(self, db, payload, user, now):
        options = self.report_options(payload)
        day = date.fromisoformat(options["date"])
        tz = zone(options["timezone"])
        start = datetime.combine(day - timedelta(days=1), clock(options["overnightStart"]), tz).astimezone(UTC)
        end = datetime.combine(day, clock(options["overnightEnd"]), tz).astimezone(UTC)
        if start >= now:
            raise ApiError(400, "Choose a report date whose overnight window has started.")
        end = min(end, now)
        tasks = self.rows(db, "tasks")
        owners = {item["id"]: item["name"] for item in self.users}
        records = [{"id": item["id"], "kind": "task", "title": item["title"], "description": item["description"],
                    "status": item["status"], "priority": item["priority"], "assignee": owners.get(item["assigneeId"], "Unassigned"),
                    "dueDate": item["dueDate"], "firstSeenAt": min(filter(None, (item["createdAt"], item["sourceObservedAt"])), key=iso), "updatedAt": item["updatedAt"], "completedAt": item["completedAt"],
                    "reference": item["sourceReference"]} for item in tasks]
        linked = {item["sourceIssueId"] for item in tasks if item["sourceIssueId"]}
        active_linked = {item["sourceIssueId"] for item in tasks if item["sourceIssueId"] and item["status"] != "done"}
        for issue in self.rows(db, "issues"):
            if issue["id"] in linked and (issue["status"] == "resolved" or issue["id"] in active_linked):
                continue
            records.append({"id": issue["id"], "kind": "issue", "title": f"{issue['category'].title()}: {issue['details'] or 'Shift issue'}",
                            "description": issue["details"], "status": "done" if issue["status"] == "resolved" else "new", "priority": "high",
                            "assignee": "Unassigned", "dueDate": None, "firstSeenAt": issue["raisedAt"],
                            "updatedAt": issue["resolvedAt"] or issue["raisedAt"], "completedAt": issue["resolvedAt"], "reference": issue["sourceLogId"]})
        records.sort(key=lambda item: (PRIORITIES.index(item["priority"]), item["firstSeenAt"]), reverse=True)
        within = lambda value: start <= iso(value) < end
        open_records = [item for item in records if item["status"] != "done"]
        sections = [
            {"key": "outstanding", "title": "Outstanding from earlier reports", "items": [item for item in open_records if iso(item["firstSeenAt"]) < start]},
            {"key": "new", "title": "New overnight", "items": [item for item in records if within(item["firstSeenAt"])]},
            {"key": "updated", "title": "Earlier work updated overnight", "items": [item for item in open_records if iso(item["firstSeenAt"]) < start and within(item["updatedAt"])]},
            {"key": "resolved", "title": "Completed overnight", "items": [item for item in records if item["completedAt"] and within(item["completedAt"])]},
            {"key": "overdue", "title": "Overdue tasks", "items": [item for item in open_records if item["dueDate"] and item["dueDate"] < now.astimezone(tz).date().isoformat()]},
            {"key": "unassigned", "title": "Unassigned work", "items": [item for item in open_records if item["assignee"] == "Unassigned"]},
        ]
        return {"id": str(uuid.uuid4()), **options, "generatedAt": stamp(now), "generatedBy": user["name"],
                "windowStart": stamp(start), "windowEnd": stamp(end), "openCount": len(open_records), "sections": sections,
                "scope": "Current status at generation; overnight events use the selected time window. Sections may overlap."}

    def validate_schedule(self, payload, at):
        options = self.report_options({**payload, "date": self.now().astimezone(zone(payload.get("timezone", "America/Los_Angeles"))).date().isoformat()})
        clock(payload.get("deliveryTime", "08:05"))
        recipients = payload.get("recipients", [])
        if not isinstance(recipients, list) or len(recipients) > 50 or any(not isinstance(item, str) or not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", item) for item in recipients):
            raise ApiError(400, "Enter valid recipient email addresses (maximum 50).")
        if not isinstance(payload.get("enabled", False), bool):
            raise ApiError(400, "Enabled must be true or false.")
        if payload.get("enabled") and not recipients:
            raise ApiError(400, "Add recipients before enabling delivery.")
        if clock(payload.get("deliveryTime", "08:05")) < clock(options["overnightEnd"]):
            raise ApiError(400, "Delivery must be at or after the overnight window ends.")
        return {"id": "daily", "title": options["title"], "timezone": options["timezone"],
                "overnightStart": options["overnightStart"], "overnightEnd": options["overnightEnd"],
                "deliveryTime": payload.get("deliveryTime", "08:05"), "recipients": list(dict.fromkeys(recipients)),
                "enabled": payload.get("enabled", False), "updatedAt": at}

    def claim_due(self, now):
        """One claim per local schedule date; no catch-up burst for old dates."""
        claimed = []
        with self.connect() as db:
            self.ensure_today(db)
            for schedule in self.rows(db, "schedules"):
                local = now.astimezone(zone(schedule["timezone"]))
                if not schedule["enabled"] or local.time().replace(tzinfo=None) < clock(schedule["deliveryTime"]):
                    continue
                today = local.date().isoformat()
                if db.execute("SELECT id FROM deliveries WHERE schedule_id=? AND local_date=?", (schedule["id"], today)).fetchone():
                    continue
                user = self.public_user(next(item for item in self.users if item["id"] == "elena"))
                report = self.build_report(db, {**schedule, "date": today}, user, now)
                self.put(db, "reports", report)
                delivery = {"id": str(uuid.uuid4()), "scheduleId": schedule["id"], "date": today, "reportId": report["id"],
                            "recipients": schedule["recipients"], "status": "queued", "attempts": 0,
                            "createdAt": stamp(now), "updatedAt": stamp(now), "error": None}
                db.execute("INSERT INTO deliveries(id,schedule_id,local_date,data) VALUES(?,?,?,?)", (delivery["id"], schedule["id"], today, json.dumps(delivery)))
            for delivery in self.rows(db, "deliveries"):
                if delivery["status"] != "queued":
                    continue
                delivery.update(status="sending", attempts=delivery["attempts"] + 1, updatedAt=stamp(now))
                self.put(db, "deliveries", delivery)
                claimed.append((delivery, self.get(db, "reports", delivery["reportId"])))
        return claimed

    def finish_delivery(self, delivery_id, status, error=None):
        with self.connect() as db:
            delivery = self.get(db, "deliveries", delivery_id)
            delivery.update(status=status, error=error, updatedAt=stamp(self.now()))
            self.put(db, "deliveries", delivery)

    def recover_deliveries(self):
        """A crash while sending cannot prove whether the mail server accepted the message."""
        with self.connect() as db:
            for delivery in self.rows(db, "deliveries"):
                if delivery["status"] == "sending":
                    delivery.update(status="unknown", error="Service restarted during delivery. Check the mail server before resending.")
                    self.put(db, "deliveries", delivery)


def render_html(report):
    escape = lambda value: html.escape(str(value or ""), quote=True)
    parts = ["<!doctype html><html><head><meta charset='utf-8'><title>", escape(report["title"]),
             "</title><style>body{font-family:system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:16px}table{width:100%;border-collapse:collapse}th,td{padding:8px;border:1px solid #ccc;text-align:left;vertical-align:top}h2{margin-top:28px}@media print{body{margin:0}tr{break-inside:avoid}}</style></head><body><h1>",
             escape(report["title"]), "</h1><p>", escape(report["date"]), " · ", escape(report["timezone"]), "</p><p>Generated ",
             escape(report["generatedAt"]), " · Open work: ", escape(report["openCount"]), "</p><p>", escape(report["scope"]), "</p><p>Overnight window: ", escape(report["windowStart"]), " to ", escape(report["windowEnd"]), "</p>"]
    for section in report["sections"]:
        parts += ["<h2>", escape(section["title"]), f" ({len(section['items'])})</h2>"]
        if not section["items"]:
            parts.append("<p>No items.</p>")
            continue
        parts.append("<table><thead><tr><th>Work</th><th>Priority / status</th><th>Owner</th><th>Due</th><th>First seen</th></tr></thead><tbody>")
        for item in section["items"]:
            parts += ["<tr><td><strong>", escape(item["title"]), "</strong><br>", escape(item["description"]), "<br>", escape(item["reference"]),
                      "</td><td>", escape(item["priority"]), " / ", escape(item["status"]), "</td><td>", escape(item["assignee"]),
                      "</td><td>", escape(item["dueDate"]), "</td><td>", escape(item["firstSeenAt"]), "</td></tr>"]
        parts.append("</tbody></table>")
    return "".join(parts) + "</body></html>"


def render_csv(report):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Section", "ID", "Kind", "Title", "Description", "Priority", "Status", "Owner", "Due", "First seen", "Reference"])
    for section in report["sections"]:
        for item in section["items"]:
            values = [section["title"], item["id"], item["kind"], item["title"], item["description"], item["priority"], item["status"], item["assignee"], item["dueDate"], item["firstSeenAt"], item["reference"]]
            # Prevent spreadsheet formula execution on opening imported descriptions.
            writer.writerow(["'" + str(value) if str(value or "").lstrip().startswith(("=", "+", "-", "@")) else value for value in values])
    return output.getvalue()
