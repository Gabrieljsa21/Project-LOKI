# -*- coding: utf-8 -*-
"""Contrato de carregamento de animações do LOKI/Mascot (Fase 0 do plano,
`C:\\Workspace\\Project LOKI.md`, seção 7.1) - único ponto que sabe ler
`assets/galateia/animations/`. Descobre os assets existentes dinamicamente;
o catálogo de estados decide quais deles podem ser pedidos pelo runtime.

Duas camadas deliberadamente separadas:
- `validar_geometria`/`validar_manifesto` (SEM Qt) - reaproveitadas por
  `scripts/validar_animacoes.py` (roda sem QApplication, checagem rápida
  de CI/terminal) e por esta própria `AssetRepository`, pra nunca existirem
  2 implementações da mesma regra.
- `AnimationAsset`/`AssetRepository` (COM Qt, `QPixmap`) - carrega pixels
  de verdade, corta os frames 1x só no load (a mesma lição do spike de
  stack: recriar recorte por frame vaza memória/CPU à toa - aqui nem chega
  a ser um risco, já nasce certo).

Contrato (seção 7.1 do plano):
1. resolve `assets/galateia/animations` pela raiz do app, nunca pelo diretório
   atual (`_RAIZ_ANIMACOES`, calculado a partir de `__file__`);
2. descobre só pastas com `animation.json` válido;
3. valida schema, dimensões, quantidade de células e textura;
4. carrega sob demanda com cache limitado (`AssetRepository.obter`, LRU);
5. usa fallback seguro (`flutuando_idle`) se um asset falhar;
6. funciona em desenvolvimento e em app empacotado (caminho por `__file__`,
   não por `os.getcwd()` - sobrevive a qualquer diretório de execução).
"""
from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

RAIZ_APP = Path(__file__).resolve().parents[1]
RAIZ_ANIMACOES = RAIZ_APP / "assets" / "galateia" / "animations"
ARQUIVO_GEOMETRIA = RAIZ_ANIMACOES / "geometry.json"

ANIMACAO_FALLBACK = "flutuando_idle"
# atlas sob demanda (seção 15), mas 4 era baixo demais pra sobreviver ao
# Wander/perseguição de destino (2026-08-29): cada direção de voo por si
# só usa 3 assets (iniciar+loop+parar) - um ÚNICO salto numa direção
# nova já expulsava a anterior (e o flutuando_idle) do cache, obrigando a
# reler o PNG do disco e decodificar de novo na hora seguinte, síncrono
# na thread da UI - bug real reportado pelo usuário: "travamento no
# início de cada fluxo de ação" era esse disk I/O, não a física.
#
# 🔥 CORRIGIDO (2026-09-01, achado medindo Fase 5 do plano) - o limite de
# "64 arquivos" (cobria o catálogo inteiro de 57 pastas da época) partia
# de uma conta ERRADA: "~76MB de atlas" usava o tamanho do `.webp`
# COMPRIMIDO em disco, não o tamanho DECODIFICADO em RAM (o que
# `atlas.copy(QRect(...))` guarda por quadro - ver `AnimationAsset.
# carregar` abaixo). Toda animação usa a MESMA célula (384x342px,
# `geometry.json`, pro pivô nunca saltar entre clipes) - cada quadro
# custa `384*342*4 bytes ≈ 513KB`, e com 62,8 quadros em média por
# animação (algumas chegam a 120), isso é ~31,5MB por animação, não os
# ~1,3MB que a conta original assumia. Com 64 slots quase iguais ao
# catálogo (71 hoje), autonomia "viva" media 700+MB reais (medido com
# `scripts/medir_desempenho.py`) - bem acima da meta de 200MB do
# plano (seção 15). Trocado de "N arquivos" pra "orçamento de memória
# real" (`ORCAMENTO_MEMORIA_PADRAO_MB` abaixo) - protege a animação
# tocando agora + as transições válidas a partir dela (nunca reintroduz
# o bug de 2026-08-29 acima) e respeita um teto de MB de verdade pro
# resto, em vez de contar arquivos sem saber o peso real de cada um.
#
# 🔥 SUBIU de 180 pra 320 (2026-09-02, proposta do usuário: "N posso deixar
# apenas a animação inicial de transição sempre carregados como extra, e
# enquanto eles acontecem carrega resto do fluxo? Tem 4s p isso") - além da
# proteção DINÂMICA acima (`definir_protegidos`, muda a cada transição),
# `AnimationController` agora fixa PERMANENTEMENTE (`definir_pinados`) os
# clipes de ENTRADA de movimento/arraste a partir do idle (8 direções de
# voo + `flutuando_para_agarrada` + `flutuando_para_sentada`, filtrados
# pela tag "transition" do próprio grafo, nunca por id à mão) - cada um
# toca 3,73-3,98s, folga de sobra sobre o pior carregamento em segundo
# plano já medido (900ms) pro clipe SEGUINTE (loop/reação) esquentar
# enquanto o de entrada ainda está tocando. Medido: 214,9MB só pras 8
# direções + agarrada, +23,5MB com para_sentada = ~238,4MB de base fixa
# (mais os 17MB do fallback, sempre protegido à parte). 320MB cobre essa
# base + folga pro que estiver tocando fora do conjunto fixo (loops de
# arraste, ações sentada) sem estourar toda hora. Configurável desde
# 2026-09-02 (`mascot/config.py::MASCOT_PADRAO["memoria_orcamento_mb"]`,
# Painel "🧚 Mascot (LOKI)" → Desempenho) - este valor continua sendo só
# o PADRÃO de fábrica, pra quem nunca mexeu na config ou usa
# `AssetRepository()`/`AnimationController()` direto (scripts, testes).
ORCAMENTO_MEMORIA_PADRAO_MB = 320.0
BYTES_POR_PIXEL_RGBA = 4

