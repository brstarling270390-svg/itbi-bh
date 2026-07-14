from pathlib import Path

import pytest

from location_logic import (
    geolocation_error_message,
    is_belo_horizonte,
    location_confirmation_label,
    location_details,
    match_bairro,
    normalize_geolocation_payload,
    reverse_geocode,
    rounded_coordinates,
    transaction_location_prefill,
    valuation_location_prefill,
)


BH_RESULT = {
    "display_name": "123, Rua Pernambuco, Funcionários, Belo Horizonte, Minas Gerais, Brasil",
    "address": {
        "house_number": "123",
        "road": "Rua Pernambuco",
        "suburb": "Funcionários",
        "city": "Belo Horizonte",
        "state": "Minas Gerais",
        "country": "Brasil",
    },
}


def test_geolocation_payload_stays_idle_until_user_grants_location():
    assert normalize_geolocation_payload(None) == {"status": "idle"}
    assert normalize_geolocation_payload({"latitude": None, "longitude": None}) == {"status": "idle"}


def test_geolocation_payload_normalizes_valid_coordinates_and_accuracy():
    result = normalize_geolocation_payload(
        {"latitude": "-19.93", "longitude": "-43.94", "accuracy": "12.4"}
    )
    assert result == {
        "status": "ok",
        "latitude": -19.93,
        "longitude": -43.94,
        "accuracy": 12.4,
    }


def test_geolocation_payload_surfaces_browser_error():
    result = normalize_geolocation_payload(
        {"latitude": None, "longitude": None, "error": 1, "message": "denied"}
    )
    assert result["status"] == "error"
    assert result["error"] == 1


def test_geolocation_payload_rejects_out_of_range_coordinates():
    result = normalize_geolocation_payload({"latitude": 100, "longitude": 200})
    assert result["status"] == "error"
    assert result["error"] == "invalid_coordinates"


def test_coordinates_are_rounded_for_cache_key():
    assert rounded_coordinates(-19.9312349, -43.9387654) == (-19.93123, -43.93877)


def test_reverse_geocode_sends_required_identification_and_parameters():
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return BH_RESULT

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    result = reverse_geocode(
        -19.93,
        -43.94,
        endpoint="https://example.test/reverse",
        requester=fake_get,
        min_interval_seconds=0,
    )
    assert result == BH_RESULT
    assert captured["url"] == "https://example.test/reverse"
    assert captured["params"]["format"] == "jsonv2"
    assert captured["params"]["layer"] == "address"
    assert captured["params"]["addressdetails"] == 1
    assert captured["headers"]["User-Agent"].startswith("QuantoValeBH/")
    assert "Referer" in captured["headers"]


def test_reverse_geocode_rejects_non_object_response():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    with pytest.raises(ValueError):
        reverse_geocode(
            -19.93,
            -43.94,
            requester=lambda *a, **k: FakeResponse(),
            min_interval_seconds=0,
        )


def test_belo_horizonte_detection_uses_city_or_display_name():
    assert is_belo_horizonte(BH_RESULT) is True
    assert is_belo_horizonte({"display_name": "Savassi, Belo Horizonte, Brasil", "address": {}}) is True
    assert is_belo_horizonte({"display_name": "Contagem, Minas Gerais", "address": {"city": "Contagem"}}) is False


def test_bairro_matching_ignores_accents_and_case():
    assert match_bairro(BH_RESULT, ["FUNCIONARIOS", "LOURDES"]) == "FUNCIONARIOS"


def test_bairro_matching_handles_osm_qualifier_and_close_spelling():
    qualified = {"address": {"suburb": "Bairro Santo Agostinho", "city": "Belo Horizonte"}}
    assert match_bairro(qualified, ["SANTO AGOSTINHO", "LOURDES"]) == "SANTO AGOSTINHO"


def test_location_details_builds_search_text_and_confirmation_label():
    details = location_details(BH_RESULT, ["FUNCIONARIOS", "LOURDES"])
    assert details["search_text"] == "Rua Pernambuco 123"
    assert details["bairro"] == "FUNCIONARIOS"
    assert details["in_belo_horizonte"] is True
    assert location_confirmation_label(details) == "Rua Pernambuco, 123 · Funcionarios"


def test_location_prefills_are_scoped_to_the_selected_product_flow():
    details = location_details(BH_RESULT, ["FUNCIONARIOS"])
    assert transaction_location_prefill(details) == {
        "text": "Rua Pernambuco 123",
        "bairros": ["FUNCIONARIOS"],
        "tipos": [],
    }
    assert valuation_location_prefill(details) == {
        "text": "Rua Pernambuco 123",
        "bairro": "FUNCIONARIOS",
    }


def test_permission_and_timeout_errors_have_actionable_messages():
    assert "permissão" in geolocation_error_message(1).lower()
    assert "sinal" in geolocation_error_message(3).lower()


def test_vendored_component_requests_high_accuracy_and_returns_errors():
    js_files = list(
        (Path("location_component") / "frontend" / "build" / "static" / "js").glob("main.*.js")
    )
    assert len(js_files) == 1
    source = js_files[0].read_text(encoding="utf-8")
    assert "Detectar minha localização" in source
    assert "navigator.geolocation.getCurrentPosition" in source
    assert "enableHighAccuracy:!0" in source
    assert "maximumAge:6e4" in source
    assert "Não foi possível obter a localização." in source


def test_reverse_geocode_rate_limiter_waits_between_requests(monkeypatch):
    import location_logic

    calls = []
    sleeps = []
    times = iter([100.0, 100.0, 100.2, 101.0])

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return BH_RESULT

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse()

    monkeypatch.setattr(location_logic, "_LAST_REVERSE_REQUEST_AT", 100.0)
    monkeypatch.setattr(location_logic.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(location_logic.time, "sleep", lambda value: sleeps.append(value))

    reverse_geocode(
        -19.93,
        -43.94,
        requester=fake_get,
        min_interval_seconds=1.0,
    )

    assert len(calls) == 1
    assert sleeps == [1.0]
