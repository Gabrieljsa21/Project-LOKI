# -*- coding: utf-8 -*-
"""LOKI dentro da bandeja da GAIA (2026-11-14): sem ícone próprio quando a
GAIA liga (`LOKI_SEM_ICONE_BANDEJA=1`) e comandos da bandeja chegando pelo
evento `tray_action`. Roda offscreen, sem janela nem socket."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LOKI_SEM_ICONE_BANDEJA"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

from core import mascot_events
from mascot import process_main

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


mascot_app = process_main.MascotApp()
checar("com LOKI_SEM_ICONE_BANDEJA=1 não existe ícone próprio", mascot_app.tray is None)

janela = mascot_app.window
visivel_antes = janela.isVisible()
# caminho completo: o evento chega como chegaria pelo canal da GAIA
mascot_app._processar_evento_gaia(mascot_events.evento_tray_action("alternar_visibilidade"))
checar("Mostrar/ocultar pelo evento da GAIA inverte a visibilidade", janela.isVisible() != visivel_antes)
mascot_app.executar_acao_bandeja("alternar_visibilidade")
checar("segundo Mostrar/ocultar volta ao estado anterior", janela.isVisible() == visivel_antes)

clique_antes = janela.click_through_ativo
mascot_app.executar_acao_bandeja("alternar_clique_atraves")
checar("Clique-através inverte o estado", janela.click_through_ativo != clique_antes)
mascot_app.executar_acao_bandeja("alternar_clique_atraves")
checar("segundo Clique-através volta ao estado anterior", janela.click_through_ativo == clique_antes)

mascot_app.config_mascot["autonomy"] = "viva"
mascot_app.executar_acao_bandeja("alternar_modo_seguro")
checar("Modo seguro para a autonomia", mascot_app.config_mascot["autonomy"] == "parada" and mascot_app.modo_seguro_ativo)
mascot_app.executar_acao_bandeja("alternar_modo_seguro")
checar("sair do Modo seguro devolve a autonomia escolhida", mascot_app.config_mascot["autonomy"] == "viva" and not mascot_app.modo_seguro_ativo)

janela.move(0, 0)
checar("Centralizar é aceito", mascot_app.executar_acao_bandeja("centralizar") is True)
tela = (janela.screen() or QApplication.primaryScreen()).availableGeometry()
checar("Centralizar põe a janela no meio da tela",
       abs(janela.x() - (tela.x() + (tela.width() - janela.width()) // 2)) <= 1,
       (janela.x(), tela))

checar("ação desconhecida é recusada sem exceção", mascot_app.executar_acao_bandeja("apagar_tudo") is False)

try:
    mascot_events.evento_tray_action("apagar_tudo")
    checar("o contrato recusa ação fora de ACOES_BANDEJA", False)
except ValueError:
    checar("o contrato recusa ação fora de ACOES_BANDEJA", True)
checar("evento tem o formato do contrato",
       mascot_events.evento_tray_action("centralizar") == {"type": "tray_action", "action": "centralizar"})

del os.environ["LOKI_SEM_ICONE_BANDEJA"]
mascot_sozinho = process_main.MascotApp()
checar("aberto sozinho (sem a variável), o ícone próprio continua", mascot_sozinho.tray is not None)

print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
