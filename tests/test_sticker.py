"""TDD tests for sticker.py — setup_url() (pure) and render_sticker() (I/O)."""
import pytest
from sunset_cam.sticker import render_sticker, setup_url


# ---------------------------------------------------------------------------
# setup_url — pure function tests
# ---------------------------------------------------------------------------


def test_setup_url_basic():
    assert setup_url("https://x.example.com", "SUNSET-AAAA-BBBB") == (
        "https://x.example.com/setup/SUNSET-AAAA-BBBB"
    )


def test_setup_url_strips_trailing_slash_from_web_base():
    assert setup_url("https://x.example.com/", "SUNSET-AAAA-BBBB") == (
        "https://x.example.com/setup/SUNSET-AAAA-BBBB"
    )


def test_setup_url_various_claim_codes():
    url = setup_url("https://sunset.cam", "SUNSET-CCCC-DDDD")
    assert url == "https://sunset.cam/setup/SUNSET-CCCC-DDDD"


def test_setup_url_preserves_https_scheme():
    url = setup_url("https://api.sunset.cam", "SUNSET-0001-AAAA")
    assert url.startswith("https://")


def test_setup_url_contains_claim_code_at_end():
    code = "SUNSET-ZZZZ-9999"
    url = setup_url("https://example.com", code)
    assert url.endswith(code)


# ---------------------------------------------------------------------------
# render_sticker — I/O tests (writes a real PNG to tmp_path)
# ---------------------------------------------------------------------------


def test_render_sticker_creates_file(tmp_path):
    out = tmp_path / "sticker.png"
    render_sticker("SUNSET-AAAA-BBBB", "https://sunset.cam", str(out))
    assert out.exists(), "render_sticker did not create the output file"


def test_render_sticker_output_is_nonempty(tmp_path):
    out = tmp_path / "sticker.png"
    render_sticker("SUNSET-AAAA-BBBB", "https://sunset.cam", str(out))
    assert out.stat().st_size > 0, "render_sticker wrote an empty file"


def test_render_sticker_creates_valid_png(tmp_path):
    """The PNG header magic bytes must be present."""
    out = tmp_path / "sticker.png"
    render_sticker("SUNSET-TEST-1234", "https://sunset.cam", str(out))
    header = out.read_bytes()[:8]
    # PNG magic: \x89PNG\r\n\x1a\n
    assert header == b"\x89PNG\r\n\x1a\n", f"Not a valid PNG header: {header!r}"


def test_render_sticker_accepts_different_claim_codes(tmp_path):
    for code in ("SUNSET-AAAA-BBBB", "SUNSET-1234-ZZZZ"):
        out = tmp_path / f"sticker-{code}.png"
        render_sticker(code, "https://sunset.cam", str(out))
        assert out.exists() and out.stat().st_size > 0
