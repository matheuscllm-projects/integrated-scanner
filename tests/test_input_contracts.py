"""Contrato dos arquivos de entrada: identificar pelo CONTEÚDO, nunca pelo nome.

Um scan cru é reconhecido pelas abas/colunas obrigatórias que só ele tem. Arquivo
que não cumpre o contrato é REJEITADO com mensagem clara e nunca vira dado
(antes: um relatório processado era lido como scan cru e saía "referência 0")."""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

import run_integrated as run
from delivery import bucket_for, build_markdown
from normalize import (SourceFormatError, ct_row_to_deal, infer_fx_from_ct, latest_ct_output,
                       latest_myp_output, liga_row_to_deal, read_comc, read_ct, read_liga,
                       read_myp)

RAW_CT = {'Card Name': 'Eevee', 'Set': 'Prismatic Evolutions (pre)', 'Nº': '074',
          'Scan R$ (raw)': 100, 'LIVE R$ (real)': 100, 'TCG Market (BRL)': 200,
          'TCG Market (USD)': 40, 'Validation Status': 'VALIDATED_REAL',
          'Link CardTrader': 'https://example.org/offer', 'Link TCG': 'https://example.org/ref'}
PROCESSED_CT = {'Decisão': 'COMPRA', 'Porque': 'x', 'Set': 'Prismatic Evolutions (pre)',
                'Carta': 'Eevee', 'Nº': '074', 'Preço CT (R$)': 100, 'TCG (R$)': 200,
                'Margem venda %': 50.0, 'ROI aquisição % (info)': 100.0,
                'Link CT': 'https://example.org/offer', 'Link TCG': 'https://example.org/ref'}
MYP = {'Card Name': 'A (1/100)', 'Edition': 'SV: X', 'MYP EN NM (R$)': 60,
       'TCG Player (R$)': 100, 'URL': 'https://example.org/myp'}
COMC = {'card': 'A - 1/100', 'set': 'S', 'comc_price': 6.0, 'tcg_reference': 10.0,
        'comc_url': 'https://example.org/comc'}
LIGA = {'card_name': 'A', 'set_name': 'S', 'price_liga_brl': 60.0, 'price_tcg_brl': 100.0,
        'liga_url': 'https://example.org/liga', 'status': 'approved'}


def xlsx(path, rows, sheet='Oportunidades', extra=None):
    with pd.ExcelWriter(path) as w:
        for name, data in ([(sheet, rows)] + list((extra or {}).items())):
            pd.DataFrame(data).to_excel(w, sheet_name=name, index=False)
    return path


# ── CardTrader: scan cru x relatório processado ─────────────────────────────

def test_processed_report_is_rejected_with_clear_message(tmp_path):
    p = xlsx(tmp_path / 'relatorio_da_vez.xlsx', [PROCESSED_CT], sheet='Deals')
    with pytest.raises(SourceFormatError) as e:
        read_ct(p, 5)
    msg = str(e.value)
    assert 'relatorio_da_vez.xlsx' in msg
    assert "'Scan R$ (raw)'" in msg and "'TCG Market (BRL)'" in msg      # o que faltou
    assert 'relatório processado' in msg                                 # diagnóstico
    assert 'Deals' in msg                                                # por aba


def test_raw_scan_accepted_regardless_of_file_name(tmp_path):
    p = xlsx(tmp_path / 'qualquer_coisa_post.xlsx', [RAW_CT])   # "_post" no nome não rejeita
    deals = read_ct(p, 5)
    assert len(deals) == 1 and deals[0].ref_brl == 200 and deals[0].compra_brl == 100


def test_processed_report_rejected_even_without_post_in_name(tmp_path):
    p = xlsx(tmp_path / 'scan_cru.xlsx', [PROCESSED_CT], sheet='Deals')
    with pytest.raises(SourceFormatError):
        read_ct(p, 5)


def test_raw_scan_found_in_any_sheet_position(tmp_path):
    p = xlsx(tmp_path / 'scan.xlsx', [RAW_CT], extra={'Stats': [{'Métrica': 'a', 'Valor': 1}]})
    assert len(read_ct(p, 5)) == 1
    p2 = xlsx(tmp_path / 'scan2.xlsx', [{'Métrica': 'a'}], sheet='Stats',
              extra={'Oportunidades': [RAW_CT]})
    assert len(read_ct(p2, 5)) == 1


