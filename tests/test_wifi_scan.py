"""Tests for the nmcli-based WiFi scanner."""
from sunset_cam.wifi_scan import parse_nmcli_wifi, scan_networks

# Terse `nmcli -t -f SSID,SIGNAL,SECURITY device wifi list` output. Real sample
# (one line) confirmed on hardware: `Antifa Headquarters:58:WPA1 WPA2`.
SAMPLE = "\n".join([
    "HomeNet:82:WPA2",
    "CoffeeShop:30:",          # open network (empty security)
    "Neighbor:55:WPA1 WPA2",   # security flags contain a space
    "",                         # blank line
    ":40:WPA2",                # hidden / blank SSID -> dropped
    "HomeNet:60:WPA2",         # duplicate, weaker -> de-duped
])


def test_parses_and_sorts_strongest_first():
    nets = parse_nmcli_wifi(SAMPLE)
    ssids = [n["ssid"] for n in nets]
    assert ssids == ["HomeNet", "Neighbor", "CoffeeShop"]  # 82, 55, 30; blank dropped


def test_signal_is_int_percentage():
    nets = parse_nmcli_wifi(SAMPLE)
    assert nets[0] == {"ssid": "HomeNet", "signal": 82, "encrypted": True}


def test_open_network_is_unencrypted():
    nets = parse_nmcli_wifi(SAMPLE)
    coffee = next(n for n in nets if n["ssid"] == "CoffeeShop")
    assert coffee["encrypted"] is False


def test_dedups_keeping_strongest():
    nets = parse_nmcli_wifi(SAMPLE)
    home = [n for n in nets if n["ssid"] == "HomeNet"]
    assert len(home) == 1 and home[0]["signal"] == 82


def test_blank_and_hidden_dropped():
    assert parse_nmcli_wifi("") == []
    assert parse_nmcli_wifi(":50:WPA2\n  \n") == []


def test_ssid_with_escaped_colon_is_unescaped():
    nets = parse_nmcli_wifi("My\\:Net:70:WPA2")
    assert nets[0]["ssid"] == "My:Net"


def test_security_with_space_is_encrypted():
    nets = parse_nmcli_wifi("Neighbor:55:WPA1 WPA2")
    assert nets[0]["encrypted"] is True


def test_scan_networks_invokes_nmcli_and_parses():
    calls = []
    def fake_runner(args):
        calls.append(args)
        return "HomeNet:82:WPA2"
    nets = scan_networks(runner=fake_runner)
    assert calls[0] == ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"]
    assert nets == [{"ssid": "HomeNet", "signal": 82, "encrypted": True}]


def test_scan_networks_returns_empty_on_runner_error():
    def boom(args):
        raise RuntimeError("nmcli not found")
    assert scan_networks(runner=boom) == []
