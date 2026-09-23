"""VISCA-over-IP (UDP) command builder + sender for PTZOptics-style cameras.

Byte layouts ported from the proven ptz-ai-controller Node implementation
(lib/visca.js): default port 1259, fire-and-forget UDP.

Builders are pure functions (unit-tested); only ViscaSender touches the
network. UDP sendto never blocks, so this is safe on the event loop.
"""

from __future__ import annotations

import logging
import socket

log = logging.getLogger("rackmon.visca")

DEFAULT_PORT = 1259

PAN_LEFT, PAN_RIGHT, PAN_STOP = 0x01, 0x02, 0x03
TILT_UP, TILT_DOWN, TILT_STOP = 0x01, 0x02, 0x03

MAX_PAN_SPEED = 24
MAX_TILT_SPEED = 20
MAX_ZOOM_SPEED = 7


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(value))))


def pan_tilt(pan_dir: int, tilt_dir: int, pan_speed: int, tilt_speed: int) -> bytes:
    """81 01 06 01 [pan_speed] [tilt_speed] [pan_dir] [tilt_dir] FF"""
    return bytes([0x81, 0x01, 0x06, 0x01,
                  _clamp(pan_speed, 1, MAX_PAN_SPEED),
                  _clamp(tilt_speed, 1, MAX_TILT_SPEED),
                  pan_dir, tilt_dir, 0xFF])


def pan_tilt_stop() -> bytes:
    return bytes([0x81, 0x01, 0x06, 0x01, 0x01, 0x01, PAN_STOP, TILT_STOP, 0xFF])


def zoom(direction: str, speed: int) -> bytes:
    """direction 'in' (tele, 0x2s) / 'out' (wide, 0x3s) / anything else = stop."""
    s = _clamp(speed, 1, MAX_ZOOM_SPEED)
    if direction == "in":
        byte = 0x20 | s
    elif direction == "out":
        byte = 0x30 | s
    else:
        byte = 0x00
    return bytes([0x81, 0x01, 0x04, 0x07, byte, 0xFF])


def zoom_stop() -> bytes:
    return bytes([0x81, 0x01, 0x04, 0x07, 0x00, 0xFF])


def home() -> bytes:
    return bytes([0x81, 0x01, 0x06, 0x04, 0xFF])


class ViscaSender:
    """One shared non-blocking UDP socket; sendto per camera IP."""

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)

    def send(self, ip: str, command: bytes) -> None:
        try:
            self._sock.sendto(command, (ip, self.port))
        except OSError as exc:
            log.debug("VISCA send to %s failed: %s", ip, exc)

    def close(self) -> None:
        self._sock.close()
