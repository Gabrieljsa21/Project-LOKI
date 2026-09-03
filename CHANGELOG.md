# Changelog

Histórico de alto nível do que muda no LOKI, por versão. Este arquivo é o
resumo pra quem só quer saber "o que mudou" - detalhe técnico completo
das fases do plano original continua em `C:\Workspace\Project LOKI.md`.

Versionamento: [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Novidades
- **Extração de `assistant/features/mascot/` pro repositório próprio** - pedido do usuário desde 2026-08-29 ("LOKI não é obrigatório pra GAIA funcionar... as animações são pesadas e vão crescer MUITO... privacidade"), executado em 2026-09-03 quando o volume de assets (148MB, 91 clipes) já pesava de verdade no repo principal. Processo separado com **venv próprio** (não mais o mesmo do processo principal da GAIA) - `integrations/mascot/supervisor.py` (do lado da GAIA) sobe este subprocesso via `pythonw.exe` de dentro do `.venv` daqui, mesmo padrão dos outros satélites do ecossistema (IRIS/MOIRAI/HESTIA/ERIS/ECHO), mas continua com supervisão ATIVA de verdade (protocolo por named pipe local, handshake com token efêmero, heartbeat) - diferente do padrão fire-and-forget dos demais. Config própria (`data/mascot_config.json`, migrada do antigo `mascot_config`/`mascot_behaviors_config` de `data/brain.json` da GAIA) - o Painel da GAIA lê/escreve esse arquivo direto por caminho (`integrations/mascot_config_client.py`, do lado de lá), sem import Python cruzando repositórios. `core/mascot_events.py`/`mascot/protocol/transport.py` (contrato do protocolo) viraram cópias deliberadas em cada lado - pequenos o bastante (138/63 linhas) pra não valer a pena uma dependência formal entre os dois repos.
- Todas as features/correções anteriores a esta extração (Menu SAO, Substituição Ninja, Voo do Caos, halo por modo de voz, CompanionPanel, orçamento de memória configurável, etc.) continuam documentadas em `C:\Workspace\Project LOKI.md` e no `CHANGELOG.md` da GAIA (histórico anterior à extração).
