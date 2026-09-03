# Importação de animações da Galateia

O procedimento completo, incluindo catálogo de estados, gatilhos, runtime,
testes e checklist de entrega, está em
[`docs/ANIMACOES_GALATEIA.md`](../../../docs/ANIMACOES_GALATEIA.md).

Para o fluxo normal, arraste os vídeos novos sobre
`assistant/AUTOMATIZAR_ANIMACOES.bat`. Sem arquivos, o mesmo BAT apenas procura
fontes novas e audita o que já está cadastrado.

O formato preferido é uma pasta com os PNGs separados e numerados na ordem correta.
Vídeo também é aceito. Uma folha única funciona, mas exige informar sua grade.

## Lote padronizado (recomendado)

As animações oficiais ficam registradas em `scripts/animacoes_galateia.json`. Dê dois
cliques em `IMPORTAR_ANIMACOES.bat` para importar todas e validar o resultado. O lote
usa `geometry.json` para manter o mesmo canvas, recorte, escala e pivô em todas as
ações. Isso evita que a personagem pule ou mude de tamanho numa transição.

Para adicionar uma animação, inclua seu id, caminho e se ela é loop na configuração.
Depois importe somente a nova entrada:

```powershell
.\.venv\Scripts\python.exe scripts\importar_lote_animacoes.py --only nova_animacao
```

Nos ids e nomes de arquivo, `_` separa categorias e `-` une palavras que
pertencem à mesma categoria. Exemplos: `flutuando_superior-esquerda_iniciar`,
`sentada_olhando-ao-redor` e `sentada_enrolando-cabelo_corando`.

Uma ação formada por vários vídeos pode ser gerada como um único asset usando
`sources` na ordem de reprodução. Cada segmento também aceita `skipStart` e
`skipEnd` próprios:

```json
{
  "id": "sentada_tehepero",
  "sources": [
    { "path": "E:\\Downloads\\Sprites\\Gaia\\sentada_para_tehepero.mp4" },
    { "path": "E:\\Downloads\\Sprites\\Gaia\\sentada_tehepero_para_sentada.mp4" }
  ],
  "loop": false
}
```

O resultado continua sendo uma única pasta com um `animation.json` e um
`spritesheet.webp`; os vídeos não são unidos ou duplicados fora do processamento.

## Cache intermediário

O lote guarda em `cache/galateia_animation_frames/` os quadros já extraídos,
recortados no tempo e com o fundo removido, ainda no canvas original. Alterar a
geometria passa a refazer somente recorte, escala e spritesheet. O cache é
reutilizado automaticamente e invalidado quando a fonte ou as opções de limpeza
mudam. Use `--prepare-only` para deixar essa etapa pronta sem montar assets,
`--rebuild-cache` para renová-la e `--no-cache` apenas para diagnóstico.

## Cenas amplas

Animações normais continuam presas à geometria compartilhada. Um vídeo que usa
uma região maior do palco 1280x720 deve declarar `"assetType": "scene"`. A cena
ganha célula própria, preserva a escala e a âncora da personagem e pode tocar as
bordas sem obrigar a reconstrução das animações normais:

```json
{
  "id": "flutuando_cortina-abrindo",
  "source": "E:\\Downloads\\Sprites\\cortina.mp4",
  "assetType": "scene",
  "background": "#14a22c",
  "loop": false
}
```

Se a nova ação ultrapassar o espaço reservado, o importador para sem cortar a
personagem. Nesse caso, amplie a geometria reconstruindo todo o conjunto:

```powershell
.\.venv\Scripts\python.exe scripts\importar_lote_animacoes.py --recalculate-geometry
```

Use `--preview` apenas quando quiser arquivos `preview.webp`; o visualizador lê o
atlas diretamente e não precisa dessas cópias. A validação também pode ser executada
separadamente com `scripts/validar_animacoes.py`.

Para conferir visualmente e por métricas as emendas dos ciclos de movimento,
execute `scripts/auditar_continuidade_movimento.py`. O relatório e as folhas de
comparação ficam em `qa_continuidade/`; essa pasta não é carregada pelo mascote.

Execute os comandos a partir da pasta `assistant` usando o Python do projeto.

## PNGs separados (recomendado)

```powershell
.\.venv\Scripts\python.exe scripts\importar_animacao.py "E:\Downloads\Sprites\nova_animacao" --name nova_animacao --fps 12 --preview
```

Se os PNGs foram extraídos em uma taxa maior, informe também a taxa original. Este
exemplo converte 96 quadros a 24 FPS em 48 quadros a 12 FPS sem alterar os 4 segundos:

```powershell
.\.venv\Scripts\python.exe scripts\importar_animacao.py "E:\Downloads\Sprites\nova_animacao" --name nova_animacao --source-fps 24 --fps 12 --preview
```

## Vídeo

```powershell
.\.venv\Scripts\python.exe scripts\importar_animacao.py "E:\Downloads\animacao.mp4" --name nova_animacao --fps 12 --preview
```

O vídeo é amostrado diretamente no FPS escolhido. Não é necessário convertê-lo em
quadros antes.

Para descartar quadros defeituosos nas pontas da sequência, use `--skip-start N` ou
`--skip-end N`. O recorte acontece depois da amostragem no FPS final.

## Folha única

```powershell
.\.venv\Scripts\python.exe scripts\importar_animacao.py "E:\Downloads\sheet.png" --name nova_animacao --columns 6 --frame-count 34 --fps 12 --preview
```

Por padrão, a cor do fundo é detectada pelas bordas. A limpeza combina cor, matiz e
saturação para alcançar também o fundo preso entre mechas de cabelo e partes da roupa,
sem apagar áreas claras de pele ou cabelo. Para indicar a cor manualmente:

```powershell
--background "#d83a9f"
```

Cada animação pronta contém apenas `spritesheet.webp` e `animation.json`. A opção
`--preview` acrescenta um `preview.webp` animado para conferência; ele pode ser apagado
depois e não é necessário durante a execução da Galateia.

## Testar e visualizar

Dê dois cliques em `TESTAR_ANIMACOES.bat`, na pasta `assistant`. O visualizador
encontra automaticamente todas as animações importadas e abre a mais recente. Ele
permite pausar, reiniciar, avançar quadro a quadro e mostrar a animação transparente
sobre a área de trabalho. A prévia lê diretamente os arquivos finais, sem criar uma
cópia adicional.

Para testar uma transição completa, selecione uma animação, clique em **Adicionar à
sequência** e repita com os próximos trechos. Os botões **Subir**, **Descer** e
**Remover** ajustam a ordem. Ao reproduzir, cada animação marcada como loop executa
uma volta e então libera a próxima; **Repetir sequência** repete a composição inteira.
O botão da área de trabalho usa a reprodução atual, inclusive quando ela é uma
sequência.

Use `--force` somente quando quiser substituir os arquivos já gerados para a mesma
animação. Para ver todas as opções:

```powershell
.\.venv\Scripts\python.exe scripts\importar_animacao.py --help
```
