import json
from sunset_cam.device_config import write_identity, write_location

def test_write_location_merges_into_existing_config(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"camera_id": 4, "device_token": "t"}))
    write_location(str(p), 48.7519, -122.4787)
    cfg = json.loads(p.read_text())
    assert cfg["lat"] == 48.7519 and cfg["lng"] == -122.4787
    assert cfg["camera_id"] == 4 and cfg["device_token"] == "t"

def test_write_location_creates_when_absent(tmp_path):
    p = tmp_path / "config.json"
    write_location(str(p), 1.0, 2.0)
    assert json.loads(p.read_text()) == {"lat": 1.0, "lng": 2.0}


# ---------------------------------------------------------------------------
# write_identity tests
# ---------------------------------------------------------------------------

def test_write_identity_writes_four_fields(tmp_path):
    p = tmp_path / "config.json"
    write_identity(
        str(p),
        claim_code="SUNSET-AAAA-BBBB",
        camera_id=1,
        device_token="tok-abc",
        api_base="https://api.example.com",
        hardware_id="hw-test",
    )
    cfg = json.loads(p.read_text())
    assert cfg["claim_code"] == "SUNSET-AAAA-BBBB"
    assert cfg["camera_id"] == 1
    assert cfg["device_token"] == "tok-abc"
    assert cfg["api_base"] == "https://api.example.com"
    assert cfg["hardware_id"] == "hw-test"


def test_write_identity_preserves_existing_keys(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"lat": 48.7519, "lng": -122.4787, "extra": "keep"}))
    write_identity(
        str(p),
        claim_code="SUNSET-CCCC-DDDD",
        camera_id=2,
        device_token="tok-xyz",
        api_base="https://api.example.com",
        hardware_id="hw-test",
    )
    cfg = json.loads(p.read_text())
    # Identity fields written
    assert cfg["claim_code"] == "SUNSET-CCCC-DDDD"
    assert cfg["camera_id"] == 2
    assert cfg["device_token"] == "tok-xyz"
    assert cfg["api_base"] == "https://api.example.com"
    # Pre-existing fields preserved
    assert cfg["lat"] == 48.7519
    assert cfg["lng"] == -122.4787
    assert cfg["extra"] == "keep"


def test_write_identity_creates_file_when_absent(tmp_path):
    p = tmp_path / "new_config.json"
    assert not p.exists()
    write_identity(
        str(p),
        claim_code="SUNSET-EEEE-FFFF",
        camera_id=3,
        device_token="tok-new",
        api_base="https://api.example.com",
        hardware_id="hw-test",
    )
    assert p.exists()
    cfg = json.loads(p.read_text())
    assert cfg["camera_id"] == 3
