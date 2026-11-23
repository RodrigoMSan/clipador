@echo off
REM Liga o bot do Clipador e religa sozinho se ele cair.
cd /d "%~dp0"
:loop
echo [%date% %time%] Iniciando o Clipador...
set PYTHONIOENCODING=utf-8
python -u telegram_bot.py >> clipador.log 2>&1
if %errorlevel%==3 exit /b
echo [%date% %time%] O bot parou. Reiniciando em 30 segundos... >> clipador.log
timeout /t 30 /nobreak > nul
goto loop
