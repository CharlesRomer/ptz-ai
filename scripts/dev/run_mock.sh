#!/usr/bin/env bash
# Dev/demo on Mac or Linux: full fake rack, no hardware needed.
# Screens: http://localhost:8080/screen1 /screen2 /screen3, toggles at /debug
cd "$(dirname "$0")/../.."
exec .venv/bin/python -m rackmon --mock "$@"
