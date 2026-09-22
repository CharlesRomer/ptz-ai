# Kiosk screens — three Chrome windows on three 7" touchscreens

Goal: after any reboot or power cut, the three DisplayLink touchscreens show
the three dashboards fullscreen, no keyboard or mouse needed.

## 1. DisplayLink driver

The Eyoyo panels connect via USB-to-HDMI (DisplayLink) adapters. Install the
driver from https://www.synaptics.com/products/displaylink-graphics/downloads/windows.
After that, Windows treats the three panels as ordinary extra monitors
(System → Display shows them). Plug the USB **touch** cables into the hub; each
panel's touch is mapped to a display under
**Settings → Bluetooth & devices → Pen and touch** — or run
`Tablet PC Settings` (search "calibrate") → **Setup** to tell Windows which
touch panel belongs to which display.

## 2. Find each screen's position

Chrome places a kiosk window by *pixel coordinates* of the target display.
Get them:

```powershell
powershell -ExecutionPolicy Bypass -File C:\rackmon\scripts\windows\find_monitors.ps1
```

Output like:

```
Display 0 (primary): position X=0 Y=0      size 1920x1080
Display 1:           position X=1920 Y=0   size 1024x600
Display 2:           position X=2944 Y=0   size 1024x600
Display 3:           position X=3968 Y=0   size 1024x600
```

The 1024x600 ones are the 7" panels. Note their X,Y values.

## 3. Edit launch_kiosks.bat

Open `C:\rackmon\scripts\windows\launch_kiosks.bat` and put your three X,Y
pairs into the three `--window-position=X,Y` flags. Two things it already gets
right — don't remove them:

- Each window has its **own `--user-data-dir`** (`C:\rackmon\kiosk1..3`).
  Without this Chrome funnels all three into one process and ignores the
  positions.
- A **20-second startup delay**, giving the DisplayLink driver and the RackMon
  service time to come up first.

Double-click the .bat to test: three fullscreen dashboards should appear, one
per panel. Exit a kiosk with Alt+F4 (attach a keyboard) or Task Manager.

## 4. Run at every boot

1. Enable **auto-logon** so the desktop appears without a password:
   Win+R → `netplwiz` → untick "Users must enter a user name and password…"
   (on newer Windows 11 this checkbox may require registry tweak or Sysinternals
   Autologon — https://learn.microsoft.com/sysinternals/downloads/autologon).
2. Win+R → `shell:startup` → put a **shortcut** to `launch_kiosks.bat` there.
3. Reboot and verify all three screens come back on their own.

## 5. Optional watchdog

If someone closes a kiosk or Chrome crashes, `kiosk_watchdog.ps1` relaunches
missing windows. Schedule it:

Task Scheduler → Create Basic Task → "Kiosk watchdog" → Daily → repeat every
5 minutes for a duration of 1 day (set on the Triggers tab after creating) →
Action:

```
powershell -ExecutionPolicy Bypass -File C:\rackmon\scripts\windows\kiosk_watchdog.ps1
```

Keep the positions inside the watchdog script in sync with launch_kiosks.bat.

## Troubleshooting

- **Window on the wrong screen** → coordinates changed (DisplayLink can
  re-enumerate after driver updates). Re-run find_monitors.ps1 and update the
  .bat (and watchdog).
- **Touch controls the wrong screen** → redo Tablet PC Settings → Setup.
- **White screen on boot** → the kiosk launched before the RackMon service;
  increase the `timeout /t 20` delay. (Once loaded, the pages reconnect on
  their own — they show a red BACKEND OFFLINE banner while the service is
  down and recover automatically.)
- **Chrome shows a restore bubble** → already suppressed by
  `--disable-session-crashed-bubble`; if one sneaks through, delete the
  `C:\rackmon\kioskN` folder and relaunch.
