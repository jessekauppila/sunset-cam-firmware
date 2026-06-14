from sunset_cam.heartbeat import parse_placement, parse_directives, post_heartbeat


def test_parse_directives_returns_the_pending_list():
    out = parse_directives({"directives": [{"id": "d1", "type": "ship-logs"}]})
    assert out == [{"id": "d1", "type": "ship-logs"}]

def test_parse_directives_defaults_to_empty_when_absent():
    assert parse_directives({"placement_status": "ready"}) == []
    assert parse_directives({"directives": None}) == []

def test_parse_placement_pulls_status_and_coords():
    out = parse_placement({"placement_status": "awaiting_aim", "lat": 48.7, "lng": -122.4, "x": 1})
    # awaiting_aim shape: top-level lat/lng; no nested placement block
    assert out["placement_status"] == "awaiting_aim"
    assert out["lat"] == 48.7
    assert out["lng"] == -122.4
    assert out["azimuth_deg"] is None
    assert out["tilt_deg"] is None
    assert out["coarse"] is None
    assert out["azimuth_source"] is None
    assert out["bracket"] is None
    assert out["phase_preference"] is None

def test_parse_placement_defaults_missing_to_none():
    out = parse_placement({"acknowledged_at": "t"})
    assert out["placement_status"] is None
    assert out["lat"] is None
    assert out["lng"] is None
    assert out["azimuth_deg"] is None
    assert out["tilt_deg"] is None
    assert out["coarse"] is None
    assert out["azimuth_source"] is None
    assert out["bracket"] is None
    assert out["phase_preference"] is None

def test_parse_placement_reads_nested_ready_shape():
    bracket = {"wedge_deg": 5.0, "window_normal_az": 265.0}
    body = {
        "placement_status": "ready",
        "placement": {
            "lat": 48.7,
            "lng": -122.4,
            "elevation_m": 10,
            "timezone": "America/Los_Angeles",
            "azimuth_deg": 270,
            "tilt_deg": 0,
            "horizon_altitude_deg": 2.0,
            "horizon_profile": [],
            "phase_preference": "sunset",
            "delivery_preferences": {},
            "azimuth_source": "bracket",
            "coarse": True,
            "bracket": bracket,
        },
    }
    out = parse_placement(body)
    assert out["placement_status"] == "ready"
    assert out["lat"] == 48.7
    assert out["lng"] == -122.4
    assert out["azimuth_deg"] == 270
    assert out["tilt_deg"] == 0
    assert out["coarse"] is True
    assert out["azimuth_source"] == "bracket"
    assert out["bracket"] == bracket
    assert out["phase_preference"] == "sunset"

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
    assert out["placement_status"] == "ready"
    assert out["lat"] == 1.0
    assert out["lng"] == 2.0
    assert out["directives"] == []
    assert out["azimuth_deg"] is None
    assert out["coarse"] is None


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


def test_parse_directives_normalizes_bare_string_to_dict():
    """Cloud can emit bare strings like ["wipe_wifi"]; normalize to {id, type}."""
    out = parse_directives({"directives": ["wipe_wifi"]})
    assert out == [{"id": None, "type": "wipe_wifi"}]


def test_parse_directives_normalizes_mixed_list():
    """A list with both bare strings and dicts: strings normalized, dicts pass through."""
    out = parse_directives({
        "directives": [
            "wipe_wifi",
            {"id": "d1", "type": "ship-logs"},
        ]
    })
    assert out == [
        {"id": None, "type": "wipe_wifi"},
        {"id": "d1", "type": "ship-logs"},
    ]
