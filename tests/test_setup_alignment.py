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