# 🔥 CORRIGIDO (2026-09-02, achado medindo o próprio fix acima ao vivo) -
# a 1ª versão do carregamento assíncrono disparava uma `threading.Thread`
# NOVA pra cada candidato de pré-carregamento (até 21 de uma vez, ver
# `AnimationController._computar_protegidos_e_candidatos_preload`) - medido:
# `solicitar_transicao()` (que deveria ser quase instantâneo, fire-and-
# forget) passou a levar 1,5s+ só pra RETORNAR, porque os `QImage`/
# `.copy()` das threads de fundo disputam o GIL entre si (não o liberam
# por completo durante a decodificação) e a thread principal fica
# esperando vez pra sequer terminar de CRIAR as threads seguintes -
# travava a UI de um jeito DIFERENTE, mas travava igual. Um
# `ThreadPoolExecutor` com poucos workers enfileira o excesso em vez de
# competir tudo de uma vez - `submit()` nunca bloqueia quem chama
# (só `Thread.start()` de N threads em sequência bloqueava), e o
# carregamento de fundo em si fica mais previsível (poucos workers
# competindo pelo GIL por vez, não dezenas).
#
# 🔥 2ª CORREÇÃO (mesmo dia, achado no teste automatizado) - uma fila
# única (`ThreadPoolExecutor`) ainda tinha um problema: FIFO significa
# que um pedido de PRÉ-CARREGAMENTO enfileirado ANTES (ex.: de um estado
# anterior) podia atrasar o carregamento da animação REALMENTE pedida
# agora, se a fila já tivesse acumulado o bastante - flakiness real
# observada ("arraste real inicia a transição para agarrada" ora
# passava, ora não, dependendo de quanto pré-carregamento sobrava na
# fila).
#
# 🔥 3ª CORREÇÃO (mesmo dia) - `ThreadPoolExecutor` foi trocado por
# `threading.Thread(daemon=True)` + `threading.Semaphore` (uma pra cada
# prioridade, ver `_SEMAFORO_PRINCIPAL`/`_SEMAFORO_PRELOAD` abaixo):
# threads de um `ThreadPoolExecutor` NÃO são daemon por padrão - o
# `atexit` que o módulo `concurrent.futures.thread` registra sozinho
# espera TODAS as threads de TODOS os pools do processo terminarem antes
# de deixar o Python fechar de vez. Com um backlog grande de
# pré-carregamento de baixa prioridade (até 21 candidatos por transição),
# isso significa a Galateia Mascot podia demorar bem mais que o esperado
# pra encerrar de verdade ao fechar - ou pior, nunca perceber isso porque
# em uso normal a diferença passaria despercebida, só aparecendo como
# "processo órfão" ocasional. `Semaphore.acquire()` bloqueado NÃO disputa
# o GIL enquanto espera (ao contrário de 20 threads todas decodificando
# ao mesmo tempo) - resolve o problema original de GIL sem herdar o
# problema de lifecycle do executor.
MAX_THREADS_CARREGAMENTO = 1
MAX_THREADS_PRELOAD = 1


class AssetInvalido(Exception):
    """Manifesto/atlas existe mas não passa da validação (schema, geometria
    incompatível com `geometry.json`, célula insuficiente pro frameCount)."""


