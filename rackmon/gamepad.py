"""Xbox controllers -> PTZ cameras, read in the backend via XInput.

Why the backend and not a browser page: the web Gamepad API only delivers
input while its page has focus, so any window popping over the old
controller page silently ate inputs — including the stop at the end of a
move (the classic "camera kept going" bug). XInput is read directly from
the OS at ~30 Hz regardless of what is on screen.

Runaway protection, in order of defense:
  1. commands are stateful — a new command is only sent when the computed
     command changes;
  2. an active move is re-sent every keepalive_s (a lost UDP packet heals
     itself within half a second);
  3. stick back in the deadzone -> stop sent twice;
  4. controller disconnects mid-move -> stop sent immediately.

Mapping (per controller, fixed controller->camera assignment from config):
  left stick  = pan/tilt (speed proportional to deflection)
  RT / LT     = zoom in / out (speed proportional to pressure)
"""

from __future__ import annotations

import asyncio
import logging
import math
import sys
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from . import visca
from .config import CameraConfig, Config
from .state import ERROR, OK, StateStore, WARN

log = logging.getLogger("rackmon.gamepad")

PUBLISH_INTERVAL = 0.5  # state store updates (drives the on-screen bars)


def camera_control_ip(cam: CameraConfig) -> str | None:
    """VISCA target: explicit visca_ip, else the camera URL's host."""
    if cam.visca_ip:
        return cam.visca_ip
    for url in (cam.rtsp_url, cam.snapshot_url):
        if url:
            host = urlparse(url).hostname
            if host:
                return host
    return None


@dataclass(frozen=True)
class PtzCommand:
    """The computed intent for one tick; frozen so it's comparable."""
    move: bytes       # pan/tilt command (or stop)
    zoom: bytes       # zoom command (or stop)
    pan: float        # signed -1..1 after deadzone (for UI bars)
    tilt: float
    zoom_axis: float

    @property
    def moving(self) -> bool:
        return (self.pan, self.tilt, self.zoom_axis) != (0.0, 0.0, 0.0)


def _scaled(value: float, deadzone: float, max_speed: int) -> tuple[float, int]:
    """Deadzoned axis -> (signed 0..1 fraction, VISCA speed >= 1)."""
    mag = abs(value)
    if mag < deadzone:
        return 0.0, 1
    frac = (mag - deadzone) / (1 - deadzone)
    speed = 1 + round(frac * (max_speed - 1))
    return math.copysign(frac, value), speed


def compute_command(x: float, y: float, lt: float, rt: float,
                    cfg) -> PtzCommand:
    """Pure mapping from stick/trigger state to VISCA commands.

    x, y in -1..1 (stick, y positive = up), lt/rt in 0..1 (triggers).
    cfg needs: deadzone, invert_tilt, max_pan_speed, max_tilt_speed,
    max_zoom_speed.
    """
    if cfg.invert_tilt:
        y = -y
    pan_frac, pan_speed = _scaled(x, cfg.deadzone, cfg.max_pan_speed)
    tilt_frac, tilt_speed = _scaled(y, cfg.deadzone, cfg.max_tilt_speed)

    pan_dir = (visca.PAN_LEFT if pan_frac < 0
               else visca.PAN_RIGHT if pan_frac > 0 else visca.PAN_STOP)
    tilt_dir = (visca.TILT_UP if tilt_frac > 0
                else visca.TILT_DOWN if tilt_frac < 0 else visca.TILT_STOP)
    if pan_frac == 0 and tilt_frac == 0:
        move = visca.pan_tilt_stop()
    else:
        move = visca.pan_tilt(pan_dir, tilt_dir, pan_speed, tilt_speed)

    # triggers: whichever is pressed harder wins; both light = stop
    zoom_axis = rt - lt
    z_frac, z_speed = _scaled(zoom_axis, cfg.deadzone, cfg.max_zoom_speed)
    if z_frac > 0:
        zoom_cmd = visca.zoom("in", z_speed)
    elif z_frac < 0:
        zoom_cmd = visca.zoom("out", z_speed)
    else:
        zoom_cmd = visca.zoom_stop()

    return PtzCommand(move=move, zoom=zoom_cmd,
                      pan=round(pan_frac, 2), tilt=round(tilt_frac, 2),
                      zoom_axis=round(z_frac, 2))


class XInputReader:
    """Thin ctypes wrapper over Windows XInput (no dependencies)."""

    def __init__(self) -> None:
        import ctypes

        class Gamepad(ctypes.Structure):
            _fields_ = [("wButtons", ctypes.c_ushort),
                        ("bLeftTrigger", ctypes.c_ubyte),
                        ("bRightTrigger", ctypes.c_ubyte),
                        ("sThumbLX", ctypes.c_short),
                        ("sThumbLY", ctypes.c_short),
                        ("sThumbRX", ctypes.c_short),
                        ("sThumbRY", ctypes.c_short)]

        class State(ctypes.Structure):
            _fields_ = [("dwPacketNumber", ctypes.c_ulong),
                        ("Gamepad", Gamepad)]

        self._State = State
        self._dll = None
        for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                self._dll = ctypes.windll.LoadLibrary(name)
                break
            except OSError:
                continue
        if self._dll is None:
            raise RuntimeError("No XInput DLL found — is this Windows?")
        self._ctypes = ctypes

    def read(self, index: int) -> tuple[bool, float, float, float, float]:
        """(connected, x, y, lt, rt) — axes -1..1, triggers 0..1."""
        state = self._State()
        if self._dll.XInputGetState(index, self._ctypes.byref(state)) != 0:
            return False, 0.0, 0.0, 0.0, 0.0
        pad = state.Gamepad
        return (True,
                max(-1.0, pad.sThumbLX / 32767),
                max(-1.0, pad.sThumbLY / 32767),
                pad.bLeftTrigger / 255,
                pad.bRightTrigger / 255)


