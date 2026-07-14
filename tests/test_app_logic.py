import duckdb
import pandas as pd
import pytest

from app_logic import (
    comparable_source_exclusions,
    evaluate_selected_transaction,
    exclude_source_rows,
    same_address_reference_breakdown,
    selected_source_identifiers,
    store_hybrid_result,
)


def _filtered_ids(*, registro_id=None, chave_tecnica=None):
    con = duckdb.connect(":memory:")
    try:
        con.execute(
            "CREATE TABLE rows (registro_id VARCHAR, chave_tecnica VARCHAR, endereco VARCHAR)"
        )
        con.executemany(
            "INSERT INTO rows VALUES (?, ?, ?)",
            [
                ("origem", "chave-origem", "RUA TESTE 10 - AP 101"),
                ("copia", "chave-origem", "RUA TESTE 10 - AP 101"),
                ("legitima", "chave-legitima", "RUA TESTE 10 - AP 202"),
                ("outra", "chave-outra", "RUA TESTE 20 - AP 301"),
            ],
        )
        clauses, params = comparable_source_exclusions(registro_id, chave_tecnica)
        where = " AND ".join(["TRUE", *clauses])
        return {
            row[0]
            for row in con.execute(
                f"SELECT registro_id FROM rows WHERE {where}", params
            ).fetchall()
        }
    finally:
        con.close()


def test_excludes_source_transaction_by_registro_id():
    remaining = _filtered_ids(registro_id="origem")
    assert "origem" not in remaining
    assert "copia" in remaining


def test_excludes_equivalent_copy_by_chave_tecnica():
    remaining = _filtered_ids(
        registro_id="origem", chave_tecnica="chave-origem"
    )
    assert "origem" not in remaining
    assert "copia" not in remaining


def test_preserves_legitimate_transactions_from_same_address():
    remaining = _filtered_ids(
        registro_id="origem", chave_tecnica="chave-origem"
    )
    assert "legitima" in remaining
    assert "outra" in remaining


def test_without_source_identifiers_preserves_existing_query_behavior():
    clauses, params = comparable_source_exclusions(None, None)
    assert clauses == []
    assert params == []


def test_selected_transaction_identifiers_reach_local_and_building_exclusions():
    selected = pd.Series(
        {"registro_id": "origem", "chave_tecnica": "chave-origem"}
    )
    identifiers = selected_source_identifiers(selected)

    assert identifiers == {
        "source_registro_id": "origem",
        "source_chave_tecnica": "chave-origem",
    }

    clauses, params = comparable_source_exclusions(**identifiers)
    assert clauses == ["registro_id <> ?", "chave_tecnica <> ?"]
    assert params == ["origem", "chave-origem"]

    building_rows = pd.DataFrame(
        [
            {"registro_id": "origem", "chave_tecnica": "chave-origem"},
            {"registro_id": "copia", "chave_tecnica": "chave-origem"},
            {"registro_id": "legitima", "chave_tecnica": "chave-legitima"},
        ]
    )
    filtered = exclude_source_rows(building_rows, **identifiers)
    assert filtered["registro_id"].tolist() == ["legitima"]


def test_selected_transaction_identifiers_reach_hybrid_evaluator():
    captured = {}

    def fake_hybrid_evaluator(**kwargs):
        captured.update(kwargs)
        return "resultado"

    selected = pd.Series(
        {"registro_id": "origem", "chave_tecnica": "chave-origem"}
    )
    result = evaluate_selected_transaction(
        fake_hybrid_evaluator,
        selected,
        old_value=420_000,
        bairro="NOVA GRANADA",
    )

    assert result == "resultado"
    assert captured["source_registro_id"] == "origem"
    assert captured["source_chave_tecnica"] == "chave-origem"
    assert captured["old_value"] == 420_000
    assert captured["bairro"] == "NOVA GRANADA"


def test_manual_flow_keeps_all_rows_without_source_identifiers():
    identifiers = {
        "source_registro_id": None,
        "source_chave_tecnica": None,
    }
    clauses, params = comparable_source_exclusions(**identifiers)
    assert clauses == []
    assert params == []

    rows = pd.DataFrame(
        [
            {"registro_id": "uma", "chave_tecnica": "chave-uma"},
            {"registro_id": "duas", "chave_tecnica": "chave-duas"},
        ]
    )
    filtered = exclude_source_rows(rows, **identifiers)
    assert filtered["registro_id"].tolist() == ["uma", "duas"]


def test_successful_hybrid_result_is_stored_for_dialog():
    state = {}
    result = store_hybrid_result(
        state,
        local_rows="locais",
        building_rows="predio",
        stats={"estimated": 700_000},
        subject={"source_transaction": False},
    )
    assert result is None
    assert state["hybrid_stats"]["estimated"] == 700_000
    assert state["hybrid_local"] == "locais"
    assert state["hybrid_building"] == "predio"


def test_repeated_results_replace_previous_dialog_content():
    state = {}
    for estimated in (700_000, 750_000, 810_000):
        store_hybrid_result(
            state,
            local_rows=f"locais-{estimated}",
            building_rows=f"predio-{estimated}",
            stats={"estimated": estimated},
            subject={"source_transaction": True},
        )

    assert state["hybrid_stats"]["estimated"] == 810_000
    assert state["hybrid_local"] == "locais-810000"
    assert state["hybrid_building"] == "predio-810000"


def test_same_address_breakdown_normalizes_area_before_fipe_update():
    breakdown = same_address_reference_breakdown(
        reference_value=700_000,
        reference_m2=700_000 / 159.90,
        transaction_area=159.90,
        subject_area=117.13,
        fipe_factor=1.4389,
    )

    assert breakdown["reference_m2"] == pytest.approx(4_377.736085, rel=1e-9)
    assert breakdown["area_adjusted_value"] == pytest.approx(512_764.2276422763, rel=1e-9)
    assert breakdown["current_equivalent"] == pytest.approx(737_816.4471544714, rel=1e-9)
    assert breakdown["current_equivalent"] != pytest.approx(700_000 * 1.4389)


def test_same_address_breakdown_same_area_reduces_to_temporal_update():
    breakdown = same_address_reference_breakdown(
        reference_value=433_272,
        reference_m2=433_272 / 117.13,
        transaction_area=117.13,
        subject_area=117.13,
        fipe_factor=1.5824,
    )

    assert breakdown["area_adjusted_value"] == pytest.approx(433_272)
    assert breakdown["current_equivalent"] == pytest.approx(433_272 * 1.5824)


def test_same_address_breakdown_rejects_non_positive_inputs():
    with pytest.raises(ValueError):
        same_address_reference_breakdown(
            reference_value=700_000,
            reference_m2=4_377.73,
            transaction_area=159.90,
            subject_area=0,
            fipe_factor=1.4389,
        )
