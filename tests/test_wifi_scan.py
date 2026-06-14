"""Tests for iwlist scan output parser."""
from __future__ import annotations

import pytest

SAMPLE_OUTPUT = """\
wlan0     Scan completed :
          Cell 01 - Address: AA:BB:CC:DD:EE:FF
                    Channel:6
                    Frequency:2.437 GHz (Channel 6)
                    Quality=70/70  Signal level=-40 dBm  Noise level=-95 dBm
                    Encryption key:on
                    ESSID:"HomeNetwork"
                    Extra: Last beacon: 10ms ago
          Cell 02 - Address: 11:22:33:44:55:66
                    Channel:11
                    Frequency:2.462 GHz (Channel 11)
                    Quality=30/70  Signal level=-78 dBm  Noise level=-95 dBm
                    Encryption key:off
                    ESSID:"CoffeeShop"
                    Extra: Last beacon: 20ms ago
"""

HIDDEN_OUTPUT = """\
wlan0     Scan completed :
          Cell 01 - Address: AA:BB:CC:DD:EE:FF
                    Quality=60/70  Signal level=-55 dBm
                    Encryption key:on
                    ESSID:""
          Cell 02 - Address: 11:22:33:44:55:66
                    Quality=40/70  Signal level=-65 dBm
                    Encryption key:off
                    ESSID:"\x00\x00\x00"
          Cell 03 - Address: 22:33:44:55:66:77
                    Quality=50/70  Signal level=-60 dBm
                    Encryption key:on
                    ESSID:"VisibleNet"
"""

DUPLICATE_OUTPUT = """\
wlan0     Scan completed :
          Cell 01 - Address: AA:BB:CC:DD:EE:01
                    Quality=30/70  Signal level=-78 dBm
                    Encryption key:on
                    ESSID:"MyNetwork"
          Cell 02 - Address: AA:BB:CC:DD:EE:02
                    Quality=65/70  Signal level=-45 dBm
                    Encryption key:on
                    ESSID:"MyNetwork"
          Cell 03 - Address: AA:BB:CC:DD:EE:03
                    Quality=20/70  Signal level=-85 dBm
                    Encryption key:off
                    ESSID:"OtherNet"
"""

NO_SIGNAL_OUTPUT = """\
wlan0     Scan completed :
          Cell 01 - Address: AA:BB:CC:DD:EE:FF
                    Channel:6
                    Encryption key:on
                    ESSID:"WeirdAP"
"""


def test_parse_sample_returns_two_networks():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(SAMPLE_OUTPUT)
    assert len(result) == 2


def test_parse_sample_home_network_first_strongest():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(SAMPLE_OUTPUT)
    assert result[0]["ssid"] == "HomeNetwork"
    assert result[1]["ssid"] == "CoffeeShop"


def test_parse_sample_signal_dbm_values():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(SAMPLE_OUTPUT)
    assert result[0]["signal_dbm"] == -40
    assert result[1]["signal_dbm"] == -78


def test_parse_sample_encrypted_flags():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(SAMPLE_OUTPUT)
    assert result[0]["encrypted"] is True
    assert result[1]["encrypted"] is False


def test_empty_input_returns_empty_list():
    from sunset_cam.wifi_scan import parse_iwlist
    assert parse_iwlist("") == []


def test_blank_essid_dropped():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(HIDDEN_OUTPUT)
    ssids = [n["ssid"] for n in result]
    assert "VisibleNet" in ssids
    assert "" not in ssids


def test_null_byte_essid_dropped():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(HIDDEN_OUTPUT)
    ssids = [n["ssid"] for n in result]
    assert all("\x00" not in s for s in ssids)


def test_hidden_essids_dropped_visible_kept():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(HIDDEN_OUTPUT)
    assert len(result) == 1
    assert result[0]["ssid"] == "VisibleNet"


def test_duplicate_ssid_keeps_strongest():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(DUPLICATE_OUTPUT)
    my_nets = [n for n in result if n["ssid"] == "MyNetwork"]
    assert len(my_nets) == 1
    assert my_nets[0]["signal_dbm"] == -45  # the stronger one


def test_duplicate_ssid_dedup_total_count():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(DUPLICATE_OUTPUT)
    assert len(result) == 2


def test_sorted_by_signal_descending():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(DUPLICATE_OUTPUT)
    signals = [n["signal_dbm"] for n in result if n["signal_dbm"] is not None]
    assert signals == sorted(signals, reverse=True)


def test_no_signal_line_yields_none():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(NO_SIGNAL_OUTPUT)
    assert len(result) == 1
    assert result[0]["ssid"] == "WeirdAP"
    assert result[0]["signal_dbm"] is None


def test_result_keys_are_correct():
    from sunset_cam.wifi_scan import parse_iwlist
    result = parse_iwlist(SAMPLE_OUTPUT)
    for net in result:
        assert set(net.keys()) == {"ssid", "signal_dbm", "encrypted"}
