@echo off
title Clipador
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
chcp 65001 > nul

where python > nul 2>&1
if errorlevel 1 (
    echo Python nao encontrado. Instalando...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    echo.
    echo Python instalado. Feche esta janela e abra o "Abrir Clipador" de novo.
    pause
    exit /b
)
where ffmpeg > nul 2>&1
if errorlevel 1 (
    echo FFmpeg nao encontrado. Instalando...
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
    echo.
    echo FFmpeg instalado. Feche esta janela e abra o "Abrir Clipador" de novo.
    pause
    exit /b
)

fc /b requirements.txt .deps_ok > nul 2>&1
if errorlevel 1 (
    echo Instalando os componentes do Clipador...
    python -m pip install -q -r requirements.txt && copy /y requirements.txt .deps_ok > nul
)

if not exist ".env" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configurar.ps1"
    if not exist ".env" (
        echo A configuracao nao terminou. Abra de novo para tentar.
        pause
        exit /b
    )
)

:loop
echo.
echo Clipador ligado. Pode minimizar esta janela; para desligar, feche ela.
python -u telegram_bot.py
if %errorlevel%==3 (
    echo.
    echo O Clipador ja esta ligado em segundo plano. Nao precisa abrir de novo.
    pause
    exit /b
)
echo.
echo O bot parou. Religando em 10 segundos (feche a janela para nao religar)...
timeout /t 10 > nul
goto loop
