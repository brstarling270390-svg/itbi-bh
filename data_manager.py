from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd
import requests

DATASET_ID = "0e13bf71-5355-47ce-8607-966413b08c0a"
PACKAGE_API_URLS = (
    f"https://dados.pbh.gov.br/api/3/action/package_show?id={DATASET_ID}",
    f"https://ckan.pbh.gov.br/api/3/action/package_show?id={DATASET_ID}",
)
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "itbi_bh.duckdb"
METADATA_PATH = DATA_DIR / "metadata.json"
DEMO_PATH = DATA_DIR / "demo_itbi.csv"

CANONICAL_COLUMNS = [
    "endereco",
    "bairro",
    "ano_construcao",
    "area_terreno",
    "area_construida",
    "area_somada",
    "padrao_acabamento",
    "fracao_ideal",
    "tipo_construtivo",
    "tipo_ocupacao",
    "valor_declarado",
    "valor_base_calculo",
    "zona_uso",
    "data_quitacao",
]

COLUMN_ALIASES = {
    "endereco": "endereco",
    "endereco completo": "endereco",
    "bairro": "bairro",
    "ano de construcao unidade": "ano_construcao",
    "ano de construcao (unidade)": "ano_construcao",
    "area terreno total": "area_terreno",
    "area construida adquirida": "area_construida",
    "area adquirida unidades somadas": "area_somada",
    "area adquirida (unidades somadas)": "area_somada",
    "padrao acabamento unidade": "padrao_acabamento",
    "padrao acabamento (unidade)": "padrao_acabamento",
    "fracao ideal adquirida": "fracao_ideal",
    "tipo construtivo preponderante": "tipo_construtivo",
    "descricao tipo ocupacao unidade": "tipo_ocupacao",
    "descricao tipo ocupacao (unidade)": "tipo_ocupacao",
    "valor declarado": "valor_declarado",
    "valor base calculo": "valor_base_calculo",
    "zona uso itbi": "zona_uso",
    "data quitacao transacao": "data_quitacao",
    "data quitacao": "data_quitacao",
}

TYPE_LABELS = {
    "AC": "Apartamento comercial",
    "AP": "Apartamento",
    "BA": "Barracão",
    "BC": "Barracão comercial",
    "CA": "Casa",
    "CC": "Casa comercial",
    "GP": "Galpão",
    "LJ": "Loja",
    "LV": "Lote vago",
    "SL": "Sala",
    "VC": "Vaga comercial",
    "VR": "Vaga residencial",
    "VV": "Vaga de uso misto",
}


@dataclass(frozen=True)
class Resource:
    resource_id: str
    name: str
    url: str
    modified: str | None
    size: int | None
    hash_value: str | None


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return re.sub(r"\s+", " ", text)


def _canonical_name(column: str) -> str | None:
    return COLUMN_ALIASES.get(normalize_text(column))


