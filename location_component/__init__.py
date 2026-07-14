from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import streamlit.components.v1 as components

_BUILD_DIR = Path(__file__).resolve().parent / "frontend" / "build"
_component: Callable[..., Any] | None = None

_DEFAULT_LOCATION = {
    "latitude": None,
    "longitude": None,
    "altitude": None,
    "accuracy": None,
    "altitudeAccuracy": None,
    "heading": None,
    "speed": None,
    "error": None,
    "message": None,
}


def _get_component() -> Callable[..., Any]:
    """Declara o componente somente quando o usuário realmente abre o GPS."""
    global _component
    if _component is None:
        _component = components.declare_component(
            "quanto_vale_bh_geolocation",
            path=str(_BUILD_DIR),
        )
    return _component


def current_location(*, key: str) -> dict[str, Any]:
    """Exibe um botão que solicita a localização do navegador e devolve as coordenadas."""
    value = _get_component()(key=key, default=_DEFAULT_LOCATION)
    return value if isinstance(value, dict) else _DEFAULT_LOCATION.copy()
