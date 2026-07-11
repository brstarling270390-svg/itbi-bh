import pandas as pd

from data_manager import Resource, normalize_chunk, normalize_text, parse_ptbr_number


def test_normalize_text():
    assert normalize_text("Rua São José, 100") == "rua sao jose 100"


def test_parse_ptbr_number():
    result = parse_ptbr_number(pd.Series(["1.234.567,89", "10,5", ""]))
    assert result.iloc[0] == 1234567.89
    assert result.iloc[1] == 10.5
    assert pd.isna(result.iloc[2])


def test_normalize_chunk():
    raw = pd.DataFrame({
        "Endereco Completo": ["RUA TESTE 1"],
        "Bairro": ["Centro"],
        "Ano de Construcao (Unidade)": ["2020"],
        "Area Construida Adquirida": ["100,00"],
        "Tipo Construtivo Preponderante": ["AP"],
        "Valor Declarado": ["500.000,00"],
        "Valor Base Calculo": ["550.000,00"],
        "Data Quitacao": ["01/05/2026"],
    })
    resource = Resource("id", "teste", "local", None, None, None)
    result = normalize_chunk(raw, resource)
    assert result.loc[0, "valor_declarado"] == 500000
    assert result.loc[0, "valor_m2_declarado"] == 5000
    assert result.loc[0, "bairro"] == "CENTRO"
