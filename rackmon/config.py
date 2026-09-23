"""Configuration loading and validation.

All device IPs, credentials and screen layout live in one YAML file.
Validation failures never crash the server: load_config returns
(config, error_message) so the web app can display the problem on the
kiosk screens instead of showing a blank page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080


class AtemConfig(BaseModel):
    ip: Optional[str] = None
    poll_interval: float = 2.0


class ObsConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 4455
    password: str = ""
    poll_interval: float = 2.0


class SwitchPort(BaseModel):
    port: int
    label: str
    expect_poe: bool = True
    # SNMP interface index for this port. On most small switches the
    # ifIndex equals the port number, so this defaults to `port`.
    if_index: Optional[int] = None


class SwitchConfig(BaseModel):
    ip: Optional[str] = None
    snmp_community: str = "public"
    poll_interval: float = 5.0
    # Vendor-specific per-port power OID with a {port} placeholder,
    # e.g. "1.3.6.1.4.1.4526.11.15.1.12.1.1.9.{port}". Leave null to
    # fall back to the standard PoE detection status (on/off only).
    poe_power_oid_template: Optional[str] = None
    poe_power_scale: float = 0.001  # multiply raw value by this to get watts
    poe_min_watts: float = 2.0  # below this a camera counts as "not powered"
    poe_group_index: int = 1  # first index of pethPsePortTable (almost always 1)
    ports: list[SwitchPort] = Field(default_factory=list)


class PingTarget(BaseModel):
    label: str
    ip: str


class SystemConfig(BaseModel):
    disks: list[str] = Field(default_factory=lambda: ["/"])
    disk_warn_pct: float = 80.0
    disk_error_pct: float = 95.0
    cpu_warn_pct: float = 85.0
    poll_interval: float = 3.0


class CameraConfig(BaseModel):
    id: str
    label: str
    mode: Literal["snapshot", "rtsp", "obs", "mock"] = "mock"
    rtsp_url: Optional[str] = None
    snapshot_url: Optional[str] = None
    obs_source: Optional[str] = None
    atem_input: Optional[int] = None  # ATEM input number for the tally border
    fps: float = 4.0
    # VISCA control address; defaults to the rtsp/snapshot URL's host
    visca_ip: Optional[str] = None

    @model_validator(mode="after")
    def _check_mode_requirements(self) -> "CameraConfig":
        if self.mode == "rtsp" and not self.rtsp_url:
            raise ValueError(f"camera '{self.id}': mode 'rtsp' requires rtsp_url")
        if self.mode == "snapshot" and not self.snapshot_url:
            raise ValueError(f"camera '{self.id}': mode 'snapshot' requires snapshot_url")
        if self.mode == "obs" and not self.obs_source:
            raise ValueError(f"camera '{self.id}': mode 'obs' requires obs_source")
        return self


class ControllerMap(BaseModel):
    index: int  # XInput slot 0-3 (order controllers were plugged in)
    camera: str  # camera id from the cameras: list


class ControlConfig(BaseModel):
    """Xbox controllers -> PTZ cameras (VISCA-over-IP), read via XInput."""
    enabled: bool = False
    visca_port: int = 1259
    poll_hz: float = 30.0
    deadzone: float = 0.25
    invert_tilt: bool = False
    max_pan_speed: int = 18   # full stick = this VISCA speed (1-24)
    max_tilt_speed: int = 14  # (1-20)
    max_zoom_speed: int = 5   # (1-7)
    keepalive_s: float = 0.4  # re-send an active move this often
    controllers: list[ControllerMap] = Field(default_factory=list)


class VideoConfig(BaseModel):
    ffmpeg_path: str = "ffmpeg"
    jpeg_width: int = 480
    stale_after: float = 10.0  # seconds before a tile shows NO SIGNAL


class YoutubeConfig(BaseModel):
    api_key: Optional[str] = None
    channel_id: Optional[str] = None
    poll_interval: float = 90.0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.channel_id)


class Config(BaseModel):
    mock: bool = False
    server: ServerConfig = Field(default_factory=ServerConfig)
    atem: AtemConfig = Field(default_factory=AtemConfig)
    obs: ObsConfig = Field(default_factory=ObsConfig)
    switch: SwitchConfig = Field(default_factory=SwitchConfig)
    ping_targets: list[PingTarget] = Field(default_factory=list)
    ping_interval: float = 5.0
    system: SystemConfig = Field(default_factory=SystemConfig)
    cameras: list[CameraConfig] = Field(default_factory=list)
    video: VideoConfig = Field(default_factory=VideoConfig)
    control: ControlConfig = Field(default_factory=ControlConfig)
    youtube: YoutubeConfig = Field(default_factory=YoutubeConfig)
    checklist_file: str = "config/checklist.yaml"

    @model_validator(mode="after")
    def _check_unique_camera_ids(self) -> "Config":
        ids = [c.id for c in self.cameras]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate camera ids: {', '.join(sorted(dupes))}")
        return self

    @model_validator(mode="after")
    def _check_controller_mappings(self) -> "Config":
        if not self.control.enabled:
            return self
        ids = {c.id for c in self.cameras}
        for m in self.control.controllers:
            if m.camera not in ids:
                raise ValueError(
                    f"control.controllers: camera '{m.camera}' is not in the "
                    f"cameras list ({', '.join(sorted(ids)) or 'empty'})")
        return self


def friendly_validation_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(top level)"
        lines.append(f"{loc}: {err['msg']}")
    return "Config file has problems:\n" + "\n".join(f"  - {ln}" for ln in lines)


def default_mock_config() -> Config:
    """A complete fake rack used by `--mock` when no config file exists."""
    return Config(
        mock=True,
        atem=AtemConfig(ip="192.168.1.240"),
        switch=SwitchConfig(
            ip="192.168.1.2",
            ports=[
                SwitchPort(port=1, label="Cam 1 (Stage Left)"),
                SwitchPort(port=2, label="Cam 2 (Center)"),
                SwitchPort(port=3, label="Cam 3 (Stage Right)"),
                SwitchPort(port=4, label="Cam 4 (Rear)"),
                SwitchPort(port=5, label="Uplink to router", expect_poe=False),
                SwitchPort(port=6, label="WiFi extender", expect_poe=False),
            ],
        ),
        ping_targets=[
            PingTarget(label="WiFi Extender", ip="192.168.1.3"),
            PingTarget(label="Building Router", ip="192.168.1.1"),
            PingTarget(label="Internet", ip="8.8.8.8"),
        ],
        cameras=[
            CameraConfig(id="cam1", label="Cam 1", mode="mock", atem_input=1),
            CameraConfig(id="cam2", label="Cam 2", mode="mock", atem_input=2),
            CameraConfig(id="cam3", label="Cam 3", mode="mock", atem_input=3),
            CameraConfig(id="cam4", label="Cam 4", mode="mock", atem_input=4),
            CameraConfig(id="pgm", label="PROGRAM", mode="mock"),
            CameraConfig(id="pvw", label="PREVIEW", mode="mock"),
        ],
        control=ControlConfig(enabled=True, controllers=[
            ControllerMap(index=0, camera="cam1"),
            ControllerMap(index=1, camera="cam2"),
            ControllerMap(index=2, camera="cam3"),
        ]),
    )


def load_config(
    path: Path | None, mock_override: bool | None = None
) -> tuple[Config | None, str | None]:
    """Returns (config, None) on success or (None, human_readable_error)."""
    if path is None:
        if mock_override:
            return default_mock_config(), None
        return None, (
            "No config file found. Copy config/config.example.yaml to "
            "config/config.yaml and fill it in, or run with --mock for a demo."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"Config file not found: {path}"
    except yaml.YAMLError as exc:
        return None, f"Config file is not valid YAML ({path}):\n{exc}"
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return None, f"Config file must be a YAML mapping, got {type(raw).__name__}"
    try:
        cfg = Config.model_validate(raw)
    except ValidationError as exc:
        return None, friendly_validation_error(exc)
    if mock_override is not None:
        cfg.mock = mock_override
    return cfg, None
