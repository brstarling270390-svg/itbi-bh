from __future__ import annotations

import json
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


def validate_frontend_assets(build_dir: Path = _BUILD_DIR) -> list[Path]:
    """Valida se todos os arquivos estáticos necessários do componente foram empacotados."""
    required = [
        build_dir / "index.html",
        build_dir / "asset-manifest.json",
    ]

    manifest_path = build_dir / "asset-manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "Os arquivos do botão de localização estão corrompidos."
            ) from exc
        for relative_path in manifest.get("files", {}).values():
            normalized = str(relative_path).removeprefix("./")
            required.append(build_dir / normalized)

    missing = sorted({path for path in required if not path.is_file()})
    if missing:
        missing_text = ", ".join(str(path.relative_to(build_dir.parent)) for path in missing)
        raise RuntimeError(
            "Os arquivos do botão de localização não foram incluídos na publicação: "
            f"{missing_text}"
        )
    return sorted(set(required))


def _get_component() -> Callable[..., Any]:
    """Declara o componente somente quando o usuário realmente abre o GPS."""
    global _component
    if _component is None:
        validate_frontend_assets()
        _component = components.declare_component(
            "quanto_vale_bh_geolocation",
            path=str(_BUILD_DIR),
        )
    return _component


def current_location(*, key: str) -> dict[str, Any]:
    """Exibe um botão que solicita a localização do navegador e devolve as coordenadas."""
    value = _get_component()(key=key, default=_DEFAULT_LOCATION)
    return value if isinstance(value, dict) else _DEFAULT_LOCATION.copy()
