import json
import threading

import duckdb
import pytest

import data_manager as dm
from data_manager import (
    DatabaseUpdateInProgressError,
    Resource,
    database_update_lock,
)


def test_database_update_lock_blocks_second_session(tmp_path):
    lock_path = tmp_path / ".pbh_update.lock"

    with database_update_lock(lock_path=lock_path):
        assert lock_path.exists()
        with pytest.raises(DatabaseUpdateInProgressError, match="já está sendo atualizada"):
            with database_update_lock(lock_path=lock_path):
                pass

    # O arquivo pode permanecer; o lock do sistema operacional é que define o uso.
    assert lock_path.exists()


def test_database_update_lock_can_be_reacquired_after_release(tmp_path):
    lock_path = tmp_path / ".pbh_update.lock"

    with database_update_lock(lock_path=lock_path):
        first_payload = json.loads(lock_path.read_text(encoding="utf-8"))

    with database_update_lock(lock_path=lock_path):
        second_payload = json.loads(lock_path.read_text(encoding="utf-8"))

    assert first_payload["pid"] == second_payload["pid"]
    assert "started_at" in second_payload


def test_update_from_pbh_rejects_concurrent_rebuild(monkeypatch, tmp_path):
    lock_path = tmp_path / ".pbh_update.lock"
    metadata_path = tmp_path / "metadata.json"
    entered_fetch = threading.Event()
    release_fetch = threading.Event()
    first_errors = []

    resource = Resource(
        resource_id="recurso",
        name="ITBI Relatorios 2026 Janeiro",
        url="https://example.invalid/itbi.csv",
        modified=None,
        size=None,
        hash_value=None,
    )

    def fake_fetch_package_metadata():
        entered_fetch.set()
        if not release_fetch.wait(timeout=5):
            raise RuntimeError("O teste não liberou a primeira atualização.")
        return {"resources": []}

    monkeypatch.setattr(dm, "UPDATE_LOCK_PATH", lock_path)
    monkeypatch.setattr(dm, "METADATA_PATH", metadata_path)
    monkeypatch.setattr(dm, "fetch_package_metadata", fake_fetch_package_metadata)
    monkeypatch.setattr(dm, "select_csv_resources", lambda package, include_historical=True: [resource])
    monkeypatch.setattr(dm, "download_resources", lambda *args, **kwargs: [tmp_path / "itbi.csv"])
    monkeypatch.setattr(
        dm,
        "build_database",
        lambda *args, **kwargs: {
            "registros": 1_500,
            "registros_unicos": 1_500,
            "data_final": "2026-06-30",
        },
    )

    def first_update():
        try:
            dm.update_from_pbh(include_historical=True)
        except Exception as exc:  # noqa: BLE001
            first_errors.append(exc)

    thread = threading.Thread(target=first_update)
    thread.start()
    assert entered_fetch.wait(timeout=2)

    with pytest.raises(DatabaseUpdateInProgressError, match="outra sessão"):
        dm.update_from_pbh(include_historical=True)

    release_fetch.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert first_errors == []
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["escopo"] == "historico_completo"


def test_failed_rebuild_cleans_unique_temp_and_preserves_main_db(monkeypatch, tmp_path):
    db_path = tmp_path / "itbi_bh.duckdb"
    metadata_path = tmp_path / "metadata.json"
    csv_path = tmp_path / "itbi.csv"

    with duckdb.connect(str(db_path)) as con:
        con.execute("CREATE TABLE sentinel (value INTEGER)")
        con.execute("INSERT INTO sentinel VALUES (7)")

    csv_path.write_text(
        ";".join(
            [
                "Endereco Completo",
                "Bairro",
                "Area Construida Adquirida",
                "Tipo Construtivo Preponderante",
                "Valor Declarado",
                "Valor Base Calculo",
                "Data Quitacao",
            ]
        )
        + "\n"
        + ";".join(
            [
                "RUA TESTE 1",
                "CENTRO",
                "100,00",
                "AP",
                "500.000,00",
                "550.000,00",
                "01/05/2026",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resource = Resource("id", "ITBI Relatorios 2026 Janeiro", "local", None, None, None)

    monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dm, "DB_PATH", db_path)
    monkeypatch.setattr(dm, "METADATA_PATH", metadata_path)

    with pytest.raises(RuntimeError, match="apenas 1 registros"):
        dm.build_database([resource], [csv_path], minimum_records=2)

    with duckdb.connect(str(db_path), read_only=True) as con:
        assert con.execute("SELECT value FROM sentinel").fetchone()[0] == 7

    leftovers = list(tmp_path.glob(".itbi_bh.*.tmp.duckdb*"))
    assert leftovers == []
    assert not metadata_path.exists()
