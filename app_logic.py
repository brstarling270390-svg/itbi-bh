from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any


HYBRID_SCROLL_SEQUENCE = "_hybrid_scroll_sequence"
HYBRID_SCROLL_PENDING = "_hybrid_scroll_pending"


def comparable_source_exclusions(
    source_registro_id: str | None,
    source_chave_tecnica: str | None,
) -> tuple[list[str], list[str]]:
    """Retorna filtros SQL que removem apenas a transação de origem e suas cópias."""
    clauses: list[str] = []
    params: list[str] = []

    if source_registro_id:
        clauses.append("registro_id <> ?")
        params.append(str(source_registro_id))

    if source_chave_tecnica:
        clauses.append("chave_tecnica <> ?")
        params.append(str(source_chave_tecnica))

    return clauses, params


def selected_source_identifiers(
    row: Any,
) -> dict[str, str | None]:
    """Transporta os identificadores da transação selecionada para a avaliação."""
    return {
        "source_registro_id": str(row["registro_id"]),
        "source_chave_tecnica": str(row["chave_tecnica"]),
    }


def evaluate_selected_transaction(
    evaluator: Callable[..., Any],
    row: Any,
    **evaluation_kwargs: Any,
) -> Any:
    """Executa a avaliação encaminhando os identificadores da linha selecionada."""
    return evaluator(
        **evaluation_kwargs,
        **selected_source_identifiers(row),
    )


def exclude_source_rows(
    rows: Any,
    source_registro_id: str | None,
    source_chave_tecnica: str | None,
) -> Any:
    """Exclui a origem e cópias equivalentes de um conjunto já carregado."""
    filtered = rows
    if source_registro_id:
        filtered = filtered[
            filtered["registro_id"].astype(str).ne(str(source_registro_id))
        ]
    if source_chave_tecnica:
        filtered = filtered[
            filtered["chave_tecnica"].astype(str).ne(str(source_chave_tecnica))
        ]
    return filtered.copy()


def next_hybrid_scroll_token(state: MutableMapping[str, Any]) -> int:
    """Gera um token crescente para forçar uma nova rolagem a cada cálculo."""
    token = int(state.get(HYBRID_SCROLL_SEQUENCE, 0)) + 1
    state[HYBRID_SCROLL_SEQUENCE] = token
    state[HYBRID_SCROLL_PENDING] = token
    return token


def store_hybrid_result(
    state: MutableMapping[str, Any],
    *,
    local_rows: Any,
    building_rows: Any,
    stats: dict,
    subject: dict,
) -> int:
    """Armazena um cálculo híbrido concluído e cria uma nova solicitação de rolagem."""
    state["hybrid_local"] = local_rows
    state["hybrid_building"] = building_rows
    state["hybrid_stats"] = stats
    state["hybrid_subject"] = subject
    return next_hybrid_scroll_token(state)


def consume_hybrid_scroll(state: MutableMapping[str, Any]) -> int | None:
    """Consome o token pendente; cada novo cálculo recebe um token diferente."""
    token = state.pop(HYBRID_SCROLL_PENDING, None)
    return int(token) if token is not None else None
