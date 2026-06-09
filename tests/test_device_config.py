import json
from sunset_cam.device_config import write_location

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
