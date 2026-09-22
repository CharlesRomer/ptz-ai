# rackmon — livestream rack monitoring dashboards

Three always-on status screens for a livestream AV rack, served by one small
Python service on the streaming mini PC and shown fullscreen on three 7"
touchscreens:

| URL | Screen | What it shows |
|---|---|---|
| `/screen1` | **System Health** | Green/red tiles: ATEM, every PoE switch port (with real power draw in watts), OBS, mini PC CPU/disk, WiFi extender, camera pings. Header says **ALL SYSTEMS GO** or **N PROBLEMS**. |
| `/screen2` | **Tally Multiview** | Grid of all camera feeds plus PROGRAM/PREVIEW, with a red border around whatever is live (driven by the ATEM's tally) and a green border on preview. Dead feeds show **NO SIGNAL**. |
| `/screen3` | **Stream Health / Checklist** | Toggle button switches between live stream stats (LIVE badge, bitrate graph, dropped frames, encoder load, YouTube confirmation) and a tap-through startup checklist for volunteers. |

No logins, no accounts — the server binds to `127.0.0.1` and the kiosks run on
the same PC.

## Try it right now (no hardware needed)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"          # Windows: .venv\Scripts\pip install -e ".[dev]"
.venv/bin/python -m rackmon --mock         # Windows: .venv\Scripts\python -m rackmon --mock
```

Open http://localhost:8080/screen1, `/screen2`, `/screen3`. Mock mode fakes the
whole rack: tally rotates between cameras every 12 seconds, bitrate wanders,
PoE wattage jitters. Open http://localhost:8080/debug to break things on
purpose (kill a camera's PoE, disconnect the ATEM, drop frames…) and watch the
dashboards react — great for volunteer training.

Run the tests with `.venv/bin/python -m pytest`.

## Real installation

1. **[docs/GATHER-FIRST.md](docs/GATHER-FIRST.md)** — the list of IPs,
   passwords and keys to collect before anything else.
2. **[docs/SETUP.md](docs/SETUP.md)** — full plain-English walkthrough:
   install on the Windows mini PC, fill in the config, enable SNMP and
   obs-websocket, install as an auto-starting service.
3. **[docs/SNMP.md](docs/SNMP.md)** — find your PoE switch's per-port power
   OID (this is what makes "is the camera actually powered?" reliable).
4. **[docs/KIOSK.md](docs/KIOSK.md)** — put the three Chrome kiosk windows on
   the three touchscreens and make them survive reboots.

## How each device is monitored

| Device | Protocol / library | What we read |
|---|---|---|
| ATEM Mini Extreme ISO G2 | built-in minimal ATEM protocol client (`rackmon/atemproto.py`) | connection, program/preview input, per-input tally, input names; stream/record state where the firmware exposes it |
| OBS (same PC) | [obs-websocket v5](https://github.com/obsproject/obs-websocket) via `simpleobsws` | stream up/down, bitrate, dropped frames, encoder/render load, record state — **OBS is the authoritative "are we live" source** — plus PROGRAM/PREVIEW images for the multiview (`GetSourceScreenshot`) |
| PoE switch | SNMP v2c via `pysnmp` | per-port link status (`ifOperStatus`), PoE delivering status (standard POWER-ETHERNET-MIB), per-port watts (vendor OID from config) |
| PTZ cameras | RTSP substream decoded by `ffmpeg` (or HTTP snapshot URL) + ping | live thumbnails for the multiview; reachability |
| Mini PC | `psutil` | CPU, memory, disk fill (recording eats disk!), uptime |
| WiFi extender / router | system `ping` | reachability |
| YouTube (optional) | YouTube Data API v3 | independent "the stream is actually visible on YouTube" confirmation |

## Architecture (for the curious)

One Python process (FastAPI + asyncio). Each device has a poller task that
writes into a shared in-memory state store; a WebSocket pushes the full state
to every open dashboard once a second. Multiview video runs at ~4 fps as JPEG
frames through `/api/frame/{id}` — plenty for "which camera is live and is it
alive", and cheap enough to not steal CPU from OBS. A poller can never crash
the process: any failure just turns its tile red and retries with backoff.
If the config file is broken, the server still starts and every page explains
the problem — a kiosk never sits on a blank screen.

```
rackmon/            the service (pollers/, video/, web/, mock/)
config/             config.example.yaml + checklist.yaml (volunteer steps)
scripts/windows/    service install, kiosk launch, monitor finder, watchdog
docs/               setup guides
tests/              pytest suite (runs with zero hardware)
```

## Known limitations

- **ATEM stream/record tiles may show "unknown"** until the switcher sends
  those status commands (varies by firmware). OBS (which does the actual
  YouTube streaming) is the reliable source; verify the ATEM ISO-record tile
  on your hardware during commissioning. (`python -m rackmon.tools.atemtest
  <ip> --dump` shows exactly what the switcher sends.)
- **Per-port PoE wattage needs a vendor OID** — 10 minutes with
  `docs/SNMP.md` + the bundled scanner. Until then you still get link + PoE
  on/off status.
- **YouTube tile only sees public streams** (API-key limitation). Unlisted
  streams show "not detected (may be unlisted)" — yellow, never red.
- Multiview is ~4 fps by design. If you later want fluid motion, run
  [go2rtc](https://github.com/AlexxIT/go2rtc) as a sidecar and point the
  tiles at its WebRTC player — the JPEG pipeline needs no changes to coexist.
