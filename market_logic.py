from __future__ import annotations

from typing import Any

import pandas as pd

MIN_RADAR_TRANSACTIONS = 20
MIN_WINDOW_TRANSACTIONS = 5

PRICE_BANDS = (
    ("Até R$ 500 mil", 0.0, 500_000.0),
    ("R$ 500–750 mil", 500_000.0, 750_000.0),
    ("R$ 750 mil–1 mi", 750_000.0, 1_000_000.0),
    ("R$ 1–1,5 mi", 1_000_000.0, 1_500_000.0),
    ("Acima de R$ 1,5 mi", 1_500_000.0, None),
)


def market_windows(end_date: object) -> dict[str, object]:
    """Cria janelas de 3 e 12 meses alinhadas por mês-calendário."""
    end = pd.Timestamp(end_date).normalize()
    current_start = end.to_period("M").to_timestamp() - pd.DateOffset(months=2)
    prior_start = current_start - pd.DateOffset(years=1)
    prior_end = end - pd.DateOffset(years=1)
    last12_start = end.to_period("M").to_timestamp() - pd.DateOffset(months=11)
    previous12_start = last12_start - pd.DateOffset(years=1)
    previous12_end = last12_start - pd.DateOffset(days=1)
    return {
        "end": end.date(),
        "current_start": current_start.date(),
        "current_end": end.date(),
        "prior_start": prior_start.date(),
        "prior_end": prior_end.date(),
        "last12_start": last12_start.date(),
        "last12_end": end.date(),
        "previous12_start": previous12_start.date(),
        "previous12_end": previous12_end.date(),
    }


