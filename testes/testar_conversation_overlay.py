# -*- coding: utf-8 -*-
"""Script avulso pra validar o Conversation Overlay/"Bubble Mode" (Project
LOKI, 2026-09-06) - sem framework de teste (mesmo padrão de
`testes/testar_mascot_*.py`), roda cada caso e imprime PASS/FAIL. Cobre
`positioning.py` (clamp dentro da work area), truncamento de `bubble.py`,
limite/ordem/indicador de `BubbleStack` e a máquina de estados de
`ConversationController` - a integração com o Menu SAO ("Conversar"/
"Voz") já é coberta em `testar_mascot_menu_sao.py`, não duplicada aqui.

Roda offscreen (`QT_QPA_PLATFORM=offscreen`) - mesmo motivo de
`testar_mascot_protocolo.py`."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz do projeto

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from mascot import platform_windows
from mascot.animation_controller import AnimationController
from mascot.asset_repository import AssetRepository
from mascot.conversation_overlay import bubble as bubble_module
from mascot.conversation_overlay import estilo as estilo_module
from mascot.conversation_overlay import input_bar as input_bar_module
from mascot.conversation_overlay import positioning
from mascot.conversation_overlay.bubble import Bubble, IndicadorVoz
from mascot.conversation_overlay.bubble_stack import MAXIMO_BUBBLES_VISIVEIS, BubbleStack
from mascot.conversation_overlay.conversation_controller import ConversationController
from mascot.safety import SafetyController
from mascot.window import MascotWindow

# mesmo achado de `testar_mascot_menu_sao.py` - `SafetyController` real
# depende do foco de janela do Windows no momento do teste, não-determinístico.
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


# ----------------------------------------------------------------------
# positioning.py - correção 2026-09-06 (a v1 ancorava em GAIA.bottom + gap
# sem NENHUMA zona de exclusão; sentada na barra de tarefas, o clamp da
# work area deslizava o composer de volta pra CIMA do corpo dela).
repositorio = AssetRepository()
controller = AnimationController(repositorio=repositorio)
janela = MascotWindow(controller)
tela = janela.screen() or QApplication.primaryScreen()
area_x, area_y, area_w, area_h = platform_windows.obter_work_area_da_tela(tela)


def _intersecta(retangulo_a, x, y, largura, altura) -> bool:
    from PySide6.QtCore import QRect
    return retangulo_a.intersects(QRect(x, y, largura, altura))


def _checar_layout_nunca_cruza_gaia(nome: str, x_janela: int, y_janela: int) -> None:
    """Regra ESTRUTURAL (doc: "Nenhum elemento... pode atravessar ou
    cobrir a bounding box da personagem") - testado em várias posições/
    poses possíveis, não só o caso feliz do centro da tela."""
    janela.move(x_janela, y_janela)
    safe = positioning.character_safe_rect(janela)
    layout = positioning.escolher_layout_conversa(
        janela, largura_bubbles=bubble_module.LARGURA_PADRAO, altura_bubbles=200,
        largura_composer=input_bar_module.LARGURA_PADRAO, altura_composer=input_bar_module.ALTURA_PADRAO,
    )
    x_composer, y_composer = layout["composer_pos"]
    checar(
        f"[{nome}] composer NUNCA intersecta o character_safe_rect",
        not _intersecta(safe, x_composer, y_composer, input_bar_module.LARGURA_PADRAO, input_bar_module.ALTURA_PADRAO),
        (safe.getRect(), (x_composer, y_composer)),
    )
    # bubbles empilham a partir de bubbles_y_base PRA CIMA (longe da GAIA,
    # nunca em direção a ela) - checar só a primeira posição já garante
    # que a pilha inteira nunca cruza (ver `BubbleStack._reposicionar`).
    x_bubble = positioning.eixo_perpendicular(layout["eixo"], layout["bubbles_regiao"], janela, bubble_module.LARGURA_PADRAO)
    y_bubble_base = layout["bubbles_y_base"] - 40  # um bubble baixinho de exemplo, encostado na base
    checar(
        f"[{nome}] bubble mais próximo da GAIA NUNCA intersecta o character_safe_rect",
        not _intersecta(safe, x_bubble, y_bubble_base, bubble_module.LARGURA_PADRAO, 40),
        (safe.getRect(), (x_bubble, y_bubble_base)),
    )


# GAIA "sentada na barra de tarefas" - exatamente o cenário do bug reportado (sem espaço ABAIXO)
_checar_layout_nunca_cruza_gaia("sentada na barra de tarefas", area_x + area_w // 2 - janela.width() // 2, area_y + area_h - janela.height())
_checar_layout_nunca_cruza_gaia("centro da tela", area_x + area_w // 2 - janela.width() // 2, area_y + area_h // 2)
_checar_layout_nunca_cruza_gaia("perto da borda direita", area_x + area_w - janela.width() - 5, area_y + area_h // 2)
_checar_layout_nunca_cruza_gaia("perto da borda esquerda", area_x + 5, area_y + area_h // 2)
_checar_layout_nunca_cruza_gaia("canto inferior direito", area_x + area_w - janela.width() - 5, area_y + area_h - janela.height())

# "lado com mais espaço" - perto da borda direita, a conversa deve preferir a ESQUERDA quando o vertical não coube
janela.move(area_x + area_w - janela.width() - 5, area_y + area_h - janela.height())
layout_lateral = positioning.escolher_layout_conversa(
    janela, largura_bubbles=bubble_module.LARGURA_PADRAO, altura_bubbles=600,
    largura_composer=input_bar_module.LARGURA_PADRAO, altura_composer=input_bar_module.ALTURA_PADRAO,
)
checar(
    "perto da borda direita SEM espaço vertical, o sistema migra pro lado com MAIS espaço (esquerda)",
    layout_lateral["eixo"] == "esquerda",
    layout_lateral["eixo"],
)

# bubbles e composer NUNCA em lados diferentes - mesmo `eixo` sempre
janela.move(area_x + area_w // 2 - janela.width() // 2, area_y + area_h // 2)
layout_vertical = positioning.escolher_layout_conversa(
    janela, largura_bubbles=bubble_module.LARGURA_PADRAO, altura_bubbles=150,
    largura_composer=input_bar_module.LARGURA_PADRAO, altura_composer=input_bar_module.ALTURA_PADRAO,
)
checar(
    "no centro da tela (espaço de sobra), o layout vertical canônico é escolhido (bubbles/composer em lados OPOSTOS por design, não é bug)",
    layout_vertical["eixo"] == "vertical",
    layout_vertical["eixo"],
)
checar(
    "composer fica ABAIXO da GAIA no layout vertical",
    layout_vertical["composer_pos"][1] > positioning.base_visivel_gaia(janela),
)

controller.parar()

# ----------------------------------------------------------------------
# bubble.py - truncamento por altura (busca binária, sempre termina em "…")
fonte = bubble_module.QFont()
fonte.setPointSizeF(10.0)
fm = QFontMetrics(fonte)

texto_curto = "Feito! Discord aberto."
exibido, cortado = bubble_module._truncar_para_altura(fm, texto_curto, 280, 200)
checar("texto curto nunca é cortado", exibido == texto_curto and not cortado)

texto_longo = "Esta é uma resposta bem longa, com muitas frases repetidas. " * 20
exibido, cortado = bubble_module._truncar_para_altura(fm, texto_longo, 280, 200)
checar("texto longo é cortado e termina em '…'", cortado and exibido.endswith("…"))

bubble_longo = Bubble("gaia", texto_longo)
checar("Bubble com texto longo nasce marcado como truncado", bubble_longo._truncado)
checar(
    "Bubble com texto longo respeita a altura máxima (+ rodapé, avatar fica FORA do balão desde 2026-09-07)",
    bubble_longo.height() <= bubble_module.ALTURA_MAXIMA_TEXTO + 2 * bubble_module.PADDING_V + bubble_module.ALTURA_RODAPE + 5,
)
checar("Bubble com texto longo usa a largura MÁXIMA (texto precisa do teto inteiro)", bubble_longo.width() == bubble_module.LARGURA_PADRAO)

# largura por CONTEÚDO (polimento 2026-09-06, doc: "width = clamp(content_width + padding, MIN, MAX)")
bubble_curto = Bubble("usuario", "Já volto.")
checar("Bubble curto NÃO nasce truncado", not bubble_curto._truncado)
checar(
    "Bubble curto NÃO ocupa a largura máxima (largura por conteúdo, não mais fixa)",
    bubble_module.LARGURA_MINIMA <= bubble_curto.width() < bubble_module.LARGURA_PADRAO,
    bubble_curto.width(),
)

bubble_media = Bubble("gaia", "Você tem 3 eventos hoje, quer que eu detalhe?")
checar(
    "duas mensagens de tamanhos bem diferentes produzem LARGURAS diferentes (não é mais um retângulo fixo pra tudo)",
    bubble_media.width() > bubble_curto.width(),
    (bubble_curto.width(), bubble_media.width()),
)

checar("bubble do usuário alinha à DIREITA", bubble_curto.alinhamento == "direita")
checar("bubble da GAIA alinha à ESQUERDA", bubble_longo.alinhamento == "esquerda")

checar("assinatura da GAIA nunca foi prefixo colado no texto", not bubble_longo.texto_exibido.startswith("✦"))
checar("bubble do usuário TAMBÉM tem avatar agora (2026-09-07, referência visual: os dois lados mostram retrato)", bubble_curto._tem_avatar)
checar("bubble 'sistema' NÃO tem avatar (neutro/centralizado)", not Bubble("sistema", "conectando...")._tem_avatar)
checar(
    "bubble da GAIA usa borda CRISTAL (2026-09-07, reversão: referência visual mostra as duas bordas com o mesmo brilho ciano - identidade da GAIA agora vem do retrato, não do contorno)",
    bubble_longo._cor_borda.name() == QColor(estilo_module.CRISTAL).name(),
)
checar("bubble do usuário usa borda CRISTAL", bubble_curto._cor_borda.name() == QColor(estilo_module.CRISTAL).name())
checar("bubble tem timestamp registrado (HH:MM)", len(bubble_curto._hora_criacao) == 5 and bubble_curto._hora_criacao[2] == ":")

# retrato da GAIA nas mensagens dela (pedido do usuário 2026-09-07: "acho
# interessante coloca a foto da gaia nas mensagens dela", depois movido
# pra FORA do balão numa revisão no mesmo dia, com referência visual) -
# cai pro glifo ✦ se o arquivo faltar, nunca quebra.
avatar = bubble_module._avatar_pixmap()
checar(
    "assets/avatar_galateia_chat.png existe e carrega como retrato (senão cai pro glifo dourado, nunca quebra)",
    avatar is not None and not avatar.isNull() and avatar.width() == bubble_module.TAMANHO_AVATAR,
    None if avatar is None else (avatar.width(), avatar.height()),
)
# o retrato só é buscado quando remetente == "gaia" (ver `Bubble.
# _desenhar_avatar` - condicional de 1 linha, revisada direto no código);
# aqui só confirma que "erro" nasce com o remetente certo pra essa
# condicional funcionar.
checar("bubble de erro nasce com remetente='erro' (nunca cai na condição do retrato)", Bubble("erro", "teste").remetente == "erro")

# avatar de gaia/erro fica à ESQUERDA do balão (balão deslocado por
# `LARGURA_AVATAR_AREA`); o do usuário fica encostado à DIREITA, depois
# do balão - larguras diferentes por conteúdo, nunca hardcoded.
checar(
    "balão da GAIA (avatar à esquerda) começa deslocado pela reserva do avatar",
    bubble_longo._x_bubble == bubble_module.LARGURA_AVATAR_AREA,
    bubble_longo._x_bubble,
)
checar(
    "balão do usuário (avatar à direita) começa em x=0 (nada à esquerda dele)",
    bubble_curto._x_bubble == 0,
)
checar(
    "widget INTEIRO (balão + avatar) nunca ultrapassa LARGURA_PADRAO (envelope de `positioning.py` intocado)",
    bubble_longo.width() <= bubble_module.LARGURA_PADRAO and bubble_curto.width() <= bubble_module.LARGURA_PADRAO,
    (bubble_longo.width(), bubble_curto.width()),
)

sinal_expandir = []
bubble_longo.expandir_solicitado.connect(lambda: sinal_expandir.append(True))


class _EventoFalso:
    def __init__(self, ponto):
        self._ponto = ponto

    def button(self):
        return Qt.MouseButton.LeftButton

    def position(self):
        return self._ponto

    def accept(self):
        pass


from PySide6.QtCore import QPointF  # noqa: E402

bubble_longo.mousePressEvent(_EventoFalso(QPointF(bubble_longo._x_bubble + 10, bubble_longo.height() - 5)))
checar("clicar na área de 'Ver completo' emite expandir_solicitado", sinal_expandir == [True])

indicador = IndicadorVoz("ouvindo")
checar("IndicadorVoz nasce com o texto certo pro tipo 'ouvindo'", "Te ouvindo" in indicador.TEXTOS["ouvindo"])
checar(
    "'processando' vira só o símbolo da GAIA + reticências animadas (polimento 2026-09-06, doc: 'prefiro três pontos animados a Pensando...')",
    indicador.TEXTOS["processando"] == "✦",
)

# ----------------------------------------------------------------------
# BubbleStack - limite de 2-3 visíveis, indicador de voz é singleton
repositorio2 = AssetRepository()
controller2 = AnimationController(repositorio=repositorio2)
janela2 = MascotWindow(controller2)
janela2.move(area_x + area_w // 2 - janela2.width() // 2, area_y + area_h // 2)
pilha = BubbleStack(janela2)

for i in range(5):
    pilha.adicionar_mensagem("usuario" if i % 2 == 0 else "gaia", f"mensagem {i}")
checar(f"pilha nunca guarda mais que {MAXIMO_BUBBLES_VISIVEIS} bubbles", len(pilha._bubbles) == MAXIMO_BUBBLES_VISIVEIS)
checar("a mais NOVA sobrevive (mensagens antigas saem primeiro)", pilha._bubbles[-1].texto_completo == "mensagem 4")

pilha.mostrar_indicador_voz("ouvindo")
checar("indicador de voz é criado", pilha._indicador_voz is not None and pilha._indicador_voz.tipo == "ouvindo")
pilha.mostrar_indicador_voz("processando")
checar("mostrar de novo SUBSTITUI o indicador (nunca acumula 2)", pilha._indicador_voz.tipo == "processando")

pilha.adicionar_mensagem("gaia", "resposta chegou")
checar("uma mensagem nova encerra o indicador de voz sozinha", pilha._indicador_voz is None)
checar(
    "bubble que SUBSTITUI o indicador de voz entra sem deslizamento (só fade 'no lugar', doc: 'sem destruir um widget e fazer outro aparecer abruptamente')",
    pilha._bubbles[-1]._deslocamento_atual == 0,
)

pilha.adicionar_mensagem("usuario", "obrigada")
checar(
    "bubble normal (sem indicador antes) continua com o deslizamento padrão de entrada",
    pilha._bubbles[-1]._deslocamento_atual == bubble_module.DESLOCAMENTO_ENTRADA_PX,
)

expandidos = []
pilha.expandir_solicitado.connect(lambda texto: expandidos.append(texto))
pilha._bubbles[-1].expandir_solicitado.emit()
checar("BubbleStack repassa expandir_solicitado com o texto completo do bubble", expandidos == [pilha._bubbles[-1].texto_completo])

pilha.limpar(imediato=True)
checar("limpar(imediato=True) esvazia a pilha na hora", pilha.esta_vazia)

# espaçamento agrupado (polimento 2026-09-06, doc: "não deixar os bubbles
# parecerem linhas de uma tabela... criar pequenos grupos conversacionais")
# - `bombear` entre cada passo: posição só assenta no ALVO depois da
# animação de entrada/realocação (mesmo achado do log real, 2026-09-06).
regiao_acima_teste = positioning.regioes_candidatas(janela2)["acima"]
pilha.definir_layout("vertical", regiao_acima_teste, regiao_acima_teste.bottom() + 1)
pilha.adicionar_mensagem("usuario", "primeira")
bombear(0.3)
pilha.adicionar_mensagem("usuario", "segunda, mesmo autor")
bombear(0.3)
# empilhamento sobe (mais NOVO = y maior, mais perto de y_base) - gap = topo do mais novo - base do mais antigo
gap_mesmo_autor = pilha._bubbles[1].y() - (pilha._bubbles[0].y() + pilha._bubbles[0].height())
pilha.adicionar_mensagem("gaia", "troca de autor")
bombear(0.3)
gap_troca_autor = pilha._bubbles[-1].y() - (pilha._bubbles[-2].y() + pilha._bubbles[-2].height())
checar(
    "mesmo autor consecutivo fica mais PERTO (grupo conversacional) que uma troca de autor",
    gap_mesmo_autor < gap_troca_autor,
    (gap_mesmo_autor, gap_troca_autor),
)
pilha.limpar(imediato=True)

# ----------------------------------------------------------------------
# Modo histórico (2026-09-07, correção do usuário: "vc entendeu errado...
# quero remover essa tela separada de histórico... qnd eu clicar em
# histórico elas tem de ficar visiveis e permanentes, permitindo voltar
# com scroll. E tem de ter um limite de altura tbm") - MESMOS bubbles
# flutuantes, nunca um painel/janela nova. `pilha_hist` NOVA (não reusa
# `pilha`) - `_historico_dados` acumula por instância, um `BubbleStack`
# fresco dá contagens previsíveis pra testar.
pilha_hist = BubbleStack(janela2)
pilha_hist.definir_layout("vertical", regiao_acima_teste, regiao_acima_teste.bottom() + 1)
TOTAL_MENSAGENS_TESTE_HISTORICO = 12  # o bastante pra empilhar mais alto que ALTURA_MAXIMA_HISTORICO e o scroll ter efeito de verdade pra testar
for indice in range(TOTAL_MENSAGENS_TESTE_HISTORICO):
    pilha_hist.adicionar_mensagem("usuario" if indice % 2 == 0 else "gaia", f"histórico {indice}")
    bombear(0.05)
checar(
    f"pilha normal continua limitada a {MAXIMO_BUBBLES_VISIVEIS} mesmo com modo histórico desligado",
    len(pilha_hist._bubbles) == MAXIMO_BUBBLES_VISIVEIS,
)
checar(
    "TODAS as mensagens ficam guardadas em _historico_dados, mesmo as que já saíram da pilha normal",
    len(pilha_hist._historico_dados) == TOTAL_MENSAGENS_TESTE_HISTORICO,
)
checar("modo histórico começa DESLIGADO", not pilha_hist.historico_ativo)

pilha_hist.alternar_historico()
checar("alternar_historico() LIGA o modo", pilha_hist.historico_ativo)
checar(
    "TODAS as mensagens viram bubbles no modo histórico (não só as últimas 3)",
    len(pilha_hist._bubbles_historico) == TOTAL_MENSAGENS_TESTE_HISTORICO,
)
checar(
    "a pilha normal (no máximo 3) fica ESCONDIDA enquanto o histórico está aberto (nunca os dois ao mesmo tempo)",
    all(bubble.isHidden() for bubble in pilha_hist._bubbles),
)

pilha_hist.adicionar_mensagem("gaia", "chegou com o histórico já aberto")
checar(
    "mensagem nova enquanto o histórico está aberto também aparece nele (ao vivo, sem precisar reabrir)",
    len(pilha_hist._bubbles_historico) == TOTAL_MENSAGENS_TESTE_HISTORICO + 1
    and pilha_hist._bubbles_historico[-1].texto_completo == "chegou com o histórico já aberto",
)

offset_antes = pilha_hist._offset_scroll_historico
pilha_hist._ao_scroll_historico(240)  # positivo = rodinha "pra cima" (ver mensagens mais antigas)
checar("rolar a rodinha PRA CIMA aumenta o offset (revela mensagens mais antigas)", pilha_hist._offset_scroll_historico > offset_antes)
pilha_hist._ao_scroll_historico(-999_999)  # bem negativo - deve CLAMPAR em 0, nunca ficar negativo
checar("offset de rolagem nunca fica negativo (clampado em 0)", pilha_hist._offset_scroll_historico == 0)
pilha_hist._ao_scroll_historico(999_999)  # bem positivo - deve clampar no máximo (nunca revelar espaço vazio acima da mensagem mais antiga)
checar(
    "offset de rolagem nunca passa do máximo (nunca rola além da mensagem mais antiga)",
    pilha_hist._offset_scroll_historico == pilha_hist._offset_maximo_scroll_historico,
)

pilha_hist.alternar_historico()
checar("alternar_historico() de novo DESLIGA o modo", not pilha_hist.historico_ativo)
checar("bubbles do modo histórico são descartados ao desligar", pilha_hist._bubbles_historico == [])
bombear(0.3)
checar(
    "a pilha normal REAPARECE (no máximo 3, com o conteúdo atualizado - a mensagem 'chegou com o histórico...' entrou por baixo dos panos)",
    len(pilha_hist._bubbles) == MAXIMO_BUBBLES_VISIVEIS and not pilha_hist._bubbles[-1].isHidden()
    and pilha_hist._bubbles[-1].texto_completo == "chegou com o histórico já aberto",
)

pilha_hist.limpar(imediato=True)
checar(
    "_historico_dados sobrevive a limpar() (2026-09-07: 'permanentes' - continua disponível se abrir a conversa de novo)",
    len(pilha_hist._historico_dados) == TOTAL_MENSAGENS_TESTE_HISTORICO + 1,
)

controller2.parar()

# ----------------------------------------------------------------------
# ConversationController - máquina de estados + bloqueio de autonomia
repositorio3 = AssetRepository()
controller3 = AnimationController(repositorio=repositorio3)
janela3 = MascotWindow(controller3)
janela3.move(area_x + area_w // 2 - janela3.width() // 2, area_y + area_h // 2)

safety = SafetyController()
safety._pausar_por_plataforma = False
safety._recalcular()

conversa = ConversationController(janela3, safety)
checar("estado inicial é 'idle'", conversa.estado == "idle" and not conversa.esta_ativo)
checar("autonomia permitida antes de entrar na conversa", safety.autonomia_permitida is True)

conversa.entrar()
checar("entrar() muda pra 'ativo' e mostra o InputBar", conversa.estado == "ativo" and conversa._input.isVisible())
checar("entrar() bloqueia autonomia", safety.autonomia_permitida is False)

conversa.alternar()
checar("alternar() em 'ativo' FECHA a conversa (volta pra idle)", conversa.estado == "idle")
checar("sair() libera autonomia", safety.autonomia_permitida is True)

conversa.notificar_estado_semantico("listening")
checar("'listening' ATIVA a conversa sozinho (voz não precisa de 'Conversar' antes)", conversa.esta_ativo)
checar("'listening' vira o estado 'ouvindo'", conversa.estado == "ouvindo")
checar("'listening' NÃO rouba foco de teclado (focar=False)", not conversa._input.hasFocus())

conversa.alternar()
checar("alternar() durante 'ouvindo' NÃO fecha a conversa (só focaria o input)", conversa.esta_ativo and conversa.estado == "ouvindo")

conversa.notificar_estado_semantico("idle")
checar("estado semântico 'idle' encerra o indicador de voz e volta pra 'ativo'", conversa.estado == "ativo")

conversa._ao_enviar_texto({"texto": "oi Gala", "imagem_preview": None, "imagem_base64": None, "imagem_mime": None})
conversa.receber_resposta("oi! como posso ajudar?")
bombear(0.3)
checar("mensagem do usuário + resposta viram bubbles de verdade", len(conversa._bubbles._bubbles) == 2)

checar("histórico começa DESLIGADO", not conversa._bubbles.historico_ativo)
checar(
    "botão de histórico nasce com o estilo INATIVO (2026-09-07, pedido do usuário: "
    "'eu tenho q saber quando o botao de historico ta habilitado ou n')",
    conversa._input._botao_historico.styleSheet() == input_bar_module._ESTILO_BOTAO_HISTORICO_INATIVO,
)

conversa.abrir_historico_completo()
checar(
    "abrir_historico_completo LIGA o modo histórico do BubbleStack SEM fechar a conversa "
    "(2026-09-07, correção do usuário: 'quero remover essa tela separada de histórico')",
    conversa._bubbles.historico_ativo and conversa.estado == "ativo",
)
checar(
    "botão de histórico muda pro estilo ATIVO junto (cristal, nunca fica sem indicação visual)",
    conversa._input._botao_historico.styleSheet() == input_bar_module._ESTILO_BOTAO_HISTORICO_ATIVO,
)
conversa.abrir_historico_completo()
checar(
    "chamar de novo (ex.: 'Ver completo' de outro bubble) NÃO desliga - só garante aberto",
    conversa._bubbles.historico_ativo,
)

conversa._input.historico_solicitado.emit()
checar("botão dedicado de histórico do InputBar ALTERNA (estava ligado, desliga)", not conversa._bubbles.historico_ativo)
checar("estilo do botão volta pro INATIVO junto", conversa._input._botao_historico.styleSheet() == input_bar_module._ESTILO_BOTAO_HISTORICO_INATIVO)
conversa._input.historico_solicitado.emit()
checar("botão dedicado liga de novo", conversa._bubbles.historico_ativo)
conversa.alternar_historico()  # deixa desligado pro resto do teste (via ConversationController, sincroniza o botão também)
checar("sair()/alternar_historico desligando também sincroniza o botão", conversa._input._botao_historico.styleSheet() == input_bar_module._ESTILO_BOTAO_HISTORICO_INATIVO)

conversa.entrar()
conversa.fechar_imediato()
checar("fechar_imediato() (arraste real) sempre volta pra idle na hora", conversa.estado == "idle")
checar("fechar_imediato() libera autonomia também", safety.autonomia_permitida is True)

conversa.receber_resposta("essa resposta não deveria aparecer - conversa está idle")
checar("resposta fora de uma conversa ativa NÃO cria bubble", conversa._bubbles.esta_vazia)

# erro LOCAL de envio (2026-09-06, doc: "não quero uma QMessageBox") -
# bubble próprio, estilo de erro discreto, nunca uma janela de sistema.
conversa.entrar()
conversa.receber_erro("Sem conexão com a GAIA (modo demonstração).")
bombear(0.3)
checar(
    "receber_erro cria um bubble remetente='erro' (nunca QMessageBox)",
    len(conversa._bubbles._bubbles) == 1 and conversa._bubbles._bubbles[0].remetente == "erro",
)
checar(
    "bubble de erro tem avatar (glifo em círculo, ainda é 'ela' avisando), texto original preservado sem prefixo colado",
    conversa._bubbles._bubbles[0]._tem_avatar and conversa._bubbles._bubbles[0].texto_exibido == "Sem conexão com a GAIA (modo demonstração).",
)
conversa.fechar_imediato()

controller3.parar()

# ----------------------------------------------------------------------
# InputBar - reage a hover/foco de verdade (correção 2026-09-06: "ainda
# parece um campo Qt jogado na tela" - borda/glow eram ESTÁTICOS antes)
campo_teste = input_bar_module.InputBar()

# "retângulo interno" ao digitar (achado ao vivo, 2026-09-06, 2 rodadas
# até achar a causa certa: "n quero q fique esse retangulo interno qnd
# começo a digitar") - a causa REAL era a cor do glow nascer OPACA
# (`QColor(hex)` sem alpha = 255); com blur > 0 (hover/foco), uma sombra
# opaca desenha uma cópia sólida da silhueta colada na borda, parecendo
# um contorno extra. `outline: none` (1ª tentativa) fica como defesa
# extra, mas o teste que garante a correção de verdade é o de baixo.
checar(
    "QPlainTextEdit tem 'outline: none' (defesa extra, não era a causa real)",
    "outline: none" in campo_teste._campo.styleSheet(),
)
checar(
    "glow NUNCA nasce opaco (causa real do retângulo - sombra opaca = contorno sólido extra, não glow)",
    campo_teste._cor_glow.alphaF() < 1.0,
)
checar(
    "InputBar NÃO usa QGraphicsEffect nenhum (achado 2026-09-06: efeito gráfico + janela top-level translúcida deixava os bubbles invisíveis no Windows - glow agora é pintado à mão, mesma técnica de halo.py)",
    campo_teste.graphicsEffect() is None,
)
checar("botão de histórico existe e tem tooltip explicando a ação", campo_teste._botao_historico.toolTip() != "")

alpha_repouso = campo_teste._cor_borda.alphaF()
def _perto(valor_a, valor_b, tolerancia=0.01) -> bool:
    """`QColor.alphaF()` quantiza pra 8 bits internamente (`setAlphaF(0.35)`
    devolve ~0.34999..., não 0.35 exato) - comparar direto contra a
    CONSTANTE Python quebraria por imprecisão de ponto flutuante, não por
    bug de verdade."""
    return abs(valor_a - valor_b) < tolerancia


checar("InputBar nasce em REPOUSO (borda discreta, sem glow)", _perto(alpha_repouso, input_bar_module._BORDA_REPOUSO[0]))

campo_teste.enterEvent(None)
checar("hover aumenta a borda (mais destaque que repouso)", _perto(campo_teste._cor_borda.alphaF(), input_bar_module._BORDA_HOVER[0]))
campo_teste.leaveEvent(None)
checar("tirar o mouse volta pro repouso", _perto(campo_teste._cor_borda.alphaF(), alpha_repouso))

from PySide6.QtCore import QEvent as _QEvent  # noqa: E402

campo_teste.eventFilter(campo_teste._campo, _QEvent(_QEvent.Type.FocusIn))
checar(
    "foco de verdade no QPlainTextEdit ativa o glow LEVE (doc: 'glow leve quando estiver focado')",
    _perto(campo_teste._cor_borda.alphaF(), input_bar_module._BORDA_FOCADO[0]) and campo_teste._intensidade_glow == input_bar_module._BORDA_FOCADO[1],
)
campo_teste.eventFilter(campo_teste._campo, _QEvent(_QEvent.Type.FocusOut))
checar("perder o foco volta pro repouso (glow desliga)", _perto(campo_teste._cor_borda.alphaF(), alpha_repouso) and campo_teste._intensidade_glow == 0.0)

# ----------------------------------------------------------------------
# InputBar - revisão 2026-09-07 (referência visual do usuário): largura
# igual ao bubble da GAIA, campo multi-linha que cresce, anexo de imagem
# (Ctrl+V/botão), seletor de emoji.
checar(
    "composer tem a MESMA largura do bubble da GAIA (pedido do usuário: 'do tamanho da fala da gaia')",
    input_bar_module.LARGURA_PADRAO == bubble_module.LARGURA_PADRAO,
)

altura_1_linha = campo_teste.height()
# "oi" (não uma frase mais longa) de propósito - o ambiente offscreen
# deste sandbox usa um fallback de fonte mais largo que a Segoe UI real
# (achado documentado em memória/sessões anteriores), então uma frase
# comum pode quebrar linha AQUI sem quebrar no Windows de verdade; "oi"
# fica curto o bastante pra nunca quebrar nem com esse fallback.
campo_teste._campo.setPlainText("oi")
checar("1 linha curta NÃO faz o composer crescer", campo_teste.height() == altura_1_linha)

texto_varias_linhas = "linha bem comprida que decerto quebra sozinha. " * 6
campo_teste._campo.setPlainText(texto_varias_linhas)
checar("texto que quebra em várias linhas faz o composer CRESCER em altura", campo_teste.height() > altura_1_linha)
checar("composer nunca cresce além de ALTURA_MAXIMA (reservada em `escolher_layout_conversa`)", campo_teste.height() <= input_bar_module.ALTURA_MAXIMA)
checar("composer cresce SEM MUDAR de largura (só altura)", campo_teste.width() == input_bar_module.LARGURA_PADRAO)
campo_teste._campo.setPlainText("")
checar("apagar o texto volta o composer pra altura de repouso", campo_teste.height() == altura_1_linha)

from PySide6.QtGui import QKeyEvent as _QKeyEvent  # noqa: E402

payloads_enviados = []
campo_teste.enviar_solicitado.connect(lambda payload: payloads_enviados.append(payload))
campo_teste._campo.setPlainText("mensagem de teste")
evento_enter = _QKeyEvent(_QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
campo_teste.eventFilter(campo_teste._campo, evento_enter)
checar("Enter sem Shift dispara o envio (payload com o texto certo)", payloads_enviados and payloads_enviados[-1]["texto"] == "mensagem de teste")

campo_teste._campo.setPlainText("linha 1")
evento_shift_enter = _QKeyEvent(_QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
consumido = campo_teste.eventFilter(campo_teste._campo, evento_shift_enter)
checar("Shift+Enter NÃO é consumido pelo filtro (deixa o QPlainTextEdit inserir a quebra de linha)", not consumido)

# anexo de imagem - Ctrl+V (clipboard) e botão 📎 (arquivo) convergem no
# MESMO `_definir_anexo`, nunca duplicado.
from PySide6.QtGui import QImage as _QImage  # noqa: E402
from PySide6.QtWidgets import QWidget as _QWidget  # noqa: E402

imagem_teste = _QImage(64, 64, _QImage.Format.Format_RGB32)
imagem_teste.fill(0xFF3366CC)
campo_teste._definir_anexo(imagem_teste)
# `isHidden()` (nunca `isVisible()`) - `campo_teste` não está numa janela
# de verdade mostrada na tela (`.show()` nunca foi chamado neste teste),
# `isVisible()` sempre devolveria False pra QUALQUER filho independente
# do próprio `setVisible` - `isHidden()` reflete só a flag explícita.
checar("anexar uma imagem mostra a linha de miniatura", not campo_teste._linha_anexo.isHidden())
checar("anexar uma imagem faz o composer crescer (reserva a linha de anexo)", campo_teste.height() > altura_1_linha)
anexo_preparado = campo_teste._preparar_imagem_para_envio()
checar(
    "imagem anexada vira JPEG base64 pronto pro protocolo (mesmo padrão de capturar_tela_b64)",
    anexo_preparado is not None and anexo_preparado[1] == "image/jpeg" and len(anexo_preparado[0]) > 0,
)
campo_teste._remover_anexo()
checar("remover o anexo esconde a linha de miniatura e volta a altura de repouso", campo_teste._linha_anexo.isHidden() and campo_teste.height() == altura_1_linha)
checar("sem anexo, _preparar_imagem_para_envio devolve None", campo_teste._preparar_imagem_para_envio() is None)

# enviar com imagem anexada - payload carrega texto + imagem (preview pro
# bubble, base64 pronto pro protocolo).
payloads_enviados.clear()
campo_teste._definir_anexo(imagem_teste)
campo_teste._campo.setPlainText("olha essa imagem")
campo_teste._ao_enviar()
checar(
    "enviar com imagem anexada manda texto + imagem_base64 no MESMO payload",
    payloads_enviados[-1]["texto"] == "olha essa imagem" and payloads_enviados[-1]["imagem_base64"] is not None
    and payloads_enviados[-1]["imagem_preview"] is not None,
)
checar("enviar limpa o anexo (não fica preso pra próxima mensagem)", campo_teste._linha_anexo.isHidden())

# emoji - insere na posição do cursor do campo, nunca precisa de QMenu nativo.
campo_teste._campo.setPlainText("")
campo_teste._inserir_emoji("🔥", _QWidget())
checar("inserir emoji escreve o glifo no campo", campo_teste._campo.toPlainText() == "🔥")

campo_teste.deleteLater()

# ----------------------------------------------------------------------
# Fluxo COMPLETO ponta a ponta (o "critério de pronto" do pedido, contra
# o MascotApp real - bridge fake só pra CAPTURAR o que sai de verdade,
# nunca mockar o ConversationController em si) - Conversar -> digitar ->
# Enter -> bubble do usuário -> indicador de espera (reaproveitando
# state_changed:"thinking" que `turno.py` já manda pra QUALQUER turno,
# voz ou texto - confirmado lendo `assistant/run.py`/`core/agent/turno.py`,
# nenhum protocolo novo) -> resposta real vira bubble da GAIA -> nova
# mensagem empurra as antigas pra cima com opacidade menor.
from core import mascot_events as mascot_events_module  # noqa: E402
from mascot import process_main as process_main_module  # noqa: E402


class _BridgeFake:
    def __init__(self):
        self.enviados = []

    def enviar(self, mensagem):
        self.enviados.append(mensagem)


mascot_app = process_main_module.MascotApp()
bridge_fake = _BridgeFake()
mascot_app.bridge = bridge_fake

mascot_app.conversation.alternar()  # mesmo caminho do clique direto/"Conversar"
checar("critério de pronto (1/7): clico 'Conversar' -> composer aparece", mascot_app.conversation._input.isVisible())

mascot_app.conversation._input._campo.setPlainText("oi")
mascot_app.conversation._input._ao_enviar()
bombear(0.3)
checar("critério de pronto (2/7): 'oi' vira bubble do USUÁRIO", any(b.remetente == "usuario" and b.texto_completo == "oi" for b in mascot_app.conversation._bubbles._bubbles))
checar("critério de pronto (2b): campo some da tela, texto some (nunca duplica no campo E no bubble)", mascot_app.conversation._input._campo.toPlainText() == "")
checar("chat_submitted REAL saiu pro bridge (nunca mock local)", any(m.get("type") == "chat_submitted" and m.get("text") == "oi" for m in bridge_fake.enviados))

mascot_app._processar_evento_gaia(mascot_events_module.evento_state_changed("thinking"))
bombear(0.1)
checar("critério de pronto (3/7): aparece o indicador de 'processando' (reaproveita o MESMO state_changed de sempre)", mascot_app.conversation.estado == "processando")

mascot_app._processar_evento_gaia(mascot_events_module.evento_assistant_message("id-e2e", "Você tem 3 eventos hoje.", "neutro", True))
bombear(0.3)
checar("critério de pronto (4/7): indicador some sozinho quando a resposta chega", mascot_app.conversation._bubbles._indicador_voz is None)
checar("critério de pronto (4b): GAIA responde em TEXTO em outro bubble", any(b.remetente == "gaia" and b.texto_completo == "Você tem 3 eventos hoje." for b in mascot_app.conversation._bubbles._bubbles))

mascot_app.conversation._input._campo.setPlainText("obrigada")
mascot_app.conversation._input._ao_enviar()
bombear(0.3)
checar("critério de pronto (5/7): posso digitar outra mensagem, ela sobe pra pilha", any(b.remetente == "usuario" and b.texto_completo == "obrigada" for b in mascot_app.conversation._bubbles._bubbles))

_bubbles_finais = mascot_app.conversation._bubbles._bubbles
_ys = [b.y() for b in _bubbles_finais]
checar(
    "critério de pronto (6/7): a resposta anterior sobe JUNTO (ordem da pilha por y crescente = mais nova mais perto da GAIA)",
    _ys == sorted(_ys) and _bubbles_finais[-1].texto_completo == "obrigada",
    _ys,
)
checar(
    "critério de pronto (7/7): mensagens antigas perdem destaque (opacidade decrescente, não é 'tudo empilhado igual')",
    _bubbles_finais[0]._opacidade_repouso < _bubbles_finais[-1]._opacidade_repouso,
)

mascot_app.conversation.fechar_imediato()
mascot_app.controller.parar()

print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
