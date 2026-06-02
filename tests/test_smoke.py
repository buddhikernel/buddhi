"""Smoke path: ``python -m buddhi`` runs the kernel end-to-end on the naive pack."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import buddhi.__main__ as main_mod

# This file lives at buddhikernel-staging/public/tests/, so parent.parent is
# buddhikernel-staging/public/, where `python -m buddhi` must be invoked from
# (the package is ./buddhi/).
STAGING_DIR = Path(__file__).resolve().parent.parent


def test_python_dash_m_buddhi_exits_zero_with_output():
    proc = subprocess.run(
        [sys.executable, "-m", "buddhi"],
        cwd=str(STAGING_DIR),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    assert proc.stdout.strip(), "smoke path produced no stdout"
    assert "SMOKE PATH OK" in proc.stdout


def test_main_returns_zero_and_prints(capsys):
    rc = main_mod.main()
    assert rc == 0
    assert capsys.readouterr().out.strip(), "main() produced no stdout"
