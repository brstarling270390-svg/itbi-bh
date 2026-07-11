import pandas as pd
import pytest

from data_manager import Resource, validate_source_schema


def _resource():
    return Resource("id", "arquivo oficial", "local", None, None, None)


def test_validate_source_schema_accepts_current_pbh_columns():
    columns = [
        "Endereco",
        "Bairro",
        "Ano de Construcao (Unidade)",
        "Area Construida Adquirida",
        "Tipo Construtivo Preponderante",
        "Valor Declarado",
        "Valor Base Calculo",
        "Data Quitacao",
    ]
    validate_source_schema(columns, _resource())


def test_validate_source_schema_accepts_historical_pbh_columns():
    columns = [
        "Endereco",
        "Bairro",
        "Ano de Construcao Unidade",
        "Area Construida Adquirida",
        "Tipo Construtivo Preponderante",
        "Valor Declarado",
        "Valor Base Calculo",
        "Data Quitacao Transacao",
    ]
    validate_source_schema(columns, _resource())


def test_validate_source_schema_rejects_silent_schema_break():
    columns = ["Endereco", "Bairro", "Preco Novo", "Data"]
    with pytest.raises(RuntimeError, match="estrutura da PBH pode ter mudado"):
        validate_source_schema(columns, _resource())


def test_demo_builder_path_can_use_small_explicit_minimum(tmp_path, monkeypatch):
    # A trava de volume é configurável para testes/demonstrações; a carga oficial
    # continua usando o mínimo padrão de 1.000 registros.
    from data_manager import Resource, build_database
    import data_manager

    rows = []
    for i in range(2):
        rows.append({
            "Endereco": f"RUA TESTE {i}",
            "Bairro": "CENTRO",
            "Area Construida Adquirida": "100,00",
            "Tipo Construtivo Preponderante": "AP",
            "Valor Declarado": "500.000,00",
            "Valor Base Calculo": "550.000,00",
            "Data Quitacao": "01/05/2026",
        })
    csv_path = tmp_path / "small.csv"
    pd.DataFrame(rows).to_csv(csv_path, sep=";", index=False)
    monkeypatch.setattr(data_manager, "DB_PATH", tmp_path / "small.duckdb")
    monkeypatch.setattr(data_manager, "METADATA_PATH", tmp_path / "metadata.json")
    resource = Resource("id", "2026 - Maio - ITBI Relatórios", "local", None, None, None)
    metadata = build_database([resource], [csv_path], minimum_records=1)
    assert metadata["registros"] == 2


def test_failed_schema_load_preserves_existing_database(tmp_path, monkeypatch):
    from data_manager import Resource, build_database
    import data_manager
    import duckdb

    db_path = tmp_path / "base.duckdb"
    meta_path = tmp_path / "metadata.json"
    monkeypatch.setattr(data_manager, "DB_PATH", db_path)
    monkeypatch.setattr(data_manager, "METADATA_PATH", meta_path)

    valid_path = tmp_path / "valid.csv"
    valid_rows = pd.DataFrame([
        {
            "Endereco": "RUA TESTE 1",
            "Bairro": "CENTRO",
            "Area Construida Adquirida": "100,00",
            "Tipo Construtivo Preponderante": "AP",
            "Valor Declarado": "500.000,00",
            "Valor Base Calculo": "550.000,00",
            "Data Quitacao": "01/05/2026",
        }
    ])
    valid_rows.to_csv(valid_path, sep=";", index=False)
    valid_resource = Resource("ok", "2026 - Maio - ITBI Relatórios", "local", None, None, None)
    build_database([valid_resource], [valid_path], minimum_records=1)

    invalid_path = tmp_path / "invalid.csv"
    pd.DataFrame([{"Endereco": "RUA X", "Preco Novo": "10"}]).to_csv(
        invalid_path, sep=";", index=False
    )
    invalid_resource = Resource("bad", "2026 - Junho - ITBI Relatórios", "local", None, None, None)

    with pytest.raises(RuntimeError):
        build_database([invalid_resource], [invalid_path], minimum_records=1)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1
    finally:
        con.close()
