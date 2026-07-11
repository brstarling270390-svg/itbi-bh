from __future__ import annotations

from datetime import timedelta

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
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1100px;}
    [data-testid="stMetricValue"] {font-size: 1.55rem;}
    .hero {padding: .2rem 0 .8rem;}
    .eyebrow {font-size: .78rem; text-transform: uppercase; letter-spacing: .09em; opacity: .62; font-weight: 700;}
    .result-box {padding: 1.15rem 1.2rem; border: 1px solid rgba(128,128,128,.28); border-radius: 1rem; margin: .4rem 0 1rem;}
    .result-title {font-size: .85rem; opacity: .72; margin-bottom: .15rem;}
    .result-value {font-size: 2rem; font-weight: 750; line-height: 1.1;}
    .muted {opacity: .7; font-size: .9rem;}
    @media (max-width: 768px) {
        .block-container {padding: .7rem .8rem 2rem;}
        h1 {font-size: 1.85rem !important; line-height: 1.12 !important;}
        h2 {font-size: 1.35rem !important;}
        [data-testid="stMetricValue"] {font-size: 1.25rem;}
        [data-testid="stHorizontalBlock"] {flex-wrap: wrap;}
        [data-testid="column"] {min-width: 100% !important; width: 100% !important; flex: 1 1 100% !important;}
        button {min-height: 2.9rem;}
        .result-value {font-size: 1.7rem;}
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
    end_date,
) -> tuple[pd.DataFrame, dict]:
    """Busca comparáveis em camadas, priorizando padrão de acabamento quando informado."""
    scenarios = [
        # meses, tolerância de área, mínimo, exigir mesmo padrão
        (24, 0.20, 8, True),
        (36, 0.30, 6, True),
        (60, 0.35, 5, True),
        (36, 0.30, 8, False),
        (60, 0.40, 6, False),
        (120, 0.50, 4, False),
    ]
    chosen = None
    frame = pd.DataFrame()

    with connect_read_only() as con:
        for months, area_tol, minimum, strict_pattern in scenarios:
            start_date = pd.Timestamp(end_date) - pd.DateOffset(months=months)
            area_min = max(area * (1 - area_tol), 1)
            area_max = area * (1 + area_tol)
            pattern_clause = " AND padrao_acabamento = ?" if (padrao and strict_pattern) else ""
            params = [
                area, area, ano, ano, padrao, padrao,
                area, area, ano, ano, padrao, padrao,
                bairro, tipo, start_date.date(), end_date, area_min, area_max,
            ]
            if padrao and strict_pattern:
                params.append(padrao)
            frame = con.execute(
                f"""
                SELECT data_quitacao, endereco, bairro, tipo_construtivo, tipo_descricao,
                       ano_construcao, area_construida, padrao_acabamento,
                       valor_declarado, valor_base_calculo, valor_m2_declarado,
                       ABS(area_construida - ?) / ? AS dist_area,
                       CASE WHEN ? IS NULL OR ano_construcao IS NULL THEN 0.18
                            ELSE LEAST(ABS(ano_construcao - ?) / 35.0, 1.0) END AS dist_ano,
                       CASE WHEN ? IS NULL OR padrao_acabamento = ? THEN 0 ELSE 0.35 END AS penalidade_padrao,
                       (ABS(area_construida - ?) / ?)
                       + CASE WHEN ? IS NULL OR ano_construcao IS NULL THEN 0.18
                              ELSE LEAST(ABS(ano_construcao - ?) / 35.0, 1.0) END
                       + CASE WHEN ? IS NULL OR padrao_acabamento = ? THEN 0 ELSE 0.35 END AS score
                FROM transactions
                WHERE bairro = ?
                  AND tipo_construtivo = ?
                  AND data_quitacao BETWEEN ? AND ?
                  AND area_construida BETWEEN ? AND ?
                  AND valor_declarado > 0
                  AND valor_m2_declarado BETWEEN 300 AND 100000
                  {pattern_clause}
                ORDER BY score, data_quitacao DESC
                LIMIT 80
                """,
                params,
            ).fetchdf()
            if len(frame) >= minimum:
                chosen = {
                    "months": months,
                    "area_tol": area_tol,
                    "minimum": minimum,
                    "strict_pattern": bool(padrao and strict_pattern),
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


st.markdown('<div class="hero"><div class="eyebrow">Dados públicos · Belo Horizonte</div></div>', unsafe_allow_html=True)
st.title("Quanto vale este imóvel?")
st.caption("Use transações declaradas à PBH para encontrar imóveis comparáveis e uma faixa de referência.")

if not database_exists():
    st.info("Na primeira utilização, prepare a base recente da PBH.")
    if st.button("Preparar base recente", type="primary", width="stretch"):
        run_update(include_historical=False)
    with st.expander("Outras opções"):
        if st.button("Preparar histórico completo desde 2008", width="stretch"):
            run_update(include_historical=True)
        if st.button("Abrir demonstração", width="stretch"):
            try:
                build_demo_database()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Não foi possível preparar a demonstração: {exc}")
    st.stop()

metadata = load_metadata()
dimensions = get_dimensions(DB_PATH.stat().st_mtime)

screen = st.segmented_control(
    "Navegação",
    ["Avaliar imóvel", "Explorar transações", "Mercado", "Dados"],
    default="Avaliar imóvel",
    label_visibility="collapsed",
)

if screen == "Avaliar imóvel":
    st.subheader("Descreva o imóvel")
    with st.form("avaliacao"):
        bairro = st.selectbox("Bairro", dimensions["bairros"], index=None, placeholder="Selecione o bairro")
        tipo = st.selectbox(
            "Tipo de imóvel",
            dimensions["tipos"],
            index=None,
            format_func=lambda code: TYPE_LABELS.get(code, code),
            placeholder="Selecione o tipo",
        )
        area = st.number_input("Área construída adquirida (m²)", min_value=10.0, max_value=10000.0, value=90.0, step=5.0)
        padrao = st.selectbox(
            "Padrão de acabamento",
            dimensions["padroes"],
            index=None,
            placeholder="Selecione, se souber",
            help="Quando informado, o app prioriza transações do mesmo padrão de acabamento. Isso tende a melhorar a comparabilidade.",
        )
        st.caption("O padrão de acabamento é usado como critério relevante na seleção dos comparáveis.")
        with st.expander("Informações adicionais"):
            current_year = pd.Timestamp.today().year
            ano_known = st.checkbox("Informar ano de construção")
            ano = st.number_input("Ano de construção", min_value=1800, max_value=current_year, value=2000, step=1, disabled=not ano_known)
        submitted = st.form_submit_button("Encontrar imóveis comparáveis", type="primary", width="stretch")

    if submitted:
        if not bairro or not tipo:
            st.warning("Selecione o bairro e o tipo de imóvel.")
        else:
            comparables, stats = valuation_query(
                bairro=bairro,
                tipo=tipo,
                area=float(area),
                ano=int(ano) if ano_known else None,
                padrao=padrao,
                end_date=dimensions["max_date"],
            )
            if comparables.empty:
                st.warning("Não encontrei transações comparáveis suficientes para esse perfil na base atual.")
            else:
                st.session_state["last_comparables"] = comparables
                st.session_state["last_valuation"] = stats
                st.session_state["last_subject"] = {"bairro": bairro, "tipo": tipo, "area": area, "padrao": padrao}

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
        c1.metric("Comparáveis usados", number_br(stats["records"]))
        c2.metric("Janela analisada", f"{stats.get('months', '—')} meses")
        st.caption(
            f"Perfil pesquisado: {TYPE_LABELS.get(subject['tipo'], subject['tipo'])}, {number_br(subject['area'], 1)} m², {subject['bairro']}"
            f"{f', padrão {subject['padrao']}' if subject.get('padrao') else ''}. "
            f"A faixa é baseada no intervalo central dos valores por m² das transações mais semelhantes."
        )
        if subject.get("padrao"):
            if stats.get("strict_pattern"):
                st.info(f"Os comparáveis usados nesta estimativa são do mesmo padrão de acabamento ({subject['padrao']}).")
            else:
                st.info(f"O padrão {subject['padrao']} foi priorizado, mas a amostra precisou ser ampliada para padrões diferentes por falta de registros suficientes.")
        st.warning("É uma referência estatística baseada em dados declarados ao ITBI. Não é laudo de avaliação nem preço de anúncio.")

        st.subheader("Transações mais semelhantes")
        for _, row in comparables.head(10).iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['endereco']}**")
                st.caption(
                    f"{pd.to_datetime(row['data_quitacao']).strftime('%d/%m/%Y')} · "
                    f"{number_br(row['area_construida'], 1)} m² · "
                    f"{TYPE_LABELS.get(row['tipo_construtivo'], row['tipo_descricao'])} · "
                    f"Padrão {row['padrao_acabamento'] or 'não informado'}"
                )
                c1, c2 = st.columns(2)
                c1.metric("Valor declarado", brl(row["valor_declarado"]))
                c2.metric("Valor por m²", brl(row["valor_m2_declarado"], 2))

