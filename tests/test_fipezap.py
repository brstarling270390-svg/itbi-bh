import pandas as pd

from data_manager import (
    fipezap_factor,
    load_fipezap_bh_series,
)


def test_bundled_fipezap_series_has_belo_horizonte_history():
    series = load_fipezap_bh_series()
    assert not series.empty
    assert series["data"].min() <= pd.Timestamp("2019-01-01")
    assert series["data"].max() >= pd.Timestamp("2026-06-01")
    assert (series["numero_indice"] > 0).all()
    assert (series["preco_m2"] > 0).all()


def test_fipezap_factor_2019_to_latest():
    series = load_fipezap_bh_series()
    result = fipezap_factor(
        "2019-12-15",
        series=series,
    )
    assert result is not None
    assert result["factor"] > 1.5
    assert result["growth_pct"] > 50


def test_fipezap_factor_rejects_start_after_latest_month():
    series = load_fipezap_bh_series()
    future = series["data"].max() + pd.DateOffset(months=1)
    assert fipezap_factor(future, series=series) is None


def test_fipezap_factor_rejects_end_before_start():
    series = load_fipezap_bh_series()
    assert fipezap_factor(
        "2020-01-01",
        end_date="2019-12-01",
        series=series,
    ) is None
