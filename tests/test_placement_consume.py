from sunset_cam.placement_consume import decide_placement, PlacementDecision


# ---------------------------------------------------------------------------
# AWAIT — any non-ready status
# ---------------------------------------------------------------------------

def test_decide_awaiting_location_gives_await():
    parsed = {
        "placement_status": "awaiting_location",
        "lat": None, "lng": None,
        "azimuth_deg": None, "tilt_deg": None,
        "coarse": None, "azimuth_source": None,
        "bracket": None, "phase_preference": None,
    }
    result = decide_placement(parsed)
    assert isinstance(result, PlacementDecision)
    assert result.verb == "AWAIT"
    assert result.placement is parsed


def test_decide_awaiting_aim_gives_await():
    parsed = {
        "placement_status": "awaiting_aim",
        "lat": 48.7, "lng": -122.4,
        "azimuth_deg": None, "tilt_deg": None,
        "coarse": None, "azimuth_source": None,
        "bracket": None, "phase_preference": None,
    }
    result = decide_placement(parsed)
    assert result.verb == "AWAIT"
    assert result.placement is parsed


def test_decide_none_status_gives_await():
    parsed = {"placement_status": None}
    result = decide_placement(parsed)
    assert result.verb == "AWAIT"


# ---------------------------------------------------------------------------
# SUN_SELF_REFINE — ready + coarse is True
# ---------------------------------------------------------------------------

def test_decide_ready_coarse_true_gives_sun_self_refine():
    parsed = {
        "placement_status": "ready",
        "lat": 48.7, "lng": -122.4,
        "azimuth_deg": 270,
        "tilt_deg": 0,
        "coarse": True,
        "azimuth_source": "bracket",
        "bracket": {"wedge_deg": 5.0},
        "phase_preference": "sunset",
    }
    result = decide_placement(parsed)
    assert result.verb == "SUN_SELF_REFINE"
    assert result.placement is parsed


# ---------------------------------------------------------------------------
# LEGACY_PRECISE — ready + coarse is not True (False or None or absent)
# ---------------------------------------------------------------------------

def test_decide_ready_coarse_false_gives_legacy_precise():
    parsed = {
        "placement_status": "ready",
        "lat": 48.7, "lng": -122.4,
        "azimuth_deg": 270,
        "tilt_deg": 0,
        "coarse": False,
        "azimuth_source": "sun",
        "bracket": None,
        "phase_preference": "sunset",
    }
    result = decide_placement(parsed)
    assert result.verb == "LEGACY_PRECISE"
    assert result.placement is parsed


def test_decide_ready_coarse_none_gives_legacy_precise():
    parsed = {
        "placement_status": "ready",
        "lat": 48.7, "lng": -122.4,
        "azimuth_deg": 270,
        "tilt_deg": 0,
        "coarse": None,
        "azimuth_source": "sun",
        "bracket": None,
        "phase_preference": "sunset",
    }
    result = decide_placement(parsed)
    assert result.verb == "LEGACY_PRECISE"


def test_decide_ready_coarse_absent_gives_legacy_precise():
    # coarse key missing entirely
    parsed = {
        "placement_status": "ready",
        "lat": 48.7, "lng": -122.4,
        "azimuth_deg": 270,
    }
    result = decide_placement(parsed)
    assert result.verb == "LEGACY_PRECISE"
