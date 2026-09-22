"""Unit tests for the built-in ATEM protocol parser (no hardware)."""

from rackmon.atemproto import (FLAG_ACK_REQUEST, AtemMonitor, build_header,
                               parse_header, split_commands)


def cmd(name: str, payload: bytes) -> bytes:
    size = 8 + len(payload)
    return size.to_bytes(2, "big") + b"\x00\x00" + name.encode() + payload


def test_header_roundtrip():
    raw = build_header(FLAG_ACK_REQUEST, 12, session=0x1234, packet_id=7)
    flags, length, session, packet_id = parse_header(raw)
    assert flags == FLAG_ACK_REQUEST
    assert length == 12
    assert session == 0x1234
    assert packet_id == 7


def test_split_commands():
    payload = cmd("PrgI", bytes([0, 0, 0, 2])) + cmd("PrvI", bytes([0, 0, 0, 3]))
    names = [n for n, _ in split_commands(payload)]
    assert names == ["PrgI", "PrvI"]


def test_split_stops_on_garbage():
    payload = cmd("PrgI", bytes([0, 0, 0, 2])) + b"\x00\x03junk"
    assert [n for n, _ in split_commands(payload)] == ["PrgI"]


def _mon() -> AtemMonitor:
    return AtemMonitor("192.0.2.1")


def test_parse_program_preview():
    m = _mon()
    m._handle("PrgI", bytes([0, 0, 0, 2]))
    m._handle("PrvI", bytes([0, 0, 0, 3]))
    assert m.program[0] == 2
    assert m.preview[0] == 3


def test_parse_tally_by_source():
    m = _mon()
    # 2 entries: source 1 flags=1 (program), source 2 flags=2 (preview)
    m._handle("TlSr", bytes([0, 2, 0, 1, 1, 0, 2, 2]))
    assert m.tally_by_source == {1: 1, 2: 2}


def test_parse_tally_by_index():
    m = _mon()
    m._handle("TlIn", bytes([0, 3, 1, 0, 2]))
    assert m.tally_by_index == {1: 1, 2: 0, 3: 2}


def test_parse_input_name():
    m = _mon()
    name = b"Stage Left" + b"\x00" * 10
    m._handle("InPr", bytes([0, 1]) + name + b"\x00" * 20)
    assert m.input_names[1] == "Stage Left"


def test_parse_model_and_status():
    m = _mon()
    m._handle("_pin", b"ATEM Mini Extreme ISO\x00\x00\x00")
    m._handle("StRS", bytes([0, 4]))
    m._handle("RecS", bytes([0, 1, 0, 0]))
    assert m.model == "ATEM Mini Extreme ISO"
    assert m.streaming is True
    assert m.recording is True
    m._handle("StRS", bytes([0, 1]))
    assert m.streaming is False


def test_unknown_command_ignored():
    m = _mon()
    m._handle("Zzzz", b"\x01\x02\x03")  # must not raise


def test_receive_acks_and_parses():
    m = _mon()
    sent = []

    class FakeTransport:
        def sendto(self, data):
            sent.append(data)

    m._transport = FakeTransport()
    payload = cmd("PrgI", bytes([0, 0, 0, 5]))
    packet = build_header(FLAG_ACK_REQUEST, 12 + len(payload),
                          session=0x8001, packet_id=42) + payload
    m._receive(packet)
    assert m.program[0] == 5
    assert m._handshaked
    flags, _, session, _ = parse_header(sent[0])
    assert flags == 0x10 and session == 0x8001  # ACK echoing the session
    assert sent[0][4:6] == (42).to_bytes(2, "big")  # acked packet id
