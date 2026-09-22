"""Standalone ATEM connection test.

Usage:  python -m rackmon.tools.atemtest 192.168.1.240

Connects, prints the model, then prints program/preview/tally once a
second for 30 seconds. Cut between cameras on the ATEM and watch the
numbers change — that proves tally will work on Screen 2.
"""

from __future__ import annotations

import sys
import time


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m rackmon.tools.atemtest <atem-ip>")
        sys.exit(2)
    ip = sys.argv[1]

    import PyATEMMax

    switcher = PyATEMMax.ATEMMax()
    print(f"Pinging ATEM at {ip}…")
    switcher.ping(ip)
    if not switcher.waitForConnection(infinite=False, timeout=5):
        print("No answer. Check the IP, and that this PC and the ATEM are "
              "on the same network (both plugged into the PoE switch).")
        sys.exit(1)
    switcher.disconnect()

    print("Ping OK — connecting fully…")
    switcher.connect(ip)
    switcher.waitForConnection(infinite=False, timeout=10)
    print(f"Connected: {switcher.atemModel}")
    print("Watching tally for 30s — cut between cameras on the ATEM now:")
    try:
        for _ in range(30):
            pgm = switcher.programInput[0].videoSource
            pvw = switcher.previewInput[0].videoSource
            print(f"  PGM={pgm}  PVW={pvw}")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    switcher.disconnect()
    print("Done. If PGM/PVW tracked your cuts, rackmon tally will work.")


if __name__ == "__main__":
    main()
