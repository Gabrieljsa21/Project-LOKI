"""Script avulso pra validar a Fase 0 do LOKI/Mascot (`AssetRepository`,
`state_catalog`, `AnimationController`) - sem framework de teste (mesmo
padrão de testes/testar_*.py), roda cada caso e imprime PASS/FAIL.

Critério de aceite (ver `docs/ARQUITETURA.md`, "Contrato de asset"):
reproduz os assets finais diretamente (não usa fontes de `E:\\Downloads`
nem `preview.webp`), mantém pivô, cai em fallback sem crash pra asset
ausente/inválido/incompatível, e transições respeitam o grafo de estados.

Roda offscreen (sem janela de verdade) - Fase 1 (janela/overlay) ainda não
existe, este teste só cobre o contrato de asset/estado.
"""
import os
import sys
import tempfile
import json
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz do projeto

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

import mascot.asset_repository as asset_repository
import mascot.state_catalog as state_catalog
from mascot.animation_controller import AnimationController
from mascot.asset_repository import AssetInvalido, AssetRepository

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


def bombear_ate(condicao, timeout_s=5):
    """Bombeia o loop do Qt até `condicao()` ser verdadeira ou o timeout
    passar - necessário desde 2026-09-02 (carregamento assíncrono do
    `AnimationController`/`AssetRepository`, ver `asset_repository.py`):
    `solicitar_transicao`/`_avancar` não aplicam mais o novo asset na
    MESMA chamada quando ele não está em cache (thread de segundo plano +
    `Signal` cruzando thread, precisa do loop do Qt rodando pra entregar)."""
    inicio = time.monotonic()
    while not condicao() and time.monotonic() - inicio < timeout_s:
        app.processEvents()
        time.sleep(0.01)
    return condicao()


def transicionar(controller, animation_id, **kwargs):
    """`solicitar_transicao` + espera SÓ o pedido em si (não o
    pré-carregamento especulativo dos candidatos, que roda numa fila
    separada de prioridade mais baixa - `AssetRepository.
    garantir_carregado_assincrono(..., prioridade=False)` - e pode
    demorar bem mais que o timeout padrão daqui sem que isso signifique
    que o pedido de verdade ainda não terminou)."""
    aceito = controller.solicitar_transicao(animation_id, **kwargs)
    bombear_ate(lambda: animation_id not in repositorio_real._carregando)
    return aceito


def avancar_ate_estavel(controller, n):
    """`n` ticks de `_avancar()` (simula o fim de um clipe sem depender de
    QTimer/event loop de verdade), esperando o carregamento assíncrono
    (se `_avancar` encadear pra outra animação no meio/fim do loop)
    terminar antes de seguir pro próximo tick - senão um `_avancar()`
    chamado ENQUANTO o anterior ainda carrega em segundo plano reentra no
    `_entrada`/`_asset` antigos (ainda não trocados). Espera só o que
    `_avancar` pode ter encadeado (`controller._id_solicitado_mais_recente`),
    nunca o pré-carregamento especulativo (fila separada, mais lenta)."""
    for _ in range(n):
        controller._avancar()
        bombear_ate(lambda: controller._id_solicitado_mais_recente not in repositorio_real._carregando)


# ----------------------------------------------------------------------
# validar_manifesto pura (sem Qt, sem disco) - regras de schema/geometria.
# ----------------------------------------------------------------------
geometria_exemplo = {
    "sourceCanvas": {"width": 100, "height": 100},
    "sourceCrop": {"left": 0, "top": 0, "right": 100, "bottom": 100},
    "cell": {"width": 10, "height": 10},
    "pivot": {"x": 5, "y": 10},
}
manifesto_base = {
    "id": "exemplo",
    "texture": "spritesheet.png",
    "frameCount": 2,
    "frameDurationMs": 100,
    "loop": True,
    "grid": {"columns": 2, "rows": 1, "cellWidth": 10, "cellHeight": 10},
    "pivot": {"x": 5, "y": 10},
    "sourceCanvas": geometria_exemplo["sourceCanvas"],
    "sourceCrop": geometria_exemplo["sourceCrop"],
}

try:
    asset_repository.validar_manifesto("exemplo", manifesto_base, geometria_exemplo)
    checar("manifesto coerente com a geometria -> não levanta nada", True)
except AssetInvalido as exc:
    checar("manifesto coerente com a geometria -> não levanta nada", False, exc)

manifesto_frames_demais = dict(manifesto_base, frameCount=5)  # grade só tem 2 células (2x1)
try:
    asset_repository.validar_manifesto("frames_demais", manifesto_frames_demais, geometria_exemplo)
    checar("frameCount maior que a grade disponível -> AssetInvalido", False)
