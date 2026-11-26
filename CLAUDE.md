# Project LOKI

Avatar animado da Galateia no desktop (PySide6), processo separado da GAIA.
Repositório público: nenhum dado pessoal, segredo ou citação a terceiros.

## Documentação: atualizar no mesmo commit da mudança

- `docs/FUNCIONALIDADES.md`: estado ATUAL do que o usuário vê e usa. Conferir
  contra o código, editar por cima.
- `docs/ARQUITETURA.md`: decisão técnica e o porquê. Editar por cima.
- `docs/TODO.md`: só pendências, cada uma com Prioridade, Complexidade e
  Status. Item concluído é removido.
- `CHANGELOG.md`: uma entrada curta por mudança, sob a versão nova da PR.
- `docs/ANIMACOES_GALATEIA.md`: guia do pipeline de animações.

Versão em `pyproject.toml` e `uv.lock` (`uv lock` depois do bump).

## Testes

```
.venv\Scripts\python.exe scripts\rodar_testes.py [filtro]
```

Cada `testes/testar_*.py` é um script independente que imprime `PASS:`/`FAIL:`
e sai com código 1 em falha. Com `QT_QPA_PLATFORM=offscreen` o código de
runtime ignora os dados reais do usuário: não lê nem grava
`data/mascot_posicao.json`, usa os padrões de fábrica do Bubble Mode e não
registra atalho global. Um teste que precise gravar outro arquivo de `data/`
faz cópia e restaura no fim.

Espere por condição (`bombear_ate`), não por tempo fixo: as animações andam
por relógio real.

## Contrato com a GAIA

`core/mascot_events.py` e `mascot/protocol/transport.py` são cópias dos
arquivos `core/mascot_events.py` e `core/mascot_transport.py` da GAIA
(`Project-GAIA`).
Evento novo entra nos dois repositórios; `testes/testar_contrato_gaia.py`
compara as cópias. `mascot/config.py` (`MASCOT_PADRAO`, `BEHAVIORS_PADRAO`)
tem espelho em `integrations/mascot_config_client.py` da GAIA.

## Convenções do código

- Todo valor que o usuário pode querer mudar vira campo do modal
  (`mascot/modal_configuracoes.py`) com padrão em `mascot/config.py`.
- Log por `logging.getLogger(__name__)`; só `process_main.main()` chama
  `mascot/registro.configurar("LOKI")` (cópia do modelo da CLIO). Vai para
  `%LOCALAPPDATA%\Ecossistema\LOKI\Logs\AAAA-MM-DD.log`, 30 dias guardados;
  `print`, stderr e exceções também. O processo roda em `pythonw.exe`, sem
  console.
- Runtime carrega animação com `garantir_carregado_assincrono`;
  `AssetRepository.obter()` bloqueia a interface e serve só ao cold-start.
- Janela top-level translúcida: brilho pintado à mão no `paintEvent`
  (`halo.py`, `_BolhaBase._desenhar_glow`), porque `QGraphicsDropShadowEffect`
  falha em silêncio nesse tipo de janela no Windows.
- Reação visual nova usa só clipes do catálogo e respeita `reduce_motion`.
- Pipeline de animações: scripts em `scripts/`, sempre chamados da raiz;
  dependências deles ficam no grupo `pipeline` do `pyproject.toml`.