def pct_change(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous is None or pd.isna(current) or pd.isna(previous):
        return None
    previous_value = float(previous)
    if abs(previous_value) < 1e-12:
        return None
    return (float(current) / previous_value - 1.0) * 100.0


def _scope_filter(bairro: str | None, tipo: str | None) -> tuple[list[str], list[object]]:
    where: list[str] = []
    params: list[object] = []
    if bairro:
        where.append("bairro = ?")
        params.append(bairro)
    if tipo:
        where.append("tipo_construtivo = ?")
        params.append(tipo)
    return where, params


def _date_sql(value: object) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def market_scope_stats(
    con: Any,
    *,
    bairro: str | None,
    tipo: str | None,
    end_date: object,
    reference_value_sql: str,
    reference_m2_sql: str,
) -> dict[str, Any]:
    windows = market_windows(end_date)
    where, params = _scope_filter(bairro, tipo)
    where.extend(
        [
            f"{reference_value_sql} > 0",
            f"{reference_m2_sql} BETWEEN 300 AND 100000",
            f"data_quitacao BETWEEN DATE '{_date_sql(windows['previous12_start'])}' AND DATE '{_date_sql(windows['end'])}'",
        ]
    )
    clause = " AND ".join(where)
    current = f"data_quitacao BETWEEN DATE '{_date_sql(windows['current_start'])}' AND DATE '{_date_sql(windows['current_end'])}'"
    prior = f"data_quitacao BETWEEN DATE '{_date_sql(windows['prior_start'])}' AND DATE '{_date_sql(windows['prior_end'])}'"
    last12 = f"data_quitacao BETWEEN DATE '{_date_sql(windows['last12_start'])}' AND DATE '{_date_sql(windows['last12_end'])}'"
    previous12 = f"data_quitacao BETWEEN DATE '{_date_sql(windows['previous12_start'])}' AND DATE '{_date_sql(windows['previous12_end'])}'"

    row = con.execute(
        f"""
        SELECT
            MEDIAN({reference_m2_sql}) FILTER (WHERE {current}) AS current_m2,
            COUNT(*) FILTER (WHERE {current}) AS current_records,
            MEDIAN({reference_m2_sql}) FILTER (WHERE {prior}) AS prior_m2,
            COUNT(*) FILTER (WHERE {prior}) AS prior_records,
            COUNT(*) FILTER (WHERE {last12}) AS records_12m,
            COUNT(*) FILTER (WHERE {previous12}) AS records_previous_12m,
            QUANTILE_CONT({reference_m2_sql}, 0.25) FILTER (WHERE {last12}) AS q25_m2,
            QUANTILE_CONT({reference_m2_sql}, 0.75) FILTER (WHERE {last12}) AS q75_m2,
            QUANTILE_CONT({reference_value_sql}, 0.25) FILTER (WHERE {last12}) AS q25_value,
            MEDIAN({reference_value_sql}) FILTER (WHERE {last12}) AS median_value,
            QUANTILE_CONT({reference_value_sql}, 0.75) FILTER (WHERE {last12}) AS q75_value,
            MEDIAN(area_construida) FILTER (WHERE {last12} AND area_construida > 0) AS median_area,
            MEDIAN(ano_construcao) FILTER (WHERE {last12} AND ano_construcao BETWEEN 1800 AND 2200) AS median_year,
            MODE(padrao_acabamento) FILTER (WHERE {last12} AND padrao_acabamento IS NOT NULL) AS common_pattern,
            COUNT(*) FILTER (WHERE {last12} AND {reference_value_sql} < 500000) AS band_0,
            COUNT(*) FILTER (WHERE {last12} AND {reference_value_sql} >= 500000 AND {reference_value_sql} < 750000) AS band_1,
            COUNT(*) FILTER (WHERE {last12} AND {reference_value_sql} >= 750000 AND {reference_value_sql} < 1000000) AS band_2,
            COUNT(*) FILTER (WHERE {last12} AND {reference_value_sql} >= 1000000 AND {reference_value_sql} < 1500000) AS band_3,
            COUNT(*) FILTER (WHERE {last12} AND {reference_value_sql} >= 1500000) AS band_4
        FROM transactions
        WHERE {clause}
        """,
        params,
    ).fetchone()
    columns = [item[0] for item in con.description]
    result = dict(zip(columns, row))
    result["change_12m"] = pct_change(result.get("current_m2"), result.get("prior_m2"))
    result["volume_change_12m"] = pct_change(
        result.get("records_12m"), result.get("records_previous_12m")
    )
    result["windows"] = windows
    return result

def monthly_market_series(
    con: Any,
    *,
    bairro: str | None,
    tipo: str | None,
    date_start: object,
    date_end: object,
    reference_m2_sql: str,
) -> pd.DataFrame:
    where = [
        "data_quitacao BETWEEN ? AND ?",
        f"{reference_m2_sql} BETWEEN 300 AND 100000",
    ]
    params: list[object] = [date_start, date_end]
    scope_where, scope_params = _scope_filter(bairro, tipo)
    where.extend(scope_where)
    params.extend(scope_params)
    frame = con.execute(
        f"""
        SELECT DATE_TRUNC('month', data_quitacao) AS mes,
               COUNT(*) AS transacoes,
               MEDIAN({reference_m2_sql}) AS mediana_m2
        FROM transactions
        WHERE {' AND '.join(where)}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
    ).fetchdf()
    return prepare_market_series(frame)


def prepare_market_series(series: pd.DataFrame) -> pd.DataFrame:
    if series.empty:
        return series.copy()
    frame = series.copy().sort_values("mes").reset_index(drop=True)
    frame["mediana_m2_3m"] = frame["mediana_m2"].rolling(3, min_periods=1).median()
    return frame


def neighborhood_snapshot(
    con: Any,
    *,
    tipo: str | None,
    end_date: object,
    reference_value_sql: str,
    reference_m2_sql: str,
) -> pd.DataFrame:
    windows = market_windows(end_date)
    where = [
        "bairro IS NOT NULL",
        f"{reference_value_sql} > 0",
        f"{reference_m2_sql} BETWEEN 300 AND 100000",
        f"data_quitacao BETWEEN DATE '{_date_sql(windows['previous12_start'])}' AND DATE '{_date_sql(windows['end'])}'",
    ]
    params: list[object] = []
    if tipo:
        where.append("tipo_construtivo = ?")
        params.append(tipo)
    current = f"data_quitacao BETWEEN DATE '{_date_sql(windows['current_start'])}' AND DATE '{_date_sql(windows['current_end'])}'"
    prior = f"data_quitacao BETWEEN DATE '{_date_sql(windows['prior_start'])}' AND DATE '{_date_sql(windows['prior_end'])}'"
    last12 = f"data_quitacao BETWEEN DATE '{_date_sql(windows['last12_start'])}' AND DATE '{_date_sql(windows['last12_end'])}'"
    previous12 = f"data_quitacao BETWEEN DATE '{_date_sql(windows['previous12_start'])}' AND DATE '{_date_sql(windows['previous12_end'])}'"
    frame = con.execute(
        f"""
        SELECT bairro,
            MEDIAN({reference_m2_sql}) FILTER (WHERE {current}) AS current_m2,
            COUNT(*) FILTER (WHERE {current}) AS current_records,
            MEDIAN({reference_m2_sql}) FILTER (WHERE {prior}) AS prior_m2,
            COUNT(*) FILTER (WHERE {prior}) AS prior_records,
            COUNT(*) FILTER (WHERE {last12}) AS records_12m,
            COUNT(*) FILTER (WHERE {previous12}) AS records_previous_12m,
            MEDIAN({reference_value_sql}) FILTER (WHERE {last12}) AS median_value,
            MEDIAN(area_construida) FILTER (WHERE {last12} AND area_construida > 0) AS median_area,
            MEDIAN(ano_construcao) FILTER (WHERE {last12} AND ano_construcao BETWEEN 1800 AND 2200) AS median_year,
            MODE(padrao_acabamento) FILTER (WHERE {last12} AND padrao_acabamento IS NOT NULL) AS common_pattern
        FROM transactions
        WHERE {' AND '.join(where)}
        GROUP BY bairro
        """,
        params,
    ).fetchdf()
    if frame.empty:
        return frame
    frame["change_12m"] = frame.apply(
        lambda row: pct_change(row["current_m2"], row["prior_m2"]), axis=1
    )
    frame["volume_change_12m"] = frame.apply(
        lambda row: pct_change(row["records_12m"], row["records_previous_12m"]), axis=1
    )
    return frame

def price_distribution(stats: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "faixa": [item[0] for item in PRICE_BANDS],
            "transacoes": [int(stats.get(f"band_{idx}") or 0) for idx in range(len(PRICE_BANDS))],
        }
    )


def eligible_neighborhoods(
    snapshot: pd.DataFrame,
    *,
    require_prior: bool = False,
    min_transactions: int = MIN_RADAR_TRANSACTIONS,
    min_window_transactions: int = MIN_WINDOW_TRANSACTIONS,
) -> pd.DataFrame:
    if snapshot.empty:
        return snapshot.copy()
    frame = snapshot[
        snapshot["records_12m"].ge(min_transactions)
        & snapshot["current_records"].ge(min_window_transactions)
        & snapshot["current_m2"].notna()
    ].copy()
    if require_prior:
        frame = frame[
            frame["prior_records"].ge(min_window_transactions)
            & frame["change_12m"].notna()
        ].copy()
    return frame


def rank_neighborhoods(snapshot: pd.DataFrame, metric: str, limit: int = 10) -> pd.DataFrame:
    valid_metrics = {"current_m2", "change_12m", "records_12m"}
    if metric not in valid_metrics:
        raise ValueError(f"Métrica de ranking inválida: {metric}")
    frame = eligible_neighborhoods(snapshot, require_prior=metric == "change_12m")
    return frame.sort_values(metric, ascending=False).head(limit).reset_index(drop=True)


def market_reading(scope_label: str, stats: dict[str, Any], city_stats: dict[str, Any]) -> str:
    change = stats.get("change_12m")
    volume = stats.get("volume_change_12m")
    current_m2 = stats.get("current_m2")
    city_m2 = city_stats.get("current_m2")
    parts: list[str] = []

    def pct_text(value: float) -> str:
        return f"{abs(value):.1f}".replace(".", ",")

    if change is not None:
        direction = "acima" if change >= 0 else "abaixo"
        parts.append(
            f"O valor de referência atual por m² está {pct_text(change)}% {direction} do observado há 12 meses"
        )
    elif current_m2 is not None:
        parts.append("Há valor de referência atual disponível, mas a amostra de 12 meses atrás é insuficiente para medir a variação")

    if volume is not None:
        verb = "cresceu" if volume >= 0 else "caiu"
        parts.append(
            f"o número de transações nos últimos 12 meses {verb} {pct_text(volume)}% em relação aos 12 meses anteriores"
        )

    premium = pct_change(current_m2, city_m2)
    if scope_label != "Belo Horizonte" and premium is not None:
        direction = "acima" if premium >= 0 else "abaixo"
        parts.append(
            f"o nível atual está {pct_text(premium)}% {direction} da referência de Belo Horizonte para o mesmo tipo de imóvel"
        )

    if not parts:
        return f"Ainda não há amostra suficiente para formar uma leitura consistente de {scope_label}."
    return ". ".join(parts) + "."
