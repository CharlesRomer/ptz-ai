"""Standalone ATEM connection test using rackmon's built-in client.

Usage:
    python -m rackmon.tools.atemtest 192.168.100.240
    python -m rackmon.tools.atemtest 192.168.100.240 --dump

Default mode prints model + program/preview/tally once a second for 30
seconds — cut between cameras on the ATEM and watch the numbers follow.

--dump prints the name of every protocol command the ATEM sends for 10
seconds. If you see a stream of 4-letter names (InPr, PrgI, Time, ...)
the protocol link works even if the normal display looks wrong — send
that output to whoever is debugging.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Test ATEM connectivity/tally")
    parser.add_argument("ip")
    parser.add_argument("--dump", action="store_true",
                        help="print raw command names for 10s")
    args = parser.parse_args()

    from ..atemproto import AtemMonitor

    seen: Counter[str] = Counter()

    def on_command(name: str, payload: bytes) -> None:
        if args.dump:
            first = not seen[name]
            seen[name] += 1
            if first:
                print(f"  cmd {name}  ({len(payload)} bytes)")

    monitor = AtemMonitor(args.ip, on_command=on_command)
    task = asyncio.create_task(monitor.run())

    print(f"Connecting to ATEM at {args.ip}…")
    try:
        if args.dump:
            await asyncio.sleep(10)
            print(f"\n{sum(seen.values())} commands, {len(seen)} distinct kinds.")
            print("Top:", ", ".join(f"{n}×{c}" for n, c in seen.most_common(10)))
        else:
            for _ in range(30):
                if not monitor.connected:
                    print("  (not connected yet…)")
                else:
                    tally = {
                        src: flag for src, flag in
                        sorted(monitor.tally_by_source.items()) if src <= 20
                    }
                    print(f"  model={monitor.model!r}  "
                          f"PGM={monitor.program.get(0)}  "
                          f"PVW={monitor.preview.get(0)}  "
                          f"tally={tally}  "
                          f"stream={monitor.streaming} rec={monitor.recording}")
                await asyncio.sleep(1)
            if monitor.connected and monitor.program.get(0) is not None:
                print("\nOK: if PGM/PVW tracked your cuts, rackmon tally will work.")
            else:
                print("\nNot connected or no data — re-run with --dump and "
                      "share the output.")
    finally:
        task.cancel()


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
