"""SNMP explorer for finding your switch's PoE power OIDs.

Usage:
    python -m rackmon.tools.snmpscan 192.168.1.2 public
    python -m rackmon.tools.snmpscan 192.168.1.2 public --base 1.3.6.1.4.1
    python -m rackmon.tools.snmpscan 192.168.1.2 public --diff

--diff mode is the non-networking-person path to the power OID:
it walks the switch, waits while you unplug a camera, walks again,
and prints only the values that changed. The OID whose number dropped
by a few thousand (milliwatts) or a few watts is your power OID.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

DEFAULT_BASE = "1.3.6.1"


async def _walk(ip: str, community: str, base: str) -> dict[str, str]:
    try:
        from pysnmp.hlapi.v3arch import asyncio as hlapi
    except ImportError:
        from pysnmp.hlapi import asyncio as hlapi  # type: ignore

    engine = hlapi.SnmpEngine()
    create = getattr(hlapi.UdpTransportTarget, "create", None)
    if create:
        target = await create((ip, 161), timeout=2.0, retries=1)
    else:
        target = hlapi.UdpTransportTarget((ip, 161), timeout=2.0, retries=1)

    results: dict[str, str] = {}
    walker = hlapi.walk_cmd(
        engine,
        hlapi.CommunityData(community, mpModel=1),
        target,
        hlapi.ContextData(),
        hlapi.ObjectType(hlapi.ObjectIdentity(base)),
        lexicographicMode=False,
    )
    async for err_ind, err_stat, _, var_binds in walker:
        if err_ind:
            print(f"\nERROR: switch not answering SNMP: {err_ind}", file=sys.stderr)
            print("Check: is SNMP enabled on the switch? Right IP? "
                  "Right community string?", file=sys.stderr)
            sys.exit(1)
        if err_stat:
            break
        for name, value in var_binds:
            results[str(name)] = value.prettyPrint()
    return results


def _numeric(text: str) -> float | None:
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


async def main_async() -> None:
    parser = argparse.ArgumentParser(
        description="Walk a switch's SNMP tree; --diff finds PoE power OIDs")
    parser.add_argument("ip")
    parser.add_argument("community", nargs="?", default="public")
    parser.add_argument("--base", default=DEFAULT_BASE,
                        help=f"OID subtree to walk (default {DEFAULT_BASE})")
    parser.add_argument("--diff", action="store_true",
                        help="walk twice with a pause; print only changed values")
    args = parser.parse_args()

    print(f"Walking {args.ip} (community '{args.community}', base {args.base})…")
    first = await _walk(args.ip, args.community, args.base)
    print(f"  got {len(first)} values")

    if not args.diff:
        for oid, value in first.items():
            print(f"{oid} = {value}")
        return

    print("\nNow UNPLUG one camera from the switch, wait ~10 seconds,")
    input("then press Enter to scan again… ")
    second = await _walk(args.ip, args.community, args.base)

    print("\nValues that CHANGED (ignore counters that only went up a little):")
    interesting = []
    for oid, before in first.items():
        after = second.get(oid)
        if after is None or after == before:
            continue
        n_before, n_after = _numeric(before), _numeric(after)
        marker = ""
        if n_before is not None and n_after is not None and n_after < n_before:
            marker = "   <-- value DROPPED, likely a power/status OID"
            interesting.append(oid)
        print(f"{oid}: {before} -> {after}{marker}")

    if interesting:
        print("\nBest candidates for config.yaml poe_power_oid_template:")
        for oid in interesting:
            head, _, tail = oid.rpartition(".")
            print(f'  "{head}.{{port}}"   (this was port {tail})')
        print("If the 'before' number looked like milliwatts (e.g. 6400 for a "
              "~6 W camera), set poe_power_scale: 0.001; if it looked like "
              "watts (6 or 64 for 6.4 W), use 1.0 or 0.1.")


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
