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

if "%~1"=="" (
    .venv\Scripts\python.exe scripts\automatizar_animacoes.py --help
    echo.
    echo Informe um comando e os argumentos. Exemplo:
    echo AUTOMATIZAR_ANIMACOES.bat scan
    echo AUTOMATIZAR_ANIMACOES.bat process "E:\Downloads\Sprites\animacao.mp4"
    pause
    exit /b 0
)

.venv\Scripts\python.exe scripts\automatizar_animacoes.py %*
set CODIGO=%ERRORLEVEL%
if not "%CODIGO%"=="0" (
    echo.
    echo O pipeline terminou com erro. Veja a mensagem acima.
)
pause
exit /b %CODIGO%
