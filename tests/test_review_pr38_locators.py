"""PR #38 revisao B5: localizadores nao pulam arquivo mais novo em silencio."""
import os
import warnings

import pandas as pd
import pytest

import normalize
from normalize import (infer_fx_from_ct, latest_ct_output, locate_ct_output, locate_myp_output)

RAW_CT = {'Card Name': 'Eevee', 'Set': 'S (pre)', 'Scan R$ (raw)': 100, 'TCG Market (BRL)': 200,
          'TCG Market (USD)': 40, 'Link CardTrader': 'https://example.org/o'}
PROCESSED = {'Preço CT (R$)': 100, 'TCG (R$)': 200, 'Carta': 'x'}


def _xlsx(path, sheets):
    with pd.ExcelWriter(path) as w:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(w, sheet_name=name, index=False)
    return path


def _repo(tmp_path):
    out = tmp_path / 'outputs'
    out.mkdir()
    good = _xlsx(out / 'scan_antigo.xlsx', {'Oportunidades': [RAW_CT]})
    bad = _xlsx(out / 'relatorio_novo.xlsx', {'Deals': [PROCESSED]})
    os.utime(good, (1_700_000_000, 1_700_000_000))
    os.utime(bad, (1_800_000_000, 1_800_000_000))
    return good, bad


def test_b5_newer_rejected_file_is_reported_with_reason_and_used_file(tmp_path):
    good, bad = _repo(tmp_path)
    found = locate_ct_output(tmp_path)
    assert found.path == good
    note = ' '.join(found.notes)
    assert 'relatorio_novo.xlsx' in note and 'rejeitado' in note
    assert "'Scan R$ (raw)'" in note                 # por que
    assert 'scan_antigo.xlsx' in note and '2023' in note   # qual foi usado e de quando


def test_b5_no_note_when_newest_file_conforms(tmp_path):
    good, bad = _repo(tmp_path)
    bad.unlink()
    found = locate_ct_output(tmp_path)
    assert found.path == good and found.notes == []


def test_b5_legacy_locator_warns_instead_of_skipping_silently(tmp_path):
    good, bad = _repo(tmp_path)
    with pytest.warns(UserWarning, match='relatorio_novo.xlsx'):
        assert latest_ct_output(tmp_path) == good


def test_b5_myp_locator_reports_too(tmp_path):
    res = tmp_path / 'results'
    res.mkdir()
    _xlsx(res / 'novo.xlsx', {'Deals': [PROCESSED]})
    found = locate_myp_output(tmp_path)
    assert found.path is None and 'novo.xlsx' in ' '.join(found.notes)


def test_b5_infer_fx_reads_the_validated_sheet_not_the_first(tmp_path):
    out = tmp_path / 'outputs'
    out.mkdir()
    _xlsx(out / 'scan.xlsx', {'Stats': [{'TCG Market (BRL)': 1, 'TCG Market (USD)': 1}],
                              'Oportunidades': [RAW_CT]})
    assert infer_fx_from_ct(tmp_path) == pytest.approx(5.0)    # 200/40, nao 1/1


def test_b5_dead_code_removed():
    import run_integrated
    assert not hasattr(run_integrated, 'infer_fx_from_ct')
    assert not hasattr(run_integrated, 'latest_myp_output')
