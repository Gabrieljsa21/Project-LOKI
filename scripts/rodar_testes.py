# -*- coding: utf-8 -*-
"""Roda todos os `testes/testar_*.py` em sequência e resume o resultado.

Cada teste é um script independente (processo próprio, `QApplication`
própria) - este executor só os dispara um a um, offscreen, e conta as
linhas `PASS:`/`FAIL:` (ou o `OK:` final dos testes de função única).
Sai com código 1 se qualquer arquivo falhar.

Uso (sempre da raiz do repositório):
    .venv\Scripts\python.exe scripts\rodar_testes.py [filtro]
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LIMITE_POR_ARQUIVO_S = 300


def rodar(caminho: Path) -> tuple[bool, str, list[str]]:
    ambiente = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    inicio = time.monotonic()
    try:
        processo = subprocess.run(
            [sys.executable, str(caminho)], cwd=RAIZ, env=ambiente,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=LIMITE_POR_ARQUIVO_S,
        )
    except subprocess.TimeoutExpired:
        return False, f"tempo esgotado ({LIMITE_POR_ARQUIVO_S}s)", []
    duracao = time.monotonic() - inicio
    linhas = processo.stdout.splitlines()
    passou = sum(1 for linha in linhas if linha.startswith(("PASS:", "OK:")))
    falhas = [linha for linha in linhas if linha.startswith("FAIL:")]
    ok = processo.returncode == 0 and not falhas
    detalhes = falhas
    if processo.returncode != 0 and not falhas:
        detalhes = (processo.stderr.strip().splitlines() or ["sem saída de erro"])[-5:]
    return ok, f"{passou} ok, {len(falhas)} falha(s), {duracao:.1f}s", detalhes


def main() -> int:
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    arquivos = sorted(p for p in (RAIZ / "testes").glob("testar_*.py") if filtro in p.name)
    if not arquivos:
        print(f"Nenhum teste encontrado para o filtro '{filtro}'.")
        return 1
    reprovados = []
    for caminho in arquivos:
        ok, resumo, detalhes = rodar(caminho)
        print(f"{'OK   ' if ok else 'FALHA'} {caminho.name}: {resumo}")
        for linha in detalhes:
            print(f"        {linha}")
        if not ok:
            reprovados.append(caminho.name)
    print()
    print(f"{len(arquivos) - len(reprovados)}/{len(arquivos)} arquivos passaram.")
    return 1 if reprovados else 0


if __name__ == "__main__":
    sys.exit(main())
