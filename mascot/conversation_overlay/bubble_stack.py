# -*- coding: utf-8 -*-
"""`BubbleStack` (Project LOKI, Conversation Overlay, 2026-09-06) - guarda
as ÚLTIMAS 2-3 mensagens (doc, seção 5: "não deixar o histórico inteiro
acumulando no desktop"), empilhadas ao longo do eixo escolhido por
`ConversationController` (`definir_layout`, ver `positioning.
escolher_layout_conversa`) - mais nova mais perto da GAIA/composer, as
antigas sobem, perdem destaque (opacidade de repouso menor, doc seção 7:
"[resposta anterior] ← mais transparente") e saem com fade quando
estouram `MAXIMO_BUBBLES_VISIVEIS`. Depois de um período de inatividade,
tudo some sozinho.

Cada `Bubble`/`IndicadorVoz` é sua PRÓPRIA janela top-level (ver docstring
de `bubble.py`) - este objeto só orquestra QUANTOS existem e ONDE ficam
(`positioning.py`), nunca é dono de nenhuma superfície própria.

**Modo histórico (2026-09-07)** - reversão de um design anterior no mesmo
dia (uma janela `CompanionPanel` separada como destino de "Ver completo";
o usuário corrigiu: "vc entendeu errado... quero remover essa tela
separada de histórico... qnd eu clicar em histórico elas [as mensagens]
tem de ficar visiveis e permanentes, permitindo voltar com scroll"). Não
existe painel/janela nova nenhuma - `self._historico_dados` guarda
`(remetente, texto, imagem)` de TODA mensagem desde que este `BubbleStack`
foi criado (nunca trimado, sobrevive a `limpar()`/timeout de
inatividade - só é descartado se o `BubbleStack` inteiro for destruído).
`alternar_historico()` LIGA/DESLIGA: ligado, reconstrói um `Bubble` NOVO
(`sem_truncamento=True` - mostra o texto INTEIRO, nunca "Ver completo"
de novo) pra cada entrada, esconde a pilha normal de ≤3 e empilha TODOS
eles (mesmos bubbles FLUTUANTES de sempre, só que muitos) numa "janela"
virtual de altura limitada (`ALTURA_MAXIMA_HISTORICO`) - rolar a rodinha
do mouse sobre qualquer um deles (`Bubble.scroll_solicitado`) desloca
essa janela pra cima/baixo pela pilha inteira. Timeout de inatividade
fica suspenso enquanto o histórico está aberto (as mensagens não são
"apagadas" nesse modo, de propósito)."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer, Signal

from mascot.conversation_overlay import positioning
from mascot.conversation_overlay.bubble import LARGURA_PADRAO, Bubble, IndicadorVoz

logger = logging.getLogger(__name__)

MAXIMO_BUBBLES_VISIVEIS = 3
# Espaçamento (polimento 2026-09-06, doc: "não deixar os bubbles
# parecerem linhas de uma tabela... criar pequenos grupos
# conversacionais") - MESMO autor consecutivo fica mais perto (grupo);
# trocar de autor (usuário<->GAIA) abre mais espaço. Reaproveitado
# também pelo empilhamento virtual do modo histórico (2026-09-07).
GAP_MESMO_AUTOR = 5
GAP_TROCA_AUTOR = 10
TIMEOUT_INATIVIDADE_MS = 15_000  # 2026-09-06: usuário pediu 10s, testou e voltou atrás ("15s tava bom") - mantido em 15s
# opacidade de REPOUSO por distância do item mais novo (índice 0 = mais
# perto da GAIA) - doc, seção 7: "antigas perdem destaque, fazem fade".
# Além do fim da lista, tudo usa o último valor (piso).
OPACIDADES_REPOUSO = (1.0, 0.75, 0.55)
# Teto de altura do modo histórico (2026-09-07, pedido do usuário: "tem
# de ter um limite de altura tbm") - clampado contra a altura REAL da
# região disponível em `_reposicionar_historico` (nunca ultrapassa o que
# `positioning.py` já reservou, mesmo numa tela pequena/GAIA perto da
# borda) - `positioning.py` continua INTOCADO, isto só decide até onde
# a pilha virtual pode desenhar DENTRO da região que ele já calculou.
ALTURA_MAXIMA_HISTORICO = 500
# Sensibilidade da rolagem - `QWheelEvent.angleDelta().y()` chega
# tipicamente em múltiplos de ±120 por "clique" da rodinha; dividir
# reduz isso a um deslocamento em pixels razoável (1 clique ~ 30px).
DIVISOR_SCROLL = 4


def _opacidade_para_indice(indice: int) -> float:
    if indice < len(OPACIDADES_REPOUSO):
        return OPACIDADES_REPOUSO[indice]
    return OPACIDADES_REPOUSO[-1]


def _x_alinhado(coluna_x: int, largura_coluna: int, item) -> int:
    """Posição x do ITEM dentro do envelope de largura `largura_coluna`
    (que já está ancorado corretamente pelo `eixo_perpendicular` de
    sempre) - `item.alinhamento` ("esquerda"/"direita"/"centro", ver
    `bubble.py`) decide ONDE dentro dele. Nunca sai do envelope (a
    largura do item já é <= `largura_coluna`, garantido por `bubble.py`),
    então nunca invade o `character_safe_rect` que o envelope já respeita."""
    alinhamento = getattr(item, "alinhamento", "centro")
    if alinhamento == "esquerda":
        return coluna_x
    if alinhamento == "direita":
        return coluna_x + (largura_coluna - item.width())
    return coluna_x + (largura_coluna - item.width()) // 2


class BubbleStack(QObject):
    expandir_solicitado = Signal(str)  # texto COMPLETO do bubble que estourou o limite

    def __init__(self, mascot_window, parent=None):
        super().__init__(parent)
        self._mascot_window = mascot_window
        self._bubbles: list[Bubble] = []
        self._indicador_voz: IndicadorVoz | None = None
        # `definir_layout` ainda não foi chamado (ex.: uso direto sem
        # `ConversationController`, testes) - `_regiao_efetiva` calcula um
        # fallback razoável (região "acima" atual) sob demanda.
        self._eixo = "vertical"
        self._regiao = None
        self._y_base = None

        self._timer_inatividade = QTimer(self)
        self._timer_inatividade.setSingleShot(True)
        self._timer_inatividade.timeout.connect(self.esconder_por_inatividade)

        # Modo histórico (2026-09-07, ver docstring do módulo) -
        # `_historico_dados` NUNCA é trimado (sobrevive a `limpar()`/
        # timeout), `_bubbles_historico` são bubbles FLUTUANTES novos
        # (`sem_truncamento=True`) construídos só quando o modo está
        # ligado, descartados ao desligar (mais barato que manter
        # centenas de janelas top-level vivas o tempo todo).
        self._historico_dados: list[tuple[str, str, object]] = []
        self._historico_ativo = False
        self._bubbles_historico: list[Bubble] = []
        self._offset_scroll_historico = 0
        self._offset_maximo_scroll_historico = 0

    @property
    def esta_vazia(self) -> bool:
        return not self._bubbles and self._indicador_voz is None

    @property
    def historico_ativo(self) -> bool:
        """Público (2026-09-07) - `ConversationController.
        abrir_historico_completo` ("Ver completo" de um bubble truncado)
        usa isto pra só LIGAR o modo (nunca desligar de volta, diferente
        do botão dedicado de histórico que alterna)."""
        return self._historico_ativo

    def definir_layout(self, eixo: str, regiao, y_base: int) -> None:
        """`ConversationController` chama isto UMA VEZ por sessão de
        conversa (`positioning.escolher_layout_conversa`) - eixo/região/
        base ficam FIXOS durante a conversa inteira (evita o layout
        pular de lado no meio de uma troca de mensagens, mesmo se um
        bubble específico crescer bastante)."""
        self._eixo = eixo
        self._regiao = regiao
        self._y_base = y_base
        logger.info("definir_layout: eixo=%s regiao=%s y_base=%d", eixo, regiao.getRect() if regiao is not None else None, y_base)
        if not self.esta_vazia:
            self._reposicionar()

    def _regiao_efetiva(self):
        if self._regiao is not None:
            return self._regiao, self._y_base
        regiao = positioning.regioes_candidatas(self._mascot_window)["acima"]
        return regiao, regiao.bottom() + 1

    def adicionar_mensagem(self, remetente: str, texto: str, imagem=None) -> None:
        # "morph" do indicador de voz pra resposta de verdade (polimento
        # 2026-09-06, doc: "sem destruir um widget e fazer outro aparecer
        # abruptamente") - se HAVIA um indicador ativo, o novo bubble entra
        # SEM o deslizamento padrão (só fade "no lugar"), ver `Bubble.
        # entrar`/`_reposicionar` abaixo. `imagem` (2026-09-07, Ctrl+V/anexo
        # no composer) - `QPixmap` opcional, ver `bubble.Bubble`.
        self._historico_dados.append((remetente, texto, imagem))  # 2026-09-07 - NUNCA trimado, ver docstring do módulo

        veio_de_indicador = self._indicador_voz is not None
        self._encerrar_indicador_voz()
        bubble = Bubble(remetente, texto, imagem=imagem)
        bubble.expandir_solicitado.connect(lambda: self.expandir_solicitado.emit(bubble.texto_completo))
        self._bubbles.append(bubble)
        if len(self._bubbles) > MAXIMO_BUBBLES_VISIVEIS:
            mais_antiga = self._bubbles.pop(0)
            mais_antiga.concluiu_saida.connect(self._ao_bubble_removida)
            mais_antiga.sair()
        logger.info("bubble '%s' criado (%d bubbles na pilha depois)", remetente, len(self._bubbles))

        if self._historico_ativo:
            # A pilha normal (acima) continua sendo atualizada por baixo
            # dos panos, mas ESCONDIDA - só a view de histórico aparece de
            # verdade enquanto esse modo estiver ligado (nunca os dois ao
            # mesmo tempo, doc do módulo: "quero remover essa tela
            # separada... só faz as bubble ficar visível").
            self._adicionar_bubble_historico(remetente, texto, imagem)
        else:
            self._reposicionar(deslizar_novo=not veio_de_indicador)
            self._reiniciar_timeout_inatividade()

    # ------------------------------------------------------------------
    # Modo histórico (2026-09-07, ver docstring do módulo)
    def alternar_historico(self) -> None:
        """Botão dedicado de histórico (`InputBar`) - LIGA/DESLIGA."""
        if self._historico_ativo:
            self._fechar_historico()
        else:
            self._abrir_historico()

    def _abrir_historico(self) -> None:
        self._historico_ativo = True
        self._offset_scroll_historico = 0
        self._timer_inatividade.stop()  # "permanentes" enquanto o histórico estiver aberto - nunca some por inatividade nesse modo
        for bubble in self._bubbles:
            bubble.hide()
        if self._indicador_voz is not None:
            self._indicador_voz.hide()
        self._bubbles_historico = []
        for remetente, texto, imagem in self._historico_dados:
            bubble = Bubble(remetente, texto, imagem=imagem, sem_truncamento=True)
            bubble.scroll_solicitado.connect(self._ao_scroll_historico)
            self._bubbles_historico.append(bubble)
        self._reposicionar_historico()
        logger.info("modo histórico LIGADO (%d mensagem(ns))", len(self._bubbles_historico))

    def _fechar_historico(self) -> None:
        self._historico_ativo = False
        for bubble in self._bubbles_historico:
            bubble.hide()
            bubble.deleteLater()
        self._bubbles_historico = []
        # `_reposicionar` normal reexibe (`entrar()`, já que estavam
        # escondidos) a pilha de ≤3 com o conteúdo ATUAL - pode ter mudado
        # enquanto o histórico estava aberto (mensagens novas continuaram
        # chegando por baixo dos panos, ver `adicionar_mensagem`).
        if not self.esta_vazia:
            self._reposicionar()
            self._reiniciar_timeout_inatividade()
        logger.info("modo histórico DESLIGADO")

    def _adicionar_bubble_historico(self, remetente: str, texto: str, imagem) -> None:
        bubble = Bubble(remetente, texto, imagem=imagem, sem_truncamento=True)
        bubble.scroll_solicitado.connect(self._ao_scroll_historico)
        self._bubbles_historico.append(bubble)
        self._offset_scroll_historico = 0  # mensagem nova - pula pro FIM (mais recente), mesmo comportamento de qualquer chat
        self._reposicionar_historico()

    def _reposicionar_historico(self) -> None:
        """Empilha TODOS os bubbles do histórico (não só os últimos 3) numa
        janela VIRTUAL de altura limitada (`ALTURA_MAXIMA_HISTORICO`,
        clampada contra a altura REAL da região - nunca ultrapassa o que
        `positioning.py` já reservou) - MESMO `y_base`/`eixo`/coluna_x de
        sempre, só que a pilha inteira pode ser mais alta que essa janela;
        `self._offset_scroll_historico` (ajustado por `Bubble.
        scroll_solicitado`, ver `_ao_scroll_historico`) decide QUAL fatia
        da pilha cai dentro dela - bubbles fora ficam escondidos
        (`.hide()`), nunca destruídos (voltam a aparecer se rolar de
        volta)."""
        if not self._bubbles_historico:
            return
        regiao, y_base = self._regiao_efetiva()
        coluna_x = positioning.eixo_perpendicular(self._eixo, regiao, self._mascot_window, LARGURA_PADRAO)
        altura_janela = min(ALTURA_MAXIMA_HISTORICO, regiao.height())

        # Posição VIRTUAL de cada bubble (0 = colado em y_base, mais
        # negativo = mais pra cima/mais antigo) - MESMO empilhamento/gaps
        # de `_reposicionar`, só que sem o corte de MAXIMO_BUBBLES_VISIVEIS.
        posicoes = []
        y_cursor = 0
        remetente_anterior = None
        for indice, bubble in enumerate(reversed(self._bubbles_historico)):
            rotulo = bubble.remetente
            if indice > 0:
                mesmo_autor = remetente_anterior is not None and rotulo == remetente_anterior
                y_cursor -= GAP_MESMO_AUTOR if mesmo_autor else GAP_TROCA_AUTOR
            y_cursor -= bubble.height()
            posicoes.append((bubble, y_cursor))
            remetente_anterior = rotulo

        altura_pilha_inteira = -min(y for _, y in posicoes)
        self._offset_maximo_scroll_historico = max(0, altura_pilha_inteira - altura_janela)
        self._offset_scroll_historico = max(0, min(self._offset_scroll_historico, self._offset_maximo_scroll_historico))

        limite_topo = y_base - altura_janela
        for bubble, y_virtual in posicoes:
            y_absoluto = y_base + y_virtual + self._offset_scroll_historico
            x = _x_alinhado(coluna_x, LARGURA_PADRAO, bubble)
            visivel = (y_absoluto + bubble.height() > limite_topo) and (y_absoluto < y_base)
            if visivel:
                bubble.move(x, y_absoluto)
                if not bubble.isVisible():
                    bubble.show()
                    bubble.raise_()
            else:
                bubble.hide()

    def _ao_scroll_historico(self, delta: int) -> None:
        """`delta`: `QWheelEvent.angleDelta().y()` bruto (ver `bubble.
        _BolhaBase.wheelEvent`) - positivo (rodinha "pra cima", gesto
        convencional de qualquer chat) revela mensagens MAIS ANTIGAS."""
        if not self._historico_ativo:
            return
        self._offset_scroll_historico += delta // DIVISOR_SCROLL
        self._offset_scroll_historico = max(0, min(self._offset_scroll_historico, self._offset_maximo_scroll_historico))
        self._reposicionar_historico()

    def mostrar_indicador_voz(self, tipo: str) -> None:
        """`tipo`: `"ouvindo"` ou `"processando"` - SUBSTITUI o indicador
        anterior se já houver um (só 1 por vez, nunca acumula com os
        bubbles de mensagem normais)."""
        self._encerrar_indicador_voz()
        self._indicador_voz = IndicadorVoz(tipo)
        self._reposicionar()
        self._timer_inatividade.stop()  # indicador de voz nunca some sozinho por inatividade - some quando a resposta chegar

    def encerrar_indicador_voz(self) -> None:
        """Público (2026-09-06) - `ConversationController` chama quando o
        estado semântico sai de "listening"/"thinking"/"transcribing" SEM
        uma mensagem nova chegando junto (`adicionar_mensagem` já encerra
        sozinho como efeito colateral - ver lá)."""
        self._encerrar_indicador_voz()

    def _encerrar_indicador_voz(self) -> None:
        if self._indicador_voz is None:
            return
        indicador = self._indicador_voz
        self._indicador_voz = None
        indicador.concluiu_saida.connect(indicador.deleteLater)
        indicador.sair()

    def _ao_bubble_removida(self, bubble: Bubble) -> None:
        bubble.deleteLater()

    def _reposicionar(self, deslizar_novo: bool = True) -> None:
        """Empilha a partir de `y_base` (a borda mais perto da GAIA/
        composer, ver `definir_layout`) PRA CIMA: o item mais próximo
        dela (o indicador de voz, se houver, senão o bubble mais NOVO)
        fica no slot mais baixo, com opacidade de repouso PLENA; os
        demais sobem um a um e vão perdendo destaque
        (`_opacidade_para_indice`). `deslizar_novo=False` (polimento
        2026-09-06) - o item mais novo (índice 0) entra só com fade, sem
        o deslizamento padrão (usado quando ele está SUBSTITUINDO o
        indicador de voz, ver `adicionar_mensagem`).

        Cada item fica alinhado DENTRO do MESMO envelope de largura
        (`bubble.LARGURA_PADRAO`) conforme seu `alinhamento` ("esquerda"/
        "direita"/"centro", por `remetente` - doc: "usuário alinhado à
        direita... GAIA alinhada à esquerda") - a coluna INTEIRA continua
        ancorada pelo MESMO `eixo_perpendicular` de sempre (nunca
        recalcula region/monitor/DPI), só desloca cada item conforme sua
        PRÓPRIA largura dentro dela - `IndicadorVoz`/`Bubble` de tamanhos
        diferentes continuam nunca saindo do envelope."""
        itens = list(self._bubbles)
        if self._indicador_voz is not None:
            itens.append(self._indicador_voz)
        regiao, y_base = self._regiao_efetiva()
        coluna_x = positioning.eixo_perpendicular(self._eixo, regiao, self._mascot_window, LARGURA_PADRAO)
        y_cursor = y_base
        remetente_anterior = None
        for indice, item in enumerate(reversed(itens)):
            rotulo = getattr(item, "remetente", None) or getattr(item, "tipo", "?")
            if indice > 0:
                mesmo_autor = remetente_anterior is not None and rotulo == remetente_anterior
                y_cursor -= GAP_MESMO_AUTOR if mesmo_autor else GAP_TROCA_AUTOR
            y_cursor -= item.height()
            opacidade = _opacidade_para_indice(indice)
            x = _x_alinhado(coluna_x, LARGURA_PADRAO, item)
            # 🔥 Log do ALVO (x, y_cursor), não de `item.x()/.y()` depois -
            # pra itens já visíveis a posição só chega lá ao FIM da
            # animação de `mover_para` (achado ao vivo, 2026-09-06: logar
            # a posição atual bem aqui mostrava o valor PRÉ-animação,
            # confuso - parecia que o bubble mais novo nascia ACIMA do
            # mais antigo, quando na verdade só ainda não tinha assentado).
            logger.info(
                "_reposicionar: item '%s' (indice %d, opacidade_repouso=%.2f) alvo=(%d, %d) tamanho=%dx%d ja_visivel=%s",
                rotulo, indice, opacidade, x, y_cursor, item.width(), item.height(), item.isVisible(),
            )
            if item.isVisible():
                item.mover_para(y_cursor, opacidade_repouso=opacidade)
                item.move(x, item.y())
            else:
                item.entrar(x, y_cursor, opacidade_repouso=opacidade, deslizar=(deslizar_novo if indice == 0 else True))
            remetente_anterior = rotulo

    def _reiniciar_timeout_inatividade(self) -> None:
        self._timer_inatividade.start(TIMEOUT_INATIVIDADE_MS)

    def esconder_por_inatividade(self) -> None:
        self.limpar()

    def limpar(self, imediato: bool = False) -> None:
        """Some com TODOS os bubbles (fim da conversa, arraste real, ou
        timeout de inatividade) - `imediato=True` (arraste, `fechar_tudo`
        do overlay) pula o fade, mesmo corte de `menu_sao.py::fechar`.
        `_historico_dados` NUNCA é limpo aqui (2026-09-07, "permanentes"
        - sobrevive ao fim da conversa, pra continuar disponível se o
        usuário abrir a conversa de novo mais tarde); só os bubbles
        FLUTUANTES do modo histórico (se estiver aberto) são desfeitos,
        já que a conversa/composer que os hospedava está fechando."""
        if self._historico_ativo:
            self._historico_ativo = False
            for bubble in self._bubbles_historico:
                bubble.hide()
                bubble.deleteLater()
            self._bubbles_historico = []
        self._timer_inatividade.stop()
        for bubble in self._bubbles:
            if imediato:
                bubble.hide()
                bubble.deleteLater()
            else:
                bubble.concluiu_saida.connect(self._ao_bubble_removida)
                bubble.sair()
        self._bubbles = []
        if imediato:
            self._encerrar_indicador_voz_imediato()
        else:
            self._encerrar_indicador_voz()

    def _encerrar_indicador_voz_imediato(self) -> None:
        if self._indicador_voz is None:
            return
        self._indicador_voz.hide()
        self._indicador_voz.deleteLater()
        self._indicador_voz = None
