from datetime import date

import duckdb
import pandas as pd
import pytest

from market_logic import (
    eligible_neighborhoods,
    market_reading,
    market_scope_stats,
    market_windows,
    monthly_market_series,
    neighborhood_snapshot,
    pct_change,
    prepare_market_series,
    price_distribution,
    rank_neighborhoods,
)

RV = "GREATEST(COALESCE(valor_declarado,0), COALESCE(valor_base_calculo,0))"
RM = f"({RV}) / NULLIF(area_construida,0)"


def _connection():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE transactions (
            bairro VARCHAR,
            tipo_construtivo VARCHAR,
            data_quitacao DATE,
            valor_declarado DOUBLE,
            valor_base_calculo DOUBLE,
            area_construida DOUBLE,
            ano_construcao INTEGER,
            padrao_acabamento VARCHAR
        )
        """
    )
    rows = []

    def add_many(bairro, when, count, value, area=100.0, year=2010, pattern="P4"):
        rows.extend(
            [(bairro, "AP", when, value, value * 0.95, area, year, pattern)] * count
        )

    # ALFA: 30 negócios atuais a 10 mil/m² e 20 na janela equivalente a 8 mil/m².
    add_many("ALFA", "2026-03-15", 10, 1_000_000)
    add_many("ALFA", "2026-04-15", 10, 1_000_000)
    add_many("ALFA", "2026-05-01", 10, 1_000_000)
    add_many("ALFA", "2025-03-15", 7, 800_000)
    add_many("ALFA", "2025-04-15", 7, 800_000)
    add_many("ALFA", "2025-05-01", 6, 800_000)
    # Negócios adicionais para volume de 12 meses e distribuição de preços.
    add_many("ALFA", "2025-08-01", 5, 400_000)
    add_many("ALFA", "2025-09-01", 5, 600_000)
    add_many("ALFA", "2025-10-01", 5, 850_000)
    add_many("ALFA", "2025-11-01", 5, 1_200_000)
    add_many("ALFA", "2025-12-01", 5, 1_700_000)
    # Período anterior aos últimos 12 meses.
    add_many("ALFA", "2024-08-01", 10, 700_000)
    add_many("ALFA", "2024-11-01", 10, 750_000)

    # BETA: bairro mais barato, mas com amostra suficiente.
    add_many("BETA", "2026-03-10", 10, 600_000, area=120.0, year=2000, pattern="P3")
    add_many("BETA", "2026-04-10", 10, 600_000, area=120.0, year=2000, pattern="P3")
    add_many("BETA", "2026-05-01", 10, 600_000, area=120.0, year=2000, pattern="P3")
    add_many("BETA", "2025-03-10", 15, 540_000, area=120.0, year=2000, pattern="P3")
    add_many("BETA", "2025-04-10", 15, 540_000, area=120.0, year=2000, pattern="P3")
    add_many("BETA", "2025-08-10", 10, 570_000, area=120.0, year=2000, pattern="P3")
    add_many("BETA", "2024-08-10", 20, 500_000, area=120.0, year=2000, pattern="P3")

    # GAMA: amostra pequena que não deve entrar nos rankings rigorosos.
    add_many("GAMA", "2026-04-01", 3, 2_000_000)
    add_many("GAMA", "2025-04-01", 3, 500_000)

    con.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return con


def test_market_windows_are_calendar_aligned():
    windows = market_windows("2026-05-01")
    assert windows["current_start"] == date(2026, 3, 1)
    assert windows["prior_start"] == date(2025, 3, 1)
    assert windows["last12_start"] == date(2025, 6, 1)
    assert windows["previous12_end"] == date(2025, 5, 31)


def test_pct_change_handles_positive_negative_and_zero_base():
    assert pct_change(125, 100) == pytest.approx(25.0)
    assert pct_change(80, 100) == pytest.approx(-20.0)
    assert pct_change(10, 0) is None
    assert pct_change(None, 10) is None


def test_prepare_market_series_masks_small_windows_without_dropping_months():
    frame = pd.DataFrame(
        {
            "mes": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
            "transacoes_3m": [4, 5, 7],
            "mediana_m2_3m": [1000.0, 2000.0, 3000.0],
        }
    )
    result = prepare_market_series(frame)
    assert len(result) == 3
    assert pd.isna(result.loc[0, "mediana_m2_3m"])
    assert result.loc[1, "mediana_m2_3m"] == 2000.0
    assert result["amostra_suficiente"].tolist() == [False, True, True]


def test_prepare_market_series_rejects_incomplete_input():
    with pytest.raises(ValueError, match="colunas obrigatórias"):
        prepare_market_series(pd.DataFrame({"mes": ["2026-01-01"]}))


def test_market_scope_stats_calculates_current_change_volume_and_profile():
    con = _connection()
    try:
        stats = market_scope_stats(
            con,
            bairro="ALFA",
            tipo="AP",
            end_date="2026-05-01",
            reference_value_sql=RV,
            reference_m2_sql=RM,
        )
    finally:
        con.close()

    assert stats["current_m2"] == pytest.approx(10_000.0)
    assert stats["prior_m2"] == pytest.approx(8_000.0)
    assert stats["change_12m"] == pytest.approx(25.0)
    assert stats["records_12m"] == 55
    assert stats["records_previous_12m"] == 40
    assert stats["volume_change_12m"] == pytest.approx(37.5)
    assert stats["median_area"] == 100.0
    assert stats["median_year"] == 2010.0
    assert stats["common_pattern"] == "P4"
    assert sum(stats[f"band_{idx}"] for idx in range(5)) == 55


def test_market_scope_stats_respects_neighborhood_filter():
    con = _connection()
    try:
        alpha = market_scope_stats(
            con,
            bairro="ALFA",
            tipo="AP",
            end_date="2026-05-01",
            reference_value_sql=RV,
            reference_m2_sql=RM,
        )
        beta = market_scope_stats(
            con,
            bairro="BETA",
            tipo="AP",
            end_date="2026-05-01",
            reference_value_sql=RV,
            reference_m2_sql=RM,
        )
    finally:
        con.close()
    assert alpha["current_m2"] > beta["current_m2"]
    assert alpha["records_12m"] != beta["records_12m"]


def test_monthly_market_series_returns_smoothed_series():
    con = _connection()
    try:
        series = monthly_market_series(
            con,
            bairro="ALFA",
            tipo="AP",
            date_start="2025-01-01",
            date_end="2026-05-01",
            reference_m2_sql=RM,
        )
    finally:
        con.close()
    assert not series.empty
    assert "mediana_m2_3m" in series.columns
    assert "transacoes_3m" in series.columns
    assert "amostra_suficiente" in series.columns
    assert series["mes"].is_monotonic_increasing


def test_monthly_market_series_uses_pooled_transactions_not_median_of_monthly_medians():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE transactions (
            bairro VARCHAR,
            tipo_construtivo VARCHAR,
            data_quitacao DATE,
            valor_declarado DOUBLE,
            valor_base_calculo DOUBLE,
            area_construida DOUBLE
        )
        """
    )
    rows = []
    rows.extend([("ALFA", "AP", "2026-01-15", 100_000.0, 100_000.0, 100.0)] * 9)
    rows.append(("ALFA", "AP", "2026-02-15", 1_000_000.0, 1_000_000.0, 100.0))
    rows.append(("ALFA", "AP", "2026-03-15", 1_000_000.0, 1_000_000.0, 100.0))
    con.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)", rows)
    try:
        series = monthly_market_series(
            con,
            bairro="ALFA",
            tipo="AP",
            date_start="2026-01-01",
            date_end="2026-03-31",
            reference_m2_sql=RM,
        )
    finally:
        con.close()

    march = series.set_index(series["mes"].dt.strftime("%Y-%m")).loc["2026-03"]
    assert march["transacoes_3m"] == 11
    assert march["mediana_m2_3m"] == pytest.approx(1000.0)


