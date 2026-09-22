from rackmon.config import SwitchConfig, SwitchPort
from rackmon.pollers.snmp_switch import build_port_oids, interpret_port


def _cfg(**kw):
    return SwitchConfig(ip="192.168.1.2", **kw)


def test_oid_template_substitution():
    cfg = _cfg(poe_power_oid_template="1.3.6.1.4.1.9999.1.{port}")
    port = SwitchPort(port=3, label="Cam")
    oids = build_port_oids(cfg, port)
    assert oids["power"] == "1.3.6.1.4.1.9999.1.3"
    assert oids["link"] == "1.3.6.1.2.1.2.2.1.8.3"
    assert oids["poe_detect"] == "1.3.6.1.2.1.105.1.1.1.6.1.3"


def test_if_index_override():
    cfg = _cfg()
    port = SwitchPort(port=3, label="Cam", if_index=10103)
    oids = build_port_oids(cfg, port)
    assert oids["link"].endswith(".10103")
    assert oids["poe_detect"].endswith(".1.3")  # poe table still keyed by port


def test_no_power_template_omits_power_oid():
    oids = build_port_oids(_cfg(), SwitchPort(port=1, label="x"))
    assert "power" not in oids


def test_interpret_power_scale_and_ok():
    cfg = _cfg(poe_power_oid_template="x.{port}", poe_power_scale=0.001,
               poe_min_watts=2.0)
    port = SwitchPort(port=1, label="Cam 1")
    res = interpret_port({"link": 1, "poe_detect": 3, "power": 6400}, cfg, port)
    assert res["watts"] == 6.4
    assert res["power_ok"] is True and res["ok"] is True
    assert "6.4 W" in res["detail"]


def test_interpret_underpowered_camera():
    cfg = _cfg(poe_power_oid_template="x.{port}")
    port = SwitchPort(port=1, label="Cam 1")
    res = interpret_port({"link": 1, "poe_detect": 3, "power": 500}, cfg, port)
    assert res["power_ok"] is False and res["ok"] is False
    assert "not powered" in res["detail"]


def test_fallback_to_detection_status():
    cfg = _cfg()  # no power template
    port = SwitchPort(port=1, label="Cam 1")
    res = interpret_port({"link": 1, "poe_detect": 3, "power": None}, cfg, port)
    assert res["watts"] is None and res["power_ok"] is True and res["ok"] is True
    res = interpret_port({"link": 1, "poe_detect": 2, "power": None}, cfg, port)
    assert res["power_ok"] is False and res["ok"] is False


def test_fallback_to_link_only():
    cfg = _cfg()
    port = SwitchPort(port=1, label="Cam 1")
    res = interpret_port({"link": 1, "poe_detect": None, "power": None}, cfg, port)
    assert res["ok"] is True and "PoE status unavailable" in res["detail"]
    res = interpret_port({"link": 2, "poe_detect": None, "power": None}, cfg, port)
    assert res["ok"] is False and res["detail"] == "no link"


def test_non_poe_port_only_checks_link():
    cfg = _cfg()
    port = SwitchPort(port=5, label="Uplink", expect_poe=False)
    assert interpret_port({"link": 1}, cfg, port)["ok"] is True
    assert interpret_port({"link": 2}, cfg, port)["ok"] is False
