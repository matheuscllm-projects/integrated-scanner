"""Defeitos reproduzidos pela revisão independente do PR #38 (um bloco por item)."""
import json
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
import api_store
import run_integrated as run
from cross_source import group_cross_source
from delivery import build_cross_source_markdown, build_markdown
from normalize import Deal

CLEAN = dict(price_status="real", validation_status="VALIDATED_REAL",
             link_tcg="https://example.org/ref", link_oferta="https://example.org/offer")


def deal(compra, ref, **kw):
    base = dict(fonte="CardTrader", carta="Carta", numero="1", set_name="Set",
                compra_brl=compra, ref_brl=ref, **CLEAN)
    base.update(kw)
    return Deal(**base)


# ── M3: exibição nunca contradiz o corte ────────────────────────────────────
def test_m3_below_cut_margin_is_never_displayed_as_30():
    d = deal(70.04, 100)                       # 29,96% -> fora do corte
    assert d.margem_venda_pct < 30
    md = build_markdown([d], [], 5.0, 30.0)
    row = next(l for l in md.splitlines() if "| Carta 1 |" in l)
    assert "30.0%" not in row and "29.9%" in row
    assert d.to_row()["Margem venda %"] < 30
    store = api_store.build_store([d], [], scope=["X"], fx=5, min_margin=30.0, stamp="T")
    assert store["deals"][0]["margem_venda_pct"] < 30
    a = deal(70.04, 100, fonte="MYP", numero="5", set_name="Surging Sparks", carta="Pikachu")
    b = deal(80, 100, numero="5", set_name="Surging Sparks", carta="Pikachu")
    cross = build_cross_source_markdown(group_cross_source([a, b]))
    assert "30.0" not in cross.split("Links |")[1]


def test_m3_exact_values_are_not_shaved_by_float_noise():
    md = build_markdown([deal(60, 100), deal(70, 100, carta="Edge")], [], 5.0, 30.0)
    assert "40.0%" in md and "30.0%" in md      # 30,0 exato continua 30,0
