from sunset_cam.directive_executor import execute


def test_execute_ship_logs_ships_and_reports_done():
    shipped = {}
    res = execute(
        {"id": "d1", "type": "ship-logs", "payload": {"unit": "sunset-cam", "lines": 50}},
        log_sink=lambda text: shipped.__setitem__("text", text),
        journal_reader=lambda unit, lines: f"== {unit} last {lines} lines ==",
    )
    assert res["id"] == "d1"
    assert res["status"] == "done"
    assert "sunset-cam" in shipped["text"]


def test_execute_unknown_type_reports_failed():
    res = execute(
        {"id": "d2", "type": "frobnicate"},
        log_sink=lambda t: None,
        journal_reader=lambda u, l: "",
    )
    assert res["id"] == "d2"
    assert res["status"] == "failed"
    assert "frobnicate" in res["detail"]


def test_execute_ship_logs_defaults_unit_and_lines():
    captured = {}
    execute(
        {"id": "d3", "type": "ship-logs"},
        log_sink=lambda t: None,
        journal_reader=lambda unit, lines: (captured.update(unit=unit, lines=lines), "x")[1],
    )
    assert captured["unit"] == "sunset-cam"   # sensible default
    assert captured["lines"] == 200


def test_execute_reports_failed_when_a_sink_raises():
    def boom(_text):
        raise RuntimeError("network down")
    res = execute(
        {"id": "d4", "type": "ship-logs"},
        log_sink=boom,
        journal_reader=lambda u, l: "logs",
    )
    assert res["status"] == "failed"
    assert "network down" in res["detail"]