def test_latest_ct_output_skips_processed_by_content(tmp_path):
    out = tmp_path / 'outputs'
    out.mkdir()
    raw = xlsx(out / 'scan_a.xlsx', [RAW_CT])
    proc = xlsx(out / 'relatorio_da_vez.xlsx', [PROCESSED_CT], sheet='Deals')
    os.utime(raw, (1_000_000_000, 1_000_000_000))
    os.utime(proc, (2_000_000_000, 2_000_000_000))                # o processado é o mais novo
    assert latest_ct_output(tmp_path) == raw
    raw.unlink()
    assert latest_ct_output(tmp_path) is None
    assert infer_fx_from_ct(tmp_path) is None                     # nada de câmbio de relatório


def test_latest_myp_output_skips_non_conforming_files(tmp_path):
    res = tmp_path / 'results'
    res.mkdir()
    good = xlsx(res / 'a.xlsx', [MYP], sheet='All EN Cards')
    bad = xlsx(res / 'b.xlsx', [PROCESSED_CT], sheet='Deals')
    os.utime(good, (1_000_000_000, 1_000_000_000))
    os.utime(bad, (2_000_000_000, 2_000_000_000))
    assert latest_myp_output(tmp_path) == good


# ── referência zerada / ausente: sinalizada, nunca margem calculada com zero ──

@pytest.mark.parametrize('ref', [0, None, float('nan')])
def test_zero_or_missing_reference_is_flagged_not_computed(ref):
    d = ct_row_to_deal(dict(RAW_CT, **{'TCG Market (BRL)': ref}), 5)
    assert d.margem_venda_pct is None and d.roi_aquisicao_pct is None
    assert any('sem referência' in r for r in d.review_reasons)
    assert bucket_for(d) == 'Rejeitados / sem referência'
    md = build_markdown([d], [], 5.0)
    row = next(line for line in md.splitlines() if '| Eevee' in line)
    assert '0.0%' not in row and '—' in row


def test_missing_purchase_is_flagged_too():
    d = liga_row_to_deal(dict(LIGA, price_liga_brl=0), 5)
    assert d.margem_venda_pct is None
    assert any('sem preço de compra' in r for r in d.review_reasons)


# ── MYP / COMC / Liga: coluna obrigatória ausente = erro visível ───────────────

def test_myp_missing_required_column_raises(tmp_path):
    row = {k: v for k, v in MYP.items() if k != 'TCG Player (R$)'}
    p = xlsx(tmp_path / 'myp.xlsx', [row], sheet='All EN Cards')
    with pytest.raises(SourceFormatError, match=r"TCG Player \(R\$\)"):
        read_myp(p, 5)


def test_myp_rejects_a_ct_file(tmp_path):
    p = xlsx(tmp_path / 'ct.xlsx', [RAW_CT])
    with pytest.raises(SourceFormatError):
        read_myp(p, 5)


def test_myp_valid_file_still_reads(tmp_path):
    p = xlsx(tmp_path / 'myp.xlsx', [MYP], sheet='All EN Cards', extra={'🔥 Deals': [MYP]})
    assert [d.carta for d in read_myp(p, 5)] == ['A']


def test_comc_missing_required_column_raises(tmp_path):
    p = tmp_path / 'c.csv'
    pd.DataFrame([{k: v for k, v in COMC.items() if k != 'tcg_reference'}]).to_csv(p, index=False)
    with pytest.raises(SourceFormatError, match='tcg_reference'):
        read_comc(p, 5)


def test_comc_empty_file_raises(tmp_path):
    p = tmp_path / 'c.csv'
    p.write_text('', encoding='utf-8')
    with pytest.raises(SourceFormatError):
        read_comc(p, 5)


def test_comc_valid_file_still_reads(tmp_path):
    p = tmp_path / 'c.csv'
    pd.DataFrame([COMC]).to_csv(p, index=False)
    assert len(read_comc(p, 5)) == 1


