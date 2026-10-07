"""Integration checks use isolated temporary databases and a local SMTP sink only."""

import base64
import hashlib
import json
import os
import socketserver
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from server.app import DeliveryError, make_handler, run_deliveries, smtp_sender
from server.core import ApiError, Service, render_csv, render_html

UTC = timezone.utc


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.now = datetime(2026, 10, 7, 15, 5, tzinfo=UTC)  # 08:05 Pacific
        self.users = [{"id": identifier, "name": name, "tokenHash": hashlib.sha256(f"test-{identifier}".encode()).hexdigest()}
                      for identifier, name in (("jordan", "Jordan"), ("avery", "Avery"), ("elena", "Elena"))]
        self.database = Path(self.directory.name) / "relay.sqlite3"
        self.service = Service(self.database, self.users, now=lambda: self.now)
        self.jordan = self.service.authenticate("test-jordan")
        self.avery = self.service.authenticate("test-avery")
        self.manager = self.service.authenticate("test-elena")

    def tearDown(self):
        self.directory.cleanup()

    def call(self, operation, payload=None, user=None):
        return self.service.operation(user or self.manager, {"operation": operation, "input": payload or {}})

    def task(self, **overrides):
        return self.call("createTask", {"title": "Investigate device", "description": "Check communication", "priority": "high", **overrides})

    def report(self, **overrides):
        return self.call("saveReport", {"date": "2026-10-07", "timezone": "America/Los_Angeles", "overnightStart": "17:00", "overnightEnd": "08:00", **overrides})

    def schedule(self, **overrides):
        return self.call("saveSchedule", {"timezone": "America/Los_Angeles", "deliveryTime": "08:05", "enabled": True, "recipients": ["operations@example.test"], **overrides})

    def assert_api_error(self, status, callback):
        with self.assertRaises(ApiError) as caught:
            callback()
        self.assertEqual(caught.exception.status, status)

    def test_database_survives_restart_and_is_visible_to_second_client(self):
        task = self.task(assigneeId="avery", dueDate="2026-10-09")
        second = Service(self.database, self.users, now=lambda: self.now)
        workspace = second.operation(self.avery, {"operation": "workspace"})
        self.assertEqual(workspace["tasks"][0]["id"], task["id"])
        self.assertEqual(workspace["tasks"][0]["assigneeId"], "avery")

    def test_invalid_token_and_identity_spoofing_are_rejected(self):
        self.assert_api_error(401, lambda: self.service.authenticate("wrong"))
        self.assert_api_error(403, lambda: self.call("createTask", {"accountId": "elena", "title": "Spoofed"}, self.jordan))
        self.assert_api_error(403, lambda: self.call("saveReport", {"date": "2026-10-07"}, self.jordan))
        self.assert_api_error(403, lambda: self.call("createTask", {"title": "Forbidden", "assigneeId": "avery"}, self.jordan))

    def test_assignment_permissions_and_completion_note(self):
        task = self.task(assigneeId="avery", dueDate="2026-10-09")
        self.assert_api_error(403, lambda: self.call("updateTask", {"id": task["id"], "version": 1, "status": "waiting"}, self.jordan))
        self.assert_api_error(400, lambda: self.call("updateTask", {"id": task["id"], "version": 1, "status": "done"}, self.avery))
        updated = self.call("updateTask", {"id": task["id"], "version": 1, "status": "done", "note": "Replaced faulty cable"}, self.avery)
        self.assertEqual(updated["dueDate"], "2026-10-09")
        self.assertEqual(updated["status"], "done")
        self.assertIn("Replaced faulty cable", updated["activity"][-1]["message"])
        self.assertIsNotNone(updated["completedAt"])
        reopened = self.call("updateTask", {"id": task["id"], "version": 2, "status": "inProgress", "note": "Problem recurred"}, self.avery)
        self.assertIsNone(reopened["completedAt"])
        self.assertEqual(len(reopened["activity"]), 3)

    def test_stale_task_edit_is_rejected_without_lost_update(self):
        task = self.task()
        self.call("updateTask", {"id": task["id"], "version": 1, "title": "Updated title"})
        self.assert_api_error(409, lambda: self.call("updateTask", {"id": task["id"], "version": 1, "title": "Stale title"}))
        self.assertEqual(self.call("workspace")["tasks"][0]["title"], "Updated title")

    def test_unassigned_creator_can_update_but_other_staff_cannot(self):
        task = self.call("createTask", {"title": "Follow up"}, self.jordan)
        self.call("updateTask", {"id": task["id"], "version": 1, "status": "waiting"}, self.jordan)
        self.assert_api_error(403, lambda: self.call("updateTask", {"id": task["id"], "version": 2, "status": "inProgress"}, self.avery))

    def test_blank_daily_sheets_roll_over_in_operational_timezone(self):
        logs = self.call("listLogs")
        self.assertEqual({item["operationalDate"] for item in logs}, {"2026-10-07"})
        self.now = datetime(2026, 10, 8, 6, 59, tzinfo=UTC)  # still October 7 Pacific
        self.assertEqual(len(self.call("listLogs")), 3)
        self.now += timedelta(minutes=2)
        self.assertEqual(len(self.call("listLogs")), 6)

    def test_shift_order_checks_and_issue_acknowledgement(self):
        logs = {item["phase"]: item for item in self.call("listLogs")}
        self.assert_api_error(409, lambda: self.call("signOffLog", {"id": logs["morning"]["id"]}, self.jordan))
        self.assert_api_error(409, lambda: self.call("signOffLog", {"id": logs["night"]["id"]}, self.avery))
        issue = self.call("raiseIssue", {"category": "equipment", "details": "Printer unavailable"}, self.jordan)
        for phase in ("morning", "midday"):
            log = logs[phase]
            self.call("toggleCheck", {"id": log["id"], "checkId": log["confirmations"][0]["id"], "checked": True}, self.jordan)
            self.call("signOffLog", {"id": log["id"], "note": "Checked"}, self.jordan)
        self.assert_api_error(409, lambda: self.call("signOffLog", {"id": logs["midday"]["id"], "reviewedIssueIds": []}, self.avery))
        handoff = self.call("signOffLog", {"id": logs["midday"]["id"], "reviewedIssueIds": [issue["id"]]}, self.avery)
        self.assertEqual(handoff["status"], "signedOff")
        self.assertEqual(len(handoff["signOffs"]), 2)
        self.assertEqual(self.call("listIssues")[0]["status"], "open")

        self.assert_api_error(403, lambda: self.call("resolveIssue", {"id": issue["id"]}, self.manager))

    def test_photos_are_shared_bytes_not_device_paths(self):
        log = next(item for item in self.call("listLogs") if item["phase"] == "morning")
        uri = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()
        self.call("addWalkPhotos", {"id": log["id"], "photos": [{"uri": uri, "source": "upload"}]}, self.jordan)
        second = Service(self.database, self.users, now=lambda: self.now)
        stored = second.operation(self.avery, {"operation": "detailLog", "id": log["id"]})
        self.assertEqual(stored["walkPhotos"][0]["uri"], uri)
        self.assert_api_error(400, lambda: self.call("addWalkPhotos", {"id": log["id"], "photos": [{"uri": "file:///private/image.jpg", "source": "camera"}]}, self.jordan))
        self.assert_api_error(403, lambda: self.call("removeWalkPhoto", {"id": log["id"], "photoId": stored["walkPhotos"][0]["id"]}, self.jordan))

    def test_issue_conversion_deduplicates_and_does_not_silently_resolve_issue(self):
        issue = self.call("raiseIssue", {"category": "other", "details": "Investigate offline endpoint"}, self.jordan)
        task = self.task(sourceIssueId=issue["id"])
        again = self.task(sourceIssueId=issue["id"])
        self.assertEqual(task["id"], again["id"])
        self.assertEqual(len(self.call("workspace")["tasks"]), 1)
        self.call("updateTask", {"id": task["id"], "version": 1, "status": "done", "note": "Verified endpoint online"})
        self.assertEqual(self.call("listIssues")[0]["status"], "open")
        self.assertEqual(self.report()["openCount"], 1, "An unresolved source issue must remain visible after its task is done")

    def test_converting_older_issue_preserves_original_first_seen(self):
        self.now -= timedelta(days=2)
        issue = self.call("raiseIssue", {"category": "other", "details": "Older endpoint outage"}, self.jordan)
        self.now += timedelta(days=2)
        task = self.task(sourceIssueId=issue["id"])
        report = self.report()
        sections = {section["key"]: section["items"] for section in report["sections"]}
        self.assertEqual([item["id"] for item in sections["outstanding"]], [task["id"]])
        self.assertEqual(sections["new"], [])
        self.assertEqual(sections["outstanding"][0]["reference"], issue["sourceLogId"])

    def test_report_overnight_boundaries_and_saved_snapshot(self):
        older = self.task(title="Older ongoing issue")
        new = self.task(title="New overnight issue")
        boundary = self.task(title="At morning cutoff")
        with self.service.connect() as db:
            for task, seen in ((older, "2026-10-05T10:00:00Z"), (new, "2026-10-07T07:01:00Z"), (boundary, "2026-10-07T15:00:00Z")):
                task.update(createdAt=seen, updatedAt=seen)
                self.service.put(db, "tasks", task)
        report = self.report()
        sections = {section["key"]: section["items"] for section in report["sections"]}
        self.assertEqual([item["id"] for item in sections["outstanding"]], [older["id"]])
        self.assertEqual([item["id"] for item in sections["new"]], [new["id"]])
        self.call("updateTask", {"id": older["id"], "version": 1, "status": "done", "note": "Fixed"})
        snapshot = self.call("getReport", {"id": report["id"]})
        self.assertEqual(snapshot["openCount"], 3)
        self.assertEqual(snapshot["sections"][0]["items"][0]["status"], "new")

    def test_report_updated_resolved_overdue_and_no_linked_issue_double_count(self):
        issue = self.call("raiseIssue", {"category": "other", "details": "Monitor"}, self.jordan)
        task = self.task(sourceIssueId=issue["id"], dueDate="2026-10-06")
        with self.service.connect() as db:
            task.update(createdAt="2026-10-05T10:00:00Z", updatedAt="2026-10-07T14:00:00Z")
            self.service.put(db, "tasks", task)
        report = self.report()
        sections = {section["key"]: section["items"] for section in report["sections"]}
        self.assertEqual(report["openCount"], 1)
        self.assertEqual(len(sections["updated"]), 1)
        self.assertEqual(len(sections["overdue"]), 1)
        self.now -= timedelta(minutes=10)
        self.call("updateTask", {"id": task["id"], "version": 1, "status": "done", "note": "Fixed"})
        self.now += timedelta(minutes=10)
        sections = {section["key"]: section["items"] for section in self.report()["sections"]}
        self.assertEqual(len(sections["resolved"]), 1)

    def test_invalid_dates_windows_timezone_and_assignment(self):
        for payload in ({"title": "Invalid", "dueDate": "2026-02-30"}, {"title": "Invalid", "assigneeId": "outsider"}, {"title": "Invalid", "priority": "extreme"}):
            self.assert_api_error(400, lambda payload=payload: self.call("createTask", payload))
        for payload in ({"date": "2026-02-30"}, {"timezone": "Not/AZone"}, {"overnightStart": "08:00", "overnightEnd": "17:00"}, {"title": "Report\r\nInjected header"}):
            self.assert_api_error(400, lambda payload=payload: self.report(**payload))

    def test_html_and_csv_escape_untrusted_task_content(self):
        self.task(title="<script>alert(1)</script>", description="=HYPERLINK(\"https://example.test\")")
        report = self.report()
        document = render_html(report)
        self.assertNotIn("<script>", document)
        self.assertIn("&lt;script&gt;", document)
        self.assertIn("'=HYPERLINK", render_csv(report))

    def test_schedule_recipient_validation_and_disabled_default(self):
        schedule = self.call("saveSchedule", {})
        self.assertFalse(schedule["enabled"])
        self.assertEqual(self.service.claim_due(self.now), [])
        self.assert_api_error(400, lambda: self.schedule(recipients=[]))
        self.assert_api_error(400, lambda: self.schedule(recipients=["user@example.test\r\nBcc: other@example.test"]))
        self.assert_api_error(400, lambda: self.schedule(deliveryTime="07:00"))

    def test_schedule_claim_is_unique_across_concurrent_clients_and_dst(self):
        self.schedule()
        results = []
        threads = [threading.Thread(target=lambda: results.extend(self.service.claim_due(self.now))) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(results), 1)
        self.assertEqual(self.service.claim_due(self.now), [])
        self.now = datetime(2026, 11, 1, 16, 5, tzinfo=UTC)  # 08:05 PST, after DST ends
        self.assertEqual(len(self.service.claim_due(self.now)), 1)

    def test_delivery_failure_retry_success_and_unknown_recovery(self):
        self.schedule()
        def failure(_delivery, _report):
            raise DeliveryError("No SMTP configured")
        run_deliveries(self.service, failure)
        failed = self.call("workspace")["deliveries"][0]
        self.assertEqual(failed["status"], "failed")
        self.call("retryDelivery", {"id": failed["id"]})
        sent = []
        run_deliveries(self.service, lambda delivery, report: sent.append(report))
        self.assertEqual(len(sent), 1)
        self.assertEqual(self.call("workspace")["deliveries"][0]["status"], "sent")
        self.now += timedelta(days=1)
        pending = self.service.claim_due(self.now)[0][0]
        self.service.recover_deliveries()
        self.assertEqual(self.call("workspace")["deliveries"][0]["status"], "unknown")
        self.assert_api_error(409, lambda: self.call("retryDelivery", {"id": pending["id"]}))

    def test_http_auth_export_origin_and_persistent_mutations(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service, {"http://localhost:8182"}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            request = urllib.request.Request(base + "/api/session", headers={"Authorization": "Bearer test-elena"})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(json.load(response)["timezone"], "America/Los_Angeles")
            for headers, status in (({}, 401), ({"Authorization": "Bearer test-elena", "Origin": "https://outside.example.test"}, 403)):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(urllib.request.Request(base + "/api/session", headers=headers))
                self.assertEqual(caught.exception.code, status)
            body = json.dumps({"operation": "createTask", "input": {"title": "From second client"}}).encode()
            with urllib.request.urlopen(urllib.request.Request(base + "/api/operations", body, {"Authorization": "Bearer test-elena", "Content-Type": "application/json"})) as response:
                self.assertEqual(json.load(response)["title"], "From second client")
            report = self.report()
            with urllib.request.urlopen(urllib.request.Request(base + f"/api/reports/{report['id']}?format=html", headers={"Authorization": "Bearer test-elena"})) as response:
                self.assertIn(b"From second client", response.read())
        finally:
            server.shutdown()
            server.server_close()

    def test_actual_smtp_delivery_to_local_sink_only(self):
        messages = []
        class SMTPHandler(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(b"220 localhost test SMTP\r\n")
                while line := self.rfile.readline():
                    command = line.decode().strip().upper()
                    if command.startswith(("EHLO", "HELO")):
                        self.wfile.write(b"250 localhost\r\n")
                    elif command == "DATA":
                        self.wfile.write(b"354 send message\r\n")
                        parts = []
                        while (part := self.rfile.readline()) != b".\r\n":
                            if not part:
                                return
                            parts.append(part)
                        messages.append(b"".join(parts))
                        self.wfile.write(b"250 accepted\r\n")
                    elif command == "QUIT":
                        self.wfile.write(b"221 bye\r\n")
                        return
                    else:
                        self.wfile.write(b"250 ok\r\n")
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), SMTPHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            self.task()
            self.schedule()
            with patch.dict(os.environ, {"SMTP_HOST": "127.0.0.1", "SMTP_PORT": str(server.server_address[1]), "SMTP_SECURITY": "none", "SMTP_FROM": "relay@example.test", "SMTP_USER": ""}):
                run_deliveries(self.service, smtp_sender)
            self.assertEqual(len(messages), 1)
            self.assertIn(b"operations@example.test", messages[0])
            self.assertIn(b"text/html", messages[0])
            self.assertEqual(self.call("workspace")["deliveries"][0]["status"], "sent")
            run_deliveries(self.service, lambda _delivery, _report: self.fail("Unexpected duplicate delivery"))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
