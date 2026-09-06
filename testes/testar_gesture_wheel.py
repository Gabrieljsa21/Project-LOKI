# -*- coding: utf-8 -*-
"""Validação geométrica da Gesture Wheel adaptativa (sem abrir desktop real)."""
import os
import sys
import json
import math
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QRectF

from mascot.gesture_wheel import (
    LayoutRoda, acoes_configuradas, calcular_distribuicao, calcular_layout_roda,
    carregar_configuracao, glifo_animacao, rotulo_animacao,
)

falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        falhas.append(nome)


area = QRectF(0, 0, 1280, 720)
raio = 180

centro = calcular_layout_roda(QPointF(640, 360), area, raio)
checar("centro usa círculo completo", centro.modo == "circulo" and centro.amplitude == 360 and centro.capacidade == 8, centro)

esquerda = calcular_layout_roda(QPointF(80, 360), area, raio)
direita = calcular_layout_roda(QPointF(1200, 360), area, raio)
cima = calcular_layout_roda(QPointF(640, 60), area, raio)
baixo = calcular_layout_roda(QPointF(640, 660), area, raio)
checar("borda esquerda abre meia-roda para dentro", esquerda.modo == "semicirculo" and esquerda.angulo_inicial == 270, esquerda)
checar("borda direita abre meia-roda para dentro", direita.modo == "semicirculo" and direita.angulo_inicial == 90, direita)
checar("borda superior abre meia-roda para baixo", cima.modo == "semicirculo" and cima.angulo_inicial == 180, cima)
checar("borda inferior abre meia-roda para cima", baixo.modo == "semicirculo" and baixo.angulo_inicial == 0, baixo)

cantos = (
    (QPointF(50, 50), 270.0),
    (QPointF(1230, 50), 180.0),
    (QPointF(50, 670), 0.0),
    (QPointF(1230, 670), 90.0),
)
for i, (ponto, inicio) in enumerate(cantos):
    layout = calcular_layout_roda(ponto, area, raio)
    checar(
        f"canto {i + 1} usa quadrante apontado para dentro",
        layout.modo == "quadrante" and layout.angulo_inicial == inicio and layout.capacidade == 8,
        layout,
    )

for modo, inicio, amplitude in (("circulo", 0, 360), ("semicirculo", 0, 180), ("quadrante", 0, 90)):
    distribuicao = calcular_distribuicao(LayoutRoda(modo, inicio, amplitude, 8), 8, 140)
    centros = [
        (raio * math.cos(math.radians(angulo)), -raio * math.sin(math.radians(angulo)))
        for angulo, raio in distribuicao
    ]
    menor = min(
        ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        for indice, a in enumerate(centros) for b in centros[:indice]
    )
    checar(f"{modo} separa os medalhões e placas", menor >= 120, menor)

checar("rótulo remove contexto técnico", rotulo_animacao("flutuando_para_sentada") == "Sentar", rotulo_animacao("flutuando_para_sentada"))
checar("rótulo longo é limitado", len(rotulo_animacao("sentada_gargalhada_quase-caindo_exageradamente")) <= 25)

setas_esperadas = {
    "direita": "→", "esquerda": "←", "subida": "↑", "descida": "↓",
    "superior-direita": "↗", "superior-esquerda": "↖",
    "inferior-direita": "↘", "inferior-esquerda": "↙",
}
for direcao_movimento, seta in setas_esperadas.items():
    animation_id = f"flutuando_{direcao_movimento}_iniciar"
    checar(
        f"movimento {direcao_movimento} aponta para a direção correta",
        glifo_animacao(animation_id) == seta,
        glifo_animacao(animation_id),
    )

with tempfile.TemporaryDirectory() as pasta:
    caminho = Path(pasta) / "wheel.json"
    caminho.write_text(json.dumps({"quantidade_maxima": 3, "acoes": ["a", "b"]}), encoding="utf-8")
    config = carregar_configuracao(caminho)
    checar("configuração personalizada altera quantidade", config["quantidade_maxima"] == 3, config)
    checar("configuração personalizada preserva ordem das ações", config["acoes"] == ["a", "b"], config)
    checar("campos opcionais ausentes recebem padrão", config["rotulos"] == {} and config["simbolos"] == {}, config)
    checar("imagens ausentes recebem padrão", config["imagens"] == {}, config)
    caminho.write_text(json.dumps({"acoes": [{"id": "a", "pagina": 2}, "b"]}), encoding="utf-8")
    checar("ações novas preservam página e ids antigos ficam na página 1", acoes_configuradas(carregar_configuracao(caminho)) == [("a", 2), ("b", 1)])

if falhas:
    raise SystemExit(f"{len(falhas)} falha(s): {', '.join(falhas)}")
print("\nGesture Wheel: tudo certo.")
