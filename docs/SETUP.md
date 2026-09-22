# Setup — Windows mini PC, step by step

Work through [GATHER-FIRST.md](GATHER-FIRST.md) before starting. Every step
here assumes you have those IPs and passwords written down.

> **You only ever need a keyboard/monitor on the mini PC once** — to get it
> on the network and install a remote-control tool. After that, do everything
> (including all of this guide) from your Mac: see
> [Controlling the mini PC from your Mac](#controlling-the-mini-pc-from-your-mac)
> at the bottom. Once the guide is done, the PC boots straight into the
> dashboards with nothing attached but power and network.

## 0. Get the code onto the mini PC (over the web)

No git or USB stick needed:

1. On the mini PC, open a browser and go to the GitHub repository page.
2. Green **Code** button → **Download ZIP**.
3. Unzip it so the files live at **`C:\rackmon`** (i.e. `C:\rackmon\pyproject.toml`
   exists — if the ZIP unpacks into a nested folder like
   `ptz-ai-livestream-rack-dashboards`, move/rename that inner folder to
   `C:\rackmon`). The scripts assume this path.

## 1. Install Python and rackmon

1. Install **Python 3.11+** from python.org — in the installer, tick
   **"Add python.exe to PATH"**.
2. Right-click PowerShell → **Run as Administrator**:

   ```powershell
   cd C:\rackmon
   powershell -ExecutionPolicy Bypass -File scripts\windows\setup.ps1
   ```

   This creates the environment, installs everything, and puts a starter
   `config\config.yaml` in place. (Manual equivalent: `python -m venv .venv`
   then `.venv\Scripts\pip install -e .`.)

## 2. Smoke test with fake hardware

```bat
.venv\Scripts\python -m rackmon --mock
```

Open http://localhost:8080/screen1 — you should see a live board of green
tiles. Also look at `/screen2`, `/screen3` and `/debug`. Press Ctrl+C to stop.
If this works, Python-side setup is done.

## 3. Install ffmpeg (camera thumbnails)

1. Download a Windows build: https://www.gyan.dev/ffmpeg/builds/ →
   "ffmpeg-release-essentials.zip".
2. Unzip so that you end up with `C:\rackmon\ffmpeg\bin\ffmpeg.exe`.
3. Test one camera (paste your real RTSP URL):

   ```bat
   C:\rackmon\ffmpeg\bin\ffmpeg.exe -rtsp_transport tcp -i "rtsp://admin:PASS@192.168.1.11:554/stream2" -frames:v 1 test.jpg
   ```

   If `test.jpg` shows a picture from the camera, the URL is right.

## 4. Fill in the config

```bat
notepad config\config.yaml
```

The file is heavily commented — replace every placeholder with your gathered
values: ATEM IP, OBS websocket password, switch IP + community string + port
list, camera RTSP URLs, ping targets, disks. Leave
`poe_power_oid_template: null` for now (step 7 upgrades it).

Also open `config\checklist.yaml` and adjust the volunteer steps to match how
your venue actually starts up (it's plain text).

## 5. Enable the device-side settings

- **OBS**: Tools → WebSocket Server Settings → Enable. Password into config.
  Also make sure OBS itself starts with Windows (put a shortcut in
  `shell:startup`) — rackmon monitors OBS, it doesn't launch it.
- **PoE switch**: admin page → enable SNMP v1/v2c read-only, set the
  community string you put in the config.
- **ATEM**: nothing to enable — just needs to be on the same network. Verify:

  ```bat
  .venv\Scripts\python -m rackmon.tools.atemtest 192.168.1.240
  ```

  Cut between cameras on the ATEM and watch PGM/PVW numbers change.

## 6. First real run

```bat
.venv\Scripts\python -m rackmon
```

Open http://localhost:8080/screen1. Expect every tile to be green except
anything you haven't wired yet. A red tile shows a plain-language reason —
fix, and it goes green within seconds (no restart needed). Two common ones:

- *"Switch not answering SNMP"* → SNMP not enabled, wrong IP, or wrong
  community string.
- *"OBS not reachable"* → OBS closed, or WebSocket server not enabled, or
  wrong password.

## 7. Upgrade to real PoE wattage (recommended)

Follow [SNMP.md](SNMP.md) — ~10 minutes with the bundled scanner. This is what
makes Screen 1 say "Cam 2 — 6.4 W" instead of just "link up", and it's the
reliable way to know a camera is actually powered rather than merely plugged in.

## 8. Auto-start as a service

Recommended (NSSM — restarts automatically if it ever crashes):

1. Download nssm.cc/download, copy `win64\nssm.exe` to `C:\rackmon\`.
2. PowerShell **as Administrator**:

   ```powershell
   cd C:\rackmon\scripts\windows
   powershell -ExecutionPolicy Bypass -File install_service.ps1
   ```

3. Reboot the PC. http://localhost:8080/screen1 should be up before you log in.
   Logs land in `C:\rackmon\logs\`.

No-third-party alternative: import `scripts\windows\rackmon_task.xml` into
Task Scheduler (Action → Import Task…).

> If you later edit `config.yaml`, restart the service:
> `nssm restart RackMon` (or Services app → RackMon → Restart).

## 9. Kiosk screens

Follow [KIOSK.md](KIOSK.md) to put the three dashboards fullscreen on the
three 7" touchscreens and make them come back after every reboot.

## 9½. Make the PC fully hands-off (no keyboard, ever)

The complete unattended chain, and where each link gets set up:

1. Power applied → PC turns on by itself — *BIOS setting, below*
2. Windows boots → **RackMon service starts** before any login — *step 8*
3. Windows **logs in automatically** — *KIOSK.md step 4 (netplwiz / Autologon)*
4. Login → **three Chrome kiosks launch** on the three screens — *KIOSK.md (shell:startup)*
5. A kiosk dies → **watchdog relaunches it** — *KIOSK.md step 5*
6. The service crashes → **NSSM restarts it in 5 s** — *step 8*
7. **OBS** — put an OBS shortcut in `shell:startup` too, so it opens by
   itself. Optional: add ` --startstreaming` to the end of the shortcut's
   Target to go live automatically at boot.

Two extra settings worth doing:

- **BIOS "Restore on AC Power Loss" = Power On** — so after a power cut the
  PC turns itself back on without anyone pressing the button. Tap Del/F2/F7
  during boot → look under Power / APM Configuration for *Restore AC Power
  Loss* / *State After G3* → set **Power On** (or *Last State*).
- **Disable Windows sleep**: Settings → System → Power → Screen and sleep →
  set everything to **Never**.

Final test: pull the plug on the whole rack, plug it back in, walk away.
Within ~3 minutes all three screens must be showing dashboards on their own.

## 10. Commissioning day checklist (with the real rack)

Isolate one thing at a time, in this order:

1. `ping` each device IP from the mini PC (Command Prompt: `ping 192.168.1.x`).
2. `python -m rackmon.tools.snmpscan <switch-ip> <community>` — should print
   hundreds of lines. Error = SNMP not enabled / wrong community.
3. `python -m rackmon.tools.atemtest <atem-ip>` — tally follows your cuts.
4. ffmpeg one-liner from step 3 for each camera.
5. Start OBS, start rackmon, check all three screens.
6. Start a real (unlisted) test stream to YouTube and watch Screen 3.
7. Now verify the two "unknown until tested on hardware" items:
   the **ATEM record tile** on Screen 1, and your **PoE wattage OID**
   (unplug a camera — its tile must go red within ~15 seconds).
8. Pull the power on the whole rack, restore it, and confirm everything —
   service, kiosks, OBS — comes back without touching a keyboard.

## Controlling the mini PC from your Mac

There is no useful direct cable for this — a USB-C cable between a Mac and a
PC can't carry keyboard/mouse control (both machines are USB "hosts").
The neat way is remote control over the network, and since the mini PC and
your Mac can both reach the internet, it works from anywhere.

**Recommended: Chrome Remote Desktop** (free, and the right choice for a
kiosk machine — see the warning below):

1. One time only, plug any monitor/TV + keyboard into the GMKtec (or use one
   of the 7" touchscreens with the Windows on-screen keyboard). Get it on the
   network, install Chrome, go to https://remotedesktop.google.com/access,
   sign in with a Google account and click **Set up remote access** (installs
   a small host program; give the PC a name and a PIN).
2. On your Mac, open the same URL in any browser, sign in with the same
   account → click the PC's name → enter the PIN. Full screen-and-keyboard
   control, from anywhere, forever. Unplug the keyboard and monitor.

You'll see exactly what the rack screens show (the three kiosks), and when
you disconnect, the screens stay as they were — which is what you want.

**Why not Microsoft Remote Desktop?** It works (Windows *Pro* only, plus the
free "Windows App" on the Mac App Store), but RDP takes over the console: while
you're connected — and after you disconnect — the physical screens show the
Windows lock screen instead of the dashboards, until someone logs in locally.
On a kiosk box that's a trap. If you do use RDP, get the screens back by
running this in the remote session just before disconnecting:
`tscon %sessionname% /dest:console`

**Handy extra:** you can open the dashboards themselves from your Mac without
any remote-control tool. In `config\config.yaml` set `server.host: 0.0.0.0`,
restart the service, and browse to `http://<mini-pc-ip>:8080/screen1` from
anything on the same network. (This exposes the dashboards — which have no
login — to your local network only; fine for a rack LAN, just know it's on.)