elif screen == "Explorar transações":
    st.subheader("Pesquisar registros")
    with st.form("consulta"):
        text = st.text_input("Rua, endereço ou bairro", placeholder="Ex.: Rua Alcântara 399")
        bairros = st.multiselect("Bairro", dimensions["bairros"], placeholder="Todos os bairros")
        tipos = st.multiselect(
            "Tipo de imóvel",
            dimensions["tipos"],
            format_func=lambda code: TYPE_LABELS.get(code, code),
            placeholder="Todos os tipos",
        )
        padroes = st.multiselect(
            "Padrão de acabamento",
            dimensions["padroes"],
            placeholder="Todos os padrões",
        )
        default_start = max(dimensions["min_date"], dimensions["max_date"] - timedelta(days=730))
        dates = st.date_input(
            "Período da quitação",
            value=(default_start, dimensions["max_date"]),
            min_value=dimensions["min_date"],
            max_value=dimensions["max_date"],
        )
        st.form_submit_button("Pesquisar", type="primary", width="stretch")
    date_start, date_end = dates if isinstance(dates, tuple) and len(dates) == 2 else (dates, dates)
    result, stats = query_transactions(text, bairros, tipos, padroes, date_start, date_end)
    c1, c2, c3 = st.columns(3)
    c1.metric("Transações", number_br(stats["records"]))
    c2.metric("Mediana do valor", brl(stats["median_value"]))
    c3.metric("Mediana por m²", brl(stats["median_m2"], 2))
    if result.empty:
        st.info("Nenhuma transação encontrada.")
    else:
        for _, row in result.head(30).iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['endereco']}**")
                st.caption(f"{row['bairro']} · {pd.to_datetime(row['data_quitacao']).strftime('%d/%m/%Y')} · {row['tipo_descricao']}")
                c1, c2 = st.columns(2)
                c1.metric("Valor declarado", brl(row["valor_declarado"]))
                c2.metric("Valor por m²", brl(row["valor_m2_declarado"], 2))
                st.caption(
                    f"Área: {number_br(row['area_construida'], 2)} m² · "
                    f"Padrão: {row['padrao_acabamento'] or 'não informado'} · "
                    f"Ano: {number_br(row['ano_construcao']) if pd.notna(row['ano_construcao']) else 'não informado'} · "
                    f"Base de cálculo: {brl(row['valor_base_calculo'])}"
                )
        csv = result.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
        st.download_button("Baixar resultados em CSV", csv, "transacoes_itbi_bh.csv", "text/csv", width="stretch")

