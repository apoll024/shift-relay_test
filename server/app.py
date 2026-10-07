"""Run with python -m server.app. Place behind HTTPS for shared deployments."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import secrets
import signal
import smtplib
import ssl
import threading
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .core import ApiError, Service, render_csv, render_html

LOGGER = logging.getLogger("shift-relay")


def init_users(path):
    destination = Path(path)
    tokens_path = destination.with_name("access-tokens.json")
    if destination.exists() or tokens_path.exists():
        raise SystemExit("Users file already exists; refusing to overwrite credentials.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    users = []
    tokens = {}
    for identifier, name in (("jordan", "Jordan Lee"), ("avery", "Avery Smith"), ("elena", "Elena Ruiz")):
        token = secrets.token_urlsafe(32)
        tokens[identifier] = token
        users.append({"id": identifier, "name": name, "tokenHash": hashlib.sha256(token.encode()).hexdigest()})
    with destination.open("x") as file:
        os.chmod(destination, 0o600)
        json.dump(users, file, indent=2)
    with tokens_path.open("x") as file:
        os.chmod(tokens_path, 0o600)
        json.dump(tokens, file, indent=2)
    print(f"Created {destination} and {tokens_path}. Share each token privately with its account holder; never commit these files.")


def load_users(path):
    try:
        users = json.loads(Path(path).read_text())
        if not isinstance(users, list) or {item["id"] for item in users} != {"jordan", "avery", "elena"} or len(users) != 3:
            raise ValueError()
        for item in users:
            if not isinstance(item["name"], str) or not item["name"].strip() or not isinstance(item["tokenHash"], str) or len(item["tokenHash"]) != 64:
                raise ValueError()
        if len({item["tokenHash"] for item in users}) != 3:
            raise ValueError()
        return users
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit("Invalid or missing users file. Run python -m server.app --init-users first.") from None


class DeliveryError(Exception):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def smtp_sender(delivery, report):
    host = os.environ.get("SMTP_HOST")
    sender = os.environ.get("SMTP_FROM")
    if not host or not sender:
        raise DeliveryError("SMTP_HOST and SMTP_FROM must be configured on the server.")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(delivery["recipients"])
    message["Subject"] = f"{report['title']} — {report['date']}"
    message["Message-ID"] = f"<shift-relay-{delivery['id']}@{sender.split('@')[-1]}>"
    summary = [f"{report['title']} — {report['date']}", f"Open work: {report['openCount']}", report["scope"]]
    for section in report["sections"]:
        summary.append(f"\n{section['title']} ({len(section['items'])})")
        summary.extend(f"- {item['title']} [{item['priority']} / {item['status']}] — {item['assignee']}" for item in section["items"])
    message.set_content("\n".join(summary))
    document = render_html(report)
    message.add_alternative(document, subtype="html")
    message.add_attachment(document.encode(), maintype="text", subtype="html", filename=f"shift-relay-{report['date']}.html")
    sending = False
    try:
        security = os.environ.get("SMTP_SECURITY", "starttls")
        if security not in ("starttls", "ssl", "none"):
            raise DeliveryError("SMTP_SECURITY must be starttls, ssl, or none.")
        port = int(os.environ.get("SMTP_PORT", "465" if security == "ssl" else "587"))
        constructor = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
        kwargs = {"timeout": 30}
        if security == "ssl":
            kwargs["context"] = ssl.create_default_context()
        with constructor(host, port, **kwargs) as client:
            if security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if os.environ.get("SMTP_USER"):
                client.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            sending = True
            refused = client.send_message(message)
            if refused:
                raise DeliveryError("Some recipients were refused; others may have received the report. Check the mail server.", uncertain=True)
    except DeliveryError:
        raise
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as error:
        raise DeliveryError(f"Mail server rejected the message ({type(error).__name__}). Correct settings and retry.") from None
    except (OSError, smtplib.SMTPException, ValueError) as error:
        raise DeliveryError(f"Delivery failed ({type(error).__name__}). Check SMTP settings and server logs.", uncertain=sending) from None


def run_deliveries(service, sender=smtp_sender):
    for delivery, report in service.claim_due(service.now()):
        try:
            sender(delivery, report)
        except DeliveryError as error:
            service.finish_delivery(delivery["id"], "unknown" if error.uncertain else "failed", str(error))
        except Exception:
            service.finish_delivery(delivery["id"], "unknown", "Unexpected delivery error. Check the mail server before resending.")
            LOGGER.exception("Delivery worker failed")
        else:
            service.finish_delivery(delivery["id"], "sent")


def make_handler(service, origins):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ShiftRelay"

        def log_message(self, format_string, *args):
            # Never log Authorization headers, request bodies, or exported work data.
            LOGGER.info("%s %s", self.command, self.path.split("?")[0])

        def origin_allowed(self):
            origin = self.headers.get("Origin")
            if origin and origin not in origins:
                raise ApiError(403, "This app origin is not allowed by the server.")

        def reply(self, status, body, content_type="application/json", filename=None):
            data = json.dumps(body).encode() if content_type == "application/json" else body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; sandbox")
            origin = self.headers.get("Origin")
            if origin in origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def user(self):
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer ") or len(header) > 512:
                raise ApiError(401, "Sign in with your private access token.")
            return service.authenticate(header[7:])

        def do_OPTIONS(self):
            try:
                self.origin_allowed()
            except ApiError as error:
                self.reply(error.status, {"message": error.message})
                return
            self.send_response(204)
            if self.headers.get("Origin") in origins:
                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def do_GET(self):
            try:
                self.origin_allowed()
                url = urlsplit(self.path)
                if url.path == "/health":
                    self.reply(200, {"status": "ok"})
                    return
                user = self.user()
                if url.path == "/api/session":
                    self.reply(200, {**user, "timezone": str(service.timezone)})
                elif url.path.startswith("/api/reports/"):
                    identifier = url.path.removeprefix("/api/reports/")
                    report = service.operation(user, {"operation": "getReport", "input": {"id": identifier}})
                    format_name = parse_qs(url.query).get("format", ["html"])[0]
                    if format_name not in ("html", "csv"):
                        raise ApiError(400, "Choose HTML or CSV export.")
                    document = render_html(report) if format_name == "html" else render_csv(report)
                    self.reply(200, document, "text/html" if format_name == "html" else "text/csv", f"shift-relay-{report['date']}.{format_name}")
                else:
                    raise ApiError(404, "Endpoint not found.")
            except ApiError as error:
                self.reply(error.status, {"message": error.message})
            except Exception:
                LOGGER.exception("Request failed")
                self.reply(500, {"message": "The service could not complete this request. Try again."})

        def do_POST(self):
            try:
                self.origin_allowed()
                user = self.user()
                if self.path != "/api/operations":
                    raise ApiError(404, "Endpoint not found.")
                if self.headers.get_content_type() != "application/json":
                    raise ApiError(415, "Send application/json.")
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 32_000_000:
                    raise ApiError(413, "Request must be smaller than 32 MB.")
                self.connection.settimeout(30)
                request = json.loads(self.rfile.read(length))
                self.reply(200, service.operation(user, request))
            except ApiError as error:
                self.reply(error.status, {"message": error.message})
            except (ValueError, UnicodeDecodeError):
                self.reply(400, {"message": "Send a valid JSON request."})
            except Exception:
                LOGGER.exception("Request failed")
                self.reply(500, {"message": "The service could not complete this request. Try again."})

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-users", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run due delivery jobs once without starting HTTP")
    args = parser.parse_args()
    users_file = os.environ.get("SHIFT_RELAY_USERS_FILE", "server/data/users.json")
    if args.init_users:
        init_users(users_file)
        return
    service = Service(os.environ.get("SHIFT_RELAY_DB", "server/data/shift-relay.sqlite3"), load_users(users_file), os.environ.get("SHIFT_RELAY_TIMEZONE", "America/Los_Angeles"))
    logging.basicConfig(level=logging.INFO)
    if args.once:
        run_deliveries(service)
        return
    service.recover_deliveries()
    origins = set(os.environ.get("SHIFT_RELAY_ORIGINS", "http://localhost:8181,http://localhost:8081").split(","))
    server = ThreadingHTTPServer((os.environ.get("SHIFT_RELAY_HOST", "127.0.0.1"), int(os.environ.get("SHIFT_RELAY_PORT", "8090"))), make_handler(service, origins))
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                run_deliveries(service)
            except Exception:
                LOGGER.exception("Scheduler tick failed; it will try again next tick")
            stop.wait(30)

    threading.Thread(target=worker, daemon=True).start()

    def shutdown(_signal, _frame):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    LOGGER.info("Shared service listening on %s:%s", *server.server_address)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
