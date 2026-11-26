# -*- coding: utf-8 -*-
"""Log no padrão do ecossistema (`mascot/registro.py`, cópia do modelo da
CLIO): pasta em LOCALAPPDATA, arquivo do dia, limpeza de 30 dias e
proteção contra laço quando o próprio log falha."""
import datetime
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mascot import registro

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


def pasta_no_localappdata(tmp):
    antigo = os.environ.get("LOCALAPPDATA")
    os.environ["LOCALAPPDATA"] = str(tmp)
    try:
        pasta = registro.pasta_logs("LOKI")
    finally:
        if antigo is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = antigo
    checar("pasta em LOCALAPPDATA/Ecossistema/LOKI/Logs", pasta == tmp / "Ecossistema" / "LOKI" / "Logs", str(pasta))


def limpar_so_logs_antigos(tmp):
    hoje = datetime.date(2026, 11, 14)
    for nome in ("2026-10-01.log", "2026-11-01.log", "anotacoes.log", "2026-13-99.log"):
        (tmp / nome).write_text("x")
    apagados = registro.limpar(tmp, dias=30, hoje=hoje)
    restantes = sorted(p.name for p in tmp.iterdir())
    checar("limpeza apaga só o AAAA-MM-DD.log antigo", apagados == 1
           and restantes == ["2026-11-01.log", "2026-13-99.log", "anotacoes.log"], str(restantes))


def arquivo_do_dia(tmp):
    manipulador = registro.ArquivoDoDia(tmp)
    manipulador.setFormatter(logging.Formatter(registro.FORMATO))
    log = logging.getLogger("teste.registro")
    log.addHandler(manipulador)
    log.propagate = False
    try:
        log.warning("algo aconteceu")
    finally:
        log.removeHandler(manipulador)
        manipulador.arquivo.close()
    texto = (tmp / f"{datetime.date.today().isoformat()}.log").read_text(encoding="utf-8")
    checar("linha no formato do ecossistema", "WARNING teste.registro: algo aconteceu" in texto, texto)


def falha_do_log_nao_vira_laco():
    saida = registro._SaidaParaLog("teste.laco", logging.WARNING)
    chamadas = []

    class Quebrado(logging.Handler):
        def emit(self, registro_):
            chamadas.append(1)
            sys.stderr.write("erro ao escrever\n")   # como o logging.handleError faz

    log = logging.getLogger("teste.laco")
    log.addHandler(Quebrado())
    log.propagate = False
    stderr_antigo = sys.stderr
    sys.stderr = saida
    try:
        saida.write("primeira linha\n")
    finally:
        sys.stderr = stderr_antigo
    checar("falha do log não vira laço", chamadas == [1], str(chamadas))


def print_em_pedacos_vira_uma_linha():
    saida = registro._SaidaParaLog("teste.pedacos", logging.INFO)
    linhas = []

    class Coleta(logging.Handler):
        def emit(self, registro_):
            linhas.append(registro_.getMessage())

    log = logging.getLogger("teste.pedacos")
    log.setLevel(logging.INFO)
    log.addHandler(Coleta())
    log.propagate = False
    print("a", "b", file=saida)
    saida.write("sem quebra")
    primeiro = list(linhas)
    saida.flush()
    checar("print em pedaços vira uma linha", primeiro == ["a b"] and linhas == ["a b", "sem quebra"], str(linhas))


with tempfile.TemporaryDirectory() as t:
    pasta_no_localappdata(Path(t))
with tempfile.TemporaryDirectory() as t:
    limpar_so_logs_antigos(Path(t))
with tempfile.TemporaryDirectory() as t:
    arquivo_do_dia(Path(t))
falha_do_log_nao_vira_laco()
print_em_pedacos_vira_uma_linha()

sys.exit(1 if _falhas else 0)
