"""A linha de comando que o orquestrador monta pro COMC tem que ser aceita pelo
parser REAL do scanner-comc (bug: subcomando `targeted` + flags que não existem
-> argparse exit 2, lido como "parcial" em vez de falha operacional)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_integrated
from normalize import REPOS

COMC_REPO = REPOS["comc"]


def _real_parser():
    if not (COMC_REPO / "comc_scanner" / "__main__.py").exists():
        pytest.skip("scanner-comc não está neste ambiente")
    sys.path.insert(0, str(COMC_REPO))
    try:
        from comc_scanner.__main__ import build_parser
        return build_parser()
    finally:
        sys.path.remove(str(COMC_REPO))


@pytest.mark.parametrize("era,abbrevs", [("recent", None), ("vintage", ["BS", "JU"])])
def test_comc_cmd_accepted_by_real_parser(era, abbrevs):
    cmd = run_integrated._comc_cmd(era, abbrevs)
    args = _real_parser().parse_args(cmd[cmd.index("comc_scanner") + 1:])
    assert args.command == "scan" and args.era == era


def test_comc_rejected_cli_is_operational_failure(tmp_path):
    log = tmp_path / "l.log"
    log.write_text("comc_scanner: error: argument command: invalid choice: 'targeted'\n")
    assert run_integrated._comc_cli_rejected(log)
    log.write_text("scan ok\n")
    assert not run_integrated._comc_cli_rejected(log)


# Formas literais do argparse (raiz e subparser): o teste não depende do repo COMC.
ROOT_ERR = "usage: comc_scanner [-h] ...\ncomc_scanner: error: argument command: invalid choice: 'targeted'\n"
SUB_ERR = "usage: comc_scanner scan [-h] ...\ncomc_scanner scan: error: argument --era: invalid choice: 'zzz'\n"


@pytest.mark.parametrize("text", [ROOT_ERR, SUB_ERR])
def test_cli_rejected_literal_samples(tmp_path, text):
    log = tmp_path / "l.log"
    log.write_text(text)
    assert run_integrated._comc_cli_rejected(log)


@pytest.mark.parametrize("argv", [["targeted"], ["scan", "--era", "zzz"], ["scan", "--min-discount", "abc"]])
def test_cli_rejected_real_argparse_output(tmp_path, argv, capsys):
    parser = _real_parser()  # skip explícito se o scanner-comc não existe
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(argv)
    assert exc.value.code == 2
    log = tmp_path / "l.log"
    log.write_text(capsys.readouterr().err)
    assert run_integrated._comc_cli_rejected(log)


# Texto real de pipeline.run_scan (log.error) quando nenhum set cruza era/allowlist.
NO_COVER = "ERROR comc_scanner.pipeline: Nenhum set validado intersecta a era 'recent' / allowlist.\n"


def test_comc_no_coverage_detected(tmp_path):
    log = tmp_path / "l.log"
    log.write_text(NO_COVER)
    assert run_integrated._comc_no_coverage(log)
    log.write_text("scan ok\n")
    assert not run_integrated._comc_no_coverage(log)


def test_scan_comc_no_coverage_status(tmp_path, monkeypatch):
    monkeypatch.setattr(run_integrated, "LOG_DIR", tmp_path)
    monkeypatch.setattr(run_integrated, "to_comc", lambda s: ([("recent", ["XYZ"])], []))
    monkeypatch.setattr(run_integrated, "is_full", lambda s: False)
    monkeypatch.setattr(run_integrated, "latest_comc_outputs", lambda r: [])

    def fake_step(name, cmd, cwd, t, log):
        log.write_text(NO_COVER)
        return "ok", "", 1.0
    monkeypatch.setattr(run_integrated, "_run_step", fake_step)
    st, det, _, outs = run_integrated.scan_comc(object(), "s", 5)
    assert st == "sem cobertura" and det.startswith("recent: COMC não cobre os sets pedidos")
    assert outs == []


def test_comc_cmd_has_explicit_integer_min_discount_accepted_by_real_parser():
    cmd = run_integrated._comc_cmd("recent", None)
    i = cmd.index("--min-discount")
    assert cmd[i + 1] == str(run_integrated.COMC_MIN_DISCOUNT_PERCENT)
    args = _real_parser().parse_args(cmd[cmd.index("comc_scanner") + 1:])
    assert args.min_discount == run_integrated.COMC_MIN_DISCOUNT_PERCENT
    assert "targeted" not in cmd and "--fetch-mode" not in cmd and "--no-sheets" not in cmd
