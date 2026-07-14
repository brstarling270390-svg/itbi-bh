import pandas as pd

from data_manager import Resource, normalize_chunk, normalize_text, parse_ptbr_number


def test_normalize_text():
    assert normalize_text("Rua São José, 100") == "rua sao jose 100"


def test_parse_ptbr_number():
    result = parse_ptbr_number(pd.Series(["1.234.567,89", "10,5", ""]))
    assert result.iloc[0] == 1234567.89
    assert result.iloc[1] == 10.5
    assert pd.isna(result.iloc[2])


def test_normalize_chunk():
    raw = pd.DataFrame({
        "Endereco Completo": ["RUA TESTE 1"],
        "Bairro": ["Centro"],
        "Ano de Construcao (Unidade)": ["2020"],
        "Area Construida Adquirida": ["100,00"],
        "Tipo Construtivo Preponderante": ["AP"],
        "Valor Declarado": ["500.000,00"],
        "Valor Base Calculo": ["550.000,00"],
        "Data Quitacao": ["01/05/2026"],
    })
    resource = Resource("id", "teste", "local", None, None, None)
    result = normalize_chunk(raw, resource)
    assert result.loc[0, "valor_declarado"] == 500000
    assert result.loc[0, "valor_m2_declarado"] == 5000
    assert result.loc[0, "bairro"] == "CENTRO"


def test_database_update_lock_serializes_competing_sessions(tmp_path, monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    import data_manager

    monkeypatch.setattr(data_manager, "UPDATE_LOCK_PATH", tmp_path / ".update.lock")
    monkeypatch.setattr(data_manager, "DATA_DIR", tmp_path)

    active = 0
    max_active = 0
    guard = threading.Lock()

    def worker():
        nonlocal active, max_active
        with data_manager.database_update_lock(
            timeout_seconds=2,
            poll_interval=0.01,
            stale_after_seconds=60,
        ):
            with guard:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.08)
            with guard:
                active -= 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        for future in futures:
            future.result(timeout=3)

    assert max_active == 1
    assert not data_manager.UPDATE_LOCK_PATH.exists()


def test_database_update_lock_replaces_stale_orphan(tmp_path, monkeypatch):
    import os
    import time

    import data_manager

    lock_path = tmp_path / ".update.lock"
    lock_path.write_text("orphan", encoding="utf-8")
    old_time = time.time() - 3600
    os.utime(lock_path, (old_time, old_time))

    monkeypatch.setattr(data_manager, "UPDATE_LOCK_PATH", lock_path)
    monkeypatch.setattr(data_manager, "DATA_DIR", tmp_path)

    with data_manager.database_update_lock(
        timeout_seconds=0.2,
        poll_interval=0.01,
        stale_after_seconds=1,
    ):
        assert lock_path.exists()
        assert "pid=" in lock_path.read_text(encoding="utf-8")

    assert not lock_path.exists()


def test_database_update_lock_timeout_is_explicit(tmp_path, monkeypatch):
    import pytest

    import data_manager

    lock_path = tmp_path / ".update.lock"
    lock_path.write_text("active", encoding="utf-8")
    monkeypatch.setattr(data_manager, "UPDATE_LOCK_PATH", lock_path)
    monkeypatch.setattr(data_manager, "DATA_DIR", tmp_path)

    with pytest.raises(data_manager.DatabaseUpdateInProgressError):
        with data_manager.database_update_lock(
            timeout_seconds=0,
            poll_interval=0.01,
            stale_after_seconds=3600,
        ):
            pass


