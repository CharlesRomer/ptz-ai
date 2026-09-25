#!/usr/bin/env python3
"""Tiny HTTP server on the Mac mini that opens all livestream apps/tabs
when Companion (Stream Deck) POSTs to /launch.

Run once at login via a LaunchAgent — see com.rackmon.launcher.plist.
Listens on 127.0.0.1:8090 (localhost only).
"""

import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8090

APPS = [
    "OBS",
    "ATEM Software Control",
    "Hive",
]

URLS = [
    # Camera web UIs
    "http://192.168.100.86",
    "http://192.168.100.87",
    "http://192.168.100.88",
    # Companion UI
    "http://localhost:8000",
    # YouTube Studio
    "https://studio.youtube.com",
]


def launch_all() -> None:
    for app in APPS:
        subprocess.Popen(["open", "-a", app])
    if URLS:
        subprocess.Popen(["open"] + URLS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence request logs

    def do_GET(self):
        if self.path == "/status":
            self._respond(200, b"ok")
        else:
            self._respond(404, b"not found")

    def do_POST(self):
        if self.path == "/launch":
            launch_all()
            self._respond(200, b"launched")
        else:
            self._respond(404, b"not found")

    def _respond(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"launch-server listening on port {PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
