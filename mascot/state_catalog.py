# -*- coding: utf-8 -*-
"""Catálogo versionado do grafo de estados do Mascot/LOKI.

Convenção dos ids: ``_`` separa categorias semânticas e ``-`` une palavras
da mesma categoria (por exemplo, ``flutuando_superior-esquerda_iniciar``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class EstadoAnimacao:
    id: str
    loop: bool
    estado_origem: str | None
    estado_destino: str | None
    fallback: str | None
    interrompivel: bool
    tags: tuple[str, ...] = field(default_factory=tuple)
    # Multiplicador de velocidade DECLARATIVO do clipe (2026-09-02) - fonte
    # ÚNICA da verdade sobre "esse clipe toca mais rápido que o normal",
    # lida direto daqui por `AnimationController` (nunca passada por quem
    # chama `solicitar_transicao`). Antes disso vivia espalhada em
    # constantes soltas de `MascotWindow` (`MULTIPLICADOR_VELOCIDADE_
    # AGARRAR`/`_NINJA`) passadas explicitamente só no caminho do arraste -
    # a bandeja do sistema ("forçar animação", playground de teste) chama
    # `solicitar_transicao` direto, sem saber desses multiplicadores, e
    # tocava tudo no ritmo normal (achado ao vivo pelo usuário, 2026-09-02:
    # "quero q pela bandeja esteja tudo funcionando como deveria tbm. N
    # gosto de ter q editar 2 lugares p msm coisa").
    velocidade_multiplicador: float = 1.0


def _estado(animation_id: str, *, loop: bool, origem: str | None, destino: str | None,
            fallback: str | None, interrompivel: bool, tags: tuple[str, ...],
            velocidade_multiplicador: float = 1.0) -> EstadoAnimacao:
    return EstadoAnimacao(animation_id, loop, origem, destino, fallback, interrompivel, tags, velocidade_multiplicador)


def _acao_sentada(animation_id: str, *tags: str) -> EstadoAnimacao:
    return _estado(
        animation_id, loop=False, origem="sentada", destino="sentada",
        fallback="sentada_balancando-pernas", interrompivel=False, tags=("action", *tags),
    )


CATALOGO: dict[str, EstadoAnimacao] = {
    "flutuando_idle": _estado(
        "flutuando_idle", loop=True, origem=None, destino="flutuando",
        fallback=None, interrompivel=True, tags=("idle", "floating"),
    ),
    "flutuando_para_sentada": _estado(
        "flutuando_para_sentada", loop=False, origem="flutuando", destino="sentada",
        fallback="sentada_balancando-pernas", interrompivel=False, tags=("transition", "sitting"),
    ),
    "sentada_para_flutuando": _estado(
        "sentada_para_flutuando", loop=False, origem="sentada", destino="flutuando",
        fallback="flutuando_idle", interrompivel=False, tags=("transition", "floating"),
    ),
    "sentada_balancando-pernas": _estado(
        "sentada_balancando-pernas", loop=True, origem="sentada", destino="sentada",
        fallback=None, interrompivel=True, tags=("idle", "sitting"),
    ),
    "sentada_pensando": _estado(
        "sentada_pensando", loop=True, origem="sentada", destino="sentada",
        fallback=None, interrompivel=True, tags=("idle", "thinking"),
    ),
    "sentada_deitando": _estado(
        "sentada_deitando", loop=False, origem="sentada", destino="deitada",
        fallback=None, interrompivel=False, tags=("transition", "sleep", "terminal-pose"),
    ),
    "sentada_caindo-no-sono": _estado(
        "sentada_caindo-no-sono", loop=False, origem="sentada", destino="dormindo",
        fallback=None, interrompivel=False, tags=("transition", "sleep", "terminal-pose"),
    ),
    "dormindo_trocando-lado": _estado(
        "dormindo_trocando-lado", loop=False, origem="dormindo", destino="dormindo",
        fallback=None, interrompivel=False, tags=("action", "sleep", "terminal-pose"),
    ),
}


CATALOGO.update({
    "sentada_espreguicando": _acao_sentada("sentada_espreguicando", "stretch"),
    "sentada_olhando-ao-redor": _acao_sentada("sentada_olhando-ao-redor", "curious"),
    "sentada_acenando": _acao_sentada("sentada_acenando", "greeting"),
    "sentada_bocejando": _acao_sentada("sentada_bocejando", "tired"),
    "sentada_brincando-cabelo": _acao_sentada("sentada_brincando-cabelo", "hair"),
    "sentada_arrumando-cabelo": _acao_sentada("sentada_arrumando-cabelo", "hair"),
    "sentada_enrolando-cabelo": _acao_sentada("sentada_enrolando-cabelo", "hair"),
    "sentada_enrolando-cabelo_corando": _acao_sentada("sentada_enrolando-cabelo_corando", "hair", "shy"),
    "sentada_jogando-cabelo": _acao_sentada("sentada_jogando-cabelo", "hair"),
    "sentada_rindo": _acao_sentada("sentada_rindo", "laugh"),
    "sentada_risada-esnobe": _acao_sentada("sentada_risada-esnobe", "laugh"),
    "sentada_gargalhada_quase-caindo": _acao_sentada("sentada_gargalhada_quase-caindo", "laugh"),
    "sentada_gargalhada_caindo": _acao_sentada("sentada_gargalhada_caindo", "laugh"),
    "sentada_segurando-riso": _acao_sentada("sentada_segurando-riso", "laugh"),
    "sentada_rindo_sem-graca": _acao_sentada("sentada_rindo_sem-graca", "laugh", "awkward"),
    "sentada_tehepero": _acao_sentada("sentada_tehepero", "playful"),
})


DIRECOES_MOVIMENTO = (
    "direita", "esquerda", "subida", "descida", "superior-direita",
    "superior-esquerda", "inferior-direita", "inferior-esquerda",
)

for direcao in DIRECOES_MOVIMENTO:
    estado_movimento = f"flutuando-{direcao}"
    iniciar = f"flutuando_{direcao}_iniciar"
    loop = f"flutuando_{direcao}_loop"
    parar = f"flutuando_{direcao}_parar"
    CATALOGO[iniciar] = _estado(
        iniciar, loop=False, origem="flutuando", destino=estado_movimento,
        fallback=loop, interrompivel=False, tags=("transition", "movement", direcao),
    )
    CATALOGO[loop] = _estado(
        loop, loop=True, origem=estado_movimento, destino=estado_movimento,
        fallback=None, interrompivel=True, tags=("movement", direcao),
    )
    CATALOGO[parar] = _estado(
        parar, loop=False, origem=estado_movimento, destino="flutuando",
        fallback="flutuando_idle", interrompivel=False, tags=("transition", "movement", direcao),
    )


for origem, destino in (("direita", "esquerda"), ("esquerda", "direita"),
                        ("descida", "subida"), ("subida", "descida")):
    animation_id = f"flutuando_{origem}_para_{destino}"
    CATALOGO[animation_id] = _estado(
        animation_id, loop=False, origem=f"flutuando-{origem}", destino=f"flutuando-{destino}",
        fallback=f"flutuando_{destino}_loop", interrompivel=False,
        tags=("transition", "movement", origem, destino),
    )


CATALOGO["flutuando_perdida"] = _estado(
    "flutuando_perdida", loop=False, origem="flutuando", destino="flutuando",
    fallback="flutuando_idle", interrompivel=False, tags=("action", "confused"),
)

CATALOGO["flutuando_cortina-abrindo"] = _estado(
    "flutuando_cortina-abrindo", loop=False, origem="flutuando", destino="flutuando",
    fallback="flutuando_idle", interrompivel=False, tags=("action", "scene", "curtain"),
)

# Sequência cinematográfica completa: a transformação ocupa dois clipes, a
# invocação introduz o dragão, o ataque troca a forma sob as chamas e a última
# cena limpa a fuligem antes de reconectar ao idle flutuando.
for animation_id, origem, destino, fallback, tags in (
    (
        "transformacao_inicio", "flutuando", "transformacao-energia",
        "transformacao_fim", ("action", "scene", "transformation", "ssj3"),
    ),
    (
        "transformacao_fim", "transformacao-energia", "ssj3",
        "ssj3_invocacao-dragao", ("transition", "scene", "transformation", "ssj3"),
    ),
    (
        "ssj3_invocacao-dragao", "ssj3", "ssj3-com-dragao",
        "ssj3_para_chamuscada", ("action", "scene", "dragon", "ssj3"),
    ),
    (
        "ssj3_para_chamuscada", "ssj3-com-dragao", "chamuscada-com-dragao",
        "chamuscada_para_flutuando", ("transition", "scene", "dragon", "soot"),
    ),
    (
        "chamuscada_para_flutuando", "chamuscada-com-dragao", "flutuando",
        "flutuando_idle", ("transition", "scene", "dragon", "recovery", "floating"),
    ),
):
    CATALOGO[animation_id] = _estado(
        animation_id, loop=False, origem=origem, destino=destino,
        fallback=fallback, interrompivel=False, tags=tags,
    )


# Fluxo de arraste: o estado lógico "agarrada" representa a Galateia
# suspensa pelo cursor. As reações são loops intercambiáveis; ao soltá-la,
# uma das duas quedas toca e encadeia automaticamente a recuperação até o
# idle flutuando.
CATALOGO["flutuando_para_agarrada"] = _estado(
    "flutuando_para_agarrada", loop=False, origem="flutuando", destino="agarrada",
    fallback="arrastada_loop_calma", interrompivel=False,
    tags=("transition", "drag", "grabbed"),
    # sem acelerar, os 48 quadros (frameDurationMs 83 -> ~4s) deixavam ela
    # demorando pra chegar na pose de carregada enquanto o usuário já está
    # arrastando de verdade em tempo real - pedido do usuário, 2026-08-29:
    # "pode agilizar a animação pra ela ficar na pose de sendo carregada
    # rápido".
    velocidade_multiplicador=3.0,
)

for animation_id, emocao in (
    ("arrastada_loop_calma", "calm"),
    ("arrastada_loop_brava", "angry"),
    ("arrastada_loop_chorando-medo", "crying-afraid"),
    ("arrastada_loop_furiosa", "furious"),
    ("arrastada_loop_panico-1", "panic"),
    ("arrastada_loop_panico-2", "panic"),
    ("arrastada_loop_emburrada", "sulking"),
):
    CATALOGO[animation_id] = _estado(
        animation_id, loop=True, origem="agarrada", destino="agarrada",
        fallback=None, interrompivel=True, tags=("drag", "grabbed", emocao),
    )

CATALOGO["arrastada_para_queda-joelho"] = _estado(
    "arrastada_para_queda-joelho", loop=False, origem="agarrada", destino="queda-joelhos",
    fallback="queda-joelhos_para_flutuando", interrompivel=False,
    tags=("transition", "drag", "fall", "knees"),
)
CATALOGO["arrastada_para_queda-bunda"] = _estado(
    "arrastada_para_queda-bunda", loop=False, origem="agarrada", destino="queda-bunda",
    fallback="queda-bunda_para_flutuando", interrompivel=False,
    tags=("transition", "drag", "fall", "seated"),
)
CATALOGO["queda-bunda_para_flutuando"] = _estado(
    "queda-bunda_para_flutuando", loop=False, origem="queda-bunda", destino="flutuando",
    fallback="flutuando_idle", interrompivel=False,
    tags=("transition", "recovery", "floating", "seated"),
)
CATALOGO["queda-joelhos_para_flutuando"] = _estado(
    "queda-joelhos_para_flutuando", loop=False, origem="queda-joelhos", destino="flutuando",
    fallback="flutuando_idle", interrompivel=False,
    tags=("transition", "recovery", "floating", "knees"),
)


def _carregar_estados_declarativos(
    config_path: Path | None = None,
) -> dict[str, EstadoAnimacao]:
    """Carrega estados opcionais declarados junto à fonte da animação.

    O catálogo histórico continua explícito neste módulo. Entradas novas podem
    trazer um objeto ``state`` em ``data/animacoes_galateia.json`` e deixam de
    exigir edição de Python para participar do grafo. Uma entrada explícita deste
    arquivo sempre vence uma declarativa com o mesmo id.
    """
    path = config_path or Path(__file__).resolve().parents[1] / "data" / "animacoes_galateia.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, EstadoAnimacao] = {}
    for item in data.get("animations", []):
        state = item.get("state")
        if not isinstance(state, dict):
            continue
        animation_id = str(item.get("id", "")).strip()
        # Ao carregar o manifesto real, as entradas históricas explícitas deste
        # módulo continuam tendo precedência. Um caminho fornecido pelo chamador
        # representa um catálogo isolado (útil para validação/testes) e deve ser
        # interpretado por completo, mesmo que reutilize um id já conhecido.
        if not animation_id or (config_path is None and animation_id in CATALOGO):
            continue
        destination = state.get("destination")
        if destination is not None and not isinstance(destination, str):
            raise ValueError(f"{animation_id}: state.destination precisa ser texto ou null.")
        origin = state.get("origin")
        fallback = state.get("fallback")
        if origin is not None and not isinstance(origin, str):
            raise ValueError(f"{animation_id}: state.origin precisa ser texto ou null.")
        if fallback is not None and not isinstance(fallback, str):
            raise ValueError(f"{animation_id}: state.fallback precisa ser texto ou null.")
        tags = state.get("tags", ())
        if not isinstance(tags, (list, tuple)) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError(f"{animation_id}: state.tags precisa ser uma lista de textos.")
        velocidade_multiplicador = state.get("speedMultiplier", 1.0)
        if not isinstance(velocidade_multiplicador, (int, float)) or isinstance(velocidade_multiplicador, bool):
            raise ValueError(f"{animation_id}: state.speedMultiplier precisa ser numérico.")
        result[animation_id] = _estado(
            animation_id,
            loop=bool(item.get("loop", True)),
            origem=origin,
            destino=destination,
            fallback=fallback,
            interrompivel=bool(state.get("interruptible", bool(item.get("loop", True)))),
            tags=tuple(tags),
            velocidade_multiplicador=float(velocidade_multiplicador),
        )
    return result


CATALOGO.update(_carregar_estados_declarativos())

ANIMACAO_INICIAL = "flutuando_idle"

# Linha do assento calibrada pelo usuário na barra de tarefas real. O recorte
# compartilhado passou a 803x715 para acomodar as quedas; a mesma coordenada
# da arte fica agora em y=224 dentro da célula 384x342.
LINHA_ASSENTO_SENTADA_PX = 224


def obter(animation_id: str) -> EstadoAnimacao:
    return CATALOGO[animation_id]


def transicoes_validas_a_partir_de(estado: str | None) -> tuple[EstadoAnimacao, ...]:
    return tuple(e for e in CATALOGO.values() if e.estado_origem == estado)