def test_second_concurrent_update_reuses_database_built_by_first(tmp_path, monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    import data_manager

    lock_path = tmp_path / ".update.lock"
    monkeypatch.setattr(data_manager, "UPDATE_LOCK_PATH", lock_path)
    monkeypatch.setattr(data_manager, "DATA_DIR", tmp_path)

    state = {
        "metadata": {
            "registros": 10,
            "registros_unicos": 10,
            "data_inicial": "2025-01-01",
            "data_final": "2026-01-01",
            "escopo": "base_recente",
        },
        "database_exists": False,
        "build_calls": 0,
    }
    guard = threading.Lock()

    monkeypatch.setattr(
        data_manager,
        "load_metadata",
        lambda: state["metadata"].copy(),
    )
    monkeypatch.setattr(
        data_manager,
        "database_exists",
        lambda: state["database_exists"],
    )
    monkeypatch.setattr(data_manager, "fetch_package_metadata", lambda: {"result": {}})
    fake_resource = data_manager.Resource("id", "arquivo.csv", "local", None, None, None)
    monkeypatch.setattr(
        data_manager,
        "select_csv_resources",
        lambda package, include_historical: [fake_resource],
    )
    monkeypatch.setattr(
        data_manager,
        "download_resources",
        lambda resources, progress_callback=None, force=False: [tmp_path / "arquivo.csv"],
    )
    monkeypatch.setattr(data_manager, "_atomic_write_text", lambda *args, **kwargs: None)

    def fake_build(resources, paths, progress_callback=None):
        with guard:
            state["build_calls"] += 1
        time.sleep(0.12)
        metadata = {
            "registros": 2500,
            "registros_unicos": 2500,
            "data_inicial": "2025-01-01",
            "data_final": "2026-06-01",
        }
        state["metadata"] = metadata
        state["database_exists"] = True
        return metadata

    monkeypatch.setattr(data_manager, "build_database", fake_build)

    def worker():
        result = data_manager.update_from_pbh(
            force_download=False,
            include_historical=False,
        )
        state["metadata"] = result.copy()
        return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        results = [future.result(timeout=5) for future in futures]

    assert state["build_calls"] == 1
    assert [result["registros"] for result in results] == [2500, 2500]
    assert all(result["escopo"] == "base_recente" for result in results)


def test_force_download_does_not_reuse_existing_database(tmp_path, monkeypatch):
    import data_manager

    monkeypatch.setattr(data_manager, "UPDATE_LOCK_PATH", tmp_path / ".update.lock")
    monkeypatch.setattr(data_manager, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        data_manager,
        "load_metadata",
        lambda: {
            "registros": 2500,
            "data_inicial": "2025-01-01",
            "escopo": "base_recente",
        },
    )
    monkeypatch.setattr(data_manager, "database_exists", lambda: True)
    monkeypatch.setattr(data_manager, "fetch_package_metadata", lambda: {"result": {}})
    fake_resource = data_manager.Resource("id", "arquivo.csv", "local", None, None, None)
    monkeypatch.setattr(
        data_manager,
        "select_csv_resources",
        lambda package, include_historical: [fake_resource],
    )
    monkeypatch.setattr(
        data_manager,
        "download_resources",
        lambda resources, progress_callback=None, force=False: [tmp_path / "arquivo.csv"],
    )
    monkeypatch.setattr(data_manager, "_atomic_write_text", lambda *args, **kwargs: None)

    calls = []

    def fake_build(resources, paths, progress_callback=None):
        calls.append(True)
        return {
            "registros": 2600,
            "registros_unicos": 2600,
            "data_inicial": "2025-01-01",
            "data_final": "2026-07-01",
        }

    monkeypatch.setattr(data_manager, "build_database", fake_build)

    result = data_manager.update_from_pbh(
        force_download=True,
        include_historical=False,
    )

    assert len(calls) == 1
    assert result["registros"] == 2600


def test_build_database_uses_unique_build_file_and_cleans_failed_build(tmp_path, monkeypatch):
    import data_manager
    import pytest

    monkeypatch.setattr(data_manager, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_manager, "DB_PATH", tmp_path / "itbi_bh.duckdb")
    monkeypatch.setattr(data_manager, "METADATA_PATH", tmp_path / "metadata.json")

    invalid_csv = tmp_path / "invalid.csv"
    invalid_csv.write_text("foo;bar\n1;2\n", encoding="utf-8")
    resource = data_manager.Resource("bad", "invalido", "local", None, None, None)

    with pytest.raises(RuntimeError):
        data_manager.build_database([resource], [invalid_csv], minimum_records=1)

    assert list(tmp_path.glob("itbi_bh.build-*.duckdb")) == []
    assert list(tmp_path.glob("itbi_bh.build-*.duckdb.wal")) == []


def test_real_duckdb_build_survives_two_concurrent_initial_updates(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    import duckdb
    import data_manager

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_path = tmp_path / "itbi.csv"
    header = (
        "Endereco Completo;Bairro;Ano de Construcao (Unidade);"
        "Area Construida Adquirida;Tipo Construtivo Preponderante;"
        "Valor Declarado;Valor Base Calculo;Data Quitacao\n"
    )
    rows = [
        f"RUA TESTE {index};Centro;2020;100,00;AP;500.000,00;550.000,00;01/05/2026"
        for index in range(1000)
    ]
    csv_path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")

    monkeypatch.setattr(data_manager, "DATA_DIR", data_dir)
    monkeypatch.setattr(data_manager, "RAW_DIR", data_dir / "raw")
    monkeypatch.setattr(data_manager, "DB_PATH", data_dir / "itbi_bh.duckdb")
    monkeypatch.setattr(data_manager, "METADATA_PATH", data_dir / "metadata.json")
    monkeypatch.setattr(data_manager, "UPDATE_LOCK_PATH", data_dir / ".update.lock")
    monkeypatch.setattr(data_manager, "fetch_package_metadata", lambda: {"result": {}})

    resource = data_manager.Resource("id", "arquivo.csv", "local", None, None, None)
    monkeypatch.setattr(
        data_manager,
        "select_csv_resources",
        lambda package, include_historical: [resource],
    )
    monkeypatch.setattr(
        data_manager,
        "download_resources",
        lambda resources, progress_callback=None, force=False: [csv_path],
    )

    def worker():
        return data_manager.update_from_pbh(
            force_download=False,
            include_historical=False,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [future.result(timeout=20) for future in [
            executor.submit(worker),
            executor.submit(worker),
        ]]

    assert [result["registros"] for result in results] == [1000, 1000]
    assert all(result["escopo"] == "base_recente" for result in results)
    assert not data_manager.UPDATE_LOCK_PATH.exists()
    assert list(data_dir.glob("itbi_bh.build-*.duckdb")) == []
    assert list(data_dir.glob("itbi_bh.build-*.duckdb.wal")) == []

    with duckdb.connect(str(data_manager.DB_PATH), read_only=True) as con:
        assert con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 1000
        assert con.execute("SELECT COUNT(*) FROM duckdb_tables() WHERE table_name = 'transactions'").fetchone()[0] == 1
