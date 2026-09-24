# The rack network — address map and recovery commands

**Never retype these numbers — copy-paste from here.** A single-digit typo in
a static IP took the Mac mini offline for a morning (two machines fighting
over one address; macOS silently backs off when it loses).

## The map

| Device | IP | How it's set |
|---|---|---|
| Rack router (LAN / gateway) | `192.168.100.150` | its own LAN setting |
| Mini PC (dashboards) | `192.168.100.220` | Windows static (below) |
| Mac mini (OBS/streaming) | `192.168.100.230` | macOS static (below) |
| ATEM Mini Extreme ISO G2 | `192.168.100.240` | ATEM Setup over USB |
| Cam 1 / Cam 2 / Cam 3 | `.86` / `.87` / `.89` | camera web UI |
| DNS everywhere | `8.8.8.8`, `1.1.1.1` | set with each static |

Statics live in the `.200`+ and `.8x` zones, outside the router's DHCP pool.
The venue's internet plugs into the router's **WAN** port; everything else
hangs off the PoE switch. Nothing here changes between venues.

## Set the mini PC's address (admin PowerShell)

```powershell
netsh interface ip set address "Ethernet 2" static 192.168.100.220 255.255.255.0 192.168.100.150
netsh interface ip set dns "Ethernet 2" static 8.8.8.8
netsh interface ip add dns "Ethernet 2" 1.1.1.1 index=2
```

## Set the Mac mini's address (Terminal)

```bash
networksetup -setmanual "Ethernet" 192.168.100.230 255.255.255.0 192.168.100.150
networksetup -setdnsservers "Ethernet" 8.8.8.8 1.1.1.1
networksetup -setv6automatic "Ethernet"
```

("Ethernet" = the built-in port, device `en0`. The Mac lists many stale
services from old adapters and other ATEMs — check what owns en0 with
`networksetup -listnetworkserviceorder` if in doubt. The service named
"ATEM Mini Extreme ISO G2" is the ATEM's USB-C control link — not internet.)

## When any machine "has no internet" — the ladder

Run in order; the first failure names the broken layer:

1. `ping 192.168.100.150` — fails → LAN: cable, switch port, wrong static,
   or an **IP conflict** (config looks right but no address takes → check
   for a conflict notification; find the squatter from another machine with
   `ping <ip>` then `arp -a`).
2. `ping 8.8.8.8` — fails → router has no internet: venue cable in the WAN
   port? router rebooted?
3. `ping google.com` — fails → DNS missing: re-run the DNS command above.

Screen 1 shows most of this at a glance: the Mini PC tile warns
**"WRONG IP"** if this PC loses its expected address (`system.expected_ip`
in config.yaml), and Rack Router / Internet / camera tiles isolate the rest.
