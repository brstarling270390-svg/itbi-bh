from __future__ import annotations

from datetime import timedelta
import html
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from data_manager import (
    DB_PATH,
    FIPEZAP_BH_PATH,
    FIPEZAP_SOURCE_URL,
    TYPE_LABELS,
    connect_read_only,
    database_exists,
    load_metadata,
    load_fipezap_bh_series,
    fipezap_factor,
    normalize_text,
    update_from_pbh,
    update_fipezap_bh,
)

st.set_page_config(
    page_title="Quanto Vale BH",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    :root {
        --qv-blue: #2f6fed;
        --qv-soft: rgba(127,127,127,.08);
        --qv-border: rgba(127,127,127,.23);
        --qv-muted: rgba(127,127,127,.90);
    }

    .block-container {
        padding-top: 1rem;
        padding-bottom: 3rem;
        max-width: 1000px;
    }

    [data-testid="stHeader"] {background: transparent;}
    #MainMenu, footer {visibility: hidden;}

    [data-testid="stMetric"] {
        background: var(--qv-soft);
        border: 1px solid var(--qv-border);
        border-radius: 16px;
        padding: .85rem 1rem;
    }
    [data-testid="stMetricLabel"] {opacity: .72;}
    [data-testid="stMetricValue"] {font-size: 1.42rem;}

    div[data-testid="stForm"] {
        border: 1px solid var(--qv-border);
        border-radius: 18px;
        padding: 1rem 1.05rem .8rem;
        background: var(--qv-soft);
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    [data-testid="stDateInput"] input {
        border-radius: 10px !important;
    }

    [data-testid="stBaseButton-primary"] {
        background: var(--qv-blue) !important;
        border-color: var(--qv-blue) !important;
        color: #fff !important;
        font-weight: 700 !important;
    }
    [data-testid="stBaseButton-primary"]:hover {
        filter: brightness(1.05);
    }

    div[data-testid="stSegmentedControl"] button {
        min-height: 2.65rem;
        border-radius: 10px !important;
        font-weight: 650;
    }
    div[data-testid="stSegmentedControl"] button[aria-pressed="true"] {
        color: var(--qv-blue) !important;
        border-color: var(--qv-blue) !important;
    }

    .brand {padding: .2rem 0 .35rem;}
    .brand-name {
        color: var(--qv-blue);
        font-size: .86rem;
        font-weight: 800;
        letter-spacing: .09em;
        text-transform: uppercase;
        margin-bottom: .4rem;
    }
    .brand-title {
        font-size: 2.15rem;
        font-weight: 800;
        line-height: 1.1;
        margin: 0;
        max-width: 820px;
    }
    .brand-subtitle {
        opacity: .72;
        font-size: .98rem;
        margin-top: .55rem;
        max-width: 760px;
    }

    .section-intro {
        opacity: .70;
        margin-top: -.35rem;
        margin-bottom: 1rem;
    }

    .data-note {
        border-left: 3px solid var(--qv-blue);
        padding: .1rem 0 .1rem .8rem;
        opacity: .72;
        font-size: .86rem;
        margin: .8rem 0 1.2rem;
    }

    .result-box {
        padding: 1.25rem 1.3rem;
        border: 1px solid var(--qv-border);
        border-radius: 18px;
        margin: .5rem 0 1rem;
        background: var(--qv-soft);
    }
    .result-title {
        font-size: .86rem;
        opacity: .72;
        margin-bottom: .25rem;
    }
    .result-value {
        font-size: 2rem;
        font-weight: 800;
        line-height: 1.12;
    }
    .muted {
        opacity: .68;
        font-size: .9rem;
        margin-top: .35rem;
    }

    .address-title {
        font-size: 1rem;
        font-weight: 760;
        line-height: 1.35;
        margin-bottom: .28rem;
    }
    .address-meta {
        opacity: .66;
        font-size: .86rem;
        margin-bottom: .85rem;
    }
    .record-detail {
        opacity: .68;
        font-size: .85rem;
        margin-top: .2rem;
    }
    .footer-note {
        border-top: 1px solid var(--qv-border);
        margin-top: 2rem;
        padding-top: 1rem;
        opacity: .62;
        font-size: .82rem;
    }

    @media (max-width: 768px) {
        .block-container {padding: .75rem .7rem 2.2rem;}
        .brand-title {font-size: 1.72rem;}
        .brand-subtitle {font-size: .9rem;}
        h2 {font-size: 1.32rem !important;}
        h3 {font-size: 1.15rem !important;}
        [data-testid="stMetricValue"] {font-size: 1.18rem;}
        [data-testid="stHorizontalBlock"] {flex-wrap: wrap;}
        [data-testid="column"] {
            min-width: 100% !important;
            width: 100% !important;
            flex: 1 1 100% !important;
        }
        button {min-height: 2.9rem;}
        .result-value {font-size: 1.55rem;}
        div[data-testid="stSegmentedControl"] {
            overflow-x: auto;
            padding-bottom: .15rem;
        }
        div[data-testid="stSegmentedControl"] button {
            white-space: nowrap;
            padding-left: .7rem !important;
            padding-right: .7rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def brl(value: float | int | None, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return "—"
    text = f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


def number_br(value: float | int | None, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


MONTHS_PT = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def normalize_date_range(value) -> tuple[object, object]:
    """Normaliza o retorno do st.date_input para um intervalo consultável."""
    if isinstance(value, tuple):
        if len(value) == 2:
            return value[0], value[1]
        if len(value) == 1:
            return value[0], value[0]
    return value, value


def data_limit_label(value: object) -> str:
    if value is None or value == "":
        return "data não informada"
    try:
        date = pd.to_datetime(value)
        return f"{MONTHS_PT[date.month - 1]} de {date.year}"
    except Exception:  # noqa: BLE001
        return str(value)


def smart_title(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    words = str(value).strip().lower().split()
    lowers = {"da", "das", "de", "do", "dos", "e"}
    pretty = [word if i > 0 and word in lowers else word.capitalize() for i, word in enumerate(words)]
    return " ".join(pretty)


def text_or_na(value: object, fallback: str = "não informado") -> str:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return fallback
    return str(value)


REFERENCE_VALUE_SQL = """
GREATEST(
    COALESCE(valor_declarado, 0),
    COALESCE(valor_base_calculo, 0)
)
"""

REFERENCE_M2_SQL = f"""
({REFERENCE_VALUE_SQL}) / NULLIF(area_construida, 0)
"""


def building_address_key(endereco: object) -> str:
    """Retorna o endereço-base do edifício/imóvel, sem complemento da unidade."""
    raw = "" if endereco is None or pd.isna(endereco) else str(endereco).strip()
    first = re.split(r"\s+-\s+", raw, maxsplit=1)[0].strip()
    return normalize_text(first)


def street_from_address(endereco: object) -> str:
    """Extrai o logradouro aproximado para priorização geográfica."""
    raw = "" if endereco is None or pd.isna(endereco) else str(endereco).strip()
    first = re.split(r"\s+-\s+", raw, maxsplit=1)[0].strip()
    first = re.sub(r",?\s+\d+[A-Za-z0-9./-]*\s*$", "", first).strip(" ,-")
    return first



def short_address(endereco: object, bairro: object = None) -> str:
    raw = "" if endereco is None or pd.isna(endereco) else str(endereco).strip()
    bairro_norm = normalize_text("" if bairro is None or pd.isna(bairro) else str(bairro))
    parts: list[str] = []
    for part in re.split(r"\s+-\s+", raw):
        clean = part.strip()
        normalized = normalize_text(clean)
        if not clean:
            continue
        if normalized in {bairro_norm, "belo horizonte", "mg"}:
            continue
        if re.fullmatch(r"\d{5}-?\d{3}", clean):
            continue
        parts.append(clean)

    if not parts:
        return smart_title(raw)

    first = smart_title(parts[0])
    first = re.sub(r"\s+(\d+[A-Za-z]?)$", r", \1", first)
    remaining = [smart_title(part) for part in parts[1:]]
    return " · ".join([first, *remaining])


def address_header(endereco: object, bairro: object, date_value: object, kind: object) -> None:
    title = html.escape(short_address(endereco, bairro))
    neighborhood = html.escape(smart_title(bairro))
    date_text = pd.to_datetime(date_value).strftime("%d/%m/%Y")
    kind_text = html.escape(str(kind) if kind is not None and not pd.isna(kind) else "Imóvel")
    st.markdown(
        f'<div class="address-title">{title}</div>'
        f'<div class="address-meta">{neighborhood} · {date_text} · {kind_text}</div>',
        unsafe_allow_html=True,
    )


def run_update(force: bool = False, include_historical: bool = False) -> None:
    progress = st.progress(0, text="Iniciando atualização...")

    def callback(current: int, total: int, message: str) -> None:
        progress.progress(min(current / max(total, 1), 1.0), text=message)

    try:
        metadata = update_from_pbh(
            progress_callback=callback,
            force_download=force,
            include_historical=include_historical,
        )
        progress.progress(0.96, text="Atualizando série FipeZAP de Belo Horizonte...")
        fipe_warning = None
        try:
            update_fipezap_bh()
        except Exception as fipe_exc:  # noqa: BLE001
            fipe_warning = str(fipe_exc)

        progress.progress(1.0, text="Bases atualizadas.")
        st.success(
            f"Atualização concluída: {metadata.get('registros', metadata.get('registros_unicos', 0)):,} registros da PBH, "
            f"até {metadata.get('data_final', 'data não informada')}.".replace(",", ".")
        )
        if fipe_warning:
            st.warning(
                "A base da PBH foi atualizada, mas a série FipeZAP não pôde ser renovada agora. "
                "O app continuará usando a última série disponível."
            )
        st.cache_data.clear()
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        progress.empty()
        st.error(f"A atualização não foi concluída: {exc}")


@st.cache_data(ttl=600)
def get_dimensions(db_mtime: float) -> dict:
    del db_mtime
    with connect_read_only() as con:
        row = con.execute(
            """
            SELECT MIN(data_quitacao), MAX(data_quitacao),
                   MIN(valor_declarado), MAX(valor_declarado),
                   MIN(area_construida), MAX(area_construida)
            FROM transactions
            """
        ).fetchone()
        bairros = con.execute(
            "SELECT DISTINCT bairro FROM transactions WHERE bairro IS NOT NULL ORDER BY bairro"
        ).fetchdf()["bairro"].tolist()
        tipos = con.execute(
            "SELECT DISTINCT tipo_construtivo FROM transactions WHERE tipo_construtivo IS NOT NULL ORDER BY tipo_construtivo"
        ).fetchdf()["tipo_construtivo"].tolist()
        padroes = con.execute(
            "SELECT DISTINCT padrao_acabamento FROM transactions WHERE padrao_acabamento IS NOT NULL ORDER BY padrao_acabamento"
        ).fetchdf()["padrao_acabamento"].tolist()
    return {
        "min_date": row[0], "max_date": row[1],
        "min_value": row[2] or 0, "max_value": row[3] or 0,
        "min_area": row[4] or 0, "max_area": row[5] or 0,
        "bairros": bairros, "tipos": tipos, "padroes": padroes,
    }


@st.cache_data(ttl=3600)
def get_fipezap_series(file_mtime: float) -> pd.DataFrame:
    del file_mtime
    return load_fipezap_bh_series()



def valuation_query(
    bairro: str,
    tipo: str,
    area: float,
    ano: int | None,
    padrao: str | None,
    rua: str | None,
    end_date,
    exclude_registro_id: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Busca comparáveis atuais em camadas.

    A janela máxima é de 36 meses. Para apartamentos, valores anteriores ao
    último mês do FipeZAP são trazidos a equivalente atual pelo índice de BH.
    """
    rua_search = normalize_text(rua)

    scenarios: list[tuple[int, float, int, bool, str]] = []

    if rua_search:
        if padrao:
            scenarios.append((24, 0.35, 3, True, "street"))
        scenarios.append((36, 0.50, 3, False, "street"))

    if padrao:
        scenarios.extend([
            (18, 0.20, 8, True, "neighborhood"),
            (24, 0.30, 6, True, "neighborhood"),
            (36, 0.40, 5, True, "neighborhood"),
        ])

    scenarios.extend([
        (18, 0.30, 8, False, "neighborhood"),
        (24, 0.40, 6, False, "neighborhood"),
        (36, 0.50, 4, False, "neighborhood"),
    ])

    chosen = None
    frame = pd.DataFrame()

    with connect_read_only() as con:
        for months, area_tol, minimum, strict_pattern, location_level in scenarios:
            start_date = pd.Timestamp(end_date) - pd.DateOffset(months=months)
            area_min = max(area * (1 - area_tol), 1)
            area_max = area * (1 + area_tol)

            where = [
                "bairro = ?",
                "tipo_construtivo = ?",
                "data_quitacao BETWEEN ? AND ?",
                "area_construida BETWEEN ? AND ?",
                f"{REFERENCE_VALUE_SQL} > 0",
                f"{REFERENCE_M2_SQL} BETWEEN 300 AND 100000",
            ]
            params: list[object] = [
                bairro,
                tipo,
                start_date.date(),
                end_date,
                area_min,
                area_max,
            ]

            if exclude_registro_id:
                where.append("registro_id <> ?")
                params.append(str(exclude_registro_id))

            if padrao and strict_pattern:
                where.append("padrao_acabamento = ?")
                params.append(padrao)

            if rua_search and location_level == "street":
                where.append("endereco_busca LIKE ?")
                params.append(f"%{rua_search}%")

            frame = con.execute(
                f"""
                SELECT registro_id, data_quitacao, endereco, endereco_busca, bairro,
                       tipo_construtivo, tipo_descricao, ano_construcao,
                       area_construida, padrao_acabamento, valor_declarado,
                       valor_base_calculo,
                       {REFERENCE_VALUE_SQL} AS valor_referencia,
                       {REFERENCE_M2_SQL} AS valor_m2_referencia
                FROM transactions
                WHERE {' AND '.join(where)}
                ORDER BY
                    CASE WHEN ? = '' OR endereco_busca LIKE ? THEN 0 ELSE 1 END,
                    data_quitacao DESC
                LIMIT 1000
                """,
                [*params, rua_search, f"%{rua_search}%"],
            ).fetchdf()

            if frame.empty:
                continue

            frame["dist_area"] = (frame["area_construida"] - area).abs() / area

            if ano is None:
                frame["dist_ano"] = 0.18
            else:
                year_distance = (
                    frame["ano_construcao"].astype("Float64") - ano
                ).abs() / 35.0
                frame["dist_ano"] = (
                    year_distance.clip(upper=1.0).fillna(0.18).astype(float)
                )

            if padrao is None:
                frame["penalidade_padrao"] = 0.0
            else:
                frame["penalidade_padrao"] = (
                    frame["padrao_acabamento"]
                    .fillna("")
                    .ne(padrao)
                    .astype(float)
                    * 0.35
                )

            if rua_search:
                same_street = frame["endereco_busca"].fillna("").str.contains(
                    rua_search,
                    regex=False,
                )
                frame["penalidade_local"] = (~same_street).astype(float) * 0.45
            else:
                frame["penalidade_local"] = 0.0

            # Recência também entra no ranking; transações antigas não devem
            # superar automaticamente observações atuais apenas por área idêntica.
            age_days = (
                pd.Timestamp(end_date) - pd.to_datetime(frame["data_quitacao"])
            ).dt.days.clip(lower=0)
            frame["penalidade_recencia"] = (age_days / 1095.0).clip(upper=1.0) * 0.20

            frame["score"] = (
                frame["dist_area"]
                + frame["dist_ano"]
                + frame["penalidade_padrao"]
                + frame["penalidade_local"]
                + frame["penalidade_recencia"]
            )
            frame = frame.sort_values(
                ["score", "data_quitacao"],
                ascending=[True, False],
            ).reset_index(drop=True)

            if len(frame) >= minimum:
                chosen = {
                    "months": months,
                    "area_tol": area_tol,
                    "minimum": minimum,
                    "strict_pattern": bool(padrao and strict_pattern),
                    "location_level": location_level,
                }
                break

    # Não produz estimativa com amostra abaixo do mínimo do cenário.
    if frame.empty or chosen is None:
        return pd.DataFrame(), {}

    frame = frame.head(30).copy()

    # Para apartamentos, normaliza temporalmente os comparáveis para o último
    # mês disponível do FipeZAP/BH. Transações posteriores ao último mês do
    # índice são mantidas com fator 1, pois já são mais recentes que o benchmark.
    frame["fator_temporal"] = 1.0
    frame["valor_equivalente_atual"] = frame["valor_referencia"].astype(float)
    frame["valor_m2_equivalente_atual"] = frame["valor_m2_referencia"].astype(float)
    time_adjusted = False

    if tipo == "AP":
        fipe_series = get_fipezap_series(
            FIPEZAP_BH_PATH.stat().st_mtime
            if FIPEZAP_BH_PATH.exists()
            else 0.0
        )
        fipe_latest = (
            pd.Timestamp(fipe_series["data"].max())
            if not fipe_series.empty
            else None
        )
        factors = []
        for date_value in frame["data_quitacao"]:
            tx_month = pd.Timestamp(date_value).to_period("M").to_timestamp()
            if fipe_latest is not None and tx_month > fipe_latest:
                factor = 1.0
            else:
                factor_info = fipezap_factor(
                    date_value,
                    series=fipe_series,
                )
                factor = (
                    float(factor_info["factor"])
                    if factor_info is not None
                    else 1.0
                )
            factors.append(factor)
        frame["fator_temporal"] = factors
        frame["valor_equivalente_atual"] = (
            frame["valor_referencia"] * frame["fator_temporal"]
        )
        frame["valor_m2_equivalente_atual"] = (
            frame["valor_m2_referencia"] * frame["fator_temporal"]
        )
        time_adjusted = bool(
            (frame["fator_temporal"] - 1.0).abs().gt(1e-9).any()
        )

    analysis_col = "valor_m2_equivalente_atual"
    q1 = frame[analysis_col].quantile(0.25)
    q3 = frame[analysis_col].quantile(0.75)
    iqr = q3 - q1
    if pd.notna(iqr) and iqr > 0:
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        trimmed = frame[frame[analysis_col].between(low, high)].copy()
        if len(trimmed) >= max(4, chosen["minimum"]):
            frame = trimmed

    median_m2 = float(frame[analysis_col].median())
    q25_m2 = float(frame[analysis_col].quantile(0.25))
    q75_m2 = float(frame[analysis_col].quantile(0.75))
    estimated = median_m2 * area
    low_value = q25_m2 * area
    high_value = q75_m2 * area

    stats = {
        "estimated": estimated,
        "low_value": low_value,
        "high_value": high_value,
        "median_m2": median_m2,
        "q25_m2": q25_m2,
        "q75_m2": q75_m2,
        "records": len(frame),
        "time_adjusted": time_adjusted,
        "reference_date": fipe_latest if tipo == "AP" and fipe_latest is not None else pd.Timestamp(end_date),
        **chosen,
    }
    return frame, stats



def query_transactions(
    text: str,
    bairros: list[str],
    tipos: list[str],
    padroes: list[str],
    date_start,
    date_end,
    limit: int = 300,
) -> tuple[pd.DataFrame, dict]:
    where = ["data_quitacao BETWEEN ? AND ?"]
    params: list[object] = [date_start, date_end]

    if text:
        terms = [
            normalize_text(term)
            for term in text.split()
            if normalize_text(term)
        ]
        for term in terms:
            where.append(
                "(endereco_busca LIKE ? OR bairro_busca LIKE ?)"
            )
            params.extend([f"%{term}%", f"%{term}%"])

    if bairros:
        placeholders = ",".join("?" for _ in bairros)
        where.append(f"bairro IN ({placeholders})")
        params.extend(bairros)

    if tipos:
        placeholders = ",".join("?" for _ in tipos)
        where.append(f"tipo_construtivo IN ({placeholders})")
        params.extend(tipos)

    if padroes:
        placeholders = ",".join("?" for _ in padroes)
        where.append(f"padrao_acabamento IN ({placeholders})")
        params.extend(padroes)

    clause = " AND ".join(where)

    with connect_read_only() as con:
        stats_row = con.execute(
            f"""
            SELECT COUNT(*),
                   MEDIAN({REFERENCE_VALUE_SQL})
                       FILTER (WHERE {REFERENCE_VALUE_SQL} > 0),
                   MEDIAN({REFERENCE_M2_SQL})
                       FILTER (WHERE {REFERENCE_M2_SQL} BETWEEN 300 AND 100000)
            FROM transactions
            WHERE {clause}
            """,
            params,
        ).fetchone()

        frame = con.execute(
            f"""
            SELECT registro_id, data_quitacao, endereco, endereco_busca, bairro,
                   tipo_construtivo, tipo_descricao, ano_construcao,
                   area_construida, area_somada, fracao_ideal,
                   padrao_acabamento, valor_declarado, valor_base_calculo,
                   {REFERENCE_VALUE_SQL} AS valor_referencia,
                   {REFERENCE_M2_SQL} AS valor_m2_referencia
            FROM transactions
            WHERE {clause}
            ORDER BY data_quitacao DESC,
                     {REFERENCE_VALUE_SQL} DESC NULLS LAST
            LIMIT {int(limit)}
            """,
            params,
        ).fetchdf()

    return frame, {
        "records": stats_row[0] or 0,
        "median_value": stats_row[1],
        "median_m2": stats_row[2],
    }


def search_transactions_for_valuation(
    text: str,
    bairro: str | None,
    date_start,
    date_end,
    limit: int = 80,
) -> pd.DataFrame:
    if not text and not bairro:
        return pd.DataFrame()

    where = [
        "data_quitacao BETWEEN ? AND ?",
        "area_construida > 0",
        f"{REFERENCE_VALUE_SQL} > 0",
    ]
    params: list[object] = [date_start, date_end]

    if text:
        terms = [
            normalize_text(term)
            for term in text.split()
            if normalize_text(term)
        ]
        for term in terms:
            where.append("endereco_busca LIKE ?")
            params.append(f"%{term}%")

    if bairro:
        where.append("bairro = ?")
        params.append(bairro)

    with connect_read_only() as con:
        return con.execute(
            f"""
            SELECT registro_id, data_quitacao, endereco, endereco_busca, bairro,
                   tipo_construtivo, tipo_descricao, ano_construcao,
                   area_construida, area_somada, fracao_ideal,
                   padrao_acabamento, valor_declarado, valor_base_calculo,
                   {REFERENCE_VALUE_SQL} AS valor_referencia,
                   {REFERENCE_M2_SQL} AS valor_m2_referencia
            FROM transactions
            WHERE {' AND '.join(where)}
            ORDER BY data_quitacao DESC
            LIMIT {int(limit)}
            """,
            params,
        ).fetchdf()


def query_same_building(
    endereco: object,
    limit: int = 200,
) -> pd.DataFrame:
    key = building_address_key(endereco)
    if not key:
        return pd.DataFrame()

    with connect_read_only() as con:
        return con.execute(
            f"""
            SELECT registro_id, data_quitacao, endereco, endereco_busca, bairro,
                   tipo_construtivo, tipo_descricao, ano_construcao,
                   area_construida, area_somada, fracao_ideal,
                   padrao_acabamento, valor_declarado, valor_base_calculo,
                   {REFERENCE_VALUE_SQL} AS valor_referencia,
                   {REFERENCE_M2_SQL} AS valor_m2_referencia
            FROM transactions
            WHERE endereco_busca = ?
               OR endereco_busca LIKE ?
            ORDER BY data_quitacao DESC
            LIMIT {int(limit)}
            """,
            [key, f"{key} %"],
        ).fetchdf()


def hybrid_value_update_query(
    old_value: float,
    purchase_date,
    bairro: str,
    tipo: str,
    area: float,
    ano: int | None,
    padrao: str | None,
    rua: str | None,
    end_date,
    source_address: str | None = None,
    source_registro_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Combina referências complementares para atualizar um valor antigo.

    1) FipeZAP BH: âncora temporal de apartamentos prontos anunciados.
    2) Comparáveis recentes PBH: nível local atual.
    3) Mesmo endereço: transações do edifício trazidas a valor atual pelo FipeZAP.

    A estimativa central é a mediana das referências centrais disponíveis.
    """
    fipe_series = get_fipezap_series(
        FIPEZAP_BH_PATH.stat().st_mtime
        if FIPEZAP_BH_PATH.exists()
        else 0.0
    )

    anchors: list[dict] = []
    fipe_info = None

    # O FipeZAP residencial acompanha apartamentos prontos.
    if tipo == "AP":
        fipe_info = fipezap_factor(
            purchase_date,
            series=fipe_series,
        )
        if fipe_info is not None:
            fipe_anchor = old_value * fipe_info["factor"]
            anchors.append(
                {
                    "source": "FipeZAP BH",
                    "value": float(fipe_anchor),
                    "detail": (
                        f"{fipe_info['growth_pct']:+.1f}% entre "
                        f"{fipe_info['start_date'].strftime('%m/%Y')} e "
                        f"{fipe_info['end_date'].strftime('%m/%Y')}"
                    ).replace(".", ","),
                    "sample": None,
                }
            )

    local_comparables, local_stats = valuation_query(
        bairro=bairro,
        tipo=tipo,
        area=area,
        ano=ano,
        padrao=padrao,
        rua=rua,
        end_date=end_date,
        exclude_registro_id=source_registro_id,
    )

    if local_stats:
        anchors.append(
            {
                "source": "Comparáveis PBH",
                "value": float(local_stats["estimated"]),
                "detail": (
                    f"{int(local_stats['records'])} comparáveis recentes · "
                    f"mediana {local_stats['median_m2']:.2f}/m² cadastral equivalente"
                ),
                "sample": int(local_stats["records"]),
            }
        )

    building_evidence = pd.DataFrame()

    if (
        source_address
        and tipo == "AP"
        and fipe_info is not None
    ):
        building_rows = query_same_building(source_address)

        if not building_rows.empty:
            building_rows = building_rows.copy()
            building_rows = building_rows[
                building_rows["tipo_construtivo"].eq(tipo)
                & building_rows["area_construida"].between(
                    area * 0.50,
                    area * 1.50,
                )
                & building_rows["valor_m2_referencia"].gt(0)
            ].copy()

            if source_registro_id:
                building_rows = building_rows[
                    building_rows["registro_id"].astype(str)
                    != str(source_registro_id)
                ].copy()

            indexed_values = []
            fipe_latest = pd.Timestamp(fipe_series["data"].max())
            for _, row in building_rows.iterrows():
                tx_month = pd.Timestamp(row["data_quitacao"]).to_period("M").to_timestamp()
                if tx_month > fipe_latest:
                    factor = 1.0
                else:
                    factor_info = fipezap_factor(
                        row["data_quitacao"],
                        series=fipe_series,
                    )
                    if factor_info is None:
                        continue
                    factor = float(factor_info["factor"])

                current_equivalent = (
                    float(row["valor_m2_referencia"])
                    * area
                    * factor
                )
                if current_equivalent <= 0:
                    continue

                item = row.copy()
                item["fator_fipe"] = factor
                item["valor_equivalente_atual"] = current_equivalent
                indexed_values.append(item)

            if indexed_values:
                building_evidence = pd.DataFrame(indexed_values)

                if len(building_evidence) >= 4:
                    q1 = building_evidence[
                        "valor_equivalente_atual"
                    ].quantile(0.25)
                    q3 = building_evidence[
                        "valor_equivalente_atual"
                    ].quantile(0.75)
                    iqr = q3 - q1
                    if pd.notna(iqr) and iqr > 0:
                        low = q1 - 1.5 * iqr
                        high = q3 + 1.5 * iqr
                        trimmed = building_evidence[
                            building_evidence[
                                "valor_equivalente_atual"
                            ].between(low, high)
                        ].copy()
                        if len(trimmed) >= 2:
                            building_evidence = trimmed

                building_anchor = float(
                    building_evidence[
                        "valor_equivalente_atual"
                    ].median()
                )
                anchors.append(
                    {
                        "source": "Mesmo endereço",
                        "value": building_anchor,
                        "detail": (
                            f"{len(building_evidence)} transação(ões) do endereço "
                            "trazida(s) ao mês mais recente pelo FipeZAP"
                        ),
                        "sample": int(len(building_evidence)),
                    }
                )

    if not anchors:
        return local_comparables, building_evidence, {}

    anchor_values = pd.Series(
        [item["value"] for item in anchors],
        dtype="float64",
    )
    estimated = float(anchor_values.median())
    low_value = float(anchor_values.min())
    high_value = float(anchor_values.max())

    spread_pct = (
        (high_value - low_value) / estimated * 100
        if estimated > 0
        else 999.0
    )

    building_count = len(building_evidence)
    local_count = int(local_stats.get("records", 0)) if local_stats else 0

    if (
        len(anchors) >= 3
        and building_count >= 3
        and local_count >= 8
        and spread_pct <= 20
    ):
        confidence = "Alta"
    elif len(anchors) >= 2 and spread_pct <= 35:
        confidence = "Média"
    else:
        confidence = "Baixa"

    return local_comparables, building_evidence, {
        "estimated": estimated,
        "low_value": low_value,
        "high_value": high_value,
        "anchors": anchors,
        "anchor_count": len(anchors),
        "spread_pct": spread_pct,
        "confidence": confidence,
        "fipe": fipe_info,
        "local_stats": local_stats,
        "building_records": building_count,
        "old_value": old_value,
    }



def monthly_series(
    bairro: str | None,
    tipo: str | None,
    date_start,
    date_end,
) -> pd.DataFrame:
    where = [
        "data_quitacao BETWEEN ? AND ?",
        f"{REFERENCE_M2_SQL} BETWEEN 300 AND 100000",
    ]
    params: list[object] = [date_start, date_end]

    if bairro:
        where.append("bairro = ?")
        params.append(bairro)

    if tipo:
        where.append("tipo_construtivo = ?")
        params.append(tipo)

    with connect_read_only() as con:
        return con.execute(
            f"""
            SELECT DATE_TRUNC('month', data_quitacao) AS mes,
                   COUNT(*) AS transacoes,
                   MEDIAN({REFERENCE_M2_SQL}) AS mediana_m2
            FROM transactions
            WHERE {' AND '.join(where)}
            GROUP BY 1
            ORDER BY 1
            """,
            params,
        ).fetchdf()


st.markdown(
    """
    <div class="brand">
      <div class="brand-name">Quanto Vale BH</div>
      <div class="brand-title">Consulte transações imobiliárias declaradas em Belo Horizonte.</div>
      <div class="brand-subtitle">
        Pesquise por rua ou bairro, compare transações e acompanhe valores de referência com dados públicos da PBH.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

metadata = load_metadata()
if (
    not database_exists()
    or metadata.get("registros", metadata.get("registros_unicos", 0)) < 1000
):
    st.info("Preparando os dados públicos da PBH. Na primeira abertura, isso pode levar alguns instantes.")
    run_update(include_historical=False)
    st.stop()

metadata = load_metadata()
dimensions = get_dimensions(DB_PATH.stat().st_mtime)
fipe_series = get_fipezap_series(
    FIPEZAP_BH_PATH.stat().st_mtime
    if FIPEZAP_BH_PATH.exists()
    else 0.0
)
fipe_latest_date = (
    pd.Timestamp(fipe_series["data"].max())
    if not fipe_series.empty
    else None
)

requested_screen = st.session_state.pop("_go_screen", None)
if requested_screen is not None:
    st.session_state.pop("screen_nav", None)

requested_valuation_mode = st.session_state.pop("_go_valuation_mode", None)
if requested_valuation_mode is not None:
    st.session_state.pop("valuation_mode_nav", None)

screen = st.segmented_control(
    "Navegação",
    ["Avaliar", "Transações", "Mercado", "Sobre"],
    default=requested_screen or "Avaliar",
    label_visibility="collapsed",
    key="screen_nav",
)
st.markdown(
    f'<div class="data-note">Base pública da PBH · {number_br(metadata.get("registros", metadata.get("registros_unicos")))} transações disponíveis · atualizada até {data_limit_label(metadata.get("data_final"))}</div>',
    unsafe_allow_html=True,
)

if screen == "Avaliar":
    st.subheader("Avaliar um imóvel")
    st.markdown(
        '<div class="section-intro">Escolha como você quer chegar à referência de valor.</div>',
        unsafe_allow_html=True,
    )

    valuation_mode = st.segmented_control(
        "Método de avaliação",
        ["Comparáveis recentes", "Atualizar valor antigo"],
        default=requested_valuation_mode or "Comparáveis recentes",
        label_visibility="collapsed",
        key="valuation_mode_nav",
    )

    if valuation_mode == "Comparáveis recentes":
        st.caption(
            "Use esta opção para estimar o imóvel com base em transações semelhantes recentes."
        )
        st.info(
            "A área usada pelo aplicativo é a **área construída cadastrada na base da PBH**. "
            "Ela pode incluir proporcionalmente áreas comuns e garagem e não corresponde necessariamente à área privativa anunciada. "
            "Se você encontrar uma transação do próprio imóvel na aba **Transações**, use o botão **Avaliar este imóvel** para carregar os dados cadastrais automaticamente."
        )

        with st.form("avaliacao"):
            bairro = st.selectbox(
                "Bairro",
                dimensions["bairros"],
                index=None,
                placeholder="Selecione o bairro",
            )
            rua = st.text_input(
                "Rua (opcional)",
                placeholder="Ex.: Rua Angra",
                help=(
                    "Quando informada, o app tenta primeiro formar a amostra "
                    "com imóveis da mesma rua. Se houver poucos registros, "
                    "amplia a busca para o bairro."
                ),
            )
            tipo = st.selectbox(
                "Tipo de imóvel",
                dimensions["tipos"],
                index=None,
                format_func=lambda code: TYPE_LABELS.get(code, code),
                placeholder="Selecione o tipo",
            )
            area = st.number_input(
                "Área construída cadastrada na PBH (m²)",
                min_value=10.0,
                max_value=10000.0,
                value=90.0,
                step=5.0,
                help=(
                    "Não use automaticamente a área privativa de anúncio. "
                    "O filtro deve ser comparado com a área cadastral utilizada na base municipal."
                ),
            )
            padrao = st.selectbox(
                "Padrão de acabamento (opcional)",
                dimensions["padroes"],
                index=None,
                placeholder="Selecione, se souber",
                help=(
                    "Quando informado, o app prioriza transações do mesmo "
                    "padrão de acabamento."
                ),
            )
            current_year = pd.Timestamp.today().year
            ano = st.number_input(
                "Ano de construção (opcional)",
                min_value=1800,
                max_value=current_year,
                value=None,
                step=1,
                format="%d",
                placeholder="Ex.: 2000",
                help="Deixe em branco se não souber.",
            )
            submitted = st.form_submit_button(
                "Ver imóveis comparáveis",
                type="primary",
                width="stretch",
            )

        if submitted:
            if not bairro or not tipo:
                st.warning("Selecione o bairro e o tipo de imóvel.")
            else:
                comparables, stats = valuation_query(
                    bairro=bairro,
                    tipo=tipo,
                    area=float(area),
                    ano=int(ano) if ano is not None else None,
                    padrao=padrao,
                    rua=rua,
                    end_date=dimensions["max_date"],
                )
                if comparables.empty:
                    st.warning(
                        "Não encontrei transações comparáveis suficientes "
                        "para esse perfil na base atual."
                    )
                else:
                    st.session_state["last_comparables"] = comparables
                    st.session_state["last_valuation"] = stats
                    st.session_state["last_subject"] = {
                        "bairro": bairro,
                        "rua": rua.strip() if rua else None,
                        "tipo": tipo,
                        "area": float(area),
                        "padrao": padrao,
                        "ano": int(ano) if ano is not None else None,
                        "source_transaction": None,
                    }

        if "last_valuation" in st.session_state:
            stats = st.session_state["last_valuation"]
            comparables = st.session_state["last_comparables"]
            subject = st.session_state["last_subject"]

            st.markdown("---")
            if subject.get("source_transaction"):
                st.success(
                    "Dados cadastrais carregados diretamente de uma transação da base da PBH."
                )

            st.markdown(
                f"""
                <div class="result-box">
                  <div class="result-title">Faixa observada entre imóveis comparáveis</div>
                  <div class="result-value">{brl(stats['low_value'])} a {brl(stats['high_value'])}</div>
                  <div class="muted">Referência central: {brl(stats['estimated'])} · mediana de {brl(stats['median_m2'], 2)}/m² cadastral equivalente em {data_limit_label(stats.get('reference_date'))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            c1, c2 = st.columns(2)
            c1.metric(
                "Imóveis comparáveis",
                number_br(stats["records"]),
            )
            c2.metric(
                "Período considerado",
                f"{stats.get('months', '—')} meses",
            )

            location_text = (
                f", {subject['rua']}"
                if subject.get("rua")
                else ""
            )
            year_text = (
                f", construção {subject['ano']}"
                if subject.get("ano")
                else ""
            )
            st.caption(
                f"Perfil pesquisado: "
                f"{TYPE_LABELS.get(subject['tipo'], subject['tipo'])}, "
                f"{number_br(subject['area'], 1)} m² de área cadastral PBH, "
                f"{subject['bairro']}{location_text}"
                f"{f', padrão {subject['padrao']}' if subject.get('padrao') else ''}"
                f"{year_text}. "
                f"A faixa usa o valor de referência por m² cadastral em equivalente de {data_limit_label(stats.get('reference_date'))}."
            )

            if subject.get("rua"):
                if stats.get("location_level") == "street":
                    st.info(
                        f"A amostra foi formada com transações encontradas "
                        f"na mesma rua informada ({subject['rua']})."
                    )
                else:
                    st.info(
                        f"A rua {subject['rua']} foi priorizada, mas havia "
                        "poucos registros comparáveis; a amostra precisou "
                        "ser ampliada para o bairro."
                    )

            if subject.get("padrao"):
                if stats.get("strict_pattern"):
                    st.info(
                        f"Os comparáveis usados são do mesmo padrão de "
                        f"acabamento ({subject['padrao']})."
                    )
                else:
                    st.info(
                        f"O padrão {subject['padrao']} foi priorizado, mas "
                        "a amostra precisou incluir outros padrões."
                    )

            if stats.get("time_adjusted"):
                st.info(
                    f"Para apartamentos, comparáveis de meses anteriores foram atualizados temporalmente pelo FipeZAP BH até {data_limit_label(stats.get('reference_date'))} antes do cálculo da mediana."
                )
            st.caption(
                "Valor de referência = maior valor entre o declarado e a base de cálculo da PBH. "
                "A estimativa é estatística e não substitui laudo técnico."
            )

            with st.expander("Como a faixa de referência é calculada?"):
                st.write(
                    "O app usa o maior valor entre o valor declarado e a base de cálculo da PBH como **valor de referência**. "
                    "Depois seleciona transações do mesmo tipo de imóvel, priorizando rua, área cadastral semelhante, recência, "
                    "ano de construção e padrão de acabamento. A busca não ultrapassa 36 meses. Para apartamentos, os comparáveis "
                    "são trazidos a equivalente temporal atual pelo FipeZAP BH antes do cálculo. A faixa usa o intervalo central "
                    "do valor por m² cadastral equivalente e reduz o peso de valores extremos."
                )

            st.subheader("Imóveis usados como referência")
            for _, row in comparables.head(10).iterrows():
                with st.container(border=True):
                    address_header(
                        row["endereco"],
                        row["bairro"],
                        row["data_quitacao"],
                        TYPE_LABELS.get(
                            row["tipo_construtivo"],
                            row["tipo_descricao"],
                        ),
                    )
                    c1, c2 = st.columns(2)
                    c1.metric(
                        "Equivalente atual",
                        brl(row["valor_equivalente_atual"]),
                    )
                    c2.metric(
                        "Por m² cadastral atual",
                        brl(row["valor_m2_equivalente_atual"], 2),
                    )
                    st.markdown(
                        f'<div class="record-detail">'
                        f'Referência na data: {brl(row["valor_referencia"])} · '
                        f'Declarado: {brl(row["valor_declarado"])} · '
                        f'Base PBH: {brl(row["valor_base_calculo"])} · '
                        f'Área cadastral PBH: {number_br(row["area_construida"], 2)} m² · '
                        f'Padrão: {html.escape(text_or_na(row["padrao_acabamento"]))}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    else:
        st.caption(
            "Use esta opção quando existe uma compra ou um valor antigo conhecido para o imóvel."
        )
        st.info(
            "A metodologia agora cruza referências complementares. Para apartamentos, o app usa o FipeZAP BH como âncora temporal, "
            "compara o imóvel com transações recentes da PBH e, quando encontra negócios do mesmo endereço, atualiza essas transações pelo FipeZAP."
        )

        old_source_mode = st.segmented_control(
            "Origem do valor antigo",
            ["Buscar transação na base", "Informar manualmente"],
            default="Buscar transação na base",
            label_visibility="collapsed",
            key="old_source_mode",
        )

        has_history = (
            metadata.get("escopo") == "historico_completo"
            or pd.Timestamp(dimensions["min_date"])
            <= pd.Timestamp("2010-01-01")
        )

        if old_source_mode == "Buscar transação na base":
            if not has_history:
                st.info(
                    "Para localizar compras antigas, o app precisa carregar o histórico completo do ITBI desde 2008."
                )
                if st.button(
                    "Ativar histórico completo para esta análise",
                    type="primary",
                    width="stretch",
                ):
                    run_update(include_historical=True)
                st.stop()

            st.success(
                "Opção recomendada: área cadastral, padrão, ano, tipo e valor de referência são carregados diretamente da transação."
            )

            with st.form("buscar_transacao_antiga"):
                old_search_text = st.text_input(
                    "Endereço ou rua",
                    placeholder="Ex.: Rua Angra 123",
                )
                old_search_bairro = st.selectbox(
                    "Bairro (opcional)",
                    [None] + dimensions["bairros"],
                    format_func=(
                        lambda x: "Todos os bairros"
                        if x is None
                        else x
                    ),
                )
                old_search_submitted = st.form_submit_button(
                    "Buscar transações antigas",
                    type="primary",
                    width="stretch",
                )

            if old_search_submitted:
                if not old_search_text and not old_search_bairro:
                    st.warning(
                        "Informe pelo menos o endereço, a rua ou o bairro."
                    )
                else:
                    st.session_state["old_search_results"] = (
                        search_transactions_for_valuation(
                            text=old_search_text,
                            bairro=old_search_bairro,
                            date_start=dimensions["min_date"],
                            date_end=dimensions["max_date"],
                        )
                    )

            old_results = st.session_state.get(
                "old_search_results",
                pd.DataFrame(),
            )

            if not old_results.empty:
                st.subheader("Selecione a transação de referência")
                st.caption(
                    f"{number_br(len(old_results))} registros encontrados."
                )

                for _, row in old_results.head(30).iterrows():
                    record_key = str(row["registro_id"])
                    with st.container(border=True):
                        address_header(
                            row["endereco"],
                            row["bairro"],
                            row["data_quitacao"],
                            row["tipo_descricao"],
                        )
                        c1, c2 = st.columns(2)
                        c1.metric(
                            "Valor de referência",
                            brl(row["valor_referencia"]),
                        )
                        c2.metric(
                            "Por m² cadastral",
                            brl(row["valor_m2_referencia"], 2),
                        )
                        st.markdown(
                            f'<div class="record-detail">'
                            f'Declarado: {brl(row["valor_declarado"])} · '
                            f'Base PBH: {brl(row["valor_base_calculo"])} · '
                            f'Área cadastral PBH: {number_br(row["area_construida"], 2)} m² · '
                            f'Padrão: {html.escape(text_or_na(row["padrao_acabamento"]))} · '
                            f'Ano: {number_br(row["ano_construcao"]) if pd.notna(row["ano_construcao"]) else "não informado"}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        if st.button(
                            "Estimar valor atual deste imóvel",
                            key=f"hybrid_update_{record_key}",
                            type="primary",
                            width="stretch",
                        ):
                            local_rows, building_rows, hybrid_stats = (
                                hybrid_value_update_query(
                                    old_value=float(row["valor_referencia"]),
                                    purchase_date=row["data_quitacao"],
                                    bairro=row["bairro"],
                                    tipo=row["tipo_construtivo"],
                                    area=float(row["area_construida"]),
                                    ano=(
                                        int(row["ano_construcao"])
                                        if pd.notna(row["ano_construcao"])
                                        else None
                                    ),
                                    padrao=(
                                        row["padrao_acabamento"]
                                        if pd.notna(row["padrao_acabamento"])
                                        else None
                                    ),
                                    rua=street_from_address(row["endereco"]),
                                    end_date=dimensions["max_date"],
                                    source_address=row["endereco"],
                                    source_registro_id=row["registro_id"],
                                )
                            )

                            if not hybrid_stats:
                                st.warning(
                                    "Não foi possível formar referências suficientes para este imóvel."
                                )
                            else:
                                st.session_state["hybrid_local"] = local_rows
                                st.session_state["hybrid_building"] = building_rows
                                st.session_state["hybrid_stats"] = hybrid_stats
                                st.session_state["hybrid_subject"] = {
                                    "old_value": float(row["valor_referencia"]),
                                    "purchase_date": row["data_quitacao"],
                                    "bairro": row["bairro"],
                                    "rua": street_from_address(row["endereco"]),
                                    "tipo": row["tipo_construtivo"],
                                    "area": float(row["area_construida"]),
                                    "padrao": (
                                        row["padrao_acabamento"]
                                        if pd.notna(row["padrao_acabamento"])
                                        else None
                                    ),
                                    "ano": (
                                        int(row["ano_construcao"])
                                        if pd.notna(row["ano_construcao"])
                                        else None
                                    ),
                                    "source_transaction": True,
                                    "source_address": row["endereco"],
                                }
                                st.rerun()

        else:
            st.warning(
                "No preenchimento manual, use **área cadastrada na PBH**, não a área privativa de anúncio."
            )

            default_purchase = max(
                pd.Timestamp(dimensions["min_date"]),
                pd.Timestamp(dimensions["max_date"])
                - pd.DateOffset(years=5),
            ).date()

            with st.form("valor_antigo_hibrido"):
                old_value = st.number_input(
                    "Valor antigo conhecido (R$)",
                    min_value=1000.0,
                    max_value=1000000000.0,
                    value=450000.0,
                    step=10000.0,
                    help=(
                        "Se a origem for uma transação do ITBI, use o maior entre "
                        "o valor declarado e a base de cálculo da PBH."
                    ),
                )
                purchase_date = st.date_input(
                    "Data aproximada da compra ou do valor conhecido",
                    value=default_purchase,
                    min_value=dimensions["min_date"],
                    max_value=dimensions["max_date"],
                )
                bairro_old = st.selectbox(
                    "Bairro",
                    dimensions["bairros"],
                    index=None,
                    placeholder="Selecione o bairro",
                    key="hybrid_bairro",
                )
                rua_old = st.text_input(
                    "Rua (opcional)",
                    placeholder="Ex.: Rua Angra",
                    key="hybrid_rua",
                )
                tipo_old = st.selectbox(
                    "Tipo de imóvel",
                    dimensions["tipos"],
                    index=None,
                    format_func=(
                        lambda code: TYPE_LABELS.get(code, code)
                    ),
                    placeholder="Selecione o tipo",
                    key="hybrid_tipo",
                )
                area_old = st.number_input(
                    "Área construída cadastrada na PBH (m²)",
                    min_value=10.0,
                    max_value=10000.0,
                    value=90.0,
                    step=5.0,
                    key="hybrid_area",
                )
                padrao_old = st.selectbox(
                    "Padrão de acabamento (opcional)",
                    dimensions["padroes"],
                    index=None,
                    placeholder="Selecione, se souber",
                    key="hybrid_padrao",
                )
                ano_old = st.number_input(
                    "Ano de construção (opcional)",
                    min_value=1800,
                    max_value=pd.Timestamp.today().year,
                    value=None,
                    step=1,
                    format="%d",
                    placeholder="Ex.: 2000",
                    key="hybrid_ano",
                )
                hybrid_submitted = st.form_submit_button(
                    "Calcular estimativa híbrida",
                    type="primary",
                    width="stretch",
                )

            if hybrid_submitted:
                validation_error = None
                if not bairro_old or not tipo_old:
                    validation_error = (
                        "Selecione o bairro e o tipo de imóvel."
                    )
                elif (
                    ano_old is not None
                    and int(ano_old)
                    > pd.Timestamp(purchase_date).year
                ):
                    validation_error = (
                        "O ano de construção não pode ser posterior "
                        "à data de referência."
                    )

                if validation_error:
                    st.warning(validation_error)
                else:
                    local_rows, building_rows, hybrid_stats = (
                        hybrid_value_update_query(
                            old_value=float(old_value),
                            purchase_date=purchase_date,
                            bairro=bairro_old,
                            tipo=tipo_old,
                            area=float(area_old),
                            ano=(
                                int(ano_old)
                                if ano_old is not None
                                else None
                            ),
                            padrao=padrao_old,
                            rua=rua_old,
                            end_date=dimensions["max_date"],
                        )
                    )

                    if not hybrid_stats:
                        st.warning(
                            "Não foi possível formar referências suficientes para essa combinação."
                        )
                    else:
                        st.session_state["hybrid_local"] = local_rows
                        st.session_state["hybrid_building"] = building_rows
                        st.session_state["hybrid_stats"] = hybrid_stats
                        st.session_state["hybrid_subject"] = {
                            "old_value": float(old_value),
                            "purchase_date": purchase_date,
                            "bairro": bairro_old,
                            "rua": (
                                rua_old.strip()
                                if rua_old
                                else None
                            ),
                            "tipo": tipo_old,
                            "area": float(area_old),
                            "padrao": padrao_old,
                            "ano": (
                                int(ano_old)
                                if ano_old is not None
                                else None
                            ),
                            "source_transaction": False,
                        }

        if "hybrid_stats" in st.session_state:
            stats = st.session_state["hybrid_stats"]
            local_rows = st.session_state["hybrid_local"]
            building_rows = st.session_state["hybrid_building"]
            subject = st.session_state["hybrid_subject"]

            st.markdown("---")

            if subject.get("source_transaction"):
                st.success(
                    "A referência histórica foi carregada diretamente da transação selecionada."
                )
                st.caption(
                    f"{short_address(subject.get('source_address'), subject['bairro'])} · "
                    f"{pd.Timestamp(subject['purchase_date']).strftime('%d/%m/%Y')} · "
                    f"valor de referência antigo {brl(subject['old_value'])}."
                )

            st.markdown(
                f"""
                <div class="result-box">
                  <div class="result-title">Estimativa híbrida de valor atual</div>
                  <div class="result-value">{brl(stats['estimated'])}</div>
                  <div class="muted">Referências disponíveis: {brl(stats['low_value'])} a {brl(stats['high_value'])} · confiança {stats['confidence'].lower()}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if stats["spread_pct"] > 30:
                st.warning(
                    f"As referências divergem {stats['spread_pct']:.1f}% entre o menor e o maior valor. "
                    "Isso reduz a confiança da estimativa e merece leitura individual das fontes."
                    .replace(".", ",")
                )

            st.subheader("Referências consideradas")

            anchor_df = pd.DataFrame(stats["anchors"])
            columns = st.columns(len(anchor_df))
            for col, (_, anchor) in zip(columns, anchor_df.iterrows()):
                col.metric(
                    anchor["source"],
                    brl(anchor["value"]),
                )
                col.caption(str(anchor["detail"]))

            fig = px.bar(
                anchor_df,
                x="source",
                y="value",
                text_auto=".3s",
                labels={
                    "source": "Referência",
                    "value": "Valor estimado",
                },
            )
            fig.update_layout(
                yaxis_tickprefix="R$ ",
                margin=dict(l=10, r=10, t=20, b=10),
                showlegend=False,
            )
            st.plotly_chart(fig, width="stretch")

            st.info(
                "O valor central é a **mediana das referências complementares disponíveis**. "
                "Assim, uma referência isolada muito baixa ou muito alta não domina automaticamente o resultado."
            )

            fipe_info = stats.get("fipe")
            if fipe_info is not None:
                growth_text = f"{fipe_info['growth_pct']:+.1f}%".replace(".", ",")
                st.markdown(
                    f"**Âncora temporal FipeZAP BH:** o número-índice passou de "
                    f"{number_br(fipe_info['start_index'], 2)} para {number_br(fipe_info['end_index'], 2)}, "
                    f"uma variação de **{growth_text}**. "
                    f"O valor antigo de {brl(subject['old_value'])} corresponderia a "
                    f"**{brl(subject['old_value'] * fipe_info['factor'])}** pela evolução do índice."
                )
                st.caption(
                    "O FipeZAP é usado como benchmark temporal de anúncios de apartamentos prontos em Belo Horizonte; "
                    "não é tratado como preço efetivo de uma transação específica."
                )
            elif subject["tipo"] != "AP":
                st.warning(
                    "O FipeZAP residencial de venda acompanha apartamentos prontos. "
                    "Por isso, ele não foi usado como âncora temporal para este tipo de imóvel."
                )

            local_stats = stats.get("local_stats") or {}
            if local_stats:
                st.markdown(
                    f"**Comparáveis atuais PBH:** {int(local_stats['records'])} imóveis semelhantes resultaram em "
                    f"referência central de **{brl(local_stats['estimated'])}**."
                )

            if stats.get("building_records", 0) > 0:
                st.markdown(
                    f"**Mesmo endereço:** {stats['building_records']} transação(ões) do edifício foi(ram) "
                    "normalizada(s) para a área cadastral do imóvel e trazida(s) ao período atual pelo FipeZAP."
                )

            with st.expander("Como a metodologia híbrida funciona?"):
                st.write(
                    "O cálculo não preserva automaticamente o desconto ou o ágio existente na compra antiga. "
                    "A primeira referência atualiza o valor antigo pelo FipeZAP BH. "
                    "A segunda mede o nível atual de imóveis comparáveis na base da PBH. "
                    "Quando há negócios do mesmo endereço, cada transação é convertida para um valor equivalente do imóvel analisado "
                    "e atualizada temporalmente pelo FipeZAP. O resultado central é a mediana dessas referências."
                )
                st.caption(
                    "O FipeZAP acompanha preços anunciados de apartamentos prontos. A base PBH contém valores declarados e bases de cálculo do ITBI. "
                    "A combinação é uma referência estatística e não substitui laudo técnico."
                )

            if not local_rows.empty:
                with st.expander("Ver comparáveis recentes da PBH"):
                    for _, row in local_rows.head(10).iterrows():
                        with st.container(border=True):
                            address_header(
                                row["endereco"],
                                row["bairro"],
                                row["data_quitacao"],
                                TYPE_LABELS.get(
                                    row["tipo_construtivo"],
                                    row["tipo_descricao"],
                                ),
                            )
                            c1, c2 = st.columns(2)
                            c1.metric(
                                "Valor de referência",
                                brl(row["valor_referencia"]),
                            )
                            c2.metric(
                                "Por m² cadastral",
                                brl(row["valor_m2_referencia"], 2),
                            )

            if not building_rows.empty:
                with st.expander("Ver transações do mesmo endereço atualizadas"):
                    for _, row in building_rows.sort_values(
                        "data_quitacao",
                        ascending=False,
                    ).head(10).iterrows():
                        with st.container(border=True):
                            address_header(
                                row["endereco"],
                                row["bairro"],
                                row["data_quitacao"],
                                row["tipo_descricao"],
                            )
                            c1, c2 = st.columns(2)
                            c1.metric(
                                "Referência na época",
                                brl(row["valor_referencia"]),
                            )
                            c2.metric(
                                "Equivalente atual",
                                brl(row["valor_equivalente_atual"]),
                            )
                            st.caption(
                                f"Área cadastral PBH: {number_br(row['area_construida'], 2)} m² · "
                                f"fator FipeZAP aplicado: {number_br(row['fator_fipe'], 4)}"
                            )

elif screen == "Transações":
    building_selected = st.session_state.get("building_selected")

    if building_selected:
        building_rows = query_same_building(
            building_selected["endereco"]
        )
        st.subheader("Transações no mesmo endereço")
        st.markdown(
            f'<div class="section-intro">{html.escape(short_address(building_selected["endereco"], building_selected["bairro"]))} · {html.escape(smart_title(building_selected["bairro"]))}</div>',
            unsafe_allow_html=True,
        )
        st.info(
            "A comparação dentro do mesmo endereço reduz parte do problema de diferença entre área privativa e área cadastral, "
            "porque as unidades tendem a estar submetidas à mesma estrutura de áreas comuns do edifício."
        )

        if st.button(
            "← Voltar à pesquisa",
            width="stretch",
        ):
            st.session_state.pop("building_selected", None)
            st.rerun()

        if building_rows.empty:
            st.info(
                "Não encontrei outras transações para esse endereço."
            )
        else:
            st.metric(
                "Transações encontradas no endereço",
                number_br(len(building_rows)),
            )
            for _, row in building_rows.iterrows():
                with st.container(border=True):
                    address_header(
                        row["endereco"],
                        row["bairro"],
                        row["data_quitacao"],
                        row["tipo_descricao"],
                    )
                    c1, c2 = st.columns(2)
                    c1.metric(
                        "Valor de referência",
                        brl(row["valor_referencia"]),
                    )
                    c2.metric(
                        "Por m² cadastral",
                        brl(row["valor_m2_referencia"], 2),
                    )
                    st.markdown(
                        f'<div class="record-detail">'
                        f'Declarado: {brl(row["valor_declarado"])} · '
                        f'Base PBH: {brl(row["valor_base_calculo"])} · '
                        f'Área cadastral PBH: {number_br(row["area_construida"], 2)} m² · '
                        f'Padrão: {html.escape(text_or_na(row["padrao_acabamento"]))} · '
                        f'Ano: {number_br(row["ano_construcao"]) if pd.notna(row["ano_construcao"]) else "não informado"}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    else:
        st.subheader("Pesquisar transações")
        st.markdown(
            '<div class="section-intro">Digite uma rua, um endereço ou um bairro e refine a busca com os filtros abaixo.</div>',
            unsafe_allow_html=True,
        )
        st.info(
            "**Sobre a área:** a área exibida é a área construída cadastrada na base da PBH. "
            "Ela pode incluir proporcionalmente áreas comuns e garagem e não corresponde necessariamente à área privativa usada em anúncios."
        )

        with st.form("consulta"):
            search_text = st.text_input(
                "Rua, endereço ou bairro",
                placeholder=(
                    "Ex.: Rua Campos Elíseos ou Nova Granada"
                ),
            )
            bairros = st.multiselect(
                "Bairro",
                dimensions["bairros"],
                placeholder="Todos os bairros",
            )
            tipos = st.multiselect(
                "Tipo de imóvel",
                dimensions["tipos"],
                format_func=(
                    lambda code: TYPE_LABELS.get(code, code)
                ),
                placeholder="Todos os tipos",
            )
            padroes = st.multiselect(
                "Padrão de acabamento (opcional)",
                dimensions["padroes"],
                placeholder="Todos os padrões",
            )
            default_start = max(
                dimensions["min_date"],
                dimensions["max_date"] - timedelta(days=730),
            )
            dates = st.date_input(
                "Período da transação",
                value=(default_start, dimensions["max_date"]),
                min_value=dimensions["min_date"],
                max_value=dimensions["max_date"],
            )
            st.form_submit_button(
                "Buscar transações",
                type="primary",
                width="stretch",
            )

        date_start, date_end = normalize_date_range(dates)

        result, stats = query_transactions(
            search_text,
            bairros,
            tipos,
            padroes,
            date_start,
            date_end,
        )

        c1, c2, c3 = st.columns(3)
        c1.metric(
            "Transações encontradas",
            number_br(stats["records"]),
        )
        c2.metric(
            "Mediana da referência",
            brl(stats["median_value"]),
        )
        c3.metric(
            "Mediana por m² cadastral",
            brl(stats["median_m2"], 2),
        )

        if result.empty:
            st.info(
                "Nenhuma transação encontrada para esses filtros."
            )
        else:
            shown = min(len(result), 30)
            if stats["records"] > shown:
                st.caption(
                    f"Exibindo as {shown} transações mais recentes de "
                    f"{number_br(stats['records'])} encontradas."
                )

            for _, row in result.head(30).iterrows():
                record_key = str(row["registro_id"])
                with st.container(border=True):
                    address_header(
                        row["endereco"],
                        row["bairro"],
                        row["data_quitacao"],
                        row["tipo_descricao"],
                    )
                    c1, c2 = st.columns(2)
                    c1.metric(
                        "Valor de referência",
                        brl(row["valor_referencia"]),
                    )
                    c2.metric(
                        "Por m² cadastral",
                        brl(row["valor_m2_referencia"], 2),
                    )
                    st.markdown(
                        f'<div class="record-detail">'
                        f'Declarado: {brl(row["valor_declarado"])} · '
                        f'Base PBH: {brl(row["valor_base_calculo"])} · '
                        f'Área cadastral PBH: {number_br(row["area_construida"], 2)} m² · '
                        f'Padrão: {html.escape(text_or_na(row["padrao_acabamento"]))} · '
                        f'Ano: {number_br(row["ano_construcao"]) if pd.notna(row["ano_construcao"]) else "não informado"}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    b1, b2 = st.columns(2)

                    if b1.button(
                        "Avaliar este imóvel",
                        key=f"evaluate_{record_key}",
                        width="stretch",
                    ):
                        comparables, valuation_stats = valuation_query(
                            bairro=row["bairro"],
                            tipo=row["tipo_construtivo"],
                            area=float(row["area_construida"]),
                            ano=(
                                int(row["ano_construcao"])
                                if pd.notna(row["ano_construcao"])
                                else None
                            ),
                            padrao=(
                                row["padrao_acabamento"]
                                if pd.notna(row["padrao_acabamento"])
                                else None
                            ),
                            rua=street_from_address(row["endereco"]),
                            end_date=dimensions["max_date"],
                        )

                        if comparables.empty:
                            st.warning(
                                "Não encontrei comparáveis suficientes "
                                "para avaliar este imóvel."
                            )
                        else:
                            st.session_state["last_comparables"] = comparables
                            st.session_state["last_valuation"] = valuation_stats
                            st.session_state["last_subject"] = {
                                "bairro": row["bairro"],
                                "rua": street_from_address(
                                    row["endereco"]
                                ),
                                "tipo": row["tipo_construtivo"],
                                "area": float(row["area_construida"]),
                                "padrao": (
                                    row["padrao_acabamento"]
                                    if pd.notna(
                                        row["padrao_acabamento"]
                                    )
                                    else None
                                ),
                                "ano": (
                                    int(row["ano_construcao"])
                                    if pd.notna(row["ano_construcao"])
                                    else None
                                ),
                                "source_transaction": True,
                                "source_address": row["endereco"],
                            }
                            st.session_state["_go_screen"] = "Avaliar"
                            st.session_state["_go_valuation_mode"] = (
                                "Comparáveis recentes"
                            )
                            st.rerun()

                    if b2.button(
                        "Ver transações deste endereço",
                        key=f"building_{record_key}",
                        width="stretch",
                    ):
                        st.session_state["building_selected"] = {
                            "endereco": row["endereco"],
                            "bairro": row["bairro"],
                        }
                        st.rerun()

            export_columns = [
                "data_quitacao",
                "endereco",
                "bairro",
                "tipo_descricao",
                "ano_construcao",
                "area_construida",
                "padrao_acabamento",
                "valor_declarado",
                "valor_base_calculo",
                "valor_referencia",
                "valor_m2_referencia",
            ]
            csv = result[export_columns].to_csv(
                index=False,
                sep=";",
                decimal=",",
                encoding="utf-8-sig",
            )
            st.download_button(
                "Baixar até 300 resultados em CSV",
                csv,
                "transacoes_itbi_bh.csv",
                "text/csv",
                width="stretch",
            )

elif screen == "Mercado":
    st.subheader("Acompanhar o mercado")
    st.markdown('<div class="section-intro">Acompanhe a evolução mensal do valor de referência mediano por m² cadastral e do volume de transações.</div>', unsafe_allow_html=True)
    bairro_market = st.selectbox("Bairro", [None] + dimensions["bairros"], format_func=lambda x: "Todos os bairros" if x is None else x)
    market_type_options = [None] + dimensions["tipos"]
    market_default = (
        market_type_options.index("AP")
        if "AP" in market_type_options
        else 0
    )
    tipo_market = st.selectbox(
        "Tipo de imóvel",
        market_type_options,
        index=market_default,
        format_func=lambda x: "Todos os tipos" if x is None else TYPE_LABELS.get(x, x),
    )
    default_start = max(dimensions["min_date"], dimensions["max_date"] - timedelta(days=730))
    series = monthly_series(bairro_market, tipo_market, default_start, dimensions["max_date"])
    if series.empty:
        st.info("Não há dados suficientes para essa combinação.")
    else:
        fig = px.line(series, x="mes", y="mediana_m2", markers=True, labels={"mes": "Mês", "mediana_m2": "Mediana por m² cadastral"})
        fig.update_layout(yaxis_tickprefix="R$ ", hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, width="stretch")
        fig2 = px.bar(series, x="mes", y="transacoes", labels={"mes": "Mês", "transacoes": "Transações"})
        fig2.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig2, width="stretch")
        st.caption("O gráfico usa o valor de referência — maior entre declarado e base PBH — dividido pela área cadastral municipal. O padrão inicial é Apartamento para evitar misturar tipologias muito diferentes; a opção Todos os tipos continua disponível. As medianas reduzem a influência de valores extremos.")

else:
    st.subheader("Sobre os dados")
    st.markdown('<div class="section-intro">Entenda a origem e a leitura das informações apresentadas no aplicativo.</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Transações na base", number_br(metadata.get("registros", metadata.get("registros_unicos"))))
    c2.metric("PBH atualizada até", data_limit_label(metadata.get("data_final")))
    c3.metric("FipeZAP até", data_limit_label(fipe_latest_date))
    st.markdown(
        """
        Os dados vêm do **Portal de Dados Abertos da Prefeitura de Belo Horizonte**.

        **Valor declarado** é o valor informado na transmissão. **Base de cálculo PBH** é o valor considerado pela administração municipal para fins do ITBI.

        Para as análises estatísticas, o app cria um **valor de referência**, definido como o **maior valor entre o declarado e a base de cálculo da PBH**. Esse valor não é apresentado como “valor real comprovado” do imóvel; é uma regra de referência adotada pelo aplicativo para reduzir a subestimação da série quando a base municipal supera o valor declarado.

        **Área cadastrada na PBH:** a área construída exibida na base municipal pode incluir proporcionalmente áreas comuns e garagem e não corresponde necessariamente à área privativa informada em anúncios. Por isso, o app identifica o indicador como **valor por m² cadastral**.

        Na aba **Avaliar**, a forma mais segura de usar a área é localizar uma transação do próprio imóvel na aba **Transações** e tocar em **Avaliar este imóvel**. Assim, área, padrão, ano e tipo são carregados diretamente da base.

        O app possui dois métodos de avaliação: **comparação com transações recentes** e **estimativa híbrida de um valor antigo**. Para apartamentos, a estimativa híbrida confronta a evolução do **FipeZAP Belo Horizonte**, comparáveis atuais da PBH e, quando disponíveis, transações do mesmo endereço trazidas ao período atual. As fontes são complementares: as referências locais também podem usar o FipeZAP apenas para normalização temporal.

        As avaliações são **referências estatísticas** e não substituem laudo técnico.

        **Hospedagem:** no Streamlit Community Cloud, o armazenamento local não tem persistência garantida. Se a instância for recriada, o aplicativo recompõe a base recente automaticamente e pode pedir uma nova carga do histórico completo para pesquisar transações antigas.
        """
    )
    c1, c2 = st.columns(2)
    c1.link_button(
        "Abrir a fonte oficial da PBH",
        "https://dados.pbh.gov.br/dataset/itbi-relatorios",
        width="stretch",
    )
    c2.link_button(
        "Abrir a fonte oficial do FipeZAP",
        FIPEZAP_SOURCE_URL,
        width="stretch",
    )
    with st.expander("Atualização da base"):
        st.caption("Use esta opção quando a PBH publicar novos arquivos mensais.")
        if st.button("Verificar e atualizar dados", type="primary", width="stretch"):
            run_update(
                force=True,
                include_historical=(
                    pd.Timestamp(dimensions["min_date"]) <= pd.Timestamp("2010-01-01")
                ),
            )
        if pd.Timestamp(dimensions["min_date"]) > pd.Timestamp("2010-01-01"):
            st.caption("O histórico completo ainda não está ativo nesta instância.")
            if st.button("Carregar histórico completo desde 2008", width="stretch"):
                run_update(include_historical=True)
    st.markdown(
        """
        **No iPhone:** abra o app no Safari, toque em **Compartilhar** e selecione **Adicionar à Tela de Início**.
        """
    )


st.markdown(
    '<div class="footer-note">Quanto Vale BH · consulta independente baseada em dados públicos da PBH e referência temporal FipeZAP/Fipe.</div>',
    unsafe_allow_html=True,
)
