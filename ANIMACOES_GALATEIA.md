# Animações da Galateia: do vídeo ao runtime

Este é o guia canônico para adicionar uma animação ao mascote da Galateia.
Ele cobre o processo inteiro: preparar a fonte, importar, validar, registrar no
grafo de estados, ligar a um comportamento e testar a sequência no runtime.

O fluxo completo é:

```text
vídeo/PNGs em E:\Downloads\Sprites
    -> data/animacoes_galateia.json
    -> importador e remoção de chroma
    -> spritesheet.webp + animation.json
    -> mascot/state_catalog.py
    -> gatilho manual, semântico ou autônomo
    -> testes e visualização sobre a área de trabalho
```

## Fontes de verdade

Cada camada tem uma responsabilidade diferente:

| Arquivo ou pasta | Responsabilidade |
| --- | --- |
| `data/animacoes_galateia.json` | Fontes, FPS, loop, cortes, chroma e tipo de asset |
| `scripts/importar_lote_animacoes.py` | Preparação em lote, cache e geometria compartilhada |
| `scripts/importar_animacao.py` | Remoção de fundo e montagem do atlas/manifesto |
| `assets/galateia/animations/geometry.json` | Canvas, recorte, célula e pivô comuns |
| `assets/galateia/animations/<id>/` | Asset final consumido pelo runtime |
| `mascot/state_catalog.py` | Estados, transições, fallbacks e tags |
| `mascot/animation_controller.py` | Reprodução e respeito ao grafo de estados |
| `mascot/behavior_scheduler.py` | Decisão de quando ações autônomas acontecem |
| `mascot/state_controller.py` | Tradução de estados semânticos da GAIA em clipes |
| `scripts/visualizar_animacoes.py` | Inspeção visual e montagem manual de sequências |

O vídeo em `E:\Downloads\Sprites` é fonte de produção, não arquivo de runtime.
Depois da importação, o mascote lê apenas os arquivos dentro de
`assets/galateia/animations`.

## Automação recomendada

O ponto de entrada preferencial agora é `AUTOMATIZAR_ANIMACOES.bat`:

- dê dois cliques sem argumentos para procurar vídeos novos e gerar uma auditoria;
- arraste um ou vários MP4s sobre o BAT para cadastrar, importar, validar e auditar;
- a busca normal considera somente arquivos na raiz de `E:\Downloads\Sprites`,
  evitando `OLD`, `fontes_brutas` e outras coleções históricas;
- use `--recursive` na linha de comando somente quando quiser procurar também nas
  subpastas.

O orquestrador usado pelo BAT é `scripts/automatizar_animacoes.py`. Seus comandos
principais são:

```powershell
# Descobrir fontes novas sem alterar nada
.\.venv\Scripts\python.exe scripts\automatizar_animacoes.py scan

# Cadastrar sem importar; mostra antes o resultado quando --dry-run é usado
.\.venv\Scripts\python.exe scripts\automatizar_animacoes.py add `
  "E:\Downloads\Sprites\leque_esnobe_loop.mp4" --dry-run

# Pipeline completo para uma ou várias fontes novas
.\.venv\Scripts\python.exe scripts\automatizar_animacoes.py process `
  "E:\Downloads\Sprites\flutuando_para_leque.mp4" `
  "E:\Downloads\Sprites\leque_esnobe_loop.mp4"

# Reprocessar fontes que já estão registradas
.\.venv\Scripts\python.exe scripts\automatizar_animacoes.py refresh `
  flutuando_para_leque leque_esnobe_loop --rebuild-cache

# Reparar referências depois de organizar/mover os vídeos entre pastas
.\.venv\Scripts\python.exe scripts\automatizar_animacoes.py repair-paths --apply

# Auditar tudo sem extrair quadros novamente
.\.venv\Scripts\python.exe scripts\automatizar_animacoes.py audit
```

O nome do arquivo define o id sugerido. Os sufixos `_loop` e `_idle` ativam loop;
o padrão `origem_para_destino` cria uma transição não interrompível. As demais
animações são cadastradas como ações do estado indicado pela primeira categoria
do id. Use as opções abaixo quando a inferência não representar a intenção:

