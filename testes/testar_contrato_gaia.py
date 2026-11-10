# -*- coding: utf-8 -*-
"""As cópias do contrato com a GAIA continuam iguais nos dois repositórios.

Compara o CÓDIGO (árvore sintática sem docstrings; comentários já não entram
na árvore) de `core/mascot_events.py` e `mascot/protocol/transport.py` com os
arquivos correspondentes do `assistant`. Sem o checkout da GAIA ao lado
(`PROJETO_GAIA_DIR` ou a pasta irmã padrão), o teste é pulado."""
import ast
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
GAIA = Path(os.environ.get("PROJETO_GAIA_DIR", RAIZ.parent / "Project G.A.I.A" / "assistant"))

PARES = (
    (RAIZ / "core" / "mascot_events.py", GAIA / "core" / "mascot_events.py"),
    (RAIZ / "mascot" / "protocol" / "transport.py", GAIA / "core" / "mascot_transport.py"),
)


def codigo_sem_docstrings(caminho: Path) -> str:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if (
            isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and corpo
            and isinstance(corpo[0], ast.Expr)
            and isinstance(corpo[0].value, ast.Constant)
            and isinstance(corpo[0].value.value, str)
        ):
            no.body = corpo[1:] or [ast.Pass()]
    return ast.dump(arvore)


def main() -> int:
    if not GAIA.is_dir():
        print(f"OK: pulado, checkout da GAIA não encontrado em {GAIA}")
        return 0
    falhas = 0
    for local, remoto in PARES:
        nome = local.relative_to(RAIZ).as_posix()
        if not remoto.is_file():
            print(f"FAIL: {nome} sem correspondente em {remoto}")
            falhas += 1
        elif codigo_sem_docstrings(local) != codigo_sem_docstrings(remoto):
            print(f"FAIL: {nome} diverge de {remoto}")
            falhas += 1
        else:
            print(f"PASS: {nome} igual à cópia da GAIA")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
