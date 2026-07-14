from __future__ import annotations

from difflib import get_close_matches
import os
from threading import Lock
import time
import unicodedata
from typing import Any, Callable

import requests

DEFAULT_REVERSE_GEOCODER_URL = "https://nominatim.openstreetmap.org/reverse"
APP_USER_AGENT = "QuantoValeBH/2026.07 (+https://itbi-bh-bruno.streamlit.app/)"
_REVERSE_REQUEST_LOCK = Lock()
_LAST_REVERSE_REQUEST_AT = 0.0


def _normalize(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.upper().strip().split())


def normalize_geolocation_payload(payload: Any) -> dict[str, Any]:
    """Valida e normaliza o retorno do componente de GPS."""
    if not isinstance(payload, dict):
        return {"status": "idle"}

    error = payload.get("error")
    if error:
        return {
            "status": "error",
            "error": error,
            "message": payload.get("message") or "Não foi possível obter a localização.",
        }

    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
    except (TypeError, ValueError):
        return {"status": "idle"}

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return {
            "status": "error",
            "error": "invalid_coordinates",
            "message": "O navegador devolveu coordenadas inválidas.",
        }

    accuracy = payload.get("accuracy")
    try:
        accuracy_value = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError):
        accuracy_value = None

    return {
        "status": "ok",
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy_value,
    }


def rounded_coordinates(latitude: float, longitude: float, decimals: int = 5) -> tuple[float, float]:
    """Arredonda coordenadas para cache sem alterar a experiência de uso."""
    return round(float(latitude), decimals), round(float(longitude), decimals)


def reverse_geocode(
    latitude: float,
    longitude: float,
    *,
    endpoint: str | None = None,
    requester: Callable[..., Any] = requests.get,
    timeout: float = 12.0,
    min_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    """Converte coordenadas em endereço aproximado por consulta reversa."""
    global _LAST_REVERSE_REQUEST_AT

    url = endpoint or os.getenv("QV_REVERSE_GEOCODER_URL") or DEFAULT_REVERSE_GEOCODER_URL
    params = {
        "format": "jsonv2",
        "lat": float(latitude),
        "lon": float(longitude),
        "zoom": 18,
        "addressdetails": 1,
        "layer": "address",
        "accept-language": "pt-BR,pt",
    }
    headers = {
        "User-Agent": APP_USER_AGENT,
        "Referer": "https://itbi-bh-bruno.streamlit.app/",
    }

    # O endpoint público padrão pede no máximo uma requisição por segundo.
    # O lock também evita rajadas de duas sessões no mesmo processo.
    with _REVERSE_REQUEST_LOCK:
        if min_interval_seconds > 0:
            elapsed = time.monotonic() - _LAST_REVERSE_REQUEST_AT
            wait_for = max(0.0, min_interval_seconds - elapsed)
            if wait_for:
                time.sleep(wait_for)

        response = requester(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        _LAST_REVERSE_REQUEST_AT = time.monotonic()

    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Resposta inválida do serviço de localização.")
    return data


def is_belo_horizonte(reverse_result: dict[str, Any]) -> bool:
    """Confirma se o resultado reverso está em Belo Horizonte."""
    address = reverse_result.get("address") or {}
    candidates = [
        address.get("city"),
        address.get("town"),
        address.get("municipality"),
        reverse_result.get("display_name"),
    ]
    return any("BELO HORIZONTE" in _normalize(value) for value in candidates if value)


def match_bairro(reverse_result: dict[str, Any], bairros: list[str]) -> str | None:
    """Tenta associar o bairro retornado pelo mapa a um bairro existente na base PBH."""
    if not bairros:
        return None

    address = reverse_result.get("address") or {}
    candidates = [
        address.get("suburb"),
        address.get("neighbourhood"),
        address.get("quarter"),
        address.get("city_district"),
    ]
    normalized_map = {_normalize(item): item for item in bairros}

    for candidate in candidates:
        normalized = _normalize(candidate)
        if normalized in normalized_map:
            return normalized_map[normalized]

    for candidate in candidates:
        normalized = _normalize(candidate)
        if not normalized:
            continue
        # Alguns resultados do OSM acrescentam qualificadores ao nome do bairro.
        for bairro_norm, original in normalized_map.items():
            if bairro_norm and (bairro_norm in normalized or normalized in bairro_norm):
                return original

    normalized_candidates = [_normalize(item) for item in candidates if _normalize(item)]
    if normalized_candidates:
        choices = list(normalized_map)
        for candidate in normalized_candidates:
            matches = get_close_matches(candidate, choices, n=1, cutoff=0.84)
            if matches:
                return normalized_map[matches[0]]
    return None


def location_details(
    reverse_result: dict[str, Any],
    bairros: list[str],
) -> dict[str, Any]:
    """Extrai texto de endereço, rua, número e bairro compatível com a base PBH."""
    address = reverse_result.get("address") or {}
    road = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("residential")
        or address.get("path")
    )
    house_number = address.get("house_number")
    bairro = match_bairro(reverse_result, bairros)

    if road and house_number:
        search_text = f"{road} {house_number}"
    else:
        search_text = road or bairro or ""

    display_name = reverse_result.get("display_name") or search_text or "Localização detectada"
    return {
        "road": road,
        "house_number": house_number,
        "bairro": bairro,
        "search_text": str(search_text).strip(),
        "display_name": str(display_name).strip(),
        "in_belo_horizonte": is_belo_horizonte(reverse_result),
    }


def transaction_location_prefill(details: dict[str, Any]) -> dict[str, Any]:
    bairro = details.get("bairro")
    return {
        "text": details.get("search_text") or "",
        "bairros": [bairro] if bairro else [],
        "tipos": [],
    }


def valuation_location_prefill(details: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": details.get("search_text") or "",
        "bairro": details.get("bairro"),
    }


def geolocation_error_message(error: object, message: object = None) -> str:
    code = str(error) if error is not None else "unknown"
    mapping = {
        "1": "A permissão de localização foi negada. Libere o acesso ao GPS nas permissões do navegador e tente novamente.",
        "2": "O dispositivo não conseguiu determinar sua localização agora. Verifique se o serviço de localização está ativo.",
        "3": "A localização demorou mais do que o esperado. Tente novamente em um local com melhor sinal.",
        "invalid_coordinates": "O navegador devolveu uma localização inválida.",
    }
    return mapping.get(code, str(message or "Não foi possível obter sua localização."))


def location_confirmation_label(details: dict[str, Any]) -> str:
    parts: list[str] = []
    road = details.get("road")
    house_number = details.get("house_number")
    bairro = details.get("bairro")
    if road:
        parts.append(f"{road}{f', {house_number}' if house_number else ''}")
    if bairro:
        parts.append(str(bairro).title())
    return " · ".join(parts) or str(details.get("display_name") or "Localização detectada")
