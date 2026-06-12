from sunset_cam.service_control import SystemctlController, AIMING_UNIT, CAPTURE_UNIT

def _controller():
    calls = []
    c = SystemctlController(runner=lambda args: calls.append(args))
    return c, calls

def test_aiming_mode_stops_capture_starts_aiming():
    c, calls = _controller()
    c.set_mode("aiming")
    assert ["stop", CAPTURE_UNIT] in calls
    assert ["start", AIMING_UNIT] in calls

def test_capture_mode_stops_aiming_starts_capture():
    c, calls = _controller()
    c.set_mode("capture")
    assert ["stop", AIMING_UNIT] in calls
    assert ["start", CAPTURE_UNIT] in calls

def test_idle_mode_stops_both():
    c, calls = _controller()
    c.set_mode("idle")
    assert ["stop", AIMING_UNIT] in calls
    assert ["stop", CAPTURE_UNIT] in calls
    assert not any(a[0] == "start" for a in calls)