except AssetInvalido:
    checar("frameCount maior que a grade disponível -> AssetInvalido", True)

manifesto_pivot_diferente = dict(manifesto_base, pivot={"x": 999, "y": 999})
try:
    asset_repository.validar_manifesto("pivot_diferente", manifesto_pivot_diferente, geometria_exemplo)
    checar("pivô diferente de geometry.json -> AssetInvalido", False)
except AssetInvalido:
    checar("pivô diferente de geometry.json -> AssetInvalido", True)


# ----------------------------------------------------------------------
# Repositório real - todos os assets finais que já existem em
# assets/galateia/animations/. Nada de E:\Downloads nem preview.webp.
# ----------------------------------------------------------------------
config_importacao = json.loads(
    (Path(__file__).parents[1] / "data" / "animacoes_galateia.json").read_text(encoding="utf-8")
)
IDS_ESPERADOS = [item["id"] for item in config_importacao["animations"]]
CONFIG_POR_ID = {item["id"]: item for item in config_importacao["animations"]}
geometria_real = asset_repository.carregar_geometria_esperada()
pivot_esperado = (geometria_real["pivot"]["x"], geometria_real["pivot"]["y"])
celula_esperada = (geometria_real["cell"]["width"], geometria_real["cell"]["height"])

ids_reais = asset_repository.descobrir_ids()
checar(
    "descobrir_ids encontra exatamente os assets finais existentes",
    sorted(ids_reais) == sorted(IDS_ESPERADOS),
    ids_reais,
)
checar(
    "catálogo de estados cobre todos os assets finais",
    set(state_catalog.CATALOGO) == set(ids_reais),
    sorted(set(ids_reais) ^ set(state_catalog.CATALOGO)),
)

repositorio_real = AssetRepository()
for animation_id in IDS_ESPERADOS:
    asset = repositorio_real.obter(animation_id)
    manifesto = json.loads(
        (asset_repository.RAIZ_ANIMACOES / animation_id / "animation.json").read_text(encoding="utf-8")
    )
    checar(f"{animation_id}: carrega sem cair em fallback", asset.id == animation_id, asset.id)
    checar(
        f"{animation_id}: frameCount bate com o manifesto real",
        asset.frame_count == manifesto["frameCount"],
        asset.frame_count,
    )
    if CONFIG_POR_ID[animation_id].get("assetType", "character") == "scene":
        checar(f"{animation_id}: carrega como cena", asset.asset_type == "scene", asset.asset_type)
        checar(
            f"{animation_id}: pode usar célula maior que a personagem",
            asset.cell_width > celula_esperada[0] or asset.cell_height > celula_esperada[1],
            (asset.cell_width, asset.cell_height),
        )
    else:
        checar(f"{animation_id}: mantém o pivô compartilhado", asset.pivot == pivot_esperado, asset.pivot)
        checar(
            f"{animation_id}: mantém a célula compartilhada",
            (asset.cell_width, asset.cell_height) == celula_esperada,
            (asset.cell_width, asset.cell_height),
        )

checar(
    "id desconhecido cai no fallback flutuando_idle sem crashar",
    repositorio_real.obter("essa_animacao_nao_existe_de_verdade").id == asset_repository.ANIMACAO_FALLBACK,
)

# ----------------------------------------------------------------------
# Orçamento de memória (2026-09-01 - substitui o antigo "N arquivos", que
# não sabia que uma animação de 120 quadros pesa 15x mais que uma de 8).
# ----------------------------------------------------------------------
repositorio_para_medir = AssetRepository(orcamento_mb=10_000)  # orçamento gigante só pra medir o custo real
repositorio_para_medir.obter("flutuando_idle")
custo_idle_mb = repositorio_para_medir.memoria_atual_mb()
checar("memoria_atual_mb reporta um custo real (> 0) depois de carregar 1 asset", custo_idle_mb > 0, custo_idle_mb)

repositorio_orcamento = AssetRepository(orcamento_mb=custo_idle_mb * 1.2)
repositorio_orcamento.obter("flutuando_idle")  # ANIMACAO_FALLBACK - sempre protegido
repositorio_orcamento.obter("sentada_pensando")  # não protegido - candidato a despejo
repositorio_orcamento.obter("sentada_deitando")  # deve expulsar sentada_pensando (mais antigo não protegido)
checar(
    "orçamento de memória NUNCA despeja o fallback universal (flutuando_idle)",
    "flutuando_idle" in repositorio_orcamento._cache,
    list(repositorio_orcamento._cache),
)
checar(
    "orçamento de memória despeja o mais antigo NÃO protegido sob pressão",
    "sentada_pensando" not in repositorio_orcamento._cache and "sentada_deitando" in repositorio_orcamento._cache,
    list(repositorio_orcamento._cache),
)