class GamepadControl:
    """The always-on controller loop; publishes a 'control' state section."""

    def __init__(self, config: Config, store: StateStore) -> None:
        self.config = config
        self.store = store
        self.cfg = config.control
        self.cameras = {c.id: c for c in config.cameras}
        self._last: dict[int, PtzCommand] = {}
        self._last_sent: dict[int, float] = {}
        self._ui: dict[str, dict] = {}

    def _publish(self, status: str = OK, message: str = "") -> None:
        self.store.update("control", {"cameras": self._ui, "enabled": True},
                          status=status, message=message,
                          interval=PUBLISH_INTERVAL * 4)

    async def run(self) -> None:
        if sys.platform != "win32":
            self._publish(WARN, "Controllers need Windows (XInput) — disabled here")
            return
        try:
            reader = XInputReader()
        except RuntimeError as exc:
            self._publish(ERROR, str(exc))
            return
        sender = visca.ViscaSender(self.cfg.visca_port)

        targets = []  # (controller_index, camera, ip)
        for m in self.cfg.controllers:
            cam = self.cameras.get(m.camera)
            ip = camera_control_ip(cam) if cam else None
            if cam and ip:
                targets.append((m.index, cam, ip))
            else:
                log.warning("controller %d: camera '%s' has no control IP",
                            m.index, m.camera)

        tick = 1.0 / max(self.cfg.poll_hz, 5)
        last_publish = 0.0
        try:
            while True:
                now = time.monotonic()
                dirty = False
                connected_count = 0
                for index, cam, ip in targets:
                    connected, x, y, lt, rt = reader.read(index)
                    if connected:
                        connected_count += 1
                        command = compute_command(x, y, lt, rt, self.cfg)
                    else:
                        command = compute_command(0, 0, 0, 0, self.cfg)

                    previous = self._last.get(index)
                    changed = command != previous
                    stale = now - self._last_sent.get(index, 0) > self.cfg.keepalive_s
                    if changed or (command.moving and stale):
                        sender.send(ip, command.move)
                        sender.send(ip, command.zoom)
                        if changed and previous is not None and previous.moving \
                                and not command.moving:
                            # belt & braces on the transition to stop
                            sender.send(ip, visca.pan_tilt_stop())
                            sender.send(ip, visca.zoom_stop())
                        self._last[index] = command
                        self._last_sent[index] = now
                        dirty = True

                    self._ui[cam.id] = {
                        "connected": connected,
                        "pan": command.pan, "tilt": command.tilt,
                        "zoom": command.zoom_axis, "moving": command.moving,
                        "controller": index + 1,
                    }

                if dirty or now - last_publish > PUBLISH_INTERVAL:
                    total = len(targets)
                    if connected_count == total and total:
                        self._publish(OK, f"{connected_count}/{total} controllers ready")
                    elif connected_count:
                        self._publish(WARN,
                                      f"Only {connected_count}/{total} controllers connected")
                    else:
                        self._publish(ERROR, "No controllers connected")
                    last_publish = now
                await asyncio.sleep(tick)
        finally:
            for _, _, ip in targets:  # never leave a camera moving
                sender.send(ip, visca.pan_tilt_stop())
                sender.send(ip, visca.zoom_stop())
            sender.close()


class MockGamepadControl:
    """Fake controller wiggles for mock mode / the Mac dev machine."""

    def __init__(self, config: Config, store: StateStore, scenario) -> None:
        self.config = config
        self.store = store
        self.scenario = scenario
        self.cams = [m.camera for m in config.control.controllers]

    async def run(self) -> None:
        start = time.monotonic()
        while True:
            t = time.monotonic() - start
            cameras = {}
            dead = self.scenario is not None and \
                self.scenario.flags.get("controller_unplugged")
            for i, cam_id in enumerate(self.cams):
                # each fake operator nudges their camera now and then
                phase = t * 0.7 + i * 2.1
                active = math.sin(phase * 0.35) > 0.55
                pan = round(math.sin(phase) * 0.8, 2) if active else 0.0
                tilt = round(math.cos(phase * 0.8) * 0.4, 2) if active else 0.0
                unplugged = dead and i == 1
                cameras[cam_id] = {
                    "connected": not unplugged,
                    "pan": 0.0 if unplugged else pan,
                    "tilt": 0.0 if unplugged else tilt,
                    "zoom": 0.0,
                    "moving": bool(active and not unplugged),
                    "controller": i + 1,
                }
            total = len(self.cams)
            ok_count = sum(1 for c in cameras.values() if c["connected"])
            status = OK if ok_count == total else WARN
            message = (f"{ok_count}/{total} controllers ready" if ok_count == total
                       else f"Only {ok_count}/{total} controllers connected")
            self.store.update("control", {"cameras": cameras, "enabled": True},
                              status=status, message=message, interval=2)
            await asyncio.sleep(0.5)
