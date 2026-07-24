from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote_plus
import html
import json
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from app_logic import (
    comparable_source_exclusions,
    evaluate_selected_transaction,
    exclude_source_rows,
    same_address_reference_breakdown,
    store_hybrid_result,
)
from market_logic import (
    MIN_RADAR_TRANSACTIONS,
    MIN_WINDOW_TRANSACTIONS,
    eligible_neighborhoods,
    market_reading,
    market_scope_stats,
    monthly_market_series,
    neighborhood_snapshot,
    price_distribution,
    rank_neighborhoods,
)
from location_component import current_location
from location_logic import (
    geocode_neighborhood,
    geolocation_error_message,
    location_confirmation_label,
    location_details,
    normalize_geolocation_payload,
    reverse_geocode,
    rounded_coordinates,
    transaction_location_prefill,
    valuation_location_prefill,
)
from data_manager import (
    DB_PATH,
    DatabaseUpdateInProgressError,
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
        --qv-blue-strong: #1f57cf;
        --qv-blue-ink: #2f6fed;
        --qv-accent-grad: linear-gradient(135deg, #2f6fed 0%, #5b8bff 100%);
        --qv-soft: rgba(127,127,127,.07);
        --qv-soft-2: rgba(127,127,127,.12);
        --qv-border: rgba(127,127,127,.20);
        --qv-border-strong: rgba(127,127,127,.30);
        --qv-muted: rgba(127,127,127,.90);
        --qv-shadow: 0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.05);
        --qv-shadow-hover: 0 2px 4px rgba(15,23,42,.06), 0 14px 34px rgba(15,23,42,.09);
        --qv-radius: 16px;
        --qv-radius-lg: 20px;
        --qv-good: #0ca30c;
        --qv-bad: #d03b3b;
    }

    html, body, [class*="css"] {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }

    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 3rem;
        max-width: 1020px;
    }

    [data-testid="stHeader"] {background: transparent;}
    #MainMenu, footer {visibility: hidden;}

    /* ---- Indicadores (metric cards) ---- */
    [data-testid="stMetric"] {
        background: var(--qv-soft);
        border: 1px solid var(--qv-border);
        border-radius: var(--qv-radius);
        padding: 1rem 1.1rem;
        box-shadow: var(--qv-shadow);
        transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: var(--qv-shadow-hover);
        border-color: var(--qv-border-strong);
    }
    [data-testid="stMetricLabel"] {opacity: .72; font-weight: 600;}
    [data-testid="stMetricLabel"] p {font-size: .82rem !important;}
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 800;
        letter-spacing: -.015em;
    }
    [data-testid="stMetricValue"] p {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        line-height: 1.15;
    }

    div[data-testid="stForm"] {
        border: 1px solid var(--qv-border);
        border-radius: var(--qv-radius-lg);
        padding: 1.1rem 1.15rem .9rem;
        background: var(--qv-soft);
        box-shadow: var(--qv-shadow);
    }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    [data-testid="stDateInput"] input {
        border-radius: 11px !important;
    }

    /* ---- Botões ---- */
    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-primaryFormSubmit"] {
        background: var(--qv-accent-grad) !important;
        border: none !important;
        color: #fff !important;
        font-weight: 700 !important;
        border-radius: 12px !important;
        box-shadow: 0 6px 16px rgba(47,111,237,.30) !important;
        transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
    }
    [data-testid="stBaseButton-primary"]:hover,
    [data-testid="stBaseButton-primaryFormSubmit"]:hover {
        filter: brightness(1.04);
        transform: translateY(-1px);
        box-shadow: 0 10px 22px rgba(47,111,237,.38) !important;
    }
    [data-testid="stBaseButton-secondary"] {
        border-radius: 12px !important;
        border: 1px solid var(--qv-border-strong) !important;
        transition: border-color .15s ease, background .15s ease;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        border-color: var(--qv-blue) !important;
        color: var(--qv-blue) !important;
    }

    /* ---- Controle segmentado (abas) ---- */
    div[data-testid="stButtonGroup"] button {
        min-height: 2.7rem;
        border-radius: 11px !important;
        font-weight: 650;
        transition: all .15s ease;
    }
    div[data-testid="stButtonGroup"] button[aria-checked="true"],
    div[data-testid="stButtonGroup"] button[aria-pressed="true"] {
        background: var(--qv-accent-grad) !important;
        color: #fff !important;
        border-color: transparent !important;
        box-shadow: 0 4px 12px rgba(47,111,237,.28);
    }
    div[data-testid="stButtonGroup"] button[aria-checked="true"] *,
    div[data-testid="stButtonGroup"] button[aria-pressed="true"] * {
        color: #fff !important;
    }

    /* ---- Cabeçalho / marca ---- */
    .brand {padding: .1rem 0 .5rem;}
    .brand-name {
        display: inline-block;
        color: #fff;
        background: var(--qv-accent-grad);
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .10em;
        text-transform: uppercase;
        margin-bottom: .7rem;
        padding: .28rem .7rem;
        border-radius: 999px;
        box-shadow: 0 4px 12px rgba(47,111,237,.28);
    }
    .brand-title {
        font-size: 2.3rem;
        font-weight: 800;
        line-height: 1.08;
        letter-spacing: -.02em;
        margin: 0;
        max-width: 820px;
    }
    .brand-subtitle {
        opacity: .74;
        font-size: 1rem;
        margin-top: .6rem;
        max-width: 760px;
        line-height: 1.5;
    }

    .section-intro {
        opacity: .70;
        margin-top: -.35rem;
        margin-bottom: 1rem;
        line-height: 1.5;
    }

    .data-note {
        display: flex;
        align-items: center;
        gap: .55rem;
        background: var(--qv-soft);
        border: 1px solid var(--qv-border);
        border-left: 3px solid var(--qv-blue);
        border-radius: 12px;
        padding: .6rem .9rem;
        opacity: .92;
        font-size: .88rem;
        margin: .9rem 0 1.3rem;
    }

    .result-box {
        padding: 1.4rem 1.4rem;
        border: 1px solid var(--qv-border);
        border-radius: var(--qv-radius-lg);
        margin: .5rem 0 1rem;
        background: var(--qv-soft);
        box-shadow: var(--qv-shadow);
    }
    .result-box.result-hero {
        border: 1px solid rgba(47,111,237,.25);
        background:
            radial-gradient(120% 140% at 0% 0%, rgba(47,111,237,.10) 0%, rgba(47,111,237,0) 55%),
            var(--qv-soft);
    }
    .result-title {
        font-size: .82rem;
        opacity: .72;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: .05em;
        margin-bottom: .3rem;
    }
    .result-value {
        font-size: 2.15rem;
        font-weight: 800;
        line-height: 1.12;
        letter-spacing: -.02em;
    }
    .muted {
        opacity: .68;
        font-size: .9rem;
        margin-top: .35rem;
        line-height: 1.5;
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
        line-height: 1.55;
    }

    hr {
        border: none;
        border-top: 1px solid var(--qv-border);
        margin: 1.4rem 0;
    }

    @media (max-width: 768px) {
        .block-container {padding: .75rem .7rem 2.2rem;}
        .brand-title {font-size: 1.78rem;}
        .brand-subtitle {font-size: .92rem;}
        h2 {font-size: 1.32rem !important;}
        h3 {font-size: 1.15rem !important;}
        [data-testid="stMetricValue"] {font-size: 1.28rem;}
        [data-testid="stHorizontalBlock"] {flex-wrap: wrap;}
        [data-testid="column"] {
            min-width: 100% !important;
            width: 100% !important;
            flex: 1 1 100% !important;
        }
        button {min-height: 2.9rem;}
        .result-value {font-size: 1.7rem;}
        div[data-testid="stButtonGroup"] {
            overflow-x: auto;
            padding-bottom: .15rem;
        }
        div[data-testid="stButtonGroup"] button {
            white-space: nowrap;
            padding-left: .7rem !important;
            padding-right: .7rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# Paleta e estilo comum dos gráficos Plotly. Cores e eixos usam tons
# semitransparentes de cinza para permanecerem legíveis em tema claro e escuro,
# sem depender de detecção de tema. A série principal usa o azul da marca; a
# comparação com Belo Horizonte usa um cinza neutro (baseline), sempre distinguível.
QV_SERIES_PRIMARY = "#2f6fed"
QV_SERIES_COMPARISON = "#94a3b8"
QV_SEQUENTIAL = "#2f6fed"
QV_GRID = "rgba(128,128,128,.16)"
QV_AXIS_TEXT = "rgba(130,130,130,.95)"
QV_PLOT_CONFIG = {"displayModeBar": False, "displaylogo": False}


def style_plotly(fig, *, show_legend: bool = False):
    """Aplica o tema visual consistente do app a uma figura Plotly."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family='system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
            color=QV_AXIS_TEXT,
            size=13,
        ),
        margin=dict(l=10, r=10, t=18, b=10),
        hoverlabel=dict(
            bgcolor="rgba(30,41,59,.94)",
            bordercolor="rgba(30,41,59,.94)",
            font=dict(color="#fff", size=12.5),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title_text="",
        ),
        showlegend=show_legend,
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="outside",
        tickcolor="rgba(128,128,128,.25)",
        ticklen=4,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=QV_GRID,
        zeroline=False,
        showline=False,
    )
    return fig


# Coordenadas dos bairros para o mapa. São geocodificadas uma única vez pelo
# OpenStreetMap/Nominatim (respeitando o limite de 1 req/s) e guardadas em disco,
# para que as próximas aberturas não dependam da rede. O mapa do ITBI não traz
# coordenadas por transação; por isso a granularidade é por bairro.
BAIRROS_COORDS_PATH = DB_PATH.with_name("bairros_coords.json")
# Escala sequencial azul (evita tons quase brancos que sumiriam no mapa claro).
QV_MAP_COLORSCALE = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281", "#0d366b"]
BH_MAP_CENTER = {"lat": -19.919, "lon": -43.938}


def _load_bairros_coords() -> dict:
    try:
        data = json.loads(BAIRROS_COORDS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _save_bairros_coords(cache: dict) -> None:
    tmp = BAIRROS_COORDS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(BAIRROS_COORDS_PATH)


def neighborhood_coordinates(bairros: tuple[str, ...], max_new: int = 80) -> dict:
    """Retorna {bairro: (lat, lon)} para os bairros pedidos.

    Lê o cache em disco e só consulta a rede para bairros ainda desconhecidos,
    limitado a ``max_new`` por execução para não travar a interface. Bairros não
    localizados são marcados como nulos no cache para não repetir a tentativa.
    """
    cache = _load_bairros_coords()
    pending = [str(b) for b in bairros if str(b) not in cache]
    if pending:
        to_fetch = pending[:max_new]
        changed = False
        with st.spinner(
            f"Localizando bairros no mapa pela primeira vez… ({len(to_fetch)} bairro(s))"
        ):
            for name in to_fetch:
                try:
                    result = geocode_neighborhood(name)
                except Exception:  # noqa: BLE001 — rede indisponível não deve quebrar o app
                    result = None
                cache[name] = [result[0], result[1]] if result else None
                changed = True
        if changed:
            try:
                _save_bairros_coords(cache)
            except OSError:
                pass
    coords: dict[str, tuple[float, float]] = {}
    for b in bairros:
        value = cache.get(str(b))
        if value:
            coords[str(b)] = (float(value[0]), float(value[1]))
    return coords


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


def google_maps_url(endereco: object, bairro: object) -> str:
    """Monta uma pesquisa textual do endereço no Google Maps."""
    raw = "" if endereco is None or pd.isna(endereco) else str(endereco).strip()
    base_address = re.split(r"\s+-\s+", raw, maxsplit=1)[0].strip()
    neighborhood = "" if bairro is None or pd.isna(bairro) else str(bairro).strip()
    query = ", ".join(
        part
        for part in [base_address, neighborhood, "Belo Horizonte", "MG", "Brasil"]
        if part
    )
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def maps_button(endereco: object, bairro: object, *, key: str | None = None) -> None:
    """Exibe um link discreto para pesquisar o endereço no Google Maps."""
    st.link_button(
        "📍 Abrir no Google Maps",
        google_maps_url(endereco, bairro),
        width="stretch",
        help="Abre uma pesquisa textual do endereço; a localização exibida pelo Google pode exigir conferência.",
    )


def friendly_update_error(exc: Exception) -> tuple[str, str]:
    """Traduz uma falha de conexão com a PBH numa mensagem clara para o usuário.

    A PBH usa um firewall que, ocasionalmente, deixa de responder para o servidor
    onde este app roda (mesmo que o site funcione normalmente num navegador comum).
    Isso é externo ao app; aqui só tornamos o aviso compreensível, sem tentar
    contornar o bloqueio. Retorna (mensagem para o usuário, detalhe técnico).
    """
    detail = str(exc)
    host_match = re.search(r"host=['\"]?([\w.\-]+)", detail)
    host_text = f" ({host_match.group(1)})" if host_match else ""
    lowered = detail.lower()

    if "read timed out" in lowered:
        reason = f"O servidor da Prefeitura{host_text} recebeu a solicitação, mas não respondeu a tempo."
    elif "connect timeout" in lowered or "timed out" in lowered:
        reason = f"Não foi possível conectar ao servidor da Prefeitura{host_text} — a conexão não respondeu a tempo."
    elif any(
        term in lowered
        for term in ("max retries exceeded", "connection refused", "name or service not known", "failed to resolve")
    ):
        reason = f"Não foi possível estabelecer conexão com o servidor da Prefeitura{host_text}."
    elif "403" in detail:
        reason = f"O servidor da Prefeitura{host_text} recusou a conexão (código 403)."
    elif any(code in detail for code in ("500", "502", "503", "504")):
        reason = f"O servidor da Prefeitura{host_text} respondeu com um erro interno."
    else:
        reason = "Não foi possível concluir a atualização dos dados da Prefeitura agora."

    message = (
        f"{reason} Isso costuma ser uma instabilidade do lado do portal de dados abertos da PBH, "
        "não deste aplicativo — tente novamente em alguns minutos."
    )
    return message, detail


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
    except DatabaseUpdateInProgressError:
        progress.empty()
        st.info(
            "A base da PBH já está sendo preparada por outra sessão. "
            "Aguarde a conclusão e recarregue a página."
        )
    except Exception as exc:  # noqa: BLE001
        progress.empty()
        friendly_message, technical_detail = friendly_update_error(exc)
        st.error(friendly_message)
        with st.expander("Detalhe técnico"):
            st.code(technical_detail)


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
    exclude_chave_tecnica: str | None = None,
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

            exclusion_clauses, exclusion_params = comparable_source_exclusions(
                exclude_registro_id,
                exclude_chave_tecnica,
            )
            where.extend(exclusion_clauses)
            params.extend(exclusion_params)

            if padrao and strict_pattern:
                where.append("padrao_acabamento = ?")
                params.append(padrao)

            if rua_search and location_level == "street":
                where.append("endereco_busca LIKE ?")
                params.append(f"%{rua_search}%")

            frame = con.execute(
                f"""
                SELECT registro_id, chave_tecnica, data_quitacao, endereco, endereco_busca, bairro,
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
            SELECT registro_id, chave_tecnica, data_quitacao, endereco, endereco_busca, bairro,
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
            SELECT registro_id, chave_tecnica, data_quitacao, endereco, endereco_busca, bairro,
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
            SELECT registro_id, chave_tecnica, data_quitacao, endereco, endereco_busca, bairro,
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
    source_chave_tecnica: str | None = None,
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
        exclude_chave_tecnica=source_chave_tecnica,
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

            building_rows = exclude_source_rows(
                building_rows,
                source_registro_id,
                source_chave_tecnica,
            )

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


def evaluate_transaction_row(row: pd.Series, end_date) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Avalia uma transação selecionada usando a metodologia híbrida vigente."""
    return evaluate_selected_transaction(
        hybrid_value_update_query,
        row,
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
        end_date=end_date,
        source_address=row["endereco"],
    )


def transaction_subject(row: pd.Series) -> dict:
    return {
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



def prefill_more_similar_transactions(subject: dict) -> None:
    """Prepara a aba Transações com o perfil do imóvel avaliado."""
    st.session_state["_prefill_transactions"] = {
        "text": subject.get("rua") or "",
        "bairros": [subject["bairro"]],
        "tipos": [subject["tipo"]],
    }
    st.session_state["_go_screen"] = "Transações"


def render_hybrid_result() -> None:
    stats = st.session_state["hybrid_stats"]
    local_rows = st.session_state["hybrid_local"]
    building_rows = st.session_state["hybrid_building"]
    subject = st.session_state["hybrid_subject"]

    if st.button("Fechar resultado", key="close_result_dialog", width="stretch"):
        st.rerun(scope="app")

    building_ids = (
        set(building_rows["registro_id"].astype(str))
        if not building_rows.empty and "registro_id" in building_rows.columns
        else set()
    )
    other_local_rows = (
        local_rows[~local_rows["registro_id"].astype(str).isin(building_ids)].copy()
        if not local_rows.empty and "registro_id" in local_rows.columns
        else local_rows.copy()
    )
    similar_count = len(building_rows) + len(other_local_rows)

    st.markdown("---")
    if subject.get("source_transaction"):
        st.success("Dados do imóvel carregados diretamente da transação selecionada.")
        st.caption(
            f"{short_address(subject.get('source_address'), subject['bairro'])} · "
            f"{pd.Timestamp(subject['purchase_date']).strftime('%d/%m/%Y')} · "
            f"valor de referência histórico {brl(subject['old_value'])}."
        )

    st.markdown(
        f"""
        <div class="result-box">
          <div class="result-title">Estimativa de valor atual</div>
          <div class="result-value">{brl(stats['estimated'])}</div>
          <div class="muted">Faixa entre as referências disponíveis: {brl(stats['low_value'])} a {brl(stats['high_value'])} · confiança {stats['confidence'].lower()}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    summary_tab, similar_tab = st.tabs(
        ["Resumo", f"Imóveis semelhantes ({similar_count})"]
    )

    with summary_tab:
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
            col.metric(anchor["source"], brl(anchor["value"]))
            col.caption(str(anchor["detail"]))

        fig = px.bar(
            anchor_df,
            x="source",
            y="value",
            text_auto=".3s",
            labels={"source": "Referência", "value": "Valor estimado"},
            color_discrete_sequence=[QV_SEQUENTIAL],
        )
        fig.update_traces(
            marker_line_width=0,
            textposition="outside",
            textfont_size=12,
            cliponaxis=False,
        )
        style_plotly(fig)
        fig.update_layout(yaxis_tickprefix="R$ ")
        st.plotly_chart(fig, width="stretch", config=QV_PLOT_CONFIG)

        st.info(
            "O valor central é a **mediana das referências complementares disponíveis**. "
            "Assim, uma referência isolada muito baixa ou muito alta não domina automaticamente o resultado."
        )

        fipe_info = stats.get("fipe")
        if fipe_info is not None:
            growth_text = f"{fipe_info['growth_pct']:+.1f}%".replace(".", ",")
            st.markdown(
                f"**Âncora temporal FipeZAP BH:** variação de **{growth_text}** entre "
                f"{fipe_info['start_date'].strftime('%m/%Y')} e {fipe_info['end_date'].strftime('%m/%Y')}. "
                f"O valor histórico de {brl(subject['old_value'])} corresponderia a "
                f"**{brl(subject['old_value'] * fipe_info['factor'])}** pela evolução do índice."
            )
            st.caption(
                "O FipeZAP é usado como benchmark temporal de anúncios de apartamentos prontos em Belo Horizonte; não é tratado como preço efetivo de uma transação específica."
            )
        elif subject["tipo"] != "AP":
            st.warning(
                "O FipeZAP residencial de venda acompanha apartamentos prontos. Por isso, ele não foi usado como âncora temporal para este tipo de imóvel."
            )

        local_stats = stats.get("local_stats") or {}
        if local_stats:
            st.markdown(
                f"**Comparáveis PBH:** {int(local_stats['records'])} imóveis semelhantes resultaram em referência central de **{brl(local_stats['estimated'])}**."
            )
        if stats.get("building_records", 0) > 0:
            st.markdown(
                f"**Mesmo endereço:** {stats['building_records']} transação(ões) do endereço foi(ram) normalizada(s) para a área cadastral do imóvel e trazida(s) ao período atual pelo FipeZAP."
            )

        with st.expander("Como calculamos esta estimativa?"):
            st.write(
                "O cálculo confronta a evolução temporal do valor histórico, o nível atual de imóveis comparáveis na base da PBH e, quando disponíveis, negócios do mesmo endereço. O resultado central é a mediana das referências disponíveis."
            )
            st.caption(
                "Valor de referência = maior valor entre o declarado e a base de cálculo da PBH. A estimativa é estatística e não substitui laudo técnico."
            )

    with similar_tab:
        st.caption(
            "Abaixo estão as transações que efetivamente participaram das referências do cálculo. Negócios do mesmo endereço aparecem primeiro."
        )

        if not building_rows.empty:
            st.subheader("Mesmo endereço")
            st.info(
                "**Como ler estes cartões:** o valor indicado para o imóvel avaliado **não é uma simples atualização do valor histórico pelo FipeZAP**. "
                "O app primeiro transforma cada transação em valor por m² cadastral, ajusta esse valor para a área cadastral do imóvel que está sendo avaliado e, só depois, aplica a atualização temporal do FipeZAP."
            )
            for _, row in building_rows.sort_values(
                "data_quitacao", ascending=False
            ).head(10).iterrows():
                breakdown = same_address_reference_breakdown(
                    reference_value=float(row["valor_referencia"]),
                    reference_m2=float(row["valor_m2_referencia"]),
                    transaction_area=float(row["area_construida"]),
                    subject_area=float(subject["area"]),
                    fipe_factor=float(row["fator_fipe"]),
                )
                with st.container(border=True):
                    address_header(
                        row["endereco"],
                        row["bairro"],
                        row["data_quitacao"],
                        row["tipo_descricao"],
                    )
                    c1, c2 = st.columns(2)
                    c1.metric(
                        "Valor de referência desta transação na época",
                        brl(row["valor_referencia"]),
                        help="Maior valor entre o declarado e a base de cálculo da PBH.",
                    )
                    c2.metric(
                        "Quanto esta transação indica para o imóvel avaliado hoje",
                        brl(row["valor_equivalente_atual"]),
                    )
                    st.markdown(
                        f"**Não estamos simplesmente atualizando {brl(row['valor_referencia'])}.** "
                        f"A transação tinha **{number_br(breakdown['transaction_area'], 2)} m² cadastrais** e o imóvel avaliado tem "
                        f"**{number_br(breakdown['subject_area'], 2)} m² cadastrais**. Por isso, o cálculo usa primeiro o valor por m², "
                        "adapta a referência para o tamanho do imóvel avaliado e somente depois aplica o FipeZAP."
                    )
                    st.caption(
                        f"{number_br(breakdown['transaction_area'], 2)} m² da transação → "
                        f"{brl(breakdown['reference_m2'], 2)}/m² → "
                        f"ajustado para {number_br(breakdown['subject_area'], 2)} m² do imóvel avaliado → "
                        f"FipeZAP × {number_br(breakdown['fipe_factor'], 4)} → "
                        f"{brl(breakdown['current_equivalent'])}"
                    )
                    with st.expander(
                        f"Ver como chegamos a {brl(row['valor_equivalente_atual'])}"
                    ):
                        st.markdown(
                            (
                                "**1. Transformamos a transação em valor por m² cadastral**\n\n"
                                f"{brl(breakdown['reference_value'])} ÷ {number_br(breakdown['transaction_area'], 2)} m² = **{brl(breakdown['reference_m2'], 2)}/m²**\n\n"
                                "**2. Aplicamos esse valor por m² à área cadastral do imóvel avaliado**\n\n"
                                f"{brl(breakdown['reference_m2'], 2)}/m² × {number_br(breakdown['subject_area'], 2)} m² = **{brl(breakdown['area_adjusted_value'])}**\n\n"
                                "**3. Só então atualizamos temporalmente pelo FipeZAP**\n\n"
                                f"{brl(breakdown['area_adjusted_value'])} × {number_br(breakdown['fipe_factor'], 4)} = **{brl(breakdown['current_equivalent'])}**"
                            ).replace("$", "\\$")
                        )
                        st.caption(
                            "Os valores intermediários exibidos são arredondados para facilitar a leitura. O cálculo usa os valores completos armazenados na base."
                        )
                    maps_button(row["endereco"], row["bairro"])

        if not other_local_rows.empty:
            st.subheader("Outros imóveis semelhantes")
            for _, row in other_local_rows.head(10).iterrows():
                with st.container(border=True):
                    address_header(
                        row["endereco"],
                        row["bairro"],
                        row["data_quitacao"],
                        TYPE_LABELS.get(row["tipo_construtivo"], row["tipo_descricao"]),
                    )
                    c1, c2 = st.columns(2)
                    c1.metric("Equivalente atual", brl(row["valor_equivalente_atual"]))
                    c2.metric("Por m² cadastral atual", brl(row["valor_m2_equivalente_atual"], 2))
                    st.markdown(
                        f'<div class="record-detail">'
                        f'Referência na data: {brl(row["valor_referencia"])} · '
                        f'Área cadastral PBH: {number_br(row["area_construida"], 2)} m² · '
                        f'Padrão: {html.escape(text_or_na(row["padrao_acabamento"]))}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    maps_button(row["endereco"], row["bairro"])

        if similar_count == 0:
            st.info("Não há transações individuais para detalhar nesta estimativa.")
        else:
            if st.button(
                "Ver mais imóveis semelhantes",
                key="view_more_similar",
                width="stretch",
                on_click=prefill_more_similar_transactions,
                args=(subject,),
            ):
                st.rerun(scope="app")


@st.dialog("Estimativa de valor atual", width="large")
def show_hybrid_result_dialog() -> None:
    """Exibe o resultado no viewport atual, sem depender de rolagem da página."""
    render_hybrid_result()


@st.cache_data(ttl=86400, show_spinner=False)
def reverse_geocode_cached(latitude: float, longitude: float) -> dict:
    """Faz uma consulta reversa e guarda o resultado para evitar chamadas repetidas."""
    return reverse_geocode(latitude, longitude)


def render_location_picker(target: str, bairros_disponiveis: list[str]) -> None:
    """Renderiza o fluxo de GPS no corpo da página, sem depender de fragmentos."""
    with st.container(border=True):
        st.markdown("**Localização atual**")
        st.caption(
            "Toque no botão abaixo e autorize o navegador. O endereço aproximado será mostrado para confirmação antes de ser usado."
        )
        payload = current_location(key=f"gps_{target}")
        location = normalize_geolocation_payload(payload)

        if location.get("status") == "error":
            st.error(
                geolocation_error_message(
                    location.get("error"),
                    location.get("message"),
                )
            )
        elif location.get("status") == "ok":
            latitude, longitude = rounded_coordinates(
                location["latitude"],
                location["longitude"],
            )
            try:
                with st.spinner("Identificando o endereço aproximado..."):
                    reverse_result = reverse_geocode_cached(latitude, longitude)
            except Exception:
                st.error(
                    "Consegui acessar o GPS, mas não foi possível transformar a coordenada em um endereço agora. Tente novamente em alguns instantes."
                )
            else:
                details = location_details(reverse_result, bairros_disponiveis)
                if not details.get("in_belo_horizonte"):
                    st.warning(
                        "A localização detectada não parece estar em Belo Horizonte. O Quanto Vale BH trabalha apenas com imóveis do município."
                    )
                else:
                    st.success(
                        f"Localização aproximada: **{location_confirmation_label(details)}**"
                    )
                    if location.get("accuracy") is not None:
                        st.caption(
                            f"Precisão informada pelo dispositivo: aproximadamente {number_br(location['accuracy'], 0)} m."
                        )
                    st.caption(
                        "O endereço é aproximado e pode corresponder ao ponto mapeado mais próximo. Dados de endereço: © OpenStreetMap contributors."
                    )

                    if target == "valuation":
                        if st.button(
                            "Usar este endereço para buscar o imóvel",
                            type="primary",
                            width="stretch",
                            key="apply_gps_valuation",
                        ):
                            st.session_state["_gps_prefill_valuation"] = valuation_location_prefill(details)
                            st.session_state["_show_gps_valuation"] = False
                            st.rerun()

                    elif target == "transactions":
                        if st.button(
                            "Buscar transações neste local",
                            type="primary",
                            width="stretch",
                            key="apply_gps_transactions",
                        ):
                            st.session_state["_gps_prefill_transactions"] = transaction_location_prefill(details)
                            st.session_state["_show_gps_transactions"] = False
                            st.rerun()

                    elif target == "market":
                        bairro = details.get("bairro")
                        if bairro:
                            if st.button(
                                f"Ver mercado de {smart_title(bairro)}",
                                type="primary",
                                width="stretch",
                                key="apply_gps_market",
                            ):
                                st.session_state["_gps_prefill_market"] = bairro
                                st.session_state["_show_gps_market"] = False
                                st.rerun()
                        else:
                            st.info(
                                "O GPS encontrou o endereço, mas não consegui associar automaticamente o local a um bairro da base da PBH."
                            )

        else:
            st.caption(
                "A localização só é solicitada depois do seu toque. As coordenadas não são gravadas na base de transações do aplicativo."
            )

        if st.button(
            "Fechar localização",
            width="stretch",
            key=f"close_gps_{target}",
        ):
            st.session_state[f"_show_gps_{target}"] = False
            st.rerun()


@st.cache_data(ttl=600)
def monthly_series(
    bairro: str | None,
    tipo: str | None,
    date_start,
    date_end,
    db_mtime: float,
) -> pd.DataFrame:
    del db_mtime
    with connect_read_only() as con:
        return monthly_market_series(
            con,
            bairro=bairro,
            tipo=tipo,
            date_start=date_start,
            date_end=date_end,
            reference_m2_sql=REFERENCE_M2_SQL,
        )


@st.cache_data(ttl=600)
def market_summary_query(
    bairro: str | None,
    tipo: str | None,
    end_date,
    db_mtime: float,
) -> dict:
    del db_mtime
    with connect_read_only() as con:
        return market_scope_stats(
            con,
            bairro=bairro,
            tipo=tipo,
            end_date=end_date,
            reference_value_sql=REFERENCE_VALUE_SQL,
            reference_m2_sql=REFERENCE_M2_SQL,
        )


@st.cache_data(ttl=600)
def neighborhood_snapshot_query(
    tipo: str | None,
    end_date,
    db_mtime: float,
) -> pd.DataFrame:
    del db_mtime
    with connect_read_only() as con:
        return neighborhood_snapshot(
            con,
            tipo=tipo,
            end_date=end_date,
            reference_value_sql=REFERENCE_VALUE_SQL,
            reference_m2_sql=REFERENCE_M2_SQL,
        )


st.markdown(
    """
    <div class="brand">
      <div class="brand-name">Quanto Vale BH</div>
      <div class="brand-title">Quanto vale um imóvel em Belo Horizonte?</div>
      <div class="brand-subtitle">
        Estime um valor atual, veja os imóveis semelhantes usados na comparação e acompanhe o mercado com dados públicos da PBH.
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
    st.subheader("Estimar valor atual")
    st.markdown(
        '<div class="section-intro">Encontre o imóvel na base da PBH para carregar os dados cadastrais e comparar o valor atual com negócios semelhantes.</div>',
        unsafe_allow_html=True,
    )

    valuation_source_mode = st.segmented_control(
        "Como informar o imóvel",
        ["Buscar imóvel na base", "Informar dados manualmente"],
        default="Buscar imóvel na base",
        label_visibility="collapsed",
        key="valuation_source_mode",
    )

    has_history = (
        metadata.get("escopo") == "historico_completo"
        or pd.Timestamp(dimensions["min_date"]) <= pd.Timestamp("2010-01-01")
    )

    gps_valuation_prefill = st.session_state.pop("_gps_prefill_valuation", None)
    if gps_valuation_prefill:
        st.session_state["valuation_search_text"] = gps_valuation_prefill.get("text", "")
        st.session_state["valuation_search_bairro"] = gps_valuation_prefill.get("bairro")
        st.session_state["valuation_search_results"] = search_transactions_for_valuation(
            text=gps_valuation_prefill.get("text", ""),
            bairro=gps_valuation_prefill.get("bairro"),
            date_start=dimensions["min_date"],
            date_end=dimensions["max_date"],
        )

    if valuation_source_mode == "Buscar imóvel na base":
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
        else:
            st.success(
                "Opção recomendada: área cadastral, padrão, ano, tipo e valor de referência são carregados diretamente da transação."
            )

            if st.button(
                "Usar minha localização atual",
                width="stretch",
                key="open_gps_valuation",
            ):
                st.session_state["_show_gps_valuation"] = True

            if st.session_state.get("_show_gps_valuation", False):
                render_location_picker("valuation", dimensions["bairros"])

            with st.form("buscar_imovel_avaliacao"):
                valuation_search_text = st.text_input(
                    "Endereço ou rua",
                    placeholder="Ex.: Rua Angra 123",
                    key="valuation_search_text",
                )
                valuation_search_bairro = st.selectbox(
                    "Bairro (opcional)",
                    [None] + dimensions["bairros"],
                    format_func=lambda x: "Todos os bairros" if x is None else x,
                    key="valuation_search_bairro",
                )
                valuation_search_submitted = st.form_submit_button(
                    "Buscar imóvel",
                    type="primary",
                    width="stretch",
                )

            if valuation_search_submitted:
                if not valuation_search_text and not valuation_search_bairro:
                    st.warning("Informe pelo menos o endereço, a rua ou o bairro.")
                else:
                    st.session_state["valuation_search_results"] = search_transactions_for_valuation(
                        text=valuation_search_text,
                        bairro=valuation_search_bairro,
                        date_start=dimensions["min_date"],
                        date_end=dimensions["max_date"],
                    )

            valuation_results = st.session_state.get(
                "valuation_search_results",
                pd.DataFrame(),
            )

            if not valuation_results.empty:
                st.subheader("Selecione o imóvel")
                st.caption(
                    f"{number_br(len(valuation_results))} transações encontradas. Se o imóvel aparecer mais de uma vez, escolha a referência histórica que você reconhece."
                )

                for _, row in valuation_results.head(30).iterrows():
                    record_key = str(row["registro_id"])
                    with st.container(border=True):
                        address_header(
                            row["endereco"],
                            row["bairro"],
                            row["data_quitacao"],
                            row["tipo_descricao"],
                        )
                        c1, c2 = st.columns(2)
                        c1.metric("Valor de referência", brl(row["valor_referencia"]))
                        c2.metric("Por m² cadastral", brl(row["valor_m2_referencia"], 2))
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
                        maps_button(row["endereco"], row["bairro"])

                        if st.button(
                            "Estimar valor atual deste imóvel",
                            key=f"hybrid_update_{record_key}",
                            type="primary",
                            width="stretch",
                        ):
                            local_rows, building_rows, hybrid_stats = evaluate_transaction_row(
                                row,
                                dimensions["max_date"],
                            )
                            if not hybrid_stats:
                                st.warning(
                                    "Não foi possível formar referências suficientes para este imóvel."
                                )
                            else:
                                store_hybrid_result(
                                    st.session_state,
                                    local_rows=local_rows,
                                    building_rows=building_rows,
                                    stats=hybrid_stats,
                                    subject=transaction_subject(row),
                                )
                                show_hybrid_result_dialog()

    else:
        st.warning(
            "Use a área construída cadastrada na PBH, e não automaticamente a área privativa de anúncio. O preenchimento manual é uma alternativa quando o imóvel não é localizado na base."
        )

        default_purchase = max(
            pd.Timestamp(dimensions["min_date"]),
            pd.Timestamp(dimensions["max_date"]) - pd.DateOffset(years=5),
        ).date()

        with st.form("valor_antigo_hibrido"):
            old_value = st.number_input(
                "Valor antigo conhecido (R$)",
                min_value=1000.0,
                max_value=1000000000.0,
                value=450000.0,
                step=10000.0,
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
                format_func=lambda code: TYPE_LABELS.get(code, code),
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
                "Estimar valor atual",
                type="primary",
                width="stretch",
            )

        if hybrid_submitted:
            validation_error = None
            if not bairro_old or not tipo_old:
                validation_error = "Selecione o bairro e o tipo de imóvel."
            elif ano_old is not None and int(ano_old) > pd.Timestamp(purchase_date).year:
                validation_error = "O ano de construção não pode ser posterior à data de referência."

            if validation_error:
                st.warning(validation_error)
            else:
                local_rows, building_rows, hybrid_stats = hybrid_value_update_query(
                    old_value=float(old_value),
                    purchase_date=purchase_date,
                    bairro=bairro_old,
                    tipo=tipo_old,
                    area=float(area_old),
                    ano=int(ano_old) if ano_old is not None else None,
                    padrao=padrao_old,
                    rua=rua_old,
                    end_date=dimensions["max_date"],
                )
                if not hybrid_stats:
                    st.warning(
                        "Não foi possível formar referências suficientes para essa combinação."
                    )
                else:
                    store_hybrid_result(
                        st.session_state,
                        local_rows=local_rows,
                        building_rows=building_rows,
                        stats=hybrid_stats,
                        subject={
                            "old_value": float(old_value),
                            "purchase_date": purchase_date,
                            "bairro": bairro_old,
                            "rua": rua_old.strip() if rua_old else None,
                            "tipo": tipo_old,
                            "area": float(area_old),
                            "padrao": padrao_old,
                            "ano": int(ano_old) if ano_old is not None else None,
                            "source_transaction": False,
                        },
                    )
                    show_hybrid_result_dialog()




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
                    maps_button(row["endereco"], row["bairro"])

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

        if st.button(
            "Usar minha localização atual",
            width="stretch",
            key="open_gps_transactions",
        ):
            st.session_state["_show_gps_transactions"] = True

        if st.session_state.get("_show_gps_transactions", False):
            render_location_picker("transactions", dimensions["bairros"])

        gps_transaction_prefill = st.session_state.pop("_gps_prefill_transactions", None)
        if gps_transaction_prefill:
            st.session_state["transaction_search_text"] = gps_transaction_prefill.get("text", "")
            st.session_state["transaction_bairros"] = [
                item for item in gps_transaction_prefill.get("bairros", [])
                if item in dimensions["bairros"]
            ]
            st.session_state["transaction_tipos"] = []

        transaction_prefill = st.session_state.pop("_prefill_transactions", None)
        if transaction_prefill:
            st.session_state["transaction_search_text"] = transaction_prefill.get("text", "")
            st.session_state["transaction_bairros"] = [
                item for item in transaction_prefill.get("bairros", [])
                if item in dimensions["bairros"]
            ]
            st.session_state["transaction_tipos"] = [
                item for item in transaction_prefill.get("tipos", [])
                if item in dimensions["tipos"]
            ]

        with st.form("consulta"):
            search_text = st.text_input(
                "Rua, endereço ou bairro",
                placeholder=(
                    "Ex.: Rua Campos Elíseos ou Nova Granada"
                ),
                key="transaction_search_text",
            )
            bairros = st.multiselect(
                "Bairro",
                dimensions["bairros"],
                placeholder="Todos os bairros",
                key="transaction_bairros",
            )
            tipos = st.multiselect(
                "Tipo de imóvel",
                dimensions["tipos"],
                format_func=(
                    lambda code: TYPE_LABELS.get(code, code)
                ),
                placeholder="Todos os tipos",
                key="transaction_tipos",
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
            period_choice = st.segmented_control(
                "Período da transação",
                ["Últimos 12 meses", "Últimos 2 anos", "Últimos 5 anos", "Tudo", "Personalizado"],
                default="Últimos 2 anos",
                key="transaction_period",
            )
            with st.expander("Escolher datas específicas"):
                custom_dates = st.date_input(
                    "Intervalo personalizado",
                    value=(default_start, dimensions["max_date"]),
                    min_value=dimensions["min_date"],
                    max_value=dimensions["max_date"],
                    key="transaction_custom_dates",
                    label_visibility="collapsed",
                )
                st.caption(
                    'Escolha a data inicial e a final. Só é aplicado quando o período acima está em "Personalizado".'
                )
            searched = st.form_submit_button(
                "Buscar transações",
                type="primary",
                width="stretch",
            )

        # Converte a escolha de período em um intervalo de datas consultável.
        min_d = dimensions["min_date"]
        max_d = dimensions["max_date"]
        if period_choice == "Últimos 12 meses":
            date_start, date_end = max(min_d, max_d - timedelta(days=365)), max_d
        elif period_choice == "Últimos 5 anos":
            date_start, date_end = max(min_d, max_d - timedelta(days=1826)), max_d
        elif period_choice == "Tudo":
            date_start, date_end = min_d, max_d
        elif period_choice == "Personalizado":
            date_start, date_end = normalize_date_range(custom_dates)
        else:  # "Últimos 2 anos" (padrão) ou nenhuma seleção
            date_start, date_end = max(min_d, max_d - timedelta(days=730)), max_d

        result, stats = query_transactions(
            search_text,
            bairros,
            tipos,
            padroes,
            date_start,
            date_end,
        )

        # Confirmação explícita de que a busca rodou. Sem isso, clicar em
        # "Buscar transações" atualizava a lista abaixo mas passava a sensação
        # de que "nada aconteceu". O banner só aparece logo após o clique.
        if searched:
            if stats["records"] > 0:
                st.success(
                    f"✅ Busca realizada: {number_br(stats['records'])} transação(ões) encontrada(s). "
                    "Veja os resultados abaixo."
                )
            else:
                st.warning(
                    "🔍 Busca realizada, mas nenhuma transação foi encontrada para esses filtros. "
                    "Tente ampliar o período ou remover algum filtro."
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
                    maps_button(row["endereco"], row["bairro"])

                    b1, b2 = st.columns(2)

                    if b1.button(
                        "Avaliar este imóvel",
                        key=f"evaluate_{record_key}",
                        width="stretch",
                    ):
                        local_rows, building_rows, hybrid_stats = evaluate_transaction_row(
                            row,
                            dimensions["max_date"],
                        )
                        if not hybrid_stats:
                            st.warning(
                                "Não foi possível formar referências suficientes para avaliar este imóvel."
                            )
                        else:
                            store_hybrid_result(
                                st.session_state,
                                local_rows=local_rows,
                                building_rows=building_rows,
                                stats=hybrid_stats,
                                subject=transaction_subject(row),
                            )
                            # Abre o resultado direto no modal, sobre a própria aba
                            # Transações (mesmo comportamento da aba Avaliar). Antes
                            # o código apenas trocava de aba e o resultado não aparecia.
                            show_hybrid_result_dialog()

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
    st.subheader("Mercado imobiliário de Belo Horizonte")
    st.markdown(
        '<div class="section-intro">Veja como os valores e o volume de negócios estão se movendo, compare bairros e entenda a faixa de preços das transações.</div>',
        unsafe_allow_html=True,
    )

    gps_market_prefill = st.session_state.pop("_gps_prefill_market", None)
    if gps_market_prefill in dimensions["bairros"]:
        st.session_state["market_bairro"] = gps_market_prefill

    if st.button(
        "Usar minha localização atual",
        width="stretch",
        key="open_gps_market",
    ):
        st.session_state["_show_gps_market"] = True

    if st.session_state.get("_show_gps_market", False):
        render_location_picker("market", dimensions["bairros"])

    filter_col1, filter_col2 = st.columns(2)
    bairro_market = filter_col1.selectbox(
        "Bairro",
        [None] + dimensions["bairros"],
        format_func=lambda x: "Visão de Belo Horizonte" if x is None else smart_title(x),
        key="market_bairro",
    )
    market_type_options = [None] + dimensions["tipos"]
    market_default = market_type_options.index("AP") if "AP" in market_type_options else 0
    tipo_market = filter_col2.selectbox(
        "Tipo de imóvel",
        market_type_options,
        index=market_default,
        format_func=lambda x: "Todos os tipos" if x is None else TYPE_LABELS.get(x, x),
        key="market_tipo",
    )

    db_mtime = DB_PATH.stat().st_mtime
    scope_label = smart_title(bairro_market) if bairro_market else "Belo Horizonte"
    type_label = TYPE_LABELS.get(tipo_market, tipo_market) if tipo_market else "todos os tipos"
    market_stats = market_summary_query(
        bairro_market,
        tipo_market,
        dimensions["max_date"],
        db_mtime,
    )
    city_stats = (
        market_stats
        if bairro_market is None
        else market_summary_query(
            None,
            tipo_market,
            dimensions["max_date"],
            db_mtime,
        )
    )

    if market_stats.get("current_m2") is None:
        st.info("Não há dados suficientes para formar uma leitura atual dessa combinação.")
    else:
        change_12m = market_stats.get("change_12m")
        q25_m2 = market_stats.get("q25_m2")
        q75_m2 = market_stats.get("q75_m2")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Valor atual por m²",
            brl(market_stats["current_m2"], 0),
            help="Mediana de todas as transações válidas dos três meses mais recentes.",
        )
        c2.metric(
            "Variação em 12 meses",
            f"{change_12m:+.1f}%".replace(".", ",") if change_12m is not None else "—",
        )
        c3.metric(
            "Negócios em 12 meses",
            number_br(market_stats.get("records_12m", 0)),
            delta=(
                f"{market_stats['volume_change_12m']:+.1f}% vs. 12m anteriores".replace(".", ",")
                if market_stats.get("volume_change_12m") is not None
                else None
            ),
        )
        c4.metric(
            "Faixa central por m²",
            (
                # Formato compacto (um só "R$") para caber no card estreito.
                # Escapa o cifrão: o valor do metric é Markdown e "R$ … R$"
                # seria lido como fórmula matemática ($…$).
                f"{brl(q25_m2, 0)} – {number_br(q75_m2, 0)}".replace("$", "\\$")
                if q25_m2 is not None and q75_m2 is not None
                else "—"
            ),
            help="Intervalo entre o 25º e o 75º percentil (por m²) dos últimos 12 meses.",
        )

        reading = market_reading(scope_label, market_stats, city_stats)
        st.info(f"**O que está acontecendo em {scope_label}**\n\n{reading}")
        st.caption(
            f"Leitura de {type_label}. O valor atual por m² usa a mediana dos três meses mais recentes para reduzir oscilações mensais isoladas."
        )

    st.markdown("---")
    st.subheader("Evolução do valor por m²")
    period_choice = st.segmented_control(
        "Período do gráfico",
        ["2 anos", "5 anos", "Todo o histórico"],
        default="2 anos",
        label_visibility="collapsed",
        key="market_period",
    )
    if period_choice == "2 anos":
        market_start = max(
            pd.Timestamp(dimensions["min_date"]),
            pd.Timestamp(dimensions["max_date"]) - pd.DateOffset(years=2),
        )
    elif period_choice == "5 anos":
        market_start = max(
            pd.Timestamp(dimensions["min_date"]),
            pd.Timestamp(dimensions["max_date"]) - pd.DateOffset(years=5),
        )
    else:
        market_start = dimensions["min_date"]

    scope_series = monthly_series(
        bairro_market,
        tipo_market,
        market_start,
        dimensions["max_date"],
        db_mtime,
    )
    plot_frames = []
    if not scope_series.empty:
        scope_plot = scope_series.copy()
        scope_plot["escopo"] = scope_label
        plot_frames.append(scope_plot)
    if bairro_market is not None:
        city_series = monthly_series(
            None,
            tipo_market,
            market_start,
            dimensions["max_date"],
            db_mtime,
        )
        if not city_series.empty:
            city_plot = city_series.copy()
            city_plot["escopo"] = "Belo Horizonte"
            plot_frames.append(city_plot)

    if plot_frames:
        plot_data = pd.concat(plot_frames, ignore_index=True)
        plot_data["mes_rotulo"] = plot_data["mes"].apply(data_limit_label)
        plot_data["valor_rotulo"] = plot_data["mediana_m2_3m"].apply(
            lambda value: brl(value, 0)
        )
        fig = px.line(
            plot_data,
            x="mes",
            y="mediana_m2_3m",
            color="escopo",
            markers=True,
            custom_data=["mes_rotulo", "valor_rotulo", "transacoes_3m"],
            labels={
                "mes": "Mês",
                "mediana_m2_3m": "Valor por m² cadastral",
                "escopo": "",
            },
        )
        fig.update_traces(
            connectgaps=False,
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "%{customdata[0]}<br>"
                "%{customdata[1]} por m² cadastral<br>"
                "%{customdata[2]} transações na janela de 3 meses"
                "<extra></extra>"
            ),
        )
        # Série principal (recorte selecionado) em azul da marca; comparação com
        # Belo Horizonte em cinza neutro (baseline). Distinguível em daltonismo
        # por ser cromático × neutro, além da legenda.
        for trace in fig.data:
            is_comparison = trace.name == "Belo Horizonte" and len(plot_frames) > 1
            color = QV_SERIES_COMPARISON if is_comparison else QV_SERIES_PRIMARY
            trace.line.color = color
            trace.line.width = 2 if is_comparison else 2.6
            if is_comparison:
                trace.line.dash = "dot"
            trace.marker.color = color
            trace.marker.size = 6.5
            trace.marker.line.width = 2
            trace.marker.line.color = "rgba(255,255,255,.65)"
        style_plotly(fig, show_legend=len(plot_frames) > 1)
        fig.update_layout(yaxis_tickprefix="R$ ", hovermode="closest")
        st.plotly_chart(fig, width="stretch", config=QV_PLOT_CONFIG)
        st.caption(
            f"Cada ponto é a mediana de todas as transações válidas da janela de três meses encerrada naquele mês. "
            f"Janelas com menos de {MIN_WINDOW_TRANSACTIONS} transações são omitidas e interrompem a linha, em vez de criar uma tendência artificial. "
            "Ao passar o cursor, o gráfico mostra quantas transações sustentam cada ponto. Quando um bairro é selecionado, Belo Horizonte aparece como comparação."
        )
    else:
        st.info("Não há série histórica suficiente para esse recorte.")

    st.markdown("---")
    st.subheader(f"Quanto custam os imóveis negociados em {scope_label}?")
    if market_stats.get("median_value") is None:
        st.info("Não há negócios suficientes nos últimos 12 meses para resumir a faixa de valores.")
    else:
        p1, p2, p3 = st.columns(3)
        p1.metric("25% até", brl(market_stats.get("q25_value")))
        p2.metric("50% até", brl(market_stats.get("median_value")))
        p3.metric("75% até", brl(market_stats.get("q75_value")))
        dist = price_distribution(market_stats)
        total_dist = int(dist["transacoes"].sum())
        if total_dist > 0:
            dist["percentual"] = dist["transacoes"] / total_dist * 100
            fig_prices = px.bar(
                dist,
                x="faixa",
                y="transacoes",
                text="transacoes",
                labels={"faixa": "Faixa de valor", "transacoes": "Transações"},
                color_discrete_sequence=[QV_SEQUENTIAL],
            )
            fig_prices.update_traces(
                marker_line_width=0,
                textposition="outside",
                textfont_size=12,
                cliponaxis=False,
            )
            style_plotly(fig_prices)
            st.plotly_chart(fig_prices, width="stretch", config=QV_PLOT_CONFIG)
        st.caption(
            "Faixas calculadas com o valor de referência das transações dos últimos 12 meses."
        )

    snapshot = neighborhood_snapshot_query(
        tipo_market,
        dimensions["max_date"],
        db_mtime,
    )

    st.markdown("---")
    st.subheader("Mapa dos bairros de Belo Horizonte")
    st.markdown(
        '<div class="section-intro">Cada bolha é um bairro. A <b>cor</b> mostra o valor por m² '
        'e o <b>tamanho</b>, o volume de negócios nos últimos 12 meses.</div>',
        unsafe_allow_html=True,
    )
    map_pool = eligible_neighborhoods(
        snapshot,
        min_transactions=5,
        min_window_transactions=1,
    )
    # Mantém o mapa limpo e a geocodificação leve: mostra os bairros com maior
    # volume de negócios (os mais representativos). O bairro selecionado é sempre
    # incluído, mesmo que fique fora do corte por volume.
    MAP_MAX_NEIGHBORHOODS = 60
    if not map_pool.empty and len(map_pool) > MAP_MAX_NEIGHBORHOODS:
        top_pool = map_pool.nlargest(MAP_MAX_NEIGHBORHOODS, "records_12m")
        if bairro_market is not None and bairro_market not in set(top_pool["bairro"]):
            selected_row = map_pool[map_pool["bairro"] == bairro_market]
            top_pool = pd.concat([top_pool, selected_row], ignore_index=True)
        map_pool = top_pool
    if map_pool.empty:
        st.info("Não há bairros com amostra suficiente para desenhar o mapa neste recorte.")
    else:
        coords = neighborhood_coordinates(tuple(sorted(map_pool["bairro"].tolist())))
        map_df = map_pool[map_pool["bairro"].isin(coords)].copy()
        if map_df.empty:
            st.info(
                "Não foi possível localizar os bairros no mapa agora. "
                "Tente novamente em instantes (o serviço de mapas pode estar indisponível)."
            )
        else:
            map_df["lat"] = map_df["bairro"].map(lambda b: coords[b][0])
            map_df["lon"] = map_df["bairro"].map(lambda b: coords[b][1])
            map_df["bairro_titulo"] = map_df["bairro"].map(smart_title)
            map_df["valor_m2_fmt"] = map_df["current_m2"].apply(lambda v: brl(v, 0))
            map_df["volume_fmt"] = map_df["records_12m"].apply(number_br)
            center = BH_MAP_CENTER
            if bairro_market is not None and bairro_market in coords:
                center = {"lat": coords[bairro_market][0], "lon": coords[bairro_market][1]}
            fig_map = px.scatter_map(
                map_df,
                lat="lat",
                lon="lon",
                size="records_12m",
                color="current_m2",
                size_max=32,
                zoom=10.6 if bairro_market is None else 12.0,
                center=center,
                hover_name="bairro_titulo",
                custom_data=["valor_m2_fmt", "volume_fmt"],
                color_continuous_scale=QV_MAP_COLORSCALE,
                map_style="carto-positron",
            )
            fig_map.update_traces(
                marker={"opacity": 0.82},
                hovertemplate=(
                    "<b>%{hovertext}</b><br>"
                    "%{customdata[0]} por m² cadastral<br>"
                    "%{customdata[1]} negócios em 12 meses"
                    "<extra></extra>"
                ),
            )
            fig_map.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                height=470,
                paper_bgcolor="rgba(0,0,0,0)",
                coloraxis_colorbar=dict(
                    title="R$/m²",
                    thickness=12,
                    len=0.7,
                    outlinewidth=0,
                ),
                font=dict(family='system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'),
                hoverlabel=dict(
                    bgcolor="rgba(30,41,59,.94)",
                    bordercolor="rgba(30,41,59,.94)",
                    font=dict(color="#fff", size=12.5),
                ),
            )
            st.plotly_chart(fig_map, width="stretch", config=QV_PLOT_CONFIG)
            pendentes = len(map_pool) - len(map_df)
            legenda = "Passe o cursor sobre um bairro para ver o valor por m² e o número de negócios."
            if pendentes > 0:
                legenda += (
                    f" {number_br(pendentes)} bairro(s) ainda serão localizados nas próximas aberturas."
                )
            st.caption(legenda)

        # Atalho para abrir a região no Google Maps (visão familiar de ruas/satélite).
        st.link_button(
            f"📍 Abrir {scope_label} no Google Maps",
            google_maps_url(None, bairro_market),
            help="Abre o Google Maps na região selecionada, para ver ruas e pontos de referência.",
        )

    st.markdown("---")
    st.subheader("Compare bairros")
    comparison_pool = eligible_neighborhoods(
        snapshot,
        min_transactions=5,
        min_window_transactions=1,
    )
    comparison_options = sorted(comparison_pool["bairro"].tolist()) if not comparison_pool.empty else []
    comparison_defaults: list[str] = []
    if bairro_market in comparison_options:
        comparison_defaults.append(bairro_market)
    if not comparison_pool.empty:
        for candidate in comparison_pool.sort_values("records_12m", ascending=False)["bairro"].tolist():
            if candidate not in comparison_defaults:
                comparison_defaults.append(candidate)
            if len(comparison_defaults) >= min(3, len(comparison_options)):
                break

    compare_bairros = st.multiselect(
        "Escolha até três bairros",
        comparison_options,
        default=comparison_defaults,
        max_selections=3,
        format_func=smart_title,
        key="market_compare_bairros",
    )
    if compare_bairros:
        compare_frame = comparison_pool[
            comparison_pool["bairro"].isin(compare_bairros)
        ].copy()
        compare_frame["Bairro"] = compare_frame["bairro"].map(smart_title)
        compare_frame["R$/m² atual"] = compare_frame["current_m2"].map(lambda value: brl(value, 0))
        compare_frame["Variação 12m"] = compare_frame["change_12m"].map(
            lambda value: f"{value:+.1f}%".replace(".", ",") if pd.notna(value) else "—"
        )
        compare_frame["Negócios 12m"] = compare_frame["records_12m"].map(lambda value: number_br(value))
        compare_frame["Área mediana"] = compare_frame["median_area"].map(
            lambda value: f"{number_br(value, 0)} m²" if pd.notna(value) else "—"
        )
        compare_frame["Valor mediano"] = compare_frame["median_value"].map(lambda value: brl(value))
        st.dataframe(
            compare_frame[
                ["Bairro", "R$/m² atual", "Variação 12m", "Negócios 12m", "Área mediana", "Valor mediano"]
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("Selecione bairros com amostra suficiente para comparar.")

    st.markdown("---")
    st.subheader("Radar dos bairros")
    radar_choice = st.segmented_control(
        "Ranking",
        ["Maior valor por m²", "Maiores altas em 12 meses", "Mais negócios"],
        default="Maior valor por m²",
        label_visibility="collapsed",
        key="market_radar_metric",
    )
    radar_metric = {
        "Maior valor por m²": "current_m2",
        "Maiores altas em 12 meses": "change_12m",
        "Mais negócios": "records_12m",
    }[radar_choice]
    ranking = rank_neighborhoods(snapshot, radar_metric, limit=10)
    if ranking.empty:
        st.info(
            "Ainda não há bairros suficientes com amostra mínima para este ranking."
        )
    else:
        ranking = ranking.copy()
        ranking.insert(0, "#", range(1, len(ranking) + 1))
        ranking["Bairro"] = ranking["bairro"].map(smart_title)
        ranking["R$/m² atual"] = ranking["current_m2"].map(lambda value: brl(value, 0))
        ranking["Variação 12m"] = ranking["change_12m"].map(
            lambda value: f"{value:+.1f}%".replace(".", ",") if pd.notna(value) else "—"
        )
        ranking["Negócios 12m"] = ranking["records_12m"].map(lambda value: number_br(value))
        st.dataframe(
            ranking[["#", "Bairro", "R$/m² atual", "Variação 12m", "Negócios 12m"]],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            f"Para reduzir distorções de amostras pequenas, os rankings exigem pelo menos {MIN_RADAR_TRANSACTIONS} transações nos últimos 12 meses e cinco negócios na janela atual de três meses. O ranking de altas também exige amostra na janela equivalente de 12 meses atrás."
        )

    st.markdown("---")
    st.subheader(f"Perfil dos imóveis negociados em {scope_label}")
    pr1, pr2, pr3, pr4 = st.columns(4)
    pr1.metric(
        "Área cadastral mediana",
        f"{number_br(market_stats.get('median_area'), 0)} m²" if market_stats.get("median_area") is not None else "—",
    )
    pr2.metric("Valor mediano", brl(market_stats.get("median_value")))
    pr3.metric(
        "Ano mediano de construção",
        number_br(market_stats.get("median_year"), 0),
    )
    pr4.metric(
        "Padrão mais frequente",
        text_or_na(market_stats.get("common_pattern"), "—"),
    )
    st.caption(
        "Perfil resumido das transações dos últimos 12 meses. A área é a área construída cadastrada na PBH."
    )


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

        Na aba **Avaliar**, a forma recomendada é localizar uma transação do próprio imóvel. Assim, área, padrão, ano, tipo e valor histórico são carregados diretamente da base. O preenchimento manual fica disponível quando o imóvel não é localizado.

        A estimativa confronta referências complementares. Para apartamentos, usa a evolução do **FipeZAP Belo Horizonte** como âncora temporal, comparáveis atuais da PBH e, quando disponíveis, transações do mesmo endereço trazidas ao período atual. Os imóveis efetivamente usados nas referências podem ser consultados no próprio resultado. As referências locais também podem usar o FipeZAP apenas para normalização temporal.

        As avaliações são **referências estatísticas** e não substituem laudo técnico.

        **Localização atual:** o uso do GPS é opcional e só começa após uma ação do usuário e a autorização do navegador. As coordenadas não são gravadas na base de transações do aplicativo. Quando a função é usada, o app consulta um serviço de geocodificação reversa para transformar a coordenada em endereço aproximado; por padrão, utiliza OpenStreetMap/Nominatim e exibe a respectiva atribuição.

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