def test_monthly_market_series_preserves_calendar_gaps_and_breaks_sparse_windows():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE transactions (
            bairro VARCHAR, tipo_construtivo VARCHAR, data_quitacao DATE,
            valor_declarado DOUBLE, valor_base_calculo DOUBLE, area_construida DOUBLE
        )
        """
    )
    rows = [("ALFA", "AP", "2026-01-15", 100_000.0, 100_000.0, 100.0)] * 5
    rows += [("ALFA", "AP", "2026-04-15", 900_000.0, 900_000.0, 100.0)] * 4
    con.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)", rows)
    try:
        series = monthly_market_series(
            con,
            bairro="ALFA",
            tipo="AP",
            date_start="2026-01-01",
            date_end="2026-04-30",
            reference_m2_sql=RM,
        )
    finally:
        con.close()

    assert series["mes"].dt.strftime("%Y-%m").tolist() == [
        "2026-01", "2026-02", "2026-03", "2026-04"
    ]
    april = series.set_index(series["mes"].dt.strftime("%Y-%m")).loc["2026-04"]
    assert april["transacoes_3m"] == 4
    assert pd.isna(april["mediana_m2_3m"])
    assert not bool(april["amostra_suficiente"])


def test_monthly_market_series_uses_two_prior_months_for_first_visible_point():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE transactions (
            bairro VARCHAR, tipo_construtivo VARCHAR, data_quitacao DATE,
            valor_declarado DOUBLE, valor_base_calculo DOUBLE, area_construida DOUBLE
        )
        """
    )
    rows = [("ALFA", "AP", "2025-11-15", 100_000.0, 100_000.0, 100.0)] * 5
    rows += [("ALFA", "AP", "2025-12-15", 200_000.0, 200_000.0, 100.0)] * 5
    rows += [("ALFA", "AP", "2026-01-15", 300_000.0, 300_000.0, 100.0)] * 5
    con.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)", rows)
    try:
        series = monthly_market_series(
            con,
            bairro="ALFA",
            tipo="AP",
            date_start="2026-01-01",
            date_end="2026-01-31",
            reference_m2_sql=RM,
        )
    finally:
        con.close()

    assert len(series) == 1
    assert series.iloc[0]["transacoes_3m"] == 15
    assert series.iloc[0]["mediana_m2_3m"] == pytest.approx(2000.0)


