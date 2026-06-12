from sunset_cam.placement_report import post_placement

def test_post_placement_posts_azimuth_tilt_with_auth():
    calls = {}
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"placement_status": "ready"}
    def fake_poster(url, json, headers, timeout):
        calls["url"] = url; calls["json"] = json; calls["headers"] = headers
        return FakeResp()
    cfg = {"api_base": "https://www.sunrisesunset.studio", "camera_id": 4, "device_token": "tok"}
    placement = {"azimuth_deg": 268.0, "tilt_deg": 1.4, "roll_deg": 0.2, "confirmed_at": "t"}
    out = post_placement(cfg, placement, poster=fake_poster)
    assert calls["url"] == "https://www.sunrisesunset.studio/api/cameras/4/placement"
    assert calls["json"] == {"azimuth_deg": 268.0, "tilt_deg": 1.4}
    assert calls["headers"]["Authorization"] == "Bearer tok"
    assert out == {"placement_status": "ready"}