@pytest.mark.parametrize('payload', [{'summary': 1}, 'texto', 42])
def test_liga_non_list_payload_raises(tmp_path, payload):
    p = tmp_path / 'r.json'
    p.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(SourceFormatError):
        read_liga(p, 5)


def test_liga_invalid_json_raises(tmp_path):
    p = tmp_path / 'r.json'
    p.write_text('{nao e json', encoding='utf-8')
    with pytest.raises(SourceFormatError):
        read_liga(p, 5)


def test_liga_rows_without_any_required_key_raise(tmp_path):
    p = tmp_path / 'r.json'
    p.write_text(json.dumps([{'card_name': 'A', 'status': 'approved'}]), encoding='utf-8')
    with pytest.raises(SourceFormatError, match='price_tcg_brl'):
        read_liga(p, 5)


def test_liga_single_row_missing_reference_is_flagged(tmp_path):
    p = tmp_path / 'r.json'
    bad = {k: v for k, v in LIGA.items() if k != 'price_tcg_brl'}
    p.write_text(json.dumps([LIGA, dict(bad, card_name='B')]), encoding='utf-8')
    deals = read_liga(p, 5)
    assert deals[0].margem_venda_pct == pytest.approx(40.0)
    assert deals[1].margem_venda_pct is None
    assert any('sem referência' in r for r in deals[1].review_reasons)


def test_liga_empty_list_is_ok(tmp_path):
    p = tmp_path / 'r.json'
    p.write_text('[]', encoding='utf-8')
    assert read_liga(p, 5) == []


# ── run_integrated: rejeição vira status visível, nunca linha ───────────────────

def test_run_marks_source_failed_on_wrong_file(monkeypatch, tmp_path):
    monkeypatch.setattr(run, 'OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr(run, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(run, 'fresh_fx', lambda: 5)
    stores = []
    monkeypatch.setattr(run, 'save_store', lambda data, **kw: stores.append((data, kw)))
    p = xlsx(tmp_path / 'relatorio_da_vez.xlsx', [PROCESSED_CT], sheet='Deals')
    monkeypatch.setattr(sys, 'argv', ['run', '--skip-scan', '--sources', 'ct', '--ct-output', str(p)])
    run.main()
    data = stores[0][0]
    assert data['deals'] == []
    src = data['sources'][0]
    assert src['status'].startswith('falhou') and 'Scan R$ (raw)' in src['detail']


def test_run_reports_rows_without_reference_in_source_status(monkeypatch, tmp_path):
    monkeypatch.setattr(run, 'OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr(run, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(run, 'fresh_fx', lambda: 5)
    stores = []
    monkeypatch.setattr(run, 'save_store', lambda data, **kw: stores.append((data, kw)))
    p = xlsx(tmp_path / 'scan.xlsx', [RAW_CT, dict(RAW_CT, **{'Card Name': 'Sem ref', 'TCG Market (BRL)': 0})])
    monkeypatch.setattr(sys, 'argv', ['run', '--skip-scan', '--sources', 'ct', '--ct-output', str(p)])
    run.main()
    src = stores[0][0]['sources'][0]
    assert '1 linha(s) sem preço de compra/referência' in src['detail']
    assert len(stores[0][0]['deals']) == 2          # a linha NÃO some: fica no bucket Rejeitados


# ── complemento LOCAL com arquivos reais (não versionados) ──────────────────────

REAL_PROCESSED = Path(r'C:\Users\mathe\ct-vintage-compare\full34\relatorio_p1b.xlsx')
REAL_RAW = Path(r'C:\Users\mathe\ct-vintage-compare\full34-v2\scan.xlsx')


@pytest.mark.skipif(not REAL_PROCESSED.exists(), reason='arquivo real só existe no PC do operador')
def test_real_processed_report_is_rejected():
    with pytest.raises(SourceFormatError) as e:
        read_ct(REAL_PROCESSED, 5)
    assert 'relatório processado' in str(e.value)


@pytest.mark.skipif(not REAL_RAW.exists(), reason='arquivo real só existe no PC do operador')
def test_real_raw_scan_is_accepted():
    deals = read_ct(REAL_RAW, 5)
    assert len(deals) > 1000
    assert all(d.ref_brl > 0 for d in deals)