repositorio_orcamento.definir_protegidos({"sentada_deitando"})
repositorio_orcamento.obter("sentada_espreguicando")
# `sentada_espreguicando` só ficou de fora do despejo ACIMA por ser o
# próprio asset recém-carregado daquela chamada (proteção automática,
# sempre vale só pra chamada em si) - uma 2ª carga depois confirma que
# ela NÃO continua protegida (só sentada_deitando, protegido de propósito
# via `definir_protegidos`, sobrevive).
repositorio_orcamento.obter("sentada_bocejando")
checar(
    "definir_protegidos protege um id explícito de ser despejado sob pressão contínua",
    "sentada_deitando" in repositorio_orcamento._cache and "sentada_espreguicando" not in repositorio_orcamento._cache,
    list(repositorio_orcamento._cache),
)

# ----------------------------------------------------------------------
# Pinados permanentes (2026-09-02) - proposta do usuário: fixar só os
# clipes de ENTRADA de movimento/arraste a partir do idle (folga de
# 3,7-4s de cada um serve de buffer pro resto do fluxo carregar em
# segundo plano). Diferente de `definir_protegidos` (transiente, muda a
# cada transição), `definir_pinados` nunca é sobrescrito pelo controller
# durante o uso normal - ver `AnimationController._computar_pinados`.
# ----------------------------------------------------------------------
repositorio_pinado = AssetRepository(orcamento_mb=custo_idle_mb * 1.2)
repositorio_pinado.definir_pinados({"sentada_deitando"})
repositorio_pinado.obter("sentada_deitando")
repositorio_pinado.obter("sentada_pensando")  # não protegido nem pinado - candidato a despejo
repositorio_pinado.obter("sentada_bocejando")  # deve expulsar sentada_pensando, nunca sentada_deitando (pinado)
checar(
    "definir_pinados protege permanentemente mesmo sem definir_protegidos ativo",
    "sentada_deitando" in repositorio_pinado._cache and "sentada_pensando" not in repositorio_pinado._cache,
    list(repositorio_pinado._cache),
)
repositorio_pinado.definir_protegidos(set())  # limpa a proteção transiente de propósito
repositorio_pinado.obter("sentada_espreguicando")
repositorio_pinado.obter("sentada_acenando")
checar(
    "definir_pinados sobrevive mesmo depois de definir_protegidos esvaziar a proteção transiente",
    "sentada_deitando" in repositorio_pinado._cache,
    list(repositorio_pinado._cache),
)

controller_pinados = AnimationController(repositorio=repositorio_real)
# 2026-09-04, achado ao vivo: "ela trava ate p sentar. E no inicio do
# projeto... ela rodava lisa" - só a TRANSIÇÃO de entrada (ex.:
# `flutuando_para_sentada`) era pinada; o loop de repouso que toca DEPOIS
# dela (`sentada_balancando-pernas`/`sentada_pensando`, e as 3 variantes de
# `leque`) não era, então podia ser despejado e recarregar (travando) cada
# vez. `flutuando_para_leque` também entrou (mesma categoria imediata de
# movimento/arraste/sentar, só faltava por descuido).
pinados_esperados = {
    "flutuando_direita_iniciar", "flutuando_esquerda_iniciar",
    "flutuando_subida_iniciar", "flutuando_descida_iniciar",
    "flutuando_superior-direita_iniciar", "flutuando_superior-esquerda_iniciar",
    "flutuando_inferior-direita_iniciar", "flutuando_inferior-esquerda_iniciar",
    "flutuando_para_agarrada", "flutuando_para_sentada", "flutuando_para_leque",
    "flutuando_idle", "sentada_balancando-pernas", "sentada_pensando",
    "leque_ironica_loop", "leque_esnobe_loop", "leque_sorriso_loop",
}
checar(
    "AnimationController fixa os clipes de entrada de movimento/arraste/leque MAIS os loops de repouso (tag 'idle')",
    controller_pinados._computar_pinados() == frozenset(pinados_esperados),
    sorted(controller_pinados._computar_pinados()),
)
checar(
    "AnimationController exclui ações/cenas raras do idle (tag 'action', não 'transition') dos pinados",
    not (pinados_esperados & {"flutuando_perdida", "flutuando_cortina-abrindo", "transformacao_inicio"}),
)
checar(
    "AnimationController já religa o repositório com definir_pinados na construção",
    repositorio_real._pinados == frozenset(pinados_esperados),
    sorted(repositorio_real._pinados),
)
bombear_ate(
    lambda: all(repositorio_real.esta_em_cache(p) for p in pinados_esperados),
    # 15s (2026-09-04, achado ao vivo: "ela trava ate p sentar... antes ela
    # rodava lisa") - com os loops de repouso de sentada/leque agora
    # também pinados (achado acima), a fila de pré-carregamento na largada
    # cresceu e MAX_THREADS_PRELOAD é 1 (estritamente serial) - medido ao
    # vivo: ~11s pra esquentar tudo. Ainda em segundo plano, não bloqueia
    # nada visível - só o teste precisa de mais paciência que o padrão de 5s.
    timeout_s=15,
)
checar(
    "todos os pinados esquentam no cache pelo preload de cold-start (sem esperar uma transição real)",
    all(repositorio_real.esta_em_cache(p) for p in pinados_esperados),
    [p for p in pinados_esperados if not repositorio_real.esta_em_cache(p)],
)


