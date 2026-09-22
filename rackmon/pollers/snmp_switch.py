"""PoE switch monitoring via SNMP v2c.

Per port we try, in order of preference:
  1. per-port power draw in watts (vendor-specific OID template from config)
  2. standard POWER-ETHERNET-MIB delivering-power status (on/off)
  3. plain link status (ifOperStatus)
Whatever is available drives the tile; missing layers degrade gracefully.

The pure functions (build_port_oids / interpret_port) are unit-tested;
only _snmp_get touches the network.
"""

from __future__ import annotations

from ..config import Config, SwitchConfig, SwitchPort
from ..state import ERROR, OK, WARN
from .base import BasePoller

OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"  # 1 = up
OID_PETH_DETECT = "1.3.6.1.2.1.105.1.1.1.6"  # 3 = deliveringPower
PETH_DELIVERING = 3
IF_UP = 1

SNMP_CHUNK = 20  # max varbinds per request, some agents choke on more


def build_port_oids(cfg: SwitchConfig, port: SwitchPort) -> dict[str, str]:
    if_index = port.if_index if port.if_index is not None else port.port
    oids = {
        "link": f"{OID_IF_OPER_STATUS}.{if_index}",
        "poe_detect": f"{OID_PETH_DETECT}.{cfg.poe_group_index}.{port.port}",
    }
    if cfg.poe_power_oid_template:
        oids["power"] = cfg.poe_power_oid_template.format(port=port.port)
    return oids


def interpret_port(raw: dict, cfg: SwitchConfig, port: SwitchPort) -> dict:
    """raw: {"link": int|None, "poe_detect": int|None, "power": int|None}"""
    link_up = raw.get("link") == IF_UP if raw.get("link") is not None else None
    detect = raw.get("poe_detect")
    delivering = detect == PETH_DELIVERING if detect is not None else None
    watts = None
    if raw.get("power") is not None:
        watts = round(raw["power"] * cfg.poe_power_scale, 1)

    if watts is not None:
        power_ok = watts >= cfg.poe_min_watts
    elif delivering is not None:
        power_ok = delivering
    else:
        power_ok = None

    if port.expect_poe:
        if power_ok is True and link_up is not False:
            ok, detail = True, (f"{watts} W, link up" if watts is not None else "powered, link up")
        elif power_ok is False:
            ok = False
            detail = (f"only {watts} W — not powered" if watts is not None else "no PoE power")
        elif link_up:
            ok, detail = True, "link up (PoE status unavailable)"
        else:
            ok, detail = False, "no link"
    else:
        ok = bool(link_up)
        detail = "link up" if link_up else "no link"

    return {
        "port": port.port,
        "label": port.label,
        "expect_poe": port.expect_poe,
        "link_up": link_up,
        "watts": watts,
        "power_ok": power_ok,
        "ok": ok,
        "detail": detail,
    }


class SnmpSwitchPoller(BasePoller):
    section = "switch"

    def __init__(self, config: Config, store):
        super().__init__(config, store, config.switch.poll_interval)
        self._engine = None
        self._target = None
        self._mod = None

    async def setup(self) -> None:
        # pysnmp >= 7 uses hlapi.v3arch.asyncio; keep a fallback for 6.x
        try:
            from pysnmp.hlapi.v3arch import asyncio as hlapi
        except ImportError:  # pysnmp 6.x layout
            from pysnmp.hlapi import asyncio as hlapi  # type: ignore
        self._mod = hlapi
        self._engine = hlapi.SnmpEngine()
        create = getattr(hlapi.UdpTransportTarget, "create", None)
        addr = (self.config.switch.ip, 161)
        if create:
            self._target = await create(addr, timeout=2.0, retries=1)
        else:
            self._target = hlapi.UdpTransportTarget(addr, timeout=2.0, retries=1)

    async def _snmp_get(self, oids: list[str]) -> dict[str, int | None]:
        """GET a list of OIDs, returning {oid: int_value_or_None}."""
        hlapi = self._mod
        results: dict[str, int | None] = {}
        for i in range(0, len(oids), SNMP_CHUNK):
            chunk = oids[i:i + SNMP_CHUNK]
            err_ind, err_stat, _, var_binds = await hlapi.get_cmd(
                self._engine,
                hlapi.CommunityData(self.config.switch.snmp_community, mpModel=1),
                self._target,
                hlapi.ContextData(),
                *(hlapi.ObjectType(hlapi.ObjectIdentity(o)) for o in chunk),
            )
            if err_ind:
                raise RuntimeError(f"Switch not answering SNMP: {err_ind}")
            if err_stat:
                raise RuntimeError(f"Switch SNMP error: {err_stat.prettyPrint()}")
            for name, value in var_binds:
                text = value.prettyPrint() if value is not None else ""
                if "No Such" in text or "noSuch" in text:
                    results[str(name)] = None
                    continue
                try:
                    results[str(name)] = int(value)
                except (ValueError, TypeError):
                    results[str(name)] = None
        return results

    async def poll(self) -> None:
        cfg = self.config.switch
        if not cfg.ip:
            self.store.update(self.section, {"ports": []}, status=WARN,
                              message="No switch IP configured")
            return
        if self._engine is None:
            await self.setup()

        port_oids = {p.port: build_port_oids(cfg, p) for p in cfg.ports}
        flat = [oid for oids in port_oids.values() for oid in oids.values()]
        values = await self._snmp_get(flat)

        ports = []
        for p in cfg.ports:
            oids = port_oids[p.port]
            raw = {key: values.get(oid) for key, oid in oids.items()}
            ports.append(interpret_port(raw, cfg, p))

        bad = [p for p in ports if not p["ok"]]
        have_power = any(p["watts"] is not None or p["power_ok"] is not None
                         for p in ports if p["expect_poe"])
        if not bad:
            message = "All ports OK" if have_power else "Links OK (PoE data unavailable)"
            status = OK
        else:
            status = ERROR
            message = "Problem: " + ", ".join(p["label"] for p in bad)
        self.store.update(self.section, {"ports": ports, "ip": cfg.ip},
                          status=status, message=message)