class AssetAusente(Exception):
    """Pasta/arquivo esperado não existe."""


# --------------------------------------------------------------------------
# Camada 1: validação pura (sem Qt) - reaproveitada por
# scripts/validar_animacoes.py e pela AssetRepository abaixo.
# --------------------------------------------------------------------------

def carregar_geometria_esperada() -> dict:
    """`geometry.json` é a autoridade de canvas/recorte/célula/pivot comuns
    a TODAS as animações (plano, seção 3.1) - sem ele, não tem como validar
    nada, é erro fatal (arquivo base do conjunto, não de uma animação só)."""
    if not ARQUIVO_GEOMETRIA.is_file():
        raise AssetAusente(f"geometry.json não encontrado em {ARQUIVO_GEOMETRIA}")
    geometria = json.loads(ARQUIVO_GEOMETRIA.read_text(encoding="utf-8"))
    return {
        "sourceCanvas": geometria["sourceCanvas"],
        "sourceCrop": geometria["sourceCrop"],
        "cell": geometria["cell"],
        "pivot": geometria["pivot"],
    }


def _geometria_do_manifesto(manifesto: dict) -> dict:
    grid = manifesto.get("grid", {})
    return {
        "sourceCanvas": manifesto.get("sourceCanvas"),
        "sourceCrop": manifesto.get("sourceCrop"),
        "cell": {"width": grid.get("cellWidth"), "height": grid.get("cellHeight")},
        "pivot": manifesto.get("pivot"),
    }


def validar_manifesto(animation_id: str, manifesto: dict, geometria_esperada: dict) -> None:
    """Levanta `AssetInvalido` com a primeira violação encontrada - schema
    mínimo, geometria compatível com `geometry.json`, células suficientes
    pro `frameCount` declarado. Não abre nenhum arquivo de imagem (isso é
    responsabilidade da camada com Qt, `AnimationAsset.carregar`)."""
    campos_obrigatorios = ("id", "texture", "frameCount", "frameDurationMs", "loop", "grid", "pivot")
    faltando = [campo for campo in campos_obrigatorios if campo not in manifesto]
    if faltando:
        raise AssetInvalido(f"{animation_id}: campos faltando no manifesto: {', '.join(faltando)}")

    asset_type = manifesto.get("assetType", "character")
    if asset_type == "character":
        if _geometria_do_manifesto(manifesto) != geometria_esperada:
            raise AssetInvalido(f"{animation_id}: geometria diferente de geometry.json")
    elif asset_type == "scene":
        canvas = manifesto.get("sourceCanvas", {})
        crop = manifesto.get("sourceCrop", {})
        grid = manifesto.get("grid", {})
        if canvas != geometria_esperada["sourceCanvas"]:
            raise AssetInvalido(f"{animation_id}: cena usa canvas de origem diferente do padrão")
        try:
            crop_width = int(crop["right"]) - int(crop["left"])
            crop_height = int(crop["bottom"]) - int(crop["top"])
            cell_width = int(grid["cellWidth"])
            cell_height = int(grid["cellHeight"])
            normal_crop = geometria_esperada["sourceCrop"]
            normal_width = int(normal_crop["right"]) - int(normal_crop["left"])
            expected_scale = int(geometria_esperada["cell"]["width"]) / normal_width
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            raise AssetInvalido(f"{animation_id}: geometria de cena inválida") from exc
        if crop_width < 1 or crop_height < 1 or cell_width < 1 or cell_height < 1:
            raise AssetInvalido(f"{animation_id}: dimensões de cena inválidas")
        # Um pixel de tolerância cobre os arredondamentos independentes de
        # largura/altura sem permitir que a personagem mude de escala.
        if abs(cell_width - crop_width * expected_scale) > 1 or abs(
            cell_height - crop_height * expected_scale
        ) > 1:
            raise AssetInvalido(f"{animation_id}: cena não preserva a escala compartilhada")
    else:
        raise AssetInvalido(f"{animation_id}: assetType desconhecido: {asset_type}")

    grid = manifesto["grid"]
    frame_count = int(manifesto["frameCount"])
    celulas_disponiveis = int(grid["columns"]) * int(grid["rows"])
    if frame_count < 1:
        raise AssetInvalido(f"{animation_id}: frameCount precisa ser >= 1")
    if frame_count > celulas_disponiveis:
        raise AssetInvalido(f"{animation_id}: atlas não possui células suficientes ({frame_count} > {celulas_disponiveis})")


