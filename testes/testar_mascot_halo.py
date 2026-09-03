"""Script avulso pra validar o Halo (Project LOKI, Fase 5, redesenhado
2026-09-02 pra refletir MODO DE VOZ, não mais estado semântico/emoção -
ver docstring de `features/mascot/halo.py`) - `definir_modo_voz` é lógica
pura (sem Qt), testável direto; `pintar` só precisa de um `QPainter` real
pra confirmar que não crasha (conteúdo visual não é verificável aqui).
Sem framework de teste (mesmo padrão de testes/testar_*.py), roda cada
caso e imprime PASS/FAIL.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz do projeto

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from mascot.halo import Halo, COR_VOZ_CONTINUA, COR_CLICK_TO_TALK

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


# ----------------------------------------------------------------------
# Os 3 modos de voz - cada um com sua cor, sem pulso (dura o modo inteiro).
# ----------------------------------------------------------------------
halo = Halo()

halo.definir_modo_voz("voz_continua")
checar("voz contínua usa a cor dourada", halo.cor_hex == COR_VOZ_CONTINUA, halo.cor_hex)
checar("halo fica ativo em voz contínua", halo.ativo is True)

halo.definir_modo_voz("ouvir_pc")
checar("'ouvir_pc' usa a MESMA cor de voz contínua (mesma família de escuta sempre ligada)", halo.cor_hex == COR_VOZ_CONTINUA, halo.cor_hex)

halo.definir_modo_voz("click_to_talk")
checar("clique-pra-falar usa a cor verde", halo.cor_hex == COR_CLICK_TO_TALK, halo.cor_hex)
checar("verde é uma cor DIFERENTE do dourado", COR_CLICK_TO_TALK != COR_VOZ_CONTINUA)

# ----------------------------------------------------------------------
# Voz desligada - sem halo nenhum.
# ----------------------------------------------------------------------
halo.definir_modo_voz(None)
checar("voz desligada (None) NÃO tem halo", halo.cor_hex is None, halo.cor_hex)
checar("halo fica inativo sem cor", halo.ativo is False)

halo.definir_modo_voz("modo_desconhecido_qualquer")
checar("modo desconhecido/inválido cai em sem halo, nunca crasha", halo.cor_hex is None, halo.cor_hex)

# ----------------------------------------------------------------------
# pintar() não crasha - com halo ativo e com halo desligado.
# ----------------------------------------------------------------------
alvo = QPixmap(200, 200)
alvo.fill()
painter = QPainter(alvo)
try:
    halo.definir_modo_voz("voz_continua")
    halo.pintar(painter, QPointF(100, 100), 80.0)
    checar("pintar() com halo ativo não crasha", True)

    halo.definir_modo_voz(None)
    halo.pintar(painter, QPointF(100, 100), 80.0)
    checar("pintar() com halo inativo (sem cor) não desenha nada e não crasha", True)

    halo.definir_modo_voz("click_to_talk")
    halo.pintar(painter, QPointF(100, 100), 0.0)
    checar("pintar() com raio_base zero não crasha", True)
finally:
    painter.end()


print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
