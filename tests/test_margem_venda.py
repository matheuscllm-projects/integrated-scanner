"""Margem SOBRE A VENDA (referência) é a única base do corte de 30%.

Decisão do dono: margem = (referência − compra) / referência alimenta o corte;
ROI = (referência − compra) / compra é métrica SEPARADA, exibida à parte e
nunca usada no corte. Nenhum nome ambíguo (`margem_pct`, "Margem bruta %")."""
import pytest

import api
import api_store
from cross_source import group_cross_source
from delivery import bucket_for, build_cross_source_markdown, build_markdown, filter_deals
from normalize import (UNIFIED_COLUMNS, Deal, comc_row_to_deal, ct_row_to_deal,
                       liga_row_to_deal, myp_row_to_deal, roi_pct, sale_margin_pct)

CLEAN = dict(price_status="real", validation_status="VALIDATED_REAL",
             link_tcg="https://example.org/ref", link_oferta="https://example.org/offer")


def deal(compra, ref, **kw):
    base = dict(fonte="CardTrader", carta="Carta", numero="1", set_name="Set",
                compra_brl=compra, ref_brl=ref, **CLEAN)
    base.update(kw)
    return Deal(**base)


def test_sale_margin_is_over_reference():
    assert sale_margin_pct(100.0, 75.0) == pytest.approx(25.0)
    assert sale_margin_pct(100.0, 70.0) == pytest.approx(30.0)


def test_roi_is_over_purchase_and_separate():
    assert roi_pct(100.0, 75.0) == pytest.approx(33.3333, abs=1e-3)
    assert roi_pct(100.0, 70.0) == pytest.approx(42.857, abs=1e-3)


@pytest.mark.parametrize("ref,compra", [(0, 50), (100, 0), (-1, 50), (100, -5), (float("nan"), 50)])
def test_invalid_prices_never_yield_a_number(ref, compra):
    assert sale_margin_pct(ref, compra) is None
    assert roi_pct(ref, compra) is None


def test_deal_exposes_both_metrics_derived_from_prices():
    d = deal(75, 100)
    assert d.margem_venda_pct == pytest.approx(25.0)
    assert d.roi_aquisicao_pct == pytest.approx(33.333, abs=1e-2)
    assert deal(0, 100).margem_venda_pct is None
    assert deal(50, 0).roi_aquisicao_pct is None


def test_cut_is_30_percent_on_sale_not_roi():
    below = deal(75, 100)     # ROI 33,3% passaria na base antiga; margem 25% NÃO passa
    edge = deal(70, 100)      # margem exatamente 30%
    above = deal(60, 100)     # margem 40%
    kept = filter_deals([below, edge, above], 30.0)
    assert [d.compra_brl for d in kept] == [60, 70]
    assert bucket_for(below).startswith("Abaixo do corte")
    assert bucket_for(edge) == "Deals limpos — referência real"


def test_every_source_uses_sale_margin():
    ct = ct_row_to_deal({"Card Name": "A", "Set": "S (x)", "TCG Market (BRL)": 100,
                         "TCG Market (USD)": 20, "Scan R$ (raw)": 75}, 5)
    myp = myp_row_to_deal({"Card Name": "A (1/100)", "MYP EN NM (R$)": 75,
                           "TCG Player (R$)": 100, "TCG US$": 20, "TCG Source": "real (tcgcsv)"}, 5)
    comc = comc_row_to_deal({"card": "A", "comc_price": 15.0, "tcg_reference": 20.0}, 5.0)
    liga = liga_row_to_deal({"card_name": "A", "price_liga_brl": 75, "price_tcg_brl": 100,
                             "price_tcg_usd": 20, "exchange_rate": 5}, 5)
    for d in (ct, myp, comc, liga):
        assert d.margem_venda_pct == pytest.approx(25.0), d.fonte
        assert d.roi_aquisicao_pct == pytest.approx(33.333, abs=1e-2), d.fonte


def test_unified_columns_have_unambiguous_names():
    assert "Margem bruta %" not in UNIFIED_COLUMNS
    assert "Margem venda %" in UNIFIED_COLUMNS and "ROI aquisição %" in UNIFIED_COLUMNS
    row = deal(75, 100).to_row()
    assert row["Margem venda %"] == 25.0 and row["ROI aquisição %"] == 33.3
    assert deal(0, 100).to_row()["Margem venda %"] == ""      # nunca "0.0" inventado


def test_delivery_labels_and_shows_roi_apart():
    md = build_markdown([deal(60, 100)], [], 5.0, 30.0)
    assert "| Margem venda % |" in md and "| ROI aquisição % |" in md
    assert "| Margem % |" not in md
    assert "(base = referência" in md and "base = preço de compra" not in md
    row = next(l for l in md.splitlines() if "| Carta 1 |" in l)
    cells = [c.strip() for c in row.split("|")]
    assert "40.0%" in cells and "66.7%" in cells        # margem 40% e ROI 66,7% lado a lado


def test_cross_source_table_uses_sale_margin_and_roi():
    a = deal(60, 100, fonte="MYP", numero="5", set_name="Surging Sparks", carta="Pikachu")
    b = deal(80, 100, fonte="CardTrader", numero="5", set_name="Surging Sparks", carta="Pikachu")
    cards = group_cross_source([a, b])
    assert cards and cards[0].best_margin == pytest.approx(40.0)
    md = build_cross_source_markdown(cards)
    assert "Margem venda %" in md and "ROI aquisição %" in md and "| Margem % |" not in md


def test_api_store_and_filter_use_sale_margin():
    low = deal(75, 100, carta="Low")      # margem 25 / ROI 33,3
    high = deal(60, 100, carta="High")    # margem 40 / ROI 66,7
    store = api_store.build_store([low, high], [], scope=["SFA"], fx=5.2, min_margin=30.0, stamp="T")
    rows = {d["carta"]: d for d in store["deals"]}
    assert rows["High"]["margem_venda_pct"] == pytest.approx(40.0)
    assert rows["High"]["roi_aquisicao_pct"] == pytest.approx(66.667, abs=1e-2)
    assert "margem_pct" not in rows["High"]
    assert rows["Low"]["bucket"].startswith("Abaixo do corte")
