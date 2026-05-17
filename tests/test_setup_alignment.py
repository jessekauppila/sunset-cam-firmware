"""Tests for setup_alignment.py — the alignment-page HTML renderer."""
from __future__ import annotations

from sunset_cam.setup_alignment import render_align_page


def test_render_align_page_returns_string():
    html = render_align_page(lat=48.75, lng=-122.48)
    assert isinstance(html, str)
    assert html.startswith("<!doctype html>")


def test_render_align_page_embeds_preview_image_src():
    html = render_align_page(lat=48.75, lng=-122.48)
    assert 'src="/setup/preview.mjpg"' in html


def test_render_align_page_has_horizon_line_at_center():
    html = render_align_page(lat=48.75, lng=-122.48)
    assert '<line' in html
    assert 'y1="450"' in html and 'y2="450"' in html
    assert 'stroke-dasharray' in html


def test_render_align_page_has_up_label():
    html = render_align_page(lat=48.75, lng=-122.48)
    assert "UP" in html
    assert ("↑" in html) or ("&uarr;" in html)


def test_render_align_page_embeds_coordinates_in_data_attrs():
    # lat/lng should be embedded so client-side JS (added in Task 6)
    # can read them. v1: just data-attributes on the root element.
    html = render_align_page(lat=48.75, lng=-122.48)
    assert 'data-lat="48.75"' in html
    assert 'data-lng="-122.48"' in html


def test_render_align_page_includes_orientation_readout_element():
    html = render_align_page(lat=48.75, lng=-122.48)
    assert 'id="roll-readout"' in html
    assert 'id="pitch-readout"' in html


def test_render_align_page_includes_polling_script_targeting_orientation_endpoint():
    html = render_align_page(lat=48.75, lng=-122.48)
    assert "/setup/orientation.json" in html
    assert "setInterval" in html


def test_render_align_page_includes_level_badge():
    html = render_align_page(lat=48.75, lng=-122.48)
    assert 'id="level-badge"' in html


import json
from sunset_cam.orientation_sampler import OrientationSampler
from sunset_cam.setup_alignment import render_orientation_json


def test_render_orientation_json_empty_when_sampler_has_no_reading():
    sampler = OrientationSampler(reader=lambda: (0.0, 0.0))
    body = render_orientation_json(sampler)
    parsed = json.loads(body)
    assert parsed == {}


def test_render_orientation_json_returns_latest_reading():
    sampler = OrientationSampler(reader=lambda: (1.5, 2.5))
    sampler.sample_once()
    body = render_orientation_json(sampler)
    parsed = json.loads(body)
    assert abs(parsed["roll_deg"] - 1.5) < 0.001
    assert abs(parsed["pitch_deg"] - 2.5) < 0.001
    assert "sampled_at" in parsed


def test_render_align_page_has_facing_selector_with_three_options():
    html = render_align_page(lat=48.75, lng=-122.48)
    assert 'value="east"' in html
    assert 'value="west"' in html
    assert 'value="both"' in html


def test_render_align_page_embeds_per_facing_solstice_markers_and_counts():
    html = render_align_page(lat=48.75, lng=-122.48)
    # Each facing variant has its own marker x-positions + sunsets/year count
    # rendered into the SVG.
    assert html.count('data-facing="east"') >= 1
    assert html.count('data-facing="west"') >= 1
    assert html.count('data-facing="both"') >= 1


def test_render_align_page_default_facing_is_west():
    html = render_align_page(lat=48.75, lng=-122.48)
    # West radio input is checked by default
    assert 'value="west" checked' in html or 'value="west"  checked' in html


from sunset_cam.setup_alignment import stream_mjpeg, MJPEG_BOUNDARY


def test_mjpeg_boundary_is_exported_and_nontrivial():
    assert isinstance(MJPEG_BOUNDARY, str)
    assert len(MJPEG_BOUNDARY) >= 8


def test_stream_mjpeg_yields_three_frames_from_a_three_call_source():
    frames = [b"AAA", b"BBB", b"CCC"]
    call_index = {"i": 0}

    def source() -> bytes:
        i = call_index["i"]
        call_index["i"] += 1
        if i >= len(frames):
            raise StopIteration
        return frames[i]

    out = b"".join(stream_mjpeg(source))
    assert out.count(f"--{MJPEG_BOUNDARY}".encode()) == 3
    assert out.count(b"Content-Type: image/jpeg") == 3
    for f in frames:
        assert f in out


def test_stream_mjpeg_includes_content_length_per_part():
    def source() -> bytes:
        source.count = getattr(source, "count", 0) + 1
        if source.count > 1:
            raise StopIteration
        return b"X" * 17

    out = b"".join(stream_mjpeg(source))
    assert b"Content-Length: 17" in out


def test_stream_mjpeg_terminates_on_stopiteration():
    def source() -> bytes:
        raise StopIteration
    assert list(stream_mjpeg(source)) == []


def test_stream_mjpeg_swallows_source_exception_and_stops():
    def source() -> bytes:
        raise RuntimeError("glitch")
    assert list(stream_mjpeg(source)) == []
