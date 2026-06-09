from sunset_cam.heartbeat import parse_placement, post_heartbeat

def test_parse_placement_pulls_status_and_coords():
    out = parse_placement({"placement_status": "awaiting_aim", "lat": 48.7, "lng": -122.4, "x": 1})
    assert out == {"placement_status": "awaiting_aim", "lat": 48.7, "lng": -122.4}

def test_parse_placement_defaults_missing_to_none():
    out = parse_placement({"acknowledged_at": "t"})
    assert out == {"placement_status": None, "lat": None, "lng": None}

def test_post_heartbeat_posts_with_auth_and_parses():
    calls = {}
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"placement_status": "ready", "lat": 1.0, "lng": 2.0}
    def fake_poster(url, json, headers, timeout):
        calls["url"] = url; calls["json"] = json; calls["headers"] = headers
        return FakeResp()
    cfg = {"api_base": "https://www.sunrisesunset.studio", "camera_id": 4, "device_token": "tok"}
    out = post_heartbeat(cfg, poster=fake_poster)
    assert calls["url"] == "https://www.sunrisesunset.studio/api/cameras/4/heartbeat"
    assert calls["json"] == {"request_placement": True}
    assert calls["headers"]["Authorization"] == "Bearer tok"
    assert out == {"placement_status": "ready", "lat": 1.0, "lng": 2.0}