def parse_ptbr_number(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype("string")
        .str.strip()
        .replace({"": pd.NA, "-": pd.NA, "None": pd.NA, "nan": pd.NA})
        .str.replace(r"R\$\s*", "", regex=True)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def parse_year(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype("string").str.extract(r"(\d{4})", expand=False), errors="coerce").astype("Int64")


def _guess_csv_settings(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()[:200_000]
    encodings = ["utf-8-sig", "utf-8", "latin-1"]
    text = None
    selected = "utf-8-sig"
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            selected = encoding
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("latin-1", errors="replace")
        selected = "latin-1"
    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    return selected, delimiter


def normalize_chunk(chunk: pd.DataFrame, resource: Resource, row_offset: int = 0) -> pd.DataFrame:
    renamed: dict[str, str] = {}
    for column in chunk.columns:
        canonical = _canonical_name(str(column))
        if canonical:
            renamed[column] = canonical
    chunk = chunk.rename(columns=renamed)

    for column in CANONICAL_COLUMNS:
        if column not in chunk.columns:
            chunk[column] = pd.NA
    chunk = chunk[CANONICAL_COLUMNS].copy()

    text_columns = [
        "endereco",
        "bairro",
        "padrao_acabamento",
        "tipo_construtivo",
        "tipo_ocupacao",
        "zona_uso",
    ]
    for column in text_columns:
        chunk[column] = chunk[column].astype("string").str.strip().replace({"": pd.NA})

    chunk["bairro"] = chunk["bairro"].str.upper()
    chunk["tipo_construtivo"] = chunk["tipo_construtivo"].str.upper()
    chunk["tipo_ocupacao"] = chunk["tipo_ocupacao"].str.upper()
    chunk["padrao_acabamento"] = chunk["padrao_acabamento"].str.upper()
    chunk["zona_uso"] = chunk["zona_uso"].str.upper()

    chunk["ano_construcao"] = parse_year(chunk["ano_construcao"])
    for column in ["area_terreno", "area_construida", "area_somada", "fracao_ideal", "valor_declarado", "valor_base_calculo"]:
        chunk[column] = parse_ptbr_number(chunk[column])
    chunk["data_quitacao"] = pd.to_datetime(chunk["data_quitacao"], dayfirst=True, errors="coerce")

    chunk["tipo_descricao"] = chunk["tipo_construtivo"].map(TYPE_LABELS).fillna(chunk["tipo_construtivo"])
    chunk["endereco_busca"] = chunk["endereco"].fillna("").map(normalize_text)
    chunk["bairro_busca"] = chunk["bairro"].fillna("").map(normalize_text)
    chunk["valor_m2_declarado"] = chunk["valor_declarado"] / chunk["area_construida"].where(chunk["area_construida"] > 0)
    chunk["valor_m2_base"] = chunk["valor_base_calculo"] / chunk["area_construida"].where(chunk["area_construida"] > 0)
    chunk["diferenca_base"] = chunk["valor_base_calculo"] - chunk["valor_declarado"]
    chunk["diferenca_pct"] = (chunk["diferenca_base"] / chunk["valor_declarado"].where(chunk["valor_declarado"] != 0)) * 100
    chunk["arquivo_origem"] = resource.name
    chunk["recurso_id"] = resource.resource_id
    chunk["atualizado_em"] = resource.modified

    hash_source = (
        chunk["endereco"].fillna("") + "|"
        + chunk["bairro"].fillna("") + "|"
        + chunk["data_quitacao"].astype("string").fillna("") + "|"
        + chunk["valor_declarado"].astype("string").fillna("") + "|"
        + chunk["valor_base_calculo"].astype("string").fillna("") + "|"
        + chunk["area_construida"].astype("string").fillna("") + "|"
        + chunk["tipo_construtivo"].fillna("")
    )
    chunk["chave_tecnica"] = hash_source.map(lambda x: hashlib.sha1(x.encode("utf-8")).hexdigest())
    chunk["linha_origem"] = range(row_offset + 2, row_offset + 2 + len(chunk))
    chunk["registro_id"] = resource.resource_id + ":" + chunk["linha_origem"].astype(str)
    return chunk


def fetch_package_metadata(timeout: int = 30) -> dict:
    last_error: Exception | None = None
    headers = {"User-Agent": "ITBI-BH-Consulta/1.0"}
    for url in PACKAGE_API_URLS:
        try:
            response = requests.get(url, timeout=timeout, headers=headers)
            response.raise_for_status()
            payload = response.json()
            if payload.get("success") and payload.get("result"):
                return payload["result"]
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"Não foi possível consultar o catálogo da PBH: {last_error}")


def select_csv_resources(package: dict, include_historical: bool = True) -> list[Resource]:
    selected: list[Resource] = []
    for item in package.get("resources", []):
        name = str(item.get("name") or "")
        fmt = str(item.get("format") or "").upper()
        url = str(item.get("url") or "")
        normalized = normalize_text(name)
        is_csv = fmt == "CSV" or url.lower().endswith(".csv")
        is_itbi_data = "itbi relatorios" in normalized and "dicionario" not in normalized
        if not (is_csv and is_itbi_data and url):
            continue
        is_historical = "2008" in normalized and "2024" in normalized
        if is_historical and not include_historical:
            continue
        selected.append(
            Resource(
                resource_id=str(item.get("id") or ""),
                name=name,
                url=url,
                modified=item.get("last_modified") or item.get("metadata_modified") or item.get("created"),
                size=item.get("size"),
                hash_value=item.get("hash"),
            )
        )

    def sort_key(resource: Resource) -> tuple[int, int]:
        norm = normalize_text(resource.name)
        historical = 0 if "2008" in norm and "2024" in norm else 1
        match = re.search(r"(20\d{2}).*?(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)", norm)
        months = {m: i for i, m in enumerate(["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"], 1)}
        if match:
            return historical, int(match.group(1)) * 100 + months[match.group(2)]
        return historical, 0

    return sorted(selected, key=sort_key)


def _safe_filename(resource: Resource) -> str:
    name = normalize_text(resource.name).replace(" ", "_")
    return f"{name}_{resource.resource_id[:8]}.csv"


def download_resources(resources: Iterable[Resource], progress_callback=None, force: bool = False) -> list[Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "ITBI-BH-Consulta/1.0"}
    resources = list(resources)
    downloaded: list[Path] = []
    for index, resource in enumerate(resources, 1):
        path = RAW_DIR / _safe_filename(resource)
        if progress_callback:
            progress_callback(index - 1, len(resources), f"Verificando {resource.name}")
        if path.exists() and path.stat().st_size > 0 and not force:
            downloaded.append(path)
            continue
        temp_path = path.with_suffix(".tmp")
        with requests.get(resource.url, stream=True, timeout=(20, 180), headers=headers) as response:
            response.raise_for_status()
            with temp_path.open("wb") as file_handle:
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if block:
                        file_handle.write(block)
        temp_path.replace(path)
        downloaded.append(path)
        if progress_callback:
            progress_callback(index, len(resources), f"Baixado: {resource.name}")
    return downloaded


def _create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE transactions (
            endereco VARCHAR,
            bairro VARCHAR,
            ano_construcao INTEGER,
            area_terreno DOUBLE,
            area_construida DOUBLE,
            area_somada DOUBLE,
            padrao_acabamento VARCHAR,
            fracao_ideal DOUBLE,
            tipo_construtivo VARCHAR,
            tipo_ocupacao VARCHAR,
            valor_declarado DOUBLE,
            valor_base_calculo DOUBLE,
            zona_uso VARCHAR,
            data_quitacao DATE,
            tipo_descricao VARCHAR,
            endereco_busca VARCHAR,
            bairro_busca VARCHAR,
            valor_m2_declarado DOUBLE,
            valor_m2_base DOUBLE,
            diferenca_base DOUBLE,
            diferenca_pct DOUBLE,
            arquivo_origem VARCHAR,
            recurso_id VARCHAR,
            atualizado_em VARCHAR,
            chave_tecnica VARCHAR,
            linha_origem BIGINT,
            registro_id VARCHAR
        )
        """
    )


def build_database(resources: list[Resource], paths: list[Path], progress_callback=None) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_db = DB_PATH.with_suffix(".tmp.duckdb")
    for suffix in ["", ".wal"]:
        candidate = Path(str(temp_db) + suffix)
        if candidate.exists():
            candidate.unlink()

    connection = duckdb.connect(str(temp_db))
    _create_schema(connection)
    total_files = len(paths)
    total_rows = 0
    if len(resources) != len(paths):
        raise ValueError("A quantidade de recursos não corresponde à quantidade de arquivos.")

    try:
        for file_index, (resource, path) in enumerate(zip(resources, paths), 1):
            if progress_callback:
                progress_callback(file_index - 1, total_files, f"Processando {resource.name}")
            encoding, delimiter = _guess_csv_settings(path)
            read_kwargs = dict(
                sep=delimiter,
                dtype=str,
                chunksize=50_000,
                encoding=encoding,
                on_bad_lines="skip",
                low_memory=False,
            )
            row_offset = 0
            for chunk in pd.read_csv(path, **read_kwargs):
                normalized = normalize_chunk(chunk, resource, row_offset=row_offset)
                connection.register("incoming_chunk", normalized)
                connection.execute("INSERT INTO transactions SELECT * FROM incoming_chunk")
                total_rows += len(normalized)
                row_offset += len(normalized)
                connection.unregister("incoming_chunk")
            if progress_callback:
                progress_callback(file_index, total_files, f"Processado: {resource.name}")

        connection.execute("CREATE INDEX idx_bairro ON transactions(bairro)")
        connection.execute("CREATE INDEX idx_data ON transactions(data_quitacao)")
        connection.execute("CREATE INDEX idx_tipo ON transactions(tipo_construtivo)")
        connection.execute("CREATE INDEX idx_chave ON transactions(chave_tecnica)")
        stats = connection.execute(
            """
            SELECT
                COUNT(*) AS registros,
                MIN(data_quitacao) AS data_inicial,
                MAX(data_quitacao) AS data_final,
                COUNT(DISTINCT bairro) AS bairros
            FROM transactions
            """
        ).fetchone()
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    if DB_PATH.exists():
        DB_PATH.unlink()
    shutil.move(str(temp_db), str(DB_PATH))

    metadata = {
        "dataset_id": DATASET_ID,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "resources": [resource.__dict__ for resource in resources],
        "registros_lidos": total_rows,
        "registros": int(stats[0]),
        "registros_unicos": int(stats[0]),
        "data_inicial": str(stats[1]) if stats[1] else None,
        "data_final": str(stats[2]) if stats[2] else None,
        "bairros": int(stats[3]),
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def update_from_pbh(progress_callback=None, force_download: bool = False, include_historical: bool = True) -> dict:
    package = fetch_package_metadata()
    resources = select_csv_resources(package, include_historical=include_historical)
    if not resources:
        raise RuntimeError("O catálogo da PBH não retornou arquivos CSV do ITBI.")
    paths = download_resources(resources, progress_callback=progress_callback, force=force_download)
    metadata = build_database(resources, paths, progress_callback=progress_callback)
    metadata["escopo"] = "historico_completo" if include_historical else "base_recente"
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def build_demo_database() -> dict:
    demo_resource = Resource(
        resource_id="demo",
        name="Base de demonstração",
        url="local",
        modified=datetime.now().date().isoformat(),
        size=DEMO_PATH.stat().st_size if DEMO_PATH.exists() else None,
        hash_value=None,
    )
    return build_database([demo_resource], [DEMO_PATH])


def load_metadata() -> dict:
    if not METADATA_PATH.exists():
        return {}
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def database_exists() -> bool:
    return DB_PATH.exists() and DB_PATH.stat().st_size > 0


def connect_read_only() -> duckdb.DuckDBPyConnection:
    if not database_exists():
        raise FileNotFoundError("Base local ainda não foi criada.")
    return duckdb.connect(str(DB_PATH), read_only=True)