# ----------------------------------------------------------------------
# Asset ausente/inválido num diretório ISOLADO (nunca nos assets reais) -
# fallback precisa funcionar mesmo quando o próprio fallback (flutuando_idle)
# é servido por um repositório com raiz diferente.
# ----------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    raiz_tmp = Path(tmp)
    (raiz_tmp / "geometry.json").write_text(
        __import__("json").dumps(geometria_exemplo), encoding="utf-8"
    )

    def _criar_pasta_animacao(nome, manifesto, com_textura=True):
        pasta = raiz_tmp / nome
        pasta.mkdir()
        (pasta / "animation.json").write_text(__import__("json").dumps(manifesto), encoding="utf-8")
        if com_textura:
            pixmap = QPixmap(20, 10)
            pixmap.fill()
            pixmap.save(str(pasta / "spritesheet.png"))

    _criar_pasta_animacao("flutuando_idle", manifesto_base)
    _criar_pasta_animacao("quebrada_sem_textura", manifesto_base, com_textura=False)
    _criar_pasta_animacao("quebrada_geometria_incompativel", manifesto_pivot_diferente)

    raiz_original, geometria_original = asset_repository.RAIZ_ANIMACOES, asset_repository.ARQUIVO_GEOMETRIA
    try:
        asset_repository.RAIZ_ANIMACOES = raiz_tmp
        asset_repository.ARQUIVO_GEOMETRIA = raiz_tmp / "geometry.json"
        repositorio_isolado = AssetRepository()

        asset_ausente = repositorio_isolado.obter("quebrada_sem_textura")
        checar(
            "asset com textura ausente cai no fallback local sem crashar",
            asset_ausente.id == "flutuando_idle",
            asset_ausente.id,
        )

        asset_invalido = repositorio_isolado.obter("quebrada_geometria_incompativel")
        checar(
            "asset com geometria incompatível cai no fallback local sem crashar",
            asset_invalido.id == "flutuando_idle",
            asset_invalido.id,
        )
    finally:
        asset_repository.RAIZ_ANIMACOES = raiz_original
        asset_repository.ARQUIVO_GEOMETRIA = geometria_original


# ----------------------------------------------------------------------
# AnimationController - grafo de estados (state_catalog) real.
# ----------------------------------------------------------------------
controller = AnimationController(repositorio=repositorio_real)
checar("controller inicia em flutuando_idle", controller.animacao_atual == "flutuando_idle", controller.animacao_atual)
checar("flutuando_idle (loop) já entra no estado 'flutuando'", controller.estado_logico == "flutuando", controller.estado_logico)
checar("controller mantém o pivô do asset carregado", controller.pivot_atual == pivot_esperado, controller.pivot_atual)
checar("controller expõe um quadro (QPixmap) não nulo", controller.quadro_atual is not None and not controller.quadro_atual.isNull())

aceitou = transicionar(controller, "flutuando_para_sentada")
checar("transição válida (flutuando -> sentada) é aceita", aceitou and controller.animacao_atual == "flutuando_para_sentada", controller.animacao_atual)

rejeitada_nao_interrompivel = transicionar(controller, "sentada_balancando-pernas")
checar(
    "transição não-interrompível recusa pedido concorrente no meio do clipe",
    rejeitada_nao_interrompivel is False and controller.animacao_atual == "flutuando_para_sentada",
    controller.animacao_atual,
)

avancar_ate_estavel(controller, repositorio_real.obter("flutuando_para_sentada").frame_count)
checar(
    "transição não-loop no fim muda o estado lógico pro destino",
    controller.estado_logico == "sentada",
    controller.estado_logico,
)
checar(
    "transição não-loop no fim cai no fallback do catálogo (idle sentado)",
    controller.animacao_atual == "sentada_balancando-pernas",
    controller.animacao_atual,
)

