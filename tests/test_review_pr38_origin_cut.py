"""PR #38 revisao B3: corte de origem de cada fonte explicito (COMC = 20% inteiro, sobre a venda)."""
import sys
from pathlib import Path

import pandas as pd

import run_integrated as run
from delivery import SourceStatus, build_markdown

ROOT = Path(__file__).resolve().parents[1]
RAW_CT = {'Card Name': 'Eevee', 'Set': 'S (pre)', 'Scan R$ (raw)': 100, 'TCG Market (BRL)': 200,
          'TCG Market (USD)': 40, 'Link CardTrader': 'https://example.org/o'}


def test_b3_comc_receives_its_origin_cut_explicitly(monkeypatch, tmp_path):
    cmds = []

    def fake_step(name, cmd, cwd, timeout_s, log_path, env_extra=None):
        cmds.append(cmd)
        return 'ok', '', 0.0

    monkeypatch.setattr(run, '_run_step', fake_step)
    monkeypatch.setattr(run, 'LOG_DIR', tmp_path)
    run.scan_comc(run.resolve_scope('PRE'), 'T', 60)
    assert cmds, 'COMC nao foi chamado'
    cmd = cmds[0]
    assert cmd[cmd.index('--min-discount') + 1] == '20'      # inteiro, nunca fracao


def test_b3_each_source_has_a_documented_origin_cut():
    assert set(run.ORIGIN_CUTS) == {'myp', 'ct', 'comc', 'liga'}
    assert '20%' in run.ORIGIN_CUTS['comc'] and 'venda' in run.ORIGIN_CUTS['comc']
    assert all('sobre a venda' in run.ORIGIN_CUTS[s] for s in ('myp', 'liga', 'ct'))


def test_b3_summary_shows_origin_cut_per_source(monkeypatch, tmp_path):
    monkeypatch.setattr(run, 'OUT_DIR', tmp_path / 'out')
    monkeypatch.setattr(run, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(run, 'fresh_fx', lambda: 5)
    stores = []
    monkeypatch.setattr(run, 'save_store', lambda data, **kw: stores.append(data))
    p = tmp_path / 'scan.xlsx'
    with pd.ExcelWriter(p) as w:
        pd.DataFrame([RAW_CT]).to_excel(w, sheet_name='Oportunidades', index=False)
    monkeypatch.setattr(sys, 'argv', ['run', '--skip-scan', '--sources', 'ct', '--ct-output', str(p)])
    run.main()
    assert 'releitura' in stores[0]['sources'][0]['origin_cut']      # corte real do arquivo e desconhecido
    md = build_markdown([], [SourceStatus(source='COMC', status='ok', origin_cut='20% sobre a venda')], 5.0)
    assert 'corte de origem: 20% sobre a venda' in md


def test_b3_no_wrong_comc_fraction_claims_left():
    for name in ('run_integrated.py', 'CLAUDE.md'):
        text = (ROOT / name).read_text(encoding='utf-8')
        assert 'CardTrader e COMC: FRAÇÃO' not in text, name
        assert 'margem default do COMC já é 0.30' not in text, name
    assert 'MIN_DISCOUNT_PERCENT' in (ROOT / 'CLAUDE.md').read_text(encoding='utf-8')
