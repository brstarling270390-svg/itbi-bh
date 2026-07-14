from streamlit.testing.v1 import AppTest
import data_manager


FAKE_METADATA = {
    "registros": 1000,
    "registros_unicos": 1000,
    "data_inicial": "2008-01-01",
    "data_final": "2026-05-01",
    "escopo": "historico_completo",
}


def _app(monkeypatch):
    monkeypatch.setattr(data_manager, "load_metadata", lambda: FAKE_METADATA.copy())
    monkeypatch.setattr(data_manager, "database_exists", lambda: True)
    return AppTest.from_file("app.py", default_timeout=30).run()


def _patch_fake_gps(monkeypatch):
    import location_component
    import location_logic

    monkeypatch.setattr(
        location_component,
        "current_location",
        lambda *, key: {
            "latitude": -19.93,
            "longitude": -43.94,
            "accuracy": 10.0,
            "error": None,
            "message": None,
        },
    )
    monkeypatch.setattr(
        location_logic,
        "reverse_geocode",
        lambda latitude, longitude: {
            "display_name": "Rua, Funcionários, Belo Horizonte, Minas Gerais, Brasil",
            "address": {
                "road": "Rua",
                "suburb": "Funcionários",
                "city": "Belo Horizonte",
                "state": "Minas Gerais",
            },
        },
    )


def test_fake_gps_can_fill_and_execute_valuation_search(monkeypatch):
    _patch_fake_gps(monkeypatch)
    at = _app(monkeypatch)
    gps = next(i for i, button in enumerate(at.button) if button.key == "open_gps_valuation")
    at.button[gps].click().run()

    assert not at.exception
    apply_button = next(i for i, button in enumerate(at.button) if button.key == "apply_gps_valuation")
    at.button[apply_button].click().run()

    assert not at.exception
    assert at.session_state["valuation_search_text"] == "Rua"
    assert at.session_state["valuation_search_bairro"] == "FUNCIONARIOS"
    assert "valuation_search_results" in at.session_state


def test_fake_gps_prefills_transactions_search(monkeypatch):
    _patch_fake_gps(monkeypatch)
    at = _app(monkeypatch)
    at.segmented_control[0].set_value("Transações").run()
    gps = next(i for i, button in enumerate(at.button) if button.key == "open_gps_transactions")
    at.button[gps].click().run()
    apply_button = next(i for i, button in enumerate(at.button) if button.key == "apply_gps_transactions")
    at.button[apply_button].click().run()

    assert not at.exception
    assert at.session_state["transaction_search_text"] == "Rua"
    assert at.session_state["transaction_bairros"] == ["FUNCIONARIOS"]


def test_fake_gps_selects_detected_neighborhood_in_market(monkeypatch):
    _patch_fake_gps(monkeypatch)
    at = _app(monkeypatch)
    at.segmented_control[0].set_value("Mercado").run()
    gps = next(i for i, button in enumerate(at.button) if button.key == "open_gps_market")
    at.button[gps].click().run()
    apply_button = next(i for i, button in enumerate(at.button) if button.key == "apply_gps_market")
    at.button[apply_button].click().run()

    assert not at.exception
    assert at.session_state["market_bairro"] == "FUNCIONARIOS"
    assert at.selectbox[0].value == "FUNCIONARIOS"
