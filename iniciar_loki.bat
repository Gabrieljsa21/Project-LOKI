@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

rem Sobe o Mascot/LOKI sozinho, sem a GAIA precisar estar rodando - sem as
rem variaveis GAIA_MASCOT_CANAL/GAIA_MASCOT_TOKEN (so a GAIA de verdade as
rem define ao subir o processo via MascotSupervisor), ele entra em "modo
rem demonstracao" (ver README.md, "Uso standalone") - CompanionPanel/Menu
rem SAO "GAIA" ficam sem efeito, o resto (animacoes, comportamento
rem autonomo, Menu SAO "Acoes", bandeja) funciona normal.
rem
rem Pra fechar, clique com o botao direito no icone dele na bandeja do
rem sistema ("Sair"). Pra debug com console de verdade:
rem ".venv\Scripts\python.exe -m mascot.process_main" direto neste terminal.

start "" /B ".venv\Scripts\pythonw.exe" -m mascot.process_main
