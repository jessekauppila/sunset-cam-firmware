from sunset_cam.heartbeat import parse_placement, parse_directives, post_heartbeat


def test_parse_directives_returns_the_pending_list():
    out = parse_directives({"directives": [{"id": "d1", "type": "ship-logs"}]})
    assert out == [{"id": "d1", "type": "ship-logs"}]

def test_parse_directives_defaults_to_empty_when_absent():
    assert parse_directives({"placement_status": "ready"}) == []
    assert parse_directives({"directives": None}) == []

def test_parse_placement_pulls_status_and_coords():
    out = parse_placement({"placement_status": "awaiting_aim", "lat": 48.7, "lng": -122.4, "x": 1})
    assert out == {"placement_status": "awaiting_aim", "lat": 48.7, "lng": -122.4}

def test_parse_placement_defaults_missing_to_none():
    out = parse_placement({"acknowledged_at": "t"})
    assert out == {"placement_status": None, "lat": None, "lng": None}

def test_parse_placement_coerces_string_coords_to_float():
    # the cloud serializes lat/lng as JSON strings; coerce at ingress so config.json
    # stores real numbers (the aiming server does math.radians on them).
    out = parse_placement({"placement_status": "awaiting_aim", "lat": "48.7", "lng": "-122.4"})
    assert out["lat"] == 48.7 and isinstance(out["lat"], float)
    assert out["lng"] == -122.4 and isinstance(out["lng"], float)
    assert out["placement_status"] == "awaiting_aim"

def test_post_heartbeat_includes_directive_results_when_provided():
    sent = {}
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {}
    def poster(url, json, headers, timeout):
        sent["json"] = json
        return FakeResp()
    cfg = {"api_base": "https://x", "camera_id": 4, "device_token": "t"}
    post_heartbeat(cfg, poster=poster, results=[{"id": "d1", "status": "done"}])
    assert sent["json"]["directive_results"] == [{"id": "d1", "status": "done"}]
    assert sent["json"]["request_placement"] is True


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
    assert out == {"placement_status": "ready", "lat": 1.0, "lng": 2.0, "directives": []}


def test_post_heartbeat_surfaces_directives_from_the_response():
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"placement_status": "ready",
                                "directives": [{"id": "d1", "type": "ship-logs"}]}
    out = post_heartbeat(
        {"api_base": "https://x", "camera_id": 4, "device_token": "t"},
        poster=lambda url, json, headers, timeout: FakeResp(),
    )
    assert out["placement_status"] == "ready"
    assert out["directives"] == [{"id": "d1", "type": "ship-logs"}]