# ----------------------------------------------------------------------
# Ação (mesmo estado de origem/destino) precisa voltar pro ÚLTIMO LOOP
# de verdade (`sentada_pensando`), não pro fallback fixo do catálogo
# (`sentada_balancando-pernas`) - controller já está nesse loop pelo bloco anterior.
# ----------------------------------------------------------------------
aceitou_pensando = transicionar(controller, "sentada_pensando")
checar("solicita sentada_pensando (segundo loop sentado) a partir do idle", aceitou_pensando and controller.animacao_atual == "sentada_pensando", controller.animacao_atual)

aceitou_acao = transicionar(controller, "sentada_espreguicando")
checar("ação (espreguiçar) é aceita a partir de sentada_pensando", aceitou_acao and controller.animacao_atual == "sentada_espreguicando", controller.animacao_atual)

avancar_ate_estavel(controller, repositorio_real.obter("sentada_espreguicando").frame_count)
checar(
    "ação termina voltando pro loop anterior (sentada_pensando), não pro fallback fixo",
    controller.animacao_atual == "sentada_pensando",
    controller.animacao_atual,
)

controller2 = AnimationController(repositorio=repositorio_real)
rejeitada_fora_do_grafo = transicionar(controller2, "sentada_deitando")  # exige estado "sentada", controller2 está em "flutuando"
checar(
    "transição fora do grafo (estado_origem incompatível) é rejeitada",
    rejeitada_fora_do_grafo is False and controller2.animacao_atual == "flutuando_idle",
    controller2.animacao_atual,
)

rejeitada_id_desconhecido = transicionar(controller2, "essa_animacao_nao_existe_no_catalogo")
checar("transição pra id fora do catálogo é rejeitada sem crash", rejeitada_id_desconhecido is False)

controller_cena = AnimationController(repositorio=repositorio_real)
aceitou_cena = transicionar(controller_cena, "flutuando_cortina-abrindo")
checar(
    "cena ampla é aceita a partir do idle flutuando",
    aceitou_cena and controller_cena.asset_atual.asset_type == "scene",
    controller_cena.animacao_atual,
)
avancar_ate_estavel(controller_cena, repositorio_real.obter("flutuando_cortina-abrindo").frame_count)
checar(
    "cena ampla termina retornando ao idle normal",
    controller_cena.animacao_atual == "flutuando_idle"
    and controller_cena.asset_atual.asset_type == "character",
    controller_cena.animacao_atual,
)

# 🔥 Achado ao vivo (2026-09-02, "ela ta travando na animação de trazendo o
# chaos") - `flutuando_para_trazendo-caos`/`trazendo-caos_para_flutuando`
# foram importadas com `fallback: null` (`data/animacoes_galateia.json`),
# tratadas então como "pose terminal" (mesma regra de dormir/deitada,
# `AnimationController._avancar`) - fica parada no último quadro até uma
# transição explicitamente compatível, mas NENHUMA existe a partir do
# destino final (`flutuando-com-caos`), travando pra sempre (diferente do
# sono, que tem `_acordar` pra escapar). Corrigido preenchendo `fallback`
# nas duas, igual o par da Substituição Ninja já fazia certo. Único jeito
# de escapar SEM esse fix seria arrastar de verdade (`forcar_estado`
# ignora o grafo).
controller_caos = AnimationController(repositorio=repositorio_real)
aceitou_caos = transicionar(controller_caos, "flutuando_para_trazendo-caos")
checar("'trazendo o caos' é aceita a partir do idle flutuando", aceitou_caos, controller_caos.animacao_atual)
avancar_ate_estavel(
    controller_caos,
    repositorio_real.obter("flutuando_para_trazendo-caos").frame_count
    + repositorio_real.obter("trazendo-caos_para_flutuando").frame_count,
)
checar(
    "'trazendo o caos' encadeia sozinha (fallback) até flutuando_idle, nunca mais trava",
    controller_caos.animacao_atual == "flutuando_idle" and controller_caos.estado_logico == "flutuando",
    (controller_caos.animacao_atual, controller_caos.estado_logico),
)

