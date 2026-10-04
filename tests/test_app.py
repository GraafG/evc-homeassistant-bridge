"""Unit tests for station parsing and API response behavior."""

import app as app_module


def test_parse_station_data_extracts_connectors_and_availability():
    raw = {
        "name": "Central Garage",
        "address": "Main Street 1",
        "postalCode": "1234 AB",
        "city": "Amsterdam",
        "operator": {"name": "EVC Network"},
        "evses": [
            {
                "evseId": "NL*EVC*1",
                "status": "OCCUPIED",
                "connectors": [
                    {
                        "id": "1",
                        "standard": "IEC_62196_T2",
                        "powerType": "AC_3_PHASE",
                        "maxElectricPower": 22000,
                    }
                ],
            },
            {"evseId": "NL*EVC*2", "status": "AVAILABLE", "connectors": []},
        ],
    }

    result = app_module.parse_station_data(
        raw, {"qr_code": "TEST-1*1", "name": "Test station"}
    )

    assert result["status"] == "AVAILABLE"
    assert result["provider"] == "EVC Network"
    assert result["connectors"][0]["connectors"][0]["max_power"] == "22.0"


def test_parse_station_data_preserves_errors():
    result = app_module.parse_station_data(
        {"error": "network unavailable"},
        {"qr_code": "TEST-1*1", "name": "Test station"},
    )

    assert result == {
        "qr_code": "TEST-1*1",
        "config_name": "Test station",
        "error": "network unavailable",
    }


def test_empty_summary_does_not_report_all_available():
    with app_module.cache_lock:
        app_module.cache.update(
            stations=[], timestamp=None, last_fetch=None, last_error=None, refreshing=False
        )

    response = app_module.app.test_client().get("/api/v1/summary")

    assert response.status_code == 200
    assert response.get_json()["all_available"] is False


def test_refresh_endpoint_is_post_only(monkeypatch):
    monkeypatch.setattr(app_module, "refresh_cache", lambda blocking=False: True)
    client = app_module.app.test_client()

    assert client.get("/api/refresh").status_code == 405
    response = client.post("/api/refresh")
    assert response.status_code == 202
    assert response.get_json()["started"] is True


def test_failed_refresh_is_visible_without_discarding_cache(monkeypatch):
    with app_module.cache_lock:
        app_module.cache.update(
            stations=[{"qr_code": "cached"}],
            timestamp="previous",
            last_fetch=1.0,
            last_error=None,
            refreshing=False,
        )

    def fail_fetch():
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(app_module, "fetch_all_stations", fail_fetch)
    assert app_module.refresh_cache() is True

    snapshot = app_module.get_cache_snapshot()
    assert snapshot["stations"] == [{"qr_code": "cached"}]
    assert snapshot["last_error"] == "upstream unavailable"
    assert snapshot["refreshing"] is False