```powershell
.\.venv\Scripts\python.exe scripts\automatizar_animacoes.py process `
  "E:\Downloads\Sprites\minha-cena.mp4" `
  --id flutuando_minha-cena `
  --scene --no-loop `
  --origin flutuando --destination flutuando `
  --fallback flutuando_idle `
  --tags action,scene --non-interruptible
```

Cada nova entrada recebe um objeto `state` declarativo. O runtime carrega esse
objeto automaticamente no catálogo, portanto animações novas não exigem editar
`state_catalog.py`. Estados históricos continuam explícitos no código. O campo
`inferred: true` no relatório indica que os metadados devem ser apenas conferidos,
não que houve erro.

Os relatórios ficam em:

- `cache/animation_pipeline_report.json`, para automações e agentes;
- `cache/animation_pipeline_report.md`, para leitura rápida.

Eles informam fontes ausentes, assets pendentes, divergência de loop/tipo,
pendências no catálogo, fontes ainda não registradas e grandes diferenças de
escala ou posição em relação a `flutuando_idle`.

O reparo de caminhos só grava uma troca quando encontra exatamente uma fonte com
o mesmo nome. Resultados ambíguos são apenas informados e exigem escolha explícita.

Antes de cadastrar um lote grande, `scripts/inspecionar_videos_animacao.py`
gera uma folha de contato e um JSON com resolução, FPS, duração e amostras de cada
vídeo. Isso permite classificar rapidamente cada fonte como `character` ou
`scene`, sem abrir e analisar os vídeos um por um durante a importação:

```powershell
.\.venv\Scripts\python.exe scripts\inspecionar_videos_animacao.py `
  "E:\Downloads\Sprites" `
  --output cache\animation_video_inspection
```

Cenas podem conter quadros totalmente transparentes quando a personagem some em
um teleporte. O pipeline aceita esses quadros apenas em assets `scene`; animações
`character` continuam rejeitando-os para detectar falhas de recorte ou chroma key.

## Modelo mental: clipe, estado e comportamento

São três coisas separadas:

1. **Clipe/asset:** os pixels da animação (`spritesheet.webp` e
   `animation.json`).
2. **Estado lógico:** a pose/situação em que a personagem está, como
   `flutuando`, `sentada`, `agarrada` ou `leque`.
3. **Comportamento:** a regra que decide quando pedir uma transição, por exemplo
   sentar na barra de tarefas, passear pela tela ou escolher uma reação.

Importar um vídeo cria o asset e o torna visível no visualizador. Isso não é
suficiente para a Galateia usá-lo no runtime: o id também precisa existir no
catálogo de estados. Para uso autônomo, ainda é necessário um gatilho ou
Behavior.

## Tipos de animação

### Loop

Permanece no mesmo estado até outra transição ser solicitada.

Exemplos: `flutuando_idle`, `sentada_balancando-pernas`,
`arrastada_loop_furiosa`.

Requisitos visuais:

- primeiro e último quadro devem emendar sem salto;
- a personagem não deve mudar de escala ou posição média;
- câmera e fundo permanecem imóveis.

### Transição

É um clipe sem loop que muda de um estado para outro. Ao terminar, o controller
carrega o `fallback` definido no catálogo.

Exemplos: `flutuando_para_sentada`, `sentada_para_flutuando`,
`flutuando_para_agarrada`.

### Ação

É um clipe sem loop cuja origem e destino são o mesmo estado. Ao terminar, ele
retorna ao último loop que estava tocando naquele estado, não necessariamente ao
fallback fixo.

Exemplos: rir, bocejar ou mexer no cabelo enquanto está sentada.

### Pose terminal

É um clipe sem fallback. Ao terminar, segura o último quadro. Use somente quando
esse congelamento for intencional, como uma pose de sono ainda sem animação de
saída.

### Cena ampla

Use `"assetType": "scene"` quando efeitos ou personagens ocupam uma região maior
do palco 1280x720. A cena mantém a escala global, mas recebe uma célula própria e
não fica limitada ao recorte compacto da personagem.