def test_neighborhood_snapshot_computes_changes_for_each_bairro():
    con = _connection()
    try:
        snapshot = neighborhood_snapshot(
            con,
            tipo="AP",
            end_date="2026-05-01",
            reference_value_sql=RV,
            reference_m2_sql=RM,
        )
    finally:
        con.close()
    alpha = snapshot.set_index("bairro").loc["ALFA"]
    beta = snapshot.set_index("bairro").loc["BETA"]
    assert alpha["change_12m"] == pytest.approx(25.0)
    assert beta["change_12m"] == pytest.approx((5000 / 4500 - 1) * 100)


def test_eligible_neighborhoods_filters_sparse_samples():
    con = _connection()
    try:
        snapshot = neighborhood_snapshot(
            con,
            tipo="AP",
            end_date="2026-05-01",
            reference_value_sql=RV,
            reference_m2_sql=RM,
        )
    finally:
        con.close()
    eligible = eligible_neighborhoods(snapshot, require_prior=True)
    assert set(eligible["bairro"]) == {"ALFA", "BETA"}
    assert "GAMA" not in set(eligible["bairro"])


def test_rank_neighborhoods_orders_metrics_and_rejects_invalid_metric():
    con = _connection()
    try:
        snapshot = neighborhood_snapshot(
            con,
            tipo="AP",
            end_date="2026-05-01",
            reference_value_sql=RV,
            reference_m2_sql=RM,
        )
    finally:
        con.close()
    highest = rank_neighborhoods(snapshot, "current_m2")
    busiest = rank_neighborhoods(snapshot, "records_12m")
    assert highest.iloc[0]["bairro"] == "ALFA"
    assert busiest.iloc[0]["bairro"] == "ALFA"
    with pytest.raises(ValueError, match="Métrica de ranking inválida"):
        rank_neighborhoods(snapshot, "inventada")


def test_price_distribution_preserves_total_transactions():
    con = _connection()
    try:
        stats = market_scope_stats(
            con,
            bairro="ALFA",
            tipo="AP",
            end_date="2026-05-01",
            reference_value_sql=RV,
            reference_m2_sql=RM,
        )
    finally:
        con.close()
    distribution = price_distribution(stats)
    assert distribution["transacoes"].sum() == stats["records_12m"]
    assert distribution.iloc[0]["faixa"] == "Até R$ 500 mil"
    assert len(distribution) == 5


def test_market_reading_mentions_price_volume_and_city_comparison():
    stats = {
        "change_12m": 12.5,
        "volume_change_12m": -10.0,
        "current_m2": 9000.0,
    }
    city = {"current_m2": 7500.0}
    reading = market_reading("Alfa", stats, city)
    assert "12,5% acima" in reading
    assert "caiu 10,0%" in reading
    assert "20,0% acima" in reading


def test_market_reading_handles_insufficient_sample():
    reading = market_reading(
        "Alfa",
        {"change_12m": None, "volume_change_12m": None, "current_m2": None},
        {"current_m2": None},
    )
    assert "amostra suficiente" in reading
