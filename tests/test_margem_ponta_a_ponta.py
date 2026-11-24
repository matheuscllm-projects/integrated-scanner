"""Margem sobre a venda de PONTA A PONTA, por leitor de fonte (substitui a trava por nome).

Cenario unico: compra 75, referencia 100 (ROI 33,3%, margem 25%). Em CADA fonte, lido do
arquivo real do formato dela, tem de dar margem 25%, ficar FORA do corte de 30%, cair em
"Abaixo do corte" na tabela de entrega e ser excluido de /deals?min_margin=30 na API."""
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
import api_store
from delivery import bucket_for, build_markdown, filter_deals
from normalize import read_comc, read_ct, read_liga, read_myp

FX = 5.0


def _ct(tmp_path):
    p = tmp_path / 'ct.xlsx'
    row = {'Card Name': 'Alvo', 'Set': 'S (x)', 'Nº': '001', 'Scan R$ (raw)': 75,
           'TCG Market (BRL)': 100, 'TCG Market (USD)': 20, 'Validation Status': 'VALIDATED_REAL',
           'Link CardTrader': 'https://example.org/o', 'Link TCG': 'https://example.org/r'}
    with pd.ExcelWriter(p) as w:
        pd.DataFrame([row]).to_excel(w, sheet_name='Oportunidades', index=False)
    return read_ct(p, FX)


def _myp(tmp_path):
    p = tmp_path / 'myp.xlsx'
    row = {'Card Name': 'Alvo (1/100)', 'Edition': 'SV: X', 'MYP EN NM (R$)': 75,
           'TCG Player (R$)': 100, 'TCG US$': 20, 'TCG Source': 'real (tcgcsv)',
           'URL': 'https://example.org/o', 'TCG URL': 'https://example.org/r'}
    with pd.ExcelWriter(p) as w:
        pd.DataFrame([row]).to_excel(w, sheet_name='All EN Cards', index=False)
    return read_myp(p, FX)


def _comc(tmp_path):
    p = tmp_path / 'comc.csv'
    pd.DataFrame([{'card': 'Alvo - 1/100', 'set': 'S', 'comc_price': 15.0, 'tcg_reference': 20.0,
                   'comc_url': 'https://example.org/o', 'tcg_url': 'https://example.org/r'}]
                 ).to_csv(p, index=False)
    return read_comc(p, FX)


def _liga(tmp_path):
    p = tmp_path / 'liga.json'
    p.write_text(json.dumps([{'card_name': 'Alvo', 'set_name': 'S', 'price_liga_brl': 75.0,
                              'price_tcg_brl': 100.0, 'price_tcg_usd': 20.0, 'exchange_rate': FX,
                              'liga_url': 'https://example.org/o', 'tcg_url': 'https://example.org/r',
                              'status': 'approved'}]), encoding='utf-8')
    return read_liga(p, FX)


READERS = {'CardTrader': _ct, 'MYP': _myp, 'COMC': _comc, 'Liga': _liga}


@pytest.mark.parametrize('fonte', sorted(READERS))
def test_75_over_100_is_25_percent_and_out_of_cut_end_to_end(fonte, tmp_path, monkeypatch):
    deals = READERS[fonte](tmp_path)
    assert len(deals) == 1 and deals[0].fonte == fonte
    d = deals[0]
    assert d.margem_venda_pct == pytest.approx(25.0)
    assert d.roi_aquisicao_pct == pytest.approx(33.333, abs=1e-2)
    assert filter_deals(deals, 30.0) == []
    assert bucket_for(d, 30.0).startswith('Abaixo do corte')

    md = build_markdown(deals, [], FX, 30.0)
    section = md.split('## Abaixo do corte')[1]
    row = next(line for line in section.splitlines() if '| 1 |' in line)
    cells = [c.strip() for c in row.split('|')]
    assert '25.0%' in cells and '33.3%' in cells and '30.0%' not in cells
    for clean in ('## Deals limpos', '## Validar manualmente'):
        assert clean not in md

    store = api_store.build_store(deals, [], scope=['X'], fx=FX, min_margin=30.0, stamp='T')
    assert store['deals'][0]['margem_venda_pct'] == pytest.approx(25.0)
    assert store['deals'][0]['bucket'].startswith('Abaixo do corte')
    monkeypatch.setattr(api_store, 'load_store', lambda *a, **k: store)
    client = TestClient(api.app)
    assert client.get('/deals', params={'min_margin': 30}).json()['count'] == 0
    body = client.get('/deals', params={'min_margin': 25}).json()
    assert body['count'] == 1 and body['deals'][0]['margem_venda_pct'] == pytest.approx(25.0)
