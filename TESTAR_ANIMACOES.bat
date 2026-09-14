@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Nao foi encontrado o ambiente Python do Project LOKI.
    echo Esperado: %CD%\.venv\Scripts\pythonw.exe
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "scripts\visualizar_animacoes.py"