# Mesmo bug do caos acima, achado 2026-09-06 ("A animação de brinde esta
# travando qnd clico pelas ações") - `flutuando_para_brinde` também tinha
# `fallback: null` (o fix do caos, 2026-09-02, não cobriu esta - ficou
# esquecida com o mesmo problema). Corrigido igual: `fallback:
# "brinde_para_flutuando"` em `data/animacoes_galateia.json`.
controller_brinde = AnimationController(repositorio=repositorio_real)
aceitou_brinde = transicionar(controller_brinde, "flutuando_para_brinde")
checar("'brinde' é aceita a partir do idle flutuando", aceitou_brinde, controller_brinde.animacao_atual)
avancar_ate_estavel(
    controller_brinde,
    repositorio_real.obter("flutuando_para_brinde").frame_count
    + repositorio_real.obter("brinde_para_flutuando").frame_count,
)
checar(
    "'brinde' encadeia sozinha (fallback) até flutuando_idle, nunca mais trava",
    controller_brinde.animacao_atual == "flutuando_idle" and controller_brinde.estado_logico == "flutuando",
    (controller_brinde.animacao_atual, controller_brinde.estado_logico),
)

# "Ficar Esnobe"/"Ficar Neutra" (leque) - achado 2026-09-06, usuário com o
# print da roda: "o ficar esnobe parece q esta sem o final tbm" -> "a
# animação na posicao 29 - Ficar Neutra, parece ser o final da 32" -
# `leque_neutra_para_esnobe` (destino "leque", igual sua própria origem)
# era tratada como AÇÃO simples pelo `AnimationController._avancar`
# (`estado_origem == estado_destino`), que SEMPRE volta pro último loop
# tocando antes, ignorando qualquer fallback declarado - `leque_esnobe_
# para_neutra` (a pose de conexão certa, confirmada visualmente batendo
# frame a frame com o fim de "Ficar Esnobe") nunca era alcançada
# automaticamente. Corrigido dando um DESTINO PRÓPRIO ("leque-esnobe") a
# "Ficar Esnobe" - deixa de ser "ação" (destino != origem), respeitando o
# fallback de verdade; o antigo `leque_esnobe_para_neutra` renomeado pra
# `leque-esnobe_para_neutra` (origem "leque-esnobe", mesma convenção de
# nomes hifenizados pra estados compostos) fecha a volta pro "leque"
# normal, terminando em `leque_esnobe_loop`.
controller_leque = AnimationController(repositorio=repositorio_real)
controller_leque.forcar_estado("leque_ironica_loop")  # entra direto num humor - a entrada em si já é testada em testar_mascot_behaviors.py
aceitou_esnobe = transicionar(controller_leque, "leque_neutra_para_esnobe")
checar("'Ficar Esnobe' é aceita a partir de um humor do leque", aceitou_esnobe, controller_leque.animacao_atual)
avancar_ate_estavel(controller_leque, repositorio_real.obter("leque_neutra_para_esnobe").frame_count)
checar(
    "'Ficar Esnobe' encadeia sozinha pra 'Ficar Neutra' (não pula pro loop anterior)",
    controller_leque.animacao_atual == "leque-esnobe_para_neutra" and controller_leque.estado_logico == "leque-esnobe",
    (controller_leque.animacao_atual, controller_leque.estado_logico),
)
avancar_ate_estavel(controller_leque, repositorio_real.obter("leque-esnobe_para_neutra").frame_count)
checar(
    "'Ficar Neutra' termina no loop esnobe, de volta ao estado 'leque'",
    controller_leque.animacao_atual == "leque_esnobe_loop" and controller_leque.estado_logico == "leque",
    (controller_leque.animacao_atual, controller_leque.estado_logico),
)


# ----------------------------------------------------------------------
# Fluxo direcional completo: iniciar -> loop -> parar -> idle.
# ----------------------------------------------------------------------
controller_movimento = AnimationController(repositorio=repositorio_real)
checar(
    "movimento aceita o início superior-direita a partir do idle",
    transicionar(controller_movimento, "flutuando_superior-direita_iniciar"),
)
avancar_ate_estavel(controller_movimento, repositorio_real.obter("flutuando_superior-direita_iniciar").frame_count)
checar(
    "fim de iniciar entra no loop da mesma direção",
    controller_movimento.animacao_atual == "flutuando_superior-direita_loop",
    controller_movimento.animacao_atual,
)
checar(
    "loop direcional aceita a parada correspondente",
    transicionar(controller_movimento, "flutuando_superior-direita_parar"),
)
avancar_ate_estavel(controller_movimento, repositorio_real.obter("flutuando_superior-direita_parar").frame_count)
checar(
    "fim da parada retorna ao idle flutuando",
    controller_movimento.animacao_atual == "flutuando_idle"
    and controller_movimento.estado_logico == "flutuando",
    (controller_movimento.animacao_atual, controller_movimento.estado_logico),
)


