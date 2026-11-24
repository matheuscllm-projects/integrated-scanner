"""Codigos de saida novos do CardTrader (20-23): parcial com motivo, XLSX deste run lido."""
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

import run_integrated as run
from normalize import SourceFormatError, _find_sheet

BASE = {'Card Name': 'Eevee', 'Set': 'S (pre)', 'Scan R$ (raw)': 100, 'TCG Market (BRL)': 200,
        'TCG Market (USD)': 40, 'Link CardTrader': 'https://example.org/o', 'Link TCG': 'https://t.example/x'}


def _write(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as w:
        pd.DataFrame(rows).to_excel(w, sheet_name='Oportunidades', index=False)


def _rows(*statuses):
    return [dict(BASE, **{'Card Name': f'C{i}', 'Validation Status': s,
                          'LIVE R$ (real)': 100 if s.startswith('VALIDATED') else 0})
            for i, s in enumerate(statuses)]


def _fake_run(code, rows, write=True):
    def fake(cmd, **kw):
        if write:
            _write(cmd[cmd.index('--output') + 1], rows)
        return subprocess.CompletedProcess(cmd, code)
    return fake


def _main(monkeypatch, tmp_path, fake):
    monkeypatch.setattr(run, 'OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr(run, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(run, 'fresh_fx', lambda: 5)
    monkeypatch.setattr(run, 'REPOS', dict(run.REPOS, ct=tmp_path))
    monkeypatch.setattr(run.subprocess, 'run', fake)
    stores = []
    monkeypatch.setattr(run, 'save_store', lambda data, **kw: stores.append(data))
    monkeypatch.setattr(sys, 'argv', ['run', '--sources', 'ct', '--sets', 'PRE'])
    run.main()
    return stores[0]


@pytest.mark.parametrize('code,fragment', [
    (20, 'validação de preço parcial'), (21, 'nenhum preço de checkout validado'),
    (22, 'API de validação falhou'), (23, 'não avaliados por falha operacional')])
def test_ct_codes_20_23_are_parcial_with_reason(code, fragment, tmp_path, monkeypatch):
    monkeypatch.setattr(run.subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(cmd, code))
    st, det, _ = run._run_step('ct', ['x'], tmp_path, 5, tmp_path / 'l.log', exit_map=run.CT_EXIT)
    assert st == 'parcial' and fragment in det


def test_ct_exit_2_and_1_are_falhou_without_data(tmp_path, monkeypatch):
    for code in (1, 2, 130):
        monkeypatch.setattr(run.subprocess, 'run', lambda cmd, c=code, **kw: subprocess.CompletedProcess(cmd, c))
        st, det, _ = run._run_step('ct', ['x'], tmp_path, 5, tmp_path / 'l.log', exit_map=run.CT_EXIT)
        assert st == 'falhou', code


def test_other_sources_keep_exit_2_parcial(tmp_path, monkeypatch):
    monkeypatch.setattr(run.subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2))
    assert run._run_step('myp', ['x'], tmp_path, 5, tmp_path / 'l.log')[0] == 'parcial'
    monkeypatch.setattr(run.subprocess, 'run', lambda cmd, **kw: subprocess.CompletedProcess(cmd, 20))
    assert run._run_step('myp', ['x'], tmp_path, 5, tmp_path / 'l.log')[0] == 'falhou'


def test_exit20_clean_deal_and_review_line(monkeypatch, tmp_path):
    store = _main(monkeypatch, tmp_path, _fake_run(20, _rows('VALIDATED_REAL', 'PRECO_INVALIDO', 'API_ERROR')))
    src = store['sources'][0]
    assert src['status'].startswith('parcial') and 'validação de preço parcial' in src['detail']
    cts = store['deals'] if 'deals' in store else []
    clean = [d for d in cts if not d.get('review_reasons')]
    assert [d['carta'] for d in clean] == ['C0']
    assert {d['carta'] for d in cts if d.get('review_reasons')} == {'C1', 'C2'}


def test_exit21_no_clean_deal(monkeypatch, tmp_path):
    store = _main(monkeypatch, tmp_path, _fake_run(21, _rows('PRECO_INVALIDO', 'API_ERROR')))
    assert store['sources'][0]['status'].startswith('parcial')
    assert all(d.get('review_reasons') for d in store['deals'])


def test_exit23_detail_mentions_sets(monkeypatch, tmp_path):
    store = _main(monkeypatch, tmp_path, _fake_run(23, _rows('VALIDATED_REAL')))
    assert 'set(s) não avaliados' in store['sources'][0]['detail']


def test_exit2_never_reads_old_file_and_stale_file_rejected(monkeypatch, tmp_path):
    store = _main(monkeypatch, tmp_path, _fake_run(2, [], write=False))
    assert not store['sources'][0]['status'].startswith('ok') and not store.get('deals')
    old = tmp_path / 'old.xlsx'
    _write(old, _rows('VALIDATED_REAL'))
    t0 = time.time() + 5
    assert run._fresh(old, t0) is None and run._fresh(old, 0) == old


@pytest.mark.parametrize('cols', [('Preço CT (R$)', 'TCG (R$)'),
                                  ('Preço CT validado (R$)', 'TCG (R$)'),
                                  ('Preço usado na conta (R$)', 'TCG (R$)')])
def test_processed_report_markers(tmp_path, cols):
    p = tmp_path / 'p.xlsx'
    pd.DataFrame([{c: 1 for c in cols}]).to_excel(p, index=False)
    with pytest.raises(SourceFormatError, match='processado'):
        _find_sheet(p, ('Card Name',), 'scan cru')


def test_origin_cut_text_per_source_is_sobre_a_venda():
    for src in ('myp', 'ct', 'liga'):
        assert run.ORIGIN_CUTS[src].startswith('30% sobre a venda'), src
    assert run.ORIGIN_CUTS['comc'].startswith('20% sobre a venda')
    assert not any('compra' in v or '23,1' in v for v in run.ORIGIN_CUTS.values())
