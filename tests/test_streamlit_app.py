import data_manager
from streamlit.testing.v1 import AppTest


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


def test_app_starts_on_single_valuation_flow_without_legacy_method_selector(monkeypatch):
    at = _app(monkeypatch)
    assert not at.exception
    assert at.subheader[0].value == "Estimar valor atual"
    assert at.segmented_control[1].options == [
        "Buscar imóvel na base",
        "Informar dados manualmente",
    ]
    assert all("Comparáveis recentes" not in control.options for control in at.segmented_control)


def test_two_consecutive_selected_property_evaluations_generate_new_scroll_tokens(monkeypatch):
    at = _app(monkeypatch)
    at.text_input[0].set_value("RUA")
    at.button[0].click().run()
    assert not at.exception

    first = next(i for i, button in enumerate(at.button) if button.key == "hybrid_update_demo:6")
    at.button[first].click().run()
    assert not at.exception
    assert at.session_state["_hybrid_scroll_sequence"] == 1
    assert [tab.label for tab in at.tabs] == ["Resumo", "Imóveis semelhantes (0)"]
    assert any('hybrid-result-anchor-1' in item.value for item in at.markdown)
    first_result = next(
        item.value for item in at.markdown if "Estimativa de valor atual" in item.value
    )

    second = next(i for i, button in enumerate(at.button) if button.key == "hybrid_update_demo:7")
    at.button[second].click().run()
    assert not at.exception
    assert at.session_state["_hybrid_scroll_sequence"] == 2
    assert "_hybrid_scroll_pending" not in at.session_state
    assert [tab.label for tab in at.tabs] == ["Resumo", "Imóveis semelhantes (4)"]
    assert any('hybrid-result-anchor-2' in item.value for item in at.markdown)
    assert "demo:7" not in set(at.session_state["hybrid_local"]["registro_id"].astype(str))
    if not at.session_state["hybrid_building"].empty:
        assert "demo:7" not in set(at.session_state["hybrid_building"]["registro_id"].astype(str))
    second_result = next(
        item.value for item in at.markdown if "Estimativa de valor atual" in item.value
    )
    assert second_result != first_result


def test_manual_valuation_flow_calculates_and_requests_scroll(monkeypatch):
    at = _app(monkeypatch)
    at.segmented_control[1].set_value("Informar dados manualmente").run()
    assert not at.exception

    at.selectbox[0].set_value("FUNCIONARIOS")
    at.selectbox[1].set_value("AP")
    at.number_input[1].set_value(120.0)
    at.button[0].click().run()

    assert not at.exception
    assert at.session_state["_hybrid_scroll_sequence"] == 1
    assert any("Estimativa de valor atual" in item.value for item in at.markdown)
    assert [tab.label for tab in at.tabs][0] == "Resumo"


def test_more_similar_properties_opens_prefilled_transactions(monkeypatch):
    at = _app(monkeypatch)
    at.text_input[0].set_value("RUA")
    at.button[0].click().run()
    target = next(i for i, button in enumerate(at.button) if button.key == "hybrid_update_demo:7")
    at.button[target].click().run()
    more = next(i for i, button in enumerate(at.button) if button.key == "view_more_similar")
    at.button[more].click().run()

    assert not at.exception
    assert at.segmented_control[0].value == "Transações"
    assert at.text_input[0].value == "RUA PERNAMBUCO"
    assert at.multiselect[0].value == ["FUNCIONARIOS"]
    assert at.multiselect[1].value == ["AP"]


def test_market_dashboard_renders_all_product_sections(monkeypatch):
    at = _app(monkeypatch)
    at.segmented_control[0].set_value("Mercado").run()
    assert not at.exception

    headings = [item.value for item in at.subheader]
    assert headings == [
        "Mercado imobiliário de Belo Horizonte",
        "Evolução do valor por m²",
        "Quanto custam os imóveis negociados em Belo Horizonte?",
        "Compare bairros",
        "Radar dos bairros",
        "Perfil dos imóveis negociados em Belo Horizonte",
    ]
    labels = [metric.label for metric in at.metric]
    assert "Valor atual por m²" in labels
    assert "Variação em 12 meses" in labels
    assert "Negócios em 12 meses" in labels
    assert "Faixa central por m²" in labels
    assert len(at.get("plotly_chart")) >= 2


def test_market_dashboard_supports_neighborhood_and_longer_period(monkeypatch):
    at = _app(monkeypatch)
    at.segmented_control[0].set_value("Mercado").run()
    at.selectbox[0].set_value("FUNCIONARIOS").run()
    assert not at.exception
    assert any(
        "O que está acontecendo em Funcionarios" in item.value for item in at.info
    )

    period_control = next(
        control for control in at.segmented_control if control.label == "Período do gráfico"
    )
    period_control.set_value("5 anos").run()
    assert not at.exception
    assert any("Perfil dos imóveis negociados em Funcionarios" == item.value for item in at.subheader)


def test_all_primary_navigation_screens_render_without_exception(monkeypatch):
    at = _app(monkeypatch)
    for screen in ["Transações", "Mercado", "Sobre", "Avaliar"]:
        at.segmented_control[0].set_value(screen).run()
        assert not at.exception, screen
