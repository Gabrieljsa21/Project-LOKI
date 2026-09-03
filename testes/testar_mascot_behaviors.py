"""Script avulso pra validar a Fase 1/2 do LOKI/Mascot (`MascotWindow`,
`physics.MovimentoAmortecido`, `BehaviorScheduler`) - sem framework de
teste (mesmo padrão de testes/testar_*.py), roda cada caso e imprime
PASS/FAIL.

Roda offscreen (QT_QPA_PLATFORM=offscreen) - não abre janela de verdade
na tela, só confere a lógica de transição/física. `SafetyController` real
depende do foco de janela do Windows no momento do teste (não-determinístico
neste processo) - por isso os testes usam um substituto simples
(`_SafetyFixo`) em vez do real, sempre com autonomia permitida.
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raiz do projeto

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

from mascot import config, platform_windows, state_catalog
from mascot import behavior_scheduler as behavior_scheduler_module
from mascot.animation_controller import AnimationController
from mascot.asset_repository import AssetRepository
from mascot.behavior_scheduler import BehaviorScheduler
from mascot.physics import MovimentoAmortecido
from mascot.window import MascotWindow

_falhas = []


def checar(nome, condicao, detalhe=""):
    if condicao:
        print(f"PASS: {nome}")
    else:
        print(f"FAIL: {nome} {detalhe}")
        _falhas.append(nome)


def bombear_ate(condicao, timeout_s=5):
    inicio = time.monotonic()
    while not condicao() and time.monotonic() - inicio < timeout_s:
        app.processEvents()
        time.sleep(0.01)
    return condicao()


def esperar_carregamento(timeout_s=5):
    """Carregamento assíncrono (2026-09-02, ver `asset_repository.py`) -
    `solicitar_transicao`/`_avancar` não aplicam mais o novo asset na
    MESMA chamada quando ele não está em cache (thread de segundo plano +
    `Signal` cruzando thread, precisa do loop do Qt rodando pra entregar).
    Chamar isso depois de qualquer transição/`_avancar()` antes de checar
    `controller.animacao_atual`/`estado_logico` direto (sem passar por um
    `bombear_ate` que já pumpa o loop sozinho). Espera só o que foi
    REALMENTE solicitado (`controller._id_solicitado_mais_recente`), nunca
    o pré-carregamento especulativo dos candidatos (fila separada, mais
    lenta - `AssetRepository.garantir_carregado_assincrono(...,
    prioridade=False)`) - esperar TODO `_carregando` esvaziar podia
    estourar o timeout à toa, sem o pedido de verdade ainda estar pendente."""
    return bombear_ate(lambda: controller._id_solicitado_mais_recente not in repositorio._carregando, timeout_s=timeout_s)


def avancar_ate_estavel(n):
    for _ in range(n):
        controller._avancar()
        esperar_carregamento()


class _SafetyFixo(QObject):
    """`QObject` (2026-09-02) - `BehaviorScheduler` agora conecta em
    `autonomia_alterada` (ver `safety.py`, bloqueio de autonomia por
    interação do Menu SAO/CompanionPanel) - sem sinal de verdade aqui, a
    conexão no construtor do scheduler quebraria com `AttributeError`."""

    autonomia_alterada = Signal(bool)
    autonomia_permitida = True


# ----------------------------------------------------------------------
# MovimentoAmortecido converge pro alvo (já coberto isoladamente, aqui só
# confere que não regrediu depois de virar dependência do window/scheduler).
# ----------------------------------------------------------------------
pos = [0.0, 0.0]
m = MovimentoAmortecido()
m.iniciar(lambda: tuple(pos), lambda x, y: (pos.__setitem__(0, x), pos.__setitem__(1, y)), (150.0, -80.0))
checar("MovimentoAmortecido converge pro alvo", bombear_ate(lambda: not m.em_andamento) and pos == [150.0, -80.0], pos)


# ----------------------------------------------------------------------
# MascotWindow - abre no tamanho da célula real, arraste puro (sem soltar
# abaixo do piso) não deveria disparar queda física.
# ----------------------------------------------------------------------
repositorio = AssetRepository()
controller = AnimationController(repositorio=repositorio)
window = MascotWindow(controller, escala=1.0)
celula_real = (controller.asset_atual.cell_width, controller.asset_atual.cell_height)
checar(
    "MascotWindow nasce do tamanho da célula real",
    (window.width(), window.height()) == celula_real,
    (window.width(), window.height()),
)

ancora_antes = (
    window.x() + controller.pivot_atual[0], window.y() + controller.pivot_atual[1]
)
controller.solicitar_transicao("flutuando_cortina-abrindo")
esperar_carregamento()
ancora_durante = (
    window.x() + controller.pivot_atual[0], window.y() + controller.pivot_atual[1]
)
celula_cena = (controller.asset_atual.cell_width, controller.asset_atual.cell_height)
checar(
    "cena ampla redimensiona a janela para a célula própria",
    (window.width(), window.height()) == celula_cena and celula_cena != celula_real,
    (window.width(), window.height()),
)
checar("cena ampla preserva a âncora da Galateia", ancora_durante == ancora_antes, (ancora_antes, ancora_durante))
avancar_ate_estavel(repositorio.obter("flutuando_cortina-abrindo").frame_count)
checar(
    "fim da cena retorna ao tamanho normal",
    (window.width(), window.height()) == celula_real and controller.animacao_atual == "flutuando_idle",
    ((window.width(), window.height()), controller.animacao_atual),
)

# Arraste real usa o fluxo animado e CORTA a introdução "sendo agarrada"
# na hora ao soltar, mesmo antes dela terminar sozinha (pedido do
# usuário, 2026-08-29: "pode cortar animações também, assim que eu
# solto ela, já realiza queda"). Zera a chance da Substituição Ninja
# (2026-09-02) pra esses testes ficarem determinísticos - ela tem teste
# PRÓPRIO em `testar_mascot_substituicao_ninja.py`.
MascotWindow.CHANCE_SUBSTITUICAO_NINJA = 0.0
window._iniciar_fluxo_animado_arraste()
esperar_carregamento()
checar(
    "arraste real inicia a transição para agarrada",
    controller.animacao_atual == "flutuando_para_agarrada",
    controller.animacao_atual,
)
window._finalizar_fluxo_animado_arraste()
esperar_carregamento()
queda_escolhida = controller.animacao_atual
checar(
    "soltar cedo corta a introdução e já começa a queda na hora",
    queda_escolhida in {"arrastada_para_queda-joelho", "arrastada_para_queda-bunda"},
    queda_escolhida,
)
avancar_ate_estavel(repositorio.obter(queda_escolhida).frame_count)
recuperacao_esperada = (
    "queda-joelhos_para_flutuando"
    if queda_escolhida == "arrastada_para_queda-joelho"
    else "queda-bunda_para_flutuando"
)
checar(
    "queda do arraste encadeia a recuperação correspondente",
    controller.animacao_atual == recuperacao_esperada,
    controller.animacao_atual,
)
avancar_ate_estavel(repositorio.obter(recuperacao_esperada).frame_count)
checar(
    "fluxo do arraste real termina no idle flutuando",
    controller.animacao_atual == "flutuando_idle" and controller.estado_logico == "flutuando",
    (controller.animacao_atual, controller.estado_logico),
)

window.move(100, 100)
window._posicao_ao_pressionar = window.pos()
window.move(120, 130)  # simula arraste real (> limiar) mantendo dentro da tela
window._acomodar_apos_arraste()
checar(
    "arraste dentro do piso não dispara queda física",
    not window._queda.em_andamento,
    window.pos(),
)

tela = window.screen()
_, tela_y, _, tela_altura = platform_windows.obter_geometria_completa_da_tela(tela)
margem_floating = controller.asset_atual.margem_inferior_vazia_px
piso = tela_y + tela_altura - window.height() + margem_floating
window.move(window.x(), piso + 500)  # solta bem abaixo do piso de propósito
window._posicao_ao_pressionar = window.pos()
window.move(window.x() + 10, window.y())  # desloca o suficiente pra contar como arraste
window._acomodar_apos_arraste()
checar("soltar abaixo do piso dispara a queda física", window._queda.em_andamento)
checar("queda física converge exatamente no piso", bombear_ate(lambda: not window._queda.em_andamento) and window.y() == piso, window.y())


# ----------------------------------------------------------------------
# BehaviorScheduler - Taskbar Sit (flutuando -> sentada) e Variação
# sentada, disparados manualmente (sem esperar o cooldown/tick real).
# ----------------------------------------------------------------------
scheduler = BehaviorScheduler(
    controller,
    window,
    repositorio,
    _SafetyFixo(),
    dict(config.MASCOT_PADRAO),
    dict(config.BEHAVIORS_PADRAO),
)
# este arquivo dispara cada Behavior MANUALMENTE (ver docstring acima) -
# o `_tick()` autônomo (QTimer real, INTERVALO_TICK_MS) continuava rodando
# em paralelo mesmo assim, e virou uma corrida de verdade depois que os
# voos passaram a durar um tempo realista (2026-08-29): dava tempo de
# sortear outro Behavior (ex. uma variação sentada) NO MEIO da checagem
# de um behavior diferente. Sem isso aqui, cada seção só testa o que
# invocou explicitamente.
scheduler._timer.stop()

# duração real de UM salto (iniciar + até 3 ciclos de loop + parar, ver
# DISTANCIA_POR_CICLO_LOOP_PX) passou a ser bem maior desde que o loop
# ganhou voltas de verdade (2026-08-29) - os tempos de espera abaixo
# precisam de folga generosa pra isso, não só pros ~4s de uma transição
# única. Taskbar Sit agora pode incluir 1+ saltos de "voo" antes da
# aproximação final precisa (mola silenciosa) + a transição de sentar em
# si, se ela estiver longe da barra (bug real reportado, 2026-08-29).
DURACAO_MAX_SALTO_S = 25

checar("controller começa flutuando antes do Taskbar Sit", controller.estado_logico == "flutuando", controller.estado_logico)
scheduler._executar_taskbar_sit()
checar("Taskbar Sit ocupa o scheduler enquanto o movimento roda", scheduler._ocupado)
checar(
    "Taskbar Sit troca pra transição flutuando_para_sentada ao chegar (com ou sem saltos de voo antes)",
    bombear_ate(lambda: controller.animacao_atual == "flutuando_para_sentada", timeout_s=2 * DURACAO_MAX_SALTO_S),
    controller.animacao_atual,
)

_, area_y, _, area_altura = platform_windows.obter_work_area_da_tela(window.screen())
linha_assento_absoluta = window.y() + state_catalog.LINHA_ASSENTO_SENTADA_PX * window.escala
checar(
    "Taskbar Sit alinha o ASSENTO (não o pé) com o topo da barra",
    abs(linha_assento_absoluta - (area_y + area_altura)) < 1,
    (linha_assento_absoluta, area_y + area_altura),
)

checar(
    "Taskbar Sit termina em sentada_balancando-pernas",
    bombear_ate(lambda: controller.animacao_atual == "sentada_balancando-pernas", timeout_s=15),
    controller.animacao_atual,
)
checar("scheduler libera a trava depois do Taskbar Sit terminar", bombear_ate(lambda: not scheduler._ocupado, timeout_s=2))

scheduler._executar_variacao_sentada()
checar("variação sentada ocupa o scheduler", scheduler._ocupado)
esperar_carregamento()
animacao_variacao = controller.animacao_atual
checar("variação sentada escolhe um clipe válido do catálogo", animacao_variacao != "sentada_balancando-pernas", animacao_variacao)
for _ in range(130):
    if controller.animacao_atual != animacao_variacao:
        break
    controller._avancar()
    esperar_carregamento()
checar("variação sentada volta pra sentada_balancando-pernas ao terminar", controller.animacao_atual == "sentada_balancando-pernas", controller.animacao_atual)
checar("scheduler libera a trava depois da variação terminar", bombear_ate(lambda: not scheduler._ocupado, timeout_s=1))


# ----------------------------------------------------------------------
# Levantar (sentada -> flutuando) - sem isso, sentar era uma viagem só de
# ida. Controller está em sentada_balancando-pernas pelo bloco anterior.
# ----------------------------------------------------------------------
scheduler._executar_levantar()
checar("Levantar ocupa o scheduler", scheduler._ocupado)
esperar_carregamento()
checar("Levantar troca pra sentada_para_flutuando", controller.animacao_atual == "sentada_para_flutuando", controller.animacao_atual)
checar(
    "Levantar termina em flutuando_idle",
    bombear_ate(lambda: controller.animacao_atual == "flutuando_idle" and controller.estado_logico == "flutuando", timeout_s=15),
    (controller.animacao_atual, controller.estado_logico),
)
checar("scheduler libera a trava depois de Levantar terminar", bombear_ate(lambda: not scheduler._ocupado, timeout_s=2))


# ----------------------------------------------------------------------
# Wander - flutuando numa direção e voltando pro idle, com deslocamento
# real de posição na tela, EM PARALELO com a animação (não antes/depois
# dela) - bug real reportado pelo usuário, 2026-08-29.
# ----------------------------------------------------------------------
posicao_antes_wander = (window.x(), window.y())
scheduler._executar_wander()
checar("Wander ocupa o scheduler", scheduler._ocupado)
checar(
    "Wander escolhe uma direção válida (flutuando_<direção>_iniciar)",
    controller.animacao_atual is not None and controller.animacao_atual.startswith("flutuando_") and controller.animacao_atual.endswith("_iniciar"),
    controller.animacao_atual,
)
direcao_escolhida = controller.animacao_atual.removeprefix("flutuando_").removesuffix("_iniciar")

checar("Wander já começa o deslocamento físico no mesmo instante (não espera 'iniciar' terminar)", scheduler._movimento_wander.em_andamento)
bombear_ate(lambda: not controller.animacao_atual.endswith("_iniciar") or (window.x(), window.y()) != posicao_antes_wander, timeout_s=2)
checar(
    "janela já se moveu ENQUANTO 'iniciar' ainda está tocando (não espera ele acabar pra sair do lugar)",
    controller.animacao_atual.endswith("_iniciar") and (window.x(), window.y()) != posicao_antes_wander,
    ((window.x(), window.y()), controller.animacao_atual),
)

# daqui em diante deixa o relógio REAL (QTimer de verdade) avançar tudo -
# misturar `controller._avancar()` manual com o deslocamento físico
# (que corre no tempo real) já mascarou uma corrida de verdade aqui
# (2026-08-29): "iniciar" pulado instantaneamente terminava MUITO antes
# do deslocamento físico (calibrado pro tempo real de iniciar+parar),
# então "parar" também acabava cedo demais e liberava a trava enquanto o
# deslocamento ainda tinha a maior parte do caminho pela frente - achado
# real que motivou o `_aguardar_fim_wander` esperar os dois relógios.
checar(
    f"Wander entra no loop direcional (flutuando-{direcao_escolhida})",
    bombear_ate(lambda: controller.estado_logico == f"flutuando-{direcao_escolhida}", timeout_s=8),
    controller.estado_logico,
)
checar(
    "deslocamento continua rodando ao entrar no loop (ainda não terminou junto com 'iniciar')",
    scheduler._movimento_wander.em_andamento,
)
checar(
    "Wander conclui o deslocamento físico até o fim",
    # duração real agora inclui várias voltas de loop (ver
    # DISTANCIA_POR_CICLO_LOOP_PX) - bem mais que só iniciar+parar.
    bombear_ate(lambda: not scheduler._movimento_wander.em_andamento, timeout_s=DURACAO_MAX_SALTO_S),
)
checar(
    "Wander termina de volta em flutuando_idle",
    bombear_ate(lambda: controller.animacao_atual == "flutuando_idle" and controller.estado_logico == "flutuando", timeout_s=10),
    (controller.animacao_atual, controller.estado_logico),
)
checar("scheduler libera a trava depois do Wander terminar (só quando animação E deslocamento já acabaram)", bombear_ate(lambda: not scheduler._ocupado, timeout_s=2))
checar(
    "deslocamento parou de vez (não fica derivando depois de liberar a trava)",
    not scheduler._movimento_wander.em_andamento,
)


# ----------------------------------------------------------------------
# Geometria de todos os monitores (Wander precisa atravessar de tela) -
# sem multi-monitor de verdade neste ambiente de teste, mas confere que a
# união bate com o que QApplication.screens() realmente reporta.
# ----------------------------------------------------------------------
telas_reais = [t.geometry() for t in QApplication.screens()]
x_esperado = min(g.x() for g in telas_reais)
y_esperado = min(g.y() for g in telas_reais)
largura_esperada = max(g.x() + g.width() for g in telas_reais) - x_esperado
altura_esperada = max(g.y() + g.height() for g in telas_reais) - y_esperado
checar(
    "geometria de todos os monitores bate com a união real das telas",
    platform_windows.obter_geometria_todos_os_monitores() == (x_esperado, y_esperado, largura_esperada, altura_esperada),
    platform_windows.obter_geometria_todos_os_monitores(),
)

nome_primeira_tela = QApplication.screens()[0].name()
checar(
    "lista de monitores permitidos filtra pelo nome real (QScreen.name())",
    platform_windows.obter_geometria_todos_os_monitores([nome_primeira_tela])
    == tuple(int(v) for v in QApplication.screens()[0].geometry().getRect()),
    platform_windows.obter_geometria_todos_os_monitores([nome_primeira_tela]),
)
checar(
    "nome de monitor desconhecido (config desatualizada) cai de volta pra todos, nunca região vazia",
    platform_windows.obter_geometria_todos_os_monitores(["monitor-que-nao-existe"])
    == platform_windows.obter_geometria_todos_os_monitores(),
)


# ----------------------------------------------------------------------
# "Ir até o destino" (hotkey de modificador+clique, pedido do usuário
# 2026-08-29) - persegue um ponto qualquer encadeando saltos de 8
# direções, sem precisar de nenhum evento de mouse/teclado de verdade
# (chama `ir_para_destino` direto, como o `ClickDestinoWatcher` faria).
# ----------------------------------------------------------------------
checar("controller está flutuando parada antes de testar destino", controller.animacao_atual == "flutuando_idle", controller.animacao_atual)
# a tela "offscreen" de teste é minúscula (800x800) perto do tamanho da
# janela - o alvo +300/+120 abaixo podia esbarrar numa borda dependendo
# de onde o Wander (direção aleatória, sem seed) deixou ela antes,
# deixando este teste instável run a run por causa do tamanho da tela de
# teste, não da lógica de perseguição em si (achado real, 2026-08-29).
# Usa uma região permitida bem maior só aqui, do tamanho de um monitor de
# verdade, e recentraliza - assim o alvo sempre cabe.
scheduler._geometria_permitida = lambda: (0, 0, 2560, 1440)
window.move(2560 // 2 - window.width() // 2, 1440 // 2 - window.height() // 2)
centro_atual = (window.x() + window.width() / 2, window.y() + window.height() / 2)
alvo_destino = (centro_atual[0] + 300, centro_atual[1] + 120)  # fora de eixo de propósito - só 8 direções não alcançam num salto só, precisa encadear
scheduler.ir_para_destino(*alvo_destino)
checar("ir_para_destino ocupa o scheduler e começa a perseguir", scheduler._ocupado and scheduler._destino_ativo is not None)
checar(
    # fora de eixo => pelo menos 2 saltos encadeados (projeção no eixo
    # escolhido evita reversão de direção, ver `_continuar_perseguicao`) -
    # folga generosa pro pior caso de 2 saltos completos.
    "destino chega perto o bastante do ponto pedido (dentro da tolerância)",
    bombear_ate(lambda: scheduler._destino_ativo is None and not scheduler._ocupado, timeout_s=2 * DURACAO_MAX_SALTO_S + 5),
)
centro_final = (window.x() + window.width() / 2, window.y() + window.height() / 2)
distancia_final = ((centro_final[0] - alvo_destino[0]) ** 2 + (centro_final[1] - alvo_destino[1]) ** 2) ** 0.5
checar(
    "posição final fica dentro da tolerância do ponto clicado",
    distancia_final <= behavior_scheduler_module.TOLERANCIA_DESTINO_PX + 5,  # +5 de folga pro arredondamento int() da janela
    (centro_final, alvo_destino, distancia_final),
)

controller.solicitar_transicao("flutuando_para_sentada")
esperar_carregamento()
for _ in range(60):
    if controller.estado_logico == "sentada":
        break
    controller._avancar()
    esperar_carregamento()
destino_antes = scheduler._destino_ativo
scheduler.ir_para_destino(9999, 9999)
checar(
    "ir_para_destino é ignorado quando ela não está no idle flutuando calmo (ex.: sentada)",
    scheduler._destino_ativo == destino_antes,
    scheduler._destino_ativo,
)
scheduler._executar_levantar()
checar(
    # 15s (não 6s) pra bater com a duração real do clipe "sentada_para_flutuando"
    # (mesmo timeout que "Levantar termina em flutuando_idle" já usa acima) -
    # sem `checar()` em volta, o timeout curto passava em silêncio e deixava
    # os testes seguintes rodarem com ela ainda NO MEIO da transição (achado
    # real, 2026-08-29, ao adicionar o teste de AFK->sono logo depois).
    "scheduler libera a trava depois de voltar a flutuar (fim da seção de destino)",
    bombear_ate(lambda: not scheduler._ocupado, timeout_s=15),
    (controller.animacao_atual, controller.estado_logico),
)


# ----------------------------------------------------------------------
# Cooldown por FAMÍLIA (tag) - sem isso, rir/gargalhar/rir_sem_graça
# (todos tag "laugh") podiam se sucederem só porque são ids diferentes.
# ----------------------------------------------------------------------
# a variação aleatória executada acima pode ter deixado cooldown em
# QUALQUER família (não só "hair") - limpa tudo antes de montar os 2
# cenários deliberados abaixo, senão o teste fica flaky dependendo de
# qual clipe o sorteio pegou (achado real, 2026-08-29).
scheduler._ultimo_disparo_por_familia.clear()
scheduler._ultimo_disparo_por_familia["laugh"] = time.monotonic()
clipes_laugh = [id_ for id_, e in state_catalog.CATALOGO.items() if "laugh" in e.tags]
clipes_hair = [id_ for id_, e in state_catalog.CATALOGO.items() if "hair" in e.tags]
checar(
    "família 'laugh' em cooldown bloqueia TODOS os clipes dessa família",
    all(not scheduler._familia_disponivel(id_, time.monotonic()) for id_ in clipes_laugh),
    clipes_laugh,
)
checar(
    "família 'hair' (sem cooldown ativo) continua disponível normalmente",
    all(scheduler._familia_disponivel(id_, time.monotonic()) for id_ in clipes_hair),
    clipes_hair,
)

# ----------------------------------------------------------------------
# AFK -> sono (pedido do usuário, 2026-08-29: "quero que ela reconheça
# quando estou afk, pra por a GAIA pra dormir") - ociosidade REAL de
# teclado/mouse, simulada aqui (não depende do estado real da máquina
# rodando o teste). Só o caminho "já sentada" - o caminho "flutuando
# senta sozinha primeiro" reusa `_executar_taskbar_sit` (já coberto
# acima) e foi validado à parte, sem duplicar aqui pra não deixar a
# suíte mais lenta.
# ----------------------------------------------------------------------
controller.solicitar_transicao("flutuando_para_sentada")
checar(
    "chega em sentada_balancando-pernas antes de testar o AFK",
    bombear_ate(lambda: controller.animacao_atual == "sentada_balancando-pernas", timeout_s=15),
    controller.animacao_atual,
)
scheduler._config["afk_minutos"] = 0.05  # 3s - rápido o bastante pro teste
ociosidade_simulada = [0.0]
behavior_scheduler_module.platform_windows.obter_segundos_ociosos = lambda: ociosidade_simulada[0]

scheduler._verificar_afk()
checar(
    "sem ociosidade real, não dorme",
    controller.animacao_atual == "sentada_balancando-pernas" and not scheduler._ocupado,
    controller.animacao_atual,
)

ociosidade_simulada[0] = 10.0
scheduler._verificar_afk()
esperar_carregamento()
checar(
    "AFK detectado a partir de sentada_balancando-pernas dispara sentada_caindo-no-sono",
    controller.animacao_atual == "sentada_caindo-no-sono" and scheduler._ocupado,
    controller.animacao_atual,
)
checar(
    "termina de dormir de vez (estado_logico == dormindo) e libera a trava",
    bombear_ate(lambda: controller.estado_logico == "dormindo" and not scheduler._ocupado, timeout_s=15),
    (controller.estado_logico, controller.animacao_atual),
)

ociosidade_simulada[0] = 0.5
scheduler._verificar_afk()
esperar_carregamento()
checar(
    "usuário volta (ociosidade cai) - reage na hora com uma ação de acordar (transição suave, não corte seco)",
    controller.animacao_atual in behavior_scheduler_module.REACOES_ACORDAR
    and controller.estado_logico == "sentada"
    and scheduler._ocupado,
    (controller.animacao_atual, controller.estado_logico),
)
checar(
    "a ação de acordar termina de volta em sentada_balancando-pernas e libera a trava",
    bombear_ate(lambda: controller.animacao_atual == "sentada_balancando-pernas" and not scheduler._ocupado, timeout_s=10),
    (controller.animacao_atual, scheduler._ocupado),
)

controller.parar()

print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S): {_falhas}")
    sys.exit(1)
print("Todos os casos passaram.")