def descobrir_ids() -> list[str]:
    """Só pastas com `animation.json` presente (contrato 7.1, ponto 2) -
    `preview.webp`/pastas sem manifesto são ignoradas silenciosamente."""
    if not RAIZ_ANIMACOES.is_dir():
        return []
    return sorted(p.parent.name for p in RAIZ_ANIMACOES.glob("*/animation.json"))


# --------------------------------------------------------------------------
# Camada 2: carregamento de pixels (Qt) - importado só aqui dentro pra quem
# só quer validar (scripts/validar_animacoes.py, testes de schema) nunca
# precisar de QApplication.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AnimationAsset:
    id: str
    frames: tuple  # tuple[QPixmap, ...] - pré-recortado 1x no load, nunca por tick
    frame_duration_ms: int
    effective_fps: float
    loop: bool
    cell_width: int
    cell_height: int
    pivot: tuple  # (x, y)
    asset_type: str = "character"

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @cached_property
    def margem_inferior_vazia_px(self) -> int:
        """Vão transparente (em px) entre o pixel visível mais baixo do
        clipe e o fundo da célula - `geometry.json` reserva a mesma
        margem/pivô pra TODOS os clipes evitar salto entre eles (seção
        3.1 do plano), mas isso não significa que o CONTEÚDO visível
        (personagem sentada, por exemplo) chegue até o fundo da célula -
        na prática ela para ~40px antes (medido, não um valor arbitrário
        digitado à mão). Quem precisa encaixar a personagem numa
        superfície real (barra de tarefas no Taskbar Sit, chão numa
        futura aterrissagem) soma esta margem, senão ela flutua acima da
        superfície como se houvesse uma parede invisível.

        Mede o MENOR vão entre os quadros amostrados (a pose que desce
        mais, ex.: perna mais baixa ao balançar) - ancorar por esse valor
        garante que ela nunca fica presa/cravada na superfície nos
        quadros onde desce menos, só flutua alguns px acima nesses.
        """
        menor_vao = self.cell_height
        passo = max(1, self.frame_count // 12)
        for indice in range(0, self.frame_count, passo):
            imagem = self.frames[indice].toImage()
            for linha in range(self.cell_height - 1, -1, -1):
                if any(
                    imagem.pixelColor(coluna, linha).alpha() > 16
                    for coluna in range(0, self.cell_width, 4)
                ):
                    menor_vao = min(menor_vao, self.cell_height - 1 - linha)
                    break
            else:
                continue  # quadro inteiramente transparente (não deveria existir) - ignora pro cálculo
        return menor_vao

    @cached_property
    def margem_superior_vazia_px(self) -> int:
        """Espelho de `margem_inferior_vazia_px` pro TOPO da célula -
        2026-09-02, achado ao vivo pelo usuário ("o halo n ta centralizado
        na gaia"): o halo (`window.py::paintEvent`) centralizava no meio
        do CANVAS/célula (`self.rect().center()`), não da silhueta visível
        - como ela não ocupa a célula inteira (nem verticalmente, nem
        lateralmente - ver `margem_esquerda/direita_vazia_px`), o halo
        saía deslocado do corpo dela de verdade."""
        menor_vao = self.cell_height
        passo = max(1, self.frame_count // 12)
        for indice in range(0, self.frame_count, passo):
            imagem = self.frames[indice].toImage()
            for linha in range(0, self.cell_height):
                if any(
                    imagem.pixelColor(coluna, linha).alpha() > 16
                    for coluna in range(0, self.cell_width, 4)
                ):
                    menor_vao = min(menor_vao, linha)
                    break
            else:
                continue
        return menor_vao

    @cached_property
    def margem_esquerda_vazia_px(self) -> int:
        """Igual `margem_inferior_vazia_px`, mas do lado ESQUERDO da célula
        (2026-09-02, Menu SAO - `menu_sao.py`) - a `janela.width()` do
        Mascot é a célula INTEIRA (canvas comum pra nunca saltar entre
        clipes, seção 3.1), não a silhueta visível; ancorar o menu pela
        borda da JANELA deixava um vão enorme e vazio entre o menu e ela
        de verdade (achado ao vivo, pedido do usuário: "pode aproximar os
        botões da GAIA")."""
        return self._medir_margem_lateral(da_esquerda=True)

    @cached_property
    def margem_direita_vazia_px(self) -> int:
        """Espelho de `margem_esquerda_vazia_px` pro lado direito."""
        return self._medir_margem_lateral(da_esquerda=False)

    def _medir_margem_lateral(self, da_esquerda: bool) -> int:
        menor_vao = self.cell_width
        passo = max(1, self.frame_count // 12)
        colunas = range(self.cell_width) if da_esquerda else range(self.cell_width - 1, -1, -1)
        for indice in range(0, self.frame_count, passo):
            imagem = self.frames[indice].toImage()
            for posicao, coluna in enumerate(colunas):
                if any(
                    imagem.pixelColor(coluna, linha).alpha() > 16
                    for linha in range(0, self.cell_height, 4)
                ):
                    menor_vao = min(menor_vao, posicao)
                    break
            else:
                continue
        return menor_vao

    @classmethod
    def carregar(cls, animation_id: str, geometria_esperada: dict) -> "AnimationAsset":
        """Caminho SÍNCRONO (bloqueia a thread de quem chamar) - usado só
        pro cold-start (`AnimationController.iniciar`/`forcar_estado`, sem
        "animação atual" nenhuma pra continuar mostrando enquanto carrega)
        e por quem só quer validar/inspecionar um asset fora do runtime
        (scripts, testes). O runtime em si (`AnimationController.
        solicitar_transicao`) usa o caminho ASSÍNCRONO (`AssetRepository.
        garantir_carregado_assincrono`, ver comentário de `_carregar_dados_brutos`
        abaixo sobre POR QUÊ isso existe)."""
        return cls.de_dados_brutos(_carregar_dados_brutos(animation_id, geometria_esperada))

    @classmethod
    def de_dados_brutos(cls, dados: "_DadosBrutosAsset") -> "AnimationAsset":
        """Converte `QImage` (thread-safe) pra `QPixmap` (só pode ser
        criado/manipulado na thread da GUI) - o ÚNICO passo do carregamento
        que precisa rodar na thread principal; tudo antes disso
        (`_carregar_dados_brutos`) é seguro de rodar numa thread de
        segundo plano."""
        from PySide6.QtGui import QPixmap

        frames = tuple(QPixmap.fromImage(imagem) for imagem in dados.frames)
        return cls(
            id=dados.id,
            frames=frames,
            frame_duration_ms=dados.frame_duration_ms,
            effective_fps=dados.effective_fps,
            loop=dados.loop,
            cell_width=dados.cell_width,
            cell_height=dados.cell_height,
            pivot=dados.pivot,
            asset_type=dados.asset_type,
        )


@dataclass(frozen=True)
class _DadosBrutosAsset:
    """Resultado do carregamento PESADO (I/O de disco + decodificação de
    imagem) - só `QImage` (nunca `QPixmap`, que não deve ser criado fora
    da thread da GUI em Qt), pra poder rodar numa `threading.Thread` de
    segundo plano sem risco (`AssetRepository.garantir_carregado_assincrono`).
    `AnimationAsset.de_dados_brutos` faz a conversão final (QPixmap) de
    volta na thread principal."""
    id: str
    frames: tuple  # tuple[QImage, ...]
    frame_duration_ms: int
    effective_fps: float
    loop: bool
    cell_width: int
    cell_height: int
    pivot: tuple
    asset_type: str


def _carregar_dados_brutos(animation_id: str, geometria_esperada: dict) -> _DadosBrutosAsset:
    """Toda a parte PESADA do carregamento (ler manifesto, validar, ler e
    decodificar o `.webp`, recortar os quadros) - medida ao vivo em
    200-900ms pras animações reais (`scripts/medir_desempenho.py`
    não mede isso, mas um teste manual direto sim - achado 2026-09-02:
    "trava as vezes quando termina uma animação"). Rodar isso na thread da
    UI trava a janela INTEIRA (mouse/arraste incluído) pelo tempo todo -
    por isso vira uma `threading.Thread` em segundo plano
    (`AssetRepository.garantir_carregado_assincrono`), com `QImage` (thread-
    safe) em vez de `QPixmap` (não é) até o quadro final."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage

    pasta = RAIZ_ANIMACOES / animation_id
    caminho_manifesto = pasta / "animation.json"
    if not caminho_manifesto.is_file():
        raise AssetAusente(f"{animation_id}: animation.json não encontrado")
    manifesto = json.loads(caminho_manifesto.read_text(encoding="utf-8"))
    validar_manifesto(animation_id, manifesto, geometria_esperada)

    caminho_textura = pasta / manifesto["texture"]
    if not caminho_textura.is_file():
        raise AssetAusente(f"{animation_id}: {manifesto['texture']} não encontrado")

    atlas = QImage(str(caminho_textura))
    if atlas.isNull():
        raise AssetInvalido(f"{animation_id}: não foi possível decodificar {caminho_textura.name}")

    grid = manifesto["grid"]
    colunas, cell_w, cell_h = int(grid["columns"]), int(grid["cellWidth"]), int(grid["cellHeight"])
    frame_count = int(manifesto["frameCount"])
    largura_esperada, altura_esperada = colunas * cell_w, int(grid["rows"]) * cell_h
    if atlas.width() != largura_esperada or atlas.height() != altura_esperada:
        raise AssetInvalido(
            f"{animation_id}: atlas mede {atlas.width()}x{atlas.height()}, "
            f"esperado {largura_esperada}x{altura_esperada}"
        )

    frames = tuple(
        atlas.copy(QRect((i % colunas) * cell_w, (i // colunas) * cell_h, cell_w, cell_h))
        for i in range(frame_count)
    )
    pivot = manifesto["pivot"]
    return _DadosBrutosAsset(
        id=animation_id,
        frames=frames,
        frame_duration_ms=max(1, int(manifesto["frameDurationMs"])),
        effective_fps=float(manifesto.get("effectiveFps", 1000 / int(manifesto["frameDurationMs"]))),
        loop=bool(manifesto["loop"]),
        cell_width=cell_w,
        cell_height=cell_h,
        pivot=(int(pivot["x"]), int(pivot["y"])),
        asset_type=str(manifesto.get("assetType", "character")),
    )


class AssetRepository(QObject):
    """Carrega sob demanda com cache limitado por ORÇAMENTO DE MEMÓRIA real
    (contrato 7.1, ponto 4 - corrigido 2026-09-01, ver comentário de
    `ORCAMENTO_MEMORIA_PADRAO_MB` acima) - LRU via `OrderedDict` (move pra
    o fim a cada acesso), mas despeja por MB decodificados de verdade, não
    por contagem de arquivos. `definir_protegidos` marca ids que NUNCA são
    despejados sob pressão de orçamento (a animação tocando agora + as que
    são transição válida a partir dela, ver `AnimationController.
    _carregar_e_tocar`) - `ANIMACAO_FALLBACK` está SEMPRE protegido nessa
    lista, é o fallback universal (plano, seção 10). Se só sobrar
    protegido e AINDA assim estourar o orçamento, aceita estourar - nunca
    despeja algo em uso só pra caber num número, correção sempre vence
    economia estrita de memória.

    Fallback seguro (contrato 7.1, ponto 5): se o carregamento falhar pra
    qualquer id que NÃO seja `ANIMACAO_FALLBACK`, cai pro fallback em vez
    de propagar - só deixa a exceção subir se o PRÓPRIO fallback também
    falhar (nada seguro sobra pra usar).

    **Carregamento assíncrono (2026-09-02, achado ao vivo: "trava as vezes
    quando termina uma animação")** - `obter()` é SÍNCRONO (bloqueia até
    ler/decodificar do disco, 200-900ms medido pras animações reais) e só
    deve ser usado no cold-start (`AnimationController.iniciar`, sem
    "animação atual" nenhuma pra continuar mostrando enquanto carrega).
    O runtime usa `garantir_carregado_assincrono` - carrega numa
    `threading.Thread` (usando `QImage`, thread-safe, nunca `QPixmap`
    fora da thread da GUI - ver `AnimationAsset.de_dados_brutos`) e
    entrega o resultado de volta na thread principal via `Signal` (Qt já
    faz esse marshalling sozinho quando emitido de outra thread, mesmo
    padrão de `MascotSupervisor.enviar_para_mascot`). Enquanto carrega,
    quem pediu continua mostrando o que já está na tela - literalmente só
    não chama o callback ainda."""

    _carregamento_concluido = Signal(str, object, object)  # id pedido, _DadosBrutosAsset|None, Exception|None

    def __init__(self, orcamento_mb: float = ORCAMENTO_MEMORIA_PADRAO_MB, parent: QObject | None = None):
        super().__init__(parent)
        self._orcamento_bytes = orcamento_mb * 1024 * 1024
        self._cache: OrderedDict[str, AnimationAsset] = OrderedDict()
        self._custo_bytes: dict[str, int] = {}
        self._protegidos: frozenset[str] = frozenset({ANIMACAO_FALLBACK})
        self._pinados: frozenset[str] = frozenset()
        self._geometria = carregar_geometria_esperada()
        self._carregando: dict[str, dict] = {}  # id -> {"prioridade": bool, "callbacks": [...]}
        self._carregamento_concluido.connect(self._ao_carregamento_concluido)
        # 🔥 Dois semáforos separados (ver comentário de `MAX_THREADS_PRELOAD`
        # acima) - a pedida de verdade (`prioridade=True`, padrão) nunca
        # espera atrás de pré-carregamento (`prioridade=False`). Threads
        # sempre `daemon=True` (nunca atrasam o processo encerrar).
        self._semaforo_principal = threading.Semaphore(MAX_THREADS_CARREGAMENTO)
        self._semaforo_preload = threading.Semaphore(MAX_THREADS_PRELOAD)

    def ids_disponiveis(self) -> list[str]:
        return descobrir_ids()

    def definir_protegidos(self, ids) -> None:
        self._protegidos = frozenset(ids) | {ANIMACAO_FALLBACK}

    def definir_pinados(self, ids) -> None:
        """Conjunto PERMANENTE de proteção (2026-09-02) - diferente de
        `definir_protegidos` (transiente, reescrito a cada transição), o
        que entra aqui nunca é despejado enquanto o processo viver, mesmo
        que o estado atual não tenha nada a ver com ele. `AnimationController`
        chama isso 1x na construção com os clipes de ENTRADA de movimento/
        arraste a partir do idle - ver comentário de `ORCAMENTO_MEMORIA_PADRAO_MB`
        acima pro raciocínio completo (a folga de 3,7-4s de cada clipe de
        entrada é o buffer que deixa o resto do fluxo carregar em segundo
        plano sem travar)."""
        self._pinados = frozenset(ids)

    def esta_em_cache(self, animation_id: str) -> bool:
        return animation_id in self._cache

    def obter(self, animation_id: str) -> AnimationAsset:
        """Síncrono - bloqueia a thread de quem chamar se não estiver em
        cache (200-900ms medido pras animações reais). Só pro cold-start
        (ver docstring da classe) - o runtime usa `garantir_carregado_assincrono`."""
        if animation_id in self._cache:
            self._cache.move_to_end(animation_id)
            return self._cache[animation_id]
        try:
            asset = AnimationAsset.carregar(animation_id, self._geometria)
        except (AssetAusente, AssetInvalido):
            if animation_id == ANIMACAO_FALLBACK:
                raise  # o próprio fallback falhou - nada seguro sobra, propaga de vez
            return self.obter(ANIMACAO_FALLBACK)
        self._inserir_no_cache(asset)
        return asset

    def garantir_carregado_assincrono(self, animation_id: str, ao_concluir, *, prioridade: bool = True) -> None:
        """`ao_concluir(asset: AnimationAsset)` roda IMEDIATAMENTE (mesma
        pilha de chamada) se `animation_id` já estiver em cache; senão,
        dispara (ou reaproveita, se já em andamento) um carregamento em
        segundo plano e chama `ao_concluir` só quando terminar - quem
        pediu não trava esperando, continua mostrando o que já está na
        tela até lá. Múltiplos pedidos pro MESMO id enquanto ainda carrega
        todos são atendidos quando terminar (nunca dispara uma 2ª leitura
        de disco pro mesmo arquivo).

        `prioridade=False` (pré-carregamento especulativo, ver
        `AnimationController._carregar_e_tocar`) usa um SEMÁFORO SEPARADO
        da pedida de verdade (`prioridade=True`, padrão) - sem isso, um
        pré-carregamento enfileirado antes podia atrasar a animação
        REALMENTE pedida agora (achado ao vivo, teste automatizado:
        "arraste real inicia a transição para agarrada" ficou instável).

        Se o MESMO id já estiver pendente só como pré-carregamento
        (`prioridade=False`) e um pedido de PRIORIDADE chegar depois, não
        dá pra "promover" a thread já em andamento (pode estar presa
        atrás de outros pré-carregamentos no semáforo de baixa
        prioridade) - dispara uma 2ª leitura, redundante mas rara, na
        fila de prioridade alta, em vez de deixar o pedido urgente
        esperar atrás de trabalho de baixa prioridade (mesma classe de
        bug do parágrafo acima, achada de novo numa colisão entre seções
        diferentes do teste automatizado)."""
        if animation_id in self._cache:
            self._cache.move_to_end(animation_id)
            ao_concluir(self._cache[animation_id])
            return
        pendente = self._carregando.get(animation_id)
        if pendente is not None and (pendente["prioridade"] or not prioridade):
            pendente["callbacks"].append(ao_concluir)
            return
        callbacks = list(pendente["callbacks"]) if pendente else []
        callbacks.append(ao_concluir)
        self._carregando[animation_id] = {"prioridade": prioridade, "callbacks": callbacks}
        semaforo = self._semaforo_principal if prioridade else self._semaforo_preload
        threading.Thread(target=self._carregar_em_thread, args=(animation_id, semaforo), daemon=True).start()

    def _carregar_em_thread(self, animation_id: str, semaforo: threading.Semaphore) -> None:
        """Roda numa `threading.Thread` de segundo plano (SEMPRE `daemon=True`
        - nunca atrasa o processo encerrar, mesmo com um backlog grande de
        pré-carregamento pendente). `semaforo.acquire()` bloqueado NÃO
        disputa o GIL enquanto espera vez (`MAX_THREADS_CARREGAMENTO`/
        `MAX_THREADS_PRELOAD` de propósito baixo - ver comentário nas
        constantes) - só código thread-safe DEPOIS de adquirir
        (`_carregar_dados_brutos`, `QImage`), NUNCA `QPixmap`. `emit()` de
        outra thread é seguro (Qt marshalla pra thread dona do objeto, a
        principal, automaticamente) - a checagem de `RuntimeError` cobre
        só o caso raro do processo estar encerrando BEM no meio
        (`AssetRepository` já destruído do lado C++) - nunca deveria
        propagar e derrubar a worker thread por causa disso."""
        with semaforo:
            try:
                dados = _carregar_dados_brutos(animation_id, self._geometria)
                resultado = (animation_id, dados, None)
            except (AssetAusente, AssetInvalido) as e:
                resultado = (animation_id, None, e)
        try:
            self._carregamento_concluido.emit(*resultado)
        except RuntimeError:
            pass  # processo encerrando - AssetRepository já foi destruído do lado Qt

    def _ao_carregamento_concluido(self, animation_id: str, dados, erro) -> None:
        """Já roda na thread principal (slot conectado a um `Signal`
        cruzando thread - Qt entrega isso na thread dona do `QObject`).
        Se uma 2ª leitura redundante (ver `garantir_carregado_assincrono`)
        já tiver sido resolvida pela 1ª, `self._carregando` não tem mais
        `animation_id` (já foi retirado) - a straggler completa aqui sem
        efeito (resultado descartado, sem crash)."""
        pendente = self._carregando.pop(animation_id, None)
        callbacks = pendente["callbacks"] if pendente else []
        if erro is not None:
            if animation_id == ANIMACAO_FALLBACK:
                logger.error("Mascot: o próprio fallback (%s) falhou ao carregar: %s", ANIMACAO_FALLBACK, erro)
                return  # nada seguro sobra - callbacks nunca são chamados, quem espera fica no que já tinha
            self.garantir_carregado_assincrono(ANIMACAO_FALLBACK, lambda asset: [cb(asset) for cb in callbacks])
            return
        asset = AnimationAsset.de_dados_brutos(dados)
        self._inserir_no_cache(asset)
        for callback in callbacks:
            callback(asset)

    def _inserir_no_cache(self, asset: AnimationAsset) -> None:
        self._cache[asset.id] = asset
        self._custo_bytes[asset.id] = sum(f.width() * f.height() for f in asset.frames) * BYTES_POR_PIXEL_RGBA
        self._cache.move_to_end(asset.id)
        # `protegido_extra=asset.id` - o asset que ACABOU de ser inserido
        # nunca é despejado por essa mesma chamada, mesmo que quem chamou
        # não tenha chamado `definir_protegidos` antes (defesa extra,
        # além do fluxo normal de `AnimationController._carregar_e_tocar`
        # já proteger o id pedido de propósito) - não faz sentido devolver
        # um asset e já despejar ele no mesmo instante.
        self._liberar_espaco_se_preciso(protegido_extra=asset.id)

    def _liberar_espaco_se_preciso(self, protegido_extra: str | None = None) -> None:
        protegidos = self._protegidos | self._pinados | ({protegido_extra} if protegido_extra else frozenset())
        while self._memoria_total_bytes() > self._orcamento_bytes:
            candidato = next((id_ for id_ in self._cache if id_ not in protegidos), None)
            if candidato is None:
                break  # só sobrou protegido - aceita estourar o orçamento (correção > economia)
            del self._cache[candidato]
            del self._custo_bytes[candidato]

    def _memoria_total_bytes(self) -> int:
        return sum(self._custo_bytes.values())

    def memoria_atual_mb(self) -> float:
        return self._memoria_total_bytes() / (1024 * 1024)

    def tamanho_cache_atual(self) -> int:
        return len(self._cache)
