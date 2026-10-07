"""Temporary local service for Playwright. Credentials are fictional test fixtures."""

import hashlib
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path

from server.app import make_handler
from server.core import Service


def main():
    with tempfile.TemporaryDirectory(prefix="shift-relay-e2e-") as directory:
        users = [{"id": identifier, "name": name, "tokenHash": hashlib.sha256(f"e2e-{identifier}-token".encode()).hexdigest()}
                 for identifier, name in (("jordan", "Jordan Lee"), ("avery", "Avery Smith"), ("elena", "Elena Ruiz"))]
        service = Service(Path(directory) / "relay.sqlite3", users)
        server = ThreadingHTTPServer(("127.0.0.1", 8091), make_handler(service, {"http://localhost:8182"}))
        try:
            server.serve_forever()
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