# ----------------------------------------------------------------------
# Fluxo de arraste completo: agarrar -> reação -> queda -> recuperação.
# ----------------------------------------------------------------------
controller_arraste = AnimationController(repositorio=repositorio_real)
checar(
    "arraste aceita agarrar a partir do idle flutuando",
    transicionar(controller_arraste, "flutuando_para_agarrada"),
)
avancar_ate_estavel(controller_arraste, repositorio_real.obter("flutuando_para_agarrada").frame_count)
checar(
    "fim de agarrar entra no loop calmo",
    controller_arraste.animacao_atual == "arrastada_loop_calma"
    and controller_arraste.estado_logico == "agarrada",
    (controller_arraste.animacao_atual, controller_arraste.estado_logico),
)
aceitou_reacao = transicionar(controller_arraste, "arrastada_loop_furiosa")
checar(
    "estado agarrada permite trocar a reação por outro loop",
    aceitou_reacao and controller_arraste.animacao_atual == "arrastada_loop_furiosa",
    controller_arraste.animacao_atual,
)
checar(
    "estado agarrada aceita a queda de joelhos",
    transicionar(controller_arraste, "arrastada_para_queda-joelho"),
)
avancar_ate_estavel(controller_arraste, repositorio_real.obter("arrastada_para_queda-joelho").frame_count)
checar(
    "queda de joelhos encadeia a recuperação",
    controller_arraste.animacao_atual == "queda-joelhos_para_flutuando"
    and controller_arraste.estado_logico == "queda-joelhos",
    (controller_arraste.animacao_atual, controller_arraste.estado_logico),
)
avancar_ate_estavel(controller_arraste, repositorio_real.obter("queda-joelhos_para_flutuando").frame_count)
checar(
    "recuperação da queda retorna ao idle flutuando",
    controller_arraste.animacao_atual == "flutuando_idle"
    and controller_arraste.estado_logico == "flutuando",
    (controller_arraste.animacao_atual, controller_arraste.estado_logico),
)

controller_queda_bunda = AnimationController(repositorio=repositorio_real)
transicionar(controller_queda_bunda, "flutuando_para_agarrada")
avancar_ate_estavel(controller_queda_bunda, repositorio_real.obter("flutuando_para_agarrada").frame_count)
checar(
    "estado agarrada aceita a queda de bunda",
    transicionar(controller_queda_bunda, "arrastada_para_queda-bunda"),
)
avancar_ate_estavel(controller_queda_bunda, repositorio_real.obter("arrastada_para_queda-bunda").frame_count)
checar(
    "queda de bunda encadeia a recuperação correspondente",
    controller_queda_bunda.animacao_atual == "queda-bunda_para_flutuando"
    and controller_queda_bunda.estado_logico == "queda-bunda",
    (controller_queda_bunda.animacao_atual, controller_queda_bunda.estado_logico),
)
avancar_ate_estavel(controller_queda_bunda, repositorio_real.obter("queda-bunda_para_flutuando").frame_count)
checar(
    "recuperação sentada retorna ao idle flutuando",
    controller_queda_bunda.animacao_atual == "flutuando_idle"
    and controller_queda_bunda.estado_logico == "flutuando",
    (controller_queda_bunda.animacao_atual, controller_queda_bunda.estado_logico),
)


# Poses finais de sono não devem teleportar de volta ao idle sentado.
# 2026-09-06: destino de `sentada_deitando`/`sentada_caindo-no-sono`
# invertido (achado ao vivo: "os finais tao trocados") - "deitando" agora
# é quem leva pra "dormindo" e "caindo no sono" leva pra "deitada"
# (exausta); os dois testes abaixo trocaram de clipe de entrada pra
# continuar cobrindo os MESMOS dois caminhos (dormindo/wakeup direto vs.
# deitada/trocar de lado/wakeup exausta), sem mudar mais nada.
controller_sono = AnimationController(repositorio=repositorio_real)
transicionar(controller_sono, "flutuando_para_sentada")
avancar_ate_estavel(controller_sono, repositorio_real.obter("flutuando_para_sentada").frame_count)
transicionar(controller_sono, "sentada_deitando")
avancar_ate_estavel(controller_sono, repositorio_real.obter("sentada_deitando").frame_count)
checar(
    "deitando segura o quadro final no estado dormindo",
    controller_sono.animacao_atual == "sentada_deitando"
    and controller_sono.estado_logico == "dormindo"
    and not controller_sono._timer.isActive(),
    (controller_sono.animacao_atual, controller_sono.estado_logico),
)

transicionar(controller_sono, "dormindo_para_sentada")
avancar_ate_estavel(controller_sono, repositorio_real.obter("dormindo_para_sentada").frame_count)
checar(
    "acordar dormindo retorna ao idle sentado",
    controller_sono.animacao_atual == "sentada_balancando-pernas"
    and controller_sono.estado_logico == "sentada",
    (controller_sono.animacao_atual, controller_sono.estado_logico),
)

