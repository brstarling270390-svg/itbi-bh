from data_manager import select_csv_resources


def _resource(name, rid):
    return {
        "id": rid,
        "name": name,
        "format": "CSV",
        "url": f"https://example.test/{rid}.csv",
        "last_modified": "2026-07-01",
    }


def test_select_csv_resources_matches_current_pbh_naming_and_scope():
    package = {
        "resources": [
            _resource("01/2008 a 05/2024 - ITBI Relatórios", "hist"),
            _resource("2024 - Junho - ITBI Relatórios", "jun24"),
            _resource("2026 - Maio - ITBI Relatórios", "mai26"),
            {"id": "dict", "name": "Dicionário de Dados ITBI Relatórios", "format": "PDF", "url": "https://example.test/dict.pdf"},
        ]
    }
    recent = select_csv_resources(package, include_historical=False)
    full = select_csv_resources(package, include_historical=True)
    assert [r.resource_id for r in recent] == ["jun24", "mai26"]
    assert [r.resource_id for r in full] == ["hist", "jun24", "mai26"]
