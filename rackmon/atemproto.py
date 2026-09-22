"""Minimal read-only Blackmagic ATEM protocol client.

Replaces PyATEMMax, which fails to decode the initial state dump on newer
ATEM firmware (ATEM Mini Extreme ISO G2 with 9.x firmware connects but
reports everything as 'black'). This client speaks just enough of the UDP
protocol (port 9910) to monitor a switcher:

  handshake -> ACK every reliable packet -> parse only the commands we
  care about (program/preview bus, tally, input names, stream/record
  status, product name) and silently skip everything else.

Skipping unknown commands by their declared length is what makes this
robust across firmware versions: new fields simply don't matter to us.

Protocol reference: the packet format is the well-documented Skaarhoj /
libqatemcontrol layout — 12-byte header (flags+length, session id, ack
id, packet id) followed by command blocks of (u16 size, u16 pad, 4-char
name, payload).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Callable

log = logging.getLogger("rackmon.atem.proto")

ATEM_PORT = 9910

FLAG_ACK_REQUEST = 0x01
FLAG_HELLO = 0x02
FLAG_ACK = 0x10

SILENCE_TIMEOUT = 5.0  # no packets for this long -> reconnect
RECONNECT_DELAY = 3.0


def _u16(data: bytes, offset: int = 0) -> int:
    return int.from_bytes(data[offset:offset + 2], "big")


def build_header(flags: int, length: int, session: int,
                 ack_id: int = 0, packet_id: int = 0) -> bytes:
    word0 = (flags << 11) | (length & 0x07FF)
    return (word0.to_bytes(2, "big") + session.to_bytes(2, "big")
            + ack_id.to_bytes(2, "big") + b"\x00\x00\x00\x00"
            + packet_id.to_bytes(2, "big"))


def parse_header(data: bytes) -> tuple[int, int, int, int]:
    """Returns (flags, length, session, packet_id)."""
    word0 = _u16(data, 0)
    return word0 >> 11, word0 & 0x07FF, _u16(data, 2), _u16(data, 10)


def split_commands(payload: bytes):
    """Yields (name, data) for each command block in a packet payload."""
    i = 0
    while i + 8 <= len(payload):
        size = _u16(payload, i)
        if size < 8 or i + size > len(payload):
            break  # malformed block; stop rather than misparse
        name = payload[i + 4:i + 8].decode("ascii", "replace")
        yield name, payload[i + 8:i + size]
        i += size


class AtemMonitor:
    """Connects to an ATEM and keeps a live state snapshot. Read-only."""

    def __init__(self, ip: str, on_command: Callable[[str, bytes], None] | None = None):
        self.ip = ip
        self.on_command = on_command  # diagnostics hook (atemtest --dump)
        self.model: str = ""
        self.program: dict[int, int] = {}   # mix effect -> source
        self.preview: dict[int, int] = {}
        self.tally_by_source: dict[int, int] = {}  # source -> flag bits
        self.tally_by_index: dict[int, int] = {}   # input order -> flag bits
        self.input_names: dict[int, str] = {}
        self.streaming: bool | None = None
        self.recording: bool | None = None
        self._handshaked = False
        self._last_rx = 0.0
        self._transport = None

    @property
    def connected(self) -> bool:
        return self._handshaked and (time.time() - self._last_rx) < SILENCE_TIMEOUT

    async def run(self) -> None:
        """Maintain a session forever; reconnect after silence or errors."""
        while True:
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — keep trying
                log.debug("ATEM session error: %s", exc)
            self._handshaked = False
            await asyncio.sleep(RECONNECT_DELAY)

    async def _session(self) -> None:
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _AtemProtocol(self), remote_addr=(self.ip, ATEM_PORT))
        self._transport = transport
        try:
            session = random.randint(1, 0x7FFF)
            hello = build_header(FLAG_HELLO, 20, session) + bytes(
                [0x01, 0, 0, 0, 0, 0, 0, 0])
            self._last_rx = time.time()  # grace period for the reply
            transport.sendto(hello)
            while time.time() - self._last_rx < SILENCE_TIMEOUT:
                await asyncio.sleep(1.0)
        finally:
            transport.close()
            self._transport = None

    # -- called from _AtemProtocol --

    def _receive(self, data: bytes) -> None:
        if len(data) < 12:
            return
        flags, length, session, packet_id = parse_header(data)
        self._last_rx = time.time()
        if self._transport is None:
            return
        if flags & FLAG_HELLO:
            # answer the hello, then the init dump starts arriving
            self._transport.sendto(build_header(FLAG_ACK, 12, session))
            return
        if flags & FLAG_ACK_REQUEST:
            self._transport.sendto(
                build_header(FLAG_ACK, 12, session, ack_id=packet_id))
            self._handshaked = True
        for name, payload in split_commands(data[12:length]):
            if self.on_command is not None:
                self.on_command(name, payload)
            try:
                self._handle(name, payload)
            except Exception:  # noqa: BLE001 — one bad block must not kill parsing
                log.debug("failed parsing ATEM command %s", name)

    def _handle(self, name: str, d: bytes) -> None:
        if name == "_pin":  # product name
            self.model = d.split(b"\x00")[0].decode("ascii", "replace").strip()
        elif name == "PrgI" and len(d) >= 4:
            self.program[d[0]] = _u16(d, 2)
        elif name == "PrvI" and len(d) >= 4:
            self.preview[d[0]] = _u16(d, 2)
        elif name == "TlIn" and len(d) >= 2:
            count = _u16(d, 0)
            for i in range(min(count, len(d) - 2)):
                self.tally_by_index[i + 1] = d[2 + i]
        elif name == "TlSr" and len(d) >= 2:
            count = _u16(d, 0)
            for i in range(count):
                off = 2 + i * 3
                if off + 3 <= len(d):
                    self.tally_by_source[_u16(d, off)] = d[off + 2]
        elif name == "InPr" and len(d) >= 22:
            source = _u16(d, 0)
            longname = d[2:22].split(b"\x00")[0].decode("ascii", "replace")
            if longname:
                self.input_names[source] = longname
        elif name == "StRS" and len(d) >= 2:
            # stream status: 1 idle, 2 connecting, 4 on-air, 0x20 stopping
            status = _u16(d, 0)
            self.streaming = bool(status & 0x04)
        elif name == "RecS" and len(d) >= 2:
            self.recording = bool(_u16(d, 0) & 0x01)


class _AtemProtocol(asyncio.DatagramProtocol):
    def __init__(self, monitor: AtemMonitor):
        self.monitor = monitor

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ARG002
        self.monitor._receive(data)

    def error_received(self, exc) -> None:
        log.debug("ATEM socket error: %s", exc)