controller_exausta = AnimationController(repositorio=repositorio_real)
transicionar(controller_exausta, "flutuando_para_sentada")
avancar_ate_estavel(controller_exausta, repositorio_real.obter("flutuando_para_sentada").frame_count)
transicionar(controller_exausta, "sentada_caindo-no-sono")
avancar_ate_estavel(controller_exausta, repositorio_real.obter("sentada_caindo-no-sono").frame_count)
checar(
    "caindo no sono segura a pose exausta (deitada) final",
    controller_exausta.estado_logico == "deitada" and not controller_exausta._timer.isActive(),
    (controller_exausta.animacao_atual, controller_exausta.estado_logico),
)
transicionar(controller_exausta, "dormindo_trocando-lado")
avancar_ate_estavel(controller_exausta, repositorio_real.obter("dormindo_trocando-lado").frame_count)
checar(
    "trocar de lado conecta a pose exausta à pose dormindo",
    controller_exausta.estado_logico == "dormindo" and not controller_exausta._timer.isActive(),
    (controller_exausta.animacao_atual, controller_exausta.estado_logico),
)
transicionar(controller_exausta, "dormindo_para_exausta")
avancar_ate_estavel(controller_exausta, repositorio_real.obter("dormindo_para_exausta").frame_count)
checar(
    "trocar de lado ao contrário retorna de dormindo para exausta",
    controller_exausta.estado_logico == "deitada" and not controller_exausta._timer.isActive(),
    (controller_exausta.animacao_atual, controller_exausta.estado_logico),
)
transicionar(controller_exausta, "exausta_para_sentada")
avancar_ate_estavel(controller_exausta, repositorio_real.obter("exausta_para_sentada").frame_count)
checar(
    "levantar exausta retorna ao idle sentado",
    controller_exausta.animacao_atual == "sentada_balancando-pernas"
    and controller_exausta.estado_logico == "sentada",
    (controller_exausta.animacao_atual, controller_exausta.estado_logico),
)


# ----------------------------------------------------------------------
# Recovery: se o asset pedido falhar no meio do caminho e o repositório
# cair no fallback (flutuando_idle), o estado_logico precisa bater com o
# que está REALMENTE na tela (flutuando), nunca ficar travado dizendo
# "sentada" enquanto mostra flutuando_idle.
# ----------------------------------------------------------------------
controller3 = AnimationController(repositorio=repositorio_real)
transicionar(controller3, "flutuando_para_sentada")
avancar_ate_estavel(controller3, repositorio_real.obter("flutuando_para_sentada").frame_count)

# 🔥 Simula falha no carregamento ASSÍNCRONO (2026-09-02) - `solicitar_
# transicao`/`_carregar_e_tocar` não chamam mais `AssetRepository.obter`
# (síncrono) pra transições em runtime, então o monkeypatch precisa ser
# no que a thread de segundo plano REALMENTE chama
# (`_carregar_dados_brutos`, módulo-level). "sentada_pensando" já foi
# pedido mais cedo neste arquivo (`repositorio_real` é COMPARTILHADO por
# todos os controllers) - remove do cache primeiro, senão o pedido
# resolve direto do cache e nunca chega a chamar a versão com falha.
repositorio_real._cache.pop("sentada_pensando", None)
repositorio_real._custo_bytes.pop("sentada_pensando", None)
carregar_dados_brutos_original = asset_repository._carregar_dados_brutos


def _carregar_dados_brutos_com_falha_simulada(animation_id, geometria):
    if animation_id == "sentada_pensando":
        raise AssetInvalido("falha simulada pro teste")
    return carregar_dados_brutos_original(animation_id, geometria)


asset_repository._carregar_dados_brutos = _carregar_dados_brutos_com_falha_simulada
try:
    aceitou_com_falha_simulada = transicionar(controller3, "sentada_pensando")
    checar(
        "pedido com asset falhando (simulado) ainda é aceito, sem crash",
        aceitou_com_falha_simulada,
    )
    checar(
        "recovery: animação real na tela é o fallback (flutuando_idle), não o quebrado",
        controller3.animacao_atual == "flutuando_idle",
        controller3.animacao_atual,
    )
    checar(
        "recovery: estado_logico bate com o que está NA TELA (flutuando), não com o pedido (sentada)",
        controller3.estado_logico == "flutuando",
        controller3.estado_logico,
    )
finally:
    asset_repository._carregar_dados_brutos = carregar_dados_brutos_original

controller.parar()
controller2.parar()
controller_cena.parar()
controller_movimento.parar()
controller_arraste.parar()
controller_queda_bunda.parar()
controller_sono.parar()

print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
