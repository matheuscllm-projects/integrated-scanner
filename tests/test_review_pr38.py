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


# ── B2: None é None, sem sentinela 0 ─────────────────────────────────────────
def test_b2_best_margin_is_none_when_no_margin_exists():
    a = deal(0, 100, fonte="MYP", numero="5", set_name="Surging Sparks", carta="Pikachu")
    b = deal(80, 0, numero="5", set_name="Surging Sparks", carta="Pikachu")
    card = group_cross_source([a, b])[0]
    assert card.best_margin is None


def test_b2_card_without_margin_sorts_after_negative_margin():
    def pair(name, num, ca, cb, ra=100, rb=100):
        return [deal(ca, ra, fonte="MYP", numero=num, set_name="Surging Sparks", carta=name),
                deal(cb, rb, numero=num, set_name="Surging Sparks", carta=name)]
    neg = pair("Neg", "1", 120, 130)             # margem negativa (-20%)
    sem = pair("Sem", "2", 0, 0)                 # sem margem
    cards = group_cross_source(neg + sem)
    assert [c.display_name for c in cards] == ["Neg", "Sem"]


# ── B1: filtro e ordenação da API tratam None como ausência ──────────────────
@pytest.fixture
def client():
    return TestClient(api.app)


def _store(deals):
    return api_store.build_store(deals, [], scope=["X"], fx=5, min_margin=30.0, stamp="T")


def test_b1_min_margin_zero_excludes_rows_without_margin(client, monkeypatch):
    store = _store([deal(60, 100, carta="Com"), deal(0, 100, carta="Sem"), deal(120, 100, carta="Neg")])
    monkeypatch.setattr(api_store, "load_store", lambda *a, **k: store)
    body = client.get("/deals", params={"min_margin": 0}).json()
    assert [d["carta"] for d in body["deals"]] == ["Com"]
    assert body["sem_margem"] == 1


def test_b1_rows_without_margin_go_last_and_are_counted(client, monkeypatch):
    store = _store([deal(0, 100, carta="Sem"), deal(120, 100, carta="Neg"), deal(60, 100, carta="Com")])
    monkeypatch.setattr(api_store, "load_store", lambda *a, **k: store)
    body = client.get("/deals").json()
    assert [d["carta"] for d in body["deals"]] == ["Com", "Neg", "Sem"]
    assert body["sem_margem"] == 1


# ── M2: store de schema antigo nunca é servido ───────────────────────────────
OLD_STORE = {"schema_version": 1, "stamp": "OLD", "deal_count": 1, "sources": [],
             "deals": [{"carta": "Velha", "fonte": "MYP", "margem_antiga": 33.3}]}


@pytest.mark.parametrize("url", ["/deals?min_margin=30", "/deals", "/status", "/sources"])
def test_m2_old_schema_store_is_refused_not_served(client, monkeypatch, tmp_path, url):
    p = tmp_path / "deals_store.json"
    p.write_text(json.dumps(OLD_STORE), encoding="utf-8")
    monkeypatch.setattr(api_store, "STORE_PATH", p)
    r = client.get(url)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "schema" in detail and "novo scan" in detail
    assert "Velha" not in r.text and "margem_antiga" not in r.text


def test_m2_store_without_schema_version_is_refused(client, monkeypatch, tmp_path):
    p = tmp_path / "deals_store.json"
    p.write_text(json.dumps({"deals": []}), encoding="utf-8")
    monkeypatch.setattr(api_store, "STORE_PATH", p)
    assert client.get("/deals").status_code == 409


def test_m2_root_reports_incompatible_store_instead_of_last_run(client, monkeypatch, tmp_path):
    p = tmp_path / "deals_store.json"
    p.write_text(json.dumps(OLD_STORE), encoding="utf-8")
    monkeypatch.setattr(api_store, "STORE_PATH", p)
    body = client.get("/").json()
    assert body["last_run"] is None and "novo scan" in body["store_error"]


def test_m2_current_schema_store_is_served(client, monkeypatch, tmp_path):
    p = tmp_path / "deals_store.json"
    api_store.save_store(_store([deal(60, 100)]), path=p, keep_history=False)
    monkeypatch.setattr(api_store, "STORE_PATH", p)
    assert client.get("/deals").json()["count"] == 1
