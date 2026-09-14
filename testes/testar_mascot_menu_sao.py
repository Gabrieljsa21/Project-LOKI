# -*- coding: utf-8 -*-
"""Script avulso pra validar o Menu SAO (`GAIA_MENU_SAO.md`, 2026-09-02) -
sem framework de teste (mesmo padrão de testes/testar_mascot_*.py), roda
cada caso e imprime PASS/FAIL. Cobre: `platform_windows.lado_com_mais_
espaco` (helper novo), `SafetyController` como conjunto de bloqueios (não
um bool único), `BehaviorScheduler` reiniciando cooldown ao liberar
autonomia sem gastar orçamento por hora, `MenuSAO` (estado/animação/
roteamento de clique/bloqueio) construindo um `MascotApp` real em modo
demonstração, e o acumulador de scroll de `MascotWindow.wheelEvent`.

Roda offscreen (`QT_QPA_PLATFORM=offscreen`) - sem janela/hotkey global de
verdade, mesmo motivo de `testar_mascot_protocolo.py`.
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz do projeto

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

from mascot import platform_windows, state_catalog
from mascot.animation_controller import AnimationController
from mascot.asset_repository import AssetRepository
from mascot.gesture_wheel import CAMINHO_CONFIG, acoes_configuradas, carregar_configuracao
from mascot.gesture_wheel_editor import CATEGORIA_TUDO, IDS_ESCOLHIVEIS, categoria_animacao
from mascot.safety import SafetyController
from mascot.window import MascotWindow

# 🔥 Achado rodando este teste várias vezes (2026-09-02) - `MascotApp` usa
# um `SafetyController` REAL (não um substituto fixo como `_SafetyFixo`
# de `testar_mascot_behaviors.py`, que já documenta esse mesmo problema:
# "SafetyController real depende do foco de janela do Windows no momento
# do teste, não-determinístico"). Sem neutralizar isso, qualquer janela
# em tela cheia/jogo/RDP no MOMENTO do teste (nada a ver com o Menu SAO)
# faz `autonomia_permitida` ficar `False` mesmo com o conjunto de
# bloqueios de interação vazio - falha intermitente, não bug do Menu SAO.
platform_windows.deve_pausar_autonomia = lambda: False

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


def bombear(segundos):
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        app.processEvents()
        time.sleep(0.01)


def evento_roda(delta_y: int) -> QWheelEvent:
    return QWheelEvent(
        QPointF(0, 0), QPointF(0, 0), QPoint(0, 0), QPoint(0, delta_y),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


# ----------------------------------------------------------------------
# platform_windows.lado_com_mais_espaco
checar(
    "mais espaço à direita escolhe 'right'",
    platform_windows.lado_com_mais_espaco(x=100, largura=50, area_x=0, area_largura=1000) == "right",
)
checar(
    "mais espaço à esquerda escolhe 'left'",
    platform_windows.lado_com_mais_espaco(x=900, largura=50, area_x=0, area_largura=1000) == "left",
)
checar(
    "empate exato cai em 'right'",
    platform_windows.lado_com_mais_espaco(x=475, largura=50, area_x=0, area_largura=1000) == "right",
)

# ----------------------------------------------------------------------
# SafetyController como CONJUNTO de bloqueios (2026-09-02) - não um bool
safety = SafetyController()
safety._pausar_por_plataforma = False  # nunca depende do foco de janela real do Windows neste teste
safety._recalcular()

eventos_autonomia = []
safety.autonomia_alterada.connect(lambda permitida: eventos_autonomia.append(permitida))

checar("autonomia permitida por padrão (sem bloqueios)", safety.autonomia_permitida is True)
safety.bloquear_autonomia("companion_panel")
checar("um bloqueio já é suficiente pra negar autonomia", safety.autonomia_permitida is False)
safety.bloquear_autonomia("menu_sao")
checar("dois bloqueios simultâneos - ainda negada", safety.autonomia_permitida is False)
safety.liberar_autonomia("companion_panel")
checar("liberar UM dos dois motivos não libera autonomia - o outro ainda segura", safety.autonomia_permitida is False)
safety.liberar_autonomia("menu_sao")
checar("liberar o ÚLTIMO motivo libera autonomia de verdade", safety.autonomia_permitida is True)
safety.liberar_autonomia("motivo_que_nunca_bloqueou")
checar("liberar um motivo que não estava bloqueando não crasha nem re-emite à toa", eventos_autonomia == [False, True])

# ----------------------------------------------------------------------
# MascotWindow.wheelEvent - acumulador com limiar e reset por inatividade
repositorio = AssetRepository()
controller = AnimationController(repositorio=repositorio)
janela = MascotWindow(controller)

scroll_baixo, scroll_cima = [], []
janela.scroll_baixo_confirmado.connect(lambda: scroll_baixo.append(True))
janela.scroll_cima_confirmado.connect(lambda: scroll_cima.append(True))

janela.wheelEvent(evento_roda(-60))
checar("um delta abaixo do limiar (60 de 120) ainda não confirma nada", not scroll_baixo and not scroll_cima)
janela.wheelEvent(evento_roda(-60))
checar("acumulado até o limiar confirma scroll pra baixo", scroll_baixo == [True])

janela._acumulador_scroll = 0.0
janela.wheelEvent(evento_roda(200))
checar("um delta bem acima do limiar confirma scroll pra cima na hora", scroll_cima == [True])

janela._acumulador_scroll = -100.0  # se NÃO resetasse, +(-90) do próximo evento cruzaria o limiar (-190)
janela._ultimo_scroll_s = time.monotonic() - 1.0  # mais velho que o limiar de reset (0.3s)
janela.wheelEvent(evento_roda(-90))
checar(
    "acumulador reseta depois de um gap de inatividade - -100 acumulado antigo + -90 novo NÃO se somam",
    scroll_baixo == [True],  # continua só o 1 disparo anterior; o -90 sozinho não cruza o limiar de -120
)

janela._arrastando = True
janela._acumulador_scroll = 0.0
janela.wheelEvent(evento_roda(-200))
checar("scroll ignorado durante arraste real", scroll_baixo == [True])
janela._arrastando = False

controller.parar()

# ----------------------------------------------------------------------
# MenuSAO completo - via MascotApp real em modo demonstração (mesmo padrão
# de testar_mascot_protocolo.py: sem GAIA_MASCOT_CANAL/TOKEN)
from mascot import menu_sao as menu_sao_module
from mascot import process_main

mascot_app = process_main.MascotApp()
menu = mascot_app.menu_sao

checar(
    "serviço de conversa é QObject sem janela, nunca um QWidget/CompanionPanel oculto",
    isinstance(mascot_app.conversation_service, QObject)
    and not isinstance(mascot_app.conversation_service, QWidget),
)
checar(
    "runtime não cria nenhuma janela top-level intitulada 'Galateia'",
    all(widget.windowTitle() != "Galateia" for widget in QApplication.topLevelWidgets()),
    [widget.windowTitle() for widget in QApplication.topLevelWidgets()],
)

checar("menu_sao existe e começa fechado", menu is not None and menu._estado == "closed")
checar("autonomia permitida antes de abrir o menu", mascot_app.safety.autonomia_permitida is True)

menu.abrir()
checar("abrir() muda o estado pra 'opening' na hora", menu._estado == "opening")
checar("abrir() bloqueia autonomia imediatamente (não espera a animação)", mascot_app.safety.autonomia_permitida is False)
checar("direção fica registrada (doc: 'armazenada enquanto o menu estiver aberto')", menu.direcao in ("left", "right"))

checar("círculo ainda animando (progresso < 1) não dispara hover-expand", menu._circulos[0]._progresso < 0.999)
menu._circulos[0].enterEvent(None)
checar("hover num círculo AINDA animando é ignorado (evita expandir antes dele assentar)", menu._hover_estado == "closed")
menu._circulos[0].leaveEvent(None)  # limpa o hover simulado antes de deixar a animação real terminar

bombear(1.0)  # sobra de tempo pros 4 itens (3*55ms atraso + 220ms cada) convergirem
checar("estado converge pra 'open' sozinho", menu._estado == "open")
checar("os 4 círculos terminam com progresso 1.0", all(c._progresso >= 0.999 for c in menu._circulos))

# hover-expand button (2026-09-02, "Oq eu queria era a ideia de
# hover-expand button" - o PRÓPRIO círculo vira pílula, sem rótulo separado)
primeiro_circulo = menu._circulos[0]
checar("círculo começa sem expandir (hover_progresso 0)", primeiro_circulo._hover_progresso == 0.0)
checar("largura reservada do widget é a MAIOR pílula entre os 4 itens (todos alinhados na mesma borda)", primeiro_circulo.width() == menu.width())
checar(
    "TODOS os círculos expandem pra MESMA largura (achado ao vivo: 'os botoes... tem de ter a msm largura')",
    len({c._largura_expandida for c in menu._circulos}) == 1,
)

# largura reservada tem que caber o texto de VERDADE na fonte de VERDADE
# usada em paintEvent - achado ao vivo (2026-09-02): "o texto maior esta
# sendo cortado quando o botao abre para a esquerda" (media com a fonte
# PADRÃO do widget, menor que a fonte de desenho de 10pt, cortava
# "Conversar", o mais longo).
from PySide6.QtGui import QFont, QFontMetrics as _QFM  # noqa: E402

_fonte_medida = QFont(menu.font())
_fonte_medida.setPointSizeF(menu_sao_module.FONTE_ROTULO_PT)
_fm_rotulo = _QFM(_fonte_medida)
for _id_, _rotulo, _, _ in menu_sao_module.ITENS:
    _necessario = (
        menu_sao_module.DIAMETRO_CIRCULO + menu_sao_module.PADDING_PILULA_H
        + _fm_rotulo.horizontalAdvance(_rotulo) + menu_sao_module.PADDING_PILULA_H
    )
    checar(
        f"largura reservada cabe '{_rotulo}' na fonte de desenho (10pt) sem cortar",
        menu.width() >= _necessario,
        (menu.width(), _necessario),
    )
primeiro_circulo.enterEvent(None)
checar("hover num círculo já assentado (progresso 1.0) começa a expandir", menu._hover_estado == "opening" and menu._circulo_animando is primeiro_circulo)
bombear(0.5)
checar("expansão converge pra 'open' com hover_progresso 1.0", menu._hover_estado == "open" and primeiro_circulo._hover_progresso >= 0.999)
primeiro_circulo.leaveEvent(None)
checar("tirar o mouse começa a recolher", menu._hover_estado == "closing")
bombear(0.5)
checar("recolhe de vez (hover_progresso volta a 0, estado 'closed')", menu._hover_estado == "closed" and primeiro_circulo._hover_progresso == 0.0)

segundo_circulo = menu._circulos[1]
primeiro_circulo.enterEvent(None)
bombear(0.5)
checar("hover no 1º círculo expandiu ele", primeiro_circulo._hover_progresso >= 0.999)
primeiro_circulo.leaveEvent(None)
segundo_circulo.enterEvent(None)
bombear(0.5)
checar("trocar de círculo (leave do 1º + enter do 2º) recolhe o antigo e expande o novo", primeiro_circulo._hover_progresso <= 0.001 and segundo_circulo._hover_progresso >= 0.999)
segundo_circulo.leaveEvent(None)
bombear(0.5)

# "Conversar" (corrigido 2026-09-06) - deixou de abrir o CompanionPanel
# direto; abre o Conversation Overlay ("Bubble Mode", `conversation_
# overlay/`) - o painel tradicional só entra via "Ver completo"/"Expandir".
checar("serviço de conversa permanece sem representação visual", not isinstance(mascot_app.companion_panel, QWidget))
menu._ao_clicar("conversar")
checar("clicar 'Conversar' ativa o Conversation Overlay (Bubble Mode)", mascot_app.conversation.esta_ativo and mascot_app.conversation._input.isVisible())
checar("'Conversar' não cria o painel tradicional", all(widget.windowTitle() != "Galateia" for widget in QApplication.topLevelWidgets()))
checar("qualquer clique fecha o menu", menu._estado in ("closing", "closed"))
checar("Conversation Overlay sozinho (motivo próprio) já segura o bloqueio mesmo com o menu fechando", mascot_app.safety.autonomia_permitida is False)
bombear(1.0)
checar("menu terminou de fechar", menu._estado == "closed")
checar("autonomia CONTINUA bloqueada - a conversa ainda está ativa", mascot_app.safety.autonomia_permitida is False)
mascot_app.conversation.sair()
checar("sair da conversa libera o motivo dela", mascot_app.safety.autonomia_permitida is True)

# "Voz" (corrigido 2026-09-06) - clicar deixou de ciclar direto; abre um
# Nível 2 (menu continua aberto), escolher uma opção aplica na hora no
# MESMO serviço de conversa (nunca um estado próprio duplicado) e volta sozinho
# ao Nível 1, com o círculo "Voz" já mostrando o ícone/rótulo do modo novo.
from mascot import conversation_service as conversation_service_module  # noqa: E402

modo_antes = mascot_app.conversation_service.modo_voz_atual
menu.abrir()
bombear(1.0)
circulo_voz = menu._circulo_voz_nivel1
glifo_antes = circulo_voz._glifo
menu._ao_clicar("voz")
checar("clicar 'Voz' NÃO fecha o menu - abre o Nível 2", menu._nivel == 2 and menu.esta_aberto)
checar("Nível 1 (4 itens) fica escondido enquanto o Nível 2 está de pé", all(not c.isVisible() for c in menu._circulos))
checar("Nível 2 mostra as 3 opções de voz + Voltar, já visíveis (troca instantânea)", all(c.isVisible() and c._progresso >= 0.999 for c in menu._circulos_voz))

indice_modo_alvo = 0 if modo_antes != menu_sao_module.ORDEM_NIVEL2_VOZ[0] else 1
modo_alvo = menu_sao_module.ORDEM_NIVEL2_VOZ[indice_modo_alvo]
circulo_marcado_antes = [c for c in menu._circulos_voz if c._marcado]
checar(
    "a opção do modo ATUAL nasce marcada no Nível 2 (destaque de contorno)",
    len(circulo_marcado_antes) == 1 and circulo_marcado_antes[0]._rotulo == conversation_service_module.MODOS_VOZ_TEXTO[modo_antes],
)
menu._ao_selecionar_modo_voz(modo_alvo)
checar("selecionar uma opção aplica o modo no serviço de conversa", mascot_app.conversation_service.modo_voz_atual == modo_alvo)
checar("selecionar uma opção volta sozinho ao Nível 1 (menu continua aberto)", menu._nivel == 1 and menu.esta_aberto)
checar("Nível 1 volta a ficar visível, Nível 2 escondido de novo", all(c.isVisible() for c in menu._circulos) and all(not c.isVisible() for c in menu._circulos_voz))
checar("círculo 'Voz' do Nível 1 já reflete o NOVO modo (ícone mudou)", circulo_voz._glifo == conversation_service_module.MODOS_VOZ_GLIFO[modo_alvo] and circulo_voz._glifo != glifo_antes)

menu._ao_clicar("voz")
checar("reabrir o Nível 2 marca a opção certa pro modo JÁ trocado", any(c._marcado and c._rotulo == conversation_service_module.MODOS_VOZ_TEXTO[modo_alvo] for c in menu._circulos_voz))
circulo_voltar = menu._circulos_voz[-1]
checar("último círculo do Nível 2 é o 'Voltar'", circulo_voltar._rotulo == "Voltar")
circulo_voltar.clicado.emit()
checar("'Voltar' retorna ao Nível 1 SEM mudar o modo", menu._nivel == 1 and mascot_app.conversation_service.modo_voz_atual == modo_alvo)

menu._ao_clicar("voz")
checar("Escape no Nível 2 volta só um nível (não fecha o menu inteiro)", menu._nivel == 2)
evento_escape_voz = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
menu.keyPressEvent(evento_escape_voz)
checar("1º Escape sai do Nível 2 e mantém o menu aberto", menu._nivel == 1 and menu.esta_aberto)
menu.keyPressEvent(evento_escape_voz)
bombear(1.0)
checar("2º Escape (já no Nível 1) fecha o menu normalmente", menu._estado == "closed")

checar(
    "nenhum item nasce desabilitado (2026-09-03: os 4 ganharam conteúdo real)",
    menu_sao_module.IDS_DESABILITADOS == frozenset(),
    menu_sao_module.IDS_DESABILITADOS,
)
circulo_acoes = menu._circulos[2]
circulo_gaia = menu._circulos[3]
checar("círculo 'Ações' NÃO está desabilitado", circulo_acoes._desabilitado is False)
checar("círculo 'Configurações' NÃO está desabilitado", circulo_gaia._desabilitado is False)

# "Ações" - MESMA lógica da bandeja ("Forçar animação"), só lista
# transições válidas a partir do estado lógico atual, sem catálogo inteiro
menu_animacao = menu._construir_menu_forcar_animacao()
validas_esperadas = sorted(
    e.id for e in state_catalog.transicoes_validas_a_partir_de(mascot_app.controller.estado_logico)
    if e.id not in state_catalog.IDS_OCULTOS_DE_SELECAO
)
rotulos_menu = [a.text() for a in menu_animacao.actions()]
checar(
    "menu de 'Ações' lista as MESMAS transições válidas do estado atual (playground da bandeja)",
    rotulos_menu == validas_esperadas if validas_esperadas else rotulos_menu == ["(nenhuma a partir do estado atual)"],
    rotulos_menu,
)

# "Configurações" - abre o modal NATIVO local (mascot/modal_configuracoes.py),
# nunca precisa de bridge/GAIA rodando (funciona igual em modo demonstração)
checar("mascot_app ainda não tem modal de configurações construído", mascot_app._modal_configuracoes is None)
menu._abrir_configuracoes()
checar("'Configurações' constrói o modal (instância única em MascotApp)", mascot_app._modal_configuracoes is not None)
checar("modal de configurações fica visível", mascot_app._modal_configuracoes.isVisible())
checar(
    "configurações têm as cinco abas principais (sem emoji, achado ao vivo 2026-09-04: 'os icones sao inuteis')",
    [mascot_app._modal_configuracoes._abas.tabText(i) for i in range(mascot_app._modal_configuracoes._abas.count())]
    == ["Geral", "Aparência", "Ações", "Movimento", "Sistema"],
)
pills = mascot_app._modal_configuracoes._editor_gesture_wheel._botoes_pill
checar(
    "Ações separa o editor em uma pill por categoria + \"Tudo\" (2026-09-04: redesign, substitui "
    "as sub-abas antigas; \"Tudo\" acrescentada 2026-09-05 pro arraste valer entre categorias; "
    "\"Outras\" virou pasta 2026-09-06 - \"Leque\" mora dentro dela agora, sem pill própria)",
    list(pills.keys())
    == ["Tudo", "Movimento", "Especiais", "Sentada", "Flutuando", "Transições", "Expressões", "Outras"],
)
# "Tudo" (2026-09-05) - mostra TODAS as escolhíveis juntas, não só as da
# categoria marcada; é aqui que o arraste entre categorias diferentes faz
# sentido (ver `_mover_na_ordem`).
editor = mascot_app._modal_configuracoes._editor_gesture_wheel
pills[CATEGORIA_TUDO].click()
checar(
    "pill \"Tudo\" mostra TODAS as animações escolhíveis, não só de uma categoria",
    set(editor._linhas.keys()) == set(IDS_ESCOLHIVEIS),
    len(editor._linhas),
)

# "Outras" (2026-09-06, "'Outras' n vai ser tag de animação, vai ser
# tipo uma pasta contendo categorias") - selecionar uma sub-categoria
# (sem passar pela pill dela mesma, que não existe mais) filtra igual a
# qualquer pill normal e marca "Outras" como ativa visualmente.
editor._selecionar_categoria("Leque")
checar(
    "sub-categoria \"Leque\" (dentro da pasta \"Outras\") filtra igual a uma pill normal",
    set(editor._linhas.keys())
    == {aid for aid in IDS_ESCOLHIVEIS if categoria_animacao(aid) == "Leque"}
    and len(editor._linhas) > 0,
    len(editor._linhas),
)
checar(
    "pill \"Outras\" fica marcada como ativa quando uma sub-categoria dela está selecionada",
    pills["Outras"].isChecked() and not any(p.isChecked() for nome, p in pills.items() if nome != "Outras"),
)
# Volta pra "Tudo" - os testes de arraste logo abaixo esperam TODAS as
# animações visíveis em `_linhas` (contaminação já vista antes com
# "leque"/`forcar_estado`, mesmo mecanismo aqui: categoria filtrada some
# de `_linhas`, quebrando quem espera achar qualquer id ali).
editor._selecionar_categoria(CATEGORIA_TUDO)

# Arraste real (2026-09-05, "cada card... tem q permitir arrastar e mover,
# trocando de posicao com outros") - `_mover_na_ordem` é o que o
# `eventFilter` chama depois de um drop de verdade; testado direto aqui
# (sem simular QDrag) pela MESMA razão dos outros testes de física deste
# arquivo - o efeito (nova posição em `_ordem`) importa, não o evento
# bruto do Qt.
ordem_antes = list(editor._ordem)
origem, destino = ordem_antes[5], ordem_antes[1]
editor._mover_na_ordem(origem, destino, depois=False)
checar(
    "arrastar um card pra ANTES de outro reordena _ordem de verdade",
    editor._ordem.index(origem) == editor._ordem.index(destino) - 1,
    (editor._ordem.index(origem), editor._ordem.index(destino)),
)
editor._mover_na_ordem(origem, destino, depois=True)
checar(
    "arrastar um card pra DEPOIS de outro também funciona",
    editor._ordem.index(origem) == editor._ordem.index(destino) + 1,
    (editor._ordem.index(origem), editor._ordem.index(destino)),
)
checar("_mover_na_ordem preserva o TOTAL de ids (nada duplicado/sumido)", sorted(editor._ordem) == sorted(ordem_antes))

# Indicador de inserção (2026-09-05, "ficando aquela linha entre os cards
# onde ele vai ser inserido") - linha única reaproveitada, nunca duplicada
# no layout mesmo mostrada em cima de linhas diferentes em sequência.
linha_um, linha_dois = editor._linhas[editor._ordem[0]], editor._linhas[editor._ordem[1]]
checar("indicador de inserção começa escondido/fora do layout", editor._lista_layout.indexOf(editor._indicador_insercao) == -1)
editor._mostrar_indicador_em(linha_um, depois=False)
checar(
    "indicador aparece IMEDIATAMENTE ANTES da linha-alvo (metade de cima)",
    editor._lista_layout.indexOf(editor._indicador_insercao) == editor._lista_layout.indexOf(linha_um) - 1,
)
editor._mostrar_indicador_em(linha_dois, depois=True)
checar(
    "mostrar de novo em outra linha MOVE o mesmo indicador (nunca duplica no layout)",
    editor._lista_layout.indexOf(editor._indicador_insercao) == editor._lista_layout.indexOf(linha_dois) + 1,
)
editor._esconder_indicador()
checar("esconder tira o indicador do layout de novo", editor._lista_layout.indexOf(editor._indicador_insercao) == -1)

# Página passou a ser DERIVADA da posição em `_ordem` entre as MARCADAS
# (não mais um spinbox "Ordem" por linha) - as 3 primeiras da ordem atual
# ficam na página 1 com limite=3. `_aplicar()` grava de VERDADE em
# `data/gesture_wheel.json` (o MESMO arquivo do app real, ver nota de
# isolamento fraco no topo do arquivo) - faz backup/restaura os bytes
# originais depois, pra não sobrescrever a configuração real do usuário.
_backup_gesture_wheel_json = CAMINHO_CONFIG.read_bytes() if CAMINHO_CONFIG.is_file() else None
try:
    editor._selecionadas = set(editor._ordem[:6])
    editor._limite = 3
    editor._spin_limite.setValue(3)
    editor._aplicar()
    salvas = acoes_configuradas(carregar_configuracao())
finally:
    if _backup_gesture_wheel_json is None:
        CAMINHO_CONFIG.unlink(missing_ok=True)
    else:
        CAMINHO_CONFIG.write_bytes(_backup_gesture_wheel_json)
paginas_por_id = dict(salvas)
checar(
    "página salva bate com a posição em _ordem entre as marcadas, respeitando o limite",
    [paginas_por_id[aid] for aid in editor._ordem[:6]] == [1, 1, 1, 2, 2, 2],
    [paginas_por_id.get(aid) for aid in editor._ordem[:6]],
)

# Botão de remover imagem (ícone de lixeira, 2026-09-05) - substitui o
# menu "⋮" (só tinha uma opção lá dentro, "usar iniciais automáticas").
# Nome do teste evita colocar o emoji em si na string (console deste
# ambiente não decodifica caractere fora do BMP, tipo 🗑 - crasharia o
# `print` do `checar`, não é limitação da UI/Qt).
aid_teste = editor._ordem[0]
botao_remover = editor._botoes_remover_imagem[aid_teste]
editor._imagens.pop(aid_teste, None)  # rascunho em memória - garante ponto de partida sem imagem, não toca disco
editor._atualizar_miniatura(aid_teste)
checar("botão de remover imagem nasce desabilitado sem imagem custom", not botao_remover.isEnabled())
editor._imagens[aid_teste] = "assets/gesture_wheel/icons/inexistente.png"
editor._atualizar_miniatura(aid_teste)
checar("botão de remover imagem habilita assim que uma imagem é atribuída", botao_remover.isEnabled())
editor._limpar_imagem(aid_teste)
checar("botão de remover imagem desabilita de novo depois de remover a imagem", not botao_remover.isEnabled())

primeira_instancia = mascot_app._modal_configuracoes
menu._abrir_configuracoes()
checar("clicar de novo reaproveita a MESMA instância (nunca duas fontes de verdade)", mascot_app._modal_configuracoes is primeira_instancia)
mascot_app._modal_configuracoes.hide()
menu._obter_bridge = lambda: None  # restaura modo demonstração pro resto do teste

# "🔄 Reiniciar Mascot" na bandeja (2026-09-06, pedido do usuário: "coloca
# o botão de riniciar loki tbm na bandeja") - fonte única em `MascotApp.
# reiniciar_mascot`, o modal só delega (ver `ModalConfiguracoes.
# _reiniciar_mascot`). `subprocess.Popen`/`QApplication.quit`/
# `confirmar_acao` mockados - nunca deixar isso realmente fechar o
# processo do teste.
acoes_bandeja = {a.text(): a for a in mascot_app.tray.contextMenu().actions()}
checar("bandeja tem a ação \"Reiniciar Mascot\"", "🔄 Reiniciar Mascot" in acoes_bandeja)
chamadas_popen = []
chamadas_quit = []
_popen_original = process_main.subprocess.Popen
_quit_original = process_main.QApplication.quit
_confirmar_original = process_main.confirmar_acao
process_main.subprocess.Popen = lambda *a, **k: chamadas_popen.append((a, k))
process_main.QApplication.quit = lambda: chamadas_quit.append(True)
process_main.confirmar_acao = lambda *a, **k: True
try:
    mascot_app.reiniciar_mascot()
finally:
    process_main.subprocess.Popen = _popen_original
    process_main.QApplication.quit = _quit_original
    process_main.confirmar_acao = _confirmar_original
checar("reiniciar_mascot sobe um processo novo (subprocess.Popen chamado 1x)", len(chamadas_popen) == 1)
checar(
    "reiniciar_mascot sobe -m mascot.process_main",
    chamadas_popen and chamadas_popen[0][0][0] == [sys.executable, "-m", "mascot.process_main"],
)
checar("reiniciar_mascot fecha o processo atual DEPOIS de subir o novo", chamadas_quit == [True])

estado_antes = menu._estado
menu._ao_clicar("acoes")
checar("clicar 'Ações' fecha o menu normalmente (não é mais item inerte)", menu._estado in ("closing", "closed"))
checar("clicar 'Ações' abre a Gesture Wheel contextual", menu._gesture_wheel.esta_aberta)
config_roda = carregar_configuracao()
configuradas = acoes_configuradas(config_roda)
# 2026-09-05: a roda deixou de se limitar às transições válidas do estado
# ATUAL ("o proposito dessa tela é listar todas as animacoes q posso
# ativar, porem n se limitar as opcoes do estado atual") - mostra
# qualquer id configurado que ainda exista no catálogo (a preparação pro
# estado exigido acontece só no clique, ver `testar_gesture_wheel.py`/
# `AnimationController.preparar_para`).
ids_permitidos = [
    aid for aid in state_catalog.CATALOGO if aid not in state_catalog.IDS_OCULTOS_DE_SELECAO
]
if configuradas:
    primeira_pagina = min(pagina for animation_id, pagina in configuradas if animation_id in ids_permitidos)
    esperadas_roda = [
        animation_id for animation_id, pagina in configuradas
        if pagina == primeira_pagina and animation_id in ids_permitidos
    ][:max(1, min(8, int(config_roda.get("quantidade_maxima", 8))))]
else:
    esperadas_roda = validas_esperadas[:8]  # bootstrap raro (sem config salva) ainda restringe ao estado atual
checar(
    "Gesture Wheel mostra TODAS as ações configuradas (não só as válidas do estado atual), respeitando página e limite",
    [item.id for item in menu._gesture_wheel._itens_visiveis] == esperadas_roda,
)
if len(menu._gesture_wheel._paginas) > 1:
    pagina_antes = menu._gesture_wheel._indice_pagina
    menu._gesture_wheel.trocar_pagina(1)
    checar("rolagem troca a página plana da roda", menu._gesture_wheel._indice_pagina != pagina_antes)
    menu._gesture_wheel.trocar_pagina(-1)  # volta pra 1ª página antes do teste de filtro abaixo

# Filtro por Ctrl+F (2026-09-06, pedido do usuário: "qnd mouse tiver na
# gaia ou em alguma animacao, apertar ctrl+f filtraria essas animações").
wheel = menu._gesture_wheel
checar(
    "mouse sobre a Gaia (centro) conta como 'sobre a Gaia ou animação'",
    wheel._sobre_gaia_ou_animacao(wheel._centro),
)
if wheel._itens_visiveis:
    centro_item_0 = wheel._centro_item(0)
    checar(
        "mouse sobre um medalhão conta como 'sobre a Gaia ou animação'",
        wheel._sobre_gaia_ou_animacao(centro_item_0),
    )
ponto_longe = QPointF(wheel._centro.x() + 10_000, wheel._centro.y() + 10_000)
checar("mouse longe de tudo NÃO conta como 'sobre a Gaia ou animação'", not wheel._sobre_gaia_ou_animacao(ponto_longe))

itens_antes_filtro = list(wheel._itens_todos)
wheel._mostrar_campo_filtro()
checar("Ctrl+F abre o campo de filtro (visível)", wheel._campo_filtro.isVisible())

alvo = itens_antes_filtro[0]
termo_unico = alvo.id.split("_")[0]  # pedaço do id, só pra achar pelo menos essa 1 animação
wheel._campo_filtro.setText(termo_unico)
checar(
    "filtro reduz a lista (mostra só quem bate com o termo digitado)",
    all(termo_unico in f"{item.id} {item.rotulo}".casefold() for pagina in wheel._paginas for item in pagina),
)
checar(
    "animação-alvo continua aparecendo depois do filtro",
    any(item.id == alvo.id for pagina in wheel._paginas for item in pagina),
)

wheel._campo_filtro.setText("termo-que-nao-bate-em-nada-12345")
checar("filtro sem nenhum resultado não crasha (fica vazio)", wheel._itens_visiveis == [])

wheel._esconder_campo_filtro()
checar("esconder o filtro limpa o texto e o campo some", not wheel._campo_filtro.isVisible() and wheel._campo_filtro.text() == "")
checar(
    "esconder o filtro restaura TODAS as animações de novo",
    sorted(item.id for pagina in wheel._paginas for item in pagina) == sorted(item.id for item in itens_antes_filtro),
)
checar("roda continua ABERTA depois de mexer no filtro (focus não fecha ela)", wheel.esta_aberta)

wheel._mostrar_campo_filtro()
evento_escape = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
wheel.keyPressEvent(evento_escape)
checar("Escape com filtro aberto fecha só o filtro, não a roda inteira", not wheel._campo_filtro.isVisible() and wheel.esta_aberta)

menu.fechar(imediato=True)
menu.abrir()
checar("Menu SAO não reabre enquanto a roda de ações está ativa", menu._estado == "closed")
menu.fechar_tudo(imediato=True)

for b in mascot_app.scheduler._behaviors:
    b.ultimo_disparo = 0.0
    b.disparos_na_janela = ["marcador"]
menu.abrir()
bombear(1.0)
antes_de_fechar = time.monotonic()
menu.fechar(imediato=True)
checar("fechar(imediato=True) muda pra 'closed' na hora, sem esperar animação", menu._estado == "closed")
checar("fechar(imediato=True) libera autonomia na hora também", mascot_app.safety.autonomia_permitida is True)
checar(
    "liberar autonomia reinicia ultimo_disparo pra AGORA (não deixa ela sair voando na hora de fechar)",
    all(abs(b.ultimo_disparo - antes_de_fechar) < 1.0 for b in mascot_app.scheduler._behaviors),
)
checar(
    "reiniciar cooldown NÃO conta como disparo real - orçamento por hora intacto",
    all(b.disparos_na_janela == ["marcador"] for b in mascot_app.scheduler._behaviors),
)

# reabrir NO MEIO de um fechamento em andamento - achado por um teste
# intermitente (o menu.abrir() de uma rodada anterior às vezes corria
# contra o fechamento da rodada anterior ainda não ter convergido) -
# sobrescrever _estado pra "opening" sem nunca liberar o bloqueio antigo
# vazava "menu_sao" pra sempre. bombear(0.05) simula "reabriu rápido, mas
# não instantâneo" - o suficiente pra estar em "closing" de verdade, não
# mais em "open".
menu.abrir()
bombear(1.0)
menu.fechar()  # começa a fechar, com animação
bombear(0.05)  # NÃO espera terminar - ainda em "closing" de verdade
checar("confirma que ainda está fechando (não terminou) antes do teste de verdade", menu._estado == "closing")
menu.abrir()  # reabre NO MEIO do fechamento anterior
checar("reabrir no meio do fechamento não trava num estado inválido", menu._estado == "opening")
checar("reabrir no meio do fechamento não vaza o bloqueio antigo (recalculado do zero)", mascot_app.safety.autonomia_permitida is False)
bombear(1.0)
checar("converge normalmente pra 'open' depois da reabertura no meio do fechamento", menu._estado == "open")
menu.fechar(imediato=True)
bombear(0.2)
checar("fecha de vez sem deixar bloqueio vazado depois de todo esse malabarismo", mascot_app.safety.autonomia_permitida is True)

mascot_app.controller.parar()


print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
