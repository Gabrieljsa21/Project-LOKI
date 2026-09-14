@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\python.exe" (
    echo Nao foi encontrado o ambiente Python do Project LOKI.
    echo Esperado: %CD%\.venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe scripts\importar_lote_animacoes.py
if errorlevel 1 goto :erro
.venv\Scripts\python.exe scripts\validar_animacoes.py
if errorlevel 1 goto :erro
echo.
echo Animacoes importadas e validadas com sucesso.
pause
exit /b 0

:erro
echo.
echo A importacao falhou. Veja a mensagem acima.
pause
exit /b 1
