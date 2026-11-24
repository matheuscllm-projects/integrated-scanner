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
