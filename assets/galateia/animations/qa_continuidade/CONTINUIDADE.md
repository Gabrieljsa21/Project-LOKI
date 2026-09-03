# Auditoria de continuidade dos movimentos

Auditoria feita nos vídeos-fonte em 24 FPS, comparando as cinco fronteiras de
cada direção: `idle → iniciar`, `iniciar → loop`, fechamento do `loop`,
`loop → parar` e `parar → idle`. As folhas de comparação desta pasta mostram
os quadros usados na conferência; `continuidade.json` guarda as métricas.

## Resultado

| Direção | Resultado | Observação |
| --- | --- | --- |
| direita | aprovado | fluxo e pose final coerentes |
| esquerda | aprovado | fluxo e pose final coerentes |
| subida | aprovado | fluxo e pose final coerentes |
| descida | aprovado | fluxo e pose final coerentes |
| superior-direita | aprovado | fluxo e pose final coerentes |
| superior-esquerda | aprovado após correção | `flutuando_superior-esquerda_parar.mp4` regerado com quadro inicial mais próximo da pose final do `loop`; melhor emenda caiu de MAE 58,92 pra 22,84 (as outras 7 direções ficam entre 13,27 e 18,75 - um pouco mais alto que a média, mas a inspeção visual do par mais próximo, quadro 80 do loop x quadro 2 do parar, mostra a mesma pose flutuando, sem salto de cabeça/membro) |
| inferior-direita | aprovado após correção | removidos os 3 quadros finais de piscada de `flutuando_inferior-direita_parar` |
| inferior-esquerda | aprovado visualmente | a métrica é alta por causa do movimento do cabelo/casaco, mas a pose continua na direção esperada |

## Correções aplicadas

- O vídeo canônico `E:\Downloads\Sprites\flutuando_inferior-direita_parar.mp4`
  termina agora no último quadro com os olhos abertos. A versão bruta com a
  piscada foi preservada em
  `E:\Downloads\Sprites\fontes_brutas\flutuando_inferior-direita_parar_com-piscada.mp4`.
- `E:\Downloads\Sprites\flutuando_superior-esquerda_parar.mp4` foi regerado
  (2026-08-28) começando de um quadro mais próximo da pose final do `loop` -
  reimportado via `importar_lote_animacoes.py --only
  flutuando_superior-esquerda_parar` e reauditado com
  `auditar_continuidade_movimento.py`. Melhor emenda `loop -> parar` caiu de
  MAE 58,92 pra 22,84.

## Pendente visual

Nenhum item aberto no momento.
