"""PR #38 revisao: M1 (status de fonte), B6 (cambio ausente), B7 (linha fora do contrato)."""
import json
import sys

import pandas as pd
import pytest

import normalize
import run_integrated as run
from delivery import SourceStatus
from normalize import CT_RAW_REQUIRED, comc_row_to_deal, read_liga

RAW_CT = {'Card Name': 'Eevee', 'Set': 'Prismatic Evolutions (pre)', 'Nº': '074',
          'Scan R$ (raw)': 100, 'LIVE R$ (real)': 100, 'TCG Market (BRL)': 200,
          'TCG Market (USD)': 40, 'Validation Status': 'VALIDATED_REAL',
          'Link CardTrader': 'https://example.org/offer', 'Link TCG': 'https://example.org/ref'}
LIGA = {'card_name': 'A', 'set_name': 'S', 'price_liga_brl': 60.0, 'price_tcg_brl': 100.0,
        'liga_url': 'https://example.org/liga', 'status': 'approved'}


def _xlsx(path, rows, sheet='Oportunidades', columns=None):
    df = pd.DataFrame(rows, columns=columns) if columns else pd.DataFrame(rows)
    with pd.ExcelWriter(path) as w:
        df.to_excel(w, sheet_name=sheet, index=False)
    return path


def _run(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(run, 'OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr(run, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(run, 'fresh_fx', lambda: 5)
    stores = []
    monkeypatch.setattr(run, 'save_store', lambda data, **kw: stores.append(data))
    monkeypatch.setattr(sys, 'argv', ['run'] + argv)
    code = run.main()
    return code, stores[0]


def _ct(monkeypatch, tmp_path, rows, columns=None):
    p = _xlsx(tmp_path / 'scan.xlsx', rows, columns=columns)
    return _run(monkeypatch, tmp_path, ['--skip-scan', '--sources', 'ct', '--ct-output', str(p)])


def _liga(monkeypatch, tmp_path, rows):
    p = tmp_path / 'r.json'
    p.write_text(json.dumps(rows), encoding='utf-8')
    return _run(monkeypatch, tmp_path, ['--skip-scan', '--sources', 'liga', '--liga-report', str(p)])


# ── M1 ────────────────────────────────────────────────────────────────────────
def test_m1_a_header_only_is_explicit_empty_source(monkeypatch, tmp_path):
    code, store = _ct(monkeypatch, tmp_path, [], columns=list(CT_RAW_REQUIRED))
    assert store['sources'][0]['status'] == 'ok (fonte sem linhas)'
    assert code == 0 and store['run_status'] == 'done'


def test_m1_b_no_row_with_reference_is_no_coverage_not_ok(monkeypatch, tmp_path):
    rows = [dict(RAW_CT, **{'TCG Market (BRL)': None}), dict(RAW_CT, **{'TCG Market (BRL)': None})]
    code, store = _ct(monkeypatch, tmp_path, rows)
    st = store['sources'][0]['status']
    assert st.startswith('sem cobertura') and not st.startswith('ok')
    assert code != 0 and store['run_status'] != 'done'
    assert len(store['deals']) == 2                      # nenhuma linha some


def test_m1_partial_rows_without_reference_report_the_count(monkeypatch, tmp_path):
    rows = [RAW_CT, dict(RAW_CT, **{'Card Name': 'Sem', 'TCG Market (BRL)': None})]
    code, store = _ct(monkeypatch, tmp_path, rows)
    st = store['sources'][0]['status']
    assert st.startswith('parcial') and '1 de 2' in st
    assert code == 2 and store['run_status'] == 'partial'
    ok = next(d for d in store['deals'] if d['carta'] == 'Eevee')
    assert 'coleta parcial' not in '; '.join(ok['review_reasons'])   # parcial de LINHAS, nao de coleta


def test_m1_valid_file_with_priced_rows_is_ok(monkeypatch, tmp_path):
    code, store = _ct(monkeypatch, tmp_path, [RAW_CT])
    assert store['sources'][0]['status'].startswith('ok')
    assert code == 0 and store['run_status'] == 'done'


def test_m1_liga_empty_list_is_explicit_empty_source(monkeypatch, tmp_path):
    code, store = _liga(monkeypatch, tmp_path, [])
    assert 'fonte sem linhas' in store['sources'][0]['status'] and code == 0


def test_m1_liga_rows_without_any_price_is_no_coverage(monkeypatch, tmp_path):
    code, store = _liga(monkeypatch, tmp_path, [dict(LIGA, price_tcg_brl=0)])
    assert store['sources'][0]['status'].startswith('sem cobertura') and code != 0


def test_m1_invalid_file_is_failed(monkeypatch, tmp_path):
    p = _xlsx(tmp_path / 'x.xlsx', [{'a': 1}], sheet='Deals')
    code, store = _run(monkeypatch, tmp_path, ['--skip-scan', '--sources', 'ct', '--ct-output', str(p)])
    assert store['sources'][0]['status'].startswith('falhou') and code == 1


@pytest.mark.parametrize('statuses,code', [
    (['ok', 'ok (fonte sem linhas)'], 0),
    (['ok', 'sem cobertura (x)'], 2),
    (['ok', 'falhou'], 2),
    (['ok', 'parcial (1 de 2)'], 2),
    (['sem cobertura (x)'], 1),
    (['falhou', 'indisponível'], 1),
    (['ok', 'pulado (escopo)'], 0),
])
def test_m1_exit_code_table(statuses, code):
    assert run.run_exit_code([SourceStatus(source=str(i), status=s) for i, s in enumerate(statuses)]) == code


def test_m1_summary_text_names_the_non_ok_sources():
    txt = run.run_outcome([SourceStatus(source='CT', status='sem cobertura (x)'),
                           SourceStatus(source='MYP', status='ok')])
    assert 'CT' in txt and 'sem cobertura' in txt and '2' in txt


# ── B6 ────────────────────────────────────────────────────────────────────────
def test_b6_comc_without_fx_is_flagged_as_missing_fx_not_missing_reference():
    d = comc_row_to_deal({'card': 'A', 'comc_price': 6.0, 'tcg_reference': 10.0}, 0.0)
    assert d.margem_venda_pct is None and d.compra_brl == 0
    reasons = '; '.join(d.review_reasons)
    assert 'câmbio ausente' in reasons and 'sem referência de preço' not in reasons
    assert d.ref_usd == 10.0 and d.compra_usd == 6.0        # o USD original e preservado


def test_b6_source_status_says_fx_missing():
    d = comc_row_to_deal({'card': 'A', 'comc_price': 6.0, 'tcg_reference': 10.0}, 0.0)
    st, _ = run.assess_coverage('ok', [d])
    assert st.startswith('sem cobertura') and 'câmbio ausente' in st


def test_b6_no_presumed_fx_constant_left():
    assert not hasattr(normalize, 'FX_FALLBACK') and not hasattr(run, 'FX_FALLBACK')


# ── B7 ────────────────────────────────────────────────────────────────────────
def test_b7_liga_row_missing_required_keys_is_flagged_and_counted(monkeypatch, tmp_path):
    rows = [LIGA, {k: v for k, v in LIGA.items() if k != 'liga_url'}]
    p = tmp_path / 'r.json'
    p.write_text(json.dumps(rows), encoding='utf-8')
    deals = read_liga(p, 5)
    assert not any('chaves obrigatórias' in r for r in deals[0].review_reasons)
    assert any('chaves obrigatórias' in r and 'liga_url' in r for r in deals[1].review_reasons)
    code, store = _liga(monkeypatch, tmp_path, rows)
    st = store['sources'][0]
    assert st['status'].startswith('parcial') and '1 de 2' in st['status']
    assert 'chaves obrigatórias' in st['detail']
