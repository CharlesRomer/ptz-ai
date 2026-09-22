# Finding your switch's PoE power OID (no networking knowledge needed)

## What this is about, in plain words

SNMP is a simple question-answer protocol that switches speak. Every fact the
switch knows lives at a numeric address called an **OID** — like
`1.3.6.1.2.1.2.2.1.8.3` = "is port 3's link up".

Link status and basic "PoE on/off" use *standard* addresses that rackmon
already knows. But **how many watts a port is delivering** lives at a
*vendor-specific* address — Netgear, TP-Link and Ubiquiti each picked their
own. So you find your switch's address once, paste it into the config, and
you're done forever.

Why bother: watts are the truth. A camera can be plugged in (link up) but not
actually powered, or a half-dead camera can draw 0.4 W instead of its usual
6 W. The wattage tile catches both.

## Step 0 — enable SNMP on the switch

Log into the switch's web admin page. Look for **SNMP** (often under System,
Management, or Security). Enable **SNMP v1/v2c, read-only**. It will ask for a
**community string** — that's just a password-word; `public` is the common
default. Put the same word in `config.yaml` under `snmp_community`.

## Step 1 — check rackmon can talk to the switch at all

On the mini PC:

```bat
cd C:\rackmon
.venv\Scripts\python -m rackmon.tools.snmpscan 192.168.1.2 public
```

(your switch IP and community string). Hundreds of lines of `OID = value`
means it works. An error means: wrong IP, SNMP not enabled, or wrong
community string — fix that first.

## Step 2 — let the scanner find the power OID for you

```bat
.venv\Scripts\python -m rackmon.tools.snmpscan 192.168.1.2 public --diff
```

The tool scans, then asks you to **unplug one camera** from the switch and
press Enter. It scans again and prints only what changed, flagging values that
*dropped* — a powered camera disappearing makes its port's power reading fall
to 0. The output ends with ready-to-paste suggestions like:

```
Best candidates for config.yaml poe_power_oid_template:
  "1.3.6.1.4.1.4526.11.15.1.12.1.1.9.{port}"   (this was port 2)
```

Plug the camera back in afterwards.

## Step 3 — paste into config.yaml

```yaml
switch:
  poe_power_oid_template: "1.3.6.1.4.1.4526.11.15.1.12.1.1.9.{port}"
  poe_power_scale: 0.001
```

**Scale**: if the "before" number for a ~6 W camera looked like `6400`, the
switch reports **milliwatts** → scale `0.001`. If it looked like `64` →
tenths of a watt → `0.1`. If it looked like `6` → watts → `1.0`.

Restart the RackMon service. Screen 1 port tiles now show real watts. Verify:
unplug a camera → its tile must go red within ~15 seconds.

## Notes

- Starting points that are sometimes right out of the box (verify with the
  scanner anyway): Netgear smart switches
  `1.3.6.1.4.1.4526.11.15.1.12.1.1.9.{port}` (mW); TP-Link
  `1.3.6.1.4.1.11863.6.56.1.1.2.1.1.6.{port}` (0.1 W); some switches implement
  the standard `1.3.6.1.2.1.105.1.1.1.10.1.{port}`.
- If ports appear under odd interface numbers (link always shows down for a
  port you know is up), the switch's ifIndex numbering doesn't match the
  printed port numbers — find the right index in the scanner output near
  `1.3.6.1.2.1.2.2.1.2` (`ifDescr`, the port names) and set `if_index:` on
  that port entry in the config.
- **No wattage OID found?** Some cheap switches simply don't expose it. You
  still get link status and (usually) standard PoE on/off — leave
  `poe_power_oid_template: null` and rackmon uses those.
