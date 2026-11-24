#!/usr/bin/env python3
"""Local helper for FamilyAIUITests.

The UI test process cannot receive the member Token through its environment,
so it fetches both the base URL and Token from this loopback-only endpoint.
Run only while executing the UI test; stop it afterwards.

    FAMILYAI_UI_TOKEN=<token> python3 ios/scripts/ui-test-credentials.py
"""

import json
import os
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer

TOKEN = os.environ.get("FAMILYAI_UI_TOKEN", "")
BASE_URL = os.environ.get("FAMILYAI_UI_BASE_URL", "http://192.168.5.18:8000")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if not TOKEN:
            self.send_error(500, "FAMILYAI_UI_TOKEN is not set")
            return
        body = json.dumps({"base_url": BASE_URL, "token": TOKEN}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


class Server(HTTPServer):
    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


if __name__ == "__main__":
    Server(("127.0.0.1", 8765), Handler).serve_forever()
