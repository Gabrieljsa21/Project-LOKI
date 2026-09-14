# -*- coding: utf-8 -*-
"""`ConversationController` (Project LOKI, Conversation Overlay,
2026-09-06) - ciclo de vida do "Bubble Mode": estados como STRINGS
simples (mesmo estilo de `menu_sao.py::_estado`, nunca `enum.Enum` - 1ª
vez introduzindo isso no projeto não parecia justificado só por isto).

```
idle <-> ativo <-> ouvindo/processando -> ativo (bubble da resposta chega)
  ^                                              |
  +---------------------- sair()/fechar_imediato()
```

`"expandido"` não é um estado PRÓPRIO deste controller - "histórico" é
uma VIEW do `BubbleStack`, nunca uma tela separada (2026-09-07, revisão:
"quero remover essa tela separada de histórico... só faz as bubble
ficar visível" - ver `alternar_historico`/`abrir_historico_completo`
abaixo e a docstring de `bubble_stack.py`). O `CompanionPanel` tradicional
não é mais o destino de "Ver completo"/histórico.

Reaproveita 100% de `platform_windows`/`positioning.py` pra posição -
`positioning.escolher_layout_conversa` (corrigido 2026-09-06: a v1
ancorava o `InputBar` em `GAIA.bottom + gap` sem NENHUMA zona de exclusão,
sentada na barra de tarefas a barra atravessava o corpo dela) decide o
lado da conversa INTEIRA (bubbles + composer sempre o MESMO sistema)
respeitando o `character_safe_rect` - ver docstring de `positioning.py`.
`SafetyController` (motivo `"conversation_overlay"`, mesmo padrão de
`"menu_sao"`/`"companion_panel"`) pro bloqueio de autonomia - o reset de
cooldown do Wander ao liberar já é genérico (`BehaviorScheduler` escuta
`SafetyController.autonomia_alterada`), nada novo precisa disso aqui."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from mascot.conversation_overlay import bubble as bubble_module
from mascot.conversation_overlay import positioning
from mascot.conversation_overlay.bubble_stack import GAP_TROCA_AUTOR, MAXIMO_BUBBLES_VISIVEIS, BubbleStack
from mascot.conversation_overlay.input_bar import ALTURA_MAXIMA, LARGURA_PADRAO, InputBar

logger = logging.getLogger(__name__)

MOTIVO_AUTONOMIA = "conversation_overlay"


def _altura_maxima_estimada_bubbles() -> int:
    """Estimativa de PIOR CASO (todos os `MAXIMO_BUBBLES_VISIVEIS` bubbles
    no tamanho máximo/truncado) - usada só pra DECIDIR o lado da conversa
    (`positioning.escolher_layout_conversa`) UMA VEZ, ao entrar; garante
    que o lado escolhido aguenta o pior caso e nunca precisa reavaliar
    (e possivelmente pular de lado) no meio de uma troca de mensagens.
    Usa `GAP_TROCA_AUTOR` (o maior dos 2 espaçamentos possíveis) - pior
    caso assume troca de autor a cada mensagem. O avatar (2026-09-07) fica
    FORA do balão e nunca deixa a altura de um bubble maior que
    `ALTURA_MAXIMA_TEXTO` no pior caso (mesma altura pra qualquer
    remetente agora - o avatar não some mais reserva vertical de dentro
    do balão)."""
    altura_bubble_maxima = (
        bubble_module.ALTURA_MAXIMA_TEXTO + 2 * bubble_module.PADDING_V + bubble_module.ALTURA_RODAPE
    )
    return MAXIMO_BUBBLES_VISIVEIS * altura_bubble_maxima + (MAXIMO_BUBBLES_VISIVEIS - 1) * GAP_TROCA_AUTOR

# estado semântico (core/mascot_events.py::ESTADOS_SEMANTICOS_VALIDOS) ->
# indicador de voz (doc, seção 8). "speaking"/"idle"/o resto não têm
# indicador - a resposta em si já chega via `receber_resposta` (bubble
# normal) ou nenhum efeito visual (mesmo corte que `state_controller.py`
# já faz pra estados sem clipe próprio).
_ESTADO_SEMANTICO_PARA_INDICADOR = {
    "listening": "ouvindo",
    "transcribing": "processando",
    "thinking": "processando",
}


class ConversationController(QObject):
    # `object` (dict `{"texto", "imagem_base64", "imagem_mime"}`, ver
    # `InputBar.enviar_solicitado`, 2026-09-07) - Mascot -> GAIA,
    # process_main.py encaminha pro envio real (bridge).
    texto_enviado = Signal(object)
    # Sinal (não chamada direta) pro hotkey global (`process_main.py::
    # _registrar_hotkey_companion_panel`) poder pedir `alternar()` com
    # segurança - o callback do `keyboard` roda numa thread PRÓPRIA da
    # lib, nunca na do Qt (mesmo motivo de `CompanionPanel.
    # alternar_visibilidade_solicitado`); `alternar()` mexe em QWidget
    # direto, então só pode ser chamado a partir da thread do Qt - emitir
    # este sinal marshalla automaticamente pra lá.
    alternar_solicitado = Signal()

    def __init__(self, mascot_window, safety, parent=None):
        super().__init__(parent)
        self._mascot_window = mascot_window
        self._safety = safety
        self._estado = "idle"
        self.alternar_solicitado.connect(self.alternar)

        self._input = InputBar()
        self._input.enviar_solicitado.connect(self._ao_enviar_texto)
        self._input.sair_solicitado.connect(self.sair)
        self._input.historico_solicitado.connect(self.alternar_historico)

        self._bubbles = BubbleStack(mascot_window, parent=self)
        self._bubbles.expandir_solicitado.connect(lambda _texto: self.abrir_historico_completo())

    @property
    def estado(self) -> str:
        return self._estado

    @property
    def esta_ativo(self) -> bool:
        return self._estado != "idle"

    # ------------------------------------------------------------------
    def alternar(self) -> None:
        """"Conversar" do Menu SAO / clique direto na GAIA (doc: os dois
        são redundantes de propósito, mesmo raciocínio que já valia pro
        `CompanionPanel`). Só FECHA se a conversa estiver num momento
        "parado" (`"ativo"`, sem voz rolando) - clicar durante `"ouvindo"`/
        `"processando"` nunca interrompe a voz no meio, só foca o input
        (doc, seção 10: "evitar que a GAIA simplesmente saia... no meio da
        conversa" vale pro overlay também, não só pro Wander)."""
        if self._estado == "ativo":
            self.sair()
        else:
            self.entrar()

    def entrar(self, focar: bool = True) -> None:
        if self.esta_ativo:
            if focar:
                self._input.focar()
            return
        self._estado = "ativo"
        if self._safety is not None:
            self._safety.bloquear_autonomia(MOTIVO_AUTONOMIA)
        # Layout COORDENADO (correção 2026-09-06: bubbles + composer NUNCA
        # em lados diferentes, e NUNCA sobre a própria GAIA) - decidido
        # UMA VEZ aqui e mantido fixo pela sessão inteira (ver docstring
        # de `_altura_maxima_estimada_bubbles`); `BubbleStack.
        # definir_layout` reaproveita a MESMA decisão pra cada bubble que
        # entrar depois.
        layout = positioning.escolher_layout_conversa(
            self._mascot_window,
            largura_bubbles=bubble_module.LARGURA_PADRAO, altura_bubbles=_altura_maxima_estimada_bubbles(),
            # `ALTURA_MAXIMA` (pior caso: texto de várias linhas + imagem
            # anexada), não a altura de REPOUSO - o composer cresce em
            # altura sozinho conforme o texto (2026-09-07, ver docstring
            # de `input_bar.py`), sempre pra BAIXO (canto superior
            # esquerdo fixo); reservar o pior caso aqui garante que esse
            # crescimento nunca invade o espaço dos bubbles, sem precisar
            # reavaliar `positioning.py` no meio da conversa.
            largura_composer=LARGURA_PADRAO, altura_composer=ALTURA_MAXIMA,
        )
        self._bubbles.definir_layout(layout["eixo"], layout["bubbles_regiao"], layout["bubbles_y_base"])
        x, y = layout["composer_pos"]
        tela = self._mascot_window.screen()
        logger.info(
            "entrar(): eixo=%s composer_pos=(%d, %d) | GAIA pos=(%d, %d) tamanho=%dx%d escala=%.2f | tela=%r geometria_tela=%s",
            layout["eixo"], x, y,
            self._mascot_window.x(), self._mascot_window.y(), self._mascot_window.width(), self._mascot_window.height(),
            self._mascot_window.escala,
            tela.name() if tela else None, tela.geometry().getRect() if tela else None,
        )
        self._input.entrar(x, y)
        if focar:
            self._input.focar()

    def sair(self) -> None:
        if not self.esta_ativo:
            return
        logger.info("sair() (estado anterior=%s)", self._estado)
        self._input.sair()
        self._bubbles.limpar()
        self._input.definir_historico_ativo(False)  # `limpar()` sempre desliga o modo histórico, mesmo se estivesse ligado
        self._estado = "idle"
        if self._safety is not None:
            self._safety.liberar_autonomia(MOTIVO_AUTONOMIA)

    def fechar_imediato(self) -> None:
        """Arraste real (`mascot_window.arraste_iniciado`, `process_main.py`)
        - some na hora, sem fade (mesmo corte de `menu_sao.py::
        fechar_tudo(imediato=True)`) - nunca deixa bubble/input "preso no
        ar" (doc, seção 10)."""
        if not self.esta_ativo:
            return
        logger.info("fechar_imediato() (estado anterior=%s)", self._estado)
        self._input.hide()
        self._bubbles.limpar(imediato=True)
        self._input.definir_historico_ativo(False)  # `limpar()` sempre desliga o modo histórico, mesmo se estivesse ligado
        self._estado = "idle"
        if self._safety is not None:
            self._safety.liberar_autonomia(MOTIVO_AUTONOMIA)

    # ------------------------------------------------------------------
    def _ao_enviar_texto(self, payload: dict) -> None:
        """`payload` vem de `InputBar.enviar_solicitado` (2026-09-07,
        Ctrl+V/anexo de imagem): `{"texto", "imagem_preview" (QPixmap|None,
        só pro bubble mostrar), "imagem_base64"/"imagem_mime" (já
        comprimidos, só pro envio de verdade)}`."""
        texto = payload["texto"]
        logger.info("usuário enviou %r (imagem_anexada=%s, estado=%s)", texto, payload["imagem_base64"] is not None, self._estado)
        self._bubbles.adicionar_mensagem("usuario", texto, imagem=payload["imagem_preview"])
        self.texto_enviado.emit(payload)

    def receber_resposta(self, texto: str) -> None:
        """`process_main.py` chama em CIMA de `assistant_message`, além do
        `companion_panel.receber_resposta` de sempre (histórico silencioso
        continua existindo lá) - só mostra bubble se a conversa estiver
        ATIVA; fora disso quem mostrou a resposta foi o próprio painel
        (se estivesse aberto) ou ninguém (turno de outro canal, ver
        `core/mascot_events.py::evento_user_message`: "Discord/visitantes
        não fazem a janela pessoal aparecer" - mesmo princípio vale aqui)."""
        if not self.esta_ativo:
            # 🔥 Diagnóstico (2026-09-06, achado ao vivo: usuário mandou
            # mensagem, resposta chegou de verdade no CompanionPanel, mas
            # NENHUM bubble apareceu) - se isto aparecer no log bem depois
            # de `_ao_enviar_texto`, a conversa foi fechada (`sair()`/
            # `fechar_imediato()`/arraste) ANTES da resposta chegar -
            # explica exatamente esse sintoma sem precisar adivinhar.
            logger.warning("resposta descartada da UI - conversa não está ativa (estado=%s): %r", self._estado, texto)
            return
        logger.info("resposta recebida (estado=%s): %r", self._estado, texto)
        self._bubbles.adicionar_mensagem("gaia", texto)

    def receber_erro(self, motivo: str) -> None:
        """`process_main.py` chama em CIMA de `companion_panel.
        falha_envio` (2026-09-06) - falha LOCAL de envio (bridge
        indisponível/GAIA desconectada), nunca vai existir uma
        `assistant_message` de resposta pra esse turno, então precisa
        avisar aqui mesmo (doc: "estilo visual de erro discreto... não
        quero uma QMessageBox"). Encerra qualquer indicador de voz
        pendente (a resposta que ele esperava nunca vai chegar)."""
        if not self.esta_ativo:
            return
        self._bubbles.encerrar_indicador_voz()
        self._bubbles.adicionar_mensagem("erro", motivo)

    def receber_mensagem_usuario_externa(self, texto: str) -> None:
        """Eco de um turno que NÃO veio do `InputBar` (voz contínua,
        clique-pra-falar - mesma razão de `companion_panel.
        receber_mensagem_usuario`); só some se a conversa já estiver
        ativa (ver `receber_resposta` acima pro mesmo raciocínio)."""
        if not self.esta_ativo:
            return
        self._bubbles.adicionar_mensagem("usuario", texto)

    def notificar_estado_semantico(self, estado: str) -> None:
        """`process_main.py` chama em CIMA de `state_changed` (além do
        `StateController` de sempre, que decide animação) - "listening"/
        "thinking"/"transcribing" mostram o indicador de voz (doc, seção
        8), ATIVANDO o overlay sozinho se ainda não estiver (sem roubar
        foco de teclado - `entrar(focar=False)` - o usuário pode nem
        estar olhando pro teclado, só falando)."""
        indicador = _ESTADO_SEMANTICO_PARA_INDICADOR.get(estado)
        if indicador is None:
            if self._estado in ("ouvindo", "processando"):
                self._bubbles.encerrar_indicador_voz()
                self._estado = "ativo"
            return
        if not self.esta_ativo:
            self.entrar(focar=False)
        self._estado = indicador
        self._bubbles.mostrar_indicador_voz(indicador)

    def alternar_historico(self) -> None:
        """Botão de histórico do `InputBar` (2026-09-06, pedido do
        usuário: "falta uma forma de habilitar p mostrar histórico das
        mensagens q mandei e q ela respondeu"). **Revisado 2026-09-07**
        (o usuário corrigiu um desenho anterior que abria uma janela
        `CompanionPanel` separada: "vc entendeu errado... quero remover
        essa tela separada de histórico... só faz as bubble ficar
        visível") - LIGA/DESLIGA o modo histórico do PRÓPRIO
        `BubbleStack` (`alternar_historico`, ver docstring de lá) - os
        MESMOS bubbles flutuantes, sem nenhum painel/janela nova, mostram
        a conversa inteira (permanente, sem o timeout de 15s) com scroll
        pra voltar. NÃO fecha a conversa (`sair()`) nem delega pra
        nenhum outro componente - a conversa continua "ativa" o tempo
        todo, só a VIEW dos bubbles muda. Sincroniza o estado visual do
        próprio botão (`InputBar.definir_historico_ativo`, 2026-09-07,
        pedido do usuário: "eu tenho q saber quando o botao de historico
        ta habilitado ou n")."""
        self._bubbles.alternar_historico()
        self._input.definir_historico_ativo(self._bubbles.historico_ativo)

    def abrir_historico_completo(self) -> None:
        """"Ver completo" de um bubble que estourou o limite de altura
        (`bubble_stack.expandir_solicitado`) - diferente do botão
        dedicado acima (que ALTERNA), isto só GARANTE que o histórico
        está aberto (nunca fecha de volta) - um bubble truncado só faz
        sentido "expandir" pra mostrar o texto inteiro, nunca esconder o
        que já estava visível."""
        if not self._bubbles.historico_ativo:
            self._bubbles.alternar_historico()
            self._input.definir_historico_ativo(self._bubbles.historico_ativo)
