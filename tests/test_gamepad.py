"""Unit tests for VISCA byte building and the controller->command mapping."""

import pytest

from rackmon import visca
from rackmon.config import (CameraConfig, Config, ControlConfig, ControllerMap,
                            default_mock_config)
from rackmon.gamepad import camera_control_ip, compute_command

CFG = ControlConfig()  # defaults: deadzone .25, max 18/14/5


# ---- visca bytes (must match the proven Node implementation) ----

def test_pan_tilt_bytes():
    assert visca.pan_tilt(visca.PAN_LEFT, visca.TILT_STOP, 12, 1) == \
        bytes([0x81, 0x01, 0x06, 0x01, 12, 1, 0x01, 0x03, 0xFF])


def test_pan_tilt_speed_clamped():
    cmd = visca.pan_tilt(visca.PAN_RIGHT, visca.TILT_UP, 99, 0)
    assert cmd[4] == 24 and cmd[5] == 1


def test_stop_bytes():
    assert visca.pan_tilt_stop() == \
        bytes([0x81, 0x01, 0x06, 0x01, 0x01, 0x01, 0x03, 0x03, 0xFF])


def test_zoom_bytes():
    assert visca.zoom("in", 3) == bytes([0x81, 0x01, 0x04, 0x07, 0x23, 0xFF])
    assert visca.zoom("out", 7) == bytes([0x81, 0x01, 0x04, 0x07, 0x37, 0xFF])
    assert visca.zoom_stop() == bytes([0x81, 0x01, 0x04, 0x07, 0x00, 0xFF])


# ---- stick mapping ----

def test_centered_stick_is_stop():
    cmd = compute_command(0, 0, 0, 0, CFG)
    assert cmd.move == visca.pan_tilt_stop()
    assert cmd.zoom == visca.zoom_stop()
    assert not cmd.moving


def test_deadzone_ignored():
    cmd = compute_command(0.2, -0.2, 0.1, 0.0, CFG)
    assert not cmd.moving


def test_full_right_pan():
    cmd = compute_command(1.0, 0, 0, 0, CFG)
    assert cmd.moving and cmd.pan == 1.0 and cmd.tilt == 0
    # 81 01 06 01 ps ts pan_dir tilt_dir FF
    assert cmd.move[6] == visca.PAN_RIGHT
    assert cmd.move[7] == visca.TILT_STOP
    assert cmd.move[4] == CFG.max_pan_speed


def test_diagonal():
    cmd = compute_command(-1.0, 1.0, 0, 0, CFG)
    assert cmd.move[6] == visca.PAN_LEFT and cmd.move[7] == visca.TILT_UP


def test_half_stick_is_slower_than_full():
    half = compute_command(0.6, 0, 0, 0, CFG)
    full = compute_command(1.0, 0, 0, 0, CFG)
    assert 1 <= half.move[4] < full.move[4]


def test_invert_tilt():
    cfg = ControlConfig(invert_tilt=True)
    cmd = compute_command(0, 1.0, 0, 0, cfg)
    assert cmd.move[7] == visca.TILT_DOWN


def test_triggers_zoom():
    cmd = compute_command(0, 0, 0, 1.0, CFG)   # RT = zoom in
    assert cmd.zoom[4] & 0xF0 == 0x20
    cmd = compute_command(0, 0, 1.0, 0, CFG)   # LT = zoom out
    assert cmd.zoom[4] & 0xF0 == 0x30
    cmd = compute_command(0, 0, 0.8, 0.8, CFG)  # both -> cancel
    assert cmd.zoom == visca.zoom_stop()


def test_commands_comparable_for_dedupe():
    a = compute_command(0.5, 0, 0, 0, CFG)
    b = compute_command(0.5, 0, 0, 0, CFG)
    c = compute_command(0.9, 0, 0, 0, CFG)
    assert a == b and a != c


# ---- config plumbing ----

def test_camera_control_ip_from_rtsp():
    cam = CameraConfig(id="c", label="C", mode="rtsp",
                       rtsp_url="rtsp://admin:pw@192.168.100.87:554/2")
    assert camera_control_ip(cam) == "192.168.100.87"


def test_camera_control_ip_override():
    cam = CameraConfig(id="c", label="C", mode="mock", visca_ip="10.0.0.9")
    assert camera_control_ip(cam) == "10.0.0.9"


def test_controller_mapping_validated():
    with pytest.raises(ValueError, match="not in the cameras list"):
        Config(
            cameras=[CameraConfig(id="cam1", label="C1", mode="mock")],
            control=ControlConfig(enabled=True, controllers=[
                ControllerMap(index=0, camera="nope")]),
        )


def test_mock_config_has_controllers():
    cfg = default_mock_config()
    assert cfg.control.enabled and len(cfg.control.controllers) == 3