elif screen == "Mercado":
    st.subheader("Evolução do mercado")
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

else:
    st.subheader("Dados e atualização")
    c1, c2 = st.columns(2)
    c1.metric("Registros", number_br(metadata.get("registros", metadata.get("registros_unicos"))))
    c2.metric("Dados até", metadata.get("data_final") or "—")
    st.caption(f"Escopo: {metadata.get('escopo', 'não informado').replace('_', ' ')}")
    if st.button("Atualizar dados da PBH", type="primary", width="stretch"):
        run_update(include_historical=metadata.get("escopo") == "historico_completo")
    with st.expander("Trocar escopo da base"):
        if st.button("Usar base recente", width="stretch"):
            run_update(include_historical=False)
        if st.button("Usar histórico completo", width="stretch"):
            run_update(include_historical=True)
    st.markdown(
        """
        **Valor declarado** é o valor de aquisição informado pelo contribuinte. **Base de cálculo** é o valor considerado para tributação. A base pública não apresenta um campo individual com o montante efetivamente recolhido de ITBI.

        No iPhone, abra o app no Safari, toque em **Compartilhar** e escolha **Adicionar à Tela de Início**.
        """
    )
    st.link_button("Fonte oficial da PBH", "https://dados.pbh.gov.br/dataset/itbi-relatorios", width="stretch")
