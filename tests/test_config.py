from pathlib import Path

from rackmon.config import default_mock_config, load_config

EXAMPLE = Path(__file__).parent.parent / "config" / "config.example.yaml"


def test_example_config_is_valid():
    cfg, err = load_config(EXAMPLE)
    assert err is None, err
    assert cfg.atem.ip
    assert cfg.switch.ports
    assert any(c.mode == "obs" for c in cfg.cameras)
    assert not cfg.youtube.enabled  # nulls in the example


def test_missing_file():
    cfg, err = load_config(Path("/nonexistent/config.yaml"))
    assert cfg is None
    assert "not found" in err


def test_invalid_yaml(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("cameras: [unclosed", encoding="utf-8")
    cfg, err = load_config(p)
    assert cfg is None
    assert "not valid YAML" in err


def test_validation_error_is_friendly(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("atem:\n  poll_interval: banana\n", encoding="utf-8")
    cfg, err = load_config(p)
    assert cfg is None
    assert "atem.poll_interval" in err


def test_camera_mode_requirements(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "cameras:\n  - {id: c1, label: C1, mode: rtsp}\n", encoding="utf-8")
    cfg, err = load_config(p)
    assert cfg is None
    assert "rtsp_url" in err


def test_duplicate_camera_ids(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "cameras:\n"
        "  - {id: c1, label: A, mode: mock}\n"
        "  - {id: c1, label: B, mode: mock}\n", encoding="utf-8")
    cfg, err = load_config(p)
    assert cfg is None
    assert "duplicate" in err


def test_no_path_with_mock_gives_default():
    cfg, err = load_config(None, mock_override=True)
    assert err is None
    assert cfg.mock and cfg.cameras


def test_no_path_without_mock_errors():
    cfg, err = load_config(None)
    assert cfg is None and "No config file" in err


def test_mock_override_applies_to_real_config():
    cfg, err = load_config(EXAMPLE, mock_override=True)
    assert err is None and cfg.mock is True


def test_default_mock_config_complete():
    cfg = default_mock_config()
    assert cfg.mock
    assert len(cfg.cameras) == 6
    assert len([p for p in cfg.switch.ports if p.expect_poe]) == 4