Uma cena ampla não deve ser usada apenas para contornar uma personagem gerada na
escala errada. Primeiro corrija a fonte para o padrão visual.

## Preparação da fonte

Antes de importar, confira:

- canvas preferencial de **1280x720** em todos os vídeos do fluxo;
- personagem com a mesma escala e âncora dos quadros de referência;
- corpo inteiro visível, salvo quando o corte é parte deliberada de uma cena;
- câmera fixa, sem zoom ou reenquadramento;
- fundo sólido e imóvel, preferencialmente `#00FF00`;
- nenhuma sombra projetada no fundo;
- começo e fim compatíveis com os clipes vizinhos;
- loops com uma volta completa e emenda visual limpa;
- nomes de arquivo claros e estáveis.

Convenção dos ids:

- `_` separa categorias semânticas;
- `-` une palavras dentro da mesma categoria.

Exemplos:

```text
flutuando_para_leque
leque_esnobe_loop
leque_para_flutuando
flutuando_superior-esquerda_iniciar
```

Evite renomear fontes depois de registrá-las. O caminho pode ser atualizado na
configuração, mas nomes estáveis facilitam cache, diagnóstico e histórico.

## Formatos aceitos

O lote oficial aceita:

- vídeo (`.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, `.m4v`);
- pasta com PNGs/WebPs numerados.

O importador individual também aceita uma folha única, desde que sua grade seja
informada. Para o catálogo oficial, prefira vídeo ou pasta de quadros.

Não é necessário converter o vídeo manualmente em imagens: vídeos são amostrados
diretamente no FPS final.

## Registrar no lote

Edite `data/animacoes_galateia.json`.

### Loop simples

```json
{
  "id": "leque_esnobe_loop",
  "source": "E:\\Downloads\\Sprites\\leque_esnobe_loop.mp4",
  "loop": true
}
```

### Transição simples

```json
{
  "id": "flutuando_para_leque",
  "source": "E:\\Downloads\\Sprites\\flutuando_para_leque.mp4",
  "loop": false,
  "skipStart": 1
}
```

### Vários vídeos formando um único asset

```json
{
  "id": "acao_composta",
  "sources": [
    {
      "path": "E:\\Downloads\\Sprites\\acao_parte-1.mp4",
      "skipEnd": 1
    },
    {
      "path": "E:\\Downloads\\Sprites\\acao_parte-2.mp4",
      "skipStart": 1
    }
  ],
  "loop": false
}
```

Os segmentos são processados na ordem declarada. Eles não são unidos em um novo
MP4: os quadros tratados alimentam diretamente um único asset final.

### Cena ampla

```json
{
  "id": "efeito_tela-inteira",
  "source": "E:\\Downloads\\Sprites\\efeito_tela-inteira.mp4",
  "assetType": "scene",
  "background": "#00FF00",
  "loop": false
}
```

### Pasta de quadros que precisa voltar ao canvas original

`restoreCanvas` serve para fontes já recortadas. Ele recoloca cada quadro dentro
do canvas de origem antes do cálculo da geometria:

```json
{
  "id": "exemplo_frames",
  "source": "E:\\Downloads\\Sprites\\exemplo_frames",
  "sourceFps": 24,
  "restoreCanvas": {
    "width": 1280,
    "height": 720,
    "left": 396,
    "top": 50
  },
  "loop": true
}
```

## Campos da configuração

| Campo | Uso |
| --- | --- |
| `id` | Identificador único; vira nome da pasta e chave do catálogo |
| `source` | Um vídeo ou uma pasta de quadros |
| `sources` | Lista ordenada de segmentos; não use junto com `source` |
| `loop` | `true` para repetição contínua, `false` para transição/ação |
| `sourceType` | Normalmente `auto`; pode forçar `video` ou `frames` |
| `sourceFps` | FPS original de uma pasta de quadros; vídeos informam isso internamente |
| `skipStart` | Quadros amostrados removidos do início |
| `skipEnd` | Quadros amostrados removidos do fim |
| `background` | `auto`, `transparent` ou uma cor `#RRGGBB` |
| `tolerance` | Alcance da remoção de fundo; maior remove mais variações |
| `feather` | Suavização da borda do recorte |
| `restoreCanvas` | Recoloca quadros recortados no canvas de origem |
| `assetType` | `character` por padrão ou `scene` para cenas amplas |

Parâmetros globais do arquivo:

| Campo | Padrão atual | Função |
| --- | --- | --- |
| `fps` | `12` | FPS final de todas as animações oficiais |
| `maxCell` | `384` | Limite do maior lado da célula da personagem |
| `geometryPadding` | `24` | Margem transparente no recorte compartilhado |
| `atlasQuality` | `90` | Qualidade do WebP final |

## Importar

Execute os comandos a partir da raiz deste repositório.

Para importar somente uma entrada nova:

```powershell
.\.venv\Scripts\python.exe scripts\importar_lote_animacoes.py --only leque_esnobe_loop
```

Para importar várias entradas específicas:

```powershell
.\.venv\Scripts\python.exe scripts\importar_lote_animacoes.py `
  --only flutuando_para_leque `
  --only leque_esnobe_loop `
  --only leque_para_flutuando
```

Para processar todas as entradas e validar os manifests, dê dois cliques em
`IMPORTAR_ANIMACOES.bat` ou execute:

```powershell
.\.venv\Scripts\python.exe scripts\importar_lote_animacoes.py
.\.venv\Scripts\python.exe scripts\validar_animacoes.py
```

### Cache

Os quadros extraídos e já limpos ficam em
`cache/galateia_animation_frames/<id>/`. Alterar somente geometria, escala ou
atlas reutiliza esse material.

Comandos úteis:

```powershell
# Atualiza apenas a preparação/cache, sem montar os assets finais
.\.venv\Scripts\python.exe scripts\importar_lote_animacoes.py --prepare-only

# Refaz a extração e limpeza mesmo que o cache pareça válido
.\.venv\Scripts\python.exe scripts\importar_lote_animacoes.py --only meu_id --rebuild-cache

# Diagnóstico sem ler nem gravar cache
.\.venv\Scripts\python.exe scripts\importar_lote_animacoes.py --only meu_id --no-cache
```

Não apague o cache por rotina. Use `--rebuild-cache` quando a fonte foi corrigida
mas o resultado ainda parece antigo, ou para investigar uma possível invalidação
incorreta.

### Recalcular geometria

O `geometry.json` é bloqueado para impedir que uma animação nova mude o tamanho e
o pivô de todas as antigas. Se uma animação `character` legítima ultrapassar o
recorte atual, o importador para em vez de cortá-la.

Só então avalie:

1. a fonte foi gerada na escala correta?
2. é realmente uma cena ampla (`assetType: scene`)?
3. o recorte compartilhado precisa crescer de verdade?

Se a terceira opção for confirmada:

```powershell
.\.venv\Scripts\python.exe scripts\importar_lote_animacoes.py --recalculate-geometry
```

Esse comando prepara todas as animações e reconstrói o conjunto. Não use para
compensar um único vídeo fora de escala.

## Resultado da importação

Cada animação oficial produz:

```text
assets/galateia/animations/<id>/
    animation.json
    spritesheet.webp
```

`animation.json` guarda FPS, quantidade de quadros, loop, grade, pivô, canvas,
recorte e tipo do asset. `spritesheet.webp` contém os pixels transparentes usados
pelo runtime.

`preview.webp` é opcional e serve apenas para inspeção. O runtime e o visualizador
oficial não precisam dele.

Não copie para o projeto:

- MP4 original;
- pasta inteira de PNGs da fonte;
- spritesheet intermediário de ferramentas externas;
- fundo verde.

## Registrar no grafo de estados

Depois de importar, registre o mesmo id em
`mascot/state_catalog.py`. O catálogo deve cobrir exatamente os assets
oficiais; o teste de assets acusa tanto pasta sem catálogo quanto catálogo sem
asset.

Cada entrada define:

- `origem`: estado lógico exigido para iniciar;
- `destino`: estado lógico após terminar/iniciar o loop;
- `fallback`: próximo asset automático de um clipe sem loop;
- `interrompivel`: se outro pedido pode substituí-lo no meio;
- `tags`: classificação usada pelo scheduler e por agrupamentos.

### Exemplo completo: fluxo do leque

```python
CATALOGO["flutuando_para_leque"] = _estado(
    "flutuando_para_leque",
    loop=False,
    origem="flutuando",
    destino="leque",
    fallback="leque_esnobe_loop",
    interrompivel=False,
    tags=("transition", "fan"),
)

for animation_id, estilo in (
    ("leque_esnobe_loop", "snobbish"),
    ("leque_misteriosa_loop", "mysterious"),
    ("leque_ironica_loop", "ironic"),
):
    CATALOGO[animation_id] = _estado(
        animation_id,
        loop=True,
        origem="leque",
        destino="leque",
        fallback=None,
        interrompivel=True,
        tags=("idle", "fan", estilo),
    )

CATALOGO["leque_para_flutuando"] = _estado(
    "leque_para_flutuando",
    loop=False,
    origem="leque",
    destino="flutuando",
    fallback="flutuando_idle",
    interrompivel=False,
    tags=("transition", "fan", "floating"),
)
```

Nesse exemplo:

```text
flutuando_idle
    -> flutuando_para_leque
    -> leque_esnobe_loop
    -> leque_misteriosa_loop ou leque_ironica_loop
    -> leque_para_flutuando
    -> flutuando_idle
```

O fallback de entrada precisa escolher um loop padrão. Os outros loops podem ser
solicitados enquanto o estado lógico for `leque`.

## Ligar a um gatilho

### Playground da bandeja

Depois que o asset e o catálogo estão corretos, o submenu de animações válidas da
bandeja passa a mostrar automaticamente o que pode iniciar no estado atual. Não é
necessário cadastrar cada item na interface.

### Pedido direto do runtime

Código do mascote deve solicitar o id ao controller:

```python
controller.solicitar_transicao("flutuando_para_leque")
```

Nunca troque o spritesheet diretamente. `solicitar_transicao` valida origem,
interrupção e compatibilidade antes de tocar.

### Comportamento autônomo

Para sorteio autônomo, adicione um `Behavior` em
`mascot/behavior_scheduler.py` com:

- peso;
- cooldown;
- orçamento por hora;
- assets candidatos/necessários;
- função `executar` que pede a primeira transição do fluxo.

O Behavior deve marcar `_ocupado` durante sequências não interrompíveis e liberar
quando o estado final esperado for emitido. Reaproveite os helpers de callback já
existentes no scheduler; não conecte sinais permanentes para uma ação temporária.

Se o usuário precisa ligar/desligar a família, adicione também uma chave na
configuração do mascote e respeite-a na elegibilidade do Behavior.

### Estado semântico da GAIA

Se a animação representa um estado da conversa, como `thinking`, a escolha deve
ser feita em `mascot/state_controller.py`. Estados sem clipe próprio não
devem inventar uma troca de pose apenas para mostrar atividade.

## Visualizar e montar sequências

Dê dois cliques em `TESTAR_ANIMACOES.bat`.

O visualizador lê diretamente os assets finais e permite:

- pausar e reiniciar;
- avançar quadro a quadro;
- repetir uma transição com pausa;
- montar uma sequência com vários assets;
- reordenar os trechos;
- repetir a sequência completa;
- mostrar a reprodução transparente sobre a área de trabalho;
- alterar temporariamente a escala de exibição.

Para validar um fluxo, adicione todos os trechos na ordem real. Um loop executa
uma volta e libera o próximo trecho da sequência de teste.

Exemplo:

```text
flutuando_para_leque
leque_esnobe_loop
leque_misteriosa_loop
leque_ironica_loop
leque_para_flutuando
flutuando_idle
```

## Validação automatizada

Execute a partir da raiz deste repositório:

```powershell
# Manifests, texturas e geometria
.\.venv\Scripts\python.exe scripts\validar_animacoes.py

# Paridade asset <-> catálogo, carregamento, pivô e grafo
.\.venv\Scripts\python.exe testes\testar_mascot_assets.py

# Scheduler, callbacks, movimento e comportamentos
.\.venv\Scripts\python.exe testes\testar_mascot_behaviors.py

# Descoberta, cadastro, inferência e catálogo declarativo
.\.venv\Scripts\python.exe testes\testar_automacao_animacoes.py
```

Se uma mudança tocar comunicação entre a GAIA e o processo do mascote, rode
também:

```powershell
.\.venv\Scripts\python.exe testes\testar_mascot_protocolo.py
.\.venv\Scripts\python.exe testes\testar_mascot_supervisor.py
```

Para as oito famílias direcionais de movimento:

```powershell
.\.venv\Scripts\python.exe scripts\auditar_continuidade_movimento.py
```

Os relatórios visuais e métricos ficam em
`assets/galateia/animations/qa_continuidade/` e não são carregados pelo mascote.

## Checklist visual

Antes de considerar a animação pronta:

- [ ] canvas da fonte está correto;
- [ ] primeiro quadro conecta ao clipe anterior;
- [ ] último quadro conecta ao próximo clipe/fallback;
- [ ] loop não dá salto ao reiniciar;
- [ ] cabeça e corpo mantêm a escala oficial;
- [ ] pivô não desloca a personagem na troca de asset;
- [ ] fundo foi completamente removido, inclusive entre pernas e cabelo;
- [ ] áreas claras da personagem não ficaram translúcidas;
- [ ] mãos, pernas, cabelo, broche e roupa não somem no meio;
- [ ] não há borda verde ou magenta;
- [ ] sequência funciona no visualizador;
- [ ] sequência funciona no overlay da área de trabalho;
- [ ] catálogo aceita somente transições coerentes;
- [ ] fallback termina no loop correto;
- [ ] testes automatizados passam.

## Diagnóstico rápido

### O vídeo aparece no visualizador, mas nunca no mascote

O asset foi importado, mas falta registrar o id em `state_catalog.py` ou criar o
gatilho que solicita a primeira transição.

### O mascote volta para `flutuando_idle`

O id pode estar ausente, inválido ou incompatível com `geometry.json`.
`AssetRepository` usa `flutuando_idle` como fallback seguro quando não consegue
carregar um asset pedido.

### A transição é rejeitada

O `estado_origem` do clipe não corresponde ao estado lógico atual, ou o clipe em
execução é não interrompível. Confira o grafo em `state_catalog.py`.

### A personagem pula ou muda de tamanho

Primeiro confirme a escala e a posição no vídeo original. A geometria
compartilhada mantém o canvas e o pivô, mas não corrige uma personagem desenhada
maior dentro do próprio quadro.

### O importador diz que a animação ultrapassa a geometria

Não recalcule imediatamente. Verifique se a fonte está fora de escala ou se deve
ser uma `scene`. Recalcule a geometria somente quando o movimento da personagem
realmente exige ampliar o recorte global.

### Há resíduos do fundo

Informe `background` explicitamente e ajuste `tolerance`/`feather`. Valores maiores
removem mais variações, mas podem abrir buracos em detalhes parecidos com a cor da
chave.

### Pele, cabelo ou roupa ficaram transparentes

Reduza `tolerance` e `feather`, confirme a cor do fundo e refaça com
`--rebuild-cache`.

### O início ou o fim tem um quadro defeituoso

Use `skipStart` ou `skipEnd`. Os valores contam quadros depois da amostragem no FPS
final.

### O resultado parece antigo depois de trocar o vídeo

Execute a entrada com `--rebuild-cache`. O cache normalmente é invalidado por
nome, tamanho e data de modificação da fonte, mas a reconstrução explícita ajuda no
diagnóstico.

## Definição de pronto

Uma animação só está integrada quando:

1. a fonte foi registrada no lote;
2. o asset final foi importado;
3. a validação de manifests passou;
4. o id existe no catálogo com origem/destino corretos;
5. existe um meio real de dispará-la;
6. o fluxo completo foi conferido no visualizador e overlay;
7. os testes de assets passaram;
8. testes de comportamento/protocolo passaram quando essas camadas mudaram;
9. somente `animation.json` e `spritesheet.webp` são necessários no runtime.

Essa lista evita o falso positivo de considerar uma animação pronta apenas porque
o MP4 foi convertido.
