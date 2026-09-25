#!/usr/bin/env python3
"""Tiny HTTP server on the Mac mini that opens all livestream apps/tabs
when Companion (Stream Deck) POSTs to /launch. Skips anything already open.

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
    "http://192.168.100.86",
    "http://192.168.100.87",
    "http://192.168.100.88",
    "http://localhost:8000",        # Companion
    "https://studio.youtube.com",
]


def is_app_running(app_name: str) -> bool:
    """True if a process with this exact name is already running."""
    result = subprocess.run(["pgrep", "-x", app_name], capture_output=True)
    return result.returncode == 0


def chrome_has_url(url: str) -> bool:
    """True if Google Chrome already has a tab whose URL starts with url."""
    script = f"""
    tell application "System Events"
        if not (exists process "Google Chrome") then return false
    end tell
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t starts with "{url}" then return true
            end repeat
        end repeat
        return false
    end tell
    """
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=4)
        return r.stdout.strip() == "true"
    except Exception:
        return False


def launch_all() -> list[str]:
    opened = []

    for app in APPS:
        # pgrep -x matches the exact process name shown in Activity Monitor
        if is_app_running(app):
            continue
        subprocess.Popen(["open", "-a", app])
        opened.append(app)

    for url in URLS:
        if chrome_has_url(url):
            continue
        subprocess.Popen(["open", url])
        opened.append(url)

    return opened


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
            opened = launch_all()
            body = ("opened: " + ", ".join(opened) if opened else "nothing new to open")
            self._respond(200, body.encode())
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
