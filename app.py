from __future__ import annotations

import io
from datetime import date, timedelta

import duckdb
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
    page_title="ITBI BH — Consulta de Transações",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 3rem; max-width: 1280px;}
    [data-testid="stMetricValue"] {font-size: 1.45rem;}
    .small-note {font-size: .88rem; color: #5d6672;}
    .source-box {padding: .85rem 1rem; border: 1px solid #d9dee5; border-radius: .6rem; background: #f8fafc;}
    @media (max-width: 768px) {
        .block-container {padding: .65rem .75rem 2rem;}
        h1 {font-size: 1.65rem !important; line-height: 1.15 !important;}
        h2 {font-size: 1.35rem !important;}
        [data-testid="stMetricValue"] {font-size: 1.25rem;}
        [data-testid="stHorizontalBlock"] {flex-wrap: wrap;}
        [data-testid="column"] {min-width: 100% !important; width: 100% !important; flex: 1 1 100% !important;}
        button {min-height: 2.7rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def brl(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return "R$ " + f"{float(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brl2(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return "R$ " + f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def number_br(value: float | int | None, decimals: int = 0) -> str:
    if value is None or pd.isna(value):
        return "—"
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def display_text(value: object, fallback: str = "—") -> str:
    if value is None or pd.isna(value):
        return fallback
    text = str(value).strip()
    return text or fallback


def run_update(force: bool = False, include_historical: bool = False) -> None:
    progress = st.progress(0, text="Iniciando atualização...")

    def callback(current: int, total: int, message: str) -> None:
        fraction = min(current / max(total, 1), 1.0)
        progress.progress(fraction, text=message)

    try:
        metadata = update_from_pbh(progress_callback=callback, force_download=force, include_historical=include_historical)
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
            SELECT
                MIN(data_quitacao), MAX(data_quitacao),
                MIN(valor_declarado), MAX(valor_declarado),
                MIN(area_construida), MAX(area_construida)
            FROM transactions
            """
        ).fetchone()
        bairros = con.execute("SELECT DISTINCT bairro FROM transactions WHERE bairro IS NOT NULL ORDER BY bairro").fetchdf()["bairro"].tolist()
        tipos = con.execute("SELECT DISTINCT tipo_construtivo FROM transactions WHERE tipo_construtivo IS NOT NULL ORDER BY tipo_construtivo").fetchdf()["tipo_construtivo"].tolist()
        ocupacoes = con.execute("SELECT DISTINCT tipo_ocupacao FROM transactions WHERE tipo_ocupacao IS NOT NULL ORDER BY tipo_ocupacao").fetchdf()["tipo_ocupacao"].tolist()
    return {
        "min_date": row[0], "max_date": row[1],
        "min_value": row[2] or 0, "max_value": row[3] or 0,
        "min_area": row[4] or 0, "max_area": row[5] or 0,
        "bairros": bairros, "tipos": tipos, "ocupacoes": ocupacoes,
    }


def query_filtered(filters: dict, limit: int = 2000) -> tuple[pd.DataFrame, dict]:
    where = ["1=1"]
    params: list[object] = []
    if filters["text"]:
        terms = [normalize_text(term) for term in filters["text"].split() if normalize_text(term)]
        for term in terms:
            where.append("(endereco_busca LIKE ? OR bairro_busca LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%"])
    if filters["bairros"]:
        placeholders = ",".join("?" for _ in filters["bairros"])
        where.append(f"bairro IN ({placeholders})")
        params.extend(filters["bairros"])
    if filters["tipos"]:
        placeholders = ",".join("?" for _ in filters["tipos"])
        where.append(f"tipo_construtivo IN ({placeholders})")
        params.extend(filters["tipos"])
    if filters["ocupacoes"]:
        placeholders = ",".join("?" for _ in filters["ocupacoes"])
        where.append(f"tipo_ocupacao IN ({placeholders})")
        params.extend(filters["ocupacoes"])
    where.extend([
        "data_quitacao BETWEEN ? AND ?",
        "COALESCE(valor_declarado, 0) BETWEEN ? AND ?",
        "COALESCE(area_construida, 0) BETWEEN ? AND ?",
    ])
    params.extend([
        filters["date_start"], filters["date_end"],
        filters["value_min"], filters["value_max"],
        filters["area_min"], filters["area_max"],
    ])
    clause = " AND ".join(where)

    with connect_read_only() as con:
        stats_row = con.execute(
            f"""
            SELECT
                COUNT(*) AS registros,
                MEDIAN(valor_declarado) AS mediana_valor,
                MEDIAN(valor_m2_declarado) FILTER (WHERE valor_m2_declarado BETWEEN 100 AND 100000) AS mediana_m2,
                MEDIAN(valor_base_calculo) AS mediana_base,
                AVG(CASE WHEN valor_base_calculo > valor_declarado THEN 1 ELSE 0 END) * 100 AS pct_base_maior
            FROM transactions WHERE {clause}
            """,
            params,
        ).fetchone()
        result = con.execute(
            f"""
            SELECT
                registro_id, chave_tecnica, data_quitacao, endereco, bairro,
                tipo_construtivo, tipo_descricao, tipo_ocupacao,
                ano_construcao, area_construida, padrao_acabamento,
                valor_declarado, valor_base_calculo, valor_m2_declarado,
                diferenca_base, diferenca_pct, zona_uso
            FROM transactions
            WHERE {clause}
            ORDER BY data_quitacao DESC, valor_declarado DESC NULLS LAST
            LIMIT {int(limit)}
            """,
            params,
        ).fetchdf()
    stats = {
        "registros": stats_row[0] or 0,
        "mediana_valor": stats_row[1],
        "mediana_m2": stats_row[2],
        "mediana_base": stats_row[3],
        "pct_base_maior": stats_row[4],
    }
    return result, stats


def comparable_query(selected: pd.Series, months: int = 36, area_tolerance: float = 0.30, limit: int = 20) -> pd.DataFrame:
    end_date = selected["data_quitacao"] if pd.notna(selected["data_quitacao"]) else pd.Timestamp.today()
    start_date = end_date - pd.DateOffset(months=months)
    area = float(selected["area_construida"]) if pd.notna(selected["area_construida"]) else None
    area_min = max(area * (1 - area_tolerance), 0) if area is not None else 0
    area_max = area * (1 + area_tolerance) if area is not None else 1e12
    year = int(selected["ano_construcao"]) if pd.notna(selected["ano_construcao"]) else None
    finish = str(selected["padrao_acabamento"]) if pd.notna(selected["padrao_acabamento"]) else None

    with connect_read_only() as con:
        frame = con.execute(
            """
            SELECT
                data_quitacao, endereco, bairro, tipo_descricao,
                ano_construcao, area_construida, padrao_acabamento,
                valor_declarado, valor_base_calculo, valor_m2_declarado,
                ABS(area_construida - ?) / NULLIF(?, 0) AS dist_area,
                CASE WHEN ? IS NULL OR ano_construcao IS NULL THEN 0.25
                     ELSE LEAST(ABS(ano_construcao - ?) / 30.0, 1.0) END AS dist_ano,
                CASE WHEN ? IS NULL OR padrao_acabamento = ? THEN 0 ELSE 0.25 END AS penalidade_padrao,
                (ABS(area_construida - ?) / NULLIF(?, 0))
                  + CASE WHEN ? IS NULL OR ano_construcao IS NULL THEN 0.25 ELSE LEAST(ABS(ano_construcao - ?) / 30.0, 1.0) END
                  + CASE WHEN ? IS NULL OR padrao_acabamento = ? THEN 0 ELSE 0.25 END AS score
            FROM transactions
            WHERE bairro = ?
              AND tipo_construtivo = ?
              AND data_quitacao BETWEEN ? AND ?
              AND area_construida BETWEEN ? AND ?
              AND registro_id <> ?
              AND valor_declarado > 0
            ORDER BY score, data_quitacao DESC
            LIMIT ?
            """,
            [
                area, area, year, year, finish, finish,
                area, area, year, year, finish, finish,
                str(selected["bairro"]), str(selected["tipo_construtivo"]),
                start_date.date(), end_date.date(), area_min, area_max,
                str(selected["chave_tecnica"]), int(limit),
            ],
        ).fetchdf()
    return frame


def monthly_series(filters: dict) -> pd.DataFrame:
    where = ["data_quitacao BETWEEN ? AND ?", "valor_m2_declarado BETWEEN 100 AND 100000"]
    params: list[object] = [filters["date_start"], filters["date_end"]]
    if filters["bairros"]:
        placeholders = ",".join("?" for _ in filters["bairros"])
        where.append(f"bairro IN ({placeholders})")
        params.extend(filters["bairros"])
    if filters["tipos"]:
        placeholders = ",".join("?" for _ in filters["tipos"])
        where.append(f"tipo_construtivo IN ({placeholders})")
        params.extend(filters["tipos"])
    with connect_read_only() as con:
        return con.execute(
            f"""
            SELECT DATE_TRUNC('month', data_quitacao) AS mes,
                   COUNT(*) AS transacoes,
                   MEDIAN(valor_m2_declarado) AS mediana_m2,
                   MEDIAN(valor_declarado) AS mediana_valor
            FROM transactions
            WHERE {' AND '.join(where)}
            GROUP BY 1 ORDER BY 1
            """,
            params,
        ).fetchdf()


def neighborhood_ranking(filters: dict, min_records: int = 10) -> pd.DataFrame:
    with connect_read_only() as con:
        return con.execute(
            """
            SELECT bairro, COUNT(*) AS transacoes,
                   MEDIAN(valor_m2_declarado) AS mediana_m2,
                   MEDIAN(valor_declarado) AS mediana_valor
            FROM transactions
            WHERE data_quitacao BETWEEN ? AND ?
              AND valor_m2_declarado BETWEEN 100 AND 100000
            GROUP BY bairro
            HAVING COUNT(*) >= ?
            ORDER BY mediana_m2 DESC
            LIMIT 30
            """,
            [filters["date_start"], filters["date_end"], min_records],
        ).fetchdf()


st.title("ITBI BH")
st.caption("Consulta de transações imobiliárias declaradas à PBH — otimizada para celular.")

if not database_exists():
    st.info("Na primeira utilização, prepare a base recente da PBH. Ela reúne os arquivos mensais disponíveis desde junho de 2024 e é suficiente para pesquisar compras recentes.")
    if st.button("Preparar base recente", type="primary", width="stretch"):
        run_update(include_historical=False)
    with st.expander("Outras opções"):
        if st.button("Preparar histórico completo desde 2008", width="stretch"):
            run_update(include_historical=True)
        if st.button("Abrir somente a demonstração", width="stretch"):
            try:
                build_demo_database()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Não foi possível preparar a demonstração: {exc}")
        st.caption("O histórico completo é mais pesado e não é necessário para a maioria das consultas de compras recentes.")
    st.stop()

metadata = load_metadata()
dimensions = get_dimensions(DB_PATH.stat().st_mtime)

def _safe_default_start():
    return max(dimensions["min_date"], dimensions["max_date"] - timedelta(days=730))

with st.expander("Pesquisar e filtrar", expanded=True):
    with st.form("filtros_principais"):
        text = st.text_input(
            "Endereço, rua, condomínio ou bairro",
            placeholder="Ex.: Rua Pernambuco 1000 ou Funcionários",
        )
        bairros = st.multiselect("Bairro", dimensions["bairros"], placeholder="Todos os bairros")
        type_options = dimensions["tipos"]
        tipos = st.multiselect(
            "Tipo de imóvel",
            type_options,
            format_func=lambda code: f"{code} — {TYPE_LABELS.get(code, code)}",
            placeholder="Todos os tipos",
        )
        selected_dates = st.date_input(
            "Período da quitação",
            value=(_safe_default_start(), dimensions["max_date"]),
            min_value=dimensions["min_date"],
            max_value=dimensions["max_date"],
        )
        with st.expander("Filtros avançados"):
            ocupacoes = st.multiselect("Ocupação", dimensions["ocupacoes"], placeholder="Todas")
            max_value = max(float(dimensions["max_value"]), 1.0)
            value_min = st.number_input("Valor mínimo (R$)", min_value=0.0, max_value=max_value, value=0.0, step=10_000.0)
            value_max = st.number_input("Valor máximo (R$)", min_value=0.0, max_value=max_value, value=max_value, step=10_000.0)
            max_area = max(float(dimensions["max_area"]), 1.0)
            area_min = st.number_input("Área mínima (m²)", min_value=0.0, max_value=max_area, value=0.0, step=10.0)
            area_max = st.number_input("Área máxima (m²)", min_value=0.0, max_value=max_area, value=max_area, step=10.0)
        st.form_submit_button("Pesquisar", type="primary", width="stretch")

if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    date_start, date_end = selected_dates
else:
    date_start = date_end = selected_dates
if value_min > value_max:
    value_min, value_max = value_max, value_min
if area_min > area_max:
    area_min, area_max = area_max, area_min

filters = {
    "text": text,
    "bairros": bairros,
    "tipos": tipos,
    "ocupacoes": ocupacoes,
    "date_start": date_start,
    "date_end": date_end,
    "value_min": value_min,
    "value_max": value_max,
    "area_min": area_min,
    "area_max": area_max,
}

screen = st.selectbox(
    "Tela",
    ["Pesquisa", "Imóveis comparáveis", "Mercado por período", "Base e atualização"],
    label_visibility="collapsed",
)

if screen == "Pesquisa":
    result, stats = query_filtered(filters)
    row1 = st.columns(2)
    row1[0].metric("Transações", number_br(stats["registros"]))
    row1[1].metric("Mediana do valor", brl(stats["mediana_valor"]))
    row2 = st.columns(2)
    row2[0].metric("Mediana por m²", brl2(stats["mediana_m2"]))
    row2[1].metric("Mediana da base", brl(stats["mediana_base"]))
    st.caption(f"Em {number_br(stats['pct_base_maior'], 1)}% dos registros filtrados, a base de cálculo supera o valor declarado.")

    if result.empty:
        st.warning("Nenhuma transação encontrada com esses filtros.")
    else:
        view_mode = st.radio("Exibição", ["Cartões", "Tabela"], horizontal=True)
        if view_mode == "Cartões":
            card_limit = st.select_slider("Quantidade exibida", options=[10, 20, 30, 50], value=20)
            for _, row in result.head(card_limit).iterrows():
                with st.container(border=True):
                    date_text = pd.to_datetime(row["data_quitacao"]).strftime("%d/%m/%Y") if pd.notna(row["data_quitacao"]) else "Data não informada"
                    st.markdown(f"**{display_text(row['endereco'], 'Endereço não informado')}**")
                    st.caption(f"{display_text(row['bairro'], 'Bairro não informado')} · {date_text} · {display_text(row['tipo_descricao'], 'Tipo não informado')}")
                    c1, c2 = st.columns(2)
                    c1.metric("Valor declarado", brl(row["valor_declarado"]))
                    c2.metric("Valor por m²", brl2(row["valor_m2_declarado"]))
                    details = []
                    if pd.notna(row["area_construida"]):
                        details.append(f"Área: {number_br(row['area_construida'], 2)} m²")
                    if pd.notna(row["ano_construcao"]):
                        details.append(f"Construção: {int(row['ano_construcao'])}")
                    if pd.notna(row["valor_base_calculo"]):
                        details.append(f"Base: {brl(row['valor_base_calculo'])}")
                    if details:
                        st.caption(" · ".join(details))
        else:
            display = result.copy()
            display["data_quitacao"] = pd.to_datetime(display["data_quitacao"]).dt.strftime("%d/%m/%Y")
            display = display.rename(columns={
                "data_quitacao": "Data", "endereco": "Endereço", "bairro": "Bairro",
                "tipo_descricao": "Tipo", "ano_construcao": "Ano", "area_construida": "Área (m²)",
                "valor_declarado": "Valor declarado", "valor_base_calculo": "Base de cálculo",
                "valor_m2_declarado": "Valor/m²",
            })
            visible = ["Data", "Endereço", "Bairro", "Tipo", "Ano", "Área (m²)", "Valor declarado", "Base de cálculo", "Valor/m²"]
            st.dataframe(display[visible], width="stretch", hide_index=True, height=520)

        export = result.copy()
        export["data_quitacao"] = pd.to_datetime(export["data_quitacao"]).dt.strftime("%d/%m/%Y")
        csv = export.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig")
        st.download_button("Baixar resultados em CSV", data=csv, file_name="itbi_bh_resultado.csv", mime="text/csv", width="stretch")

elif screen == "Imóveis comparáveis":
    result_for_selection, _ = query_filtered(filters, limit=300)
    if result_for_selection.empty:
        st.warning("Nenhum imóvel disponível com os filtros atuais.")
    else:
        labels = result_for_selection.apply(
            lambda row: f"{pd.to_datetime(row['data_quitacao']).strftime('%d/%m/%Y')} | {row['bairro']} | {row['endereco']} | {brl(row['valor_declarado'])}",
            axis=1,
        ).tolist()
        selected_index = st.selectbox("Transação de referência", range(len(labels)), format_func=lambda i: labels[i])
        selected = result_for_selection.iloc[selected_index]
        with st.container(border=True):
            st.markdown(f"**{selected['endereco']}**")
            st.caption(f"{selected['bairro']} · {pd.to_datetime(selected['data_quitacao']).strftime('%d/%m/%Y')}")
            c1, c2 = st.columns(2)
            c1.metric("Valor declarado", brl(selected["valor_declarado"]))
            c2.metric("Valor por m²", brl2(selected["valor_m2_declarado"]))
            st.caption(f"Área: {number_br(selected['area_construida'], 2)} m² · Ano: {int(selected['ano_construcao']) if pd.notna(selected['ano_construcao']) else '—'}")

        months = st.slider("Janela temporal (meses)", 12, 120, 36, 12)
        tolerance = st.slider("Tolerância de área", 10, 60, 30, 5) / 100
        comparables = comparable_query(selected, months=months, area_tolerance=tolerance)
        if comparables.empty:
            st.info("Não foram encontrados comparáveis. Amplie a janela temporal ou a tolerância de área.")
        else:
            median_m2 = comparables["valor_m2_declarado"].median()
            estimated = median_m2 * selected["area_construida"] if pd.notna(selected["area_construida"]) else None
            c1, c2 = st.columns(2)
            c1.metric("Mediana por m²", brl2(median_m2))
            c2.metric("Referência × área", brl(estimated))
            st.caption("Referência estatística; não constitui laudo de avaliação.")
            for _, row in comparables.head(20).iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['endereco']}**")
                    st.caption(f"{pd.to_datetime(row['data_quitacao']).strftime('%d/%m/%Y')} · {number_br(row['area_construida'], 2)} m²")
                    c1, c2 = st.columns(2)
                    c1.metric("Valor", brl(row["valor_declarado"]))
                    c2.metric("Valor por m²", brl2(row["valor_m2_declarado"]))

elif screen == "Mercado por período":
    series = monthly_series(filters)
    if series.empty:
        st.warning("Não há dados suficientes no período selecionado.")
    else:
        fig = px.line(series, x="mes", y="mediana_m2", markers=True, labels={"mes": "Mês", "mediana_m2": "Mediana por m²"})
        fig.update_layout(yaxis_tickprefix="R$ ", hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width="stretch")
        fig2 = px.bar(series, x="mes", y="transacoes", labels={"mes": "Mês", "transacoes": "Transações"})
        fig2.update_layout(margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig2, width="stretch")
    ranking = neighborhood_ranking(filters)
    if not ranking.empty:
        st.subheader("Bairros com maior mediana por m²")
        for _, row in ranking.head(15).iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['bairro']}**")
                c1, c2 = st.columns(2)
                c1.metric("Mediana por m²", brl2(row["mediana_m2"]))
                c2.metric("Transações", number_br(row["transacoes"]))

else:
    st.subheader("Base e atualização")
    info = st.columns(2)
    info[0].metric("Registros", number_br(metadata.get("registros", metadata.get("registros_unicos"))))
    info[1].metric("Última data", metadata.get("data_final") or "—")
    st.caption(f"Escopo atual: {metadata.get('escopo', 'não informado').replace('_', ' ')}")
    if st.button("Atualizar dados da PBH", type="primary", width="stretch"):
        run_update(include_historical=metadata.get("escopo") == "historico_completo")
    with st.expander("Trocar o escopo da base"):
        if st.button("Usar base recente", width="stretch"):
            run_update(include_historical=False)
        if st.button("Usar histórico completo", width="stretch"):
            run_update(include_historical=True)
    st.markdown(
        """
        **Valor declarado** é o valor de aquisição informado pelo contribuinte. **Base de cálculo** é o valor considerado para tributação. A base pública não traz um campo individualizado com o montante efetivamente recolhido de ITBI.

        Para deixar o aplicativo com aparência de app no iPhone, abra o endereço no Safari, toque em **Compartilhar** e escolha **Adicionar à Tela de Início**.
        """
    )
    st.warning("Os resultados são referências baseadas em registros públicos. Não substituem avaliação imobiliária.")
    st.link_button("Abrir a fonte oficial da PBH", "https://dados.pbh.gov.br/dataset/itbi-relatorios", width="stretch")
