# Gather this first

Collect everything on this list *before* setting up rackmon. Write the values
down — you'll paste them into `config/config.yaml`.

## 1. IP addresses

Every device needs a **fixed** IP address. The easiest way: log into the
building router's admin page, find the connected-devices list, and give each
device a *DHCP reservation* (sometimes called "static lease" or "always use
this address") so its IP never changes after a power cut.

| Device | Where to find its IP | Write it here |
|---|---|---|
| ATEM Mini Extreme ISO G2 | Blackmagic "ATEM Setup" app with the ATEM connected by USB, or router client list | `___.___.___.___` |
| PoE switch | Its admin web page / label on the box / router client list | `___.___.___.___` |
| Each PTZ camera | Camera vendor's discovery tool, or router client list (they usually show up named) | cam1 `___` cam2 `___` cam3 `___` |
| WiFi extender router | Router client list | `___.___.___.___` |
| Building router (gateway) | On the mini PC: `ipconfig` → "Default Gateway" | `___.___.___.___` |
| This mini PC | `ipconfig` → "IPv4 Address" (for reference) | `___.___.___.___` |

## 2. PoE switch

- [ ] **Admin login** for the switch's web page (often printed on the switch,
      e.g. admin/password — change it if it's the default).
- [ ] **SNMP enabled** with a **community string** (a password-like word,
      often `public` by default). Where: switch web page → usually under
      *System*, *Management*, or *SNMP*. Enable "SNMP v1/v2c read-only".
      Write the community string here: `________`
- [ ] **Which camera is in which port** — physically look at the switch and
      note the port numbers: Cam 1 → port `__`, Cam 2 → port `__`,
      Cam 3 → port `__`, uplink → port `__`, WiFi extender → port `__`,
      mini PC → port `__`.
- [ ] Switch **brand + model** (for docs/SNMP.md): `________________`

## 3. OBS (on the mini PC)

- [ ] OBS → **Tools → WebSocket Server Settings** → check **Enable WebSocket
      server**. Note the **port** (default 4455) and click **Show Connect
      Info** for the **password**: `________`
- [ ] Two OBS sources (or scenes) showing the ATEM's **program** feed and (if
      you have one) a **preview/multiview** feed. Note their exact names as
      they appear in OBS: `________` / `________`. (The ATEM appears in OBS as
      a webcam/USB source; that source *is* your program feed.)

## 4. Cameras ("Orb" PTZ)

- [ ] The camera's **web page login** (usually `admin` + a password you set).
- [ ] The **RTSP URL of the low-res substream** for each camera. Check the
      camera's web page under *Network → RTSP*, or the manual. Common shapes:
      `rtsp://admin:PASS@IP:554/stream2`,
      `rtsp://admin:PASS@IP:554/2`, or
      `rtsp://admin:PASS@IP:554/cam/realmonitor?channel=1&subtype=1`
      Test it on any PC with VLC: *Media → Open Network Stream*.
- [ ] If RTSP is a pain, look for an **HTTP snapshot URL** instead
      (e.g. `http://IP/snapshot.jpg`) — rackmon supports either, per camera.

## 5. YouTube (optional — skip freely)

Only needed for the independent "actually live on YouTube" confirmation, and
it only works for **public** streams.

- [ ] A free **API key**: console.cloud.google.com → create project → enable
      **YouTube Data API v3** → Credentials → Create credentials → API key.
- [ ] Your **channel ID**: YouTube Studio → Settings → Channel → Advanced
      settings (looks like `UCxxxxxxxxxxxxxxxxxxxxxx`).

## 6. Software on the mini PC

- [ ] **Python 3.11 or newer** — python.org/downloads (tick "Add python.exe
      to PATH" in the installer).
- [ ] **ffmpeg** (for RTSP camera thumbnails) — see docs/SETUP.md step 3.
- [ ] **Google Chrome** (for the kiosk windows).
- [ ] **NSSM** (tiny service wrapper, recommended) — nssm.cc/download.
