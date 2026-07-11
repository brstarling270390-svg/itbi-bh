from __future__ import annotations

from datetime import timedelta
import html
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from data_manager import (
    DB_PATH,
    TYPE_LABELS,
    build_demo_database,
    connect_read_only,
    database_exists,
    load_metadata,
    normalize_text,
    update_from_pbh,
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
        progress.progress(1.0, text="Base atualizada.")
        st.success(
            f"Atualização concluída: {metadata.get('registros', metadata.get('registros_unicos', 0)):,} registros, "
            f"até {metadata.get('data_final', 'data não informada')}.".replace(",", ".")
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


def valuation_query(
    bairro: str,
    tipo: str,
    area: float,
    ano: int | None,
    padrao: str | None,
    rua: str | None,
    end_date,
) -> tuple[pd.DataFrame, dict]:
    """Busca comparáveis em camadas, priorizando rua, padrão, área, idade e recência."""
    rua_search = normalize_text(rua)

    scenarios: list[tuple[int, float, int, bool, str]] = []

    # Primeiro tenta formar uma amostra apenas na mesma rua.
    if rua_search:
        if padrao:
            scenarios.append((60, 0.35, 4, True, "street"))
        scenarios.append((120, 0.50, 3, False, "street"))

    # Depois amplia para o bairro, mantendo imóveis da rua no topo do ranking.
    if padrao:
        scenarios.extend([
            (24, 0.20, 8, True, "neighborhood"),
            (36, 0.30, 6, True, "neighborhood"),
            (60, 0.35, 5, True, "neighborhood"),
        ])

    scenarios.extend([
        (36, 0.30, 8, False, "neighborhood"),
        (60, 0.40, 6, False, "neighborhood"),
        (120, 0.50, 4, False, "neighborhood"),
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
                "valor_declarado > 0",
                "valor_m2_declarado BETWEEN 300 AND 100000",
            ]
            params: list[object] = [
                bairro,
                tipo,
                start_date.date(),
                end_date,
                area_min,
                area_max,
            ]

            if padrao and strict_pattern:
                where.append("padrao_acabamento = ?")
                params.append(padrao)

            if rua_search and location_level == "street":
                where.append("endereco_busca LIKE ?")
                params.append(f"%{rua_search}%")

            frame = con.execute(
                f"""
                SELECT data_quitacao, endereco, endereco_busca, bairro,
                       tipo_construtivo, tipo_descricao, ano_construcao,
                       area_construida, padrao_acabamento, valor_declarado,
                       valor_base_calculo, valor_m2_declarado
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
                year_distance = (frame["ano_construcao"].astype("Float64") - ano).abs() / 35.0
                frame["dist_ano"] = year_distance.clip(upper=1.0).fillna(0.18).astype(float)

            if padrao is None:
                frame["penalidade_padrao"] = 0.0
            else:
                frame["penalidade_padrao"] = (
                    frame["padrao_acabamento"].fillna("").ne(padrao).astype(float) * 0.35
                )

            if rua_search:
                same_street = frame["endereco_busca"].fillna("").str.contains(
                    rua_search, regex=False
                )
                frame["penalidade_local"] = (~same_street).astype(float) * 0.45
            else:
                frame["penalidade_local"] = 0.0

            frame["score"] = (
                frame["dist_area"]
                + frame["dist_ano"]
                + frame["penalidade_padrao"]
                + frame["penalidade_local"]
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

    if frame.empty:
        return frame, {}

    frame = frame.head(30).copy()
    q1 = frame["valor_m2_declarado"].quantile(0.25)
    q3 = frame["valor_m2_declarado"].quantile(0.75)
    iqr = q3 - q1
    if pd.notna(iqr) and iqr > 0:
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        trimmed = frame[frame["valor_m2_declarado"].between(low, high)].copy()
        if len(trimmed) >= 4:
            frame = trimmed

    median_m2 = float(frame["valor_m2_declarado"].median())
    q25_m2 = float(frame["valor_m2_declarado"].quantile(0.25))
    q75_m2 = float(frame["valor_m2_declarado"].quantile(0.75))
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
        **(chosen or {}),
    }
    return frame, stats


def query_transactions(
    text: str, bairros: list[str], tipos: list[str], padroes: list[str],
    date_start, date_end, limit: int = 300
) -> tuple[pd.DataFrame, dict]:
    where = ["data_quitacao BETWEEN ? AND ?"]
    params: list[object] = [date_start, date_end]
    if text:
        terms = [normalize_text(term) for term in text.split() if normalize_text(term)]
        for term in terms:
            where.append("(endereco_busca LIKE ? OR bairro_busca LIKE ?)")
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
            SELECT COUNT(*), MEDIAN(valor_declarado),
                   MEDIAN(valor_m2_declarado) FILTER (WHERE valor_m2_declarado BETWEEN 300 AND 100000)
            FROM transactions WHERE {clause}
            """,
            params,
        ).fetchone()
        frame = con.execute(
            f"""
            SELECT data_quitacao, endereco, bairro, tipo_descricao, ano_construcao,
                   area_construida, padrao_acabamento, valor_declarado,
                   valor_base_calculo, valor_m2_declarado
            FROM transactions
            WHERE {clause}
            ORDER BY data_quitacao DESC, valor_declarado DESC NULLS LAST
            LIMIT {int(limit)}
            """,
            params,
        ).fetchdf()
    return frame, {"records": stats_row[0] or 0, "median_value": stats_row[1], "median_m2": stats_row[2]}


def monthly_series(bairro: str | None, tipo: str | None, date_start, date_end) -> pd.DataFrame:
    where = ["data_quitacao BETWEEN ? AND ?", "valor_m2_declarado BETWEEN 300 AND 100000"]
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
                   MEDIAN(valor_m2_declarado) AS mediana_m2
            FROM transactions
            WHERE {' AND '.join(where)}
            GROUP BY 1 ORDER BY 1
            """,
            params,
        ).fetchdf()


st.markdown(
    """
    <div class="brand">
      <div class="brand-name">Quanto Vale BH</div>
      <div class="brand-title">Consulte transações imobiliárias declaradas em Belo Horizonte.</div>
      <div class="brand-subtitle">
        Pesquise por rua ou bairro, encontre imóveis comparáveis e acompanhe valores por m² com dados públicos da PBH.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not database_exists():
    st.info("Preparando os dados públicos da PBH. Na primeira abertura, isso pode levar alguns instantes.")
    run_update(include_historical=False)
    st.stop()

metadata = load_metadata()
dimensions = get_dimensions(DB_PATH.stat().st_mtime)

screen = st.segmented_control(
    "Navegação",
    ["Avaliar", "Transações", "Mercado", "Sobre"],
    default="Avaliar",
    label_visibility="collapsed",
)
st.markdown(
    f'<div class="data-note">Base pública da PBH · {number_br(metadata.get("registros", metadata.get("registros_unicos")))} transações disponíveis · atualizada até {data_limit_label(metadata.get("data_final"))}</div>',
    unsafe_allow_html=True,
)

if screen == "Avaliar":
    st.subheader("Avaliar um imóvel")
    st.markdown('<div class="section-intro">Informe as características principais. O app busca transações semelhantes e apresenta uma faixa de referência.</div>', unsafe_allow_html=True)
    with st.form("avaliacao"):
        bairro = st.selectbox("Bairro", dimensions["bairros"], index=None, placeholder="Selecione o bairro")
        rua = st.text_input(
            "Rua (opcional)",
            placeholder="Ex.: Rua Angra",
            help="Quando informada, o app tenta primeiro formar a amostra com imóveis da mesma rua. Se houver poucos registros, amplia a busca para o bairro.",
        )
        tipo = st.selectbox(
            "Tipo de imóvel",
            dimensions["tipos"],
            index=None,
            format_func=lambda code: TYPE_LABELS.get(code, code),
            placeholder="Selecione o tipo",
        )
        area = st.number_input("Área do imóvel (m²)", min_value=10.0, max_value=10000.0, value=90.0, step=5.0)
        padrao = st.selectbox(
            "Padrão de acabamento (opcional)",
            dimensions["padroes"],
            index=None,
            placeholder="Selecione, se souber",
            help="Quando informado, o app prioriza transações do mesmo padrão de acabamento. Isso tende a melhorar a comparabilidade.",
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
        submitted = st.form_submit_button("Ver imóveis comparáveis", type="primary", width="stretch")

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
                st.warning("Não encontrei transações comparáveis suficientes para esse perfil na base atual.")
            else:
                st.session_state["last_comparables"] = comparables
                st.session_state["last_valuation"] = stats
                st.session_state["last_subject"] = {
                    "bairro": bairro,
                    "rua": rua.strip() if rua else None,
                    "tipo": tipo,
                    "area": area,
                    "padrao": padrao,
                    "ano": int(ano) if ano is not None else None,
                }

    if "last_valuation" in st.session_state:
        stats = st.session_state["last_valuation"]
        comparables = st.session_state["last_comparables"]
        subject = st.session_state["last_subject"]
        st.markdown("---")
        st.markdown(
            f"""
            <div class="result-box">
              <div class="result-title">Faixa observada entre imóveis comparáveis</div>
              <div class="result-value">{brl(stats['low_value'])} a {brl(stats['high_value'])}</div>
              <div class="muted">Referência central: {brl(stats['estimated'])} · mediana de {brl(stats['median_m2'], 2)}/m²</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        c1.metric("Imóveis comparáveis", number_br(stats["records"]))
        c2.metric("Período considerado", f"{stats.get('months', '—')} meses")
        location_text = f", {subject['rua']}" if subject.get("rua") else ""
        year_text = f", construção {subject['ano']}" if subject.get("ano") else ""
        st.caption(
            f"Perfil pesquisado: {TYPE_LABELS.get(subject['tipo'], subject['tipo'])}, "
            f"{number_br(subject['area'], 1)} m², {subject['bairro']}{location_text}"
            f"{f', padrão {subject['padrao']}' if subject.get('padrao') else ''}{year_text}. "
            f"A faixa é baseada no intervalo central dos valores por m² das transações mais semelhantes."
        )
        if subject.get("rua"):
            if stats.get("location_level") == "street":
                st.info(f"A amostra foi formada com transações encontradas na mesma rua informada ({subject['rua']}).")
            else:
                st.info(
                    f"A rua {subject['rua']} foi priorizada, mas havia poucos registros comparáveis; "
                    "por isso, a amostra precisou ser ampliada para o restante do bairro."
                )
        if subject.get("padrao"):
            if stats.get("strict_pattern"):
                st.info(f"Os comparáveis usados nesta estimativa são do mesmo padrão de acabamento ({subject['padrao']}).")
            else:
                st.info(f"O padrão {subject['padrao']} foi priorizado, mas a amostra precisou ser ampliada para padrões diferentes por falta de registros suficientes.")
        st.caption("Referência estatística baseada em valores declarados ao ITBI. Não substitui laudo técnico de avaliação.")

        with st.expander("Como a faixa de referência é calculada?"):
            st.write(
                "O app seleciona transações do mesmo tipo de imóvel. Quando uma rua é informada, tenta primeiro formar a amostra na própria rua; "
                "se não houver registros suficientes, amplia para o bairro e mantém os imóveis da rua com prioridade no ranking. "
                "Também considera área, recência, ano de construção e padrão de acabamento. A faixa usa o intervalo central dos valores por m², "
                "reduzindo o peso de valores extremos."
            )

        st.subheader("Imóveis usados como referência")
        for _, row in comparables.head(10).iterrows():
            with st.container(border=True):
                address_header(
                    row["endereco"],
                    row["bairro"],
                    row["data_quitacao"],
                    TYPE_LABELS.get(row["tipo_construtivo"], row["tipo_descricao"]),
                )
                st.markdown(
                    f'<div class="record-detail">{number_br(row["area_construida"], 1)} m² · Padrão {html.escape(text_or_na(row["padrao_acabamento"]))}</div>',
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns(2)
                c1.metric("Valor declarado", brl(row["valor_declarado"]))
                c2.metric("Valor por m²", brl(row["valor_m2_declarado"], 2))

elif screen == "Transações":
    st.subheader("Pesquisar transações")
    st.markdown('<div class="section-intro">Digite uma rua, um endereço ou um bairro e refine a busca com os filtros abaixo.</div>', unsafe_allow_html=True)
    with st.form("consulta"):
        text = st.text_input("Rua, endereço ou bairro", placeholder="Ex.: Rua Campos Elíseos ou Nova Granada")
        bairros = st.multiselect("Bairro", dimensions["bairros"], placeholder="Todos os bairros")
        tipos = st.multiselect(
            "Tipo de imóvel",
            dimensions["tipos"],
            format_func=lambda code: TYPE_LABELS.get(code, code),
            placeholder="Todos os tipos",
        )
        padroes = st.multiselect(
            "Padrão de acabamento (opcional)",
            dimensions["padroes"],
            placeholder="Todos os padrões",
        )
        default_start = max(dimensions["min_date"], dimensions["max_date"] - timedelta(days=730))
        dates = st.date_input(
            "Período da transação",
            value=(default_start, dimensions["max_date"]),
            min_value=dimensions["min_date"],
            max_value=dimensions["max_date"],
        )
        st.form_submit_button("Buscar transações", type="primary", width="stretch")
    date_start, date_end = dates if isinstance(dates, tuple) and len(dates) == 2 else (dates, dates)
    result, stats = query_transactions(text, bairros, tipos, padroes, date_start, date_end)
    c1, c2, c3 = st.columns(3)
    c1.metric("Transações encontradas", number_br(stats["records"]))
    c2.metric("Mediana do valor", brl(stats["median_value"]))
    c3.metric("Mediana por m²", brl(stats["median_m2"], 2))
    if result.empty:
        st.info("Nenhuma transação encontrada para esses filtros.")
    else:
        shown = min(len(result), 30)
        if stats["records"] > shown:
            st.caption(f"Exibindo as {shown} transações mais recentes de {number_br(stats['records'])} encontradas.")
        for _, row in result.head(30).iterrows():
            with st.container(border=True):
                address_header(row["endereco"], row["bairro"], row["data_quitacao"], row["tipo_descricao"])
                c1, c2 = st.columns(2)
                c1.metric("Valor declarado", brl(row["valor_declarado"]))
                c2.metric("Valor por m²", brl(row["valor_m2_declarado"], 2))
                st.markdown(
                    f'<div class="record-detail">Área: {number_br(row["area_construida"], 2)} m² · '
                    f'Padrão: {html.escape(text_or_na(row["padrao_acabamento"]))} · '
                    f'Ano: {number_br(row["ano_construcao"]) if pd.notna(row["ano_construcao"]) else "não informado"} · '
                    f'Base de cálculo: {brl(row["valor_base_calculo"])}</div>',
                    unsafe_allow_html=True,
                )
        csv = result.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
        st.download_button("Baixar até 300 resultados em CSV", csv, "transacoes_itbi_bh.csv", "text/csv", width="stretch")

elif screen == "Mercado":
    st.subheader("Acompanhar o mercado")
    st.markdown('<div class="section-intro">Acompanhe a evolução mensal do valor mediano por m² e do volume de transações declaradas.</div>', unsafe_allow_html=True)
    bairro_market = st.selectbox("Bairro", [None] + dimensions["bairros"], format_func=lambda x: "Todos os bairros" if x is None else x)
    tipo_market = st.selectbox(
        "Tipo de imóvel",
        [None] + dimensions["tipos"],
        format_func=lambda x: "Todos os tipos" if x is None else TYPE_LABELS.get(x, x),
    )
    default_start = max(dimensions["min_date"], dimensions["max_date"] - timedelta(days=730))
    series = monthly_series(bairro_market, tipo_market, default_start, dimensions["max_date"])
    if series.empty:
        st.info("Não há dados suficientes para essa combinação.")
    else:
        fig = px.line(series, x="mes", y="mediana_m2", markers=True, labels={"mes": "Mês", "mediana_m2": "Mediana por m²"})
        fig.update_layout(yaxis_tickprefix="R$ ", hovermode="x unified", margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, width="stretch")
        fig2 = px.bar(series, x="mes", y="transacoes", labels={"mes": "Mês", "transacoes": "Transações"})
        fig2.update_layout(margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig2, width="stretch")
        st.caption("Os gráficos usam medianas para reduzir a influência de valores extremos.")

else:
    st.subheader("Sobre os dados")
    st.markdown('<div class="section-intro">Entenda a origem e a leitura das informações apresentadas no aplicativo.</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.metric("Transações na base", number_br(metadata.get("registros", metadata.get("registros_unicos"))))
    c2.metric("Atualizada até", data_limit_label(metadata.get("data_final")))
    st.markdown(
        """
        Os dados vêm do **Portal de Dados Abertos da Prefeitura de Belo Horizonte**.

        **Valor declarado** é o valor da aquisição informado pelo contribuinte. **Base de cálculo** é o valor considerado para tributação pela administração municipal. A base pública não apresenta um campo individual com o valor efetivamente recolhido de ITBI.

        A avaliação apresentada no app é uma **referência estatística** baseada em transações comparáveis. Ela não substitui laudo técnico de avaliação.
        """
    )
    st.link_button("Abrir a fonte oficial da PBH", "https://dados.pbh.gov.br/dataset/itbi-relatorios", width="stretch")
    with st.expander("Atualização da base"):
        st.caption("Use esta opção quando a PBH publicar novos arquivos mensais.")
        if st.button("Verificar e atualizar dados", type="primary", width="stretch"):
            run_update(include_historical=False)
    st.markdown(
        """
        **No iPhone:** abra o app no Safari, toque em **Compartilhar** e selecione **Adicionar à Tela de Início**.
        """
    )


st.markdown(
    '<div class="footer-note">Quanto Vale BH · consulta independente baseada em dados públicos da Prefeitura de Belo Horizonte.</div>',
    unsafe_allow_html=True,
)
