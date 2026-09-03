# -*- coding: utf-8 -*-
"""Controller de reprodução do Mascot/LOKI (plano, seção 7 - contrato de
animação). Só cuida de ESTADO e QUADRO ATUAL; a janela/overlay de verdade
(transparência, clique-através, posição na tela) é responsabilidade da
Fase 1 do plano, ainda não implementada - este módulo não abre nenhuma
janela, só expõe o quadro atual (`QPixmap` + pivô) via sinal, do jeito que
`AnimationCanvas` já faz em `scripts/visualizar_animacoes.py`, mas com a
troca de asset validada contra `state_catalog` em vez de aceita sem checar.

Diferença deliberada do `AnimationCanvas` do visualizador (que é ferramenta
de desenvolvedor, aceita qualquer sequência montada à mão): aqui,
`solicitar_transicao(id)` só aceita ids cujo `estado_origem` bate com o
estado atual do grafo (`state_catalog.transicoes_validas_a_partir_de`) -
um pedido fora do grafo é REJEITADO (log + retorna False), nunca tenta
"tocar assim mesmo" e deixar a personagem num estado incoerente.

Uma AÇÃO (não-loop, `estado_origem == estado_destino` - ex.: rir, mexer
no cabelo) sempre volta pro ÚLTIMO LOOP que estava tocando antes dela
(`self._ultimo_loop_id`), nunca pro `fallback` fixo do catálogo - hoje só
existe um loop sentado de verdade em uso (`sentada_balancando-pernas`),
mas já existe um segundo (`sentada_pensando`) esperando ganhar um
gatilho de verdade (Fase 3). Sem esse retorno dinâmico, uma ação
disparada enquanto ela está "pensando" a devolveria pro idle comum em
vez de continuar pensando - regressão visual boba, mas real, e mais
barata de evitar agora do que remendar depois. `fallback` do catálogo
continua sendo o destino de uma TRANSIÇÃO (que muda de estado de
verdade, não "volta") e o resguardo pra quando não há loop anterior
conhecido (ex.: logo na entrada, antes de qualquer loop ter tocado).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer, Signal

from mascot import state_catalog
from mascot.asset_repository import AnimationAsset, AssetRepository

logger = logging.getLogger(__name__)


class AnimationController(QObject):
    quadro_alterado = Signal()  # payload fica em .quadro_atual / .pivot_atual, não no sinal
    estado_alterado = Signal(str)  # novo estado lógico (ex.: "sentada")
    clipe_concluido = Signal(str)  # id do clipe NÃO-LOOP que acabou de chegar no último quadro

    def __init__(self, repositorio: AssetRepository | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self._repositorio = repositorio or AssetRepository()
        self._asset: AnimationAsset | None = None
        self._entrada: state_catalog.EstadoAnimacao | None = None
        self._indice_quadro = 0
        self._estado_logico: str | None = None
        self._ultimo_loop_id: str | None = None
        self._id_solicitado_mais_recente: str | None = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._avancar)

        self._repositorio.definir_pinados(self._computar_pinados())
        self.iniciar(state_catalog.ANIMACAO_INICIAL)

    def _computar_pinados(self) -> frozenset[str]:
        """Conjunto PERMANENTE de clipes de entrada de movimento/arraste a
        partir do idle (2026-09-02, proposta do usuário: fixar só a
        animação de entrada, usar os 3,7-4s dela como buffer pro resto do
        fluxo carregar). Filtra pela tag `"transition"` que o grafo já usa
        (`state_catalog.py`) em vez de listar ids à mão - pega os 8
        `_iniciar` de direção + `flutuando_para_agarrada` +
        `flutuando_para_sentada` (todos tagueados "transition") e exclui de
        propósito as ações/cenas raras a partir do idle (`flutuando_perdida`,
        `flutuando_cortina-abrindo`, `transformacao_inicio` - tagueadas
        "action", nunca "transition") - essas não valem o RAM permanente,
        são raras e já se beneficiam do pré-carregamento especulativo
        transiente de qualquer forma (`_computar_protegidos_e_candidatos_preload`)."""
        entrada_inicial = state_catalog.CATALOGO[state_catalog.ANIMACAO_INICIAL]
        candidatos = state_catalog.transicoes_validas_a_partir_de(entrada_inicial.estado_destino)
        # Nem toda transição nova a partir do idle merece ficar residente. As
        # cinematográficas (leque, brinde, ninja, Chaos...) são carregadas sob
        # demanda; só os fluxos interativos imediatos de movimento, arraste e
        # sentar entram no conjunto permanente de cold-start.
        categorias_imediatas = {"movement", "drag", "sitting"}
        return frozenset(
            e.id
            for e in candidatos
            if "transition" in e.tags and categorias_imediatas.intersection(e.tags)
        )

    @property
    def animacao_atual(self) -> str | None:
        return self._entrada.id if self._entrada else None

    @property
    def estado_logico(self) -> str | None:
        return self._estado_logico

    @property
    def quadro_atual(self):
        if self._asset is None:
            return None
        return self._asset.frames[self._indice_quadro]

    @property
    def pivot_atual(self) -> tuple[int, int] | None:
        return self._asset.pivot if self._asset else None

    @property
    def tags_atuais(self) -> tuple[str, ...]:
        """Tags do clipe tocando agora (`state_catalog.EstadoAnimacao.tags`)
        - vazio se nada tocando. Exposto pra quem precisa reconhecer uma
        cena ESPECÍFICA por marcação (ex.: `"ninja"`) sem reimplementar o
        lookup no catálogo - `MascotWindow` (2026-09-02, Substituição
        Ninja)."""
        return self._entrada.tags if self._entrada is not None else ()

    @property
    def asset_atual(self) -> AnimationAsset | None:
        return self._asset

    def iniciar(self, animation_id: str) -> None:
        """Só usado na entrada do controller (construtor) - ignora o grafo
        porque não existe "estado atual" ainda pra validar contra.
        SÍNCRONO de propósito (`_carregar_e_tocar_sincrono`) - não existe
        "animação atual" nenhuma pra continuar mostrando enquanto carrega
        em segundo plano, e vários consumidores (`MascotWindow.__init__`,
        testes) esperam a 1ª animação já pronta logo após construir."""
        self._carregar_e_tocar_sincrono(animation_id)

    def forcar_estado(self, animation_id: str) -> None:
        """Escape hatch pro runtime (não só a entrada, como `iniciar`) pra
        estados SEM NENHUMA transição de volta no grafo - ex.: acordar do
        sono (pedido do usuário, 2026-08-29: "reconhecer AFK pra por a
        GAIA pra dormir"), onde não existe arte de "acordando" ainda,
        então não tem clipe pra tocar entre "dormindo" e o idle normal.
        Pula a validação do grafo de propósito - usar só quando a arte
        certa pra uma transição de verdade não existe; prefira sempre
        `solicitar_transicao` quando ela existir. SÍNCRONO (evento raro,
        não é o caminho comum de transição do dia a dia) - ver `iniciar`."""
        self._carregar_e_tocar_sincrono(animation_id)

    def solicitar_transicao(self, animation_id: str) -> bool:
        entrada_pedida = state_catalog.CATALOGO.get(animation_id)
        if entrada_pedida is None:
            logger.warning("Mascot: animação desconhecida no catálogo: %s", animation_id)
            return False

        if self._entrada is not None and not self._entrada.loop and not self._entrada.interrompivel:
            logger.info("Mascot: transição pra %s rejeitada, %s não é interrompível", animation_id, self._entrada.id)
            return False

        validas = state_catalog.transicoes_validas_a_partir_de(self._estado_logico)
        if entrada_pedida not in validas:
            logger.info(
                "Mascot: transição pra %s rejeitada, grafo não permite a partir de %s",
                animation_id, self._estado_logico,
            )
            return False

        self._carregar_e_tocar(animation_id)
        return True

    def parar(self) -> None:
        self._timer.stop()

    def _computar_protegidos_e_candidatos_preload(self, animation_id: str):
        """Proteção de cache por orçamento de memória (2026-09-01, ver
        comentário de `ORCAMENTO_MEMORIA_PADRAO_MB` em `asset_repository.
        py`) - protege o clipe que está prestes a carregar + o que for
        transição válida a partir do destino dele, reusando o MESMO grafo
        já usado pra validar transições (nunca uma lista nova) - evita
        reler do disco algo que está em uso/prestes a usar de novo quando
        o orçamento aperta. Os mesmos "prováveis próximos" também viram
        candidatos de PRÉ-CARREGAMENTO (`_carregar_e_tocar`, achado
        2026-09-02: carregar do zero trava a UI por até quase 1s) - a
        lista de preload continua SEM filtro de tag (ações raras também
        merecem esquentar o cache, evita o pulo visual na 1ª vez).

        🔥 CORRIGIDO (2026-09-02, achado na remedição de desempenho pós-
        Achado 4) - `protegidos` filtrava só pelo `animation_id` + TODAS as
        transições válidas a partir do destino, sem filtrar por tag como
        `_computar_pinados` já faz. Parado em `flutuando_idle` (idle nunca
        muda de estado, então `protegidos` nunca é recalculado), isso
        deixava `flutuando_cortina-abrindo`/`transformacao_inicio`/
        `flutuando_perdida` (tag `"action"`, EXCLUÍDAS de propósito do
        pinning permanente no Achado 4 - "não valem o RAM permanente")
        permanentemente protegidas mesmo assim, por nunca perderem a
        proteção transiente enquanto parada. Resultado medido: idle puro
        subiu pra 438,5MB (~113MB a mais que os 10 pinados documentados).
        Filtrar `protegidos` pela tag `"transition"` (mesmo filtro de
        `_computar_pinados`) devolve o comportamento pretendido: ações
        raras continuam pré-carregadas (preload sem filtro, acima), mas
        voltam a ser despejáveis sob pressão de orçamento em vez de presas
        pra sempre enquanto parada."""
        entrada_pedida = state_catalog.CATALOGO.get(animation_id)
        candidatos = state_catalog.transicoes_validas_a_partir_de(entrada_pedida.estado_destino) if entrada_pedida else ()
        protegidos = {animation_id} | {e.id for e in candidatos if "transition" in e.tags}
        return protegidos, candidatos

    def _carregar_e_tocar_sincrono(self, animation_id: str, *, estado_confirmado: str | None = None) -> None:
        """Bloqueia até carregar (200-900ms medido pras animações reais) -
        só pro cold-start (`iniciar`/`forcar_estado`, ver docstrings lá).

        🔥 CORRIGIDO (2026-09-02, achado ao vivo pelo usuário: "antes de
        fazer uma animação de flutuar pra alguma direção, ela dá uma
        travada") - até aqui, o cold-start NUNCA pré-carregava nada (só
        `_carregar_e_tocar`, o caminho assíncrono, disparava
        pré-carregamento) - a 1ª vez que o Mascot liga e fica parada em
        `flutuando_idle`, as 8 direções de voo (candidatas de Wander a
        partir do idle) nunca esquentavam o cache até uma transição de
        verdade acontecer. Resultado: o 1º Wander depois de ligar sempre
        pegava uma direção FRIA - o deslocamento físico já começa na hora
        (`BehaviorScheduler`), mas a pose de voar só aparecia depois do
        carregamento em segundo plano terminar, um "pulo" visível."""
        protegidos, candidatos_preload = self._computar_protegidos_e_candidatos_preload(animation_id)
        self._repositorio.definir_protegidos(protegidos)
        asset = self._repositorio.obter(animation_id)
        self._id_solicitado_mais_recente = animation_id
        self._aplicar_asset_carregado(asset, animation_id, estado_confirmado=estado_confirmado)
        for candidata in candidatos_preload:
            self._repositorio.garantir_carregado_assincrono(candidata.id, lambda _asset: None, prioridade=False)

    def _carregar_e_tocar(self, animation_id: str, *, estado_confirmado: str | None = None) -> None:
        """Caminho do RUNTIME (`solicitar_transicao`, encadeamento de
        `_avancar`) - NUNCA bloqueia a UI (`AssetRepository.
        garantir_carregado_assincrono`). Enquanto o novo asset carrega em
        segundo plano, a animação ATUAL continua tocando normalmente (o
        timer antigo só é parado aqui, retomado só quando o novo estiver
        pronto - `_aplicar_asset_carregado`) - achado ao vivo 2026-09-02:
        "trava as vezes quando termina uma animação" era isso rodando
        síncrono antes."""
        protegidos, candidatos_preload = self._computar_protegidos_e_candidatos_preload(animation_id)
        self._repositorio.definir_protegidos(protegidos)

        self._timer.stop()  # evita o timer antigo re-disparar _avancar (mesmo intervalo de antes) enquanto o novo asset ainda carrega
        self._id_solicitado_mais_recente = animation_id
        self._repositorio.garantir_carregado_assincrono(
            animation_id,
            lambda asset, _pedido=animation_id: self._aplicar_asset_carregado(
                asset, _pedido, estado_confirmado=estado_confirmado,
            ),
        )
        for candidata in candidatos_preload:
            self._repositorio.garantir_carregado_assincrono(candidata.id, lambda _asset: None, prioridade=False)

    def _aplicar_asset_carregado(
        self, asset: AnimationAsset, id_pedido: str, *, estado_confirmado: str | None
    ) -> None:
        if id_pedido != self._id_solicitado_mais_recente:
            # Pedido OBSOLETO - uma transição mais nova já foi solicitada
            # enquanto este carregava em segundo plano (ex.: o usuário
            # arrastou ela, ou o scheduler mudou de ideia) - aplicar isso
            # agora sobrescreveria um estado mais recente com um antigo.
            return
        # asset.id pode diferir de id_pedido se o repositório caiu no
        # fallback (asset pedido inválido/ausente) - o catálogo é indexado
        # pelo id que REALMENTE carregou, não pelo que foi pedido.
        entrada = state_catalog.CATALOGO[asset.id]

        self._asset = asset
        self._entrada = entrada
        self._indice_quadro = 0
        # `entrada.velocidade_multiplicador` é declarativo (catálogo, não
        # argumento) - fonte ÚNICA da verdade sobre a velocidade de um
        # clipe, lida aqui não importa QUEM pediu a transição
        # (`solicitar_transicao` do arraste real, `forcar_estado`, ou o
        # "forçar animação" da bandeja do sistema) - 2026-09-02, pedido do
        # usuário: "N gosto de ter q editar 2 lugares p msm coisa".
        self._timer.start(max(1, round(asset.frame_duration_ms / entrada.velocidade_multiplicador)))
        self.quadro_alterado.emit()

        if entrada.loop:
            # um loop de espera JÁ representa o estado, não precisa
            # "terminar" pra estado_logico virar o destino (diferente de
            # uma transição, que só chega no destino no fim do clipe).
            self._estado_logico = entrada.estado_destino
            self._ultimo_loop_id = asset.id
            self.estado_alterado.emit(self._estado_logico or "")
        elif estado_confirmado is not None:
            # Encadeamento transição -> transição: o clipe anterior já chegou
            # ao destino, mas o próximo ainda não chegou ao destino dele. A
            # confirmação acontece só depois de carregar o próximo asset para
            # que listeners reentrantes nunca sejam sobrescritos por uma carga
            # que ainda estava pendente.
            self._estado_logico = estado_confirmado
            self.estado_alterado.emit(self._estado_logico)

    def _avancar(self) -> None:
        if self._asset is None or self._entrada is None:
            return
        proximo = self._indice_quadro + 1
        if proximo < self._asset.frame_count:
            self._indice_quadro = proximo
            self.quadro_alterado.emit()
            return

        if self._entrada.loop:
            self._indice_quadro = 0
            self.quadro_alterado.emit()
            return

        # não-loop chegou no fim: entra no estado de destino sem deixar o
        # Mascot parado no último quadro. Uma AÇÃO (mesmo estado de
        # origem e destino) volta pro loop que estava tocando antes dela;
        # uma TRANSIÇÃO (muda de estado de verdade) usa o destino
        # declarado no catálogo - ver docstring do módulo.
        self.clipe_concluido.emit(self._entrada.id)
        e_acao = self._entrada.estado_origem == self._entrada.estado_destino
        destino = self._entrada.estado_destino
        ultimo_loop_compativel = (
            self._ultimo_loop_id is not None
            and state_catalog.CATALOGO[self._ultimo_loop_id].estado_destino == destino
        )
        if e_acao and ultimo_loop_compativel:
            proxima_animacao = self._ultimo_loop_id
        elif self._entrada.fallback:
            proxima_animacao = self._entrada.fallback
        else:
            # Poses terminais (deitada/dormindo) permanecem no último
            # quadro até uma transição explicitamente compatível. Não tem
            # `_carregar_e_tocar` nenhum depois daqui, então precisa
            # atualizar/emitir `estado_logico` direto (único caso deste
            # método que faz isso - ver nota abaixo sobre reentrância).
            self._estado_logico = destino
            self.estado_alterado.emit(self._estado_logico or "")
            self._indice_quadro = self._asset.frame_count - 1
            self._timer.stop()
            self.quadro_alterado.emit()
            return
        # `estado_logico` só é atualizado (e `estado_alterado` só emitido)
        # DENTRO de `_carregar_e_tocar`, nunca antes de chamá-lo - emitir
        # cedo demais deixava quem escuta o sinal (ex.: `BehaviorScheduler`
        # pedindo a animação de parar) reentrar em `solicitar_transicao`
        # ENQUANTO este método ainda ia chamar `_carregar_e_tocar` de novo
        # logo abaixo pra carregar o loop de fallback - o pedido
        # reentrante era sobrescrito na sequência (bug real, 2026-08-29:
        # Wander nunca saía do quadro do loop, "parar" nunca aparecia).
        self._carregar_e_tocar(proxima_animacao, estado_confirmado=destino)
